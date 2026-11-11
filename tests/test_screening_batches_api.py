"""Screening batches api regressions, grouped by behavior."""

from __future__ import annotations

import base64
import asyncio
from contextlib import contextmanager
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from tests.conftest import ADMIN_HEADERS
from app.screening.models import BatchItemRow
from app.screening.schema import ItemStatus
from tests.test_screening_service import _PausedEngine
from tests.test_report_erasure_concurrency import database


BATCH_READS = [
    ('detail', '/screening/batches/{bid}', 'get'),
    ('list', '/screening/batches', 'list'),
    ('queue', '/screening/batches/{bid}/queue', 'queue'),
    ('summary', '/screening/batches/{bid}/summary', 'summary'),
]

BATCH_MUTATIONS = [('retry', 'post', '/retry'), ('delete', 'delete', '')]


def _batch_mutation_setup(settings, factory, resume):
    from datetime import datetime, timezone
    from sqlalchemy import select
    setup = _batch_read_setup(settings, factory, resume)
    services, org, _, bid, _, _, _ = setup
    services.screening._store.add_items(org, bid, texts=[resume, resume])
    with factory() as session:
        rows = session.scalars(select(BatchItemRow).where(BatchItemRow.batch_id == bid)
            .order_by(BatchItemRow.created_at, BatchItemRow.id)).all()
        for row in rows[:2]:
            row.status, row.error = 'failed', 'internal_error'
        rows[1].raw_text = ''
        rows[2].status, rows[2].claimed_at = 'processing', datetime.now(timezone.utc)
        rows[3].status, rows[3].raw_text = 'done', ''
        session.commit()
    return setup


@pytest.mark.parametrize('action,verb,suffix', BATCH_MUTATIONS, ids=['retry', 'delete'])
async def test_batch_mutation_sql_leaves_unrelated_requests_responsive(database, settings, genuine_resume, action, verb, suffix):
    from threading import Event
    from sqlalchemy import event
    engine, factory = database
    services, _, key, bid, _, _, _ = _batch_mutation_setup(settings, factory, genuine_resume)
    entered, release, finished = Event(), Event(), Event()
    needle = 'update batch_items' if action == 'retry' else 'delete from screening_batches'
    def sql(conn, cursor, statement, parameters, context, many):
        if needle in statement.lower() and not entered.is_set():
            entered.set()
            release.wait(3)
            finished.set()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.request(verb, '/screening/batches/' + bid + suffix, headers={'X-Org-Key': key}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    assert not finished.is_set(), 'batch mutation SQL blocked the event loop'
                finally:
                    release.set()
                    assert (await pending).status_code == 200
    finally:
        release.set()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)
        await services.aclose()


@pytest.mark.parametrize('action,verb,suffix', BATCH_MUTATIONS, ids=['retry', 'delete'])
def test_batch_mutation_refuses_ownership_change_before_write(database, settings, genuine_resume, action, verb, suffix):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, current_thread
    from sqlalchemy import event, text
    engine, factory = database
    services, org, _, bid, other, _, _ = _batch_mutation_setup(settings, factory, genuine_resume)
    entered, release = Event(), Event()
    needle = 'screening_erasure_state' if action == 'retry' else 'delete from screening_batches'
    def sql(conn, cursor, statement, parameters, context, many):
        if needle in statement.lower() and current_thread().name.startswith('scope-change') and not entered.is_set():
            entered.set()
            assert release.wait(10)
    event.listen(engine, 'before_cursor_execute', sql)
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='scope-change') as pool:
            pending = pool.submit(getattr(services.screening, action), org, bid)
            try:
                assert entered.wait(8)
                with engine.begin() as connection:
                    connection.execute(text('UPDATE screening_batches SET org_id = :org WHERE id = :bid'), {'org': other, 'bid': bid})
            finally:
                release.set()
            assert pending.result(timeout=10) == (None if action == 'retry' else False)
        assert services.screening.get(org, bid) is None
        assert services.screening.get(other, bid).counts.model_dump() == {'pending': 0, 'processing': 1, 'done': 1, 'failed': 2}
    finally:
        release.set()
        event.remove(engine, 'before_cursor_execute', sql)
        asyncio.run(services.aclose())


