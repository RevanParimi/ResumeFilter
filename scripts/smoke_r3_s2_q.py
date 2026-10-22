"""Operator accounts, retention, metrics and curation on migrated scratch SQL.

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
import sys
import tempfile

from sqlalchemy import create_engine, select, text, update

from app.candidates.models import ResumeRow
from app.curation.models import CurationAliasRow, CurationObservationRow
from _smoke import Smoke, base_env, client, wait_healthy
from smoke_curation_input import export
from smoke_r1_s1_t3a_v1 import database

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-review-revision-admin"


def main():
    scratch = Path(tempfile.mkdtemp(prefix="r3-s2-q-http-"))
    print(f"Synthetic revision HTTP evidence: {scratch}", flush=True)
    checks = Smoke("R3-S2-Q combined operator HTTP/restart")
    mailbox = scratch / "mail.jsonl"
    codes = []
    emails = ["sprint-operator-a@example.com", "sprint-operator-b@example.com"]

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
            "DEE_RETENTION_SWEEP_ENABLED": "false",
            "VERITAS_SQL_SMOKE_FACTORY": "smoke_r3_s1_t2:create_smoke_app",
            "PGOPTIONS": pg_options, "NO_PROXY": "127.0.0.1,localhost",
            "PYTHONPATH": os.pathsep.join(str(p) for p in (ROOT / "src", ROOT / "scripts", ROOT)),
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        stop = scratch / "stop"

        @contextmanager
        def server():
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                def launch():
                    stop.unlink(missing_ok=True)
                    return subprocess.Popen([sys.executable, str(ROOT / "scripts/smoke_r4_s1_t1a.py"),
                        "--serve", str(port), str(stop)], env=env, cwd=scratch,
                        stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

                def shutdown():
                    stop.write_text("stop", encoding="utf-8")
                    try:
                        proc.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        proc.terminate(); proc.wait(timeout=10)
                        raise AssertionError("scratch app failed graceful shutdown")
                    assert proc.returncode == 0, "scratch app failed during lifespan"

                proc = launch()
                try:
                    with client(base, headers={"X-API-Key": ADMIN}) as admin:
                        assert wait_healthy(admin), "scratch app failed to start"
                        def restart():
                            nonlocal proc
                            shutdown()
                            proc = launch()
                            assert wait_healthy(admin), "restarted scratch app failed to start"
                        yield admin, restart
                finally:
                    shutdown()

        engine = create_engine(url, hide_parameters=True,
            connect_args={"options": pg_options} if pg_options else {})
        try:
            with ExitStack() as actors:
                a, b, stranger = [actors.enter_context(client(base)) for _ in range(3)]
                def public_ui():
                    page = stranger.get("/ui/")
                    for name in ("operator-accounts.js", "organization-admin.js"):
                        module = stranger.get(f"/ui/{name}")
                        checks.check(f"anonymous UI delivers its declared extracted module {name}",
                            page.status_code == module.status_code == 200
                            and f'<script src="./{name}"></script>' in page.text
                            and module.content == (ROOT / "frontend" / name).read_bytes()
                            and "javascript" in module.headers["content-type"]
                            and stranger.get("/ui/not-an-asset.txt").status_code == 404)
                with server() as (admin, restart_app):
                    public_ui()
                    with engine.connect() as conn:
                        checks.check("scratch schema is migrated to current head", conn.scalar(
                            text("SELECT version_num FROM alembic_version")) == "0029_candidate_login_binding")
                    operators = [require(admin.post("/admin/users", json={"email": email})) for email in emails]
                    login(a, emails[0]); login(b, emails[1])
                    candidates = [require(admin.post("/candidates", json={"evaluate": False,
                        "resume_text": f"Synthetic {i}\nEmail: revision-candidate-{i}@example.com\nSkills: Python SQL"}))["candidate_id"]
                        for i in range(2)]
                    first, second = candidates

                    retained = require(admin.post("/candidates", json={"evaluate": False,
                        "resume_text": "Synthetic retention\nEmail: retention@example.com\nSkills: Python"}))["candidate_id"]
                    with engine.begin() as conn:
                        conn.execute(update(ResumeRow).where(ResumeRow.candidate_id == retained).values(
                            created_at=datetime.now(timezone.utc) - timedelta(days=2000)))

                    def resume_ids():
                        with engine.connect() as conn:
                            return set(conn.scalars(select(ResumeRow.id)))

                    all_resumes = resume_ids()
                    preview = require(a.post("/admin/retention/sweep", json={}))
                    preview_resumes = next(r for r in preview["by_class"] if r["data_class"] == "resumes")
                    checks.check("empty HTTP sweep body previews expired resume without mutation",
                        preview["dry_run"] is True and preview_resumes["affected"] == 1 and resume_ids() == all_resumes)
                    checks.check("disabled apply refuses over HTTP without deleting rows",
                        require(a.post("/admin/retention/sweep", json={"dry_run": False}), 409)
                        == {"detail": "retention_sweep_disabled"} and resume_ids() == all_resumes)
                    csrf = a.headers.pop("X-CSRF-Token")
                    try:
                        checks.check("retention cookie plus machine key cannot bypass CSRF",
                            a.post("/admin/retention/sweep", json={}, headers={"X-API-Key": ADMIN}).status_code == 403
                            and resume_ids() == all_resumes)
                    finally:
                        a.headers["X-CSRF-Token"] = csrf

                    report = require(admin.post("/evaluate", json={"domain": "genai",
                        "resume_text": "Synthetic signal report\nSkills: Python SQL\nBuilt an API and tested its behavior."}))
                    require(a.post(f"/report/{report['id']}/outcome", json={"outcome": "verified_genuine"}))
                    quality = require(a.get("/admin/signal-quality"))
                    opted = require(a.get("/admin/signal-quality?include_operator_labels=true"))
                    ledger_quality = require(a.get("/admin/signal-quality?source=ledger"))
                    checks.check("signal HTTP report retains operator-label opt-in and insufficient-sample refusals",
                        quality["population"]["labels_usable"] == 0 and opted["population"]["labels_usable"] == 1
                        and opted["population"]["include_operator_labels"] is True
                        and len(opted["signals"]) == 12 and all(not s["sufficient"] for s in opted["signals"]))
                    checks.check("ledger signal source keeps hire labels and mismatch refusal; malformed queries refuse",
                        ledger_quality["population"]["label_kind"] == "hire"
                        and next(s for s in ledger_quality["signals"] if s["signal"] == "fabrication_risk.score")["reason"] == "label_kind_mismatch"
                        and a.get("/admin/signal-quality?source=unknown").status_code == 422
                        and a.get("/admin/signal-quality?include_operator_labels=invalid").status_code == 422)
                    metrics = a.get("/metrics")
                    checks.check("metrics HTTP response retains Prometheus media type and omits source identities",
                        metrics.status_code == 200 and metrics.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
                        and "veritas_http_requests_total" in metrics.text
                        and all(secret not in metrics.text for secret in (*emails, *candidates, retained, report["id"])))

                    org_a = require(a.post("/ledger/orgs", json={"name": "Combined HTTP agency A"}))
                    org_b = require(b.post("/ledger/orgs", json={"name": "Combined HTTP agency B"}))
                    oid = org_a["org"]["id"]
                    checks.check("operator-created org and users use server rows", len(require(a.get("/ledger/orgs"))) == 2
                        and {u["id"] for u in require(b.get("/admin/users"))} == {u["id"] for u in operators})
                    csrf = a.headers.pop("X-CSRF-Token")
                    try:
                        checks.check("org and user changes require session CSRF",
                            a.post(f"/ledger/orgs/{oid}/reliability", json={"weight": 99}).status_code == 403
                            and a.post("/admin/users", json={"email": "refused@example.com"}).status_code == 403)
                    finally: a.headers["X-CSRF-Token"] = csrf
                    require(a.post(f"/ledger/orgs/{oid}/reliability", json={"weight": 1.75}))
                    rotated = require(a.post(f"/ledger/orgs/{oid}/api-key"))["api_key"]
                    checks.check("actual org rotation revokes old credential and preserves second org",
                        stranger.get("/screening/batches", headers={"X-Org-Key": org_a["api_key"]}).status_code == 401
                        and stranger.get("/screening/batches", headers={"X-Org-Key": rotated}).status_code == 200
                        and stranger.get("/screening/batches", headers={"X-Org-Key": org_b["api_key"]}).status_code == 200)

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

                    org = org_b
                    key = require(admin.post(f"/candidates/{second}/auth-key"))["access_key"]
                    body = dict(norm_key=old["norm_key"], action="ignore", expected_revision=old["review_revision"])
                    for label, headers in (("anonymous", {}), ("organization", {"X-Org-Key": org["api_key"]}),
                                           ("candidate", {"X-Candidate-Key": key})):
                        checks.check(label + " cannot read or decide shared curation", stranger.get(
                            "/curation/skills/unmapped", headers=headers).status_code == 401 and stranger.post(
                            "/curation/skills/resolve", json=body, headers=headers).status_code == 401)
                    for label, headers in (("anonymous", {}), ("organization", {"X-Org-Key": org_b["api_key"]}),
                                           ("candidate", {"X-Candidate-Key": key})):
                        checks.check(label + " cannot inspect/mutate operator surfaces",
                            all(stranger.get(path, headers=headers).status_code == 401
                                for path in ("/ledger/orgs", "/admin/users", "/metrics", "/admin/signal-quality"))
                            and stranger.post("/admin/retention/sweep", json={}, headers=headers).status_code == 401
                            and stranger.post(f"/ledger/orgs/{oid}/reliability", json={"weight": 99}, headers=headers).status_code == 401
                            and stranger.delete(f"/admin/users/{operators[1]['id']}", headers=headers).status_code == 401)
                    checks.check("refused requests leave org weight and accounts unchanged",
                        next(o for o in require(a.get("/ledger/orgs")) if o["id"] == oid)["reliability_weight"] == 1.75
                        and len(require(a.get("/admin/users"))) == 2)
                    if "--browser" in sys.argv:
                        import asyncio
                        from check_ui_operator_browser import run_browser
                        asyncio.run(run_browser(base, scratch, admin, checks, restart_app))
                    ingest(second, "Restart review raw")
                    restart, = queue()

                env["DEE_RETENTION_SWEEP_ENABLED"] = "true"
                with server() as (admin, restart_app):
                    public_ui()
                    before_apply = resume_ids()
                    applied = require(b.post("/admin/retention/sweep", json={"dry_run": False}))
                    checks.check("enabled sweep after graceful restart deletes exactly previewed expired resumes",
                        applied["dry_run"] is False
                        and next(r for r in applied["by_class"] if r["data_class"] == "resumes") == preview_resumes
                        and len(before_apply - resume_ids()) == 1)
                    with engine.connect() as conn:
                        checks.check("retention preserves the active candidate resume and clears the expired one",
                            not list(conn.scalars(select(ResumeRow.id).where(ResumeRow.candidate_id == retained)))
                            and bool(list(conn.scalars(select(ResumeRow.id).where(ResumeRow.candidate_id == second)))))
                    checks.check("operator label and signal refusal survive graceful restart",
                        require(b.get("/admin/signal-quality?include_operator_labels=true"))["population"] == opted["population"])
                    checks.check("queue revision survives real app restart", queue(b) == [restart])
                    checks.check("combined restart preserves sessions/accounts/org settings and keys",
                        len(require(b.get("/admin/users"))) == 2
                        and next(o for o in require(b.get("/ledger/orgs")) if o["id"] == oid)["reliability_weight"] == 1.75
                        and stranger.get("/screening/batches", headers={"X-Org-Key": rotated}).status_code == 200)

                    signal = require(admin.post(f"/candidates/{second}/sources/linkedin",
                        json=export(["Approved revision alias", "Approved revision tool"])))
                    checks.check("restart reloads persisted map/create overlay",
                        [s["canonical"] for s in signal["skills"]] == ["python", "revision_tool"])
                    decide(b, restart)
                    checks.check("persisted decisions and final empty queue agree", queue(a) == []
                        and decide(a, old, status=404) == {"detail": "term not found"})
                    with engine.connect() as conn:
                        aliases = conn.execute(select(CurationAliasRow.alias, CurationAliasRow.admin_user_id)).all()
                        expected = {("Approved revision alias", operators[1]["id"]),
                                    ("Approved revision tool", operators[0]["id"])}
                        extras = {alias for alias, _ in aliases if alias not in {name for name, _ in expected}}
                        checks.check("only explicit successful vocabulary persisted", expected <= set(aliases)
                            and extras == ({"Combined approved alias", "Combined approved tool"} if "--browser" in sys.argv else set()))
                        checks.check("no remaining raw observations", conn.execute(select(CurationObservationRow.id)).all() == [])
                    require(b.delete(f"/ledger/orgs/{oid}"))
                    checks.check("offboarding revokes only target org after integrated restart",
                        stranger.get("/screening/batches", headers={"X-Org-Key": rotated}).status_code == 401
                        and stranger.get("/screening/batches", headers={"X-Org-Key": org_b["api_key"]}).status_code == 200
                        and {o["id"] for o in require(b.get("/ledger/orgs"))} == {org_b["org"]["id"]})
                    require(b.delete(f"/admin/users/{operators[0]['id']}"))
                    checks.check("revoked operator cannot reuse revision and other operator remains",
                        all(a.get(p).status_code == 401 for p in ("/curation/skills/unmapped", "/ledger/orgs", "/admin/users", "/metrics", "/admin/signal-quality"))
                        and a.post("/admin/retention/sweep", json={}).status_code == 401
                        and all(b.get(p).status_code == 200 for p in ("/curation/skills/unmapped", "/ledger/orgs", "/admin/users", "/metrics", "/admin/signal-quality")))
            logged = (scratch / "server.log").read_text(encoding="utf-8")
            checks.check("HTTP logs omit captured codes and operator emails", all(value not in logged for value in [*emails, *codes]))
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
