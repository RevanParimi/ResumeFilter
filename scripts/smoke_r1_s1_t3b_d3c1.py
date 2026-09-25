"""Migrated HTTP/restart materialization consent-audit checks; synthetic erasure.

The scratch server injects erasure on a separate database session immediately
at the consent audit boundary. Competing-thread/lock evidence lives in pytest.
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
ADMIN = "synthetic-materialization-audit-admin"
GATE_APP = '''
from sqlalchemy import event
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.ledger.store import LedgerStore
from app.main import app

original = LedgerStore.materialization_consent
armed = None

def consent(self, candidate_id, **kwargs):
    global armed
    mode, armed = armed, None
    if mode:
        def erase(*_):
            factory = make_session_factory(self._session_factory.kw["bind"])
            assert CandidateStore(factory).delete_candidate(candidate_id)
        if mode == "before_check":
            erase()
        else:
            event.listen(self._session_factory, mode, erase, once=True)
    return original(self, candidate_id, **kwargs)

LedgerStore.materialization_consent = consent

@app.post("/_test/arm")
async def arm(mode: str):
    global armed
    assert mode in ("before_check", "before_flush", "after_commit")
    armed = mode
    return {"armed": True}
'''


def main():
    checks = Smoke("materialization audit erasure HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-materialization-audit-"))
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
            require(http.post("/features/materialize", headers={
                "X-API-Key": "wrong", "X-Org-Key": org["api_key"]}, json={}), 401)
            checks.check("organization key cannot materialize", True)
            for allowed in (False, True):
                for boundary in ("before_check", "before_flush", "after_commit"):
                    saved = require(http.post("/candidates", json=body(f"Subject{allowed}{boundary}")))
                    cid = saved["candidate_id"]
                    erased.append(cid)
                    if allowed:
                        require(http.post(f"/ledger/candidates/{cid}/consent", json={
                            "purpose": "ledger_read", "org_id": org["org"]["id"]}))
                    require(http.post("/_test/arm", params={"mode": boundary}))
                    payload = {"candidate_ids": [cid, "missing", kept["candidate_id"]]}
                    result = require(http.post("/features/materialize", json=payload))
                    checks.check(f"{allowed}/{boundary} skips erasure and continues survivor",
                                 (result["materialized"], result["skipped"]) == (1, 2))
                    require(http.get(f"/candidates/{cid}"), 404)
                    retry = require(http.post("/features/materialize", json=payload))
                    checks.check(f"{allowed}/{boundary} retry stays skipped",
                                 (retry["materialized"], retry["skipped"]) == (1, 2))
            checks.check("normal survivor materialization succeeds", require(http.post(
                "/features/materialize", json={"candidate_ids": [kept["candidate_id"]]}))["materialized"] == 1)

        with server(False) as http:
            require(http.get(f"/candidates/{kept['candidate_id']}"))
            for cid in erased:
                require(http.get(f"/candidates/{cid}"), 404)
            checks.check("restart preserves erasures and survivor", True)
            result = require(http.post("/features/materialize", json={
                "candidate_ids": [*erased, kept["candidate_id"]]}))
            checks.check("restart materialization still skips erased subjects",
                         (result["materialized"], result["skipped"]) == (1, len(erased)))
            args = {"connect_args": {"options": pg_options}} if pg_options else {}
            engine = create_engine(url, hide_parameters=True, **args)
            try:
                with engine.connect() as connection:
                    for table in ("audit_log", "ml_feature_vectors"):
                        owners = set(connection.scalars(text(
                            f"SELECT candidate_id FROM {table} WHERE candidate_id IS NOT NULL")))
                        checks.check(f"only survivor retains {table}", owners == {kept["candidate_id"]})
            finally:
                engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
