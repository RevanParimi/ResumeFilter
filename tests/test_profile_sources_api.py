import base64
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.github import GitHubUserRaw
from tests.conftest import ADMIN_HEADERS, FakeGitHub, make_services
from tests.test_report_erasure_concurrency import database  # noqa: F401


@pytest.mark.parametrize('phase', ['initial', 'history', 'final'])
async def test_source_listing_sql_leaves_unrelated_requests_responsive(database, settings, phase):
    import asyncio
    import time
    from threading import Event
    import httpx
    from sqlalchemy import event
    from app.candidates.store import CandidateStore
    from app.profile_sources.schema import ProfileSourceType
    from tests.test_profile_sources_store import _sig
    engine, factory = database
    services = make_services(settings, candidates=CandidateStore(factory))
    store = services.profile_sources._store
    store.save_signal('a', _sig('owned-github'))
    store.save_signal('a', _sig('owned-linkedin').model_copy(update={
        'source_type': ProfileSourceType.LINKEDIN_EXPORT, 'method': 'export'}))
    store.save_signal('b', _sig('other-subject'))
    expected = [s.model_dump(mode='json') for s in services.profile_sources.list_sources('a', ProfileSourceType.GITHUB)]
    entered, release, finished = Event(), Event(), Event()
    history_seen = False
    def sql(conn, cursor, statement, parameters, context, many):
        nonlocal history_seen
        query = statement.upper()
        target = False
        if 'FROM PROFILE_SOURCES' in query:
            history_seen = True
            target = phase == 'history'
        elif 'FROM CANDIDATES' in query:
            target = phase == 'initial' or (phase == 'final' and history_seen)
        if target and not entered.is_set():
            entered.set()
            release.wait(3)
            finished.set()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get('/candidates/a/sources?source_type=github'))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    start = time.monotonic()
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    assert not finished.is_set(), 'source listing SQL blocked the event loop'
                    assert time.monotonic() - start < 1
                finally:
                    release.set()
                    response = await pending
                assert response.status_code == 200 and response.json() == {'candidate_id': 'a', 'sources': expected}
                assert services.github.user_calls == []
    finally:
        release.set()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)
        await services.aclose()


@pytest.mark.parametrize('phase', ['initial', 'history', 'final'])
@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'late_failure'])
async def test_source_listing_uncertainty_retains_shared_admission_without_data(database, settings, monkeypatch, log_output, phase, ending):
    import asyncio
    from threading import Event, get_ident, local
    import httpx
    from sqlalchemy import event
    from app.candidates.store import CandidateStore
    from tests.test_profile_sources_store import _sig
    engine, factory = database
    settings.candidate_record_max_concurrent_requests = 1
    settings.candidate_record_wait_seconds = .2 if ending in ('timeout', 'late_failure') else 20
    services = make_services(settings, candidates=CandidateStore(factory))
    services.profile_sources._store.save_signal('a', _sig('owned'))
    services.profile_sources._store.save_signal('b', _sig('other'))
    expected = [s.model_dump(mode='json') for s in services.profile_sources.list_sources('a')]
    entered, release = Event(), Event()
    state, calls, workers = local(), [], []
    caller = get_ident()
    listing = services.profile_sources.list_sources
    def observed(*args):
        calls.append(args)
        workers.append(get_ident())
        state.active, state.history = True, False
        try:
            return listing(*args)
        finally:
            state.active = False
    def sql(conn, cursor, statement, parameters, context, many):
        if not getattr(state, 'active', False):
            return
        query = statement.upper()
        target = False
        if 'FROM PROFILE_SOURCES' in query:
            state.history = True
            target = phase == 'history'
        elif 'FROM CANDIDATES' in query:
            target = phase == 'initial' or (phase == 'final' and state.history)
        if target and not entered.is_set():
            entered.set()
            assert release.wait(10)
            if ending == 'late_failure':
                raise RuntimeError('synthetic-private-source-read-error')
    def begin(session, transaction, connection):
        assert session.info.setdefault('source_read_owner', get_ident()) == get_ident()
    def end(session, transaction):
        assert session.info.get('source_read_owner', get_ident()) == get_ident()
    monkeypatch.setattr(services.profile_sources, 'list_sources', observed)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            event.listen(engine, 'before_cursor_execute', sql)
            event.listen(factory, 'after_begin', begin)
            event.listen(factory, 'after_transaction_end', end)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get('/candidates/a/sources'))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == 200
                    if ending in ('timeout', 'late_failure'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503 and response.json() == {'detail': 'candidate_record_pending'}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    for path in ('/candidates/b', '/candidates/b/sources'):
                        busy = await http.get(path)
                        assert busy.status_code == 503 and busy.json() == {'detail': 'candidate_record_capacity_exhausted'}
                        assert busy.headers['retry-after'] == '1' and 'set-cookie' not in busy.headers
                    assert len(calls) == 1
                finally:
                    release.set()
                    responses = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(8):
                        while services.candidate_records._active:
                            await asyncio.sleep(.01)
                assert workers and all(worker != caller for worker in workers) and len(calls) == 1
                if ending == 'release':
                    assert responses[0].status_code == 200
                    assert responses[0].json() == {'candidate_id': 'a', 'sources': expected}
                services.candidate_records._wait_seconds = 20
                fresh = await http.get('/candidates/a/sources')
                assert fresh.status_code == 200 and fresh.json() == {'candidate_id': 'a', 'sources': expected}
                assert len(calls) == 2 and services.github.user_calls == []
                assert [s.identifier for s in listing('b')] == ['other']
                services.candidate_records.close()
                closed = await http.get('/candidates/a/sources')
                assert closed.status_code == 503 and closed.json() == {'detail': 'candidate_record_executor_closed'}
                assert closed.headers['retry-after'] == '1' and 'set-cookie' not in closed.headers and len(calls) == 2
    finally:
        release.set()
        for target, name, listener in [(engine, 'before_cursor_execute', sql),
                (factory, 'after_begin', begin), (factory, 'after_transaction_end', end)]:
            if event.contains(target, name, listener):
                event.remove(target, name, listener)
        await services.aclose()
    assert 'synthetic-private-source-read-error' not in log_output.text


async def test_source_listing_refuses_competing_erasure_before_final_snapshot(database, settings, monkeypatch):
    import asyncio
    from threading import Event
    import httpx
    from app.candidates.store import CandidateStore
    from tests.test_profile_sources_store import _sig
    _, factory = database
    services = make_services(settings, candidates=CandidateStore(factory))
    store = services.profile_sources._store
    store.save_signal('a', _sig('erase-me'))
    store.save_signal('b', _sig('keep-me'))
    loaded, release = Event(), Event()
    read = store.signals_for_candidate
    def controlled(*args):
        result = read(*args)
        loaded.set()
        assert release.wait(10)
        return result
    monkeypatch.setattr(store, 'signals_for_candidate', controlled)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get('/candidates/a/sources'))
                try:
                    assert await asyncio.to_thread(loaded.wait, 8)
                    assert await asyncio.to_thread(CandidateStore(factory).delete_candidate, 'a')
                finally:
                    release.set()
                    response = await pending
                assert response.status_code == 404 and response.json() == {'detail': 'candidate not found'}
                assert read('a') == [] and [s.identifier for s in read('b')] == ['keep-me']
                assert services.candidates.get_candidate('b') is not None
    finally:
        release.set()
        await services.aclose()


