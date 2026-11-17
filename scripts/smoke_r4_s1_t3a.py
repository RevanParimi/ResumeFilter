"""API extraction composition: migrated HTTP, ownership and graceful restart.

Uses captured mail and the existing fake-provider SQL app/graceful server loop.
No external mail/provider calls, working storage or existing demo restart.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, asynccontextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from threading import get_ident, local

from _smoke import Smoke, base_env, client, wait_healthy
from smoke_s82 import _code_for as latest_code
from smoke_r4_s1_t1a import serve
from smoke_r4_s1_t1a import create_smoke_app as sql_app
from smoke_r1_s1_t3a_v1 import database


ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-router-admin"


def create_auth_code_smoke_app():
    """Actual SQL composition with controlled captured mail / SQL waits."""
    from sqlalchemy import event
    from app.services.email import EmailSendFailed
    app = sql_app()
    original = app.router.lifespan_context
    scratch = Path(os.environ['VERITAS_SQL_SMOKE_EVENTS']).parent
    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            services = app.state.services
            send, issue = services.email.send, services.auth.issue_code
            resolver_state = local()
            resolve, resolve_any = services.auth.resolve, services.auth.resolve_any
            def resolution_mode():
                path = scratch / 'resolve-mode'
                return path.read_text() if path.exists() else ''
            def observed_resolution(function, **credentials):
                resolver_state.held = False
                try:
                    return function(**credentials)
                finally:
                    if getattr(resolver_state, 'held', False):
                        with (scratch / 'resolve-completed').open('a') as log:
                            log.write('completed\n')
            services.auth.resolve = lambda **credentials: observed_resolution(resolve, **credentials)
            services.auth.resolve_any = lambda **credentials: observed_resolution(resolve_any, **credentials)
            verify = services.auth.verify_code
            redemption_state = local()
            def observed_verify(**credentials):
                redemption_state.active, redemption_state.held = True, False
                try:
                    return verify(**credentials)
                finally:
                    redemption_state.active = False
                    if redemption_state.held:
                        (scratch / 'redeem-completed').touch()
            services.auth.verify_code = observed_verify
            session_state = local()
            for operation in ('logout', 'sessions_for', 'revoke_session'):
                function = getattr(services.auth, operation)
                def observed_session(*args, _operation=operation, _function=function, **kwargs):
                    session_state.operation, session_state.held = _operation, False
                    try:
                        return _function(*args, **kwargs)
                    finally:
                        session_state.operation = None
                        if session_state.held:
                            (scratch / 'session-completed').touch()
                setattr(services.auth, operation, observed_session)
            def mode():
                path = scratch / 'auth-mode'
                return path.read_text() if path.exists() else ''
            def hold():
                (scratch / 'auth-entered').touch()
                deadline = time.monotonic() + 20
                while not (scratch / 'auth-release').exists():
                    assert time.monotonic() < deadline, 'synthetic auth gate timed out'
                    time.sleep(.01)
            def mail(**kwargs):
                if mode() == 'mail':
                    hold()
                if mode() == 'fail':
                    raise EmailSendFailed('private-auth-smoke-sentinel')
                return send(**kwargs)
            def observed_issue(**kwargs):
                try:
                    return issue(**kwargs)
                finally:
                    if mode():
                        (scratch / 'auth-completed').touch()
            def sql(conn, cursor, statement, parameters, context, many):
                session_mode = scratch / 'session-mode'
                if (session_mode.exists() and getattr(session_state, 'operation', None) == session_mode.read_text()
                        and not session_state.held and 'auth_sessions' in statement):
                    session_state.held = True
                    (scratch / 'session-entered').touch()
                    deadline = time.monotonic() + 20
                    while not (scratch / 'session-release').exists():
                        assert time.monotonic() < deadline, 'synthetic session SQL gate timed out'
                        time.sleep(.01)
                redeem_mode = scratch / 'redeem-mode'
                if redeem_mode.exists() and getattr(redemption_state, 'active', False) and not redemption_state.held:
                    gate = redeem_mode.read_text()
                    target = ('login_challenges' in statement if gate == 'sql' else
                              statement.lstrip().startswith('INSERT INTO auth_sessions'))
                    if target:
                        redemption_state.held = True
                        (scratch / 'redeem-entered').touch()
                        deadline = time.monotonic() + 20
                        while not (scratch / 'redeem-release').exists():
                            assert time.monotonic() < deadline, 'synthetic redemption SQL gate timed out'
                            time.sleep(.01)
                if mode() == 'sql' and 'rate_limit_counters' in statement and not (scratch / 'auth-entered').exists():
                    hold()
                gate = resolution_mode()
                target = ('auth_sessions' in statement if gate == 'sql' else
                          statement.lstrip().upper().startswith('UPDATE AUTH_SESSIONS') if gate == 'touch' else False)
                if target and not getattr(resolver_state, 'held', False):
                    resolver_state.held = True
                    with (scratch / 'resolve-entered').open('a') as log:
                        log.write('entered\n')
                    deadline = time.monotonic() + 20
                    while not (scratch / 'resolve-release').exists():
                        assert time.monotonic() < deadline, 'synthetic resolver SQL gate timed out'
                        time.sleep(.01)
            def owner(session, transaction, connection):
                previous = session.info.setdefault('auth_smoke_thread', get_ident())
                assert previous == get_ident(), 'SQL session crossed threads'
                with (scratch / 'auth-thread-ownership.jsonl').open('a') as log:
                    log.write(json.dumps({'owner': previous, 'current': get_ident()}) + '\n')
            services.email.send, services.auth.issue_code = mail, observed_issue
            engine = services.session_factory.kw['bind']
            event.listen(engine, 'before_cursor_execute', sql)
            event.listen(services.session_factory, 'after_begin', owner)
            try:
                yield
            finally:
                event.remove(engine, 'before_cursor_execute', sql)
                event.remove(services.session_factory, 'after_begin', owner)
    app.router.lifespan_context = lifespan
    return app


def check_auth_session_workers(checks, scratch, base, control, mailbox, login):
    saved = []
    for plane in ('candidate', 'org', 'admin'):
        for operation in ('sessions_for', 'revoke_session', 'logout'):
            email = f'session-{plane}-{operation}@example.in'
            if plane == 'admin':
                assert control.post('/admin/users', json={'email': email}).status_code == 200
            with client(base) as actor, client(base) as sibling:
                csrf = login(actor, plane, email, organization=f'Session {operation}' if plane == 'org' else None)
                other_csrf = login(sibling, plane, email)
                actor.headers['X-CSRF-Token'] = csrf
                sibling.headers['X-CSRF-Token'] = other_csrf
                target = sibling.get('/auth/me').json()['session_id']
                path = {'sessions_for': '/auth/sessions', 'revoke_session': f'/auth/sessions/{target}/revoke', 'logout': '/auth/logout'}[operation]
                for name in ('session-entered', 'session-completed', 'session-release'):
                    (scratch / name).unlink(missing_ok=True)
                before_cookie, before_mail = dict(actor.cookies), mailbox.read_text()
                (scratch / 'session-mode').write_text(operation)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    held = pool.submit(actor.request, 'GET' if operation == 'sessions_for' else 'POST', path)
                    try:
                        deadline = time.monotonic() + 8
                        while not (scratch / 'session-entered').exists():
                            assert time.monotonic() < deadline
                            time.sleep(.01)
                        start = time.monotonic()
                        health, read = control.get('/healthz'), control.get('/admin/users')
                        elapsed = time.monotonic() - start
                        checks.check(f'{plane}/{operation}: health and unrelated SQL read stay responsive',
                            health.status_code == read.status_code == 200 and elapsed < 1, f'{elapsed:.4f}s')
                        for method, busy_path in [('GET', '/auth/sessions'), ('POST', '/auth/logout'), ('POST', f'/auth/sessions/{target}/revoke')]:
                            busy = actor.request(method, busy_path)
                            checks.check(f'{plane}/{operation}: shared capacity refuses {busy_path} before cookie success',
                                busy.status_code == 503 and busy.json() == {'detail': 'auth_session_capacity_exhausted'}
                                and busy.headers.get('retry-after') == '1' and 'set-cookie' not in busy.headers)
                        pending = held.result(timeout=8)
                        checks.check(f'{plane}/{operation}: uncertain caller keeps cookies without false success',
                            pending.status_code == 503 and pending.json() == {'detail': 'auth_session_pending'}
                            and pending.headers.get('retry-after') == '1' and 'set-cookie' not in pending.headers
                            and dict(actor.cookies) == before_cookie)
                    finally:
                        (scratch / 'session-release').touch()
                        deadline = time.monotonic() + 8
                        while not (scratch / 'session-completed').exists():
                            assert time.monotonic() < deadline
                            time.sleep(.01)
                        (scratch / 'session-mode').unlink(missing_ok=True)
                current = sibling if operation == 'logout' else actor
                rows = current.get('/auth/sessions')
                checks.check(f'{plane}/{operation}: manual saved-state check sees late result without mail or replay',
                    rows.status_code == 200 and len(rows.json()) == (2 if operation == 'sessions_for' else 1)
                    and mailbox.read_text() == before_mail
                    and (actor.get('/auth/me').status_code == (401 if operation == 'logout' else 200))
                    and (sibling.get('/auth/me').status_code == (401 if operation == 'revoke_session' else 200)))
                saved.append((dict(current.cookies), current.get('/auth/me').json()))
    return saved


def check_auth_redemption_workers(checks, scratch, base, control, mailbox):
    sessions = []
    for plane in ('candidate', 'org', 'admin'):
        for gate in ('sql', 'commit'):
            email = f'redeem-{plane}-{gate}@example.in'
            if plane == 'admin':
                assert control.post('/admin/users', json={'email': email, 'label': 'Synthetic'}).status_code == 200
            with client(base) as actor:
                body = {'email': email}
                if plane == 'org':
                    body['organization_name'] = f'Synthetic redeem {gate}'
                purpose = 'login' if plane == 'admin' else 'signup'
                assert actor.post(f'/auth/{plane}/{purpose}', json=body).status_code == 202
                code = latest_code(mailbox, email)
                for name in ('redeem-entered', 'redeem-release', 'redeem-completed'):
                    (scratch / name).unlink(missing_ok=True)
                (scratch / 'redeem-mode').write_text(gate)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    held = pool.submit(actor.post, f'/auth/{plane}/verify', json={'email': email, 'code': code})
                    try:
                        deadline = time.monotonic() + 8
                        while not (scratch / 'redeem-entered').exists():
                            assert time.monotonic() < deadline
                            time.sleep(.01)
                        start = time.monotonic()
                        health = control.get('/healthz')
                        read = control.get('/admin/users')
                        elapsed = time.monotonic() - start
                        checks.check(f'{plane}/{gate}: health and unrelated admitted SQL read remain responsive',
                            health.status_code == read.status_code == 200 and elapsed < 1, f'{elapsed:.4f}s')
                        for other in ('candidate', 'org', 'admin'):
                            busy = control.post(f'/auth/{other}/verify', json={'email': 'unknown@example.in', 'code': '000000'})
                            checks.check(f'{plane}/{gate}: shared redemption admission refuses {other} without cookies',
                                busy.status_code == 503 and busy.json() == {'detail': 'auth_redemption_capacity_exhausted'}
                                and busy.headers.get('retry-after') == '1' and 'set-cookie' not in busy.headers)
                        pending = held.result(timeout=8)
                        checks.check(f'{plane}/{gate}: caller timeout is uncertain without false cookie success',
                            pending.status_code == 503 and pending.json() == {'detail': 'auth_redemption_pending'}
                            and pending.headers.get('retry-after') == '1' and 'set-cookie' not in pending.headers
                            and not actor.cookies and actor.get('/auth/me').status_code == 401)
                    finally:
                        (scratch / 'redeem-release').touch()
                        deadline = time.monotonic() + 8
                        while not (scratch / 'redeem-completed').exists():
                            assert time.monotonic() < deadline
                            time.sleep(.01)
                        (scratch / 'redeem-mode').unlink(missing_ok=True)
                refused = actor.post(f'/auth/{plane}/verify', json={'email': email, 'code': code})
                checks.check(f'{plane}/{gate}: late commit consumes the original code without browser session',
                    refused.status_code == 400 and refused.json() == {'detail': 'invalid_code'}
                    and 'set-cookie' not in refused.headers and not actor.cookies)
                assert actor.post(f'/auth/{plane}/login', json={'email': email}).status_code == 202
                recovered = actor.post(f'/auth/{plane}/verify', json={'email': email, 'code': latest_code(mailbox, email)})
                saved = actor.get('/auth/sessions').json()
                checks.check(f'{plane}/{gate}: deliberate fresh code recovers and observes both committed sessions',
                    recovered.status_code == 200 and len(recovered.headers.get_list('set-cookie')) == 2 and len(saved) == 2)
                sessions.append((dict(actor.cookies), actor.get('/auth/me').json()))
    return sessions


def check_auth_code_workers(checks, scratch, base, control, mailbox):
    saved = []
    def wait(path):
        deadline = time.monotonic() + 10
        while not path.exists():
            assert time.monotonic() < deadline, 'controlled auth operation did not reach checkpoint'
            time.sleep(.01)
    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()
    def ready(http):
        deadline = time.monotonic() + 8
        while True:
            response = http.post('/auth/admin/login', json={'email': 'unknown-ready@example.in'})
            if response.status_code == 202:
                return
            assert response.status_code == 503 and time.monotonic() < deadline
            time.sleep(.01)
    require(control.post('/admin/users', json={'email': 'bounded-admin@example.in', 'label': 'Synthetic bounded admin'}))
    for gate, plane, purpose, email in (
        ('mail', 'admin', 'login', 'bounded-admin@example.in'),
        ('sql', 'candidate', 'signup', 'bounded-candidate@example.in'),
    ):
        for name in ('auth-entered', 'auth-release', 'auth-completed'):
            (scratch / name).unlink(missing_ok=True)
        (scratch / 'auth-mode').write_text(gate)
        before_mail = mailbox.read_text() if mailbox.exists() else ''
        with client(base) as actor, ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(actor.post, f'/auth/{plane}/{purpose}', json={'email': email})
            try:
                wait(scratch / 'auth-entered')
                started = time.monotonic()
                health, read = control.get('/healthz'), control.get('/admin/users')
                elapsed = time.monotonic() - started
                checks.check(f'{gate}: health plus authorized SQL read finish during blocked issuance',
                    health.status_code == read.status_code == 200 and elapsed <= 1,
                    f'two_requests_seconds={elapsed:.4f}; budget=1.0000')
                response = pending.result(timeout=4)
                checks.check(f'{gate}: caller timeout is uniform accepted with no premature delivery/cookie',
                    response.status_code == 202 and response.json() == {'status': 'accepted'}
                    and 'set-cookie' not in response.headers
                    and (mailbox.read_text() if mailbox.exists() else '') == before_mail)
                for path, body in (
                    ('/auth/org/signup', {'email': 'busy-org@example.in', 'organization_name': 'Busy Organization'}),
                    ('/auth/org/login', {'email': 'unknown@example.in'}),
                    ('/auth/candidate/signup', {'email': 'new@example.in'}),
                    ('/auth/candidate/login', {'email': email}),
                    ('/auth/admin/login', {'email': 'unknown@example.in'}),
                ):
                    busy = control.post(path, json=body)
                    checks.check(f'{gate}: {path} shares retained admission', busy.status_code == 503
                        and busy.json() == {'detail': 'auth_code_capacity_exhausted'}
                        and busy.headers.get('retry-after') == '1')
            finally:
                (scratch / 'auth-release').touch()
            wait(scratch / 'auth-completed')
            (scratch / 'auth-mode').unlink()
            ready(control)
            verified = require(actor.post(f'/auth/{plane}/verify', json={'email': email, 'code': latest_code(mailbox, email)}))
            me = require(actor.get('/auth/me'))
            checks.check(f'{gate}: late operation completes once and delivered code establishes its own session',
                verified['principal'] == me['kind'] == plane
                and len([row for row in mailbox.read_text().splitlines() if json.loads(row)['to'] == email]) == 1)
            saved.append((dict(actor.cookies), me))
    (scratch / 'auth-mode').write_text('fail')
    response = control.post('/auth/candidate/signup', json={'email': 'failed-auth@example.in'})
    (scratch / 'auth-mode').unlink()
    checks.check('provider failure preserves opaque accepted contract and safe details',
        response.status_code == 202 and response.json() == {'status': 'accepted'}
        and 'private-auth-smoke-sentinel' not in response.text)
    accepted = require(control.post('/auth/candidate/signup', json={'email': 'failed-auth@example.in'}), 202)
    checks.check('capacity recovers after provider failure without automatic replay', accepted == {'status': 'accepted'}
        and len([row for row in mailbox.read_text().splitlines() if json.loads(row)['to'] == 'failed-auth@example.in']) == 1)
    rows = [json.loads(line) for line in (scratch / 'auth-thread-ownership.jsonl').read_text().splitlines()]
    checks.check('SQL sessions retain one thread and independent caller/worker lanes',
        all(row['owner'] == row['current'] for row in rows) and len({row['owner'] for row in rows}) >= 2)
    return saved


def check_auth_resolution_workers(checks, scratch, base, control, actors):
    def wait_count(name, count):
        path = scratch / name
        deadline = time.monotonic() + 10
        while not path.exists() or len(path.read_text().splitlines()) < count:
            assert time.monotonic() < deadline, 'controlled resolver checkpoint missing'
            time.sleep(.01)
    for gate in ('sql', 'touch'):
        for name in ('resolve-entered', 'resolve-completed', 'resolve-release'):
            (scratch / name).unlink(missing_ok=True)
        (scratch / 'resolve-mode').write_text(gate)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(actors[0].get, '/auth/me')
            try:
                wait_count('resolve-entered', 1)
                started = time.monotonic()
                health, read = control.get('/healthz'), control.get('/admin/users')
                elapsed = time.monotonic() - started
                checks.check(f'{gate}: liveness and admitted admin SQL read finish while resolution waits',
                    health.status_code == read.status_code == 200 and elapsed < 1,
                    f'two_requests_seconds={elapsed:.4f}; budget=1.0000')
                second = pool.submit(actors[1].get, '/auth/me')
                wait_count('resolve-entered', 2)
                for path, http in (('/admin/users', control), ('/jobs', actors[1]),
                                   ('/portal/me', actors[0]), ('/auth/me', actors[0])):
                    response = http.get(path)
                    checks.check(f'{gate}: full resolution capacity safely refuses {path}',
                        response.status_code == 503 and response.json() == {'detail': 'auth_resolution_capacity_exhausted'}
                        and response.headers.get('retry-after') == '1' and 'set-cookie' not in response.headers)
                for pending in (first, second):
                    response = pending.result(timeout=4)
                    checks.check(f'{gate}: caller wait ends without principal or session cookie',
                        response.status_code == 503 and response.json() == {'detail': 'auth_resolution_pending'}
                        and response.headers.get('retry-after') == '1' and 'set-cookie' not in response.headers)
                checks.check(f'{gate}: timed-out original work retains admission',
                    actors[0].get('/auth/me').json() == {'detail': 'auth_resolution_capacity_exhausted'})
            finally:
                (scratch / 'resolve-release').touch()
            wait_count('resolve-completed', 2)
        (scratch / 'resolve-mode').unlink()
        # Checkpoint is just before actual Future completion; a safe read may
        # briefly see retained admission. Never replay a mutation to probe it.
        deadline = time.monotonic() + 8
        while (response := actors[0].get('/auth/me')).status_code == 503:
            assert time.monotonic() < deadline
            time.sleep(.01)
        checks.check(f'{gate}: manual fresh read recovers the original candidate session',
            response.status_code == 200 and response.json()['kind'] == 'candidate')
    rows = [json.loads(line) for line in (scratch / 'auth-thread-ownership.jsonl').read_text().splitlines()]
    checks.check('all SQL session transactions keep their original thread', all(row['owner'] == row['current'] for row in rows))


def main():
    scratch = Path(tempfile.mkdtemp(prefix='r4-s2-t3c1-' if '--auth-code-workers' in sys.argv else 'r4-s1-t3a-'))
    with database(scratch) as (url, pg_options):
        return run(scratch, url, pg_options)


def run(scratch, url, pg_options):
    workers = '--auth-code-workers' in sys.argv
    resolution_workers = '--auth-resolution-workers' in sys.argv
    redemption_workers = '--auth-redemption-workers' in sys.argv
    session_workers = '--auth-session-workers' in sys.argv
    checks = Smoke('R4-S2-T3C1 auth code workers / HTTP / restart' if workers else 'R4-S1-T3A auth/session extraction HTTP/restart')
    print(f"Synthetic auth evidence: {scratch}", flush=True)
    stop, events, mailbox = scratch / "stop", scratch / "lifecycle.jsonl", scratch / "mail.jsonl"
    env = {key: value for key, value in base_env().items() if not key.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_ENV": "local",
        "DEE_CANDIDATES_DB_URL": url, 'PGOPTIONS': pg_options,
        "DEE_DB_MIGRATE_ON_BOOT": "true", "DEE_API_AUTH_KEY": ADMIN,
        "DEE_OPENROUTER_API_KEY": "", "DEE_GITHUB_TOKEN": "",
        "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_SPEECH_PROVIDER": "local",
        "DEE_EMAIL_PROVIDER": "capture", "DEE_EMAIL_CAPTURE_PATH": str(mailbox),
        "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
        "DEE_VERIF_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_COOLDOWN_SECONDS": "0",
        "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
        "DEE_GRIEVANCE_OFFICER_NAME": "Synthetic Public Officer",
        "DEE_GRIEVANCE_OFFICER_EMAIL": "public-officer@example.in",
        "DEE_GRIEVANCE_OFFICER_PHONE": "+91 80 4000 0000", "DEE_GRIEVANCE_RESPONSE_DAYS": "21",
        "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "VERITAS_SQL_SMOKE_EVENTS": str(events),
        "VERITAS_SQL_SMOKE_FACTORY": "smoke_r4_s1_t3a:create_auth_code_smoke_app" if workers or resolution_workers or redemption_workers or session_workers else "smoke_r4_s1_t1a:create_smoke_app",
        "PYTHONPATH": os.pathsep.join(str(path) for path in (ROOT / "src", ROOT / "scripts", ROOT)),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    if workers:
        env.update(DEE_AUTH_CODE_MAX_CONCURRENT_REQUESTS='1', DEE_AUTH_CODE_WAIT_SECONDS='.3')
    if resolution_workers:
        env.update(DEE_AUTH_RESOLUTION_MAX_CONCURRENT_REQUESTS='2', DEE_AUTH_RESOLUTION_WAIT_SECONDS='.3',
                   DEE_SESSION_LAST_SEEN_WRITE_SECONDS='0')
    if redemption_workers:
        env.update(DEE_AUTH_REDEMPTION_MAX_CONCURRENT_REQUESTS='1', DEE_AUTH_REDEMPTION_WAIT_SECONDS='.3')
    if session_workers:
        env.update(DEE_AUTH_SESSION_MAX_CONCURRENT_REQUESTS='1', DEE_AUTH_SESSION_WAIT_SECONDS='.3')
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    @contextmanager
    def server():
        stop.unlink(missing_ok=True)
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", str(port), str(stop)],
                env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                with client(base) as health:
                    assert wait_healthy(health), "scratch auth app failed to start"
                yield
            finally:
                stop.write_text("stop", encoding="utf-8")
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    proc.wait(timeout=10)
                    raise AssertionError("scratch auth app failed graceful shutdown")
                assert proc.returncode == 0, "scratch auth app failed during lifespan"

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    def public_surface():
        from app import __version__

        with client(base) as anonymous:
            page = anonymous.get("/ui/")
            checks.check("anonymous UI delivers the exact entry document",
                page.status_code == 200 and page.content == (ROOT / "frontend/Veritas.dc.html").read_bytes())
            for asset in ("api.js", "portal-auth.js", "employer-roles.js"):
                module = anonymous.get("/ui/" + asset)
                checks.check("anonymous UI delivers its declared " + asset,
                    page.status_code == module.status_code == 200
                    and f'<script src="./{asset}"></script>' in page.text
                    and module.content == (ROOT / "frontend" / asset).read_bytes()
                    and "javascript" in module.headers["content-type"]
                    and anonymous.get("/ui/not-an-asset.txt").status_code == 404)
            health = require(anonymous.get("/healthz"))
            contact = require(anonymous.get("/grievance"))
            service = require(anonymous.get("/"))
            checks.check("anonymous health preserves version environment effective mode and ordered domains",
                health == {"status": "ok", "version": __version__, "env": "local",
                    "llm_mode": "live", "domains": ["data_eng", "genai"]})
            checks.check("published grievance exposes exactly the configured contact",
                contact == {"name": "Synthetic Public Officer", "email": "public-officer@example.in",
                    "phone": "+91 80 4000 0000", "response_days": 21})
            schema = require(anonymous.get("/openapi.json"))
            advertised = sorted((f"{method.upper()} {path}" for path, methods in schema["paths"].items()
                for method in methods if path != "/" and method in {"get", "post", "put", "patch", "delete"}),
                key=lambda e: (e.split(" ", 1)[1], e))
            checks.check("service stays advisory and advertises all 74 other operations without docs or UI",
                service == {"service": "depth-eval-engine", "advisory": True,
                    "human_review_required": True, "endpoints": advertised} and len(advertised) == 74)
            checks.check("invalid machine credentials do not gate the three public reads", all(
                require(anonymous.get(path, headers={"X-API-Key": "invalid"})) == body
                for path, body in (("/healthz", health), ("/grievance", contact), ("/", service))))
            checks.check("domains refuse anonymous and invalid admin credentials", all(
                require(anonymous.get("/domains", headers=headers), 401)
                    == {"detail": "invalid or missing admin credential"}
                for headers in ({}, {"X-API-Key": "invalid"})))
        return health, contact, service

    def login(http, plane, email, *, organization=None):
        body = {"email": email}
        if organization:
            body["organization_name"] = organization
        path = f"/auth/{plane}/" + ("signup" if organization or plane == "candidate" else "login")
        assert require(http.post(path, json=body), 202) == {"status": "accepted"}
        response = http.post(f"/auth/{plane}/verify", json={"email": email, "code": latest_code(mailbox, email)})
        session = require(response)
        cookies = response.headers.get_list("set-cookie")
        checks.check(f"{plane} verify preserves cookie posture", len(cookies) == 2
            and sum("HttpOnly" in value for value in cookies) == 1
            and all("SameSite=lax" in value and "Path=/" in value for value in cookies))
        assert session["principal"] == ("org" if plane == "org" else plane)
        return session["csrf_token"]

    with client(base, headers={"X-API-Key": ADMIN}) as control, client(base) as operator, \
            client(base) as org, client(base) as other_org, client(base) as candidate, client(base) as sibling:
        with server():
            saved_public = public_surface()
            if workers:
                worker_sessions = check_auth_code_workers(checks, scratch, base, control, mailbox)
            if redemption_workers:
                worker_sessions = check_auth_redemption_workers(checks, scratch, base, control, mailbox)
            if session_workers:
                worker_sessions = check_auth_session_workers(checks, scratch, base, control, mailbox, login)
            saved_domains = require(control.get("/domains"))
            checks.check("admin machine key reads both domains with their existing metadata",
                [row["key"] for row in saved_domains] == ["data_eng", "genai"]
                and all(set(row) == {"key", "display_name", "claim_types"}
                    and row["display_name"] and row["claim_types"] for row in saved_domains))
            require(control.post("/admin/users", json={"email": "router-admin@example.in", "label": "Synthetic router admin"}))
            admin_csrf = login(operator, "admin", "router-admin@example.in")
            org_csrf = login(org, "org", "router-org@example.in", organization="Synthetic Router A")
            other_csrf = login(other_org, "org", "router-other@example.in", organization="Synthetic Router B")
            candidate_csrf = login(candidate, "candidate", "router-candidate@example.in")
            sibling_csrf = login(sibling, "candidate", "router-candidate@example.in")
            who = [require(http.get("/auth/me")) for http in (operator, org, other_org, candidate)]
            if resolution_workers:
                check_auth_resolution_workers(checks, scratch, base, control, (candidate, org))
            checks.check("three planes resolve their own sessions", [row["kind"] for row in who] == ["admin", "org", "org", "candidate"])
            checks.check("domain safe read accepts operator cookie and refuses org and candidate cookies",
                require(operator.get("/domains", headers={"X-API-Key": "invalid"})) == saved_domains
                and org.get("/domains").status_code == candidate.get("/domains").status_code == 401)
            checks.check("anonymous and header-only callers cannot use session lifecycle", control.get("/auth/me").status_code == 401)
            for http, path, body in (
                (operator, "/ledger/orgs", {"name": "Denied without CSRF"}),
                (org, "/jobs", {"title": "Denied without CSRF", "must_have_skills": ["python"]}),
                (candidate, "/portal/consents", {"purpose": "ledger_read"}),
            ):
                checks.check(path + " retains session CSRF refusal", http.post(path, json=body).status_code == 403)
            other_id = who[2]["organization_id"]
            other_key = require(control.post(f"/ledger/orgs/{other_id}/api-key"))["api_key"]
            org.headers["X-Org-Key"] = other_key
            checks.check("cookie plus another employer key cannot bypass CSRF", org.post("/jobs", json={"title": "Denied", "must_have_skills": ["python"]}).status_code == 403)
            org.headers["X-CSRF-Token"] = org_csrf
            job = require(org.post("/jobs", json={"title": "Synthetic Router Engineer", "must_have_skills": ["python"]}))
            checks.check("session retains tenant precedence over header key", other_org.get(f"/jobs/{job['id']}").status_code == 404)
            candidate.headers["X-CSRF-Token"] = candidate_csrf
            checks.check("candidate cannot revoke an employer session", candidate.post(f"/auth/sessions/{who[1]['session_id']}/revoke").status_code == 404)
            sessions = require(candidate.get("/auth/sessions"))
            checks.check("same subject sees both own devices only", len(sessions) == 2 and all(row["id"] != who[1]["session_id"] for row in sessions))
            require(candidate.post(f"/auth/sessions/{who[3]['session_id']}/revoke"))
            checks.check("self revocation leaves sibling session usable", candidate.get("/auth/me").status_code == 401 and sibling.get("/portal/me").status_code == 200)
            unknown = require(control.post("/auth/org/login", json={"email": "router-unknown@example.in"}), 202)
            checks.check("unknown organization login remains uniform", unknown == {"status": "accepted"})
            invalid = control.post("/auth/admin/verify", json={"email": "missing@example.in", "code": "000000"})
            checks.check("invalid verification sets no cookies", invalid.status_code == 400 and "set-cookie" not in invalid.headers)

            # T3E reuses this migrated, captured-login, graceful-restart journey.
            operator.headers["X-CSRF-Token"] = admin_csrf
            other_org.headers["X-CSRF-Token"] = other_csrf
            subject = require(sibling.get("/portal/me"))["candidate_id"]
            intake = require(control.post("/candidates", json={"evaluate": False, "resume_text":
                "Synthetic Feature Subject\nEmail: router-candidate@example.in\nSKILLS\nSQL"}))
            assert intake["candidate_id"] == subject, "feature fixture must belong to the verified portal subject"
            ledger_path = f"/ledger/candidates/{subject}"
            org_id = who[1]["organization_id"]
            grants = {purpose: require(operator.post(ledger_path + "/consent", json={
                "purpose": purpose, "org_id": org_id})) for purpose in ("ledger_read", "ledger_write")}
            checks.check("admin cookie grants exact-purpose employer consent", all(
                require(operator.get(ledger_path + "/consent", params={"org_id": org_id, "purpose": purpose}))["grant_id"] == grant["id"]
                for purpose, grant in grants.items()))
            # T3F employer composition shares this existing restart harness.
            checks.check("employer board explains the empty feature pool",
                require(org.get(f"/jobs/{job['id']}/board"))["match"]["reason"] == "no_materialized_candidates")
            checks.check("employer job and board hide other tenant", all(
                other_org.get(f"/jobs/{job['id']}" + suffix).status_code == 404 for suffix in ("", "/board"))
                and other_org.patch(f"/jobs/{job['id']}", json={"status": "closed"}).status_code == 404
                )
            employer_candidate = require(control.post("/candidates", json={"evaluate": False, "resume_text":
                "Synthetic Employer Candidate\nEmail: employer-flow@example.in\nEXPERIENCE\nEngineer at Example, 2020 - 2025\nSKILLS\nPython, Django"}))["candidate_id"]
            updated_job = require(org.patch(f"/jobs/{job['id']}", json={"spec": {
                "title": "Synthetic Backend Role", "must_have_skills": ["Python"],
                "comp_band": {"ctc_min": 1500000, "ctc_max": 2500000}}}))
            materialized = require(control.post("/features/materialize", json={}))
            # T3G: actual feature composition and CSRF.
            checks.check("feature routes refuse other planes and preserve admin session CSRF",
                all(http.post("/features/materialize", json={}).status_code == 401
                    for http in (org, other_org, sibling)))
            operator.headers.pop("X-CSRF-Token")
            operator.headers["X-API-Key"] = ADMIN
            checks.check("valid admin key alongside a cookie cannot bypass feature CSRF",
                operator.post("/features/materialize", json={}).status_code == 403)
            operator.headers.pop("X-API-Key")
            operator.headers["X-CSRF-Token"] = admin_csrf
            refreshed = require(operator.post("/features/materialize", json={"candidate_ids": [subject, "missing"]}))
            checks.check("partial feature refresh skips unknown IDs",
                refreshed["materialized"] == refreshed["skipped"] == 1)
            checks.check("feature view errors retain their HTTP contracts",
                operator.post("/features/materialize", json={"view_name": "unknown-view"}).status_code == 422)
            employer_board = require(org.get(f"/jobs/{job['id']}/board"))
            checks.check("materialized employer board returns saved advisory data", employer_board["match"]["advisory"]
                and employer_board["match"]["ranked"][0]["candidate_id"] == employer_candidate
                and employer_board["match"]["pool_size"] >= 1
                and employer_board["advisory"])
            # T3H: subject-owned requests and operator review across restart.
            sibling.headers["X-CSRF-Token"] = sibling_csrf
            own_portal_key = require(control.post(f"/candidates/{subject}/auth-key"))["access_key"]
            other_portal_key = require(control.post(f"/candidates/{employer_candidate}/auth-key"))["access_key"]
            sibling.headers["X-Candidate-Key"] = other_portal_key
            checks.check("portal cookie keeps subject ownership over a different valid key",
                require(sibling.get("/portal/me", params={"candidate_id": employer_candidate}))["candidate_id"] == subject)
            sibling.headers.pop("X-CSRF-Token")
            checks.check("portal cookie plus another key cannot bypass write CSRF", all(
                sibling.request(method, path, json=body).status_code == 403 for method, path, body in (
                    ("POST", "/portal/consents", {"purpose": "verification_read"}),
                    ("DELETE", "/portal/me", None))))
            sibling.headers["X-CSRF-Token"] = sibling_csrf
            # T3I: manual review and redacted employer reads.
            verification_paths = {kind: f"/verification/candidates/{subject}/{kind}" for kind in ("assurance",)}
            checks.check("employer verification reads require current consent", all(
                org.get(path).status_code == 403 for path in verification_paths.values()))
            checks.check("verifications start empty for the cookie subject and the other subject",
                require(sibling.get("/portal/verifications"))["verifications"] == []
                and require(sibling.get("/portal/verifications"))["assurance"]["level"] == 0
                and require(control.get("/portal/verifications", headers={"X-Candidate-Key": other_portal_key}))["verifications"] == [])
            review_path = f"/candidates/{subject}/verifications/manual-review"
            checks.check("manual review refuses candidate and admin cookie without CSRF",
                sibling.post(review_path, json={"outcome": "verified"}).status_code == 401
                and operator.post(review_path, json={"outcome": "verified"}, headers={"X-CSRF-Token": ""}).status_code == 403)
            saved_review = require(operator.post(review_path, json={"outcome": "verified", "evidence_digest": "a" * 64, "note": "Private manual evidence"}))
            saved_verifications = require(sibling.get("/portal/verifications"))
            checks.check("manual review lifts the identity ladder",
                saved_review["assurance_level"] == saved_verifications["assurance"]["level"] == 3)
            portal_grant = require(sibling.post("/portal/consents", json={"purpose": "verification_read", "org_id": org_id}))
            saved_assessments = {kind: require(org.get(path)) for kind, path in verification_paths.items()}
            checks.check("consented employer receives advisory summaries without private evidence", all(
                body["advisory"] and not any(secret in json.dumps(body) for secret in (
                    "evidence_digest", "destination_hash", "claim_ref", "Private manual evidence", "a" * 64, employer_candidate))
                for body in saved_assessments.values())
                and saved_assessments["assurance"]["level"] == 3)
            checks.check("verification consent is employer scoped and other subject stays private", all(
                other_org.get(path).status_code == 403 for path in verification_paths.values()))
        with server():
            if workers or redemption_workers or session_workers:
                for cookies, me in worker_sessions:
                    with client(base) as resumed:
                        resumed.cookies.update(cookies)
                        checks.check('recovered auth session survives graceful restart',
                            require(resumed.get('/auth/me')) == me)
            checks.check("public bodies and guarded domain metadata survive graceful restart exactly",
                public_surface() == saved_public and require(operator.get("/domains")) == saved_domains
                and org.get("/domains").status_code == sibling.get("/domains").status_code == 401)
            checks.check("all planes and tenant data survive graceful restart", operator.get("/admin/users").status_code == 200
                and org.get(f"/jobs/{job['id']}").status_code == 200 and sibling.get("/portal/me").status_code == 200
                and other_org.get(f"/jobs/{job['id']}").status_code == 404)
            checks.check("employer job and board survive restart",
                require(org.get(f"/jobs/{job['id']}")) == updated_job
                and require(org.get(f"/jobs/{job['id']}/board")) == employer_board)
            checks.check("subject grants survive graceful restart exactly",
                portal_grant["id"] in {row["grant"]["id"] for row in require(sibling.get("/portal/consents"))})
            checks.check("verification manual review and employer summaries survive graceful restart exactly",
                require(sibling.get("/portal/verifications")) == saved_verifications
                and all(require(org.get(path)) == saved_assessments[kind] for kind, path in verification_paths.items()))
            require(sibling.post(f"/portal/consents/{portal_grant['id']}/revoke"))
            checks.check("revoked verification consent refuses both employer summaries", all(
                org.get(path).status_code == 403 for path in verification_paths.values()))
            for purpose, grant in grants.items():
                require(operator.post(f"/ledger/consent/{grant['id']}/revoke"))
            checks.check("revoked persisted consent is immediately reported as not allowed", not any(
                require(operator.get(ledger_path + "/consent", params={"org_id": org_id, "purpose": purpose}))["allowed"]
                for purpose in grants))
            access_log = require(sibling.get("/portal/access-log"))
            checks.check("verification audit retains allowed and denied employer access", all(
                {row["allowed"] for row in access_log if row["action"] == action} == {True, False}
                for action in ("verification.query",)))
            machine_org = require(operator.post("/ledger/orgs", json={"name": "Synthetic ledger key lifecycle"}))
            machine_id = machine_org["org"]["id"]
            with client(base, headers={"X-Org-Key": machine_org["api_key"]}) as machine:
                rotated = require(operator.post(f"/ledger/orgs/{machine_id}/api-key"))
                checks.check("ledger key rotation invalidates original credential", machine.get("/jobs").status_code == 401)
                machine.headers["X-Org-Key"] = rotated["api_key"]
                checks.check("rotated credential resolves on the employer plane", machine.get("/jobs").status_code == 200)
                require(operator.delete(f"/ledger/orgs/{machine_id}"))
                checks.check("organization offboarding invalidates rotated credential", machine.get("/jobs").status_code == 401)
            for http, token in ((operator, admin_csrf), (org, org_csrf), (other_org, other_csrf), (sibling, sibling_csrf)):
                http.headers["X-CSRF-Token"] = token
                assert require(http.post("/auth/logout")) == {"logged_out": True}
                assert http.get("/auth/me").status_code == 401
            checks.check("logout clears all four sessions across planes", True)
            erased = require(control.delete("/portal/me", headers={"X-Candidate-Key": own_portal_key}))
            checks.check("portal erasure removes own credential while another subject survives",
                erased["deleted"] and erased["candidate_id"] == subject
                and control.get("/portal/me", headers={"X-Candidate-Key": own_portal_key}).status_code == 401
                and require(control.get("/portal/me", headers={"X-Candidate-Key": other_portal_key}))["candidate_id"] == employer_candidate)
            checks.check("erasure removes verification access while another subject survives",
                control.get("/portal/verifications", headers={"X-Candidate-Key": own_portal_key}).status_code == 401
                and control.get("/portal/verifications", headers={"X-Candidate-Key": other_portal_key}).status_code == 200
                and all(control.get(path, headers={"X-Org-Key": other_key}).status_code == 404 for path in verification_paths.values()))
        rows = [json.loads(line) for line in events.read_text().splitlines()]
        checks.check("two migrated lifespans close and detach owned SQL", sum(row["event"] == "stopped" for row in rows) == 2
            and sum(row["event"] == "disposed" for row in rows) == 2
            and all(row["revision"] == "0031_cut_unused_tables" for row in rows if row["event"] == "started"))
    return checks.summary()


if __name__ == "__main__":
    if "--serve" in sys.argv:
        asyncio.run(serve(int(sys.argv[2]), Path(sys.argv[3])))
    else:
        raise SystemExit(main())
