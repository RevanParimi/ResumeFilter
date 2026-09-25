"""Migrated durable screening input HTTP/restart; synthetic separate-session erasure.

Concurrency/lock assertions live in pytest. --postgres uses an owned scratch
schema on DEE_TEST_DB_URL. Providers and inherited application settings are disabled.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

import httpx

from sqlalchemy import create_engine, text

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-refusal-retention-admin"
GATE_APP = '''
import os
from app.graph.build import EvaluationEngine
from app.main import app

original = EvaluationEngine.evaluate
armed = None

async def evaluate(self, **kwargs):
    global armed
    mode = armed
    armed = None
    if mode == "crash":
        os._exit(71)
    if mode == "failure":
        raise RuntimeError("synthetic provider failure")
    return await original(self, **kwargs)

EvaluationEngine.evaluate = evaluate

@app.post("/_test/arm")
async def arm(mode: str):
    global armed
    armed = mode
    return {"armed": True}
'''


def main():
    checks = Smoke("durable screening input HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-screening-input-"))
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
                        yield http, proc
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

        def register(http, headers, name):
            return require(http.post("/screening/batches", headers=headers, json={
                "name": name, "domain": "genai", "items": [
                    {"resume_text": "Synthetic engineer\nSkills: Python"}]}))["id"]

        args = {"connect_args": {"options": pg_options}} if pg_options else {}
        engine = create_engine(url, hide_parameters=True, **args)

        def retained(batch):
            with engine.connect() as conn:
                return conn.execute(text(
                    "SELECT b.id, b.raw_text, b.text_sha256, r.id AS rid, r.candidate_id AS cid "
                    "FROM batch_items b JOIN screening_item_inputs i ON i.id=b.id "
                    "JOIN resumes r ON r.id=i.resume_id WHERE b.batch_id=:batch"),
                    {"batch": batch}).one()

        def assert_erased(batch):
            with engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT b.raw_text, b.text_sha256, i.id FROM batch_items b "
                    "LEFT JOIN screening_item_inputs i ON i.id=b.id WHERE b.batch_id=:batch"),
                    {"batch": batch}).one()
                assert tuple(row) == ("", "", None)

        try:
            with server(True) as (http, _):
                org = require(http.post("/ledger/orgs", json={"name": "Synthetic agency"}))
                other = require(http.post("/ledger/orgs", json={"name": "Other agency"}))
                headers = {"X-Org-Key": org["api_key"]}
                checks.check("migrated app starts", True)
                batch = register(http, headers, "Ordinary failure")
                path = f"/screening/batches/{batch}"
                require(http.post("/_test/arm", params={"mode": "failure"}))
                result = require(http.post(path + "/process", headers=headers))
                row = retained(batch)
                checks.check("failed evaluation retains only resume reference",
                             result["failed"] == 1 and row.raw_text == row.text_sha256 == "")
                require(http.post(path + "/retry", headers={"X-Org-Key": other["api_key"]}), 404)
                checks.check("other tenant cannot retry", True)
                require(http.post(path + "/retry", headers=headers))
                checks.check("ordinary retry succeeds", require(http.post(
                    path + "/process", headers=headers))["processed"] == 1)
                completed = require(http.get(path + "/queue", headers=headers))["rows"][0]
                checks.check("contact-free retry preserves exact identity and resume",
                    (completed["candidate_id"], completed["resume_id"]) == (row.cid, row.rid))
                require(http.delete(f"/candidates/{row.cid}"))
                completed = require(http.get(path + "/queue", headers=headers))["rows"][0]
                checks.check("completed anonymous record survives erasure",
                             completed["status"] == "done" and completed["candidate_id"] is None)

            for parent in ("candidate", "resume"):
                with server(True) as (http, proc):
                    batch = register(http, headers, "Interrupted " + parent)
                    path = f"/screening/batches/{batch}"
                    require(http.post("/_test/arm", params={"mode": "crash"}))
                    try:
                        http.post(path + "/process", headers=headers)
                    except httpx.TransportError:
                        pass
                    else:
                        raise AssertionError("crashed worker returned a response")
                    checks.check(parent + " worker exits inside evaluation", proc.wait(timeout=15) == 71)
                row = retained(batch)
                checks.check(parent + " committed input reference survives worker exit",
                             row.raw_text == row.text_sha256 == "")
                with server(False) as (http, _):
                    suffix = "" if parent == "candidate" else f"/resumes/{row.rid}"
                    require(http.delete(f"/candidates/{row.cid}" + suffix))
                    assert_erased(batch)
                    checks.check(parent + " erasure removes retry input without worker cleanup", True)
                    # Select stale recovery deterministically, without waiting for the real timeout.
                    with engine.begin() as conn:
                        stale = datetime.now(timezone.utc) - timedelta(days=1)
                        conn.execute(text("UPDATE batch_items SET claimed_at=:at WHERE batch_id=:batch"),
                                     {"at": stale, "batch": batch})
                    result = require(http.post(path + "/process", headers=headers))
                    with engine.connect() as conn:
                        resume_count = conn.scalar(text("SELECT count(*) FROM resumes"))
                    checks.check(parent + " stale recovery cannot recreate resume",
                                 result["processed"] == 0 and resume_count == 0)
                    retry = require(http.post(path + "/retry", headers=headers))
                    checks.check(parent + " cleared retry is skipped", retry["requeued"] == 0
                                 and retry["skipped"] == 1)
                with server(False) as (http, _):
                    assert_erased(batch)
                    queue = require(http.get(path + "/queue", headers=headers))["rows"][0]
                    checks.check(parent + " second restart remains failed and advisory",
                                 queue["status"] == "failed" and queue["advisory"]
                                 and queue["human_review_required"])
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
