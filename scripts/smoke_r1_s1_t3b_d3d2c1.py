"""Atomic login erasure through real HTTP, process exit and migrated restart.

SQLite by default; --postgres uses an owned schema on disposable DEE_TEST_DB_URL.
Synthetic capture email only. The injection exists only in the scratch app.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

import httpx

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database
from smoke_s82 import _code_for

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-atomic-erasure-admin"
GATE_APP = '''
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from sqlalchemy import event, select
from app.main import app
from app.auth.challenges import ChallengeScope
from app.auth.models import LoginChallengeRow, LoginIssuanceRow
from app.auth.schema import AuthPlane, LoginPurpose

issuer = ThreadPoolExecutor(max_workers=1)
ready, release = Event(), Event()
pending = None

@app.post('/_test/start-send')
async def start_send(email: str, plane: AuthPlane = AuthPlane.CANDIDATE, crash: bool = False):
    global pending
    auth = app.state.services.auth
    auth._settings.login_otp_cooldown_seconds = 0
    digest = auth.hash_email(email)
    if plane == AuthPlane.ORG and auth._store.org_user_by_email(digest) is None:
        auth._store.create_org_with_owner(name='Synthetic ' + email, email_hash=digest)
    if plane == AuthPlane.ADMIN and auth._store.admin_user_by_email(digest) is None:
        auth._store.create_admin_user(email_hash=digest)
    actual_send = auth._email.send
    ready.clear()
    release.clear()
    def held_send(**kwargs):
        actual_send(**kwargs)
        if crash:
            os._exit(74)
        ready.set()
        assert release.wait(30)
    def work():
        auth._email.send = held_send
        try:
            sent, code = auth.issue_code(email=email, plane=plane, purpose=LoginPurpose.LOGIN,
                                        at=datetime.now(timezone.utc))
            return {'activated': sent, 'has_code': code is not None}
        finally:
            auth._email.send = actual_send
    pending = issuer.submit(work)
    assert ready.wait(10)
    with app.state.services.candidates._session_factory() as session:
        token = session.scalar(select(LoginIssuanceRow.id).where(LoginIssuanceRow.email_hash == digest))
    return {'reserved': token is not None, 'token': token}

@app.post('/_test/finish-send')
async def finish_send():
    release.set()
    return pending.result(timeout=15)

@app.post('/_test/replay')
async def replay(email: str, token: str):
    auth = app.state.services.auth
    now = datetime.now(timezone.utc)
    activated = auth._store.activate_issuance(
        ChallengeScope(auth.hash_email(email), LoginPurpose.LOGIN, AuthPlane.CANDIDATE),
        issuance_id=token, code_hash='synthetic', expires_at=now + timedelta(minutes=10),
        payload={}, at=now)
    return {'activated': activated}

@app.get('/_test/pending')
async def pending_tokens(email: str):
    services = app.state.services
    with services.candidates._session_factory() as session:
        return list(session.scalars(select(LoginIssuanceRow.id).where(
            LoginIssuanceRow.email_hash == services.auth.hash_email(email))))

@app.post('/_test/scopes')
async def scopes(email: str):
    auth = app.state.services.auth
    digest = auth.hash_email(email)
    row = auth._store.get_challenge(ChallengeScope(digest, LoginPurpose.LOGIN, AuthPlane.CANDIDATE))
    assert row is not None
    for plane in AuthPlane:
        for purpose in LoginPurpose:
            if plane == AuthPlane.CANDIDATE and purpose == LoginPurpose.LOGIN:
                continue
            auth._store.upsert_challenge(ChallengeScope(digest, purpose, plane),
                code_hash=row.code_hash, expires_at=row.expires_at, payload={}, at=row.created_at)
    return {'seeded': True}

@app.get('/_test/count')
async def count(email: str):
    services = app.state.services
    with services.candidates._session_factory() as session:
        rows = list(session.scalars(select(LoginChallengeRow.id).where(
            LoginChallengeRow.email_hash == services.auth.hash_email(email))))
    return {'count': len(rows)}

@app.post('/_test/arm')
async def arm():
    def stop(conn, cursor, statement, params, context, executemany):
        if statement.lower().startswith('delete from candidates'):
            os._exit(73)
    engine = app.state.services.candidates._session_factory.kw['bind']
    event.listen(engine, 'before_cursor_execute', stop)
    return {'armed': True}
'''


def main():
    checks = Smoke("atomic login erasure HTTP/interruption/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-login-atomic-"))
    print(f"Synthetic artifacts: {scratch}")
    (scratch / "gate_app.py").write_text(GATE_APP, encoding="utf-8")
    mailbox = scratch / "mailbox.jsonl"
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
        env.update({
            "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"),
            "DEE_CANDIDATES_DB_URL": url, "DEE_ENV": "local",
            "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
            "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
            "DEE_EMAIL_PROVIDER": "capture", "DEE_EMAIL_CAPTURE_PATH": str(mailbox),
            "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
            "DEE_VECTORSTORE_BACKEND": "memory",
            "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
            "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
            "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(scratch)]),
            "NO_PROXY": "127.0.0.1,localhost", "PGOPTIONS": pg_options,
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        @contextmanager
        def server():
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(
                    uvicorn_argv(port, target="gate_app:app"), env=env, cwd=scratch,
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                try:
                    with client(base, headers={"X-API-Key": ADMIN}) as admin:
                        assert wait_healthy(admin), "scratch app failed to start"
                        yield admin, proc
                finally:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=10)

        def require(response, status=200):
            assert response.status_code == status, (response.request.url.path, response.status_code)
            return response.json()

        def issue(http, email):
            result = require(http.post("/auth/candidate/signup", json={"email": email}), 202)
            return result, _code_for(mailbox, email)

        def verify(http, email, code):
            return require(http.post("/auth/candidate/verify", json={"email": email, "code": code}))

        if "--issuance" in sys.argv:
            for door in ("portal", "admin"):
                for plane in ("candidate", "org", "admin"):
                    email = f"{door}-{plane}@example.in"
                    with client(base) as person, client(base) as keeper:
                        with server() as (admin, _):
                            _, code = issue(person, email)
                            csrf = verify(person, email, code)["csrf_token"]
                            cid = require(person.get("/portal/me"))["candidate_id"]
                            other = f"keep-{door}-{plane}@example.in"
                            _, code = issue(keeper, other)
                            verify(keeper, other, code)
                            state = require(admin.post("/_test/start-send", params={"email": email, "plane": plane}))
                            checks.check(f"{door}/{plane}: send registered before erasure", state["reserved"])
                            old_code = _code_for(mailbox, email)
                            actor = person if door == "portal" else admin
                            path = "/portal/me" if door == "portal" else f"/candidates/{cid}"
                            require(actor.delete(path, headers={"X-CSRF-Token": csrf}))
                            result = require(admin.post("/_test/finish-send"))
                            checks.check(f"{door}/{plane}: cancelled send cannot activate or echo",
                                         result == {"activated": False, "has_code": False})
                            require(person.post(f"/auth/{plane}/verify", json={"email": email, "code": old_code}), 400)
                            checks.check(f"{door}/{plane}: stale code refused; reservation erased",
                                         require(admin.get("/_test/pending", params={"email": email})) == [])
                            require(keeper.get("/portal/me"))
                            checks.check(f"{door}/{plane}: unrelated session survives", True)
                        with server() as (admin, _):
                            require(admin.get(f"/candidates/{cid}"), 404)
                            require(person.get("/portal/me"), 401)
                            require(person.post(f"/auth/{plane}/login", json={"email": email}), 202)
                            code = _code_for(mailbox, email)
                            require(person.post(f"/auth/{plane}/verify", json={"email": email, "code": code}))
                            checks.check(f"{door}/{plane}: restart and fresh login succeed", True)

            # A worker dies after delivery and before activation. Its pending
            # token survives restart but cannot authorize after portal erasure.
            email = "interrupted@example.in"
            with client(base) as person:
                with server() as (admin, proc):
                    _, code = issue(person, email)
                    csrf = verify(person, email, code)["csrf_token"]
                    try:
                        admin.post("/_test/start-send", params={"email": email, "crash": "true"})
                        raise AssertionError("expected process exit during send")
                    except httpx.TransportError:
                        pass
                    checks.check("issuance worker exits before activation", proc.wait(timeout=15) == 74)
                with server() as (admin, _):
                    tokens = require(admin.get("/_test/pending", params={"email": email}))
                    checks.check("restart exposes one abandoned reservation", len(tokens) == 1)
                    require(person.delete("/portal/me", headers={"X-CSRF-Token": csrf}))
                    result = require(admin.post("/_test/replay", params={"email": email, "token": tokens[0]}))
                    checks.check("erasure cancels abandoned work durably", result == {"activated": False})
                    _, code = issue(person, email)
                    verify(person, email, code)
                    checks.check("fresh signup after interruption remains allowed", True)
            return checks.summary()

        for door in ("portal", "admin"):
            email, other = f"{door}@example.in", f"{door}-keeper@example.in"
            with client(base) as person, client(base) as keeper:
                with server() as (admin, proc):
                    cid = require(admin.post("/candidates", json={
                        "resume_text": f"Synthetic {door}\nEmail: {email}\nSKILLS\nPython\n",
                        "evaluate": False,
                    }))["candidate_id"]
                    known_response, code = issue(person, email)
                    csrf = verify(person, email, code)["csrf_token"]
                    unknown_response, code = issue(keeper, other)
                    verify(keeper, other, code)
                    keeper_id = require(keeper.get("/portal/me"))["candidate_id"]
                    checks.check(f"{door}: known/unknown signup share public response",
                                 known_response == unknown_response)
                    _, old_code = issue(person, email)
                    require(admin.post("/_test/scopes", params={"email": email}))
                    _, keep_code = issue(keeper, other)
                    require(admin.post("/_test/scopes", params={"email": other}))
                    require(admin.post("/_test/arm"))
                    path = "/portal/me" if door == "portal" else f"/candidates/{cid}"
                    actor = person if door == "portal" else admin
                    try:
                        actor.delete(path, headers={"X-CSRF-Token": csrf})
                        raise AssertionError("expected process exit before DELETE returned")
                    except httpx.TransportError:
                        pass
                    checks.check(f"{door}: process exits inside erasure", proc.wait(timeout=15) == 73)

                with server() as (admin, _):
                    data = require(person.get("/portal/me"))
                    checks.check(f"{door}: restart retains candidate/session/resume",
                                 data["candidate_id"] == cid and len(data["resumes"]) == 1)
                    checks.check(f"{door}: restart retains every challenge scope",
                                 require(admin.get("/_test/count", params={"email": email}))["count"] == 6)
                    csrf = verify(person, email, old_code)["csrf_token"]
                    checks.check(f"{door}: pre-interruption code still works", True)
                    # Other same-plane signup scope still exists after verification;
                    # replace it using the explicit scratch seed with a fresh real code.
                    _, doomed_code = issue(person, email)
                    require(admin.post("/_test/scopes", params={"email": email}))
                    actor = person if door == "portal" else admin
                    erased = require(actor.delete(path, headers={"X-CSRF-Token": csrf}))
                    checks.check(f"{door}: retry succeeds", erased == {
                        "candidate_id": cid, "deleted": True, "reports_deleted": 0})
                    require(person.get("/portal/me"), 401)
                    require(person.post("/auth/candidate/verify", json={"email": email, "code": doomed_code}), 400)
                    checks.check(f"{door}: session and old code are refused", True)
                    checks.check(f"{door}: all challenge scopes removed",
                                 require(admin.get("/_test/count", params={"email": email}))["count"] == 0)
                    checks.check(f"{door}: unrelated session/scopes survive",
                                 require(keeper.get("/portal/me"))["candidate_id"] == keeper_id
                                 and require(admin.get("/_test/count", params={"email": other}))["count"] == 6)

                with server() as (admin, _):
                    require(admin.get(f"/candidates/{cid}"), 404)
                    require(person.get("/portal/me"), 401)
                    checks.check(f"{door}: committed erasure survives restart", True)
                    verify(keeper, other, keep_code)
                    checks.check(f"{door}: unrelated code remains redeemable", True)
                    _, code = issue(person, email)
                    verify(person, email, code)
                    checks.check(f"{door}: fresh signup creates a new candidate",
                                 require(person.get("/portal/me"))["candidate_id"] != cid)

    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
