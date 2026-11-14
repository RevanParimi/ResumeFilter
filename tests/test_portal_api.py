from datetime import datetime, timezone
import asyncio
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import create_app
from app.candidates.store import CandidateStore
from app.ledger.schema import InterviewOutcome, InterviewStage
from tests.conftest import ADMIN_HEADERS, make_services
from tests.test_report_erasure_concurrency import database  # noqa: F401


PORTAL_READS = [('me', '/portal/me', 'my_data', 'from resumes'),
    ('access', '/portal/access-log', 'access_log', 'from audit_log'),
    ('consents', '/portal/consents', 'consents', 'from consent_grants')]


def _portal_read_setup(settings, factory):
    from app.schemas.report import Report
    services = make_services(settings, candidates=CandidateStore(factory))
    headers = {cid: {'X-Candidate-Key': services.candidates.issue_access_key(cid)} for cid in ('a', 'b')}
    for cid in headers:
        services.ledger.grant_consent(candidate_id=cid, purpose='ledger_read')
        services.report_store.save(Report(candidate_id=cid, summary='Synthetic private ' + cid))
    return services, headers


@pytest.mark.parametrize('case,path,method,needle', PORTAL_READS, ids=[r[0] for r in PORTAL_READS])
async def test_portal_read_sql_leaves_unrelated_requests_responsive(database, settings, case, path, method, needle):
    engine, factory = database
    services, headers = _portal_read_setup(settings, factory)
    entered, release, finished = Event(), Event(), Event()
    def sql(conn, cursor, statement, parameters, context, many):
        if needle in statement.lower() and not entered.is_set():
            entered.set()
            release.wait(3)
            finished.set()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                event.listen(engine, 'before_cursor_execute', sql)
                pending = asyncio.create_task(http.get(path, headers=headers['a']))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == 200
                    assert (await http.get('/admin/users')).status_code == 200
                    assert not finished.is_set(), 'portal SQL blocked the event loop'
                finally:
                    release.set()
                    assert (await pending).status_code == 200
    finally:
        release.set()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)
        await services.aclose()


