"""Captured contact email/refusal/retry/restart on migrated scratch storage.

Default SQLite; --postgres requires an explicitly configured disposable database.
Never sends real email/SMS. The control file changes only this synthetic provider.
"""
from contextlib import asynccontextmanager, contextmanager
from concurrent.futures import ThreadPoolExecutor
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from threading import get_ident

from sqlalchemy import create_engine, event, select, update

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database
from app.core.db import make_session_factory
from app.services.email import CaptureEmail, EmailSendFailed, NullEmail
from app.verification.models import VerificationChallengeRow

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-contact-delivery-admin"


class ControlledCaptureEmail(CaptureEmail):
    """Capture/failure controls are local evidence, never a production provider."""
    @property
    def mode(self):
        path = Path(self.settings.email_capture_path + ".control")
        return path.read_text(encoding="utf-8") if path.exists() else "ok"

    @property
    def available(self):
        return self.mode != "unavailable"

    def send(self, *, to, subject, body):
        if subject == "Verify your Veritas contact" and self.mode == 'held':
            contact_hold(Path(self.settings.email_capture_path))
        if subject == "Verify your Veritas contact" and self.mode == "failed":
            raise EmailSendFailed("synthetic provider refusal")
        super().send(to=to, subject=subject, body=body)
        if subject == "Verify your Veritas contact" and self.mode == "partial":
            raise EmailSendFailed("synthetic ambiguous provider acknowledgment")


def create_smoke_app():
    import app.services as services
    from smoke_r2_s2_t1 import create_smoke_app as fake_engine_app
    services.build_email = lambda settings: (ControlledCaptureEmail(settings)
        if settings.email_provider == "capture" else NullEmail(settings))
    if os.environ.get('VERITAS_CONTACT_CODE_SMOKE') != 'true':
        return fake_engine_app()
    from smoke_r4_s1_t1a import create_smoke_app as sql_app
    app = sql_app()
    original = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            svc = app.state.services
            mailbox = Path(svc.settings.email_capture_path)
            mode = Path(str(mailbox) + '.control')
            start = svc.verification.start
            def current():
                return mode.read_text() if mode.exists() else ''
            def observed_start(*args, **kwargs):
                try:
                    return start(*args, **kwargs)
                finally:
                    if current() in {'held', 'sql'}:
                        contact_marker(mailbox, 'completed').touch()
            def sql(conn, cursor, statement, parameters, context, many):
                if current() == 'sql' and 'verifications' in statement and not contact_marker(mailbox, 'entered').exists():
                    contact_hold(mailbox)
            def owner(session, transaction, connection):
                previous = session.info.setdefault('contact_worker_owner', get_ident())
                assert previous == get_ident(), 'live Session crossed threads'
                with contact_marker(mailbox, 'threads').open('a') as log:
                    log.write(json.dumps({'owner': previous, 'current': get_ident()}) + '\n')
            svc.verification.start = observed_start
            engine = svc.session_factory.kw['bind']
            event.listen(engine, 'before_cursor_execute', sql)
            event.listen(svc.session_factory, 'after_begin', owner)
            try:
                yield
            finally:
                event.remove(engine, 'before_cursor_execute', sql)
                event.remove(svc.session_factory, 'after_begin', owner)
    app.router.lifespan_context = lifespan
    return app


def contact_marker(mailbox, name):
    return Path(str(mailbox) + '.contact-' + name)


def contact_hold(mailbox):
    contact_marker(mailbox, 'entered').touch()
    deadline = time.monotonic() + 20
    while not contact_marker(mailbox, 'release').exists():
        assert time.monotonic() < deadline, 'synthetic contact gate timed out'
        time.sleep(.01)


