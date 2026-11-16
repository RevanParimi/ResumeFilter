"""The operator reviews, decides, and is recorded deciding (S8.3 Phase B)."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rights.schema import ResolvedBy
from tests.conftest import ADMIN_HEADERS, make_services
from tests.test_report_erasure_concurrency import database  # noqa: F401
from tests.test_rights_api import _rights_read_setup


DECISION = {'status': 'resolved', 'resolution': 'Synthetic private operator reason', 'apply': True}


def _decision_setup(settings, factory):
    from app.candidates.models import CandidateRow
    from app.rights.schema import CorrectionField, RequestKind
    services, headers, rows = _rights_read_setup(settings, factory)
    with factory() as session:
        session.get(CandidateRow, 'a').full_name = 'Original synthetic name'
        session.commit()
    request = services.rights._store.create('a', kind=RequestKind.CORRECTION,
        field=CorrectionField.FULL_NAME, current_value='Original synthetic name',
        requested_value='Reviewed synthetic name', note='Synthetic private correction')
    return services, headers, request, rows


async def test_rights_decision_sql_keeps_unrelated_requests_responsive(database, settings):
    import asyncio
    from threading import Event
    import httpx
    from sqlalchemy import event
    engine, factory = database
    services, _, record, _ = _decision_setup(settings, factory)
    entered, release, finished = Event(), Event(), Event()
    def sql(conn, cursor, statement, parameters, context, many):
        if 'update data_principal_requests' in statement.lower() and not entered.is_set():
            entered.set()
            release.wait(3)
            finished.set()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.post(f'/admin/requests/{record.id}/resolve', json=DECISION))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    assert not finished.is_set(), 'decision SQL blocked the event loop'
                finally:
                    release.set()
                    assert (await pending).status_code == 200
    finally:
        release.set()
        await services.aclose()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)


def test_rights_decision_rejects_open_target(database, settings):
    _, factory = database
    services, _, record, _ = _decision_setup(settings, factory)
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as http:
        response = http.post(f'/admin/requests/{record.id}/resolve', json={**DECISION, 'status':'open', 'apply':False})
        assert response.status_code == 422
        saved = services.rights._store.get(record.id)[0]
        assert saved.status == 'open' and saved.resolved_at is None and not saved.applied
        assert not [row for row in services.ledger.audit_for_candidate('a') if row.action == 'request.resolve']


@pytest.mark.parametrize('failure', ['correction', 'audit'])
def test_rights_decision_failure_rolls_back_all_effects(database, settings, monkeypatch, failure):
    _, factory = database
    services, _, record, _ = _decision_setup(settings, factory)
    def failed(*args, **kwargs):
        raise RuntimeError('synthetic-private-decision-failure')
    target, method = (services.candidates, 'apply_correction') if failure == 'correction' else (services.ledger, 'audit_request_event')
    monkeypatch.setattr(target, method, failed)
    with TestClient(create_app(services), headers=ADMIN_HEADERS, raise_server_exceptions=False) as http:
        response = http.post(f'/admin/requests/{record.id}/resolve', json=DECISION)
        assert response.status_code == 500
        saved = services.rights._store.get(record.id)[0]
        assert saved.status == 'open' and saved.resolved_at is None and not saved.applied
        candidate = services.candidates.get_candidate('a')
        assert candidate.full_name == 'Original synthetic name'
        assert not [row for row in services.ledger.audit_for_candidate('a') if row.action == 'request.resolve']


def test_rights_decision_observed_final_erasure_refuses_detached_view(database, settings, monkeypatch):
    _, factory = database
    services, _, record, rows = _decision_setup(settings, factory)
    original = services.rights._store.get
    def erased(*args, **kwargs):
        result = original(*args, **kwargs)
        if result is not None and result[0].status != 'open':
            assert services.candidates.delete_candidate('a')
        return result
    monkeypatch.setattr(services.rights._store, 'get', erased)
    with TestClient(create_app(services), headers=ADMIN_HEADERS, raise_server_exceptions=False) as http:
        response = http.post(f'/admin/requests/{record.id}/resolve', json=DECISION)
        assert response.status_code == 404 and response.json() == {'detail':'request not found'}
        assert DECISION['resolution'] not in response.text
        assert services.rights.for_candidate('b') == [rows['b']]


@pytest.mark.parametrize('apply', [False, True], ids=['record-only', 'apply-name'])
@pytest.mark.parametrize('ending', ['success', 'timeout', 'cancel', 'failure', 'late_failure', 'audit_rollback', 'post_commit_failure'])
async def test_rights_decision_owns_transaction_and_saved_recovery(database, settings, monkeypatch, log_output, apply, ending):
    import asyncio
    from threading import Event, current_thread, get_ident
    import httpx
    from sqlalchemy import event
    from app.candidates.models import CandidateRow
    engine, factory = database
    settings.portal_write_max_concurrent_requests = 1
    settings.portal_write_wait_seconds = .2 if ending in ('timeout', 'late_failure') else 20
    services, headers, record, rows = _decision_setup(settings, factory)
    with factory() as session:
        original_updated_at = session.get(CandidateRow, 'a').updated_at
    original = services.rights.resolve
    entered, release, owners, sessions, commits = Event(), Event(), [], [], []
    caller = get_ident()
    def begin(session, transaction, connection):
        if current_thread().name.startswith('portal-write'):
            sessions.append(session)
            session.info['decision_owner'] = get_ident()
    def end(session, transaction):
        if 'decision_owner' in session.info:
            assert session.info['decision_owner'] == get_ident()
    def committed(session):
        if current_thread().name.startswith('portal-write'):
            commits.append(session)
    def sql(conn, cursor, statement, parameters, context, many):
        if ending == 'audit_rollback' and current_thread().name.startswith('portal-write') and 'insert into audit_log' in statement.lower():
            raise RuntimeError('synthetic-private-decision-audit-rollback')
    def work(*args, **kwargs):
        owners.append(get_ident())
        entered.set()
        assert release.wait(10)
        if ending in ('failure', 'late_failure'):
            raise RuntimeError('synthetic-private-decision-error')
        result = original(*args, **kwargs)
        if ending == 'post_commit_failure':
            raise RuntimeError('synthetic-private-decision-after-commit')
        return result
    app = create_app(services)
    listeners = [(factory, 'after_begin', begin), (factory, 'after_transaction_end', end),
        (factory, 'after_commit', committed), (engine, 'before_cursor_execute', sql)]
    try:
        async with app.router.lifespan_context(app):
            for target, name, callback in listeners:
                event.listen(target, name, callback)
            monkeypatch.setattr(services.rights, 'resolve', work)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                path = f'/admin/requests/{record.id}/resolve'
                pending = asyncio.create_task(http.post(path, json={**DECISION, 'apply':apply}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    assert (await http.get('/admin/requests')).status_code == 200
                    for target, body in [('/portal/grievances', {'note':'not admitted'}),
                        ('/portal/corrections', {'field':'full_name', 'requested_value':'not admitted'}),
                        ('/portal/consents', {'purpose':'ledger_read'})]:
                        response = await http.post(target, json=body, headers=headers['b'])
                        assert response.status_code == 503 and response.json() == {'detail':'portal_write_capacity_exhausted'}
                    if ending in ('timeout', 'late_failure'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503 and response.json() == {'detail':'portal_write_pending'}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    assert len(services.portal_writes._active) == 1
                finally:
                    release.set()
                    responses = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.portal_writes._active:
                            await asyncio.sleep(.01)
                commit = ending not in ('failure', 'late_failure', 'audit_rollback')
                assert len(owners) == 1 and owners[0] != caller
                assert len(commits) == int(commit), 'borrowed store operation committed separately'
                assert all(s.info['decision_owner'] == owners[0] for s in sessions)
                if ending == 'success':
                    assert responses[0].status_code == 200 and responses[0].json()['applied'] is apply
                if ending in ('failure', 'audit_rollback', 'post_commit_failure'):
                    response = responses[0]
                    assert response.status_code == 500
                    assert response.json() == {'detail':'internal_error', 'request_id':response.headers['x-request-id']}
                # Explicit GET recovery never repeats any decision or repair.
                saved = [row for row in (await http.get('/admin/requests')).json() if row['id'] == record.id][0]
                assert saved['status'] == ('resolved' if commit else 'open') and saved['applied'] == (commit and apply)
                with factory() as session:
                    candidate = session.get(CandidateRow, 'a')
                    assert candidate.full_name == ('Reviewed synthetic name' if commit and apply else 'Original synthetic name')
                    assert (candidate.full_name_corrected_at is not None) == (commit and apply)
                    if not (commit and apply):
                        assert candidate.updated_at == original_updated_at
                assert [r.action for r in services.ledger.audit_for_candidate('a')].count('request.resolve') == int(commit)
                assert services.rights.for_candidate('b') == [rows['b']] and len(owners) == 1
                if commit:
                    repeat = await http.post(path, json={**DECISION, 'apply':apply})
                    assert repeat.status_code == 409
                    assert [r.action for r in services.ledger.audit_for_candidate('a')].count('request.resolve') == 1
                services.portal_writes.close()
                closed = await http.post(path, json=DECISION)
                assert closed.status_code == 503 and closed.json() == {'detail':'portal_write_executor_closed'}
                assert closed.headers['retry-after'] == '1' and 'set-cookie' not in closed.headers
    finally:
        release.set()
        await services.aclose()
        for target, name, callback in listeners:
            if event.contains(target, name, callback):
                event.remove(target, name, callback)
    assert DECISION['resolution'] not in log_output.text and 'synthetic-private-decision' not in log_output.text


def test_competing_rights_decisions_commit_one_effect_and_audit(database, settings, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, current_thread
    from datetime import datetime, timezone
    from app.rights.schema import RequestAlreadyResolved, RequestStatus
    _, factory = database
    services, _, record, _ = _decision_setup(settings, factory)
    barrier = Barrier(2)
    get, apply_correction = services.rights._store.get, services.candidates.apply_correction
    applied = []
    def selected(*args, **kwargs):
        found = get(*args, **kwargs)
        if current_thread().name.startswith('decision-race') and found is not None and found[0].status == 'open':
            barrier.wait(8)
        return found
    def apply(*args, **kwargs):
        applied.append(True)
        return apply_correction(*args, **kwargs)
    monkeypatch.setattr(services.rights._store, 'get', selected)
    monkeypatch.setattr(services.candidates, 'apply_correction', apply)
    def decide(reason):
        try:
            return services.rights.resolve(record.id, status=RequestStatus.RESOLVED, resolution=reason,
                apply=True, resolved_by=ResolvedBy.OPERATOR_KEY, admin_user_id=None, now=datetime.now(timezone.utc))
        except RequestAlreadyResolved:
            return None
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='decision-race') as pool:
        futures = [pool.submit(decide, reason) for reason in ('one operator', 'other operator')]
        results = [future.result(timeout=15) for future in futures]
    winners = [result for result in results if result is not None]
    assert len(winners) == len(applied) == 1
    assert services.rights._store.get(record.id)[0] == winners[0]
    assert [row.action for row in services.ledger.audit_for_candidate('a')].count('request.resolve') == 1
    assert services.candidates.get_candidate('a').full_name == 'Reviewed synthetic name'


async def test_rights_decisions_share_default_five_write_slots(database, settings, monkeypatch):
    import asyncio
    from threading import Event, Condition, get_ident
    import httpx
    _, factory = database
    services, headers, record, rows = _decision_setup(settings, factory)
    grant = services.ledger.grant_consent(candidate_id='b', purpose='ledger_read')
    assert services.portal_writes._capacity == 2 and services.portal_writes._wait_seconds == 20
    release, condition, owners = Event(), Condition(), set()
    original = services.rights.resolve
    def work(*args, **kwargs):
        with condition:
            owners.add(get_ident())
            condition.notify_all()
        assert release.wait(12)
        return original(*args, **kwargs)
    def occupied():
        with condition:
            return condition.wait_for(lambda:len(owners) == 2, timeout=8)
    app, pending = create_app(services), []
    try:
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(services.rights, 'resolve', work)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = [asyncio.create_task(http.post(f'/admin/requests/{rid}/resolve',
                    json={**DECISION, 'apply':False})) for rid in (record.id, rows['b'].id)]
                try:
                    assert await asyncio.to_thread(occupied)
                    for path, body, auth in [(f'/admin/requests/{record.id}/resolve', DECISION, {}),
                        ('/portal/corrections', {'field':'full_name', 'requested_value':'x'}, headers['b']),
                        ('/portal/grievances', {'note':'x'}, headers['b']),
                        ('/portal/consents', {'purpose':'ledger_read'}, headers['b']),
                        (f'/portal/consents/{grant.id}/revoke', None, headers['b'])]:
                        response = await http.post(path, json=body, headers=auth)
                        assert response.status_code == 503 and response.json() == {'detail':'portal_write_capacity_exhausted'}
                    assert (await http.get('/portal/requests', headers=headers['b'])).status_code == 200
                    assert (await http.get('/admin/users')).status_code == 200
                finally:
                    release.set()
                    responses = await asyncio.gather(*pending, return_exceptions=True)
                assert all(response.status_code == 200 for response in responses)
    finally:
        release.set()
        await asyncio.gather(*pending, return_exceptions=True)
        await services.aclose()


@pytest.mark.parametrize('order', ['erase-first', 'decision-first'])
async def test_rights_decision_real_erasure_order_and_atomic_visibility(database, settings, monkeypatch, log_output, order):
    import asyncio
    from threading import Event, current_thread
    import httpx
    from sqlalchemy import event, text
    from app.candidates.store import CandidateStore
    from app.core.db import make_session_factory
    engine, factory = database
    settings.portal_write_max_concurrent_requests = 1
    settings.portal_write_wait_seconds = 1 if order == 'decision-first' else 20
    services, _, record, rows = _decision_setup(settings, factory)
    entered, release, deleting, pids = Event(), Event(), Event(), {}
    deleter_factory = make_session_factory(engine)
    original = services.rights._store.resolve
    def hold():
        entered.set()
        assert release.wait(10)
    def wrapped(*args, **kwargs):
        if order == 'erase-first':
            hold()
        return original(*args, **kwargs)
    def committing(session):
        if order == 'decision-first' and current_thread().name.startswith('portal-write') and not entered.is_set():
            if engine.dialect.name == 'postgresql':
                pids['writer'] = session.connection().scalar(text('SELECT pg_backend_pid()'))
            hold()
    def deletion_started(session, transaction, connection):
        if engine.dialect.name == 'postgresql':
            pids['deleter'] = connection.scalar(text('SELECT pg_backend_pid()'))
        deleting.set()
    app, erase = create_app(services), None
    try:
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(services.rights._store, 'resolve', wrapped)
            event.listen(factory, 'before_commit', committing)
            event.listen(deleter_factory, 'after_begin', deletion_started, once=True)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.post(f'/admin/requests/{record.id}/resolve', json=DECISION))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == 200
                    if order == 'erase-first':
                        assert await asyncio.to_thread(CandidateStore(deleter_factory).delete_candidate, 'a')
                        release.set()
                        response = await pending
                        assert response.status_code == 404 and response.json() == {'detail':'request not found'}
                    else:
                        # All three effects exist only in the owning transaction.
                        visible = [r for r in (await http.get('/admin/requests')).json() if r['id'] == record.id][0]
                        assert visible['status'] == 'open' and not visible['applied']
                        assert (await http.get('/candidates/a')).json()['full_name'] == 'Original synthetic name'
                        assert not services.ledger.audit_for_candidate('a')
                        erase = asyncio.create_task(asyncio.to_thread(CandidateStore(deleter_factory).delete_candidate, 'a'))
                        assert await asyncio.to_thread(deleting.wait, 8)
                        if engine.dialect.name == 'postgresql':
                            async with asyncio.timeout(8):
                                with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                    while pids['writer'] not in observer.scalar(text('SELECT pg_blocking_pids(:pid)'), {'pid':pids['deleter']}):
                                        await asyncio.sleep(.01)
                        assert not erase.done(), 'erasure did not wait for the atomic decision'
                        response = await asyncio.wait_for(pending, 3)
                        assert response.status_code == 503 and response.json() == {'detail':'portal_write_pending'}
                finally:
                    release.set()
                    await asyncio.gather(pending, return_exceptions=True)
                    if erase is not None:
                        assert await asyncio.wait_for(erase, 8)
                    async with asyncio.timeout(10):
                        while services.portal_writes._active:
                            await asyncio.sleep(.01)
                assert services.rights.for_candidate('a') == [] and services.ledger.audit_for_candidate('a') == []
                assert services.candidates.get_candidate('a') is None
                assert services.rights.for_candidate('b') == [rows['b']]
    finally:
        release.set()
        await services.aclose()
        if event.contains(factory, 'before_commit', committing):
            event.remove(factory, 'before_commit', committing)
        if event.contains(deleter_factory, 'after_begin', deletion_started):
            event.remove(deleter_factory, 'after_begin', deletion_started)
    assert DECISION['resolution'] not in log_output.text and 'UPDATE data_principal_requests' not in log_output.text


@pytest.mark.parametrize('failure', ['actor-fk', 'audit-constraint'])
def test_rights_decision_unrelated_constraint_rolls_back_every_effect(database, settings, monkeypatch, log_output, failure):
    from sqlalchemy import event
    from app.ledger.models import AuditLogRow
    _, factory = database
    services, _, record, _ = _decision_setup(settings, factory)
    original = services.rights.resolve
    def wrong_actor(*args, **kwargs):
        return original(*args, **{**kwargs, 'resolved_by':ResolvedBy.ADMIN_USER, 'admin_user_id':'missing-operator'})
    def invalid_audit(session, *_):
        for row in session.new:
            if isinstance(row, AuditLogRow) and row.action == 'request.resolve':
                row.actor_type = None
    if failure == 'actor-fk':
        monkeypatch.setattr(services.rights, 'resolve', wrong_actor)
    else:
        event.listen(factory, 'before_flush', invalid_audit)
    try:
        with TestClient(create_app(services), headers=ADMIN_HEADERS, raise_server_exceptions=False) as http:
            response = http.post(f'/admin/requests/{record.id}/resolve', json=DECISION)
            assert response.status_code == 500
            assert response.json() == {'detail':'internal_error', 'request_id':response.headers['x-request-id']}
            saved = services.rights._store.get(record.id)[0]
            assert saved.status == 'open' and not saved.applied and saved.resolved_at is None
            assert services.candidates.get_candidate('a').full_name == 'Original synthetic name'
            assert not services.ledger.audit_for_candidate('a')
    finally:
        if event.contains(factory, 'before_flush', invalid_audit):
            event.remove(factory, 'before_flush', invalid_audit)
    assert DECISION['resolution'] not in log_output.text and 'INSERT INTO' not in log_output.text


def test_rights_named_decision_preserves_actor_and_cookie_csrf(database, settings, tmp_path):
    from app.rights.models import DataPrincipalRequestRow
    _, factory = database
    settings.email_provider = 'capture'
    settings.email_capture_path = str(tmp_path / 'operator-mail.jsonl')
    settings.session_cookie_secure = False
    settings.session_cookie_samesite = 'lax'
    services, _, record, _ = _decision_setup(settings, factory)
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as http:
        http.post('/admin/users', json={'email':'synthetic-operator@example.in'})
        assert http.post('/auth/admin/login', json={'email':'synthetic-operator@example.in'}).status_code == 202
        message = json.loads((tmp_path / 'operator-mail.jsonl').read_text(encoding='utf-8').splitlines()[-1])
        code = re.search(r'\b(\d{6})\b', message['body']).group(1)
        signed = http.post('/auth/admin/verify', json={'email':'synthetic-operator@example.in', 'code':code}).json()
        path = f'/admin/requests/{record.id}/resolve'
        assert http.post(path, json=DECISION).status_code == 403
        assert services.rights._store.get(record.id)[0].status == 'open'
        response = http.post(path, json=DECISION, headers={'X-CSRF-Token':signed['csrf_token']})
        assert response.status_code == 200 and response.json()['resolved_by'] == 'admin_user'
        with factory() as session:
            actor_id = session.get(DataPrincipalRequestRow, record.id).resolved_by_admin_user_id
            assert actor_id is not None and actor_id not in response.text
        audit = [r for r in services.ledger.audit_for_candidate('a') if r.action == 'request.resolve']
        assert len(audit) == 1 and audit[0].actor_id == actor_id


@pytest.fixture
def capture_path(tmp_path):
    return tmp_path / "mailbox.jsonl"


@pytest.fixture
def _setup(settings):
    services = make_services(settings)
    with TestClient(
        create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS
    ) as client:
        yield client, services


def _candidate_with_key(client, email="d@e.com"):
    cid = client.post("/candidates", json={
        "resume_text": f"Asha R\nEmail: {email}\nSKILLS\nPython\n", "evaluate": False,
    }).json()["candidate_id"]
    key = client.post(f"/candidates/{cid}/auth-key").json()["access_key"]
    return cid, {"X-Candidate-Key": key}


def _file_correction(client, headers, field="full_name", value="Asha Rao"):
    return client.post("/portal/corrections", headers=headers,
                       json={"field": field, "requested_value": value}).json()


def test_both_admin_routes_need_the_admin_credential(settings):
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        assert c.get("/admin/requests").status_code == 401
        assert c.post("/admin/requests/x/resolve", json={}).status_code == 401


def test_the_operator_lists_open_requests(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    _file_correction(client, h)
    listed = client.get("/admin/requests?status=open").json()
    assert len(listed) == 1
    assert listed[0]["field"] == "full_name"
    assert listed[0]["current_value"] == "Asha R"


def test_the_operator_sees_EVERY_candidates_requests(_setup):
    """The admin plane is not tenant-scoped -- an operator handling complaints
    has to see the queue, not one person's slice of it."""
    client, _ = _setup
    _, one = _candidate_with_key(client, email="one@e.com")
    _, two = _candidate_with_key(client, email="two@e.com")
    client.post("/portal/grievances", headers=one, json={"note": "a"})
    client.post("/portal/grievances", headers=two, json={"note": "b"})
    assert {r["note"] for r in client.get("/admin/requests").json()} == {"a", "b"}


