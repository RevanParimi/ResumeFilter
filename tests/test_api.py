"""API surface tests — TestClient over injected offline services (FR-6..FR-15)."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services
from tests.test_report_erasure_concurrency import database

RESUME = (
    "- Fine-tuned GPT-4 to improve accuracy.\n"
    "- Built production RAG at scale for support tickets.\n"
)


@pytest.mark.parametrize('phase', ['save', 'final'])
async def test_evaluation_publication_sql_leaves_unrelated_requests_responsive(database, settings, monkeypatch, phase):
    from threading import Event, get_ident
    import httpx
    from sqlalchemy import event
    from app.candidates.store import CandidateStore
    from tests.test_report_store import _report
    engine, factory = database
    services = make_services(settings, candidates=CandidateStore(factory))
    report, caller = _report(), get_ident()
    entered, release, finished, committed = Event(), Event(), Event(), Event()
    async def assess(**kwargs):
        assert get_ident() == caller
        await asyncio.sleep(0)
        return report
    def sql(conn, cursor, statement, parameters, context, many):
        query = statement.lower()
        if not entered.is_set() and ((phase == 'save' and query.lstrip().startswith('insert into reports'))
                or (phase == 'final' and committed.is_set() and 'from reports' in query)):
            entered.set()
            release.wait(3)
            finished.set()
    def commit(session):
        committed.set()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(app.state.engine, 'evaluate', assess)
            event.listen(engine, 'before_cursor_execute', sql)
            event.listen(factory, 'after_commit', commit)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.post('/evaluate', json={'resume_text': RESUME}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    assert not finished.is_set(), 'evaluation publication SQL blocked the event loop'
                finally:
                    release.set()
                    assert (await pending).status_code == 200
    finally:
        release.set()
        for target, name, listener in [(engine, 'before_cursor_execute', sql), (factory, 'after_commit', commit)]:
            if event.contains(target, name, listener):
                event.remove(target, name, listener)
        await services.aclose()


@pytest.mark.parametrize('phase', ['save', 'final'])
@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'late_failure'])
async def test_evaluation_publication_admission_ownership_and_recovery(database, settings, monkeypatch, log_output, phase, ending):
    from threading import Event, get_ident, current_thread
    import httpx
    from sqlalchemy import event
    from app.candidates.store import CandidateStore
    from tests.test_report_store import _report
    _, factory = database
    settings.evaluation_record_max_concurrent_requests = 1
    settings.evaluation_record_wait_seconds = .2 if ending in ('timeout', 'late_failure') else 20
    services = make_services(settings, candidates=CandidateStore(factory))
    report, caller, assessments, calls, sql_threads = _report(), get_ident(), [], [], set()
    entered, release = Event(), Event()
    save, get = services.report_store.save, services.report_store.get
    async def assess(**kwargs):
        assert get_ident() == caller
        assessments.append(True)
        await asyncio.sleep(0)
        return report
    def hold():
        calls.append(get_ident())
        entered.set()
        assert release.wait(15)
        if ending == 'late_failure':
            raise RuntimeError('synthetic-private-publication-failure')
    def write(value, **kwargs):
        if phase == 'save':
            hold()
        return save(value, **kwargs)
    def read(*args):
        if phase == 'final' and current_thread().name.startswith('evaluation-record'):
            hold()
        return get(*args)
    def begin(session, transaction, connection):
        assert session.info.setdefault('publication_owner', get_ident()) == get_ident()
        if current_thread().name.startswith('evaluation-record'):
            sql_threads.add(get_ident())
    def end(session, transaction):
        assert session.info.get('publication_owner', get_ident()) == get_ident()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(app.state.engine, 'evaluate', assess)
            monkeypatch.setattr(services.report_store, 'save', write)
            monkeypatch.setattr(services.report_store, 'get', read)
            event.listen(factory, 'after_begin', begin)
            event.listen(factory, 'after_transaction_end', end)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.post('/evaluate', json={'resume_text': RESUME}))
                try:
                    assert await asyncio.to_thread(entered.wait, 10)
                    assert (await http.get('/healthz')).status_code == 200
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as anonymous:
                        assert (await anonymous.post('/evaluate', json={'resume_text': RESUME})).status_code == 401
                    busy = await http.post('/evaluate', json={'resume_text': RESUME})
                    assert busy.status_code == 503 and busy.json() == {'detail': 'evaluation_record_capacity_exhausted'}
                    assert busy.headers['retry-after'] == '1' and 'set-cookie' not in busy.headers
                    snapshot = await http.get(f'/report/{report.id}')
                    assert snapshot.status_code == (404 if phase == 'save' else 200)
                    if ending in ('timeout', 'late_failure'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503 and response.json() == {'detail': {
                            'code': 'evaluation_record_pending', 'report_id': report.id}}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                        assert report.summary not in response.text
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    assert len(services.evaluation_records._active) == 1
                finally:
                    release.set()
                    results = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.evaluation_records._active:
                            await asyncio.sleep(.01)
                assert len(assessments) == 2  # Two deliberate POSTs; never an automatic replay.
                assert len(calls) == 1 and calls[0] != caller and sql_threads <= {calls[0]}
                if ending == 'release':
                    assert results[0].status_code == 200 and results[0].json()['id'] == report.id
                committed = ending != 'late_failure' or phase == 'final'
                assert (get(report.id) == report) == committed
                fresh = await http.get(f'/report/{report.id}')
                assert fresh.status_code == (200 if committed else 404)
                assert len(assessments) == 2  # GET recovery does not assess again.
                monkeypatch.setattr(services.report_store, 'save', save)
                monkeypatch.setattr(services.report_store, 'get', get)
                services.evaluation_records.close()
                closed = await http.post('/evaluate', json={'resume_text': RESUME})
                assert closed.status_code == 503 and closed.json() == {'detail': 'evaluation_record_executor_closed'}
                assert closed.headers['retry-after'] == '1' and 'set-cookie' not in closed.headers
    finally:
        release.set()
        await services.aclose()
        for name, listener in [('after_begin', begin), ('after_transaction_end', end)]:
            if event.contains(factory, name, listener):
                event.remove(factory, name, listener)
    assert 'synthetic-private-publication-failure' not in log_output.text


@pytest.mark.parametrize('case', ['save_commit', 'save_rollback', 'save_erase', 'final_read', 'final_erase'])
async def test_evaluation_publication_real_lock_commit_rollback_and_erasure(database, settings, monkeypatch, case):
    from threading import Event, current_thread
    import httpx
    from sqlalchemy import event, text
    from app.candidates.store import CandidateStore
    from app.reports.models import ReportRow
    from tests.test_report_store import _report
    engine, factory = database
    settings.evaluation_record_max_concurrent_requests = 1
    settings.evaluation_record_wait_seconds = .2
    services = make_services(settings, candidates=CandidateStore(factory))
    report, kept = _report(candidate_id='a'), _report(candidate_id='b')
    services.report_store.save(kept)
    final = case.startswith('final')
    entered, proceed, pids = Event(), Event(), []
    async def assess(**kwargs):
        return report
    get = services.report_store.get
    def read(*args):
        if final and current_thread().name.startswith('evaluation-record'):
            entered.set()
            assert proceed.wait(10)
        return get(*args)
    def sql(conn, cursor, statement, parameters, context, many):
        query = statement.lower()
        target = ('from reports' in query if final else query.lstrip().startswith('insert into reports'))
        if target and current_thread().name.startswith('evaluation-record'):
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            if not final:
                entered.set()
                assert proceed.wait(10)
    def flushed(session, context):
        if case == 'save_rollback' and current_thread().name.startswith('evaluation-record') and any(isinstance(row, ReportRow) for row in session.new):
            raise RuntimeError('synthetic report rollback after INSERT')
    app, blocker = create_app(services), None
    try:
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(app.state.engine, 'evaluate', assess)
            monkeypatch.setattr(services.report_store, 'get', read)
            event.listen(engine, 'before_cursor_execute', sql)
            event.listen(factory, 'after_flush', flushed)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.post('/evaluate', json={'resume_text': RESUME}))
                try:
                    assert await asyncio.to_thread(entered.wait, 10)
                    blocker = engine.connect()
                    if engine.dialect.name == 'sqlite':
                        blocker.exec_driver_sql('BEGIN EXCLUSIVE' if final else 'BEGIN IMMEDIATE')
                    else:
                        blocker.execute(text('LOCK TABLE reports IN ' + ('ACCESS EXCLUSIVE' if final else 'SHARE ROW EXCLUSIVE') + ' MODE'))
                    proceed.set()
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(8):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not pids or not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[-1]}):
                                    await asyncio.sleep(.01)
                    assert (await http.get('/healthz')).status_code == 200
                    response = await asyncio.wait_for(pending, 2)
                    assert response.status_code == 503 and response.json() == {'detail': {
                        'code': 'evaluation_record_pending', 'report_id': report.id}}
                    assert len(services.evaluation_records._active) == 1
                    if case == 'save_erase':
                        blocker.execute(text("DELETE FROM candidates WHERE id = 'a'"))
                        blocker.commit()
                    elif case == 'final_erase':
                        blocker.execute(text('DELETE FROM reports WHERE id = :rid'), {'rid': report.id})
                        blocker.commit()
                finally:
                    proceed.set()
                    if blocker is not None:
                        blocker.rollback()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.evaluation_records._active:
                            await asyncio.sleep(.01)
                committed = case in ('save_commit', 'final_read')
                assert (get(report.id) == report) == committed
                fresh = await http.get(f'/report/{report.id}')
                assert fresh.status_code == (200 if committed else 404)
                assert get(kept.id) == kept
    finally:
        proceed.set()
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        for target, name, listener in [(engine, 'before_cursor_execute', sql), (factory, 'after_flush', flushed)]:
            if event.contains(target, name, listener):
                event.remove(target, name, listener)
        await services.aclose()


REPORT_READS = [
    ('operator-report', '/report/{rid}', 'get'),
    ('operator-history', '/report/{rid}/outcomes', 'outcomes'),
    ('employer-report', '/screening/reports/{rid}', 'get_for_org'),
    ('employer-candidate', '/screening/candidates/a/reports', 'for_candidate_and_org'),
    ('employer-history', '/screening/reports/{rid}/outcomes', 'outcomes_for_org'),
]


def _report_read_setup(settings, factory):
    from app.candidates.store import CandidateStore
    from app.reports.schema import OutcomeRecord
    from tests.test_report_store import _report
    services = make_services(settings, candidates=CandidateStore(factory))
    org = services.ledger.create_organization('Report owner')
    other = services.ledger.create_organization('Other report owner')
    key = services.ledger.issue_api_key(org.id)
    other_key = services.ledger.issue_api_key(other.id)
    owned, kept = _report(candidate_id='a'), _report(candidate_id='b')
    services.report_store.save(owned, org_id=org.id)
    services.report_store.save(kept, org_id=other.id)
    services.report_store.add_outcome(OutcomeRecord(report_id=owned.id,
        outcome='inconclusive', recorded_by='organization', org_id=org.id, notes='Owned review'))
    return services, owned, kept, key, other_key


@pytest.mark.parametrize('case,path,method', REPORT_READS, ids=[r[0] for r in REPORT_READS])
async def test_report_read_sql_leaves_unrelated_requests_responsive(database, settings, case, path, method):
    import time
    from threading import Event
    import httpx
    from sqlalchemy import event
    engine, factory = database
    services, report, _, key, _ = _report_read_setup(settings, factory)
    entered, release, finished = Event(), Event(), Event()
    def sql(conn, cursor, statement, parameters, context, many):
        if 'from reports' in statement.lower() and not entered.is_set():
            entered.set()
            release.wait(3)
            finished.set()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                headers = {'X-Org-Key': key} if case.startswith('employer') else {}
                pending = asyncio.create_task(http.get(path.format(rid=report.id), headers=headers))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    start = time.monotonic()
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    assert not finished.is_set(), 'report read blocked the event loop'
                    assert time.monotonic() - start < 1
                finally:
                    release.set()
                    assert (await pending).status_code == 200
    finally:
        release.set()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)
        await services.aclose()


@pytest.mark.parametrize('door,change', [('operator', 'erase'), ('employer', 'erase'), ('employer', 'owner')])
def test_report_history_refuses_observed_erasure(database, settings, monkeypatch, request, door, change):
    _, factory = database
    services, report, kept, key, _ = _report_read_setup(settings, factory)
    request.addfinalizer(lambda: asyncio.run(services.aclose()))
    store = services.report_store
    from app.reports.models import ReportRow
    with factory() as session:
        other_org = session.get(ReportRow, kept.id).org_id
    method = 'outcomes' if door == 'operator' else 'outcomes_for_org'
    read = getattr(store, method)
    def erased(*args):
        loaded = read(*args)
        if change == 'erase':
            assert store.delete(report.id)
        else:
            store.save(report, org_id=other_org)
        return loaded
    monkeypatch.setattr(store, method, erased)
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as http:
        path = f'/report/{report.id}/outcomes' if door == 'operator' else f'/screening/reports/{report.id}/outcomes'
        response = http.get(path, headers={'X-Org-Key': key} if door == 'employer' else {})
        assert response.status_code == 404
        assert response.json() == {'detail': 'report not found'}
        assert store.get(kept.id) == kept


@pytest.mark.parametrize('case,path,method', REPORT_READS, ids=[r[0] for r in REPORT_READS])
@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'late_failure'])
async def test_report_read_admission_ownership_and_recovery(database, settings, monkeypatch, log_output, case, path, method, ending):
    from threading import Event, get_ident
    import httpx
    from sqlalchemy import event
    _, factory = database
    settings.report_record_max_concurrent_requests = 1
    settings.report_record_wait_seconds = .2 if ending in ('timeout', 'late_failure') else 20
    services, report, kept, key, other_key = _report_read_setup(settings, factory)
    caller, calls = get_ident(), []
    entered, release = Event(), Event()
    original = getattr(services.report_store, method)
    def observed(*args):
        calls.append(get_ident())
        entered.set()
        assert release.wait(15)
        if ending == 'late_failure':
            raise RuntimeError('synthetic-private-report-read-error')
        return original(*args)
    def begin(session, transaction, connection):
        assert session.info.setdefault('read_owner', get_ident()) == get_ident()
    def end(session, transaction):
        assert session.info.get('read_owner', get_ident()) == get_ident()
    app = create_app(services)
    headers = {'X-Org-Key': key} if case.startswith('employer') else {}
    path = path.format(rid=report.id)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                expected = (await http.get(path, headers=headers)).json()
                monkeypatch.setattr(services.report_store, method, observed)
                event.listen(factory, 'after_begin', begin)
                event.listen(factory, 'after_transaction_end', end)
                pending = asyncio.create_task(http.get(path, headers=headers))
                try:
                    assert await asyncio.to_thread(entered.wait, 10)
                    assert (await http.get('/healthz')).status_code == 200
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as anonymous:
                        assert (await anonymous.get(path)).status_code == 401
                    for peer_path, peer_headers in [(f'/report/{kept.id}', {}),
                            (f'/screening/reports/{kept.id}', {'X-Org-Key': other_key})]:
                        busy = await http.get(peer_path, headers=peer_headers)
                        assert busy.status_code == 503 and busy.json() == {'detail': 'report_record_capacity_exhausted'}
                        assert busy.headers['retry-after'] == '1' and 'set-cookie' not in busy.headers
                    if ending in ('timeout', 'late_failure'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503 and response.json() == {'detail': 'report_record_pending'}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                finally:
                    release.set()
                    responses = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.report_records._active:
                            await asyncio.sleep(.01)
                assert len(calls) == 1 and calls[0] != caller
                if ending == 'release':
                    assert responses[0].status_code == 200 and responses[0].json() == expected
                monkeypatch.setattr(services.report_store, method, original)
                services.report_records._wait_seconds = 20
                fresh = await http.get(path, headers=headers)
                assert fresh.status_code == 200 and fresh.json() == expected
                assert services.report_store.get(kept.id) == kept
                assert (await http.get(f'/screening/reports/{report.id}', headers={'X-Org-Key': other_key})).status_code == 404
                assert (await http.get('/screening/candidates/a/reports', headers={'X-Org-Key': other_key})).json() == []
                services.report_records.close()
                closed = await http.get(path, headers=headers)
                assert closed.status_code == 503 and closed.json() == {'detail': 'report_record_executor_closed'}
                assert closed.headers['retry-after'] == '1' and 'set-cookie' not in closed.headers
    finally:
        release.set()
        await services.aclose()
        for name, listener in [('after_begin', begin), ('after_transaction_end', end)]:
            if event.contains(factory, name, listener):
                event.remove(factory, name, listener)
    assert 'synthetic-private-report-read-error' not in log_output.text


@pytest.mark.parametrize('case,path,method', REPORT_READS, ids=[r[0] for r in REPORT_READS])
@pytest.mark.parametrize('erase', [False, True])
async def test_report_reads_real_lock_and_erasure(database, settings, case, path, method, erase):
    import time
    from threading import Event
    import httpx
    from sqlalchemy import event, text
    engine, factory = database
    settings.report_record_max_concurrent_requests = 1
    settings.report_record_wait_seconds = .2
    services, report, kept, key, _ = _report_read_setup(settings, factory)
    entered, proceed, pids = Event(), Event(), []
    def sql(conn, cursor, statement, parameters, context, many):
        if 'from reports' in statement.lower() and not entered.is_set():
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
            assert proceed.wait(10)
    app = create_app(services)
    blocker = None
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            headers = {'X-Org-Key': key} if case.startswith('employer') else {}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get(path.format(rid=report.id), headers=headers))
                try:
                    assert await asyncio.to_thread(entered.wait, 10)
                    # Authenticate before a database-wide SQLite read lock.
                    # Hold the worker just before its report SELECT, then use
                    # a real competing connection to block that SQL operation.
                    blocker = engine.connect()
                    if engine.dialect.name == 'sqlite':
                        blocker.exec_driver_sql('BEGIN EXCLUSIVE')
                    else:
                        blocker.execute(text('LOCK TABLE reports IN ACCESS EXCLUSIVE MODE'))
                    proceed.set()
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(8):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    start = time.monotonic()
                    assert (await http.get('/healthz')).status_code == 200
                    assert time.monotonic() - start < 1
                    response = await asyncio.wait_for(pending, 2)
                    assert response.status_code == 503 and response.json() == {'detail': 'report_record_pending'}
                    busy = await http.get(f'/report/{kept.id}')
                    assert busy.status_code == 503 and busy.json() == {'detail': 'report_record_capacity_exhausted'}
                    if erase:
                        blocker.execute(text('DELETE FROM reports WHERE id = :id'), {'id': report.id})
                        blocker.commit()
                finally:
                    proceed.set()
                    if blocker is not None:
                        blocker.rollback()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.report_records._active:
                            await asyncio.sleep(.01)
                services.report_records._wait_seconds = 20
                fresh = await http.get(path.format(rid=report.id), headers=headers)
                assert fresh.status_code == (404 if erase and case != 'employer-candidate' else 200)
                if erase and case == 'employer-candidate':
                    assert fresh.json() == []
                assert services.report_store.get(kept.id) == kept
    finally:
        proceed.set()
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)
        await services.aclose()


@pytest.mark.parametrize('door', ['operator', 'employer'])
@pytest.mark.parametrize('phase', ['lookup', 'append', 'observer'])
async def test_outcome_write_sql_and_observer_leave_unrelated_requests_responsive(database, settings, door, phase):
    from threading import Event
    import httpx
    from sqlalchemy import event
    engine, factory = database
    services, report, _, key, _ = _report_read_setup(settings, factory)
    entered, release, finished = Event(), Event(), Event()
    def hold():
        entered.set()
        release.wait(3)
        finished.set()
    def sql(conn, cursor, statement, parameters, context, many):
        query = statement.lower()
        if not entered.is_set() and ((phase == 'lookup' and 'from reports' in query)
                or (phase == 'append' and query.lstrip().startswith('insert into outcomes'))):
            hold()
    observe = services.flywheel.log
    def observer(record):
        if phase == 'observer' and record.get('record_type') == 'outcome':
            hold()
        observe(record)
    services.flywheel.log = observer
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                path = f'/report/{report.id}/outcome' if door == 'operator' else f'/screening/reports/{report.id}/outcome'
                pending = asyncio.create_task(http.post(path, headers={'X-Org-Key': key} if door == 'employer' else {},
                    json={'outcome': 'inconclusive', 'notes': 'Synthetic review'}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    assert not finished.is_set(), 'outcome SQL/observer blocked the event loop'
                finally:
                    release.set()
                    assert (await pending).status_code == 200
    finally:
        release.set()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)
        await services.aclose()


@pytest.mark.parametrize('door', ['operator', 'employer'])
@pytest.mark.parametrize('phase', ['lookup', 'append', 'observer'])
@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'late_failure'])
async def test_outcome_write_admission_ownership_and_recovery(database, settings, monkeypatch, log_output, door, phase, ending):
    from threading import Event, get_ident, current_thread
    import httpx
    from sqlalchemy import event
    _, factory = database
    settings.outcome_record_max_concurrent_requests = 1
    settings.outcome_record_wait_seconds = .2 if ending in ('timeout', 'late_failure') else 20
    services, report, kept, key, other_key = _report_read_setup(settings, factory)
    caller, calls, observed, sql_threads = get_ident(), [], [], set()
    entered, release = Event(), Event()
    def hold():
        calls.append(get_ident())
        entered.set()
        assert release.wait(15)
        if ending == 'late_failure':
            raise RuntimeError('synthetic-private-outcome-error')
    read_method = 'get' if door == 'operator' else 'get_for_org'
    read, append, observe = getattr(services.report_store, read_method), services.report_store.add_outcome, services.flywheel.log
    def lookup(*args, **kwargs):
        if phase == 'lookup' and current_thread().name.startswith('outcome-record'):
            hold()
        return read(*args, **kwargs)
    def write(*args, **kwargs):
        if phase == 'append':
            hold()
        return append(*args, **kwargs)
    def observer(record):
        if record.get('record_type') == 'outcome':
            observed.append(record)
            if phase == 'observer':
                hold()
        return observe(record)
    def begin(session, transaction, connection):
        assert session.info.setdefault('outcome_owner', get_ident()) == get_ident()
        if current_thread().name.startswith('outcome-record'):
            sql_threads.add(get_ident())
    def end(session, transaction):
        assert session.info.get('outcome_owner', get_ident()) == get_ident()
    app = create_app(services)
    path = f'/report/{report.id}/outcome' if door == 'operator' else f'/screening/reports/{report.id}/outcome'
    headers = {'X-Org-Key': key} if door == 'employer' else {}
    body = {'outcome': 'verified_genuine', 'notes': 'Private synthetic review draft'}
    try:
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(services.report_store, read_method, lookup)
            monkeypatch.setattr(services.report_store, 'add_outcome', write)
            monkeypatch.setattr(services.flywheel, 'log', observer)
            event.listen(factory, 'after_begin', begin)
            event.listen(factory, 'after_transaction_end', end)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.post(path, headers=headers, json=body))
                try:
                    assert await asyncio.to_thread(entered.wait, 10)
                    assert (await http.get('/healthz')).status_code == 200
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as anonymous:
                        assert (await anonymous.post(path, json=body)).status_code == 401
                    for peer_path, peer_headers in [(f'/report/{kept.id}/outcome', {}),
                            (f'/screening/reports/{kept.id}/outcome', {'X-Org-Key': other_key})]:
                        busy = await http.post(peer_path, headers=peer_headers, json=body)
                        assert busy.status_code == 503 and busy.json() == {'detail': 'outcome_record_capacity_exhausted'}
                        assert busy.headers['retry-after'] == '1' and 'set-cookie' not in busy.headers
                    # Reads have separate admission even after SQL commits but
                    # before an optional observer finishes or fails.
                    history = await http.get(f'/report/{report.id}/outcomes')
                    assert history.status_code == 200
                    assert len(history.json()['outcomes']) == (2 if phase == 'observer' else 1)
                    if ending in ('timeout', 'late_failure'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503 and response.json() == {'detail': 'outcome_record_pending'}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    # A caller's timeout/cancel cannot release this admission.
                    busy = await http.post(path, headers=headers, json=body)
                    assert busy.json() == {'detail': 'outcome_record_capacity_exhausted'}
                finally:
                    release.set()
                    responses = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.outcome_records._active:
                            await asyncio.sleep(.01)
                assert len(calls) == 1 and calls[0] != caller
                assert sql_threads <= {calls[0]}
                if ending == 'release':
                    assert responses[0].status_code == 200
                saved = services.report_store.outcomes(report.id)
                committed = ending != 'late_failure' or phase == 'observer'
                assert len(saved) == (2 if committed else 1)
                if committed:
                    rec = saved[-1]
                    assert rec.notes == body['notes'] and rec.claim_id is None
                    assert rec.recorded_by.value == ('operator' if door == 'operator' else 'organization')
                    assert (rec.org_id is not None) == (door == 'employer')
                    assert rec.recorded_by_org_user_id is None  # API-key principal, not a user session.
                    assert observed == [{'record_type': 'outcome', 'report_id': report.id, 'claim_id': None,
                        'outcome': body['outcome'], 'recorded_by': rec.recorded_by.value, 'org_id': rec.org_id}]
                else:
                    assert observed == []
                monkeypatch.setattr(services.report_store, read_method, read)
                monkeypatch.setattr(services.report_store, 'add_outcome', append)
                monkeypatch.setattr(services.flywheel, 'log', observe)
                services.outcome_records._wait_seconds = 20
                fresh = await http.get(f'/report/{report.id}/outcomes')
                assert len(fresh.json()['outcomes']) == len(saved)
                assert (await http.post(f'/screening/reports/{report.id}/outcome',
                    headers={'X-Org-Key': other_key}, json=body)).status_code == 404
                assert (await http.post(path, headers=headers, json={**body, 'claim_id': 'foreign-claim'})).status_code == 422
                assert len(services.report_store.outcomes(report.id)) == len(saved)
                # A new deliberate POST is additive, not an idempotent replay.
                assert (await http.post(path, headers=headers, json=body)).status_code == 200
                assert len(services.report_store.outcomes(report.id)) == len(saved) + 1
                assert services.report_store.outcomes(kept.id) == []
                services.outcome_records.close()
                closed = await http.post(path, headers=headers, json=body)
                assert closed.status_code == 503 and closed.json() == {'detail': 'outcome_record_executor_closed'}
                assert closed.headers['retry-after'] == '1' and 'set-cookie' not in closed.headers
    finally:
        release.set()
        await services.aclose()
        for name, listener in [('after_begin', begin), ('after_transaction_end', end)]:
            if event.contains(factory, name, listener):
                event.remove(factory, name, listener)
    assert 'synthetic-private-outcome-error' not in log_output.text
    assert body['notes'] not in log_output.text


@pytest.mark.parametrize('door', ['operator', 'employer'])
@pytest.mark.parametrize('failure', ['validation', 'admission', 'pending'])
def test_outcome_observer_failure_after_commit_is_not_a_definite_refusal(database, settings, monkeypatch, request, door, failure):
    from app.core.blocking import ExecutionPending, ExecutionUnavailable
    from app.reports.outcomes import OutcomeRefused
    _, factory = database
    services, report, _, key, _ = _report_read_setup(settings, factory)
    request.addfinalizer(lambda: asyncio.run(services.aclose()))
    def observe(record):
        if failure == 'validation':
            raise OutcomeRefused('synthetic', 'synthetic-private-observer-error')
        if failure == 'admission':
            raise ExecutionUnavailable('outcome_record_capacity_exhausted')
        raise ExecutionPending()
    monkeypatch.setattr(services.flywheel, 'log', observe)
    with TestClient(create_app(services), headers=ADMIN_HEADERS, raise_server_exceptions=False) as http:
        path = f'/report/{report.id}/outcome' if door == 'operator' else f'/screening/reports/{report.id}/outcome'
        response = http.post(path, headers={'X-Org-Key': key} if door == 'employer' else {}, json={'outcome': 'inconclusive'})
        assert response.status_code == 500
        assert response.json()['detail'] == 'internal_error'
        assert len(http.get(f'/report/{report.id}/outcomes').json()['outcomes']) == 2
        assert len(services.report_store.outcomes(report.id)) == 2
    assert 'synthetic-private-observer-error' not in response.text


@pytest.mark.parametrize('door', ['operator', 'employer'])
@pytest.mark.parametrize('resolution', ['commit', 'rollback', 'erase'])
async def test_outcome_write_real_lock_late_commit_rollback_and_erasure(database, settings, door, resolution):
    from threading import Event, current_thread
    import time
    import httpx
    from sqlalchemy import event, text
    from app.reports.models import OutcomeRow
    engine, factory = database
    settings.outcome_record_max_concurrent_requests = 1
    settings.outcome_record_wait_seconds = .2
    services, report, kept, key, _ = _report_read_setup(settings, factory)
    entered, proceed, pids = Event(), Event(), []
    def sql(conn, cursor, statement, parameters, context, many):
        if statement.lower().lstrip().startswith('insert into outcomes') and not entered.is_set():
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
            assert proceed.wait(10)
    def flushed(session, context):
        if resolution == 'rollback' and current_thread().name.startswith('outcome-record') and any(isinstance(row, OutcomeRow) for row in session.new):
            raise RuntimeError('synthetic rollback after outcome SQL')
    app, blocker = create_app(services), None
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            event.listen(factory, 'after_flush', flushed)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                path = f'/report/{report.id}/outcome' if door == 'operator' else f'/screening/reports/{report.id}/outcome'
                pending = asyncio.create_task(http.post(path, headers={'X-Org-Key': key} if door == 'employer' else {}, json={'outcome': 'inconclusive'}))
                try:
                    assert await asyncio.to_thread(entered.wait, 10)
                    blocker = engine.connect()
                    if engine.dialect.name == 'sqlite':
                        blocker.exec_driver_sql('BEGIN IMMEDIATE')
                    else:
                        blocker.execute(text('LOCK TABLE outcomes IN ACCESS EXCLUSIVE MODE'))
                    proceed.set()
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(8):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    start = time.monotonic()
                    assert (await http.get('/healthz')).status_code == 200
                    assert time.monotonic() - start < 1
                    response = await asyncio.wait_for(pending, 2)
                    assert response.status_code == 503 and response.json() == {'detail': 'outcome_record_pending'}
                    # Refusal happens before lookup, including another door.
                    busy = await http.post(f'/report/{kept.id}/outcome', json={'outcome': 'inconclusive'})
                    assert busy.json() == {'detail': 'outcome_record_capacity_exhausted'}
                    if resolution == 'erase':
                        blocker.execute(text('DELETE FROM reports WHERE id = :id'), {'id': report.id})
                        blocker.commit()
                finally:
                    proceed.set()
                    if blocker is not None:
                        blocker.rollback()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.outcome_records._active:
                            await asyncio.sleep(.01)
                assert len(services.report_store.outcomes(report.id)) == {'commit': 2, 'rollback': 1, 'erase': 0}[resolution]
                fresh = await http.get(f'/report/{report.id}/outcomes')
                assert fresh.status_code == (404 if resolution == 'erase' else 200)
                assert services.report_store.get(kept.id) == kept
    finally:
        proceed.set()
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        for target, name, listener in [(engine, 'before_cursor_execute', sql), (factory, 'after_flush', flushed)]:
            if event.contains(target, name, listener):
                event.remove(target, name, listener)
        await services.aclose()


async def _body_gate(events, *, headers=(), limit=8, trace=None, scope_type="http"):
    """Drive actual ASGI receive events, including events left unread on refusal."""
    from app.core.request_body import RequestBodyLimitMiddleware
    trace = trace if trace is not None else {"read": [], "forwarded": [], "sent": []}
    pending = iter(events)
    async def receive():
        message = next(pending)
        trace["read"].append(message)
        if isinstance(message, BaseException):
            raise message
        return message
    async def send(message):
        trace["sent"].append(message)
    async def downstream(scope, receive, send):
        if scope["type"] != "http":
            trace["forwarded"].append(scope["type"])
            return
        message = await receive()
        trace["forwarded"].append(message)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": message["body"]})
    await RequestBodyLimitMiddleware(downstream, max_bytes=limit)(
        {"type": scope_type, "headers": headers}, receive, send)
    return trace


def _chunks(*values):
    return [{"type": "http.request", "body": value, "more_body": i < len(values) - 1}
            for i, value in enumerate(values)]


@pytest.mark.parametrize("chunks", [(b"",), (b"12345678",), (b"", b"123", b"", b"45678"),
                                     ("éé".encode(), "éé".encode())])
async def test_body_budget_accepts_equality_and_replays_exact_bytes(chunks):
    trace = await _body_gate(_chunks(*chunks))
    expected = b"".join(chunks)
    assert trace["forwarded"] == [{"type": "http.request", "body": expected, "more_body": False}]
    assert trace["sent"][-1]["body"] == expected


@pytest.mark.parametrize("headers", [[], [(b"content-length", b"1")],
    [(b"content-length", b"garbage")], [(b"content-length", b"0" * 5000 + b"1")]])
async def test_streamed_body_budget_counts_actual_bytes_and_stops_early(headers):
    events = _chunks(b"1234", b"56789", b"must-remain-unread")
    trace = await _body_gate(events, headers=headers)
    assert trace["read"] == events[:2]
    assert trace["forwarded"] == []
    assert trace["sent"][0]["status"] == 413
    assert json.loads(trace["sent"][-1]["body"]) == {
        "detail": "request body exceeds max_request_body_bytes=8"}


@pytest.mark.parametrize("headers", [[(b"content-length", b"9")],
    [(b"Content-Length", b"0009")], [(b"content-length", b"9" * 5000)],
    [(b"content-length", b"1"), (b"content-length", b"9")]])
async def test_declared_oversize_body_refuses_without_receiving(headers):
    trace = await _body_gate([], headers=headers)
    assert trace["read"] == trace["forwarded"] == []
    assert trace["sent"][0]["status"] == 413


async def test_many_empty_chunks_do_not_change_payload_or_budget():
    trace = await _body_gate(_chunks(*([b""] * 1000), b"12345678"),
                             headers=[(b"content-length", b"0" * 5000 + b"8")])
    assert trace["sent"][0]["status"] == 200
    assert trace["forwarded"][0]["body"] == b"12345678"


async def test_body_disconnect_stops_without_downstream_and_completes_outer_middleware():
    events = _chunks(b"partial", b"unused")[:1] + [{"type": "http.disconnect"}]
    trace = await _body_gate(events)
    assert trace["read"] == events
    assert trace["forwarded"] == []
    assert trace["sent"][0]["status"] == 400
    assert json.loads(trace["sent"][-1]["body"]) == {"detail": "request_body_incomplete"}


async def test_body_read_cancellation_propagates_without_downstream_or_response():
    trace = {"read": [], "forwarded": [], "sent": []}
    with pytest.raises(asyncio.CancelledError):
        await _body_gate(_chunks(b"partial", b"unused")[:1] + [asyncio.CancelledError()], trace=trace)
    assert trace["forwarded"] == trace["sent"] == []


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
async def test_body_gate_preserves_non_http_scopes(scope_type):
    trace = await _body_gate([], scope_type=scope_type)
    assert trace["forwarded"] == [scope_type]
    assert trace["read"] == trace["sent"] == []


async def test_body_replay_then_delegates_disconnect_to_the_original_receive():
    from app.core.request_body import RequestBodyLimitMiddleware
    events = iter(_chunks(b"12345678") + [{"type": "http.disconnect"}])
    forwarded = []
    async def receive():
        return next(events)
    async def send(message):
        pass
    async def downstream(scope, receive, send):
        forwarded.extend([await receive(), await receive()])
    await RequestBodyLimitMiddleware(downstream, max_bytes=8)({"type": "http"}, receive, send)
    assert forwarded == [{"type": "http.request", "body": b"12345678", "more_body": False},
                         {"type": "http.disconnect"}]


@pytest.fixture
def api(services):
    """TestClient wired to fully offline services (NullLLM, in-memory stores)."""
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False, headers=ADMIN_HEADERS) as client:
        yield client, services


def _evaluate(client) -> dict:
    resp = client.post("/evaluate", json={"resume_text": RESUME})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── persistence (FR-6) ────────────────────────────────────────────────────────
def test_evaluate_then_get_report(api):
    client, services = api
    report = _evaluate(client)
    assert report["advisory"] is True and report["human_review_required"] is True

    got = client.get(f"/report/{report['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == report["id"]
    # Persisted through the store, not a per-process dict.
    assert services.report_store.get(report["id"]) is not None


def test_get_missing_report_404(api):
    client, _ = api
    assert client.get("/report/rep_nope").status_code == 404


# ── outcome loop (FR-7, FR-8) ─────────────────────────────────────────────────
def test_report_level_outcome_recorded_and_fed_to_flywheel(api):
    client, services = api
    report = _evaluate(client)

    resp = client.post(
        f"/report/{report['id']}/outcome",
        json={"outcome": "inconclusive", "notes": "screen pending"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["report_id"] == report["id"]
    assert body["claim_id"] is None
    assert body["outcome"] == "inconclusive"

    wheel_outcomes = [
        r for r in services.flywheel.records if r.get("record_type") == "outcome"
    ]
    assert len(wheel_outcomes) == 1
    assert wheel_outcomes[0]["report_id"] == report["id"]
    # The test observer still receives labels/provenance, never human notes.
    # Production retains only SQL outcomes, not a second event stream.
    assert "notes" not in wheel_outcomes[0]
    assert "screen pending" not in str(wheel_outcomes[0])
    # It gains provenance instead, which is what a calibration harness needs.
    assert wheel_outcomes[0]["recorded_by"] == "operator"
    assert wheel_outcomes[0]["org_id"] is None


def test_the_admin_door_enforces_the_same_notes_cap_as_the_org_one(api):
    """One rule, two doors. Fixing one entry point and leaving the other is
    this repo's signature defect -- so the operator's route gained the bound in
    the same commit that gave the customer a route at all."""
    client, services = api
    report = _evaluate(client)
    over = "x" * (services.settings.max_outcome_notes_chars + 1)

    resp = client.post(
        f"/report/{report['id']}/outcome",
        json={"outcome": "inconclusive", "notes": over},
    )
    assert resp.status_code == 422
    assert "max_outcome_notes_chars" in resp.text
    assert services.report_store.outcomes(report["id"]) == [], (
        "a refused outcome must write nothing"
    )


def test_an_operator_recorded_outcome_says_so(api):
    client, services = api
    report = _evaluate(client)
    client.post(f"/report/{report['id']}/outcome", json={"outcome": "inconclusive"})

    stored = services.report_store.outcomes(report["id"])[0]
    assert stored.recorded_by.value == "operator"
    assert stored.org_id is None
    assert stored.recorded_by_org_user_id is None


def test_claim_level_outcome(api):
    client, _ = api
    report = _evaluate(client)
    claim_id = report["verdicts"][0]["claim_id"]

    resp = client.post(
        f"/report/{report['id']}/outcome",
        json={"outcome": "verified_fabricated", "claim_id": claim_id},
    )
    assert resp.status_code == 200
    assert resp.json()["claim_id"] == claim_id

    outs = client.get(f"/report/{report['id']}/outcomes")
    assert outs.status_code == 200
    listed = outs.json()["outcomes"]
    assert len(listed) == 1 and listed[0]["outcome"] == "verified_fabricated"


def test_outcome_unknown_claim_422(api):
    client, _ = api
    report = _evaluate(client)
    resp = client.post(
        f"/report/{report['id']}/outcome",
        json={"outcome": "verified_genuine", "claim_id": "clm_not_there"},
    )
    assert resp.status_code == 422


def test_outcome_unknown_report_404(api):
    client, _ = api
    resp = client.post(
        "/report/rep_nope/outcome", json={"outcome": "verified_genuine"}
    )
    assert resp.status_code == 404


# ── hardening (FR-11..FR-15) ──────────────────────────────────────────────────
def test_oversize_resume_text_422(api):
    client, services = api
    too_big = "x" * (services.settings.max_resume_chars + 1)
    resp = client.post("/evaluate", json={"resume_text": too_big})
    assert resp.status_code == 422
    assert "max_resume_chars" in resp.text


def test_oversize_pdf_b64_422(api):
    client, services = api
    too_big = "A" * (services.settings.max_pdf_b64_chars + 1)
    resp = client.post("/evaluate", json={"resume_pdf_b64": too_big})
    assert resp.status_code == 422
    assert "max_pdf_b64_chars" in resp.text


def test_unknown_domain_422_lists_registered(api):
    client, _ = api
    resp = client.post(
        "/evaluate", json={"resume_text": RESUME, "domain": "astrology"}
    )
    assert resp.status_code == 422
    assert "genai" in resp.text


def test_request_id_generated_and_echoed(api):
    client, _ = api
    generated = client.get("/healthz")
    assert generated.headers.get("x-request-id", "").startswith("req_")

    echoed = client.get("/healthz", headers={"X-Request-ID": "trace-abc-123"})
    assert echoed.headers["x-request-id"] == "trace-abc-123"


def test_healthz_payload(api):
    client, _ = api
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["llm_mode"] == "null"  # offline fixture has no key
    assert "genai" in body["domains"]
    assert body["version"] and body["env"] == "local"


def test_domains_endpoint(api):
    client, _ = api
    body = client.get("/domains").json()
    keys = {d["key"] for d in body}
    assert "genai" in keys
    genai = next(d for d in body if d["key"] == "genai")
    assert genai["display_name"] and "fine_tuning" in genai["claim_types"]


def test_auth_enforced_when_key_configured(settings, flywheel):
    from pydantic import SecretStr

    locked = settings.model_copy(update={"api_auth_key": SecretStr("s3cret")})
    services = make_services(locked, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/evaluate", json={"resume_text": RESUME}).status_code == 401
        assert client.get("/report/rep_x").status_code == 401
        # healthz and root stay open for probes/humans.
        assert client.get("/healthz").status_code == 200
        assert client.get("/").status_code == 200
        ok = client.post(
            "/evaluate", json={"resume_text": RESUME}, headers={"X-API-Key": "s3cret"}
        )
        assert ok.status_code == 200


def test_auth_refuses_when_no_key_is_sent(api):
    """S8.1: this was `test_auth_open_by_default`, and it was the test PINNING
    the fail-open defect in place. The suite now runs with a configured admin
    key, and a client that sends none is refused."""
    client, _ = api
    bare = TestClient(client.app, raise_server_exceptions=False)
    with bare:
        assert bare.post("/evaluate", json={"resume_text": RESUME}).status_code == 401


def test_unhandled_error_returns_generic_500(api):
    client, _ = api

    class Boom:
        async def evaluate(self, **kwargs):
            raise RuntimeError("secret internals leak")

    client.app.state.engine = Boom()
    resp = client.post("/evaluate", json={"resume_text": RESUME})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "internal_error"
    assert "secret internals" not in resp.text
