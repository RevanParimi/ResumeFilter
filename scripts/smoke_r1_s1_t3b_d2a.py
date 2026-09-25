"""Migrated HTTP/restart ingest checks; synthetic erasure after resolution.

The scratch server injects erasure on a separate database session immediately
after identity resolution. Competing-thread/lock evidence lives in pytest.
Supports SQLite and --postgres (fresh owned schema on DEE_TEST_DB_URL).
"""

from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, text

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-ingest-erasure-admin"
GATE_APP = '''
from app.candidates.store import CandidateStore
from app.main import app

original = CandidateStore._resolve_candidate
armed = False

def resolve(self, session, profile):
    global armed
    row, matched_on = original(session, profile)
    if armed and row is not None:
        armed = False
        assert CandidateStore(self._session_factory).delete_candidate(row.id)
    return row, matched_on

CandidateStore._resolve_candidate = resolve

@app.post("/_test/arm")
async def arm():
    global armed
    armed = True
    return {"armed": True}
'''


def main():
    checks = Smoke("ingest erasure HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-ingest-erasure-"))
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

        def body(name):
            return {"resume_text": f"{name}\nEmail: {name.lower()}@example.com\nSkills: Python",
                    "evaluate": False}

        erased = []
        with server(True) as http:
            checks.check("migrated application starts", True)
            kept = require(http.post("/candidates", json=body("Kept")))
            org = require(http.post("/ledger/orgs", json={"name": "Synthetic agency"}))
            for door in ("admin", "org"):
                path = "/candidates" if door == "admin" else "/screening/candidates"
                headers = {} if door == "admin" else {"X-Org-Key": org["api_key"]}
                saved = require(http.post(path, headers=headers, json=body(door)))
                erased.append(saved["candidate_id"])
                duplicate = require(http.post(path, headers=headers, json=body(door)))
                checks.check(f"{door} duplicate retains identity/version",
                             duplicate["candidate_id"] == saved["candidate_id"] and
                             duplicate["resume_id"] == saved["resume_id"] and
                             duplicate["duplicate_resume"])
                require(http.post("/_test/arm"))
                refusal = require(http.post(path, headers=headers, json=body(door)), 422)
                checks.check(f"{door} erased resolved upload returns safe refusal",
                             refusal == {"detail": "candidate_erased"})
                require(http.get(f"/candidates/{saved['candidate_id']}"), 404)
                checks.check(f"{door} interrupted upload does not recreate subject", True)
            done = require(http.post("/candidates", json=body("WriteFirst")))
            erased.append(done["candidate_id"])
            checks.check("committed ingest can subsequently be erased",
                         require(http.delete(f"/candidates/{done['candidate_id']}"))["deleted"])

        with server(False) as http:
            require(http.get(f"/candidates/{kept['candidate_id']}"))
            checks.check("restart preserves other candidate", True)
            for cid in erased:
                require(http.get(f"/candidates/{cid}"), 404)
            checks.check("restart preserves all erasures", True)
            args = {"connect_args": {"options": pg_options}} if pg_options else {}
            engine = create_engine(url, hide_parameters=True, **args)
            try:
                with engine.connect() as connection:
                    for table in ("resumes", "extractions"):
                        owners = set(connection.scalars(text(f"SELECT candidate_id FROM {table}")))
                        checks.check(f"only survivor retains {table}", owners == {kept["candidate_id"]})
            finally:
                engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
