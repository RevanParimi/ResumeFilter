"""Migrated unresolved screening input HTTP/restart; synthetic separate-session erasure.

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

import app.auth.models  # noqa: F401 - report outcome authorship FK metadata
import app.ledger.models  # noqa: F401 - report organization FK metadata
from app.core.db import make_engine, make_session_factory
from app.reports.store import SqlReportStore

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-refusal-retention-admin"
GATE_APP = '''
import os
from app.candidates.store import CandidateStore
from app.candidates import extractor
from app.main import app

original_ingest = CandidateStore.ingest
original_extract = extractor.extract_profile
armed = None

async def extract(*args, **kwargs):
    global armed
    if armed == "extract_crash":
        os._exit(71)
    return await original_extract(*args, **kwargs)

def ingest(self, *args, **kwargs):
    global armed
    mode, armed = armed, None
    if mode == "failure":
        raise RuntimeError("synthetic first ingest failure")
    if mode == "crash":
        original = kwargs.get("before_commit")
        def stop(session, outcome):
            if original:
                original(session, outcome)
                session.flush()
            os._exit(72)
        kwargs["before_commit"] = stop
    return original_ingest(self, *args, **kwargs)

CandidateStore.ingest = ingest
extractor.extract_profile = extract

@app.post("/_test/arm")
async def arm(mode: str):
    global armed
    armed = mode
    return {"armed": True}
'''



def main():
    checks = Smoke("unresolved screening input HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-screening-unresolved-"))
    print(f"Synthetic artifacts: {scratch}")
    (scratch / "gate_app.py").write_text(GATE_APP, encoding="utf-8")
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
        env.update({
            "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"),
            "DEE_CANDIDATES_DB_URL": url, "DEE_ENV": "local",
            "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
            "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
            "DEE_EMAIL_PROVIDER": "capture", "DEE_EMAIL_CAPTURE_PATH": str(scratch / "mailbox.jsonl"),
            "DEE_SESSION_COOKIE_SECURE": "false", "DEE_VECTORSTORE_BACKEND": "memory",
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

        def register(http, headers, name, content="Synthetic engineer"):
            return require(http.post("/screening/batches", headers=headers, json={
                "name": name, "domain": "genai", "items": [{"resume_text": content}]}))["id"]

        args = {"connect_args": {"options": pg_options}} if pg_options else {}
        engine = create_engine(url, hide_parameters=True, **args)

        def assert_preserved(batch, content):
            with engine.connect() as conn:
                row = conn.execute(text("SELECT raw_text, text_sha256 FROM batch_items WHERE batch_id=:b"),
                                   {"b": batch}).one()
                assert row.raw_text == content and row.text_sha256
                assert conn.scalar(text("SELECT count(*) FROM screening_item_inputs i JOIN batch_items b "
                                        "ON i.id=b.id WHERE b.batch_id=:b"), {"b": batch}) == 0

        try:
            with server(True) as (http, _):
                org = require(http.post("/ledger/orgs", json={"name": "Synthetic agency"}))
                other = require(http.post("/ledger/orgs", json={"name": "Other agency"}))
                headers = {"X-Org-Key": org["api_key"]}
                checks.check("migrated app starts", True)
                content = "Synthetic engineer\nEmail: failure@example.com"
                seed = require(http.post("/screening/candidates", headers=headers,
                               json={"resume_text": content, "evaluate": False}))
                batch = register(http, headers, "Ordinary first failure", content)
                other_batch = register(http, {"X-Org-Key": other["api_key"]}, "Unrelated")
                path = f"/screening/batches/{batch}"
                require(http.post("/_test/arm", params={"mode": "failure"}))
                assert require(http.post(path + "/process", headers=headers))["failed"] == 1
                require(http.delete(f"/candidates/{seed['candidate_id']}"))
                checks.check("first failure retry skipped after erasure",
                             require(http.post(path + "/retry", headers=headers))["skipped"] == 1)
                assert_preserved(batch, content)
                checks.check("unlinked text retained rather than silently deleted", True)
                row = require(http.get(path + "/queue", headers=headers))["rows"][0]
                checks.check("actionable safe queue reason", row["error"] == "fresh_upload_required"
                             and "Upload this resume again" in row["reason"])
                other_rows = require(http.get(f"/screening/batches/{other_batch}/queue",
                    headers={"X-Org-Key": other["api_key"]}))["rows"]
                checks.check("other unlinked tenant input is conservatively paused",
                             other_rows[0]["error"] == "fresh_upload_required")
                require(http.get(path + "/queue", headers={"X-Org-Key": other["api_key"]}), 404)
                checks.check("tenant reads remain isolated", True)
                fresh = register(http, headers, "Fresh upload", content)
                checks.check("fresh upload remains permitted", require(http.post(
                    f"/screening/batches/{fresh}/process", headers=headers))["processed"] == 1)

            for phase in ("extract_crash", "crash"):
                with server(True) as (http, proc):
                    content = "Synthetic engineer\nEmail: " + phase + "@example.com"
                    seed = require(http.post("/screening/candidates", headers=headers,
                        json={"resume_text": content, "evaluate": False}))
                    batch = register(http, headers, "Interrupted " + phase, content)
                    path = f"/screening/batches/{batch}"
                    require(http.post("/_test/arm", params={"mode": phase}))
                    try:
                        http.post(path + "/process", headers=headers)
                    except httpx.TransportError:
                        pass
                    else:
                        raise AssertionError("crashed worker returned a response")
                    checks.check(phase + " real worker exit", proc.wait(timeout=15) == (
                        71 if phase == "extract_crash" else 72))
                assert_preserved(batch, content)
                checks.check(phase + " uncommitted ingest binding rolled back", True)
                with server(False) as (http, _):
                    require(http.delete(f"/candidates/{seed['candidate_id']}"))
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE batch_items SET claimed_at=:at WHERE batch_id=:b"),
                                     {"at": datetime.now(timezone.utc)-timedelta(days=1), "b": batch})
                        before = conn.execute(text("SELECT id FROM candidates ORDER BY id")).all()
                    result = require(http.post(path + "/process", headers=headers))
                    with engine.connect() as conn:
                        after = conn.execute(text("SELECT id FROM candidates ORDER BY id")).all()
                    checks.check(phase + " stale recovery cannot recreate subject",
                                 result["processed"] == 0 and before == after)
                    checks.check(phase + " retry stays skipped",
                                 require(http.post(path + "/retry", headers=headers))["skipped"] == 1)
                    assert_preserved(batch, content)
                with server(False) as (http, _):
                    row = require(http.get(path + "/queue", headers=headers))["rows"][0]
                    checks.check(phase + " refusal survives second restart",
                                 row["status"] == "failed" and row["error"] == "fresh_upload_required"
                                 and row["advisory"] and row["human_review_required"])
            if "--browser" in __import__("sys").argv:
                import asyncio
                from check_ui_screening_unresolved_browser import check_browser
                with server(False) as (http, _):
                    asyncio.run(check_browser(str(http.base_url).rstrip("/"), http,
                                              scratch, checks))
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