@pytest.mark.parametrize('case,path,method,needle', PORTAL_READS, ids=[r[0] for r in PORTAL_READS])
@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'late_failure', 'failure'])
async def test_portal_read_ownership_admission_and_recovery(database, settings, monkeypatch, log_output,
    case, path, method, needle, ending):
    from threading import get_ident, current_thread
    _, factory = database
    settings.portal_read_max_concurrent_requests = 1
    settings.portal_read_wait_seconds = .2 if ending in ('timeout', 'late_failure') else 20
    services, headers = _portal_read_setup(settings, factory)
    entered, release = Event(), Event()
    caller, calls, sessions = get_ident(), [], []
    original = getattr(services.portal, method)
    def observed(*args):
        calls.append(get_ident())
        entered.set()
        assert release.wait(15)
        if ending in ('late_failure', 'failure'):
            raise RuntimeError('synthetic-private-portal-read-error')
        return original(*args)
    def begin(session, transaction, connection):
        assert session.info.setdefault('portal_owner', get_ident()) == get_ident()
        if current_thread().name.startswith('portal-read'):
            sessions.append(get_ident())
    def end(session, transaction):
        assert session.info.get('portal_owner', get_ident()) == get_ident()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url='http://test', headers=ADMIN_HEADERS) as http:
                expected = (await http.get(path, headers=headers['a'])).json()
                monkeypatch.setattr(services.portal, method, observed)
                event.listen(factory, 'after_begin', begin)
                event.listen(factory, 'after_transaction_end', end)
                pending = asyncio.create_task(http.get(path, headers=headers['a']))
                try:
                    assert await asyncio.to_thread(entered.wait, 10)
                    assert (await http.get('/healthz')).status_code == 200
                    assert (await http.get('/admin/users')).status_code == 200
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as anonymous:
                        assert (await anonymous.get(path)).status_code == 401
                    for _, peer, _, _ in PORTAL_READS:
                        busy = await http.get(peer, headers=headers['b'])
                        assert busy.status_code == 503 and busy.json() == {'detail': 'portal_read_capacity_exhausted'}
                        assert busy.headers['retry-after'] == '1' and 'set-cookie' not in busy.headers
                    if ending in ('timeout', 'late_failure'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503 and response.json() == {'detail': 'portal_read_pending'}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    assert len(services.portal_reads._active) == 1
                    assert len(calls) == 1
                finally:
                    release.set()
                    responses = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.portal_reads._active:
                            await asyncio.sleep(.01)
                assert len(calls) == 1 and calls[0] != caller
                if ending == 'release':
                    assert responses[0].status_code == 200 and responses[0].json() == expected
                    assert sessions and set(sessions) == {calls[0]}
                if ending == 'failure':
                    assert responses[0].status_code == 500
                    assert responses[0].json() == {'detail': 'internal_error',
                        'request_id': responses[0].headers['x-request-id']}
                    assert 'synthetic-private' not in responses[0].text
                    assert 'portal_read_failed' in log_output.text
                monkeypatch.setattr(services.portal, method, original)
                services.portal_reads._wait_seconds = 20
                fresh = await http.get(path, headers=headers['a'])
                assert fresh.status_code == 200 and fresh.json() == expected
                assert (await http.get('/portal/me?candidate_id=a', headers=headers['b'])).json()['candidate_id'] == 'b'
                services.portal_reads.close()
                closed = await http.get(path, headers=headers['a'])
                assert closed.status_code == 503 and closed.json() == {'detail': 'portal_read_executor_closed'}
                assert closed.headers['retry-after'] == '1' and 'set-cookie' not in closed.headers
    finally:
        release.set()
        await services.aclose()
        for name, listener in [('after_begin', begin), ('after_transaction_end', end)]:
            if event.contains(factory, name, listener):
                event.remove(factory, name, listener)
    assert 'synthetic-private-portal-read-error' not in log_output.text


async def test_portal_default_read_pool_shares_two_slots_and_keeps_auth_independent(database, settings):
    from threading import Condition, current_thread, get_ident
    engine, factory = database
    services, headers = _portal_read_setup(settings, factory)
    assert services.portal_reads._capacity == 2 and services.portal_reads._wait_seconds == 20
    from app.rights.schema import RequestKind
    request_b = services.rights.submit('b', kind=RequestKind.GRIEVANCE, field=None,
        requested_value='', note='Synthetic B request', now=datetime.now(timezone.utc))
    release, condition, owners = Event(), Condition(), set()
    def sql(conn, cursor, statement, parameters, context, many):
        if current_thread().name.startswith('portal-read'):
            with condition:
                owners.add(get_ident())
                condition.notify_all()
            assert release.wait(15)
    def occupied():
        with condition:
            return condition.wait_for(lambda: len(owners) == 2, timeout=10)
    app = create_app(services)
    pending = []
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                expected_a = services.portal.my_data('a').model_dump(mode='json')
                expected_b = [row.model_dump(mode='json') for row in services.portal.consents('b')]
                pending = [asyncio.create_task(http.get(path, headers=headers[cid]))
                    for cid, path in [('a', '/portal/me'), ('b', '/portal/consents')]]
                try:
                    assert await asyncio.to_thread(occupied)
                    assert len(services.portal_reads._active) == 2
                    peer = await http.get('/portal/requests', headers=headers['b'])
                    assert peer.status_code == 200 and [row['id'] for row in peer.json()] == [request_b.id]
                    assert (await http.get('/candidates/b')).status_code == 200
                    for _, path, _, _ in PORTAL_READS:
                        busy = await http.get(path, headers=headers['a'])
                        assert busy.status_code == 503 and busy.json() == {'detail': 'portal_read_capacity_exhausted'}
                finally:
                    release.set()
                    responses = await asyncio.gather(*pending, return_exceptions=True)
                a, b = responses
                assert a.status_code == b.status_code == 200
                assert a.json() == expected_a and b.json() == expected_b
                assert {r['report_id'] for r in a.json()['reports']} == {r.id for r in services.report_store.for_candidate('a')}
    finally:
        release.set()
        await asyncio.gather(*pending, return_exceptions=True)
        await services.aclose()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)


