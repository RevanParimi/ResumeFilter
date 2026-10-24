"""Screening HTTP contract and persisted employer workflow on scratch SQL.

Uses the existing fake-provider production SQL app and graceful restart loop.
The reused UI contract is HTTP simulation, not actual browser execution.
--leases adds R4-S2-T1A's two-app-process slow-provider scheduling journey.
--outcomes adds R4-S2-T1B1's terminal refusal/erasure journey to --leases.
--postgres uses an explicitly disposable DEE_TEST_DB_URL and an owned schema.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import check_ui_screening_contract as contract
from _smoke import Smoke, base_env, client, wait_healthy
from smoke_r4_s1_t1a import create_smoke_app as sql_app, serve
from smoke_r1_s1_t3a_v1 import database
from smoke_s82 import _code_for


ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-screening-router-admin"


def create_smoke_app():
    """Pause one synthetic evaluation across two real app processes."""
    app = sql_app()
    original = app.router.lifespan_context
    scratch = Path(os.environ["VERITAS_SQL_SMOKE_EVENTS"]).parent

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            evaluate = app.state.engine.evaluate
            svc = app.state.services.screening
            now, complete = svc._now, svc._store.complete

            def controlled_now():
                # Deterministic expiry for competing OS processes, not a
                # measured wall-clock timeout or an active-expiry fence test.
                offset = svc._settings.screening_claim_timeout_seconds + 1 if (scratch / "outcome-advanced").exists() else 0
                return now() + timedelta(seconds=offset)

            def controlled_complete(item_id, **kwargs):
                armed = scratch / "outcome-mode"
                if armed.exists():
                    mode = armed.read_text(encoding="utf-8")
                    try:
                        (scratch / f"outcome-claimed-{mode}").open("x").close()
                    except FileExistsError:
                        pass
                    else:
                        entered = scratch / f"outcome-entered-{mode}.json"
                        temporary = entered.with_suffix(".tmp")
                        temporary.write_text(json.dumps({
                            "candidate_id": kwargs["candidate_id"], "report_id": kwargs["report_id"]}), encoding="utf-8")
                        temporary.replace(entered)
                        deadline = time.monotonic() + 30
                        while not (scratch / f"outcome-release-{mode}").exists():
                            assert time.monotonic() < deadline, "synthetic terminal gate timed out"
                            time.sleep(.05)
                return complete(item_id, **kwargs)

            svc._now = controlled_now
            svc._store.complete = controlled_complete

            async def controlled(**kwargs):
                if "R4-S2-T1A slow fake gate" in (kwargs.get("resume_text") or ""):
                    try:
                        (scratch / "lease-claimed").open("x").close()
                    except FileExistsError:
                        pass
                    else:
                        (scratch / "lease-entered").write_text("ready", encoding="utf-8")
                        deadline = time.monotonic() + 30
                        while not (scratch / "lease-release").exists():
                            assert time.monotonic() < deadline, "synthetic provider gate timed out"
                            await asyncio.sleep(.05)
                return await evaluate(**kwargs)

            app.state.engine.evaluate = controlled
            yield

    app.router.lifespan_context = lifespan
    return app


def run(scratch, url, pg_options):
    terminal_outcomes = "--outcomes" in sys.argv
    leases = "--leases" in sys.argv or terminal_outcomes
    cap = 2 if leases else 1
    print(f"Synthetic screening HTTP evidence: {scratch}", flush=True)
    checks = Smoke("R4-S2-T1B1 terminal outcomes / two workers / graceful restart" if terminal_outcomes
                   else "R4-S2-T1A two-worker leases / screening HTTP / graceful restart" if leases
                   else "R4-S1-T3D screening HTTP and graceful restart")
    stop, events, mailbox = scratch / "stop", scratch / "lifecycle.jsonl", scratch / "mail.jsonl"
    env = {key: value for key, value in base_env().items() if not key.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_ENV": "local",
        "DEE_CANDIDATES_DB_URL": url, "PGOPTIONS": pg_options,
        "DEE_DB_MIGRATE_ON_BOOT": "true", "DEE_API_AUTH_KEY": ADMIN,
        "DEE_OPENROUTER_API_KEY": "", "DEE_GITHUB_TOKEN": "",
        "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_SPEECH_PROVIDER": "local",
        "DEE_EMAIL_PROVIDER": "capture", "DEE_EMAIL_CAPTURE_PATH": str(mailbox),
        "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
        "DEE_VERIF_OTP_DEBUG_ECHO": "false", "DEE_SESSION_COOKIE_SECURE": "false",
        "DEE_SESSION_COOKIE_SAMESITE": "lax", "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "DEE_CORS_ALLOWED_ORIGINS": json.dumps([contract.UI_ORIGIN]),
        "DEE_SCREENING_MAX_ITEMS_PER_CALL": str(cap),
        "VERITAS_SQL_SMOKE_EVENTS": str(events),
        "VERITAS_SQL_SMOKE_FACTORY": "smoke_r4_s1_t3d:create_smoke_app" if leases else "smoke_r4_s1_t1a:create_smoke_app",
        "PYTHONPATH": os.pathsep.join(str(path) for path in (ROOT / "src", ROOT / "scripts", ROOT)),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    contract.BASE = base

    @contextmanager
    def server(server_port=port, stop_path=stop):
        stop_path.unlink(missing_ok=True)
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", str(server_port), str(stop_path)],
                env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                server_base = f"http://127.0.0.1:{server_port}"
                with client(server_base) as health:
                    assert wait_healthy(health), "scratch screening app failed to start"
                yield server_base
            finally:
                stop_path.write_text("stop", encoding="utf-8")
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
                {"resume_text": text + f"\nUpdated availability {i}."} for i in range(cap + 1)]}))
            bid, path = created["id"], f"/screening/batches/{created['id']}"
            checks.check("batch registration records the same named human", created["created_by_org_user_id"] == outcomes[0]["recorded_by_org_user_id"]
                and created["counts"]["pending"] == cap + 1)
            first = require(actor.post(path + "/process"))
            checks.check("processing respects configured item bound", first["processed"] == cap and first["remaining"] == 1)
            require(actor.post(path + "/process"))
            checks.check("successful items are not replayed by retry", require(actor.post(path + "/retry")) == {"batch_id": bid, "requeued": 0, "skipped": 0})
            saved = {suffix: require(actor.get(path + suffix)) for suffix in ("", "/queue", "/summary")}
            saved_report = require(actor.get(report_path))
            checks.check("completed queue and summary remain advisory", saved[""]["counts"]["done"] == cap + 1
                and saved["/summary"]["n_screened"] == cap + 1 and all(row["advisory"] and row["human_review_required"] for row in saved["/queue"]["rows"]))
            if leases:
                org = require(control.post("/ledger/orgs", json={"name": "Two process lease worker"}))
                headers = {"X-Org-Key": org["api_key"]}
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0)); worker_port = sock.getsockname()[1]
                with server(worker_port, scratch / "stop-worker") as worker_base:
                    with client(base, headers=headers) as worker_a, client(worker_base, headers=headers) as worker_b:
                        batch = require(worker_b.post("/screening/batches", json={"name": "Concurrent lease intake", "items": [
                            {"resume_text": contract._resume(f"Lease candidate {i}", f"lease-worker-{i}@example.com")
                             + "\nR4-S2-T1A slow fake gate"} for i in range(3)]}))
                        lease_path = "/screening/batches/" + batch["id"]
                        with ThreadPoolExecutor(max_workers=1) as executor:
                            pending = executor.submit(worker_a.post, lease_path + "/process")
                            try:
                                deadline = time.monotonic() + 15
                                while not (scratch / "lease-entered").exists():
                                    assert time.monotonic() < deadline, "first worker never reached provider gate"
                                    time.sleep(.05)
                                counts = require(worker_b.get(lease_path))["counts"]
                                checks.check("waiting worker leases only its active item", counts["processing"] == 1 and counts["pending"] == 2)
                                second = require(worker_b.post(lease_path + "/process"))
                                checks.check("second app process consumes unstarted work within its own cap",
                                    (second["processed"], second["failed"], second["remaining"]) == (2, 0, 1))
                                checks.check("retry does not replay active or completed work",
                                    require(worker_b.post(lease_path + "/retry"))["requeued"] == 0)
                            finally:
                                (scratch / "lease-release").write_text("release", encoding="utf-8")
                            first_worker = require(pending.result(timeout=30))
                        checks.check("first worker commits only its own item after provider release",
                            (first_worker["processed"], first_worker["failed"], first_worker["remaining"]) == (1, 0, 0))
                        lease_saved = {suffix: require(worker_b.get(lease_path + suffix)) for suffix in ("", "/queue", "/summary")}
                        checks.check("two processes persist exactly three advisory queue results",
                            lease_saved[""]["counts"] == {"pending":0, "processing":0, "failed":0, "done":3}
                            and len({row["report_id"] for row in lease_saved["/queue"]["rows"]}) == 3
                            and lease_saved["/summary"]["n_screened"] == 3
                            and all(row["advisory"] and row["human_review_required"] for row in lease_saved["/queue"]["rows"]))
                        checks.check("another tenant cannot read or process worker intake", other.get(lease_path).status_code == 404
                            and other.post(lease_path + "/process").status_code == 404)
                        outcome_saved = {}
                        if terminal_outcomes:
                            for mode in ("stolen", "erased"):
                                batch = require(worker_b.post("/screening/batches", json={"name": f"Terminal {mode}", "items": [{
                                    "resume_text": contract._resume(f"Outcome {mode}", f"outcome-{mode}@example.com") }]}))
                                outcome_path = "/screening/batches/" + batch["id"]
                                (scratch / "outcome-mode").write_text(mode, encoding="utf-8")
                                with ThreadPoolExecutor(max_workers=1) as executor:
                                    pending = executor.submit(worker_a.post, outcome_path + "/process")
                                    try:
                                        entered = scratch / f"outcome-entered-{mode}.json"
                                        deadline = time.monotonic() + 15
                                        while not entered.exists():
                                            assert time.monotonic() < deadline, "worker never reached terminal gate"
                                            time.sleep(.05)
                                        subject = json.loads(entered.read_text(encoding="utf-8"))
                                        if mode == "stolen":
                                            (scratch / "outcome-advanced").write_text("advance", encoding="utf-8")
                                            winner = require(worker_b.post(outcome_path + "/process"))
                                            checks.check("replacement worker alone acknowledges completion",
                                                (winner["processed"], winner["failed"], winner["remaining"]) == (1, 0, 0))
                                        else:
                                            erased = require(worker_b.delete(f"/candidates/{subject['candidate_id']}", headers={"X-API-Key": ADMIN}))
                                            checks.check("second app erases subject before terminal write", erased["deleted"])
                                    finally:
                                        (scratch / f"outcome-release-{mode}").write_text("release", encoding="utf-8")
                                    loser = require(pending.result(timeout=30))
                                (scratch / "outcome-mode").unlink()
                                (scratch / "outcome-advanced").unlink(missing_ok=True)
                                state = {suffix: require(worker_b.get(outcome_path + suffix)) for suffix in ("", "/queue", "/summary")}
                                row = state["/queue"]["rows"][0]
                                checks.check(f"{mode}: response counts only this call's acknowledged transitions",
                                    (loser["processed"], loser["failed"], loser["remaining"]) == (0, int(mode == "erased"), 0))
                                if mode == "stolen":
                                    checks.check("stale completion cannot overwrite replacement report or saved counts",
                                        row["status"] == "done" and row["report_id"] != subject["report_id"]
                                        and state[""]["counts"] == {"pending":0, "processing":0, "failed":0, "done":1})
                                else:
                                    checks.check("acknowledged erasure failure has no subject links or signals",
                                        row["status"] == "failed" and row["error"] == "candidate_erased"
                                        and row["candidate_id"] is row["resume_id"] is row["report_id"] is row["signals"] is None
                                        and state[""]["counts"] == {"pending":0, "processing":0, "failed":1, "done":0})
                                checks.check(f"{mode}: retries do not replay settled or scrubbed input",
                                    require(worker_b.post(outcome_path + "/retry")) == {"batch_id":batch["id"], "requeued":0, "skipped":int(mode == "erased")}
                                    and require(worker_b.post(outcome_path + "/process"))["processed"] == 0
                                    and row["advisory"] and row["human_review_required"]
                                    and other.get(outcome_path + "/queue").status_code == 404)
                                outcome_saved[outcome_path] = state
        with server():
            public_ui()
            if leases:
                with client(base, headers=headers) as worker:
                    checks.check("exact concurrent queue and counters survive graceful app restart",
                        all(require(worker.get(lease_path + suffix)) == body for suffix, body in lease_saved.items())
                        and require(worker.post(lease_path + "/process"))["processed"] == 0
                        and require(worker.post(lease_path + "/retry"))["requeued"] == 0)
                    if terminal_outcomes:
                        checks.check("terminal outcomes and exact saved queue summaries survive graceful restart",
                            all(require(worker.get(path + suffix)) == body for path, state in outcome_saved.items() for suffix, body in state.items()))
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
    starts = 3 if leases else 2
    checks.check("all migrated workers share SQL topology and shut down gracefully", sum(row["event"] == "started" and row["revision"] == "0029_candidate_login_binding" and row["one_factory"] for row in lifecycle) == starts
        and sum(row["event"] == "disposed" for row in lifecycle) == starts
        and sum(row["event"] == "stopped" and row["detached"] for row in lifecycle) == starts)
    return checks.summary()


def main():
    scratch = Path(tempfile.mkdtemp(prefix="r4-s2-t1b1-" if "--outcomes" in sys.argv else "r4-s2-t1a-" if "--leases" in sys.argv else "r4-s1-t3d-"))
    with database(scratch) as (url, pg_options):
        return run(scratch, url, pg_options)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        asyncio.run(serve(int(sys.argv[2]), Path(sys.argv[3])))
    else:
        raise SystemExit(main())
