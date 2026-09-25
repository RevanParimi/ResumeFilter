"""Migrated HTTP/restart checks for post-fingerprint ingest response erasure.

The scratch server injects erasure on a separate database session immediately
after ingest, comparison, evaluation or report persistence. Thread evidence is in pytest.
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
from app.graph.build import EvaluationEngine
from app.reports.store import SqlReportStore
from app.main import app

original_ingest = CandidateStore.ingest
original_compare = CandidateStore.similar_resumes
original_eval = EvaluationEngine.evaluate
original_save = SqlReportStore.save
armed = None
pending = None

def erase(boundary):
    global pending
    if pending and pending[0]['boundary'] == boundary:
        config, store, outcome = pending
        pending = None
        if config['parent'] == 'candidate':
            assert store.delete_candidate(outcome.candidate_id)
        else:
            assert store.delete_resume(outcome.resume_id)

def ingest(self, *args, **kwargs):
    global armed, pending
    result = original_ingest(self, *args, **kwargs)
    if armed:
        pending = (armed, CandidateStore(self._session_factory), result)
        armed = None
        erase('short')
    return result

def compare(self, *args, **kwargs):
    result = original_compare(self, *args, **kwargs)
    erase('comparison')
    return result

async def evaluate(self, **kwargs):
    result = await original_eval(self, **kwargs)
    erase('evaluation')
    return result

def save(self, *args, **kwargs):
    result = original_save(self, *args, **kwargs)
    erase('report')
    return result

CandidateStore.ingest = ingest
CandidateStore.similar_resumes = compare
EvaluationEngine.evaluate = evaluate
SqlReportStore.save = save

@app.post("/_test/arm")
async def arm(parent: str, boundary: str):
    global armed
    assert parent in ('candidate', 'resume')
    assert boundary in ('short', 'comparison', 'evaluation', 'report')
    armed = {'parent': parent, 'boundary': boundary}
    return {"armed": True}
'''


def main():
    checks = Smoke("ingest response erasure HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-ingest-response-"))
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
            return {"resume_text": f"{name}\nEmail: {name.lower()}@example.com\nSkills: Python\n{content}",
                    "evaluate": False}

        erased = []
        resume_only = []
        with server(True) as http:
            checks.check("migrated application starts", True)
            kept = require(http.post("/candidates", json=body("Kept")))
            org = require(http.post("/ledger/orgs", json={"name": "Synthetic agency"}))
            for door in ("admin", "org"):
                path = "/candidates" if door == "admin" else "/screening/candidates"
                headers = {} if door == "admin" else {"X-Org-Key": org["api_key"]}
                for parent in ("candidate", "resume"):
                    for boundary, evaluate in (("short", False), ("short", True),
                            ("comparison", False), ("comparison", True),
                            ("evaluation", True), ("report", True)):
                        payload = body(f"{door}{parent}{boundary}{evaluate}", short=boundary == "short")
                        saved = require(http.post(path, headers=headers, json=payload))
                        (erased if parent == "candidate" else resume_only).append(saved["candidate_id"])
                        duplicate = require(http.post(path, headers=headers, json=payload))
                        assert duplicate["candidate_id"] == saved["candidate_id"]
                        assert duplicate["resume_id"] == saved["resume_id"] and duplicate["duplicate_resume"]
                        require(http.post("/_test/arm", params={"parent": parent, "boundary": boundary}))
                        payload["evaluate"] = evaluate
                        refusal = require(http.post(path, headers=headers, json=payload), 422)
                        checks.check(f"{door}/{parent}/{boundary}/{evaluate}: duplicate then safe refusal",
                                     refusal == {"detail": f"{parent}_erased"})
            headers = {"X-Org-Key": org["api_key"]}
            for parent in ("candidate", "resume"):
                batch = require(http.post("/screening/batches", headers=headers, json={
                    "name": "Synthetic", "domain": "genai",
                    "items": [{"resume_text": body("batch" + parent)["resume_text"]}]}))
                require(http.post("/_test/arm", params={"parent": parent, "boundary": "comparison"}))
                ran = require(http.post(f"/screening/batches/{batch['id']}/process", headers=headers))
                row = require(http.get(f"/screening/batches/{batch['id']}/queue", headers=headers))["rows"][0]
                checks.check(f"batch/{parent} records safe late refusal",
                             ran["failed"] == 1 and ran["processed"] == 0 and
                             row["error"] == f"{parent}_erased" and row["candidate_id"] is None)
                retry = require(http.post(f"/screening/batches/{batch['id']}/retry", headers=headers))
                assert (retry["requeued"], retry["skipped"]) == (0, 1)
            done = require(http.post("/candidates", json=body("WriteFirst")))
            erased.append(done["candidate_id"])
            checks.check("committed fingerprint can subsequently be erased",
                         require(http.delete(f"/candidates/{done['candidate_id']}"))["deleted"])
            fresh = require(http.post("/screening/batches", headers=headers, json={
                "name": "Fresh survivor", "domain": "genai",
                "items": [{"resume_text": body("FreshSurvivor")["resume_text"]}]}))
            ran = require(http.post(f"/screening/batches/{fresh['id']}/process", headers=headers))
            checks.check("fresh batch after erasure proceeds", (ran["processed"], ran["failed"]) == (1, 0))
            fresh_row = require(http.get(f"/screening/batches/{fresh['id']}/queue", headers=headers))["rows"][0]

        with server(False) as http:
            require(http.get(f"/candidates/{kept['candidate_id']}"))
            checks.check("restart preserves other candidate", True)
            for cid in erased:
                require(http.get(f"/candidates/{cid}"), 404)
            checks.check("restart preserves candidate erasures", True)
            for cid in resume_only:
                require(http.get(f"/candidates/{cid}"))
            checks.check("resume-only erasure preserves candidate identity", True)
            args = {"connect_args": {"options": pg_options}} if pg_options else {}
            engine = create_engine(url, hide_parameters=True, **args)
            try:
                with engine.connect() as connection:
                    for table in ("resumes", "extractions", "resume_fingerprints"):
                        owners = set(connection.scalars(text(f"SELECT candidate_id FROM {table}")))
                        checks.check(f"only survivors retain {table}", owners == {
                            kept["candidate_id"], fresh_row["candidate_id"]})
                    report_owners = set(connection.scalars(text("SELECT candidate_id FROM reports")))
                    assert not (report_owners & set(erased))
                    checks.check("candidate erasures retain no reports; resume-only report policy unchanged",
                                 len(report_owners) == 3)
            finally:
                engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