@pytest.mark.parametrize('case,path,method,needle', PORTAL_READS, ids=[r[0] for r in PORTAL_READS])
async def test_portal_read_refuses_erasure_after_materialization(database, settings, monkeypatch, case, path, method, needle):
    _, factory = database
    services, headers = _portal_read_setup(settings, factory)
    entered, release = Event(), Event()
    require, calls = services.portal._require_candidate, []
    def guard(cid):
        if cid == 'a':
            calls.append(cid)
            if len(calls) == (2 if case == 'me' else 1):
                entered.set()
                assert release.wait(10)
        return require(cid)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(services.portal, '_require_candidate', guard)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get(path, headers=headers['a']))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert await asyncio.to_thread(services.candidates.delete_candidate, 'a')
                finally:
                    release.set()
                    responses = await asyncio.gather(pending, return_exceptions=True)
                response = responses[0]
                assert response.status_code == 404 and response.json() == {'detail': 'candidate not found'}
                assert (await http.get(path, headers=headers['a'])).status_code == 401
                assert (await http.get('/portal/me', headers=headers['b'])).json()['candidate_id'] == 'b'
    finally:
        release.set()
        await services.aclose()


@pytest.mark.parametrize('case,path,method,needle', PORTAL_READS, ids=[r[0] for r in PORTAL_READS])
@pytest.mark.parametrize('ending', ['rollback', 'erase'])
async def test_portal_read_real_lock_pending_and_erasure(database, settings, case, path, method, needle, ending):
    from sqlalchemy import text
    from app.core.blocking import ExecutionUnavailable
    engine, factory = database
    settings.portal_read_max_concurrent_requests = 1
    settings.portal_read_wait_seconds = .2
    services, headers = _portal_read_setup(settings, factory)
    entered, proceed, pids = Event(), Event(), []
    def sql(conn, cursor, statement, parameters, context, many):
        if needle in statement.lower() and not entered.is_set():
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
            assert proceed.wait(10)
    app = create_app(services)
    blocker = None
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get(path, headers=headers['a']))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    blocker = engine.connect()
                    if engine.dialect.name == 'sqlite':
                        blocker.exec_driver_sql('BEGIN EXCLUSIVE')
                    else:
                        blocker.execute(text('LOCK TABLE ' + needle.removeprefix('from ') + ' IN ACCESS EXCLUSIVE MODE'))
                    proceed.set()
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(8):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    assert (await http.get('/healthz')).status_code == 200
                    response = await asyncio.wait_for(pending, 2)
                    assert response.status_code == 503 and response.json() == {'detail': 'portal_read_pending'}
                    assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    # SQLite EXCLUSIVE also blocks credential reads. Probe the
                    # admitted pool directly, separately from HTTP auth here.
                    with pytest.raises(ExecutionUnavailable, match='portal_read_capacity_exhausted'):
                        await services.portal_reads.run(lambda: None)
                    if ending == 'erase':
                        blocker.execute(text('DELETE FROM candidates WHERE id = :cid'), {'cid': 'a'})
                        blocker.commit()
                finally:
                    proceed.set()
                    if blocker is not None:
                        blocker.rollback()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.portal_reads._active:
                            await asyncio.sleep(.01)
                services.portal_reads._wait_seconds = 20
                fresh = await http.get(path, headers=headers['a'])
                assert fresh.status_code == (401 if ending == 'erase' else 200)
                assert (await http.get('/portal/me', headers=headers['b'])).json()['candidate_id'] == 'b'
    finally:
        proceed.set()
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        await services.aclose()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)


@pytest.fixture
def _setup(settings):
    # NOTE (mirrors tests/test_candidate_auth_api.py `_client`): a plain
    # TestClient does not run the app lifespan, so app.state.services is never
    # set and every request 500s. Enter via a pytest fixture wrapping a `with`
    # block so every route here resolves `_services(request)` correctly, AND
    # the lifespan shutdown (closing the background portal thread) runs on
    # fixture teardown even if the test body raises.
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS) as client:
        yield client, services


