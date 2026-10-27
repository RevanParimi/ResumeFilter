"""The auth HTTP surface over real requests (S8.2).

Cookies, CSRF, CORS and the no-enumeration rule are properties of the WIRE, not
of the service, so they are asserted here through an actual client.
"""

from __future__ import annotations

import json
import asyncio
import re
from pathlib import Path
from threading import Event
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth.models import AuthSessionRow, LoginChallengeRow
from app.main import create_app
from app.services.email import CaptureEmail
from tests.conftest import ADMIN_HEADERS, make_services
from tests.test_report_erasure_concurrency import database  # noqa: F401


def _resolver_session(services, cfg):
    email = 'resolver-owner@example.in'
    services.auth.issue_code(plane='candidate', purpose='signup', email=email, at=datetime.now(timezone.utc))
    token, csrf, principal = services.auth.verify_code(plane='candidate', email=email,
                                                      code=_code(Path(cfg.email_capture_path)))
    stale = datetime.now(timezone.utc) - timedelta(minutes=2)
    with services.session_factory() as session:
        session.execute(update(AuthSessionRow).where(AuthSessionRow.id == principal.session_id).values(last_seen_at=stale))
        session.commit()
    return token, csrf, principal, stale


@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'late_failure'])
async def test_resolver_admission_never_runs_a_refused_or_abandoned_handler(database, cfg, monkeypatch, ending):
    import httpx
    from threading import get_ident
    from sqlalchemy import event
    from app.candidates.store import CandidateStore
    engine, factory = database
    cfg.auth_resolution_max_concurrent_requests = 1
    cfg.auth_resolution_wait_seconds = .1 if ending in ('timeout', 'late_failure') else 20
    services = make_services(cfg, candidates=CandidateStore(factory))
    token, csrf, principal, stale = _resolver_session(services, cfg)
    entered, release = Event(), Event()
    caller = get_ident()
    resolver_calls, handler_calls, worker_sql = [], [], []
    resolve, grant = services.auth.resolve, services.portal.grant
    def observed(**credentials):
        resolver_calls.append(get_ident())
        return resolve(**credentials)
    def handler(*args, **kwargs):
        handler_calls.append(True)
        return grant(*args, **kwargs)
    def begin(session, transaction, connection):
        owner = session.info.setdefault('resolution_thread', get_ident())
        assert owner == get_ident(), 'SQL session crossed threads'
    def end(session, transaction):
        assert session.info.get('resolution_thread', get_ident()) == get_ident()
    def sql(conn, cursor, statement, parameters, context, many):
        if 'auth_sessions' in statement and get_ident() != caller:
            worker_sql.append(get_ident())
        if statement.lstrip().upper().startswith('UPDATE AUTH_SESSIONS') and not entered.is_set():
            entered.set()
            assert release.wait(15)
            if ending == 'late_failure':
                raise RuntimeError('private-resolver-failure-sentinel')
    monkeypatch.setattr(services.auth, 'resolve', observed)
    monkeypatch.setattr(services.portal, 'grant', handler)
    event.listen(factory, 'after_begin', begin)
    event.listen(factory, 'after_transaction_end', end)
    event.listen(engine, 'before_cursor_execute', sql)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
                headers = {'Cookie': f'{cfg.session_cookie_name}={token}; {cfg.csrf_cookie_name}={csrf}',
                           'X-CSRF-Token': csrf}
                pending = asyncio.create_task(http.post('/portal/consents', headers=headers, json={'purpose': 'ledger_read'}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == 200
                    for path, busy_headers in (
                        ('/admin/users', ADMIN_HEADERS), ('/jobs', {'X-Org-Key': 'unadmitted'}),
                        ('/portal/me', {'X-Candidate-Key': 'unadmitted'}), ('/auth/me', headers),
                    ):
                        response = await http.get(path, headers=busy_headers)
                        assert response.status_code == 503
                        assert response.json() == {'detail': 'auth_resolution_capacity_exhausted'}
                        assert response.headers['retry-after'] == '1'
                        assert 'set-cookie' not in response.headers
                    assert len(resolver_calls) == 1 and not handler_calls
                    if ending in ('timeout', 'late_failure'):
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 503
                        assert response.json() == {'detail': 'auth_resolution_pending'}
                        assert response.headers['retry-after'] == '1' and 'set-cookie' not in response.headers
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    assert not handler_calls
                    assert (await http.get('/auth/me', headers=headers)).status_code == 503
                finally:
                    release.set()
                    outcome = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(8):
                        while services.auth_resolution._active:
                            await asyncio.sleep(.01)
                assert len(resolver_calls) == 1 and len(handler_calls) == (1 if ending == 'release' else 0)
                if ending == 'release':
                    assert outcome[0].status_code == 200
                with factory() as session:
                    saved = session.get(AuthSessionRow, principal.session_id)
                    from app.auth.sessions import as_utc
                    assert (as_utc(saved.last_seen_at) > stale) == (ending != 'late_failure')
                assert (await http.get('/auth/me', headers=headers)).json()['kind'] == 'candidate'
                assert len(handler_calls) == (1 if ending == 'release' else 0), 'abandoned write replayed'
                assert resolver_calls and all(thread != caller for thread in resolver_calls)
                assert worker_sql and len(set(worker_sql)) == 1
                services.auth_resolution.close()
                response = await http.get('/portal/me', headers=headers)
                assert response.status_code == 503 and response.json() == {'detail': 'auth_resolution_executor_closed'}
    finally:
        release.set()
        if services._auth_resolution is not None:
            services._auth_resolution.close()
        event.remove(engine, 'before_cursor_execute', sql)
        event.remove(factory, 'after_begin', begin)
        event.remove(factory, 'after_transaction_end', end)


async def test_resolver_touch_waits_for_real_sql_lock_without_blocking_event_loop(database, cfg):
    import httpx
    from sqlalchemy import event, text
    from app.auth.sessions import as_utc
    from app.candidates.store import CandidateStore
    engine, factory = database
    cfg.auth_resolution_wait_seconds = .1
    services = make_services(cfg, candidates=CandidateStore(factory))
    token, csrf, principal, stale = _resolver_session(services, cfg)
    entered, pids = Event(), []
    def sql(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('UPDATE AUTH_SESSIONS'):
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
    blocker = engine.connect()
    if engine.dialect.name == 'sqlite':
        blocker.exec_driver_sql('BEGIN IMMEDIATE')
    else:
        blocker.execute(text('SELECT * FROM auth_sessions WHERE id = :id FOR UPDATE'), {'id': principal.session_id}).all()
    event.listen(engine, 'before_cursor_execute', sql)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
                pending = asyncio.create_task(http.get('/auth/me', headers={'Cookie': f'{cfg.session_cookie_name}={token}'}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(5):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    start = time.monotonic()
                    assert (await http.get('/healthz')).status_code == 200
                    assert (await http.get('/admin/users', headers=ADMIN_HEADERS)).status_code == 200
                    assert time.monotonic() - start < 1
                    response = await pending
                    assert response.status_code == 503 and response.json() == {'detail': 'auth_resolution_pending'}
                finally:
                    blocker.rollback()
                    blocker.close()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(8):
                        while services.auth_resolution._active:
                            await asyncio.sleep(.01)
                with factory() as session:
                    assert as_utc(session.get(AuthSessionRow, principal.session_id).last_seen_at) > stale
                assert services.candidates.get_candidate('b') is not None
    finally:
        blocker.close()
        services.auth_resolution.close()
        event.remove(engine, 'before_cursor_execute', sql)


@pytest.mark.parametrize('plane,path,header,via_session', [
    ('candidate', '/portal/me', 'X-Candidate-Key', True),
    ('org', '/jobs', 'X-Org-Key', True),
    ('admin', '/admin/users', 'X-API-Key', True),
    ('candidate', '/auth/me', None, True),
    ('candidate', '/portal/me', 'X-Candidate-Key', False),
    ('org', '/jobs', 'X-Org-Key', False),
])
async def test_slow_principal_sql_leaves_unrelated_requests_responsive(database, cfg, plane, path, header, via_session):
    import httpx
    from sqlalchemy import event
    from app.candidates.store import CandidateStore
    engine, factory = database
    services = make_services(cfg, candidates=CandidateStore(factory))
    if plane == 'admin':
        services.auth.create_admin_user(email_hash=services.auth.hash_email('slow-resolve@example.in'), label='Synthetic')
    services.auth.issue_code(plane=plane, purpose='signup' if plane != 'admin' else 'login',
                             email='slow-resolve@example.in', payload={'organization_name': 'Resolver Org'},
                             at=datetime.now(timezone.utc))
    token, csrf, principal = services.auth.verify_code(plane=plane, email='slow-resolve@example.in',
                                                      code=_code(Path(cfg.email_capture_path)))
    key = None
    if not via_session:
        key = (services.candidates.issue_access_key(principal.candidate_id) if plane == 'candidate' else
               services.ledger.issue_api_key(principal.org_id))
    entered, release, finished = Event(), Event(), Event()
    def sql(conn, cursor, statement, parameters, context, many):
        table = 'auth_sessions' if via_session else 'candidate_credentials' if plane == 'candidate' else 'organizations'
        if table in statement and not entered.is_set():
            entered.set()
            release.wait(3)
            finished.set()
    event.listen(engine, 'before_cursor_execute', sql)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
                headers = {'Cookie': f'{cfg.session_cookie_name}={token}'} if via_session else {}
                if header:
                    headers[header] = 'invalid-key-session-must-win' if via_session else key
                pending = asyncio.create_task(http.get(path, headers=headers))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    start = time.monotonic()
                    health = await http.get('/healthz')
                    read = await http.get('/admin/users', headers=ADMIN_HEADERS)
                    elapsed = time.monotonic() - start
                    assert health.status_code == read.status_code == 200
                    assert not finished.is_set(), f'{plane}/{path}: resolver blocked event loop ({elapsed:.4f}s)'
                    assert elapsed < 1
                finally:
                    release.set()
                    assert (await pending).status_code == 200
    finally:
        release.set()
        event.remove(engine, 'before_cursor_execute', sql)
        if getattr(services, '_auth_resolution', None) is not None:
            services._auth_resolution.close()


@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'erase'])
async def test_auth_code_admission_retains_owning_work_until_completion(database, cfg, monkeypatch, ending):
    import httpx
    from threading import get_ident
    from sqlalchemy import event, text
    from app.candidates.store import CandidateStore
    from app.candidates.models import CandidateRow
    engine, factory = database
    cfg.auth_code_max_concurrent_requests = 1
    cfg.auth_code_wait_seconds = .05 if ending == 'timeout' else 20
    services = make_services(cfg, candidates=CandidateStore(factory))
    email = 'retained-auth@example.in'
    with factory() as session:
        session.add(CandidateRow(id='auth-owner', email_hash=services.auth.hash_email(email)))
        session.commit()
    entered, release = Event(), Event()
    caller = get_ident()
    mail_threads, session_threads, calls = [], [], []
    send = services.email.send
    def mail(**kwargs):
        calls.append(kwargs['to'])
        mail_threads.append(get_ident())
        entered.set()
        assert release.wait(15)
        return send(**kwargs)
    def begin(session, transaction, connection):
        owner = session.info.setdefault('auth_owner_thread', get_ident())
        assert owner == get_ident(), 'one SQL session crossed threads'
        session_threads.append(get_ident())
    def end(session, transaction):
        assert session.info.get('auth_owner_thread', get_ident()) == get_ident()
    monkeypatch.setattr(services.email, 'send', mail)
    event.listen(factory, 'after_begin', begin)
    event.listen(factory, 'after_transaction_end', end)
    def state():
        with factory() as session:
            return {table: list(session.execute(text(f'SELECT * FROM {table} ORDER BY id')).tuples())
                    for table in ('rate_limit_counters', 'login_issuances', 'login_challenges')}
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
                pending = asyncio.create_task(http.post('/auth/candidate/signup', json={'email': email}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    before = state()
                    for path, body in (
                        ('/auth/org/signup', {'email': 'other@example.in', 'organization_name': 'Other'}),
                        ('/auth/org/login', {'email': 'unknown@example.in'}),
                        ('/auth/candidate/signup', {'email': 'new@example.in'}),
                        ('/auth/candidate/login', {'email': email}),
                        ('/auth/admin/login', {'email': 'unknown@example.in'}),
                    ):
                        response = await http.post(path, json=body)
                        assert response.status_code == 503, (path, response.text)
                        assert response.json() == {'detail': 'auth_code_capacity_exhausted'}
                        assert response.headers['retry-after'] == '1' and response.headers['x-request-id']
                    assert state() == before, 'unadmitted requests reached SQL'
                    assert calls == [email]
                    assert (await http.get('/admin/users', headers=ADMIN_HEADERS)).status_code == 200
                    if ending == 'timeout':
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 202 and response.json() == {'status': 'accepted'}
                        assert 'set-cookie' not in response.headers
                        assert not Path(cfg.email_capture_path).exists()
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    elif ending == 'erase':
                        erased = await http.delete('/candidates/auth-owner', headers=ADMIN_HEADERS)
                        assert erased.status_code == 200
                        assert services.candidates.get_candidate('b') is not None
                    assert (await http.post('/auth/admin/login', json={'email': 'unknown@example.in'})).status_code == 503
                finally:
                    release.set()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(8):
                        while services.auth_codes._active:
                            await asyncio.sleep(.01)
                code = _code(Path(cfg.email_capture_path))
                verified = await http.post('/auth/candidate/verify', json={'email': email, 'code': code})
                assert verified.status_code == (400 if ending == 'erase' else 200)
                if ending == 'erase':
                    assert verified.json() == {'detail': 'invalid_code'}
                    assert services.candidates.get_candidate('auth-owner') is None
                assert (await http.post('/auth/admin/login', json={'email': 'unknown@example.in'})).json() == {'status': 'accepted'}
                assert calls == [email], 'the original request was replayed'
        assert mail_threads and all(thread != caller for thread in mail_threads)
        assert caller in session_threads and any(thread != caller for thread in session_threads)
    finally:
        release.set()
        services.auth_codes.close()
        event.remove(factory, 'after_begin', begin)
        event.remove(factory, 'after_transaction_end', end)


async def test_auth_code_worker_waits_for_a_real_competing_sql_transaction(database, cfg):
    import httpx
    from sqlalchemy import event, text
    from app.candidates.store import CandidateStore
    engine, factory = database
    cfg.auth_code_max_concurrent_requests = 1
    cfg.auth_code_wait_seconds = .1
    cfg.login_otp_cooldown_seconds = 0
    services = make_services(cfg, candidates=CandidateStore(factory))
    entered = Event()
    pids = []
    def observing(conn, cursor, statement, parameters, context, many):
        if 'rate_limit_counters' in statement and statement.lstrip().upper().startswith(('UPDATE', 'INSERT')):
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
                assert (await http.post('/auth/candidate/login', json={'email': 'lock-auth@example.in'})).status_code == 202
                async with asyncio.timeout(8):
                    while services.auth_codes._active:
                        await asyncio.sleep(.01)
                blocker = engine.connect()
                if engine.dialect.name == 'sqlite':
                    blocker.exec_driver_sql('BEGIN IMMEDIATE')
                else:
                    blocker.execute(text('SELECT * FROM rate_limit_counters FOR UPDATE')).all()
                event.listen(engine, 'before_cursor_execute', observing)
                pending = asyncio.create_task(http.post('/auth/candidate/login', json={'email': 'lock-auth@example.in'}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(5):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    assert (await http.get('/healthz')).status_code == 200
                    assert (await http.get('/admin/users', headers=ADMIN_HEADERS)).status_code == 200
                    response = await pending
                    assert response.status_code == 202 and response.json() == {'status': 'accepted'}
                    assert (await http.post('/auth/admin/login', json={'email': 'other@example.in'})).status_code == 503
                finally:
                    blocker.rollback()
                    blocker.close()
                    event.remove(engine, 'before_cursor_execute', observing)
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(8):
                        while services.auth_codes._active:
                            await asyncio.sleep(.01)
                code = _code(Path(cfg.email_capture_path))
                assert (await http.post('/auth/candidate/verify', json={'email': 'lock-auth@example.in', 'code': code})).status_code == 200
    finally:
        services.auth_codes.close()


@pytest.mark.parametrize('gate', ['mail', 'sql'])
async def test_slow_auth_issuance_does_not_block_unrelated_requests(database, cfg, monkeypatch, gate):
    import httpx
    from sqlalchemy import event
    from app.candidates.store import CandidateStore
    engine, factory = database
    services = make_services(cfg, candidates=CandidateStore(factory))
    entered, release, finished = Event(), Event(), Event()
    send = services.email.send
    def hold():
        entered.set()
        release.wait(3)
        finished.set()
    def mail(**kwargs):
        if gate == 'mail':
            hold()
        return send(**kwargs)
    def sql(conn, cursor, statement, parameters, context, many):
        if gate == 'sql' and 'rate_limit_counters' in statement and not entered.is_set():
            hold()
    monkeypatch.setattr(services.email, 'send', mail)
    event.listen(engine, 'before_cursor_execute', sql)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
                pending = asyncio.create_task(http.post('/auth/candidate/signup', json={'email': 'slow-auth@example.in'}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    start = time.monotonic()
                    health = await http.get('/healthz')
                    read = await http.get('/admin/users', headers=ADMIN_HEADERS)
                    elapsed = time.monotonic() - start
                    assert health.status_code == read.status_code == 200
                    assert not finished.is_set(), f'unrelated requests waited for {gate} work ({elapsed:.4f}s)'
                finally:
                    release.set()
                    response = await pending
                assert response.status_code == 202 and response.json() == {'status': 'accepted'}
    finally:
        event.remove(engine, 'before_cursor_execute', sql)
        if getattr(services, '_auth_codes', None) is not None:
            services._auth_codes.close()


@pytest.fixture
def capture_path(tmp_path):
    return tmp_path / "mail.jsonl"


@pytest.fixture
def cfg(settings, capture_path):
    """Localhost-shaped: capture email, and a cookie a test client will keep.

    Secure=True cookies are dropped by any correct client over http://, so the
    smoke and these tests run the same lax/insecure combination a developer runs
    -- and prod refuses to BOOT in that configuration (app/core/boot.py).
    """
    return settings.model_copy(update={
        "email_provider": "capture",
        "email_capture_path": str(capture_path),
        "session_cookie_secure": False,
        "session_cookie_samesite": "lax",
    })


@pytest.fixture
def client(cfg, flywheel):
    services = make_services(cfg, flywheel=flywheel)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        c.app_services = services
        yield c
    if services._auth_codes is not None:
        services._auth_codes.close()
    if services._auth_resolution is not None:
        services._auth_resolution.close()


def _code(capture_path) -> str:
    line = json.loads(capture_path.read_text(encoding="utf-8").splitlines()[-1])
    return re.search(r"\b(\d{6})\b", line["body"]).group(1)


def _sent(capture_path) -> int:
    if not capture_path.exists():
        return 0
    return len(capture_path.read_text(encoding="utf-8").splitlines())


@pytest.mark.parametrize('denial', ['exhausted', 'expired'])
def test_stale_valid_code_returns_generic_failure_without_cookie(client, capture_path, monkeypatch, denial):
    email = 'stale-login@example.in'
    assert client.post('/auth/candidate/login', json={'email': email}).status_code == 202
    code = _code(capture_path)
    auth = client.app_services.auth
    original = auth._live_scopes

    def invalidate(*args):
        stale = original(*args)
        with auth._store._session_factory.begin() as session:
            for _, row in stale:
                session.execute(update(LoginChallengeRow).where(LoginChallengeRow.id == row.id).values(
                    **({'attempts': client.app_services.settings.login_otp_max_attempts}
                       if denial == 'exhausted' else {'expires_at': datetime.now(timezone.utc)})))
        return stale

    monkeypatch.setattr(auth, '_live_scopes', invalidate)
    response = client.post('/auth/candidate/verify', json={'email': email, 'code': code})
    assert response.status_code == 400
    assert response.json() == {'detail': 'invalid_code'}
    assert 'set-cookie' not in response.headers
    with auth._store._session_factory() as session:
        assert session.scalars(select(AuthSessionRow)).all() == []


def _signup_candidate(client, capture_path, email="a@b.in") -> str:
    """Returns the CSRF token; the session cookie lives on the client jar."""
    assert client.post(
        "/auth/candidate/signup", json={"email": email}
    ).status_code == 202
    r = client.post(
        "/auth/candidate/verify", json={"email": email, "code": _code(capture_path)}
    )
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


# ── no enumeration ──────────────────────────────────────────────────────────


def test_unknown_email_login_still_returns_202(client, capture_path):
    """Small, easy to skip, and the only thing standing between a stranger and
    a list of who has an account here."""
    r = client.post("/auth/candidate/login", json={"email": "nobody@nowhere.in"})
    assert r.status_code == 202


def test_the_candidate_plane_is_indistinguishable_known_vs_unknown(
    client, capture_path
):
    """Uniformity is the anti-enumeration property, and on the candidate plane
    it is total: same status, same body, same email sent, whether or not a
    record exists. (A candidates row is not an account -- see
    test_the_candidate_plane_treats_signup_and_login_as_the_same_act.)"""
    _signup_candidate(client, capture_path, "known@example.in")

    before = _sent(capture_path)
    known = client.post("/auth/candidate/login", json={"email": "known@example.in"})
    after_known = _sent(capture_path)
    unknown = client.post(
        "/auth/candidate/login", json={"email": "stranger@example.in"}
    )
    after_unknown = _sent(capture_path)

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert after_known - before == after_unknown - after_known == 1


def test_org_signup_on_a_taken_address_returns_202_and_sends_nothing(
    client, capture_path
):
    """The ORG plane keeps the distinction: an org_user IS an account."""
    client.post(
        "/auth/org/signup",
        json={"email": "ops@acme.in", "organization_name": "Acme"},
    )
    client.post(
        "/auth/org/verify",
        json={"email": "ops@acme.in", "code": _code(capture_path)},
    )
    before = _sent(capture_path)
    r = client.post(
        "/auth/org/signup",
        json={"email": "ops@acme.in", "organization_name": "Acme Again"},
    )
    assert r.status_code == 202
    assert _sent(capture_path) == before


def test_a_cooldown_is_not_observable(client, capture_path):
    """A cooldown is a refusal the SERVICE makes, and the route answers 202
    anyway. Surfacing it as a 429 would say "this scope has a live challenge",
    which is the enumeration oracle by another door."""
    client.post("/auth/candidate/signup", json={"email": "a@b.in"})
    r = client.post("/auth/candidate/signup", json={"email": "a@b.in"})
    assert r.status_code == 202
    assert _sent(capture_path) == 1      # the second send was suppressed


def test_there_is_no_admin_signup_route(client):
    assert client.post(
        "/auth/admin/signup", json={"email": "attacker@evil.in"}
    ).status_code == 404


def test_every_failure_mode_returns_the_same_400(client, capture_path):
    """Distinguishing expired from wrong from exhausted tells a brute-forcer
    which assumption was right."""
    client.post("/auth/candidate/signup", json={"email": "a@b.in"})
    wrong = client.post(
        "/auth/candidate/verify", json={"email": "a@b.in", "code": "000000"}
    )
    unknown = client.post(
        "/auth/candidate/verify", json={"email": "ghost@nowhere.in", "code": "000000"}
    )
    assert wrong.status_code == unknown.status_code == 400
    assert wrong.json()["detail"] == unknown.json()["detail"] == "invalid_code"


# ── cookies ─────────────────────────────────────────────────────────────────


def test_verify_sets_both_cookies_with_the_right_flags(client, capture_path):
    client.post("/auth/candidate/signup", json={"email": "a@b.in"})
    r = client.post(
        "/auth/candidate/verify",
        json={"email": "a@b.in", "code": _code(capture_path)},
    )
    assert r.status_code == 200
    jar = "; ".join(r.headers.get_list("set-cookie"))
    assert "dee_session=" in jar and "dee_csrf=" in jar

    session_bit = next(
        c for c in r.headers.get_list("set-cookie") if c.startswith("dee_session")
    )
    csrf_bit = next(
        c for c in r.headers.get_list("set-cookie") if c.startswith("dee_csrf")
    )
    # httpOnly on the session so XSS cannot read it; NOT on the CSRF token,
    # because the browser client must read it to echo it back. That asymmetry
    # is the double-submit scheme, not an oversight.
    assert "HttpOnly" in session_bit
    assert "HttpOnly" not in csrf_bit


def test_no_email_provider_returns_503(settings, flywheel):
    """NullEmail refuses, so signup cannot pretend to have sent anything."""
    services = make_services(settings, flywheel=flywheel)   # default NullEmail
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        r = c.post("/auth/candidate/login", json={"email": "a@b.in"})
        assert r.status_code == 503
        assert r.json()["detail"] == "email_unavailable"


# ── the session reaches the ordinary planes ─────────────────────────────────


def test_a_session_authenticates_the_portal_with_no_header_key(client, capture_path):
    """The point of the whole sprint: 63 endpoints gained session mode without
    a single handler edit."""
    _signup_candidate(client, capture_path)
    r = client.get("/portal/me")
    assert r.status_code == 200
    assert "X-Candidate-Key" not in r.request.headers


def test_auth_me_reports_the_principal(client, capture_path):
    _signup_candidate(client, capture_path)
    assert client.get("/auth/me").json()["kind"] == "candidate"


def test_logout_revokes_immediately(client, capture_path):
    csrf = _signup_candidate(client, capture_path)
    assert client.post(
        "/auth/logout", headers={"X-CSRF-Token": csrf}
    ).status_code == 200
    assert client.get("/portal/me").status_code == 401


# ── CSRF ────────────────────────────────────────────────────────────────────


def test_a_mutating_session_request_without_csrf_is_refused(client, capture_path):
    _signup_candidate(client, capture_path)
    r = client.post("/portal/consents", json={"purpose": "ledger_read"})
    assert r.status_code == 403


def test_a_mutating_session_request_with_csrf_passes(client, capture_path):
    csrf = _signup_candidate(client, capture_path)
    r = client.post(
        "/portal/consents",
        json={"purpose": "ledger_read"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code != 403


def test_a_wrong_csrf_token_is_refused(client, capture_path):
    _signup_candidate(client, capture_path)
    r = client.post(
        "/portal/consents",
        json={"purpose": "ledger_read"},
        headers={"X-CSRF-Token": "not-the-token"},
    )
    assert r.status_code == 403


def test_a_safe_method_needs_no_csrf(client, capture_path):
    _signup_candidate(client, capture_path)
    assert client.get("/portal/me").status_code == 200


def test_a_header_key_needs_no_csrf(client, capture_path, cfg, flywheel):
    """Machines carry no cookie and cannot be CSRF'd. Both modes are permanent
    (PI-8 decision 0.4), so this must keep working forever."""
    _signup_candidate(client, capture_path)
    cid = client.get("/auth/me").json()["session_id"]
    assert cid
    services = client.app_services
    candidate_id = services.auth.resolve(
        kind=__import__(
            "app.auth.schema", fromlist=["PrincipalKind"]
        ).PrincipalKind.CANDIDATE,
        session_token=client.cookies.get("dee_session"),
        header_key=None,
    ).candidate_id
    key = services.candidates.issue_access_key(candidate_id)

    with TestClient(create_app(services), raise_server_exceptions=False) as machine:
        r = machine.post(
            "/portal/consents",
            json={"purpose": "ledger_read"},
            headers={"X-Candidate-Key": key},
        )
        assert r.status_code != 403


def test_a_session_cookie_plus_a_header_key_is_still_csrf_checked(
    client, capture_path
):
    """THE TRAP (spec 4.2). If the exemption keyed on "a header was present"
    instead of "this request authenticated BY a header", an attacker-supplied
    X-Candidate-Key would turn every session request into a CSRF-exempt one.
    """
    _signup_candidate(client, capture_path)
    services = client.app_services
    other = services.candidates.create_bare_candidate(email_hash="someone-else")
    stolen = services.candidates.issue_access_key(other)

    r = client.post(
        "/portal/consents",
        json={"purpose": "ledger_read"},
        headers={"X-Candidate-Key": stolen},   # no CSRF token
    )
    assert r.status_code == 403


# ── session lifecycle ───────────────────────────────────────────────────────


def test_sessions_lists_only_your_own(client, capture_path, cfg, flywheel):
    csrf = _signup_candidate(client, capture_path, "one@example.in")
    mine = {s["id"] for s in client.get("/auth/sessions").json()}
    assert len(mine) == 1

    services = client.app_services
    with TestClient(create_app(services), raise_server_exceptions=False) as other:
        other.post("/auth/candidate/signup", json={"email": "two@example.in"})
        other.post(
            "/auth/candidate/verify",
            json={"email": "two@example.in", "code": _code(capture_path)},
        )
        theirs = {s["id"] for s in other.get("/auth/sessions").json()}

    assert mine.isdisjoint(theirs)


def test_revoking_someone_elses_session_is_an_indistinguishable_404(
    client, capture_path
):
    csrf = _signup_candidate(client, capture_path)
    r = client.post(
        "/auth/sessions/not-a-real-session/revoke", headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 404


def test_a_key_authenticated_caller_cannot_use_the_session_routes(
    client, capture_path
):
    """A key has no session to list or revoke, so these refuse rather than
    pretending to work."""
    _signup_candidate(client, capture_path)
    services = client.app_services
    other = services.candidates.create_bare_candidate(email_hash="machine")
    key = services.candidates.issue_access_key(other)
    with TestClient(create_app(services), raise_server_exceptions=False) as machine:
        assert machine.get(
            "/auth/sessions", headers={"X-Candidate-Key": key}
        ).status_code == 401


# ── operator accounts ───────────────────────────────────────────────────────


def test_admin_user_creation_requires_the_shared_key(client):
    assert client.post(
        "/admin/users", json={"email": "op@veritas.in"}
    ).status_code == 401
    r = client.post(
        "/admin/users", json={"email": "op@veritas.in"}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 200
    assert "email_hash" in r.json()


def test_operator_email_is_stored_only_as_a_hash(client):
    r = client.post(
        "/admin/users", json={"email": "op@veritas.in"}, headers=ADMIN_HEADERS
    )
    assert "op@veritas.in" not in r.text


def test_a_duplicate_operator_is_409(client):
    client.post(
        "/admin/users", json={"email": "op@veritas.in"}, headers=ADMIN_HEADERS
    )
    assert client.post(
        "/admin/users", json={"email": "op@veritas.in"}, headers=ADMIN_HEADERS
    ).status_code == 409


def test_an_operator_can_log_in_and_use_the_admin_plane(client, capture_path):
    """The attribution win: this request is a named person, not a shared secret."""
    client.post(
        "/admin/users", json={"email": "op@veritas.in"}, headers=ADMIN_HEADERS
    )
    assert client.post(
        "/auth/admin/login", json={"email": "op@veritas.in"}
    ).status_code == 202
    r = client.post(
        "/auth/admin/verify",
        json={"email": "op@veritas.in", "code": _code(capture_path)},
    )
    assert r.status_code == 200
    # No X-API-Key anywhere -- the session alone reaches the admin plane.
    assert client.get("/domains").status_code == 200


def test_deleting_an_operator_kills_their_sessions(client, capture_path):
    created = client.post(
        "/admin/users", json={"email": "op@veritas.in"}, headers=ADMIN_HEADERS
    ).json()
    client.post("/auth/admin/login", json={"email": "op@veritas.in"})
    csrf = client.post(
        "/auth/admin/verify",
        json={"email": "op@veritas.in", "code": _code(capture_path)},
    ).json()["csrf_token"]
    assert client.get("/domains").status_code == 200

    # The CSRF token is REQUIRED here even though X-API-Key is also present:
    # the client now holds a session cookie, so resolve() picks the session and
    # the stronger requirement applies. Sending only X-API-Key gets a 403, which
    # is the trap in spec 4.2 firing exactly as designed.
    assert client.delete(
        f"/admin/users/{created['id']}", headers=ADMIN_HEADERS
    ).status_code == 403

    assert client.delete(
        f"/admin/users/{created['id']}",
        headers={**ADMIN_HEADERS, "X-CSRF-Token": csrf},
    ).status_code == 200
    # Their session died with them (auth_sessions.admin_user_id CASCADE).
    assert client.get("/domains").status_code == 401


# ── CORS ────────────────────────────────────────────────────────────────────


def test_cors_is_absent_by_default(client):
    """Fail-closed: with no configured origin the middleware is not installed,
    so nothing cross-site can reach the API at all."""
    r = client.options(
        "/portal/me",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_cors_allows_a_listed_origin(cfg, flywheel):
    allowed = cfg.model_copy(
        update={"cors_allowed_origins": ["https://app.example.com"]}
    )
    services = make_services(allowed, flywheel=flywheel)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        r = c.options(
            "/portal/me",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r.headers["access-control-allow-origin"] == "https://app.example.com"
        assert r.headers["access-control-allow-credentials"] == "true"


def test_cors_rejects_an_unlisted_origin(cfg, flywheel):
    allowed = cfg.model_copy(
        update={"cors_allowed_origins": ["https://app.example.com"]}
    )
    services = make_services(allowed, flywheel=flywheel)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        r = c.options(
            "/portal/me",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r.headers.get("access-control-allow-origin") != "https://evil.example"


def test_a_broken_provider_refuses_identically_for_known_and_unknown(
    settings, flywheel, capture_path
):
    """The oracle this nearly shipped with.

    With email broken, `login` for an UNKNOWN address short-circuited before
    attempting a send and answered 202, while a KNOWN address reached the send
    and answered 503. That difference is account enumeration, and it appears
    only when email is misconfigured -- i.e. exactly when nobody is watching.
    The provider is now probed BEFORE any account lookup.
    """
    services = make_services(settings, flywheel=flywheel)   # NullEmail
    known = services.candidates.create_bare_candidate(
        email_hash=services.auth.hash_email("known@example.in")
    )
    assert known
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        a = c.post("/auth/candidate/login", json={"email": "known@example.in"})
        b = c.post("/auth/candidate/login", json={"email": "ghost@example.in"})
        assert a.status_code == b.status_code == 503
        assert a.json() == b.json()
