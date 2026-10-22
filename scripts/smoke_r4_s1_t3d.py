"""Screening HTTP contract and persisted employer workflow on scratch SQL.

Uses the existing fake-provider production SQL app and graceful restart loop.
The reused UI contract is HTTP simulation, not actual browser execution.
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

import check_ui_screening_contract as contract
from _smoke import Smoke, base_env, client, wait_healthy
from smoke_r4_s1_t1a import serve
from smoke_s82 import _code_for


ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-screening-router-admin"


def main():
    scratch = Path(tempfile.mkdtemp(prefix="r4-s1-t3d-"))
    print(f"Synthetic screening HTTP evidence: {scratch}", flush=True)
    checks = Smoke("R4-S1-T3D screening HTTP and graceful restart")
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
        "DEE_VERIF_OTP_DEBUG_ECHO": "false", "DEE_SESSION_COOKIE_SECURE": "false",
        "DEE_SESSION_COOKIE_SAMESITE": "lax", "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "DEE_CORS_ALLOWED_ORIGINS": json.dumps([contract.UI_ORIGIN]),
        "DEE_SCREENING_MAX_ITEMS_PER_CALL": "1",
        "VERITAS_SQL_SMOKE_EVENTS": str(events),
        "VERITAS_SQL_SMOKE_FACTORY": "smoke_r4_s1_t1a:create_smoke_app",
        "PYTHONPATH": os.pathsep.join(str(path) for path in (ROOT / "src", ROOT / "scripts", ROOT)),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    contract.BASE = base

    @contextmanager
    def server():
        stop.unlink(missing_ok=True)
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", str(port), str(stop)],
                env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                with client(base) as health:
                    assert wait_healthy(health), "scratch screening app failed to start"
                yield
            finally:
                stop.write_text("stop", encoding="utf-8")
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    proc.wait(timeout=10)
                    raise AssertionError("scratch screening app failed graceful shutdown")
                assert proc.returncode == 0, "scratch screening app failed during lifespan"

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    def login(http, email, name):
        require(http.post("/auth/org/signup", json={"email": email, "organization_name": name}), 202)
        session = require(http.post("/auth/org/verify", json={"email": email, "code": _code_for(mailbox, email)}))
        http.headers["X-CSRF-Token"] = session["csrf_token"]
        return session

    def public_ui():
        with client(base) as page:
            entry = page.get("/ui/")
            for name in ("evaluation-report.js", "screening.js"):
                module = page.get(f"/ui/{name}")
                checks.check(f"anonymous UI delivers its declared {name} module",
                    entry.status_code == module.status_code == 200
                    and f'<script src="./{name}"></script>' in entry.text
                    and module.content == (ROOT / "frontend" / name).read_bytes()
                    and "javascript" in module.headers["content-type"]
                    and page.get("/ui/not-an-asset.txt").status_code == 404)

    with client(base, headers={"X-API-Key": ADMIN}) as control, client(base) as actor, client(base) as other:
        with server():
            public_ui()
            contract.run_checks(mailbox)
            checks.check("reused UI HTTP contract passes", contract.S.summary() == 0)
            login(actor, "screening-router-a@example.in", "Screening Router A")
            login(other, "screening-router-b@example.in", "Screening Router B")
            text = contract._resume("Synthetic Screening Router", "screening-intake@example.in")
            uploaded = require(actor.post("/screening/candidates", json={"resume_text": text}))
            rid, cid = uploaded["report"]["id"], uploaded["candidate_id"]
            report_path = f"/screening/reports/{rid}"
            checks.check("single intake keeps advisory report and scoped candidate reads", uploaded["report"]["advisory"]
                and uploaded["report"]["human_review_required"]
                and [row["id"] for row in require(actor.get(f"/screening/candidates/{cid}/reports"))] == [rid]
                and require(other.get(f"/screening/candidates/{cid}/reports")) == [])
            require(control.post(f"/report/{rid}/outcome", json={"outcome": "inconclusive", "notes": "Internal operator note"}))
            checks.check("operator note remains private", require(actor.get(report_path + "/outcomes"))["outcomes"] == [])
            require(actor.post(report_path + "/outcome", json={"outcome": "candidate_clarified", "notes": "Named human reviewer"}))
            outcomes = require(actor.get(report_path + "/outcomes"))["outcomes"]
            checks.check("cookie reviewer provenance survives write/read", len(outcomes) == 1 and bool(outcomes[0]["recorded_by_org_user_id"])
                and outcomes[0]["recorded_by"] == "organization")
            checks.check("other tenant report and outcome doors remain absent", all(other.get(report_path + suffix).status_code == 404 for suffix in ("", "/outcomes"))
                and other.post(report_path + "/outcome", json={"outcome": "inconclusive"}).status_code == 404)
            created = require(actor.post("/screening/batches", json={"name": "Restarted screening", "items": [
                {"resume_text": text}, {"resume_text": text + "\nUpdated availability."}]}))
            bid, path = created["id"], f"/screening/batches/{created['id']}"
            checks.check("batch registration records the same named human", created["created_by_org_user_id"] == outcomes[0]["recorded_by_org_user_id"]
                and created["counts"]["pending"] == 2)
            first = require(actor.post(path + "/process"))
            checks.check("processing respects one-item configured bound", first["processed"] == 1 and first["remaining"] == 1)
            require(actor.post(path + "/process"))
            checks.check("successful items are not replayed by retry", require(actor.post(path + "/retry")) == {"batch_id": bid, "requeued": 0, "skipped": 0})
            saved = {suffix: require(actor.get(path + suffix)) for suffix in ("", "/queue", "/summary")}
            saved_report = require(actor.get(report_path))
            checks.check("completed queue and summary remain advisory", saved[""]["counts"]["done"] == 2
                and saved["/summary"]["n_screened"] == 2 and all(row["advisory"] and row["human_review_required"] for row in saved["/queue"]["rows"]))
        with server():
            public_ui()
            checks.check("cookie session and exact batch queue summary survive restart", all(require(actor.get(path + suffix)) == body for suffix, body in saved.items()))
            checks.check("report and employer judgments survive restart exactly", require(actor.get(report_path)) == saved_report
                and require(actor.get(report_path + "/outcomes"))["outcomes"] == outcomes)
            checks.check("tenant isolation survives restart on all batch doors", all(other.get(path + suffix).status_code == 404 for suffix in ("", "/queue", "/summary"))
                and all(other.post(path + suffix).status_code == 404 for suffix in ("/process", "/retry")) and other.delete(path).status_code == 404)
            checks.check("malformed cursors still return 422", all(actor.get(target, params={"cursor": "!!!"}).status_code == 422 for target in ("/screening/batches", path + "/queue")))
            csrf = actor.headers.pop("X-CSRF-Token")
            checks.check("persisted cookie still requires CSRF for writes", actor.delete(path).status_code == 403
                and actor.post(path + "/process").status_code == 403)
            actor.headers["X-CSRF-Token"] = csrf
            checks.check("owner can delete batch after restart", require(actor.delete(path)) == {"batch_id": bid, "deleted": True}
                and actor.get(path).status_code == 404 and actor.get(report_path).status_code == 200)
    lifecycle = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    checks.check("both migrated starts share SQL and shut down gracefully", sum(row["event"] == "started" and row["revision"] == "0029_candidate_login_binding" and row["one_factory"] for row in lifecycle) == 2
        and sum(row["event"] == "disposed" for row in lifecycle) == 2
        and sum(row["event"] == "stopped" and row["detached"] for row in lifecycle) == 2)
    return checks.summary()


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        asyncio.run(serve(int(sys.argv[2]), Path(sys.argv[3])))
    else:
        raise SystemExit(main())