@pytest.mark.parametrize('action,verb,suffix', BATCH_MUTATIONS, ids=['retry', 'delete'])
@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'rollback'])
async def test_batch_mutation_admission_owning_sessions_and_recovery(database, settings, genuine_resume, monkeypatch, log_output, action, verb, suffix, ending):
    from threading import Event, get_ident, current_thread
    from sqlalchemy import event
    engine, factory = database
    settings.batch_mutation_max_concurrent_requests = 1
    settings.batch_mutation_wait_seconds = .2 if ending in ('timeout', 'rollback') else 20
    services, org, key, bid, other, other_key, kept = _batch_mutation_setup(settings, factory, genuine_resume)
    original = getattr(services.screening, action)
    entered, release, calls, sql_threads = Event(), Event(), [], set()
    caller = get_ident()
    def operation(*args):
        calls.append(get_ident())
        entered.set()
        assert release.wait(10)
        return original(*args)
    def begin(session, transaction, connection):
        assert session.info.setdefault('mutation_owner', get_ident()) == get_ident()
        if current_thread().name.startswith('batch-mutation'):
            sql_threads.add(get_ident())
    def end(session, transaction):
        assert session.info.get('mutation_owner', get_ident()) == get_ident()
    def commit(session):
        if ending == 'rollback' and current_thread().name.startswith('batch-mutation'):
            session.flush()
            raise RuntimeError('synthetic-private-batch-mutation-error')
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(services.screening, action, operation)
            for name, listener in [('after_begin', begin), ('after_transaction_end', end), ('before_commit', commit)]:
                event.listen(factory, name, listener)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test', headers=ADMIN_HEADERS) as http:
                path = '/screening/batches/' + bid
                pending = asyncio.create_task(http.request(verb, path + suffix, headers={'X-Org-Key': key}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    read = await http.get(path, headers={'X-Org-Key': key})
                    assert read.status_code == 200 and read.json()['counts']['failed'] == 2
                    for _, peer_verb, peer_suffix in BATCH_MUTATIONS:
                        refused = await http.request(peer_verb, '/screening/batches/' + kept + peer_suffix, headers={'X-Org-Key': other_key})
                        assert refused.status_code == 503 and refused.json() == {'detail': 'batch_mutation_capacity_exhausted'}
                        assert refused.headers['retry-after'] == '1' and 'set-cookie' not in refused.headers
                    if ending in ('timeout', 'rollback'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503 and response.json() == {'detail': 'batch_mutation_pending'}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    assert len(services.batch_mutations._active) == 1
                finally:
                    release.set()
                    results = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.batch_mutations._active:
                            await asyncio.sleep(.01)
                assert len(calls) == 1 and calls[0] != caller and sql_threads == {calls[0]}
                monkeypatch.setattr(services.screening, action, original)
                event.remove(factory, 'before_commit', commit)
                saved = await http.get(path, headers={'X-Org-Key': key})
                assert saved.status_code == (404 if action == 'delete' and ending != 'rollback' else 200)
                if saved.status_code == 200:
                    assert saved.json()['counts'] == {'pending': int(ending != 'rollback'), 'processing': 1, 'done': 1,
                        'failed': 1 if ending != 'rollback' else 2}
                if ending == 'release':
                    assert results[0].json() == ({'batch_id': bid, 'requeued': 1, 'skipped': 1}
                        if action == 'retry' else {'batch_id': bid, 'deleted': True})
                for _, peer_verb, peer_suffix in BATCH_MUTATIONS:
                    foreign = await http.request(peer_verb, path + peer_suffix, headers={'X-Org-Key': other_key})
                    absent = await http.request(peer_verb, '/screening/batches/missing' + peer_suffix, headers={'X-Org-Key': other_key})
                    assert foreign.status_code == absent.status_code == 404 and foreign.json() == absent.json()
                assert services.screening.get(other, kept).counts.pending == 2
                services.batch_mutations.close()
                for _, peer_verb, peer_suffix in BATCH_MUTATIONS:
                    refused = await http.request(peer_verb, path + peer_suffix, headers={'X-Org-Key': key})
                    assert refused.status_code == 503 and refused.json() == {'detail': 'batch_mutation_executor_closed'}
                    assert refused.headers['retry-after'] == '1' and 'set-cookie' not in refused.headers
    finally:
        release.set()
        await services.aclose()
        for name, listener in [('after_begin', begin), ('after_transaction_end', end), ('before_commit', commit)]:
            if event.contains(factory, name, listener):
                event.remove(factory, name, listener)
    assert 'synthetic-private-batch-mutation-error' not in log_output.text


@pytest.mark.parametrize('action,verb,suffix', BATCH_MUTATIONS, ids=['retry', 'delete'])
@pytest.mark.parametrize('ending', ['commit', 'rollback'])
async def test_batch_mutation_real_lock_and_late_atomic_result(database, settings, genuine_resume, action, verb, suffix, ending):
    from threading import Event, current_thread
    from sqlalchemy import event, text, select, func
    engine, factory = database
    settings.batch_mutation_max_concurrent_requests = 1
    settings.batch_mutation_wait_seconds = .2
    services, _, key, bid, _, other_key, kept = _batch_mutation_setup(settings, factory, genuine_resume)
    entered, proceed, pids = Event(), Event(), []
    needle = 'screening_erasure_state' if action == 'retry' else 'delete from screening_batches'
    def sql(conn, cursor, statement, parameters, context, many):
        if needle in statement.lower() and current_thread().name.startswith('batch-mutation') and not entered.is_set():
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
            assert proceed.wait(10)
    def commit(session):
        if ending == 'rollback' and current_thread().name.startswith('batch-mutation'):
            session.flush()
            raise RuntimeError('synthetic-private-batch-mutation-error')
    app, blocker = create_app(services), None
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            event.listen(factory, 'before_commit', commit)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test', headers=ADMIN_HEADERS) as http:
                path = '/screening/batches/' + bid
                pending = asyncio.create_task(http.request(verb, path + suffix, headers={'X-Org-Key': key}))
                try:
                    assert await asyncio.to_thread(entered.wait, 10)
                    blocker = engine.connect()
                    if engine.dialect.name == 'sqlite':
                        blocker.exec_driver_sql('BEGIN EXCLUSIVE')
                    else:
                        blocker.execute(text('LOCK TABLE screening_batches IN ACCESS EXCLUSIVE MODE'))
                    proceed.set()
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(8):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    assert (await http.get('/healthz')).status_code == 200
                    response = await asyncio.wait_for(pending, 2)
                    assert response.status_code == 503 and response.json() == {'detail': 'batch_mutation_pending'}
                    assert len(services.batch_mutations._active) == 1
                finally:
                    proceed.set()
                    if blocker is not None:
                        blocker.rollback()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.batch_mutations._active:
                            await asyncio.sleep(.01)
                saved = await http.get(path, headers={'X-Org-Key': key})
                gone = action == 'delete' and ending == 'commit'
                assert saved.status_code == (404 if gone else 200)
                if not gone:
                    assert saved.json()['counts'] == {'pending': int(action == 'retry' and ending == 'commit'),
                        'processing': 1, 'done': 1, 'failed': 1 if action == 'retry' and ending == 'commit' else 2}
                with factory() as session:
                    assert session.scalar(select(func.count()).select_from(BatchItemRow).where(BatchItemRow.batch_id == bid)) == (0 if gone else 4)
                assert (await http.get('/screening/batches/' + kept, headers={'X-Org-Key': other_key})).status_code == 200
    finally:
        proceed.set()
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        for target, name, listener in [(engine, 'before_cursor_execute', sql), (factory, 'before_commit', commit)]:
            if event.contains(target, name, listener):
                event.remove(target, name, listener)
        await services.aclose()


async def test_batch_registration_sql_leaves_unrelated_requests_responsive(database, settings, genuine_resume):
    from threading import Event
    from sqlalchemy import event
    engine, factory = database
    services, _, key, _, _, _, _ = _batch_read_setup(settings, factory, genuine_resume)
    entered, release, finished = Event(), Event(), Event()
    def sql(conn, cursor, statement, parameters, context, many):
        if 'insert into screening_batches' in statement.lower() and not entered.is_set():
            entered.set()
            release.wait(3)
            finished.set()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.post('/screening/batches', headers={'X-Org-Key': key},
                    json={'name': 'Responsive registration', 'items': [{'resume_text': genuine_resume}]}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    assert not finished.is_set(), 'batch registration SQL blocked the event loop'
                finally:
                    release.set()
                    assert (await pending).status_code == 200
    finally:
        release.set()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)
        await services.aclose()


def _batch_read_setup(settings, factory, resume):
    from app.candidates.store import CandidateStore
    from tests.conftest import make_services
    services = make_services(settings, candidates=CandidateStore(factory))
    org, key = _key(services)
    other, other_key = _key(services, 'Other batch reader')
    def register(owner, name):
        return services.screening.register(owner, name=name, domain='genai',
            texts=[resume + f'\nSynthetic item {i}' for i in range(2)], created_by_org_user_id=None).id
    return services, org, key, register(org, 'Owned batch'), other, other_key, register(other, 'Kept batch')


@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'rollback'])
async def test_batch_registration_admission_and_owning_sessions(database, settings, genuine_resume, monkeypatch, log_output, ending):
    from threading import Event, get_ident, current_thread
    from sqlalchemy import event
    engine, factory = database
    settings.batch_registration_max_concurrent_requests = 1
    settings.batch_registration_wait_seconds = .2 if ending in ('timeout', 'rollback') else 20
    services, _, key, _, other, other_key, kept = _batch_read_setup(settings, factory, genuine_resume)
    entered, release = Event(), Event()
    caller, calls, sql_threads = get_ident(), [], set()
    original = services.screening.register
    def register(*args, **kwargs):
        calls.append((get_ident(), kwargs['batch_id']))
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    def begin(session, transaction, conn):
        assert session.info.setdefault('registration_owner', get_ident()) == get_ident()
        if current_thread().name.startswith('batch-registration'):
            sql_threads.add(get_ident())
    def end(session, transaction):
        assert session.info.get('registration_owner', get_ident()) == get_ident()
    def commit(session):
        if ending == 'rollback' and current_thread().name.startswith('batch-registration'):
            session.flush()
            raise RuntimeError('synthetic-private-registration-rollback')
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(services.screening, 'register', register)
            for name, listener in [('after_begin', begin), ('after_transaction_end', end), ('before_commit', commit)]:
                event.listen(factory, name, listener)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test', headers=ADMIN_HEADERS) as http:
                payload = {'name': 'Uncertain batch', 'domain': 'data_eng', 'items': [{'resume_text': genuine_resume}] * 2}
                pending = asyncio.create_task(http.post('/screening/batches', json=payload, headers={'X-Org-Key': key}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == 200
                    # Read admission remains available while registration is full.
                    assert (await http.get('/screening/batches/' + kept, headers={'X-Org-Key': other_key})).status_code == 200
                    refused = await http.post('/screening/batches', json=payload, headers={'X-Org-Key': other_key})
                    assert refused.status_code == 503 and refused.json() == {'detail': 'batch_registration_capacity_exhausted'}
                    assert refused.headers['retry-after'] == '1' and 'set-cookie' not in refused.headers
                    if ending in ('timeout', 'rollback'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503 and response.json() == {'detail': {
                            'code': 'batch_registration_pending', 'batch_id': calls[0][1]}}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    assert len(services.batch_registrations._active) == 1
                finally:
                    release.set()
                    results = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.batch_registrations._active:
                            await asyncio.sleep(.01)
                assert len(calls) == 1 and calls[0][0] != caller and sql_threads == {calls[0][0]}
                path = '/screening/batches/' + calls[0][1]
                saved = await http.get(path, headers={'X-Org-Key': key})
                assert saved.status_code == (404 if ending == 'rollback' else 200)
                if ending != 'rollback':
                    assert saved.json()['counts'] == {'pending': 2, 'processing': 0, 'done': 0, 'failed': 0}
                    assert saved.json()['domain'] == 'data_eng' and saved.json()['created_by_org_user_id'] is None
                    if ending == 'release':
                        assert results[0].json() == saved.json()
                foreign = await http.get(path, headers={'X-Org-Key': other_key})
                absent = await http.get('/screening/batches/missing', headers={'X-Org-Key': other_key})
                assert foreign.status_code == absent.status_code == 404 and foreign.json() == absent.json()
                assert services.screening.get(other, kept).counts.pending == 2
                assert len(calls) == 1
                services.batch_registrations.close()
                refused = await http.post('/screening/batches', json=payload, headers={'X-Org-Key': key})
                assert refused.status_code == 503 and refused.json() == {'detail': 'batch_registration_executor_closed'}
                assert refused.headers['retry-after'] == '1'
    finally:
        release.set()
        await services.aclose()
        for name, listener in [('after_begin', begin), ('after_transaction_end', end), ('before_commit', commit)]:
            if event.contains(factory, name, listener):
                event.remove(factory, name, listener)
    assert 'synthetic-private-registration-rollback' not in log_output.text


@pytest.mark.parametrize('ending', ['commit', 'rollback'])
async def test_batch_registration_real_sql_lock_late_atomic_result(database, settings, genuine_resume, ending):
    from threading import Event, current_thread
    from sqlalchemy import event, text, select, func
    from app.screening.models import ScreeningBatchRow
    engine, factory = database
    settings.batch_registration_max_concurrent_requests = 1
    settings.batch_registration_wait_seconds = .2
    services, org, key, _, _, other_key, _ = _batch_read_setup(settings, factory, genuine_resume)
    entered, proceed, pids = Event(), Event(), []
    def sql(conn, cursor, statement, parameters, context, many):
        if 'screening_erasure_state' in statement.lower() and current_thread().name.startswith('batch-registration') and not entered.is_set():
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
            assert proceed.wait(10)
    def commit(session):
        if ending == 'rollback' and current_thread().name.startswith('batch-registration'):
            session.flush()  # Prove the real insert and all child inserts roll back.
            raise RuntimeError('synthetic-private-registration-rollback')
    app, blocker = create_app(services), None
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            event.listen(factory, 'before_commit', commit)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.post('/screening/batches', headers={'X-Org-Key': key},
                    json={'name': 'Locked registration', 'items': [{'resume_text': genuine_resume}] * 2}))
                try:
                    assert await asyncio.to_thread(entered.wait, 10)
                    blocker = engine.connect()
                    if engine.dialect.name == 'sqlite':
                        blocker.exec_driver_sql('BEGIN EXCLUSIVE')
                    else:
                        blocker.execute(text('LOCK TABLE screening_batches IN ACCESS EXCLUSIVE MODE'))
                    proceed.set()
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(8):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    assert (await http.get('/healthz')).status_code == 200
                    response = await asyncio.wait_for(pending, 2)
                    assert response.status_code == 503
                    detail = response.json()['detail']
                    assert detail['code'] == 'batch_registration_pending'
                    bid = detail['batch_id']
                    assert len(services.batch_registrations._active) == 1
                finally:
                    proceed.set()
                    if blocker is not None:
                        blocker.rollback()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.batch_registrations._active:
                            await asyncio.sleep(.01)
                saved = await http.get('/screening/batches/' + bid, headers={'X-Org-Key': key})
                assert saved.status_code == (200 if ending == 'commit' else 404)
                if ending == 'commit':
                    assert saved.json()['counts'] == {'pending': 2, 'processing': 0, 'done': 0, 'failed': 0}
                assert (await http.get('/screening/batches/' + bid, headers={'X-Org-Key': other_key})).status_code == 404
                with factory() as session:
                    assert session.scalar(select(func.count()).select_from(ScreeningBatchRow).where(ScreeningBatchRow.id == bid)) == int(ending == 'commit')
                    assert session.scalar(select(func.count()).select_from(BatchItemRow).where(BatchItemRow.batch_id == bid)) == (2 if ending == 'commit' else 0)
    finally:
        proceed.set()
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        for target, name, listener in [(engine, 'before_cursor_execute', sql), (factory, 'before_commit', commit)]:
            if event.contains(target, name, listener):
                event.remove(target, name, listener)
        await services.aclose()


def test_batch_registration_observed_deletion_returns_absent_not_assertion(services, genuine_resume, monkeypatch):
    _, key = _key(services)
    create = services.screening._store.create_batch
    def deleted(org_id, **kwargs):
        bid = create(org_id, **kwargs)
        assert services.screening._store.delete_batch(org_id, bid)
        return bid
    monkeypatch.setattr(services.screening._store, 'create_batch', deleted)
    with _client(services) as http:
        response = _register(http, key, [genuine_resume])
        assert response.status_code == 404 and response.json() == {'detail': 'batch not found'}


@pytest.mark.parametrize('case,path,method', BATCH_READS, ids=[row[0] for row in BATCH_READS])
async def test_batch_read_sql_leaves_unrelated_requests_responsive(database, settings, genuine_resume, case, path, method):
    from threading import Event
    from sqlalchemy import event
    engine, factory = database
    services, _, key, bid, _, _, _ = _batch_read_setup(settings, factory, genuine_resume)
    entered, release, finished = Event(), Event(), Event()
    def sql(conn, cursor, statement, parameters, context, many):
        if 'from batch_items' in statement.lower() and not entered.is_set():
            entered.set()
            release.wait(3)
            finished.set()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get(path.format(bid=bid), headers={'X-Org-Key': key}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    assert not finished.is_set(), 'batch view SQL blocked the event loop'
                finally:
                    release.set()
                    assert (await pending).status_code == 200
    finally:
        release.set()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)
        await services.aclose()


@pytest.mark.parametrize('case,path,method', BATCH_READS, ids=[row[0] for row in BATCH_READS])
@pytest.mark.parametrize('change', ['delete', 'owner'])
def test_batch_read_refuses_observed_scope_loss(database, settings, genuine_resume, monkeypatch, case, path, method, change):
    from app.screening.models import ScreeningBatchRow
    _, factory = database
    services, org, key, bid, other, other_key, kept = _batch_read_setup(settings, factory, genuine_resume)
    target = 'queue_page' if case == 'queue' else 'counts'
    original = getattr(services.screening._store, target)
    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        with factory() as session:
            row = session.get(ScreeningBatchRow, bid)
            if change == 'delete':
                session.delete(row)
            else:
                row.org_id = other
            session.commit()
        return value
    try:
        with _client(services) as http:
            with monkeypatch.context() as patch:
                patch.setattr(services.screening._store, target, changed)
                response = http.get(path.format(bid=bid), headers={'X-Org-Key': key})
            if case == 'list':
                assert response.status_code == 200 and response.json()['batches'] == []
            else:
                assert response.status_code == 404 and response.json() == {'detail': 'batch not found'}
            assert http.get(f'/screening/batches/{kept}', headers={'X-Org-Key': other_key}).status_code == 200
    finally:
        asyncio.run(services.aclose())


@pytest.mark.parametrize('case,path,method', BATCH_READS, ids=[row[0] for row in BATCH_READS])
@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'late_failure'])
async def test_batch_read_admission_sessions_and_recovery(database, settings, genuine_resume, monkeypatch, log_output, case, path, method, ending):
    from threading import Event, get_ident, current_thread
    from sqlalchemy import event
    _, factory = database
    settings.batch_read_max_concurrent_requests = 1
    settings.batch_read_wait_seconds = .2 if ending in ('timeout', 'late_failure') else 20
    services, org, key, bid, other, other_key, kept = _batch_read_setup(settings, factory, genuine_resume)
    entered, release, calls, sql_threads = Event(), Event(), [], set()
    caller = get_ident()
    original = getattr(services.screening, method)
    args = (org,) if case == 'list' else (org, bid)
    kwargs = {'cursor': None, 'limit': 1} if case in ('list', 'queue') else {}
    params = {'limit': 1} if kwargs else {}
    expected = original(*args, **kwargs).model_dump(mode='json')
    def held(*values, **options):
        calls.append(get_ident())
        entered.set()
        assert release.wait(15)
        if ending == 'late_failure':
            raise RuntimeError('synthetic-private-batch-read-error')
        return original(*values, **options)
    def begin(session, transaction, connection):
        assert session.info.setdefault('batch_view_owner', get_ident()) == get_ident()
        if current_thread().name.startswith('batch-read'):
            sql_threads.add(get_ident())
    def end(session, transaction):
        assert session.info.get('batch_view_owner', get_ident()) == get_ident()
    async def no_assessment(**kwargs):
        pytest.fail('reading a batch must not assess a resume')
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(services.screening, method, held)
            monkeypatch.setattr(app.state.engine, 'evaluate', no_assessment)
            event.listen(factory, 'after_begin', begin)
            event.listen(factory, 'after_transaction_end', end)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get(path.format(bid=bid), params=params, headers={'X-Org-Key': key}))
                try:
                    assert await asyncio.to_thread(entered.wait, 10)
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as anonymous:
                        assert (await anonymous.get(path.format(bid=bid))).status_code == 401
                    for _, peer_path, _ in BATCH_READS:
                        busy = await http.get(peer_path.format(bid=kept), headers={'X-Org-Key': other_key})
                        assert busy.status_code == 503 and busy.json() == {'detail': 'batch_read_capacity_exhausted'}
                        assert busy.headers['retry-after'] == '1' and 'set-cookie' not in busy.headers
                    if ending in ('timeout', 'late_failure'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503 and response.json() == {'detail': 'batch_read_pending'}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    assert len(services.batch_reads._active) == 1
                finally:
                    release.set()
                    results = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.batch_reads._active:
                            await asyncio.sleep(.01)
                assert len(calls) == 1 and calls[0] != caller and sql_threads <= {calls[0]}
                if ending == 'release':
                    assert results[0].status_code == 200 and results[0].json() == expected
                monkeypatch.setattr(services.screening, method, original)
                services.batch_reads._wait_seconds = 20
                fresh = await http.get(path.format(bid=bid), params=params, headers={'X-Org-Key': key})
                assert fresh.status_code == 200 and fresh.json() == expected
                assert len(calls) == 1  # No background replay after timeout/cancel/failure.
                for suffix in ('', '/queue', '/summary'):
                    foreign = await http.get(f'/screening/batches/{bid}' + suffix, headers={'X-Org-Key': other_key})
                    absent = await http.get('/screening/batches/missing' + suffix, headers={'X-Org-Key': other_key})
                    assert foreign.status_code == absent.status_code == 404 and foreign.json() == absent.json()
                for target in ('/screening/batches', f'/screening/batches/{bid}/queue'):
                    assert (await http.get(target, params={'cursor': '!!!'}, headers={'X-Org-Key': key})).status_code == 422
                assert services.screening.get(other, kept).counts.pending == 2
                services.batch_reads.close()
                closed = await http.get(path.format(bid=bid), headers={'X-Org-Key': key})
                assert closed.status_code == 503 and closed.json() == {'detail': 'batch_read_executor_closed'}
                assert closed.headers['retry-after'] == '1' and 'set-cookie' not in closed.headers
    finally:
        release.set()
        await services.aclose()
        for name, listener in [('after_begin', begin), ('after_transaction_end', end)]:
            if event.contains(factory, name, listener):
                event.remove(factory, name, listener)
    assert 'synthetic-private-batch-read-error' not in log_output.text


@pytest.mark.parametrize('case,path,method', BATCH_READS, ids=[row[0] for row in BATCH_READS])
@pytest.mark.parametrize('change', ['release', 'delete', 'owner'])
async def test_batch_read_real_lock_and_scope_loss(database, settings, genuine_resume, case, path, method, change):
    from threading import Event, current_thread
    from sqlalchemy import event, text
    engine, factory = database
    settings.batch_read_max_concurrent_requests = 1
    settings.batch_read_wait_seconds = .2
    services, org, key, bid, other, other_key, kept = _batch_read_setup(settings, factory, genuine_resume)
    entered, proceed, pids = Event(), Event(), []
    def sql(conn, cursor, statement, parameters, context, many):
        if 'from batch_items' in statement.lower() and current_thread().name.startswith('batch-read') and not entered.is_set():
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
            assert proceed.wait(10)
    app, blocker = create_app(services), None
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get(path.format(bid=bid), headers={'X-Org-Key': key}))
                try:
                    assert await asyncio.to_thread(entered.wait, 10)
                    blocker = engine.connect()
                    if engine.dialect.name == 'sqlite':
                        blocker.exec_driver_sql('BEGIN EXCLUSIVE')
                    else:
                        blocker.execute(text('LOCK TABLE batch_items IN ACCESS EXCLUSIVE MODE'))
                    proceed.set()
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(8):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    assert (await http.get('/healthz')).status_code == 200
                    response = await asyncio.wait_for(pending, 2)
                    assert response.status_code == 503 and response.json() == {'detail': 'batch_read_pending'}
                    assert len(services.batch_reads._active) == 1
                    if change == 'delete':
                        blocker.execute(text('DELETE FROM screening_batches WHERE id = :bid'), {'bid': bid})
                        blocker.commit()
                    elif change == 'owner':
                        blocker.execute(text('UPDATE screening_batches SET org_id = :org WHERE id = :bid'), {'org': other, 'bid': bid})
                        blocker.commit()
                finally:
                    proceed.set()
                    if blocker is not None:
                        blocker.rollback()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.batch_reads._active:
                            await asyncio.sleep(.01)
                fresh = await http.get(path.format(bid=bid), headers={'X-Org-Key': key})
                if case == 'list':
                    assert fresh.status_code == 200
                    assert [b['id'] for b in fresh.json()['batches']] == ([bid] if change == 'release' else [])
                else:
                    assert fresh.status_code == (200 if change == 'release' else 404)
                assert services.screening.get(other, kept).counts.pending == 2
    finally:
        proceed.set()
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)
        await services.aclose()