@pytest.mark.parametrize('erase', [False, True])
async def test_source_listing_real_read_lock_retains_capacity_and_observes_erasure(database, settings, erase):
    import asyncio
    import time
    from threading import Event
    import httpx
    from sqlalchemy import event, text
    from app.candidates.store import CandidateStore
    from tests.test_profile_sources_store import _sig
    engine, factory = database
    settings.candidate_record_max_concurrent_requests = 1
    settings.candidate_record_wait_seconds = .5
    services = make_services(settings, candidates=CandidateStore(factory))
    store = services.profile_sources._store
    store.save_signal('a', _sig('owned'))
    store.save_signal('b', _sig('other'))
    entered, pids = Event(), []
    def sql(conn, cursor, statement, parameters, context, many):
        target = 'FROM CANDIDATES' if engine.dialect.name == 'sqlite' else 'FROM PROFILE_SOURCES'
        if target in statement.upper() and not entered.is_set():
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
    app = create_app(services)
    blocker = None
    try:
        async with app.router.lifespan_context(app):
            blocker = engine.connect()
            if engine.dialect.name == 'sqlite':
                blocker.exec_driver_sql('BEGIN EXCLUSIVE')
            else:
                blocker.execute(text('LOCK TABLE profile_sources IN ACCESS EXCLUSIVE MODE'))
            event.listen(engine, 'before_cursor_execute', sql)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.get('/candidates/a/sources'))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(5):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    start = time.monotonic()
                    assert (await http.get('/healthz')).status_code == 200
                    assert time.monotonic() - start < 1
                    response = await asyncio.wait_for(pending, 2)
                    assert response.status_code == 503 and response.json() == {'detail': 'candidate_record_pending'}
                    assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    busy = await http.get('/candidates/b/sources')
                    assert busy.status_code == 503 and busy.json() == {'detail': 'candidate_record_capacity_exhausted'}
                    if erase:
                        blocker.execute(text('DELETE FROM candidates WHERE id = :id'), {'id': 'a'})
                        blocker.commit()
                finally:
                    blocker.rollback()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(8):
                        while services.candidate_records._active:
                            await asyncio.sleep(.01)
                assert (services.candidates.get_candidate('a') is None) == erase
                assert [s.identifier for s in store.signals_for_candidate('a')] == ([] if erase else ['owned'])
                assert [s.identifier for s in store.signals_for_candidate('b')] == ['other']
                fresh = await http.get('/candidates/a/sources')
                assert fresh.status_code == (404 if erase else 200)
    finally:
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        if event.contains(engine, 'before_cursor_execute', sql):
            event.remove(engine, 'before_cursor_execute', sql)
        await services.aclose()