def check_contact_workers(checks, http, base, mailbox, headers, other, email, codes):
    control = Path(str(mailbox) + '.control')
    def wait(name):
        deadline = time.monotonic() + 10
        while not contact_marker(mailbox, name).exists():
            assert time.monotonic() < deadline, 'contact worker did not reach checkpoint'
            time.sleep(.01)
    for gate in ('held', 'sql'):
        for name in ('entered', 'release', 'completed'):
            contact_marker(mailbox, name).unlink(missing_ok=True)
        control.write_text(gate)
        before = mailbox.read_text() if mailbox.exists() else ''
        with client(base, headers=headers) as actor, ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(actor.post, '/portal/verifications', json={'method': 'otp_email', 'destination': email})
            try:
                wait('entered')
                began = time.monotonic()
                health, read = http.get('/healthz'), http.get('/admin/users')
                elapsed = time.monotonic() - began
                checks.check(f'{gate}: unrelated health plus authorized SQL read finish during held contact work',
                    health.status_code == read.status_code == 200 and elapsed <= 1,
                    f'two_requests_seconds={elapsed:.4f}; budget=1.0000')
                response = pending.result(timeout=4)
                checks.check(f'{gate}: caller wait refuses honestly before delivery without code or invented success',
                    response.status_code == 504 and response.json() == {'detail': 'contact_code_pending'}
                    and (mailbox.read_text() if mailbox.exists() else '') == before)
                for candidate in (headers, other):
                    busy = http.post('/portal/verifications', headers=candidate, json={'method': 'self_attested'})
                    checks.check(f'{gate}: start/resend actors share retained admission', busy.status_code == 503
                        and busy.json() == {'detail': 'contact_code_capacity_exhausted'} and busy.headers.get('retry-after') == '1')
            finally:
                contact_marker(mailbox, 'release').touch()
            wait('completed')
            control.write_text('ok')
            listed = actor.get('/portal/verifications').json()['verifications']
            row = next(row for row in reversed(listed) if row['status'] == 'pending')
            code = latest_code(mailbox, email)
            codes.append(code)
            # Only the newly delivered message is counted, not earlier verified codes.
            after = mailbox.read_text()
            checks.check(f'{gate}: late completion sends once and own saved status recovers its code',
                len(after.splitlines()) == len(before.splitlines()) + 1
                and actor.post(f"/portal/verifications/{row['id']}/confirm", json={'code': code}).json()['status'] == 'verified')
    rows = [json.loads(row) for row in contact_marker(mailbox, 'threads').read_text().splitlines()]
    checks.check('contact SQL sessions keep one owner across separate caller/worker threads',
        all(row['owner'] == row['current'] for row in rows) and len({row['owner'] for row in rows}) >= 2)


def latest_code(mailbox, destination):
    messages = [json.loads(line) for line in mailbox.read_text(encoding="utf-8").splitlines()]
    msg = next(m for m in reversed(messages) if m["to"] == destination and m["subject"] == "Verify your Veritas contact")
    return re.search(r"\b(\d{6})\b", msg["body"])[1]


