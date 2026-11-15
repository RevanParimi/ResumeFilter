"""The candidate plane files corrections and grievances (S8.3 Phase B)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services
from tests.test_report_erasure_concurrency import database  # noqa: F401


RIGHTS_READS = [('candidate', '/portal/requests', 'for_candidate'),
    ('operator', '/admin/requests', 'list_by_status')]


def _rights_read_setup(settings, factory):
    from app.candidates.store import CandidateStore
    from app.rights.schema import RequestKind
    services = make_services(settings, candidates=CandidateStore(factory))
    headers = {cid: {'X-Candidate-Key': services.candidates.issue_access_key(cid)} for cid in ('a', 'b')}
    rows = {cid: services.rights._store.create(cid, kind=RequestKind.GRIEVANCE,
        field=None, current_value='', requested_value='', note='Synthetic private request ' + cid)
        for cid in ('a', 'b')}
    return services, headers, rows


@pytest.mark.parametrize('case,path,method', RIGHTS_READS)
async def test_rights_read_sql_keeps_unrelated_requests_responsive(database, settings, case, path, method):
    import asyncio
    from threading import Event
    import httpx
    from sqlalchemy import event
    engine, factory = database
    services, headers, _ = _rights_read_setup(settings, factory)
    entered, release, finished = Event(), Event(), Event()
    def sql(conn, cursor, statement, parameters, context, many):
        if 'from data_principal_requests' in statement.lower() and not entered.is_set():
            entered.set()
            release.wait(3)
            finished.set()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get(path, headers=headers['a'] if case == 'candidate' else {}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == 200
                    assert (await http.get('/admin/users')).status_code == 200
                    assert not finished.is_set(), 'rights SQL blocked the event loop'
                finally:
                    release.set()
                    assert (await pending).status_code == 200
    finally:
        release.set()
        await services.aclose()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)


@pytest.mark.parametrize('case,path,method', RIGHTS_READS)
def test_rights_materialized_views_omit_erased_subject(database, settings, monkeypatch, case, path, method):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import app.rights.store as store_module
    engine, factory = database
    services, _, rows = _rights_read_setup(settings, factory)
    entered, release = Event(), Event()
    original = store_module._view
    def materialize(row):
        view = original(row)
        if view.id == rows['a'].id:
            entered.set()
            assert release.wait(10)
        return view
    monkeypatch.setattr(store_module, '_view', materialize)
    operation = (lambda: services.rights.for_candidate('a')) if case == 'candidate' else (
        lambda: services.rights.list_by_status(None, 50))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(operation)
        try:
            assert entered.wait(8)
            assert services.candidates.delete_candidate('a')
        finally:
            release.set()
        result = pending.result(timeout=10)
    assert [view.id for view in result] == ([] if case == 'candidate' else [rows['b'].id])


@pytest.mark.parametrize('case,path,method', RIGHTS_READS)
@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'failure', 'late_failure'])
async def test_rights_read_owns_sessions_admission_and_safe_recovery(database, settings, monkeypatch, log_output, case, path, method, ending):
    import asyncio
    from threading import Event, current_thread, get_ident
    import httpx
    from sqlalchemy import event
    _, factory = database
    settings.portal_read_max_concurrent_requests = 1
    settings.portal_read_wait_seconds = .2 if ending in ('timeout', 'late_failure') else 20
    services, headers, rows = _rights_read_setup(settings, factory)
    expected = [rows['a'].model_dump(mode='json')] if case == 'candidate' else [rows[cid].model_dump(mode='json') for cid in ('a', 'b')]
    entered, release, owners, sessions = Event(), Event(), [], []
    caller, original = get_ident(), getattr(services.rights, method)
    def begin(session, transaction, connection):
        if current_thread().name.startswith('portal-read'):
            sessions.append(get_ident())
            session.info['rights_owner'] = get_ident()
    def end(session, transaction):
        if 'rights_owner' in session.info:
            assert session.info['rights_owner'] == get_ident()
    def work(*args, **kwargs):
        owners.append(get_ident())
        entered.set()
        assert release.wait(10)
        if ending in ('failure', 'late_failure'):
            raise RuntimeError('synthetic-private-rights-error')
        return original(*args, **kwargs)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            event.listen(factory, 'after_begin', begin)
            event.listen(factory, 'after_transaction_end', end)
            monkeypatch.setattr(services.rights, method, work)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get(path, headers=headers['a'] if case == 'candidate' else {}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/admin/users')).status_code == 200
                    assert (await http.post('/portal/consents', json={'purpose': 'ledger_read'}, headers=headers['b'])).status_code == 200
                    for peer in ('/portal/me', '/portal/access-log', '/portal/consents', '/portal/requests', '/admin/requests'):
                        response = await http.get(peer, headers=headers['b'] if peer.startswith('/portal/') else {})
                        assert response.status_code == 503 and response.json() == {'detail': 'portal_read_capacity_exhausted'}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    if ending in ('timeout', 'late_failure'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503 and response.json() == {'detail': 'portal_read_pending'}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    assert len(services.portal_reads._active) == 1
                finally:
                    release.set()
                    responses = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(10):
                        while services.portal_reads._active:
                            await asyncio.sleep(.01)
                assert len(owners) == 1 and owners[0] != caller
                if ending not in ('failure', 'late_failure'):
                    assert len(sessions) == 2 and set(sessions) == set(owners)
                if ending == 'release':
                    assert responses[0].status_code == 200 and responses[0].json() == expected
                if ending == 'failure':
                    response = responses[0]
                    assert response.status_code == 500
                    assert response.json() == {'detail': 'internal_error', 'request_id': response.headers['x-request-id']}
                    assert 'set-cookie' not in response.headers and 'portal_read_failed' in log_output.text
                monkeypatch.setattr(services.rights, method, original)
                services.portal_reads._wait_seconds = 20
                response = await http.get(path, headers=headers['a'] if case == 'candidate' else {})
                assert response.status_code == 200 and response.json() == expected
                assert (await http.get('/portal/requests?candidate_id=a', headers=headers['b'])).json() == [rows['b'].model_dump(mode='json')]
                services.portal_reads.close()
                response = await http.get(path, headers=headers['a'] if case == 'candidate' else {})
                assert response.status_code == 503 and response.json() == {'detail': 'portal_read_executor_closed'}
                assert response.headers['retry-after'] == '1'
    finally:
        release.set()
        await services.aclose()
        for name, listener in [('after_begin', begin), ('after_transaction_end', end)]:
            if event.contains(factory, name, listener):
                event.remove(factory, name, listener)
    assert 'synthetic-private-rights-error' not in log_output.text


async def test_rights_views_share_both_default_slots_with_portal_views(database, settings):
    import asyncio
    from threading import Event, Condition, current_thread, get_ident
    import httpx
    from sqlalchemy import event
    engine, factory = database
    services, headers, rows = _rights_read_setup(settings, factory)
    assert services.portal_reads._capacity == 2 and services.portal_reads._wait_seconds == 20
    release, condition, owners = Event(), Condition(), set()
    def sql(conn, cursor, statement, parameters, context, many):
        if current_thread().name.startswith('portal-read'):
            with condition:
                owners.add(get_ident())
                condition.notify_all()
            assert release.wait(12)
    def occupied():
        with condition:
            return condition.wait_for(lambda: len(owners) == 2, timeout=8)
    app, pending = create_app(services), []
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = [asyncio.create_task(http.get('/portal/requests', headers=headers['a'])),
                    asyncio.create_task(http.get('/admin/requests?status=open&limit=1'))]
                try:
                    assert await asyncio.to_thread(occupied)
                    for path in ('/portal/me', '/portal/access-log', '/portal/consents', '/portal/requests', '/admin/requests'):
                        response = await http.get(path, headers=headers['b'] if path.startswith('/portal/') else {})
                        assert response.status_code == 503 and response.json() == {'detail': 'portal_read_capacity_exhausted'}
                    assert (await http.get('/admin/users')).status_code == 200
                    assert (await http.post('/portal/consents', json={'purpose': 'ledger_read'}, headers=headers['b'])).status_code == 200
                    assert (await http.get('/admin/requests?limit=-1')).status_code == 422
                finally:
                    release.set()
                    responses = await asyncio.gather(*pending, return_exceptions=True)
                assert [response.json() for response in responses] == [[rows['a'].model_dump(mode='json')]] * 2
    finally:
        release.set()
        await asyncio.gather(*pending, return_exceptions=True)
        await services.aclose()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)


@pytest.mark.parametrize('case,path,method', RIGHTS_READS)
async def test_rights_http_erasure_omits_materialized_notes_without_refilling_limit(database, settings, monkeypatch, case, path, method):
    import asyncio
    from threading import Event
    import httpx
    import app.rights.store as store_module
    _, factory = database
    services, headers, rows = _rights_read_setup(settings, factory)
    entered, release = Event(), Event()
    original = store_module._view
    def materialize(row):
        result = original(row)
        if row.id == rows['a'].id:
            entered.set()
            assert release.wait(10)
        return result
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(store_module, '_view', materialize)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get(path + '?limit=1', headers=headers['a'] if case == 'candidate' else {}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert await asyncio.to_thread(services.candidates.delete_candidate, 'a')
                finally:
                    release.set()
                    responses = await asyncio.gather(pending, return_exceptions=True)
                assert responses[0].status_code == 200 and responses[0].json() == []
                assert 'Synthetic private request a' not in responses[0].text
                assert (await http.get('/portal/requests', headers=headers['a'])).status_code == 401
                assert (await http.get('/portal/requests', headers=headers['b'])).json() == [rows['b'].model_dump(mode='json')]
    finally:
        release.set()
        await services.aclose()


@pytest.mark.parametrize('case,path,method', RIGHTS_READS)
@pytest.mark.parametrize('ending', ['rollback', 'erase'])
async def test_rights_read_real_lock_pending_and_erasure(database, settings, case, path, method, ending):
    import asyncio
    from threading import Event
    import httpx
    from sqlalchemy import event, text
    from app.core.blocking import ExecutionUnavailable
    engine, factory = database
    settings.portal_read_max_concurrent_requests = 1
    settings.portal_read_wait_seconds = .2
    services, headers, rows = _rights_read_setup(settings, factory)
    entered, proceed, pids = Event(), Event(), []
    def sql(conn, cursor, statement, parameters, context, many):
        if 'from data_principal_requests' in statement.lower() and not entered.is_set():
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
            assert proceed.wait(10)
    app, blocker = create_app(services), None
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get(path, headers=headers['a'] if case == 'candidate' else {}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    blocker = engine.connect()
                    if engine.dialect.name == 'sqlite':
                        blocker.exec_driver_sql('BEGIN EXCLUSIVE')
                    else:
                        blocker.execute(text('LOCK TABLE data_principal_requests IN ACCESS EXCLUSIVE MODE'))
                    proceed.set()
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(8):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    response = await asyncio.wait_for(pending, 3)
                    assert response.status_code == 503 and response.json() == {'detail': 'portal_read_pending'}
                    assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    assert (await http.get('/healthz')).status_code == 200
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
                response = await http.get(path, headers=headers['a'] if case == 'candidate' else {})
                assert response.status_code == (401 if ending == 'erase' and case == 'candidate' else 200)
                if case == 'operator' and ending == 'erase':
                    assert response.json() == [rows['b'].model_dump(mode='json')]
                assert (await http.get('/portal/requests', headers=headers['b'])).status_code == 200
    finally:
        proceed.set()
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        await services.aclose()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)


def test_rights_final_snapshot_handles_large_lists_with_bounded_sql_binds(database, settings):
    from datetime import datetime, timezone
    from sqlalchemy import event, insert
    from app.rights.models import DataPrincipalRequestRow
    engine, factory = database
    services, _, _ = _rights_read_setup(settings, factory)
    with factory() as session:
        session.execute(insert(DataPrincipalRequestRow), [dict(id=f'bulk-{i:04}', candidate_id='a',
            kind='grievance', note='Synthetic bulk request', created_at=datetime(2030, 1, 1, tzinfo=timezone.utc))
            for i in range(501)])
        session.commit()
    binds = []
    def sql(conn, cursor, statement, parameters, context, many):
        if 'join candidates' in statement.lower() and 'data_principal_requests.id in (' in statement.lower():
            binds.append(len(parameters))
    event.listen(engine, 'before_cursor_execute', sql)
    try:
        views = services.rights.for_candidate('a')
        assert len(views) == 502 and [view.id for view in views[:501]] == [f'bulk-{i:04}' for i in reversed(range(501))]
        assert sum(binds) == 502 and max(binds) <= 500
    finally:
        event.remove(engine, 'before_cursor_execute', sql)


@pytest.fixture
def _setup(settings):
    # A plain TestClient does not run the app lifespan, so app.state.services
    # is never set and every request 500s -- enter through a `with` block, the
    # tests/test_portal_api.py pattern.
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


def _anon(client):
    """A client carrying NO admin header -- the fixture above sets one app-wide,
    which would otherwise make an unauthenticated assertion untestable."""
    return client


def test_every_request_route_needs_a_candidate_credential(settings):
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        assert c.post("/portal/corrections", json={}).status_code == 401
        assert c.post("/portal/grievances", json={}).status_code == 401
        assert c.get("/portal/requests").status_code == 401


def test_a_correction_round_trips(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    r = client.post("/portal/corrections", headers=h,
                    json={"field": "full_name", "requested_value": "Asha Rao"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "open" and body["applied"] is False
    assert body["kind"] == "correction"

    listed = client.get("/portal/requests", headers=h).json()
    assert [x["id"] for x in listed] == [body["id"]]


def test_a_grievance_round_trips(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    r = client.post("/portal/grievances", headers=h,
                    json={"note": "nobody answered my correction"})
    assert r.status_code == 200
    assert r.json()["kind"] == "grievance"
    assert r.json()["field"] is None


def test_a_refused_submission_is_422_and_says_why(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    r = client.post("/portal/corrections", headers=h,
                    json={"field": "full_name", "requested_value": "   "})
    assert r.status_code == 422
    assert r.json()["detail"]


def test_an_unknown_field_is_refused_by_the_MODEL(_setup):
    """CorrectionField is an enum on the request body, so a field nobody
    implemented is a 422 from FastAPI before any handler runs."""
    client, _ = _setup
    _, h = _candidate_with_key(client)
    r = client.post("/portal/corrections", headers=h,
                    json={"field": "risk_score", "requested_value": "0"})
    assert r.status_code == 422


def test_the_submission_appears_in_the_candidates_own_access_log(_setup):
    """S3.1's rule -- surveillance is itself observable -- applied to the
    handling of the subject's own complaint, which is where it matters most."""
    client, _ = _setup
    _, h = _candidate_with_key(client)
    client.post("/portal/grievances", headers=h, json={"note": "nobody answered"})
    log = client.get("/portal/access-log", headers=h).json()
    assert any(e["entity_type"] == "data_principal_request" for e in log)


