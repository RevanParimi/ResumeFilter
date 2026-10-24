"""Screening HTTP contract and persisted employer workflow on scratch SQL.

Uses the existing fake-provider production SQL app and graceful restart loop.
The reused UI contract is HTTP simulation, not actual browser execution.
--leases adds R4-S2-T1A's two-app-process slow-provider scheduling journey.
--outcomes adds R4-S2-T1B1's terminal refusal/erasure journey to --leases.
--expiry adds R4-S2-T1B2a's no-reclaimer terminal expiry and recovery.
--persistence adds R4-S2-T1B2b1's input/report expiry rollback and recovery.
Its checkpoints also verify B2b2a's private original facts across workers.
B2b2b adds first-report reuse without provider replay, including after restart.
--postgres uses an explicitly disposable DEE_TEST_DB_URL and an owned schema.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from datetime import timedelta
from hashlib import sha256
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
            retain, bind = svc._store.retain_ingested_input, svc._store.bind_input_report

            def controlled_now():
                # Deterministic expiry for competing OS processes, not a
                # measured wall-clock timeout.
                offset = svc._settings.screening_claim_timeout_seconds + 1 if (scratch / "outcome-advanced").exists() else 0
                return now() + timedelta(seconds=offset)

            def gate(mode, subject):
                armed = scratch / "outcome-mode"
                if armed.exists() and armed.read_text(encoding="utf-8") == mode:
                    try:
                        (scratch / f"outcome-claimed-{mode}").open("x").close()
                    except FileExistsError:
                        pass
                    else:
                        entered = scratch / f"outcome-entered-{mode}.json"
                        temporary = entered.with_suffix(".tmp")
                        temporary.write_text(json.dumps(subject), encoding="utf-8")
                        temporary.replace(entered)
                        deadline = time.monotonic() + 30
                        while not (scratch / f"outcome-release-{mode}").exists():
                            assert time.monotonic() < deadline, "synthetic persistence gate timed out"
                            time.sleep(.05)

            def controlled_complete(item_id, **kwargs):
                from app.screening.models import ScreeningInputRow
                with svc._store._session_factory() as session:
                    ref = session.get(ScreeningInputRow, item_id)
                    checkpoint = {"ingest_facts": ref.ingest_facts if ref else None,
                                  "input_created_at": ref.created_at.isoformat() if ref else None}
                target = scratch / f"checkpoint-{kwargs['report_id']}.json"
                temporary = target.with_suffix(".tmp")
                temporary.write_text(json.dumps(checkpoint), encoding="utf-8")
                temporary.replace(target)
                armed = scratch / "outcome-mode"
                if armed.exists():
                    mode = armed.read_text(encoding="utf-8")
                    if mode in {"stolen", "erased", "expired", "restart"}:
                        gate(mode, {"candidate_id": kwargs["candidate_id"], "report_id": kwargs["report_id"],
                                    **checkpoint})
                return complete(item_id, **kwargs)

            def controlled_retain(session, org, item, outcome, **kwargs):
                (scratch / f"ingested-{outcome.extraction_id}.json").write_text(json.dumps({
                    "candidate_id": outcome.candidate_id}), encoding="utf-8")
                gate("input-expired", {"candidate_id": outcome.candidate_id, "report_id": None})
                return retain(session, org, item, outcome, **kwargs)

            def controlled_bind(session, org, item, report, **kwargs):
                from app.screening.models import ScreeningInputRow
                ref = session.get(ScreeningInputRow, item.id)
                gate("report-expired", {"candidate_id": report.candidate_id, "report_id": report.id,
                    "ingest_facts": ref.ingest_facts if ref else None,
                    "input_created_at": ref.created_at.isoformat() if ref else None})
                return bind(session, org, item, report, **kwargs)

            svc._now = controlled_now
            svc._store.complete = controlled_complete
            svc._store.retain_ingested_input = controlled_retain
            svc._store.bind_input_report = controlled_bind

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
                report = await evaluate(**kwargs)
                (scratch / f"evaluated-{report.id}.json").write_text(json.dumps({
                    "sha256": sha256(kwargs["resume_text"].encode("utf-8")).hexdigest()}), encoding="utf-8")
                return report

            app.state.engine.evaluate = controlled
            yield

    app.router.lifespan_context = lifespan
    return app


def run(scratch, url, pg_options):
    persistence = "--persistence" in sys.argv
    expiry = "--expiry" in sys.argv or persistence
    terminal_outcomes = "--outcomes" in sys.argv or expiry
    leases = "--leases" in sys.argv or terminal_outcomes
    cap = 2 if leases else 1
    print(f"Synthetic screening HTTP evidence: {scratch}", flush=True)
    checks = Smoke("R4-S2-T1B2b2b authorized report recovery / two workers / restart" if persistence
                   else "R4-S2-T1B2a terminal expiry / two workers / graceful restart" if expiry
                   else "R4-S2-T1B1 terminal outcomes / two workers / graceful restart" if terminal_outcomes
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

    def evaluations(text):
        digest = sha256(text.encode("utf-8")).hexdigest()
        return sum(json.loads(path.read_text(encoding="utf-8"))["sha256"] == digest
                   for path in scratch.glob("evaluated-*.json"))

    def ingestions(candidate_id):
        return sum(json.loads(path.read_text(encoding="utf-8"))["candidate_id"] == candidate_id
                   for path in scratch.glob("ingested-*.json"))

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
                        outcome_saved, recovery_restart = {}, None
                        if terminal_outcomes:
                            modes = ["stolen", "erased"] + (["expired"] if expiry else [])
                            if persistence:
                                modes += ["input-expired", "report-expired", "restart"]
                            expired_modes = {"expired", "input-expired", "report-expired", "restart"}
                            for mode in modes:
                                resume_text = contract._resume(f"Outcome {mode}", f"outcome-{mode}@example.com")
                                batch = require(worker_b.post("/screening/batches", json={"name": f"Terminal {mode}", "items": [{
                                    "resume_text": resume_text }]}))
                                outcome_path = "/screening/batches/" + batch["id"]
                                (scratch / "outcome-mode").write_text(mode, encoding="utf-8")
                                with ThreadPoolExecutor(max_workers=1) as executor:
                                    pending = executor.submit(worker_a.post, outcome_path + "/process")
                                    try:
                                        entered = scratch / f"outcome-entered-{mode}.json"
                                        deadline = time.monotonic() + 15
                                        while True:
                                            assert time.monotonic() < deadline, "worker never reached persistence gate"
                                            try:
                                                subject = json.loads(entered.read_text(encoding="utf-8"))
                                                break
                                            except (FileNotFoundError, PermissionError):
                                                # Windows can expose a renamed gate before its
                                                # writer releases the transient sharing lock.
                                                time.sleep(.05)
                                        if mode in {"stolen", "expired", "restart"}:
                                            subject["saved_report"] = require(worker_b.get(f"/screening/reports/{subject['report_id']}"))
                                        if mode == "stolen" or mode in expired_modes:
                                            (scratch / "outcome-advanced").write_text("advance", encoding="utf-8")
                                            if mode == "stolen":
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
                                state = {suffix: require(worker_b.get(outcome_path + suffix)) for suffix in ("", "/queue", "/summary")}
                                row = state["/queue"]["rows"][0]
                                checks.check(f"{mode}: response counts only this call's acknowledged transitions",
                                    (loser["processed"], loser["failed"], loser["remaining"]) == (0, int(mode == "erased"), int(mode in expired_modes)))
                                if mode in expired_modes:
                                    if mode == "input-expired":
                                        checks.check("expired ingest rolls back its subject through HTTP",
                                            control.get(f"/candidates/{subject['candidate_id']}").status_code == 404)
                                    elif mode == "report-expired":
                                        checks.check("expired report rolls back while earlier subject survives",
                                            control.get(f"/candidates/{subject['candidate_id']}").status_code == 200
                                            and worker_b.get(f"/screening/reports/{subject['report_id']}").status_code == 404)
                                    checks.check(f"{mode}: expired attempt stays pending without public result links",
                                        row["status"] == "pending" and row["error"] is None
                                        and row["candidate_id"] is row["resume_id"] is row["report_id"] is row["signals"] is None
                                        and state[""]["counts"] == {"pending":1, "processing":0, "failed":0, "done":0}
                                        and state["/summary"]["n_screened"] == 0)
                                    if mode == "restart":
                                        recovery_restart = outcome_path, subject, resume_text
                                    else:
                                        recovered = require(worker_b.post(outcome_path + "/process"))
                                        checks.check("later request recovers expired work using retained input",
                                            (recovered["processed"], recovered["failed"], recovered["remaining"]) == (1, 0, 0))
                                        state = {suffix: require(worker_b.get(outcome_path + suffix)) for suffix in ("", "/queue", "/summary")}
                                        row = state["/queue"]["rows"][0]
                                        checks.check(f"{mode}: recovery commits expected subject and exactly one queue result",
                                            (row["candidate_id"] != subject["candidate_id"] if mode == "input-expired"
                                             else row["candidate_id"] == subject["candidate_id"]) and row["status"] == "done"
                                            and state[""]["counts"] == {"pending":0, "processing":0, "failed":0, "done":1}
                                            and state["/summary"]["n_screened"] == 1)
                                if mode != "restart": (scratch / "outcome-advanced").unlink(missing_ok=True)
                                if mode in {"stolen", "expired", "report-expired"}:
                                    checkpoint = json.loads((scratch / f"checkpoint-{row['report_id']}.json").read_text(encoding="utf-8"))
                                    checks.check(f"{mode}: original private matching facts and TTL survive recovery",
                                        checkpoint == {key: subject[key] for key in ("ingest_facts", "input_created_at")}
                                        and checkpoint["ingest_facts"] == {"version":1, "matched_existing":False,
                                            "matched_on":None, "duplicate_resume":False})
                                checks.check(f"{mode}: private ingest checkpoint never enters public batch reads",
                                    "ingest_facts" not in json.dumps(state) and "input_created_at" not in json.dumps(state))
                                if mode == "stolen":
                                    checks.check("stale completion cannot overwrite recovered report or saved counts",
                                        row["status"] == "done" and row["report_id"] == subject["report_id"]
                                        and state[""]["counts"] == {"pending":0, "processing":0, "failed":0, "done":1})
                                elif mode == "erased":
                                    checks.check("acknowledged erasure failure has no subject links or signals",
                                        row["status"] == "failed" and row["error"] == "candidate_erased"
                                        and row["candidate_id"] is row["resume_id"] is row["report_id"] is row["signals"] is None
                                        and state[""]["counts"] == {"pending":0, "processing":0, "failed":1, "done":0})
                                if mode in {"stolen", "expired"}:
                                    checks.check(f"{mode}: reuse preserves report/body/original facts without provider or ingest replay",
                                        row["report_id"] == subject["report_id"]
                                        and require(worker_b.get(f"/screening/reports/{row['report_id']}")) == subject["saved_report"]
                                        and all(row["signals"][key] == subject["ingest_facts"][key] for key in (
                                            "matched_existing", "matched_on", "duplicate_resume"))
                                        and evaluations(resume_text) == ingestions(subject["candidate_id"]) == 1
                                        and len(require(worker_b.get(f"/screening/candidates/{row['candidate_id']}/reports"))) == 1)
                                elif mode in {"input-expired", "report-expired"}:
                                    checks.check(f"{mode}: pre-checkpoint provider cost is distinct from one persisted report",
                                        evaluations(resume_text) == (2 if mode == "report-expired" else 1)
                                        and len(require(worker_b.get(f"/screening/candidates/{row['candidate_id']}/reports"))) == 1)
                                checks.check(f"{mode}: retries do not replay settled or scrubbed input",
                                    require(worker_b.post(outcome_path + "/retry")) == {"batch_id":batch["id"], "requeued":0, "skipped":int(mode == "erased")}
                                    and (mode == "restart" or require(worker_b.post(outcome_path + "/process"))["processed"] == 0)
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
                    if recovery_restart is not None:
                        restart_path, subject, resume_text = recovery_restart
                        try:
                            recovered = require(worker.post(restart_path + "/process"))
                            state = {suffix: require(worker.get(restart_path + suffix)) for suffix in ("", "/queue", "/summary")}
                            row = state["/queue"]["rows"][0]
                            checks.check("pending report checkpoint recovers after app restart with exact original result and counts",
                                (recovered["processed"], recovered["failed"], recovered["remaining"]) == (1,0,0)
                                and row["report_id"] == subject["report_id"]
                                and require(worker.get(f"/screening/reports/{row['report_id']}")) == subject["saved_report"]
                                and all(row["signals"][key] == subject["ingest_facts"][key] for key in (
                                    "matched_existing", "matched_on", "duplicate_resume"))
                                and state["/summary"]["n_screened"] == 1 and state[""]["counts"]["done"] == 1
                                and evaluations(resume_text) == ingestions(subject["candidate_id"]) == 1)
                            checks.check("recovered checkpoint cannot replay after restart",
                                require(worker.post(restart_path + "/process"))["processed"] == 0
                                and require(worker.post(restart_path + "/retry"))["requeued"] == 0)
                        finally: (scratch / "outcome-advanced").unlink(missing_ok=True)
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
    checks.check("all migrated workers share SQL topology and shut down gracefully", sum(row["event"] == "started" and row["revision"] == "0030_screening_ingest_facts" and row["one_factory"] for row in lifecycle) == starts
        and sum(row["event"] == "disposed" for row in lifecycle) == starts
        and sum(row["event"] == "stopped" and row["detached"] for row in lifecycle) == starts)
    return checks.summary()


def main():
    scratch = Path(tempfile.mkdtemp(prefix="r4-s2-t1b2b2b-" if "--persistence" in sys.argv else "r4-s2-t1b2a-" if "--expiry" in sys.argv else "r4-s2-t1b1-" if "--outcomes" in sys.argv else "r4-s2-t1a-" if "--leases" in sys.argv else "r4-s1-t3d-"))
    with database(scratch) as (url, pg_options):
        return run(scratch, url, pg_options)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        asyncio.run(serve(int(sys.argv[2]), Path(sys.argv[3])))
    else:
        raise SystemExit(main())