def test_resolving_with_apply_updates_the_candidate_and_the_portal_shows_it(_setup):
    client, services = _setup
    cid, h = _candidate_with_key(client)
    submitted = _file_correction(client, h)
    r = client.post(f"/admin/requests/{submitted['id']}/resolve",
                    json={"status": "resolved", "resolution": "checked the ID",
                          "apply": True})
    assert r.status_code == 200 and r.json()["applied"] is True

    me = client.get("/portal/me", headers=h).json()
    assert me["requests"][0]["status"] == "resolved"
    assert me["requests"][0]["applied"] is True
    # The IDENTITY row is what moved. `profile` is the EXTRACTION's view and is
    # deliberately untouched (spec §8.2), so assert the column directly.
    assert services.candidates.get_candidate(cid).full_name == "Asha Rao"


def test_applying_an_email_correction_is_422_and_names_the_reason(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    submitted = _file_correction(client, h, field="email",
                                 value="new@example.com")
    r = client.post(f"/admin/requests/{submitted['id']}/resolve",
                    json={"status": "resolved", "resolution": "ok", "apply": True})
    assert r.status_code == 422
    assert "login" in r.json()["detail"].lower()


def test_an_email_correction_can_still_be_resolved_without_apply(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    submitted = _file_correction(client, h, field="email",
                                 value="new@example.com")
    r = client.post(f"/admin/requests/{submitted['id']}/resolve",
                    json={"status": "resolved",
                          "resolution": "changed by hand after an ID check",
                          "apply": False})
    assert r.status_code == 200
    assert r.json()["status"] == "resolved" and r.json()["applied"] is False


def test_an_unknown_request_id_is_404(_setup):
    client, _ = _setup
    r = client.post("/admin/requests/nope/resolve",
                    json={"status": "resolved", "resolution": "x", "apply": False})
    assert r.status_code == 404


def test_resolving_twice_is_409(_setup):
    """409 and not 422: a second decision on a decided request is a different
    operator mistake from an impermissible one, and collapsing them makes the
    second unactionable."""
    client, _ = _setup
    _, h = _candidate_with_key(client)
    submitted = client.post("/portal/grievances", headers=h,
                            json={"note": "nobody answered"}).json()
    body = {"status": "resolved", "resolution": "called them", "apply": False}
    assert client.post(f"/admin/requests/{submitted['id']}/resolve",
                       json=body).status_code == 200
    assert client.post(f"/admin/requests/{submitted['id']}/resolve",
                       json=body).status_code == 409


def test_a_decision_without_a_reason_is_422(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    submitted = _file_correction(client, h)
    r = client.post(f"/admin/requests/{submitted['id']}/resolve",
                    json={"status": "rejected", "resolution": "  ", "apply": False})
    assert r.status_code == 422


def test_a_machine_key_resolution_is_recorded_as_a_KEY_not_as_a_person(_setup):
    """S8.5's `recorded_by` argument at a second table: the shared admin key
    has no human behind it, and a null admin_user_id alone would be
    indistinguishable from an admin who was later deleted."""
    client, services = _setup
    _, h = _candidate_with_key(client)
    submitted = client.post("/portal/grievances", headers=h,
                            json={"note": "x"}).json()
    client.post(f"/admin/requests/{submitted['id']}/resolve",
                json={"status": "resolved", "resolution": "done", "apply": False})

    row = services.rights.list_by_status(None, limit=10)[0]
    assert row.resolved_by is ResolvedBy.OPERATOR_KEY
    # And the subject is told the KIND of decider, never a person's identity.
    shown = client.get("/portal/requests", headers=h).json()[0]
    assert shown["resolved_by"] == "operator_key"


def test_the_resolution_appears_in_the_subjects_access_log(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    submitted = client.post("/portal/grievances", headers=h,
                            json={"note": "x"}).json()
    client.post(f"/admin/requests/{submitted['id']}/resolve",
                json={"status": "resolved", "resolution": "done", "apply": False})
    log = client.get("/portal/access-log", headers=h).json()
    actions = [e["action"] for e in log
               if e["entity_type"] == "data_principal_request"]
    assert sorted(actions) == ["request.resolve", "request.submit"]


def test_an_unknown_status_filter_is_refused_by_the_MODEL(_setup):
    client, _ = _setup
    assert client.get("/admin/requests?status=pending").status_code == 422


def test_a_NAMED_OPERATOR_is_recorded_as_a_person_not_as_the_shared_key(
    settings, capture_path, flywheel
):
    """REVIEW GAP. `resolved_by`/`resolved_by_admin_user_id` exist precisely to
    distinguish a human from the machine credential -- and every test above,
    and the smoke, authenticates with `X-API-Key`, which has no human behind
    it. The ADMIN_USER arm was reachable in production (an operator who logged
    in through /auth/admin/verify has a session carrying admin_user_id) and
    exercised nowhere.

    If `principal.admin_user_id` were mis-wired, every human decision would be
    filed as `operator_key` and the column that exists to prevent exactly that
    confusion would be silently useless. This is the S8.5 lesson -- its smoke
    had to sign up through a real session to prove a real org_user id lands on
    the row -- applied to the plane S8.5 did not cover.
    """
    cfg = settings.model_copy(update={
        "email_provider": "capture",
        "email_capture_path": str(capture_path),
        "session_cookie_secure": False,
        "session_cookie_samesite": "lax",
    })
    services = make_services(cfg, flywheel=flywheel)
    # The admin header is for the SETUP calls (creating a candidate and its
    # key). The resolve below is answered by the SESSION: AuthService.resolve
    # prefers it when both arrive, which is why CSRF is required there and why
    # admin_user_id is set at all (S8.2).
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as client:
        _, h = _candidate_with_key(client)
        submitted = client.post("/portal/grievances", headers=h,
                                json={"note": "nobody answered"}).json()

        # A NAMED operator, logging in with no shared secret in sight.
        client.post("/admin/users", json={"email": "op@veritas.in"},
                    headers=ADMIN_HEADERS)
        client.post("/auth/admin/login", json={"email": "op@veritas.in"})
        line = json.loads(
            capture_path.read_text(encoding="utf-8").splitlines()[-1]
        )
        code = re.search(r"\b(\d{6})\b", line["body"]).group(1)
        csrf = client.post(
            "/auth/admin/verify", json={"email": "op@veritas.in", "code": code},
        ).json()["csrf_token"]

        r = client.post(
            f"/admin/requests/{submitted['id']}/resolve",
            headers={"X-CSRF-Token": csrf},
            json={"status": "resolved", "resolution": "called them",
                  "apply": False},
        )
        assert r.status_code == 200, r.text
        assert r.json()["resolved_by"] == "admin_user"

        row = services.rights.list_by_status(None, limit=10)[0]
        assert row.resolved_by is ResolvedBy.ADMIN_USER
        # And the FK carries WHICH person, which is the whole point of having
        # two columns rather than one.
        stored = services.rights._store.get(submitted["id"])
        assert stored is not None
        with services.rights._store._session_factory() as s:
            from app.rights.models import DataPrincipalRequestRow

            saved = s.get(DataPrincipalRequestRow, submitted["id"])
            assert saved.resolved_by_admin_user_id is not None


def test_the_queue_limit_is_CLAMPED_like_every_other_paged_read(_setup):
    """REVIEW FINDING. Every paged read in this repo goes through
    `clamp_limit` (page_max_limit = 200); this route took a raw `limit: int`
    and handed it to SQL.

    `?limit=-1` is the one that matters: SQLite reads a negative LIMIT as
    UNLIMITED, so a bound that looks present returns the entire table -- on the
    one table that holds every data principal's complaints, including their
    free-text notes. `?limit=10000000` is the same read with an honest-looking
    number.
    """
    client, services = _setup
    _, h = _candidate_with_key(client)
    for i in range(4):
        client.post("/portal/grievances", headers=h, json={"note": f"n{i}"})

    assert client.get("/admin/requests?limit=2").status_code == 200
    assert len(client.get("/admin/requests?limit=2").json()) == 2

    # Over the cap: capped, not refused -- a client asking for too much should
    # get a page, not an error it cannot size correctly on its first call.
    huge = client.get(f"/admin/requests?limit={10 ** 7}")
    assert huge.status_code == 200
    assert len(huge.json()) <= services.settings.page_max_limit

    # Nonsensical: refused, and NEVER passed through to SQL.
    assert client.get("/admin/requests?limit=-1").status_code == 422
    assert client.get("/admin/requests?limit=0").status_code == 422
