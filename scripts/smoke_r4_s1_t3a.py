"""Authentication extraction: migrated HTTP, all planes, ownership and restart.

Uses captured mail and the existing fake-provider SQL app/graceful server loop.
No external mail/provider calls, working storage or existing demo restart.
"""

import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from _smoke import Smoke, base_env, client, wait_healthy
from smoke_s82 import _code_for as latest_code
from smoke_r4_s1_t1a import serve


ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-router-admin"


def main():
    checks = Smoke("R4-S1-T3A auth/session extraction HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r4-s1-t3a-"))
    print(f"Synthetic auth evidence: {scratch}", flush=True)
    stop, events, mailbox = scratch / "stop", scratch / "lifecycle.jsonl", scratch / "mail.jsonl"
    env = {key: value for key, value in base_env().items() if not key.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_ENV": "local",
        "DEE_CANDIDATES_DB_URL": "sqlite:///" + (scratch / "app.db").as_posix(),
        "DEE_DB_MIGRATE_ON_BOOT": "true", "DEE_API_AUTH_KEY": ADMIN,
        "DEE_OPENROUTER_API_KEY": "", "DEE_GITHUB_TOKEN": "",
        "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_SPEECH_PROVIDER": "local",
        "DEE_EMAIL_PROVIDER": "capture", "DEE_EMAIL_CAPTURE_PATH": str(mailbox),
        "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
        "DEE_VERIF_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_COOLDOWN_SECONDS": "0",
        "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
        "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "VERITAS_SQL_SMOKE_EVENTS": str(events),
        "VERITAS_SQL_SMOKE_FACTORY": "smoke_r4_s1_t1a:create_smoke_app",
        "PYTHONPATH": os.pathsep.join(str(path) for path in (ROOT / "src", ROOT / "scripts", ROOT)),
        "NO_PROXY": "127.0.0.1,localhost",
    })
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
            require(control.post("/admin/users", json={"email": "router-admin@example.in", "label": "Synthetic router admin"}))
            admin_csrf = login(operator, "admin", "router-admin@example.in")
            org_csrf = login(org, "org", "router-org@example.in", organization="Synthetic Router A")
            other_csrf = login(other_org, "org", "router-other@example.in", organization="Synthetic Router B")
            candidate_csrf = login(candidate, "candidate", "router-candidate@example.in")
            sibling_csrf = login(sibling, "candidate", "router-candidate@example.in")
            who = [require(http.get("/auth/me")) for http in (operator, org, other_org, candidate)]
            checks.check("three planes resolve their own sessions", [row["kind"] for row in who] == ["admin", "org", "org", "candidate"])
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
        with server():
            checks.check("all planes and tenant data survive graceful restart", operator.get("/admin/users").status_code == 200
                and org.get(f"/jobs/{job['id']}").status_code == 200 and sibling.get("/portal/me").status_code == 200
                and other_org.get(f"/jobs/{job['id']}").status_code == 404)
            for http, token in ((operator, admin_csrf), (org, org_csrf), (other_org, other_csrf), (sibling, sibling_csrf)):
                http.headers["X-CSRF-Token"] = token
                assert require(http.post("/auth/logout")) == {"logged_out": True}
                assert http.get("/auth/me").status_code == 401
            checks.check("logout clears all four sessions across planes", True)
        rows = [json.loads(line) for line in events.read_text().splitlines()]
        checks.check("two migrated lifespans close and detach owned SQL", sum(row["event"] == "stopped" for row in rows) == 2
            and sum(row["event"] == "disposed" for row in rows) == 2
            and all(row["revision"] == "0029_candidate_login_binding" for row in rows if row["event"] == "started"))
    return checks.summary()


if __name__ == "__main__":
    if "--serve" in sys.argv:
        asyncio.run(serve(int(sys.argv[2]), Path(sys.argv[3])))
    else:
        raise SystemExit(main())
