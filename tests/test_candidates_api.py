"""Candidates api regressions, grouped by behavior."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from app.candidates.store import CandidateStore
from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services
from tests.test_report_erasure_concurrency import database  # noqa: F401


# Candidates api

RESUME = """Asha Rao
Email: asha.rao@example.com | Phone: +91 98765 43210

EXPERIENCE
- Senior ML Engineer, Acme AI (2021 - Present)
- Fine-tuned transformer models and built production RAG pipelines.

SKILLS
Python, PyTorch, LangChain
"""


@pytest.mark.parametrize('suffix,method', [('', 'GET'), ('/resumes', 'GET'), ('/reports', 'GET'), ('/auth-key', 'POST')])
async def test_operator_candidate_sql_leaves_unrelated_requests_responsive(database, settings, suffix, method):
    import asyncio
    import time
    from threading import Event
    import httpx
    from sqlalchemy import event
    engine, factory = database
    services = make_services(settings, candidates=CandidateStore(factory))
    entered, release, finished = Event(), Event(), Event()
    def sql(conn, cursor, statement, parameters, context, many):
        if 'candidates' in statement and not entered.is_set():
            entered.set()
            release.wait(3)
            finished.set()
    event.listen(engine, 'before_cursor_execute', sql)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.request(method, '/candidates/a' + suffix))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    start = time.monotonic()
                    assert (await http.get('/healthz')).status_code == 200
                    assert (await http.get('/admin/users')).status_code == 200
                    assert not finished.is_set(), 'candidate handler blocked the event loop'
                    assert time.monotonic() - start < 1
                finally:
                    release.set()
                    assert (await pending).status_code == 200
    finally:
        release.set()
        event.remove(engine, 'before_cursor_execute', sql)
        for executor in (services._auth_resolution, getattr(services, '_candidate_records', None)):
            if executor is not None:
                executor.close()


@pytest.fixture
def api(settings, flywheel):
    """TestClient wired to fully offline services (NullLLM, in-memory stores)."""
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False, headers=ADMIN_HEADERS) as client:
        yield client, services
    if services._candidate_records is not None:
        services._candidate_records.close()


@pytest.mark.parametrize('suffix,method', [('', 'GET'), ('/resumes', 'GET'), ('/reports', 'GET'), ('/auth-key', 'POST')])
@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'late_failure', 'erase'])
async def test_candidate_record_admission_retains_work_without_partial_reads_or_secret_keys(database, settings, monkeypatch, suffix, method, ending):
    import asyncio
    from threading import Event, get_ident
    import httpx
    from sqlalchemy import event, select
    from app.api import candidates as routes
    from app.candidates.models import CandidateCredentialRow
    engine, factory = database
    settings.candidate_record_max_concurrent_requests = 1
    settings.candidate_record_wait_seconds = .1 if ending in ('timeout', 'late_failure') else 20
    services = make_services(settings, candidates=CandidateStore(factory))
    old = services.candidates.issue_access_key('a')
    survivor = services.candidates.issue_access_key('b')
    from app.auth.schema import PrincipalKind
    admin = services.auth._store.create_admin_user(email_hash='candidate-record-admin')
    admin_token, _ = services.auth._store.create_session(kind=PrincipalKind.ADMIN,
        subject_id=admin.id, csrf_token='synthetic-csrf', at=datetime.now(timezone.utc))
    entered, release = Event(), Event()
    calls, workers, caller = [], [], get_ident()
    for name in ('_candidate_snapshot', '_candidate_key'):
        actual = getattr(routes, name)
        def observed(*args, _actual=actual, **kwargs):
            calls.append(get_ident())
            return _actual(*args, **kwargs)
        monkeypatch.setattr(routes, name, observed)
    def before(conn, cursor, statement, parameters, context, many):
        target = (statement.lstrip().upper().startswith('UPDATE CANDIDATE_CREDENTIALS')
                  if method == 'POST' and ending != 'erase' else 'candidates' in statement)
        if target and not entered.is_set():
            workers.append(get_ident())
            context.record_test_held = True
            entered.set()
            assert release.wait(15)
    def after(conn, cursor, statement, parameters, context, many):
        if getattr(context, 'record_test_held', False) and ending == 'late_failure':
            raise RuntimeError('private-candidate-record-sentinel')
    def begin(session, transaction, connection):
        assert session.info.setdefault('candidate_record_owner', get_ident()) == get_ident()
    def end(session, transaction):
        assert session.info.get('candidate_record_owner', get_ident()) == get_ident()
    event.listen(engine, 'before_cursor_execute', before)
    event.listen(engine, 'after_cursor_execute', after)
    event.listen(factory, 'after_begin', begin)
    event.listen(factory, 'after_transaction_end', end)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.request(method, '/candidates/a' + suffix))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    assert (await http.get('/candidates/a', headers={'X-API-Key': ''})).status_code == 401
                    assert (await http.post('/candidates/a/auth-key', headers={
                        'Cookie': f'dee_session={admin_token}; dee_csrf=synthetic-csrf'})).status_code == 403
                    for other, verb in [('', 'GET'), ('/resumes', 'GET'), ('/reports', 'GET'), ('/auth-key', 'POST')]:
                        busy = await http.request(verb, '/candidates/a' + other)
                        assert busy.status_code == 503 and busy.json() == {'detail': 'candidate_record_capacity_exhausted'}
                        assert busy.headers['retry-after'] == '1' and 'set-cookie' not in busy.headers
                    assert len(calls) == 1
                    if ending in ('timeout', 'late_failure'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503 and response.json() == {'detail': 'candidate_record_pending'}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    elif ending == 'erase':
                        assert await asyncio.to_thread(services.candidates.delete_candidate, 'a')
                finally:
                    release.set()
                    outcome = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(8):
                        while services.candidate_records._active:
                            await asyncio.sleep(.01)
                assert len(calls) == 1 and workers == calls and calls[0] != caller
                if ending == 'erase':
                    assert outcome[0].status_code == 404 and outcome[0].json() == {'detail': 'candidate not found'}
                    with factory() as session:
                        assert session.scalar(select(CandidateCredentialRow).where(CandidateCredentialRow.candidate_id == 'a')) is None
                elif method == 'POST':
                    assert services.candidates.authenticate_candidate(old) == ('a' if ending == 'late_failure' else None)
                    if ending == 'release':
                        assert outcome[0].status_code == 200
                        assert services.candidates.authenticate_candidate(outcome[0].json()['access_key']) == 'a'
                    else:
                        # Deliberate recovery after uncertainty, never automatic
                        # replay of the original operation or hidden-key return.
                        services.candidate_records._wait_seconds = 20
                        recovered = await http.post('/candidates/a/auth-key')
                        assert recovered.status_code == 200
                        assert services.candidates.authenticate_candidate(recovered.json()['access_key']) == 'a'
                else:
                    assert services.candidates.authenticate_candidate(old) == 'a'
                    if ending == 'release':
                        assert outcome[0].status_code == 200
                assert services.candidates.authenticate_candidate(survivor) == 'b'
                services.candidate_records.close()
                closed = await http.get('/candidates/a')
                assert closed.status_code == 503 and closed.json() == {'detail': 'candidate_record_executor_closed'}
    finally:
        release.set()
        for executor in (services._auth_resolution, services._candidate_records):
            if executor is not None:
                executor.close()
        event.remove(engine, 'before_cursor_execute', before)
        event.remove(engine, 'after_cursor_execute', after)
        event.remove(factory, 'after_begin', begin)
        event.remove(factory, 'after_transaction_end', end)


async def test_candidate_key_real_lock_retains_capacity_and_rotates_after_timeout(database, settings):
    import asyncio
    import time
    from threading import Event
    import httpx
    from sqlalchemy import event, text
    engine, factory = database
    settings.candidate_record_max_concurrent_requests = 1
    settings.candidate_record_wait_seconds = .1
    services = make_services(settings, candidates=CandidateStore(factory))
    old = services.candidates.issue_access_key('a')
    entered, pids = Event(), []
    def sql(conn, cursor, statement, parameters, context, many):
        target = ('UPDATE CANDIDATES' in statement.upper() if engine.dialect.name == 'sqlite' else 'FOR UPDATE' in statement.upper())
        if target and not entered.is_set():
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
    blocker = engine.connect()
    if engine.dialect.name == 'sqlite':
        blocker.exec_driver_sql('BEGIN IMMEDIATE')
    else:
        blocker.execute(text("SELECT id FROM candidates WHERE id = 'a' FOR UPDATE")).all()
    event.listen(engine, 'before_cursor_execute', sql)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=ADMIN_HEADERS) as http:
                pending = asyncio.create_task(http.post('/candidates/a/auth-key'))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(5):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    start = time.monotonic()
                    assert (await http.get('/healthz')).status_code == (await http.get('/admin/users')).status_code == 200
                    assert time.monotonic() - start < 1
                    response = await pending
                    assert response.status_code == 503 and response.json() == {'detail': 'candidate_record_pending'}
                    assert (await http.get('/candidates/b')).json() == {'detail': 'candidate_record_capacity_exhausted'}
                    assert services.candidates.authenticate_candidate(old) == 'a'
                finally:
                    blocker.rollback()
                    blocker.close()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(8):
                        while services.candidate_records._active:
                            await asyncio.sleep(.01)
                assert services.candidates.authenticate_candidate(old) is None
    finally:
        blocker.close()
        for executor in (services._auth_resolution, services._candidate_records):
            if executor is not None:
                executor.close()
        event.remove(engine, 'before_cursor_execute', sql)


@pytest.mark.parametrize('suffix,method,owner_name,method_name', [
    ('', 'GET', 'candidates', 'latest_profile'),
    ('/resumes', 'GET', 'candidates', 'list_resumes'),
    ('/reports', 'GET', 'report_store', 'for_candidate'),
    ('/auth-key', 'POST', 'candidates', 'issue_access_key'),
])
def test_operator_candidate_result_refuses_observed_erasure(api, monkeypatch, suffix, method, owner_name, method_name):
    client, services = api
    cid = services.candidates.create_bare_candidate(email_hash='erasure-target')
    survivor = services.candidates.create_bare_candidate(email_hash='erasure-survivor')
    owner = getattr(services, owner_name)
    actual = getattr(owner, method_name)
    def erase_after_load(*args, **kwargs):
        result = actual(*args, **kwargs)
        assert services.candidates.delete_candidate(cid)
        return result
    monkeypatch.setattr(owner, method_name, erase_after_load)
    response = client.request(method, f'/candidates/{cid}' + suffix)
    assert response.status_code == 404
    assert response.json() == {'detail': 'candidate not found'}
    assert services.candidates.get_candidate(survivor) is not None


def test_services_bundle_has_working_candidate_store(services):
    assert isinstance(services.candidates, CandidateStore)
    # Live schema behind it (create_all in the test fake), not a stub.
    assert services.candidates.get_candidate("no-such-id") is None


def test_create_candidate_ingests_and_links_report(api):
    client, services = api
    resp = client.post("/candidates", json={"resume_text": RESUME})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["candidate_id"] and body["resume_id"]
    assert body["resume_version"] == 1
    assert body["matched_existing"] is False
    assert body["extraction_method"] == "heuristic"  # NullLLM abstains offline
    # Auto depth-eval ran, stayed advisory, and is linked to the candidate.
    assert body["report"] is not None
    assert body["report"]["candidate_id"] == body["candidate_id"]
    assert body["report"]["advisory"] is True
    assert body["report"]["human_review_required"] is True
    # Persisted through BOTH stores, not just echoed on the wire.
    assert services.candidates.get_candidate(body["candidate_id"]) is not None
    stored = services.report_store.get(body["report"]["id"])
    assert stored is not None and stored.candidate_id == body["candidate_id"]


def test_linked_report_retrievable_via_report_endpoint(api):
    client, _ = api
    body = client.post("/candidates", json={"resume_text": RESUME}).json()
    got = client.get(f"/report/{body['report']['id']}")
    assert got.status_code == 200
    assert got.json()["candidate_id"] == body["candidate_id"]


def test_same_text_is_duplicate_resume_same_candidate(api):
    client, _ = api
    first = client.post("/candidates", json={"resume_text": RESUME}).json()
    again = client.post("/candidates", json={"resume_text": RESUME}).json()
    assert again["candidate_id"] == first["candidate_id"]
    assert again["duplicate_resume"] is True
    assert again["resume_version"] == 1


def test_updated_text_matches_identity_as_new_version(api):
    client, _ = api
    first = client.post("/candidates", json={"resume_text": RESUME}).json()
    second = client.post(
        "/candidates", json={"resume_text": RESUME + "\n- AWS certified (2026)."}
    ).json()
    assert second["candidate_id"] == first["candidate_id"]
    assert second["matched_existing"] is True
    assert second["matched_on"] == "email_hash"
    assert second["resume_version"] == 2


def test_evaluate_false_skips_depth_eval(api):
    client, services = api
    body = client.post(
        "/candidates", json={"resume_text": RESUME, "evaluate": False}
    ).json()
    assert body["report"] is None
    assert services.report_store.for_candidate(body["candidate_id"]) == []
    # Ingestion still happened.
    assert services.candidates.get_candidate(body["candidate_id"]) is not None


def test_candidates_oversize_resume_422(api):
    client, services = api
    too_big = "x" * (services.settings.max_resume_chars + 1)
    resp = client.post("/candidates", json={"resume_text": too_big})
    assert resp.status_code == 422
    assert "max_resume_chars" in resp.text


def test_candidates_unknown_domain_422(api):
    client, _ = api
    resp = client.post(
        "/candidates", json={"resume_text": RESUME, "domain": "astrology"}
    )
    assert resp.status_code == 422
    assert "genai" in resp.text


def test_candidates_requires_a_source_422(api):
    client, _ = api
    assert client.post("/candidates", json={}).status_code == 422


def test_candidate_detail_includes_latest_profile(api):
    client, _ = api
    cid = client.post(
        "/candidates", json={"resume_text": RESUME, "evaluate": False}
    ).json()["candidate_id"]
    resp = client.get(f"/candidates/{cid}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == cid
    assert detail["resume_count"] == 1
    assert detail["email_hash"]
    assert detail["latest_profile"] is not None
    assert detail["latest_profile"]["contact"]["email_hash"] == detail["email_hash"]


def test_candidate_detail_404(api):
    client, _ = api
    assert client.get("/candidates/no-such-id").status_code == 404


def test_list_candidate_resumes(api):
    client, _ = api
    cid = client.post(
        "/candidates", json={"resume_text": RESUME, "evaluate": False}
    ).json()["candidate_id"]
    client.post(
        "/candidates",
        json={"resume_text": RESUME + "\n- New project shipped.", "evaluate": False},
    )
    resp = client.get(f"/candidates/{cid}/resumes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidate_id"] == cid
    assert [r["version"] for r in body["resumes"]] == [1, 2]
    assert client.get("/candidates/no-such-id/resumes").status_code == 404


def test_list_candidate_reports(api):
    client, _ = api
    first = client.post("/candidates", json={"resume_text": RESUME}).json()
    cid = first["candidate_id"]
    resp = client.get(f"/candidates/{cid}/reports")
    assert resp.status_code == 200
    reports = resp.json()
    assert len(reports) == 1
    assert reports[0]["id"] == first["report"]["id"]
    assert reports[0]["candidate_id"] == cid
    assert client.get("/candidates/no-such-id/reports").status_code == 404


RESUME_B = """Ravi Kumar
Email: ravi.kumar@example.com