def test_a_candidate_never_sees_another_candidates_requests(_setup):
    client, _ = _setup
    _, mine = _candidate_with_key(client, email="one@e.com")
    _, theirs = _candidate_with_key(client, email="two@e.com")
    client.post("/portal/grievances", headers=mine, json={"note": "mine"})
    assert client.get("/portal/requests", headers=theirs).json() == []


def test_the_route_returns_429_when_the_budget_is_spent(_setup):
    client, services = _setup
    _, h = _candidate_with_key(client)
    limit = services.settings.rate_limit_request_per_hour_per_candidate
    for i in range(limit):
        assert client.post("/portal/grievances", headers=h,
                           json={"note": f"n{i}"}).status_code == 200
    over = client.post("/portal/grievances", headers=h, json={"note": "over"})
    assert over.status_code == 429
    assert over.headers["Retry-After"]
    assert over.json()["detail"] == "rate_limited"


def test_my_data_carries_the_subjects_own_requests(_setup):
    """The DPDP access view is everything the platform holds about the person
    that the portal surfaces. A complaint they filed is squarely that -- and a
    mechanism whose state they cannot see is not a mechanism."""
    client, _ = _setup
    _, h = _candidate_with_key(client)
    client.post("/portal/grievances", headers=h, json={"note": "nobody answered"})
    me = client.get("/portal/me", headers=h).json()
    assert [r["note"] for r in me["requests"]] == ["nobody answered"]


def test_my_data_has_no_requests_when_none_were_filed(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    assert client.get("/portal/me", headers=h).json()["requests"] == []