def test_source_listing_preserves_empty_history_and_admin_only_access(services):
    from tests.test_profile_sources_service import _bare_candidate
    from tests.test_profile_sources_store import _sig
    from tests.test_screening_batches_api import _key
    cid = _bare_candidate(services.candidates)
    other = _bare_candidate(services.candidates)
    services.profile_sources._store.save_signal(other, _sig('other-subject'))
    _, org_key = _key(services)
    candidate_key = services.candidates.issue_access_key(cid)
    with _client(services) as client:
        assert client.get(f'/candidates/{cid}/sources').json() == {'candidate_id': cid, 'sources': []}
        for credentials in ({}, {'X-Org-Key': org_key}, {'X-Candidate-Key': candidate_key}):
            denied = client.get(f'/candidates/{other}/sources', headers={'X-API-Key': '', **credentials})
            assert denied.status_code == 401 and 'other-subject' not in denied.text
        assert client.get(f'/candidates/{other}/sources?source_type=linkedin_export').json()['sources'] == []
        assert client.get(f'/candidates/{other}/sources').json()['sources'][0]['identifier'] == 'other-subject'


def test_source_listing_unrelated_lookup_failure_remains_500(services, monkeypatch):
    from tests.test_profile_sources_service import _bare_candidate
    cid = _bare_candidate(services.candidates)
    def broken(*args):
        raise LookupError('synthetic-private-source-lookup-error')
    with _client(services) as client:
        with monkeypatch.context() as scoped:
            scoped.setattr(services.profile_sources._store, 'signals_for_candidate', broken)
            response = client.get(f'/candidates/{cid}/sources')
        assert response.status_code == 500 and 'synthetic-private' not in response.text
        assert client.get(f'/candidates/{cid}/sources').status_code == 200


def _client(services):
    return TestClient(create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS)


def _candidate(client) -> str:
    r = client.post("/candidates", json={"resume_text":
        "Dev\nEmail: dev@example.com\nSKILLS\nPython\n", "evaluate": False})
    assert r.status_code == 200
    return r.json()["candidate_id"]


def test_post_github_source_available(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/github", json={"handle": "octocat"})
        assert r.status_code == 200
        body = r.json()
        assert body["method"] == "api"
        assert body["identifier"] == "octocat"
        assert any(s["canonical"] == "python" for s in body["skills"])

        lst = client.get(f"/candidates/{cid}/sources")
        assert lst.status_code == 200
        assert len(lst.json()["sources"]) == 1


def test_post_github_source_unavailable_is_200(settings):
    gh = FakeGitHub(user_signals={"ghost": GitHubUserRaw(login="ghost", available=False, warnings=["not found"])})
    services = make_services(settings, github=gh)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/github", json={"handle": "ghost"})
        assert r.status_code == 200
        assert r.json()["method"] == "unavailable"


def test_post_github_source_no_handle_is_400(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)  # resume has no github link
        r = client.post(f"/candidates/{cid}/sources/github", json={})
        assert r.status_code == 400


def test_post_github_source_unknown_candidate_is_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.post("/candidates/nope/sources/github", json={"handle": "octocat"})
        assert r.status_code == 404


def test_get_sources_unknown_candidate_is_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.get("/candidates/nope/sources")
        assert r.status_code == 404


def _linkedin_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Skills.csv", "Name\nPython\nLeadership\n")
        zf.writestr("Positions.csv", "Company Name,Title,Finished On\nInfosys,Python Dev,\n")
        zf.writestr("Profile.csv", "Headline,Industry\nPython Engineer,IT\n")
    return base64.b64encode(buf.getvalue()).decode()


def test_post_linkedin_source_available(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": _linkedin_b64()})
        assert r.status_code == 200
        body = r.json()
        assert body["method"] == "export"
        assert body["source_type"] == "linkedin_export"
        assert any(s["canonical"] == "python" for s in body["skills"])
        assert body["activity"]["employers"] == ["Infosys"]

        lst = client.get(f"/candidates/{cid}/sources?source_type=linkedin_export")
        assert lst.status_code == 200
        assert len(lst.json()["sources"]) == 1


def test_post_linkedin_wrong_zip_is_200_unavailable(settings, fake_github):
    services = make_services(settings, github=fake_github)
    b64 = base64.b64encode(_wrong_zip()).decode()
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": b64})
        assert r.status_code == 200
        assert r.json()["method"] == "unavailable"


def _wrong_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Ad_Targeting.csv", "Member Age\n25\n")
    return buf.getvalue()


def test_post_linkedin_bad_base64_is_422(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": "!!!not base64!!!"})
        assert r.status_code == 422


def test_post_linkedin_oversize_is_422(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        big = "A" * (services.settings.max_linkedin_b64_chars + 1)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": big})
        assert r.status_code == 422


def test_post_linkedin_unknown_candidate_is_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.post("/candidates/nope/sources/linkedin", json={"export_b64": _linkedin_b64()})
        assert r.status_code == 404
