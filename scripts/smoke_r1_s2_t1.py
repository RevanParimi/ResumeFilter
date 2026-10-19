"""Current consent vs historical serving on migrated scratch SQLite/PostgreSQL.

Uses the real app with refusing external providers. Expiry is a deterministic
fixture change to a scratch grant after active materialization, not a sleep.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, update

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database
from app.features.store import FeatureStore
from app.core.db import make_session_factory
from app.ledger.models import ConsentGrantRow

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-current-consent-admin"
RANKING = {"terms": [{"feature": name, "weight": 1} for name in
                     ("candidate.num_skills", "reputation.score")]}


def main():
    checks = Smoke("current consent serving HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-consent-serving-"))
    print(f"Synthetic artifacts: {scratch}")
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
            "PYTHONPATH": str(ROOT / "src"), "NO_PROXY": "127.0.0.1,localhost",
            "PGOPTIONS": pg_options,
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        @contextmanager
        def server():
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(uvicorn_argv(port), env=env, cwd=scratch,
                                        stdout=log, stderr=subprocess.STDOUT,
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

        def search(http, cutoff, *, op=None):
            body = {"ranking": RANKING, "as_of": cutoff}
            if op:
                body["filters"] = [{"feature": "ledger.interview_record_count", "op": op,
                                    "value": 0 if op == "gte" else None}]
            return require(http.post("/talent/search", json=body))

        engine = create_engine(url, hide_parameters=True,
                               connect_args={"options": pg_options} if pg_options else {})
        try:
            features = FeatureStore(make_session_factory(engine))
            with server() as http:
                checks.check("real migrated app starts", True)
                orgs = [require(http.post("/ledger/orgs", json={"name": f"Synthetic {name}"}))
                        for name in ("A", "B")]
                headers = [{"X-Org-Key": org["api_key"]} for org in orgs]
                ids, grants, jobs = [], [], []
                for name, org, org_headers in zip(("A", "B"), orgs, headers):
                    cid = require(http.post("/candidates", json={"resume_text":
                        f"Candidate {name}\nEmail: consent-{name.lower()}@example.com\nSKILLS\nPython\n"}))[
                            "candidate_id"]
                    ids.append(cid)
                    grants.append(require(http.post(f"/ledger/candidates/{cid}/consent", json={
                        "purpose": "ledger_read", "org_id": org["org"]["id"],
                        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                    })))
                    jobs.append(require(http.post("/jobs", headers=org_headers, json={
                        "title": f"Engineer {name}", "must_have_skills": ["python"],
                    })))
                batch = require(http.post("/features/materialize", json={}))
                cutoff = batch["as_of"]
                checks.check("both active snapshots materialize", batch["materialized"] == 2)
                before = search(http, cutoff)
                checks.check("active platform search includes gated contributions", before["pool_size"] == 2
                             and all(r["coverage"] == 1 and len(r["contributions"]) == 2 for r in before["ranked"]))
                checks.check("active gated filter includes both", search(http, cutoff, op="gte")["filtered_size"] == 2)
                card = require(http.get(f"/candidates/{ids[0]}/card", headers=headers[1]))
                checks.check("other org cannot read candidate A reputation", card["reputation"]["status"] == "consent_required")
                require(http.post(f"/ledger/consent/{grants[0]['id']}/revoke"))
                after = search(http, cutoff)
                rows = {r["candidate_id"]: r for r in after["ranked"]}
                checks.check("historical cut cannot restore revoked contribution", rows[ids[0]]["coverage"] == 0.5
                             and [c["feature"] for c in rows[ids[0]]["contributions"]] == ["candidate.num_skills"])
                checks.check("other candidate retains current permission", rows[ids[1]]["coverage"] == 1)
                checks.check("revoked candidate cannot satisfy gated filter", [r["candidate_id"] for r in
                             search(http, cutoff, op="gte")["ranked"]] == ids[1:])
                # Age only the owned scratch grant to the already-materialized
                # instant. Both DBs use an actual current clock on the next HTTP read.
                with engine.begin() as conn:
                    conn.execute(update(ConsentGrantRow).where(ConsentGrantRow.id == grants[1]["id"])
                                 .values(expires_at=datetime.fromisoformat(cutoff)))
                expired = search(http, cutoff)
                checks.check("expiry masks both candidates without losing first-party scores",
                             expired["pool_size"] == 2 and all(r["coverage"] == 0.5
                             and r["score"] == 0.5 for r in expired["ranked"]))
                checks.check("expired gated exists filter is empty", search(http, cutoff, op="exists")["filtered_size"] == 0)
                checks.check("withheld missing filter includes both", search(http, cutoff, op="missing")["filtered_size"] == 2)
                for index, (job, org_headers) in enumerate(zip(jobs, headers)):
                    match = require(http.post(f"/jobs/{job['id']}/match", headers=org_headers,
                                              json={"as_of": cutoff}))
                    checks.check(f"org {index} first-party matching survives", match["advisory"]
                                 and match["pool_size"] == 2 and all(r["score"] == 1 for r in match["ranked"]))
                    board = require(http.get(f"/jobs/{job['id']}/board", headers=org_headers,
                                             params={"as_of": cutoff}))
                    checks.check(f"org {index} dashboard matching agrees", board["match"]["pool_size"] == 2)
                    card = require(http.get(f"/candidates/{ids[index]}/card", headers=org_headers))
                    checks.check(f"org {index} card respects revoked or expired read", card["reputation"]["status"] == "consent_required")
                require(http.post(f"/jobs/{jobs[0]['id']}/match", headers=headers[1], json={"as_of": cutoff}), 404)
                checks.check("other org cannot match another org job", True)
                raw = features.vectors_for_view("core_v1", 1, as_of=datetime.fromisoformat(cutoff))
                checks.check("serving preserved historical values and cached evidence", len(raw) == 2
                             and all(mv.consent_state["allowed"] and mv.vector.values["reputation.score"] is not None
                                     for mv in raw))
            with server() as http:
                checks.check("restart preserves current denial at historical cut", all(r["coverage"] == 0.5
                             for r in search(http, cutoff)["ranked"]))
                checks.check("restart gated filter remains empty", search(http, cutoff, op="exists")["filtered_size"] == 0)
                match = require(http.post(f"/jobs/{jobs[0]['id']}/match", headers=headers[0], json={"as_of": cutoff}))
                checks.check("restart preserves first-party matching", match["pool_size"] == 2)
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
