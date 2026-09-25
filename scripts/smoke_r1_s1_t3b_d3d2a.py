"""Migrated HTTP/restart checks for report-only response erasure.

The scratch server injects erasure on a separate database session immediately
after report persistence or the final read. Thread evidence is in pytest.
Supports SQLite and --postgres (fresh owned schema on DEE_TEST_DB_URL).
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, text

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-report-erasure-admin"
GATE_APP = '''
from app.reports.store import SqlReportStore
from app.main import app

original_save = SqlReportStore.save
original_get = SqlReportStore.get
armed = None
pending = None
last = None

def save(self, report, **kwargs):
    global armed, pending, last
    result = original_save(self, report, **kwargs)
    last = {'id': report.id, 'candidate_id': report.candidate_id}
    mode, armed = armed, None
    if mode == 'erase':
        assert SqlReportStore(self._session_factory).delete(report.id)
    elif mode:
        pending = (mode, report.id)
    return result

def get(self, report_id):
    global pending
    mode = None
    if pending and pending[1] == report_id:
        mode, _ = pending
        pending = None
    if mode == 'fail_read':
        raise RuntimeError('synthetic private lookup error')
    report = original_get(self, report_id)
    if mode == 'after_read':
        assert report is not None
        assert SqlReportStore(self._session_factory).delete(report_id)
    return report

SqlReportStore.save = save
SqlReportStore.get = get

@app.post('/_test/arm')
async def arm(mode: str):
    global armed, pending
    assert mode in ('erase', 'after_read', 'fail_read')
    armed, pending = mode, None
    return {'armed': True}

@app.get('/_test/last')
async def last_report():
    return last
'''


def main():
    checks = Smoke("report response erasure HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-report-response-"))
    print(f"Synthetic artifacts: {scratch}")
    (scratch / "gate_app.py").write_text(GATE_APP, encoding="utf-8")
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
        env.update({
            "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"),
            "DEE_CANDIDATES_DB_URL": url, "DEE_ENV": "local",
            "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
            "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
            "DEE_EMAIL_PROVIDER": "null", "DEE_VECTORSTORE_BACKEND": "memory",
            "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
            "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
            "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(scratch)]),
            "NO_PROXY": "127.0.0.1,localhost", "PGOPTIONS": pg_options,
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        @contextmanager
        def server(gated):
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(
                    uvicorn_argv(port, target="gate_app:app" if gated else "app.main:app"),
                    env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                try:
                    with client(f"http://127.0.0.1:{port}", headers={"X-API-Key": ADMIN}) as http:
                        assert wait_healthy(http), "scratch app failed to start"
                        yield http
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)

        def require(response, status=200):
            assert response.status_code == status, (response.request.url.path, response.status_code)
            return response.json()

        def body(name, short=False):
            content = "" if short else " ".join(f"synthetic{i}" for i in range(90))
            return {"resume_text": f"{name}\nEmail: {name.lower()}@example.com\nSkills: Python\n{content}"}

        erased, candidates, kept = [], [], []
        with server(True) as http:
            checks.check("migrated application starts", True)
            org = require(http.post("/ledger/orgs", json={"name": "Synthetic report agency"}))
            other = require(http.post("/ledger/orgs", json={"name": "Other agency"}))
            org_headers = {"X-Org-Key": org["api_key"]}
            keep = require(http.post("/screening/candidates", headers=org_headers, json=body("Kept")))
            kept.append(keep["report"]["id"])
            for path, door in (("/candidates", "admin"), ("/screening/candidates", "org"),
                               ("/evaluate", "standalone")):
                headers = org_headers if door == "org" else {}
                for short in (True, False):
                    payload = body(f"{door}{short}", short)
                    require(http.post("/_test/arm", params={"mode": "erase"}))
                    response = require(http.post(path, headers=headers, json=payload), 422)
                    last = require(http.get("/_test/last"))
                    erased.append(last["id"])
                    if last["candidate_id"]:
                        candidates.append(last["candidate_id"])
                        require(http.get(f"/candidates/{last['candidate_id']}"))
                    require(http.get(f"/report/{last['id']}"), 404)
                    checks.check(f"{door}/{short}: erased report refused; subject survives",
                                 response == {"detail": "report_erased"})
                    fresh = require(http.post(path, headers=headers, json=payload))
                    report = fresh if door == "standalone" else fresh["report"]
                    kept.append(report["id"])
                    checks.check(f"{door}/{short}: fresh request succeeds",
                                 report["id"] != last["id"] and
                                 (door == "standalone" or fresh["duplicate_resume"]))

                require(http.post("/_test/arm", params={"mode": "after_read"}))
                snapshot = require(http.post(path, headers=headers, json=body(door + "Snapshot")))
                report = snapshot if door == "standalone" else snapshot["report"]
                erased.append(report["id"])
                require(http.get(f"/report/{report['id']}"), 404)
                checks.check(f"{door}: deletion after final read leaves only snapshot", True)

                require(http.post("/_test/arm", params={"mode": "fail_read"}))
                failed = http.post(path, headers=headers, json=body(door + "Failure"))
                checks.check(f"{door}: unrelated failure stays generic 500",
                             failed.status_code == 500 and "synthetic private" not in failed.text)
                kept.append(require(http.get("/_test/last"))["id"])
                recovered = require(http.post(path, headers=headers, json=body(door + "Recovery")))
                kept.append((recovered if door == "standalone" else recovered["report"])["id"])

            batch = require(http.post("/screening/batches", headers=org_headers, json={
                "name": "Erased report", "domain": "genai",
                "items": [{"resume_text": body("Batch")["resume_text"]}]}))
            require(http.post("/_test/arm", params={"mode": "erase"}))
            result = require(http.post(f"/screening/batches/{batch['id']}/process", headers=org_headers))
            erased.append(require(http.get("/_test/last"))["id"])
            row = require(http.get(f"/screening/batches/{batch['id']}/queue", headers=org_headers))["rows"][0]
            checks.check("batch reports safe report refusal",
                         (result["processed"], result["failed"]) == (0, 1) and
                         row["error"] == "report_erased" and row["report_id"] is None)
            retry = require(http.post(f"/screening/batches/{batch['id']}/retry", headers=org_headers))
            checks.check("erased batch input cannot retry", (retry["requeued"], retry["skipped"]) == (0, 1))
            require(http.get(f"/screening/batches/{batch['id']}/queue",
                             headers={"X-Org-Key": other["api_key"]}), 404)
            require(http.get(f"/screening/reports/{keep['report']['id']}",
                             headers={"X-Org-Key": other["api_key"]}), 404)
            checks.check("other tenant cannot read batch or retained report", True)
            denied = http.post("/evaluate", headers={"X-API-Key": "invalid"}, json=body("Denied"))
            checks.check("unauthorized evaluation is refused", denied.status_code == 401)

            fresh = require(http.post("/screening/batches", headers=org_headers, json={
                "name": "Fresh", "domain": "genai",
                "items": [{"resume_text": body("Batch")["resume_text"]}]}))
            result = require(http.post(f"/screening/batches/{fresh['id']}/process", headers=org_headers))
            checks.check("fresh batch remains permitted", (result["processed"], result["failed"]) == (1, 0))
            row = require(http.get(f"/screening/batches/{fresh['id']}/queue", headers=org_headers))["rows"][0]
            kept.append(row["report_id"])

        with server(False) as http:
            for report_id in erased:
                require(http.get(f"/report/{report_id}"), 404)
            checks.check("restart retains all report erasures", True)
            for report_id in kept:
                require(http.get(f"/report/{report_id}"))
            checks.check("restart retains surviving reports", True)
            for candidate_id in candidates:
                require(http.get(f"/candidates/{candidate_id}"))
                assert require(http.get(f"/candidates/{candidate_id}/resumes"))["resumes"]
            checks.check("report-only erasure retains candidate and resume", True)
            args = {"connect_args": {"options": pg_options}} if pg_options else {}
            engine = create_engine(url, hide_parameters=True, **args)
            try:
                with engine.connect() as connection:
                    ids = set(connection.scalars(text("SELECT id FROM reports")))
                    checks.check("persisted report set matches successful writes", ids == set(kept))
                    assert connection.scalar(text("SELECT count(*) FROM screening_item_inputs")) == 0
                    failed = list(connection.execute(text("SELECT raw_text, text_sha256, candidate_id, resume_id, report_id, signals, risk_score FROM batch_items WHERE status = 'failed'")).one())
                    if isinstance(failed[5], str):
                        failed[5] = json.loads(failed[5])  # SQLite returns JSON text.
                    checks.check("failed batch retains no input or identifying links",
                                 tuple(failed) == ("", "", None, None, None, None, None))
            finally:
                engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
