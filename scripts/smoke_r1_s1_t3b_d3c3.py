"""Migrated match/board HTTP erasure boundaries and restart inspection.

Synthetic local hooks erase through a separate session; controlled concurrent
thread and PostgreSQL lock evidence live in test_match_disclosure_erasure.py.
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
ADMIN = "synthetic-match-audit-admin"
GATE_APP = '''
from sqlalchemy import event
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.ledger.models import AuditLogRow
from app.matching import store as matching
from app.main import app

original = matching.JobStore.run_match
engine = matching._match_engine
armed = None
at_rank = None

def rank(*args):
    global at_rank
    result = engine(*args)
    hook, at_rank = at_rank, None
    if hook:
        hook()
    return result

def match(self, org_id, req_id, **kwargs):
    global armed, at_rank
    if armed and armed['req_id'] == req_id and self.get_requisition(org_id, req_id):
        config, armed = armed, None
        def erase(*_):
            factory = make_session_factory(self._session_factory.kw['bind'])
            for cid in config['ids']:
                assert CandidateStore(factory).delete_candidate(cid)
        if config['mode'] == 'ranked':
            at_rank = erase
        elif config['mode'] == 'invalid':
            def invalid(session, *_):
                for row in session.new:
                    if isinstance(row, AuditLogRow):
                        row.action = None
            event.listen(self._session_factory, 'before_flush', invalid, once=True)
        else:
            event.listen(self._session_factory, config['mode'], erase, once=True)
    return original(self, org_id, req_id, **kwargs)

matching.JobStore.run_match = match
matching._match_engine = rank

@app.post('/_test/arm')
async def arm(config: dict):
    global armed
    assert config['mode'] in ('ranked', 'before_flush', 'after_commit', 'invalid')
    armed = config
    return {'armed': True}
'''


def main():
    checks = Smoke("matching disclosure HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-match-audit-"))
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
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
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

        def seed(http, name, skills):
            return require(http.post("/candidates", json={"resume_text":
                f"{name}\nEmail: {name.lower()}@example.com\nSKILLS\n{skills}",
                "evaluate": False}))["candidate_id"]

        def call(http, req_id, route, headers, limit=None):
            path = f"/jobs/{req_id}/{route}"
            return (http.post(path, headers=headers, json={"limit": limit}) if route == "match"
                    else http.get(path, headers=headers))

        def match_body(response, route):
            body = require(response)
            return body if route == "match" else body["match"]

        erased = []
        with server(True) as http:
            checks.check("migrated application starts", True)
            org = require(http.post("/ledger/orgs", json={"name": "Synthetic matching agency"}))
            other = require(http.post("/ledger/orgs", json={"name": "Other agency"}))
            headers = {"X-Org-Key": org["api_key"]}
            req = require(http.post("/jobs", headers=headers, json={"title": "Engineer",
                "must_have_skills": ["python", "django"]}))
            kept = [seed(http, "Weak", "Python"), seed(http, "Other", "Java")]
            require(http.post("/features/materialize", json={}))
            for route in ("match", "board"):
                for boundary in ("ranked", "before_flush", "after_commit"):
                    cid = seed(http, f"Subject{route}{boundary}", "Python, Django")
                    erased.append(cid)
                    require(http.post("/features/materialize", json={"candidate_ids": [cid]}))
                    baseline = match_body(call(http, req["id"], route, headers), route)
                    assert baseline["ranked"][0]["candidate_id"] == cid
                    require(http.post("/_test/arm", json={"req_id": req["id"], "mode": boundary, "ids": [cid]}))
                    require(call(http, req["id"], route, {"X-Org-Key": other["api_key"]}), 404)
                    require(call(http, req["id"], route, {"X-Org-Key": ""}), 401)
                    body = match_body(call(http, req["id"], route, headers), route)
                    assert body["ranked"] == baseline["ranked"][1:]
                    assert (body["pool_size"], body["filtered_size"], body["advisory"]) == (2, 2, True)
                    checks.check(f"{route}/{boundary}: ownership, survivor ranking and counts", True)
                    require(http.get(f"/candidates/{cid}"), 404)
                    retry = match_body(call(http, req["id"], route, headers), route)
                    assert [m["candidate_id"] for m in retry["ranked"]] == kept
                    checks.check(f"{route}/{boundary}: retry stays erased", True)

            # A committed limit-one disclosure is never backfilled without audit.
            cid = seed(http, "Limited", "Python, Django")
            erased.append(cid)
            require(http.post("/features/materialize", json={"candidate_ids": [cid]}))
            require(http.post("/_test/arm", json={"req_id": req["id"], "mode": "after_commit", "ids": [cid]}))
            result = match_body(call(http, req["id"], "match", headers, 1), "match")
            checks.check("post-commit limit-one erasure does not disclose unaudited replacement",
                         result["ranked"] == [] and result["pool_size"] == 2)

            for route in ("match", "board"):
                require(http.post("/_test/arm", json={"req_id": req["id"], "mode": "invalid", "ids": []}))
                failed = call(http, req["id"], route, headers)
                assert failed.status_code == 500 and "INSERT INTO" not in failed.text
                assert len(match_body(call(http, req["id"], route, headers), route)["ranked"]) == 2
                checks.check(f"{route}: unrelated audit failure remains failure and retry recovers", True)

        with server(False) as http:
            for cid in erased:
                require(http.get(f"/candidates/{cid}"), 404)
            for route in ("match", "board"):
                result = match_body(call(http, req["id"], route, headers), route)
                assert [m["candidate_id"] for m in result["ranked"]] == kept
            checks.check("restart preserves both matching entry points and erasures", True)
            args = {"connect_args": {"options": pg_options}} if pg_options else {}
            engine = create_engine(url, hide_parameters=True, **args)
            try:
                with engine.connect() as connection:
                    for table in ("audit_log", "ml_feature_vectors"):
                        owners = set(connection.scalars(text(
                            f"SELECT candidate_id FROM {table} WHERE candidate_id IS NOT NULL")))
                        checks.check(f"only survivors retain {table}", owners == set(kept))
            finally:
                engine.dispose()
            for cid in kept:
                require(http.delete(f"/candidates/{cid}"))
            for route in ("match", "board"):
                result = match_body(call(http, req["id"], route, headers), route)
                assert result["pool_size"] == result["filtered_size"] == 0
                assert result["ranked"] == [] and result["reason"] == "no_materialized_candidates"
                checks.check(f"{route}: all erased uses existing empty response", True)
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