SKILLS
Java, Spring
"""


def test_delete_candidate_erases_store_and_reports(api):
    client, services = api
    body = client.post("/candidates", json={"resume_text": RESUME}).json()
    cid, report_id = body["candidate_id"], body["report"]["id"]

    resp = client.delete(f"/candidates/{cid}")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["deleted"] is True
    assert payload["reports_deleted"] == 1
    # Everything derived from the resume is gone (DPDP erasure).
    assert client.get(f"/candidates/{cid}").status_code == 404
    assert client.get(f"/report/{report_id}").status_code == 404
    assert services.candidates.get_candidate(cid) is None


def test_delete_missing_candidate_404(api):
    client, _ = api
    assert client.delete("/candidates/no-such-id").status_code == 404


def test_delete_one_resume_keeps_candidate(api):
    client, _ = api
    client.post("/candidates", json={"resume_text": RESUME, "evaluate": False})
    second = client.post(
        "/candidates",
        json={"resume_text": RESUME + "\n- Extra line.", "evaluate": False},
    ).json()
    cid = second["candidate_id"]

    resp = client.delete(f"/candidates/{cid}/resumes/{second['resume_id']}")
    assert resp.status_code == 200 and resp.json()["deleted"] is True
    versions = [
        r["version"] for r in client.get(f"/candidates/{cid}/resumes").json()["resumes"]
    ]
    assert versions == [1]
    assert client.get(f"/candidates/{cid}").status_code == 200


def test_delete_resume_of_another_candidate_404(api):
    client, _ = api
    a = client.post("/candidates", json={"resume_text": RESUME, "evaluate": False}).json()
    b = client.post("/candidates", json={"resume_text": RESUME_B, "evaluate": False}).json()
    assert a["candidate_id"] != b["candidate_id"]  # distinct contacts ⇒ distinct people
    # A's resume under B's candidate id must not delete anything.
    resp = client.delete(f"/candidates/{b['candidate_id']}/resumes/{a['resume_id']}")
    assert resp.status_code == 404
    assert client.get(f"/candidates/{a['candidate_id']}/resumes").json()["resumes"] != []


def test_report_not_persisted_if_candidate_erased_during_eval(api):
    """DPDP: a depth-eval racing a candidate erasure must not leave a report."""
    client, services = api
    cid = client.post(
        "/candidates", json={"resume_text": RESUME, "evaluate": False}
    ).json()["candidate_id"]

    real_engine = client.app.state.engine

    class EraseMidEval:
        async def evaluate(self, **kwargs):
            report = await real_engine.evaluate(**kwargs)
            services.candidates.delete_candidate(cid)  # erasure lands mid-flight
            return report

    client.app.state.engine = EraseMidEval()
    response = client.post("/candidates", json={"resume_text": RESUME})
    assert response.status_code == 422
    assert response.json() == {"detail": "candidate_erased"}
    assert services.report_store.for_candidate(cid) == []


# Candidate auth api

@pytest.fixture
def _client(settings):
    # NOTE: this repo's installed Starlette/FastAPI only runs the app's
    # lifespan (which sets app.state.services) when the TestClient is used as
    # a context manager (see every other tests/test_*_api.py `with _client(...)
    # as client:` fixture). We keep the brief's tuple-return shape but do the
    # entering via a pytest fixture wrapping a `with` block, so every route in
    # this file — including the ones Task 9 still owes — resolves
    # `_services(request)` correctly, AND the lifespan shutdown (closing the
    # background portal thread) runs on fixture teardown even if the test
    # body raises.
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS) as client:
        yield client, services
    if services._candidate_records is not None:
        services._candidate_records.close()


def _make_candidate(client) -> str:
    r = client.post("/candidates", json={"resume_text": "Dev\nEmail: d@e.com\nSKILLS\nPython\n",
                                         "evaluate": False})
    assert r.status_code == 200
    return r.json()["candidate_id"]


def test_admin_mints_candidate_key_and_it_authenticates(_client):
    client, _ = _client
    cid = _make_candidate(client)
    r = client.post(f"/candidates/{cid}/auth-key")
    assert r.status_code == 200
    key = r.json()["access_key"]
    assert r.json()["candidate_id"] == cid and key
    # the key authenticates on a portal route
    ok = client.get("/portal/me", headers={"X-Candidate-Key": key})
    assert ok.status_code == 200


def test_mint_unknown_candidate_404(_client):
    client, _ = _client
    r = client.post("/candidates/nope/auth-key")
    assert r.status_code == 404


def test_portal_route_without_key_is_401(_client):
    client, _ = _client
    assert client.get("/portal/me").status_code == 401
    assert client.get("/portal/me", headers={"X-Candidate-Key": "bad"}).status_code == 401