def _candidate_with_key(client, email="d@e.com"):
    # NOTE: candidate identity resolution (S1.1) matches on email_hash, so two
    # uploads sharing an email resolve to the SAME candidate_id (by design —
    # that's how resume-version dedup works). test_cross_candidate_isolation
    # needs two genuinely DISTINCT candidates, so it passes distinct emails;
    # every other caller keeps the brief's original single shared default.
    cid = client.post("/candidates", json={
        "resume_text": f"Dev\nEmail: {email}\nSKILLS\nPython\n", "evaluate": False,
    }).json()["candidate_id"]
    key = client.post(f"/candidates/{cid}/auth-key").json()["access_key"]
    return cid, {"X-Candidate-Key": key}


def test_portal_me_returns_access_view(_setup):
    client, _ = _setup
    cid, h = _candidate_with_key(client)
    r = client.get("/portal/me", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["candidate_id"] == cid
    assert len(body["resumes"]) == 1
    # TRUE since S8.3 Phase B -- the sweep exists and this value is derived
    # from retention_sweep_enabled rather than hardcoded.
    assert body["retention"]["sweep_active"] is True
    assert body["retention"]["windows"]  # posture present


def test_portal_access_log_shows_org_disclosure(_setup):
    client, services = _setup
    cid, h = _candidate_with_key(client)
    org = services.ledger.create_organization("Acme")
    services.ledger.grant_consent(candidate_id=cid, purpose="ledger_write", org_id=org.id)
    services.ledger.grant_consent(candidate_id=cid, purpose="ledger_read", org_id=org.id)
    services.ledger.submit_interview_record(
        org_id=org.id, candidate_id=cid, stage=InterviewStage.TECH,
        outcome=InterviewOutcome.ADVANCED, interviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    services.ledger.query_records_for_org(org_id=org.id, candidate_id=cid)
    r = client.get("/portal/access-log", headers=h)
    assert r.status_code == 200
    actions = {e["action"] for e in r.json()}
    assert "record.query" in actions and "record.submit" in actions
    q = next(e for e in r.json() if e["action"] == "record.query")
    assert q["actor_name"] == "Acme" and q["allowed"] is True


def test_portal_first_party_grant_then_revoke(_setup):
    client, _ = _setup
    cid, h = _candidate_with_key(client)
    g = client.post("/portal/consents", headers=h, json={"purpose": "ledger_read"})
    assert g.status_code == 200
    gid = g.json()["id"]
    assert client.get("/portal/consents", headers=h).status_code == 200
    rv = client.post(f"/portal/consents/{gid}/revoke", headers=h)
    assert rv.status_code == 200 and rv.json()["revoked"] is True
    # state now revoked
    states = {c["grant"]["id"]: c["state"] for c in client.get("/portal/consents", headers=h).json()}
    assert states[gid] == "revoked"


def test_grant_unknown_org_404(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    r = client.post("/portal/consents", headers=h, json={"purpose": "ledger_read", "org_id": "ghost"})
    assert r.status_code == 404


def test_cross_candidate_isolation(_setup):
    client, services = _setup
    a, ha = _candidate_with_key(client, email="a@e.com")
    b, hb = _candidate_with_key(client, email="b@e.com")
    assert a != b
    g_b = services.ledger.grant_consent(candidate_id=b, purpose="ledger_read")
    # A revoking B's grant → 404, B's grant untouched
    assert client.post(f"/portal/consents/{g_b.id}/revoke", headers=ha).status_code == 404
    assert services.ledger.get_grant(g_b.id).revoked_at is None
    # A's /portal/me never contains B
    assert client.get("/portal/me", headers=ha).json()["candidate_id"] == a


def test_self_erase_kills_the_key(_setup):
    client, _ = _setup
    cid, h = _candidate_with_key(client)
    d = client.delete("/portal/me", headers=h)
    assert d.status_code == 200 and d.json()["deleted"] is True
    # key no longer authenticates
    assert client.get("/portal/me", headers=h).status_code == 401