def test_batch_read_scope_filter_preserves_the_original_page_cursor(database, settings, genuine_resume, monkeypatch):
    from app.screening.models import ScreeningBatchRow
    _, factory = database
    services, org, key, bid, other, _, _ = _batch_read_setup(settings, factory, genuine_resume)
    second = services.screening.register(org, name='Another owned batch', domain='genai',
        texts=[genuine_resume], created_by_org_user_id=None).id
    original = services.screening.list(org, cursor=None, limit=1)
    cut_id = original.batches[0].id
    assert original.next_cursor
    counts = services.screening._store.counts
    def changed(*args, **kwargs):
        value = counts(*args, **kwargs)
        with factory() as session:
            session.get(ScreeningBatchRow, cut_id).org_id = other
            session.commit()
        return value
    try:
        with _client(services) as http:
            with monkeypatch.context() as patch:
                patch.setattr(services.screening._store, 'counts', changed)
                page = http.get('/screening/batches?limit=1', headers={'X-Org-Key': key}).json()
            assert page == {'batches': [], 'next_cursor': original.next_cursor}
            next_page = http.get('/screening/batches', params={'limit': 1, 'cursor': page['next_cursor']},
                headers={'X-Org-Key': key}).json()
            assert {row['id'] for row in next_page['batches']} == {bid, second} - {cut_id}
    finally:
        asyncio.run(services.aclose())