def main():
    workers = '--contact-code-workers' in sys.argv
    scratch = Path(tempfile.mkdtemp(prefix="r3-contact-delivery-"))
    print(f"Synthetic HTTP evidence: {scratch}", flush=True)
    checks = Smoke("R3-S1-T2 contact delivery HTTP/restart")
    mailbox = scratch / "mail.jsonl"
    control = Path(str(mailbox) + ".control")
    codes = []
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
        env.update({
            "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_CANDIDATES_DB_URL": url,
            "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
            "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
            "DEE_EMAIL_PROVIDER": "capture", "DEE_EMAIL_CAPTURE_PATH": str(mailbox),
            "DEE_VECTORSTORE_BACKEND": "memory", "DEE_SPEECH_PROVIDER": "local",
            "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
            "DEE_VERIF_OTP_DEBUG_ECHO": "false", "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
            "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
            "PGOPTIONS": pg_options, "PYTHONPATH": os.pathsep.join(str(p) for p in (ROOT / "src", ROOT / "scripts", ROOT)),
            "NO_PROXY": "127.0.0.1,localhost",
        })
        stop, events = scratch / 'stop', scratch / 'lifecycle.jsonl'
        if workers:
            env.update(DEE_CONTACT_CODE_MAX_CONCURRENT_REQUESTS='1', DEE_CONTACT_CODE_WAIT_SECONDS='.5',
                VERITAS_CONTACT_CODE_SMOKE='true', VERITAS_SQL_SMOKE_EVENTS=str(events),
                VERITAS_SQL_SMOKE_FACTORY='smoke_r3_s1_t2:create_smoke_app')
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]

        @contextmanager
        def server():
            stop.unlink(missing_ok=True)
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                args = ([sys.executable, str(Path(__file__).resolve()), '--serve', str(port), str(stop)] if workers
                    else uvicorn_argv(port, target="smoke_r3_s1_t2:create_smoke_app") + ["--factory"])
                proc = subprocess.Popen(args,
                    env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    with client(f"http://127.0.0.1:{port}", headers={"X-API-Key": ADMIN}) as http:
                        assert wait_healthy(http), "scratch app failed to start"
                        yield http
                finally:
                    if workers:
                        stop.touch()
                        try: proc.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            proc.terminate(); proc.wait(timeout=10)
                            raise AssertionError('scratch contact app failed graceful shutdown')
                        assert proc.returncode == 0, 'scratch contact app failed during lifespan'
                    else:
                        proc.terminate()
                        try: proc.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            proc.kill(); proc.wait(timeout=10)

        def require(response, status=200):
            assert response.status_code == status, (response.request.url.path, response.status_code)
            return response.json()

        engine = create_engine(url, hide_parameters=True,
            connect_args={"options": pg_options} if pg_options else {})
        factory = make_session_factory(engine)
        def mutate(vid, **values):
            with factory.begin() as session:
                session.execute(update(VerificationChallengeRow).where(
                    VerificationChallengeRow.verification_id == vid).values(**values))
        def challenges():
            with factory() as session: return len(session.scalars(select(VerificationChallengeRow)).all())

        email = "http-contact@example.com"
        other_email = "http-other@example.com"
        try:
            with server() as http:
                candidates = [require(http.post("/candidates", json={"evaluate": False, "resume_text":
                    f"Synthetic Contact\nEmail: {address}\nPhone: +919876543210\nSkills: Python SQL"}))["candidate_id"]
                    for address in (email, other_email)]
                headers = [{"X-Candidate-Key": require(http.post(f"/candidates/{cid}/auth-key"))["access_key"]} for cid in candidates]
                a, b = headers
                def start(method="otp_email", destination=email, status=200):
                    return require(http.post("/portal/verifications", headers=a,
                        json={"method": method, "destination": destination}), status)
                def confirm(vid, value, headers=a, status=200):
                    return require(http.post(f"/portal/verifications/{vid}/confirm", headers=headers, json={"code": value}), status)
                def rows(): return require(http.get("/portal/verifications", headers=a))["verifications"]

                checks.check("migrated app and two candidate actors start", True)
                checks.check("wrong destination refuses before delivery", start(destination=other_email, status=400)["detail"])
                checks.check("phone delivery is explicitly unavailable", start("otp_phone", "+919876543210", 503) == {"detail": "phone_unavailable"})
                first = start()["verification"]; first_code = latest_code(mailbox, email); codes.append(first_code)
                checks.check("actual email capture supplies code without plaintext echo", bool(first_code) and first["status"] == "pending")
                checks.check("cooldown refuses a second send", "recently" in start(status=429)["detail"])
                before = challenges()
                control.write_text("unavailable", encoding="utf-8")
                checks.check("unavailable email refuses without new secret", start(status=503) == {"detail": "email_unavailable"} and challenges() == before)
                control.write_text("partial", encoding="utf-8")
                mutate(first["id"], last_sent_at=datetime.now(timezone.utc)-timedelta(seconds=61))
                checks.check("provider acknowledgment failure is not sent success", start(status=503) == {"detail": "email_send_failed"})
                partial_code = latest_code(mailbox, email); codes.append(partial_code)
                failed = next(v for v in reversed(rows()) if v["status"] == "failed")
                checks.check("provider-rejected captured code cannot confirm", confirm(failed["id"], partial_code, status=400)["detail"])
                checks.check("failure rollback retains exactly the previous active secret", challenges() == before)
                checks.check("foreign confirmation remains indistinguishable 404", confirm(first["id"], first_code, headers=b, status=404) == {"detail": "verification not found"})
                checks.check("previous code still confirms after failed resend", confirm(first["id"], first_code)["status"] == "verified")
                checks.check("confirmation is single use", confirm(first["id"], first_code, status=400)["detail"])
                control.write_text("failed", encoding="utf-8")
                checks.check("unsent request fails with safe response", start(status=503) == {"detail": "email_send_failed"} and challenges() == 0)
                control.write_text("ok", encoding="utf-8")
                retry = start()["verification"]; retry_code = latest_code(mailbox, email); codes.append(retry_code)
                mutate(retry["id"], expires_at=datetime.now(timezone.utc)-timedelta(seconds=1))
                checks.check("expired delivered code is refused", confirm(retry["id"], retry_code, status=400)["detail"] == "challenge expired")
                exhausted = start()["verification"]; exhausted_code = latest_code(mailbox, email); codes.append(exhausted_code)
                mutate(exhausted["id"], attempts=5)
                checks.check("exhausted correct code is refused", confirm(exhausted["id"], exhausted_code, status=400)["detail"] == "too many attempts")
                final = start(); final_code = latest_code(mailbox, email); codes.append(final_code)
                checks.check("successful API never exposes raw code", final.get("debug_code") is None)
                completed = confirm(final["verification"]["id"], final_code)
                if workers:
                    check_contact_workers(checks, http, f'http://127.0.0.1:{port}', mailbox, a, b, email, codes)

            with server() as http:
                saved = require(http.get("/portal/verifications", headers=a))
                checks.check("restart preserves actual outcome and advisory contact assurance", any(v == completed for v in saved["verifications"]) and saved["assurance"]["level"] == 2 and saved["assurance"]["advisory"])
                require(http.delete("/portal/me", headers=a))
                checks.check("erasure refuses the old candidate and preserves the second", http.get("/portal/verifications", headers=a).status_code == 401 and http.get("/portal/verifications", headers=b).status_code == 200)
                checks.check("erasure leaves no candidate challenge secrets", challenges() == 0)
            if workers:
                lifecycle = [json.loads(row) for row in events.read_text().splitlines()]
                checks.check('both migrated contact lifespans dispose and detach SQL gracefully',
                    sum(row['event'] == 'disposed' for row in lifecycle) == 2
                    and sum(row['event'] == 'stopped' and row['detached'] for row in lifecycle) == 2)
            logged = (scratch / "server.log").read_text(encoding="utf-8")
            checks.check("actual rendered server logs omit destinations and codes", all(value not in logged for value in [email, other_email, *codes]))
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    if '--serve' in sys.argv:
        from smoke_r4_s1_t1a import serve
        asyncio.run(serve(int(sys.argv[2]), Path(sys.argv[3])))
        raise SystemExit(0)
    raise SystemExit(main())
