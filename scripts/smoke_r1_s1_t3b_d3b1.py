"""Migrated screening refusal retention HTTP/restart; synthetic separate-session erasure.

Concurrency/lock assertions live in pytest. --postgres uses an owned scratch
schema on DEE_TEST_DB_URL. Providers and inherited application settings are disabled.
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
ADMIN = "synthetic-refusal-retention-admin"
GATE_APP = '''
from app.candidates.store import CandidateStore
from app.main import app

resolve = CandidateStore._resolve_candidate
save = CandidateStore.save_fingerprint
armed = None

def resolve_with_erasure(self, session, profile):
    global armed
    row, matched = resolve(session, profile)
    if armed == "resolved":
        armed = None
        assert CandidateStore(self._session_factory).delete_candidate(row.id)
    return row, matched

def fingerprint_with_erasure(self, fp, *, resume_id, candidate_id):
    global armed
    mode = armed
    armed = None
    if mode == "candidate":
        assert CandidateStore(self._session_factory).delete_candidate(candidate_id)
    elif mode == "resume":
        assert CandidateStore(self._session_factory).delete_resume(resume_id)
    return save(self, fp, resume_id=resume_id, candidate_id=candidate_id)

CandidateStore._resolve_candidate = resolve_with_erasure
CandidateStore.save_fingerprint = fingerprint_with_erasure

@app.post("/_test/arm")
async def arm(parent: str):
    global armed
    armed = parent
    return {"armed": True}
'''


def main():
    checks = Smoke("screening refusal retention HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-screening-refusal-"))
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

        def register(http, headers, name):
            content = " ".join(f"synthetic{i}" for i in range(90))
            resume = f"{name}\nEmail: {name.lower()}@example.com\nSkills: Python\n{content}"
            if name == "resolved":
                require(http.post("/screening/candidates", headers=headers,
                                  json={"resume_text": resume, "evaluate": False}))
            return require(http.post("/screening/batches", headers=headers, json={
                "name": name, "domain": "genai", "items": [{"resume_text": resume}]}))["id"]

        failed = []
        with server(True) as http:
            checks.check("migrated application starts", True)
            org = require(http.post("/ledger/orgs", json={"name": "Synthetic agency"}))
            other = require(http.post("/ledger/orgs", json={"name": "Other agency"}))
            headers = {"X-Org-Key": org["api_key"]}
            for stage in ("resolved", "candidate", "resume"):
                parent = "candidate" if stage == "resolved" else stage
                batch = register(http, headers, stage)
                path = f"/screening/batches/{batch}"
                require(http.post("/_test/arm", params={"parent": stage}))
                ran = require(http.post(path + "/process", headers=headers))
                row = require(http.get(path + "/queue", headers=headers))["rows"][0]
                failed.append((batch, row["item_id"], parent, stage))
                checks.check(f"{stage} refusal counted with no retained signals",
                             ran["processed"] == 0 and ran["failed"] == 1 and ran["remaining"] == 0
                             and row["error"] == f"{parent}_erased" and row["signals"] is None
                             and row["candidate_id"] is None and row["report_id"] is None
                             and row["advisory"] and row["human_review_required"])
                retry = require(http.post(path + "/retry", headers=headers))
                checks.check(f"{stage} cleared item cannot retry", retry["requeued"] == 0
                             and retry["skipped"] == 1
                             and require(http.post(path + "/process", headers=headers))["processed"] == 0)
                require(http.get(path + "/queue", headers={"X-Org-Key": other["api_key"]}), 404)
                checks.check(f"{stage} other tenant denied", True)
            kept = register(http, headers, "Kept")
            path = f"/screening/batches/{kept}"
            checks.check("unrelated screening still succeeds",
                         require(http.post(path + "/process", headers=headers))["processed"] == 1)
            done = register(http, headers, "WriteFirst")
            path = f"/screening/batches/{done}"
            require(http.post(path + "/process", headers=headers))
            row = require(http.get(path + "/queue", headers=headers))["rows"][0]
            require(http.delete(f"/candidates/{row['candidate_id']}"))
            row = require(http.get(path + "/queue", headers=headers))["rows"][0]
            checks.check("write-first retains anonymous completion", row["status"] == "done"
                         and row["candidate_id"] is row["resume_id"] is row["report_id"] is None)

        with server(False) as http:
            for batch, item, parent, stage in failed:
                path = f"/screening/batches/{batch}"
                row = require(http.get(path + "/queue", headers=headers))["rows"][0]
                checks.check(f"restart preserves {stage} refusal", row["status"] == "failed"
                             and row["error"] == f"{parent}_erased")
            checks.check("restart preserves successful screening", require(http.get(
                f"/screening/batches/{kept}/queue", headers=headers))["rows"][0]["candidate_id"] is not None)
            args = {"connect_args": {"options": pg_options}} if pg_options else {}
            engine = create_engine(url, hide_parameters=True, **args)
            try:
                with engine.connect() as connection:
                    for _, item, parent, stage in failed:
                        row = connection.execute(text(
                            "SELECT raw_text, text_sha256, candidate_id, resume_id, report_id, risk_score "
                            "FROM batch_items WHERE id=:id"), {"id": item}).one()
                        checks.check(f"restart SQL {stage} input/links scrubbed",
                                     tuple(row) == ("", "", None, None, None, None))
            finally:
                engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