# Screening batches api

@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _key(services, name="Agency A"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _register(c, key, texts, name="Q3"):
    return c.post("/screening/batches", headers={"X-Org-Key": key},
                  json={"name": name, "domain": "genai",
                        "items": [{"resume_text": t} for t in texts]})


def test_register_then_process_then_read_the_queue(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        created = _register(c, key, [genuine_resume])
        assert created.status_code == 200, created.text
        bid = created.json()["id"]
        assert created.json()["counts"]["pending"] == 1
        assert created.json()["status"] == "pending"

        ran = c.post(f"/screening/batches/{bid}/process", headers={"X-Org-Key": key})
        assert ran.status_code == 200
        assert ran.json()["processed"] == 1 and ran.json()["remaining"] == 0

        queue = c.get(f"/screening/batches/{bid}/queue", headers={"X-Org-Key": key})
        row = queue.json()["rows"][0]
        assert row["status"] == "done" and row["reason"]
        assert row["advisory"] is True

        summary = c.get(f"/screening/batches/{bid}/summary", headers={"X-Org-Key": key})
        assert summary.status_code == 200 and summary.json()["n_screened"] == 1


@pytest.mark.asyncio
async def test_two_process_requests_share_unstarted_work_and_report_saved_counts(services, genuine_resume, monkeypatch):
    monkeypatch.setattr(services.settings, "screening_max_items_per_call", 2)
    org, key = _key(services)
    _, other_key = _key(services, "Other lease actor")
    app = create_app(services)
    slow = _PausedEngine(services)
    async with app.router.lifespan_context(app):
        app.state.engine = slow
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                    headers={"X-Org-Key": key}) as actor:
            created = await actor.post("/screening/batches", json={"name": "Two requests", "items": [
                {"resume_text": genuine_resume + f"\nSynthetic request {i}"} for i in range(3)]})
            assert created.status_code == 200
            path = "/screening/batches/" + created.json()["id"]
            pending = asyncio.create_task(actor.post(path + "/process"))
            try:
                await asyncio.wait_for(slow.entered.wait(), 10)
                current = (await actor.get(path)).json()["counts"]
                assert (current["processing"], current["pending"]) == (1, 2)
                assert (await actor.post(path + "/process", headers={"X-Org-Key": other_key})).status_code == 404
                app.state.engine = slow.real
                second = await actor.post(path + "/process")
                assert second.status_code == 200
                assert (second.json()["processed"], second.json()["failed"], second.json()["remaining"]) == (2, 0, 1)
                assert (await actor.post(path + "/retry")).json()["requeued"] == 0
            finally:
                slow.release.set()
                first = await pending
            assert first.status_code == 200
            assert (first.json()["processed"], first.json()["failed"], first.json()["remaining"]) == (1, 0, 0)
            saved = (await actor.get(path)).json()
            assert saved["counts"] == {"pending": 0, "processing": 0, "failed": 0, "done": 3}
            assert (await actor.get(path + "/summary")).json()["n_screened"] == 3
            assert (await actor.post(path + "/process")).json()["processed"] == 0


def test_an_empty_batch_is_422(services):
    _, key = _key(services)
    with _client(services) as c:
        r = c.post("/screening/batches", headers={"X-Org-Key": key},
                   json={"name": "x", "domain": "genai", "items": []})
        assert r.status_code == 422


def test_an_oversize_batch_is_422(services):
    _, key = _key(services)
    cap = services.settings.screening_max_batch_items
    with _client(services) as c:
        r = _register(c, key, ["resume"] * (cap + 1))
        assert r.status_code == 422


def test_a_corrupt_pdf_refuses_the_whole_registration_and_names_the_item(services):
    """A half-registered batch would leave the org unable to say which files
    made it in."""
    _, key = _key(services)
    with _client(services) as c:
        r = c.post("/screening/batches", headers={"X-Org-Key": key}, json={
            "name": "x", "domain": "genai",
            "items": [
                {"resume_text": "a real resume"},
                {"resume_pdf_b64": base64.b64encode(b"not a pdf").decode()},
            ],
        })
        assert r.status_code == 422
        assert "1" in str(r.json()["detail"]), "the failing item's index is named"
        assert c.get("/screening/batches", headers={"X-Org-Key": key}).json()["batches"] == []


def test_the_item_count_cap_runs_before_any_pdf_is_decoded(services):
    """The bound must cost arithmetic, not work: an over-cap batch of corrupt
    PDFs was decoded item by item and only THEN counted, so the cap protected
    nothing. The cap message -- not pdf_parse_failed -- proves the ordering."""
    _, key = _key(services)
    cap = services.settings.screening_max_batch_items
    items = [{"resume_pdf_b64": "bm90IGEgcGRm"} for _ in range(cap + 1)]
    with _client(services) as c:
        r = c.post("/screening/batches", headers={"X-Org-Key": key},
                   json={"name": "x", "domain": "genai", "items": items})
        assert r.status_code == 422
        detail = str(r.json()["detail"])
        assert "at most" in detail, detail
        assert "pdf_parse_failed" not in detail, "a PDF was decoded before the cap"


def test_a_malformed_cursor_is_422_not_500(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        for path in ("/screening/batches?cursor=!!!",
                     f"/screening/batches/{bid}/queue?cursor=!!!"):
            r = c.get(path, headers={"X-Org-Key": key})
            assert r.status_code == 422, f"{path} -> {r.status_code}"


def test_a_type_forged_cursor_is_422_not_500(services, genuine_resume):
    """A cursor that DECODES but carries the wrong types. base64+arity is not
    validation: `[1,"x"]` reached datetime.fromisoformat as an int and raised
    TypeError -- which `except (InvalidCursor, ValueError)` does not catch --
    so a hand-built cursor was a 500 on demand."""
    import base64 as b64
    import json

    def forge(values):
        raw = json.dumps(values).encode()
        return b64.urlsafe_b64encode(raw).decode().rstrip("=")

    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        cases = [
            (f"/screening/batches?cursor={forge([1, 'x'])}", "int where ISO string"),
            (f"/screening/batches?cursor={forge(['garbage', 'x'])}", "non-ISO string"),
            (f"/screening/batches?cursor={forge([None, None])}", "nulls"),
            (f"/screening/batches/{bid}/queue?cursor={forge(['x', 'y'])}",
             "string where score"),
            (f"/screening/batches/{bid}/queue?cursor={forge([[0.5], 'y'])}",
             "nested list where score"),
        ]
        for path, why in cases:
            r = c.get(path, headers={"X-Org-Key": key})
            assert r.status_code == 422, f"{why}: {path} -> {r.status_code}"


def test_the_queue_pages_with_a_cursor(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        texts = [f"{genuine_resume}\nRef {i}" for i in range(3)]
        bid = _register(c, key, texts).json()["id"]
        while c.post(f"/screening/batches/{bid}/process",
                     headers={"X-Org-Key": key}).json()["remaining"]:
            pass

        first = c.get(f"/screening/batches/{bid}/queue?limit=2",
                      headers={"X-Org-Key": key}).json()
        assert len(first["rows"]) == 2 and first["next_cursor"]
        second = c.get(
            f"/screening/batches/{bid}/queue?cursor={first['next_cursor']}",
            headers={"X-Org-Key": key},
        ).json()
        ids = [r["item_id"] for r in first["rows"] + second["rows"]]
        assert len(ids) == len(set(ids)) == 3


def test_delete_removes_the_batch(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        gone = c.delete(f"/screening/batches/{bid}", headers={"X-Org-Key": key})
        assert gone.status_code == 200 and gone.json()["deleted"] is True
        assert c.get(f"/screening/batches/{bid}",
                     headers={"X-Org-Key": key}).status_code == 404


def test_a_machine_caller_records_no_human_creator(services, genuine_resume):
    """X-Org-Key is an ORGANISATION credential. Inventing an actor would be a
    false audit trail."""
    _, key = _key(services)
    with _client(services) as c:
        created = _register(c, key, [genuine_resume])
        assert created.json()["created_by_org_user_id"] is None


# Screening retry

def _items(services):
    with services.candidates._session_factory() as session:
        return session.query(BatchItemRow).order_by(BatchItemRow.created_at).all()


def _fail_item(services, item_id: str, *, error="internal_error", clear_text=False):
    with services.candidates._session_factory() as session:
        row = session.get(BatchItemRow, item_id)
        row.status = ItemStatus.FAILED.value
        row.error = error
        if clear_text:
            row.raw_text = ""
        session.commit()


def test_a_failed_item_is_requeued_and_becomes_claimable(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        item_id = _items(services)[0].id
        _fail_item(services, item_id)

        resp = c.post(f"/screening/batches/{bid}/retry", headers={"X-Org-Key": key})
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"batch_id": bid, "requeued": 1, "skipped": 0}

    with services.candidates._session_factory() as session:
        row = session.get(BatchItemRow, item_id)
        assert row.status == ItemStatus.PENDING.value
        assert row.error is None
        assert row.claimed_at is None
        assert row.processed_at is None


def test_an_item_with_no_text_is_SKIPPED_not_requeued(services, genuine_resume):
    """Either the text was cleared on success or the failure was empty_resume.
    Re-queueing it would report requeued:1 and then fail identically -- a
    promise the next process call breaks."""
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        item_id = _items(services)[0].id
        _fail_item(services, item_id, error="empty_resume", clear_text=True)

        body = c.post(f"/screening/batches/{bid}/retry",
                      headers={"X-Org-Key": key}).json()
    assert body == {"batch_id": bid, "requeued": 0, "skipped": 1}
    with services.candidates._session_factory() as session:
        assert session.get(BatchItemRow, item_id).status == ItemStatus.FAILED.value


def test_done_and_pending_items_are_untouched(services, genuine_resume):
    """Retry means 'try the failures again', not 'run everything again'. A
    finished item has had its text cleared and is not re-runnable at all."""
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume, genuine_resume]).json()["id"]
        rows = _items(services)
        done_id, pending_id = rows[0].id, rows[1].id
        with services.candidates._session_factory() as session:
            row = session.get(BatchItemRow, done_id)
            row.status = ItemStatus.DONE.value
            row.raw_text = ""
            session.commit()

        body = c.post(f"/screening/batches/{bid}/retry",
                      headers={"X-Org-Key": key}).json()

    assert body["requeued"] == 0 and body["skipped"] == 0
    with services.candidates._session_factory() as session:
        assert session.get(BatchItemRow, done_id).status == ItemStatus.DONE.value
        assert session.get(BatchItemRow, pending_id).status == ItemStatus.PENDING.value


def test_another_org_gets_404_never_403(services, genuine_resume):
    """403 confirms the batch exists to anyone guessing ids. The same rule S8.5
    asserted on both outcome verbs, and the two answers must be
    byte-identical."""
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        bid = _register(c, key_a, [genuine_resume]).json()["id"]
        theirs = c.post(f"/screening/batches/{bid}/retry",
                        headers={"X-Org-Key": key_b})
        unknown = c.post(
            "/screening/batches/00000000-0000-0000-0000-000000000000/retry",
            headers={"X-Org-Key": key_b},
        )
    assert theirs.status_code == unknown.status_code == 404
    assert theirs.json() == unknown.json()


def test_a_requeued_item_is_actually_picked_up_by_process(services, genuine_resume):
    """The point of the whole task: retry re-queues, and the EXISTING process
    door does the work. There is no second processing path."""
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        item_id = _items(services)[0].id
        _fail_item(services, item_id)
        c.post(f"/screening/batches/{bid}/retry", headers={"X-Org-Key": key})
        result = c.post(f"/screening/batches/{bid}/process",
                        headers={"X-Org-Key": key}).json()
    assert result["processed"] + result["failed"] == 1


def test_retrying_a_batch_with_nothing_failed_is_a_no_op(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        body = c.post(f"/screening/batches/{bid}/retry",
                      headers={"X-Org-Key": key}).json()
    assert body == {"batch_id": bid, "requeued": 0, "skipped": 0}


# Screening tenancy

def _screening_tenancy_key(services, name):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def test_every_batch_route_is_404_for_another_org_and_matches_absence(
    services, genuine_resume
):
    _, key_a = _screening_tenancy_key(services, "Agency A")
    _, key_b = _screening_tenancy_key(services, "Agency B")
    with _client(services) as c:
        bid = _register(c, key_a, [genuine_resume]).json()["id"]
        b = {"X-Org-Key": key_b}

        cases = [
            ("get", f"/screening/batches/{bid}", "/screening/batches/nope"),
            ("get", f"/screening/batches/{bid}/queue", "/screening/batches/nope/queue"),
            ("get", f"/screening/batches/{bid}/summary", "/screening/batches/nope/summary"),
            ("post", f"/screening/batches/{bid}/process", "/screening/batches/nope/process"),
            ("delete", f"/screening/batches/{bid}", "/screening/batches/nope"),
        ]
        for method, theirs, absent in cases:
            got = getattr(c, method)(theirs, headers=b)
            missing = getattr(c, method)(absent, headers=b)
            assert got.status_code == 404, f"{method} {theirs} -> {got.status_code}"
            assert got.json() == missing.json(), (
                f"{method} {theirs}: a different body from a genuinely absent "
                f"batch confirms this one exists"
            )


def test_listing_shows_only_my_own_batches(services, genuine_resume):
    _, key_a = _screening_tenancy_key(services, "Agency A")
    _, key_b = _screening_tenancy_key(services, "Agency B")
    with _client(services) as c:
        _register(c, key_a, [genuine_resume], name="A's batch")
        mine = c.get("/screening/batches", headers={"X-Org-Key": key_b}).json()
        assert mine["batches"] == []


def test_a_cursor_from_another_org_reaches_nothing(services, genuine_resume):
    """A cursor is a sort position, not a capability -- the org filter is what
    protects the boundary, so a stolen cursor buys nothing."""
    _, key_a = _screening_tenancy_key(services, "Agency A")
    _, key_b = _screening_tenancy_key(services, "Agency B")
    with _client(services) as c:
        # TWO batches, so a limit=1 page actually has a next_cursor to steal.
        _register(c, key_a, [genuine_resume], name="first")
        _register(c, key_a, [genuine_resume + "\nRef 2"], name="second")
        page = c.get("/screening/batches?limit=1", headers={"X-Org-Key": key_a}).json()
        stolen = page["next_cursor"]
        assert stolen, "two batches and limit=1 must produce a cursor"

        theirs = c.get(f"/screening/batches?cursor={stolen}",
                       headers={"X-Org-Key": key_b})
        assert theirs.status_code == 200
        assert theirs.json()["batches"] == []


def test_all_batch_routes_require_an_org_credential(services):
    with _client(services) as c:
        assert c.get("/screening/batches").status_code == 401
        assert c.post("/screening/batches", json={}).status_code == 401
        assert c.get("/screening/batches/x/queue").status_code == 401
        assert c.post("/screening/batches/x/process").status_code == 401
        assert c.delete("/screening/batches/x").status_code == 401
