"""Guarded curation with two captured operators, migrated scratch SQL/restart.

SQLite by default; --postgres needs disposable DEE_TEST_DB_URL. Uses existing
fake-model/captured-email composition. No working data or live providers.
"""
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, select, text, update

from app.curation.models import CurationAliasRow, CurationObservationRow
from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_curation_input import export
from smoke_r1_s1_t3a_v1 import database

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-review-revision-admin"


def main():
    scratch = Path(tempfile.mkdtemp(prefix="r3-s2-t3a-http-"))
    print(f"Synthetic revision HTTP evidence: {scratch}", flush=True)
    checks = Smoke("R3-S2-T3A guarded review HTTP/restart")
    mailbox = scratch / "mail.jsonl"
    codes = []
    emails = ["revision-operator-a@example.com", "revision-operator-b@example.com"]

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    def login(actor, email):
        require(actor.post("/auth/admin/login", json={"email": email}), 202)
        messages = [json.loads(line) for line in mailbox.read_text(encoding="utf-8").splitlines()]
        msg = next(m for m in reversed(messages) if m["to"] == email)
        code = re.search(r"\b(\d{6})\b", msg["body"])[1]
        codes.append(code)
        verified = require(actor.post("/auth/admin/verify", json={"email": email, "code": code}))
        actor.headers["X-CSRF-Token"] = verified["csrf_token"]

    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
        env.update({
            "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_CANDIDATES_DB_URL": url,
            "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
            "DEE_LLM_MAX_RETRIES": "0", "DEE_GITHUB_TOKEN": "", "DEE_DB_MIGRATE_ON_BOOT": "true",
            "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_EMAIL_PROVIDER": "capture",
            "DEE_EMAIL_CAPTURE_PATH": str(mailbox), "DEE_VECTORSTORE_BACKEND": "memory",
            "DEE_SPEECH_PROVIDER": "local", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
            "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_VERIF_OTP_DEBUG_ECHO": "false",
            "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
            "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
            "PGOPTIONS": pg_options, "NO_PROXY": "127.0.0.1,localhost",
            "PYTHONPATH": os.pathsep.join(str(p) for p in (ROOT / "src", ROOT / "scripts", ROOT)),
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        @contextmanager
        def server():
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(uvicorn_argv(port, target="smoke_r3_s1_t2:create_smoke_app") + ["--factory"],
                    env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    with client(base, headers={"X-API-Key": ADMIN}) as admin:
                        assert wait_healthy(admin), "scratch app failed to start"
                        yield admin
                finally:
                    proc.terminate()
                    try: proc.wait(timeout=15)
                    except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=10)

        engine = create_engine(url, hide_parameters=True,
            connect_args={"options": pg_options} if pg_options else {})
        try:
            with ExitStack() as actors:
                a, b, stranger = [actors.enter_context(client(base)) for _ in range(3)]
                with server() as admin:
                    with engine.connect() as conn:
                        checks.check("scratch schema is migrated to current head", conn.scalar(
                            text("SELECT version_num FROM alembic_version")) == "0029_candidate_login_binding")
                    operators = [require(admin.post("/admin/users", json={"email": email})) for email in emails]
                    login(a, emails[0]); login(b, emails[1])
                    candidates = [require(admin.post("/candidates", json={"evaluate": False,
                        "resume_text": f"Synthetic {i}\nEmail: revision-candidate-{i}@example.com\nSkills: Python SQL"}))["candidate_id"]
                        for i in range(2)]
                    first, second = candidates

                    def ingest(cid, *names):
                        return require(admin.post(f"/candidates/{cid}/sources/linkedin", json=export(list(names))))

                    def queue(actor=a):
                        return require(actor.get("/curation/skills/unmapped"))["terms"]

                    def decide(actor, snapshot, action="ignore", status=200, **vocabulary):
                        return require(actor.post("/curation/skills/resolve", json={
                            "norm_key": snapshot["norm_key"], "expected_revision": snapshot["review_revision"],
                            "action": action, **vocabulary}), status)

                    ingest(first, "Repeated review raw")
                    old, = queue(a)
                    checks.check("two operators read one stable exact revision", queue(b) == [old])
                    for extra in ({}, {"expected_revision": None}):
                        refused = a.post("/curation/skills/resolve", json={"norm_key": old["norm_key"], "action": "ignore", **extra})
                        checks.check("missing/null HTTP revision refuses without mutation", refused.status_code == 422 and queue(a) == [old])
                    csrf = a.headers.pop("X-CSRF-Token")
                    try:
                        checks.check("guarded write still requires session CSRF", decide(a, old, status=403)["detail"])
                    finally:
                        a.headers["X-CSRF-Token"] = csrf
                    checks.check("CSRF refusal preserves exact snapshot", queue() == [old])
                    decide(a, old)
                    checks.check("ignored raw disappears on actual reload", queue(a) == queue(b) == [])
                    ingest(first, "Repeated review raw")
                    fresh, = queue()
                    checks.check("new input under ignored key gets a new revision", fresh["review_revision"] != old["review_revision"])
                    error = decide(b, old, "map", 409, alias="Stale approval", canonical="python", category="language")
                    checks.check("stale second reviewer cannot approve fresh submission", error == {
                        "detail": "review snapshot changed; refresh before deciding"} and queue() == [fresh])
                    receipt = decide(b, fresh, "map", alias="Approved revision alias", canonical="python", category="language")
                    checks.check("fresh approval has real operator identity and raw-free receipt",
                        receipt["admin_user_id"] == operators[1]["id"] and set(receipt) == {
                            "action", "alias", "canonical", "category", "decided_at", "admin_user_id"})
                    checks.check("accepted raw disappears on actual reload", queue() == [])
                    checks.check("duplicate review is explicit absence", decide(a, fresh, status=404) == {"detail": "term not found"})

                    ingest(first, "Create review raw")
                    created, = queue()
                    decide(a, created, "create", alias="Approved revision tool", canonical="revision_tool", category="data")
                    normalized = ingest(second, "Approved revision alias", "Approved revision tool", "Python")["skills"]
                    checks.check("approved map/create refresh current process without changing static taxonomy",
                        [s["canonical"] for s in normalized] == ["python", "revision_tool", "python"])
                    ingest(first, "Conflict review raw")
                    conflict, = queue()
                    checks.check("alias conflict preserves raw and distinguishes stale revision",
                        decide(a, conflict, "map", 409, alias="Approved revision alias", canonical="python", category="language")
                        == {"detail": "approved alias already exists"} and queue() == [conflict])
                    decide(a, conflict)

                    ingest(first, "Erasure review raw"); ingest(second, "Erasure review raw")
                    erased, = queue()
                    require(admin.delete(f"/candidates/{first}"))
                    survivor, = queue()
                    checks.check("partial erasure changes revision and preserves surviving observation",
                        survivor["occurrences"] == 1 and survivor["review_revision"] != erased["review_revision"]
                        and decide(b, erased, status=409)["detail"] == "review snapshot changed; refresh before deciding"
                        and queue() == [survivor])
                    decide(b, survivor)
                    ingest(second, "Expiry review raw")
                    expired, = queue()
                    with engine.begin() as conn:
                        conn.execute(update(CurationObservationRow).values(
                            created_at=datetime.now(timezone.utc)-timedelta(days=31)))
                    checks.check("expired snapshot cannot authorize promotion",
                        decide(a, expired, "map", 404, alias="Expired approval", canonical="python", category="language")
                        == {"detail": "term not found"} and queue() == [])

                    org = require(admin.post("/ledger/orgs", json={"name": "Revision tenant"}))
                    key = require(admin.post(f"/candidates/{second}/auth-key"))["access_key"]
                    body = dict(norm_key=old["norm_key"], action="ignore", expected_revision=old["review_revision"])
                    for label, headers in (("anonymous", {}), ("organization", {"X-Org-Key": org["api_key"]}),
                                           ("candidate", {"X-Candidate-Key": key})):
                        checks.check(label + " cannot read or decide shared curation", stranger.get(
                            "/curation/skills/unmapped", headers=headers).status_code == 401 and stranger.post(
                            "/curation/skills/resolve", json=body, headers=headers).status_code == 401)
                    ingest(second, "Restart review raw")
                    restart, = queue()

                with server() as admin:
                    checks.check("queue revision survives real app restart", queue(b) == [restart])
                    signal = require(admin.post(f"/candidates/{second}/sources/linkedin",
                        json=export(["Approved revision alias", "Approved revision tool"])))
                    checks.check("restart reloads persisted map/create overlay",
                        [s["canonical"] for s in signal["skills"]] == ["python", "revision_tool"])
                    decide(b, restart)
                    checks.check("persisted decisions and final empty queue agree", queue(a) == []
                        and decide(a, old, status=404) == {"detail": "term not found"})
                    with engine.connect() as conn:
                        aliases = conn.execute(select(CurationAliasRow.alias, CurationAliasRow.admin_user_id)).all()
                        checks.check("only explicit successful vocabulary persisted", set(aliases) == {
                            ("Approved revision alias", operators[1]["id"]), ("Approved revision tool", operators[0]["id"])})
                        checks.check("no remaining raw observations", conn.execute(select(CurationObservationRow.id)).all() == [])
                    require(admin.delete(f"/admin/users/{operators[0]['id']}"))
                    checks.check("revoked operator cannot reuse revision and other operator remains",
                        a.get("/curation/skills/unmapped").status_code == 401 and b.get("/curation/skills/unmapped").status_code == 200)
            logged = (scratch / "server.log").read_text(encoding="utf-8")
            checks.check("HTTP logs omit captured codes and operator emails", all(value not in logged for value in [*emails, *codes]))
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
