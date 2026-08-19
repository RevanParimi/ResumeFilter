"""S3.4 smoke: advisory cross-company reputation over the ledger HTTP surface.

Migrates a scratch DB, boots uvicorn with an admin key, then:
create 2 orgs (A, B) + keys -> ingest a candidate -> grant ledger_write to each
-> A and B each submit a couple of favorable interview records + a coding round
-> reputation query WITHOUT read consent (403) -> grant ledger_read -> query
(200: corroborated band, score > 0.5) -> admin lowers B's reliability, re-query
(200, coherent shift) -> DPDP-erase candidate -> reputation 404. LLM-free;
heuristic extraction with no API key. Run from the repo root:
    python scripts/smoke_s34.py
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from _smoke import base_env

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")
PORT = 8034
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
AT = "2026-07-24T10:00:00+00:00"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s34.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = base_env()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_API_AUTH_KEY": ADMIN,
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    try:
        admin_h = {"X-API-Key": ADMIN}
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            orgs = {}
            for name in ("Org A", "Org B"):
                created = c.post("/ledger/orgs", json={"name": name},
                                 headers=admin_h).json()
                orgs[name] = (created["org"]["id"], created["api_key"])
            reader = c.post("/ledger/orgs", json={"name": "Reader Co"},
                            headers=admin_h).json()
            reader_id, reader_key = reader["org"]["id"], reader["api_key"]
            reader_h = {"X-Org-Key": reader_key}

            text = FIXTURE.read_text(encoding="utf-8")
            cand = c.post("/candidates", json={"resume_text": text}, headers=admin_h).json()
            cid = cand["candidate_id"]
            print(f"candidate [{cand['extraction_method']}]: {cid[:8]}")

            for name, (oid, okey) in orgs.items():
                oh = {"X-Org-Key": okey}
                c.post(f"/ledger/candidates/{cid}/consent",
                       json={"purpose": "ledger_write", "org_id": oid}, headers=admin_h)
                for _ in range(2):
                    c.post("/ledger/records",
                           json={"candidate_id": cid, "stage": "hm",
                                 "outcome": "hired", "interviewed_at": AT}, headers=oh)
                c.post("/ledger/coding-rounds",
                       json={"candidate_id": cid, "platform": "hackerrank",
                             "score": 90.0, "max_score": 100.0, "percentile": 92.0,
                             "taken_at": AT}, headers=oh)

            denied = c.get(f"/ledger/candidates/{cid}/reputation", headers=reader_h)

            c.post(f"/ledger/candidates/{cid}/consent",
                   json={"purpose": "ledger_read", "org_id": reader_id}, headers=admin_h)
            ok = c.get(f"/ledger/candidates/{cid}/reputation", headers=reader_h)
            rep = ok.json() if ok.status_code == 200 else {}
            if rep:
                print(f"reputation: band={rep.get('band')} score={rep.get('score'):.3f} "
                      f"orgs={rep.get('distinct_orgs')} obs={rep.get('total_observations')}")

            # lower Org B's reliability and re-query (score should stay valid, shift)
            b_id = orgs["Org B"][0]
            rel = c.post(f"/ledger/orgs/{b_id}/reliability", json={"weight": 0.2},
                         headers=admin_h)
            ok2 = c.get(f"/ledger/candidates/{cid}/reputation", headers=reader_h)
            rep2 = ok2.json() if ok2.status_code == 200 else {}

            c.delete(f"/candidates/{cid}", headers=admin_h)
            after = c.get(f"/ledger/candidates/{cid}/reputation", headers=reader_h)

        checks = {
            "reputation without read consent 403": denied.status_code == 403,
            "reputation with read consent 200": ok.status_code == 200,
            "corroborated across 2 orgs": rep.get("distinct_orgs") == 2,
            "band favorable or strong": rep.get("band") in {"favorable", "strong"},
            "score above neutral prior": rep.get("score", 0) > 0.5,
            "assessment is advisory": rep.get("advisory") is True,
            "reliability set 200": rel.status_code == 200,
            "reliability shift keeps valid score": ok2.status_code == 200
            and 0.0 <= rep2.get("score", -1) <= 1.0,
            "reputation after DPDP erasure 404": after.status_code == 404,
        }
        failed = [name for name, v in checks.items() if not v]
        for name, v in checks.items():
            print(f"  {'OK  ' if v else 'FAIL'} {name}")
        if failed:
            return 1
        print("\nSMOKE OK")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=15)


if __name__ == "__main__":
    sys.exit(main())
