"""S3.3 smoke: coding-round ingest over the ledger HTTP surface.

Migrates a scratch DB with Alembic, boots uvicorn with an admin key set, then:
create org (one-time key) → ingest a candidate → submit coding round WITHOUT
write consent (403) → grant write consent → submit (200) → query WITHOUT read
consent (403) → grant read consent → query (200, 1 result) → DPDP erase
candidate → query 404. LLM-free; heuristic extraction with no API key. Run from
the repo root:
    python scripts/smoke_s33.py
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")
PORT = 8033
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
TAKEN_AT = "2026-07-24T10:00:00+00:00"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s33.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update(
        {
            "DEE_CANDIDATES_DB_URL": url,
            "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
            "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
            "DEE_VECTORSTORE_BACKEND": "memory",
            "DEE_API_AUTH_KEY": ADMIN,
        }
    )
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

            created = c.post("/ledger/orgs", json={"name": "Coding Corp"},
                             headers=admin_h).json()
            org_id, org_key = created["org"]["id"], created["api_key"]
            org_h = {"X-Org-Key": org_key}
            print(f"org: {org_id[:8]} key issued")

            text = FIXTURE.read_text(encoding="utf-8")
            cand = c.post("/candidates", json={"resume_text": text}, headers=admin_h).json()
            cid = cand["candidate_id"]
            print(f"candidate [{cand['extraction_method']}]: {cid[:8]}")

            payload = {
                "candidate_id": cid, "platform": "hackerrank", "score": 740.0,
                "max_score": 850.0, "percentile": 88.0,
                "problem_tags": ["arrays", "dynamic-programming"],
                "taken_at": TAKEN_AT, "assessment_name": "SDE Screen",
            }
            refused = c.post("/ledger/coding-rounds", json=payload, headers=org_h)

            c.post(f"/ledger/candidates/{cid}/consent",
                   json={"purpose": "ledger_write", "org_id": org_id}, headers=admin_h)
            submitted = c.post("/ledger/coding-rounds", json=payload, headers=org_h)

            query_denied = c.get(f"/ledger/candidates/{cid}/coding-rounds", headers=org_h)

            c.post(f"/ledger/candidates/{cid}/consent",
                   json={"purpose": "ledger_read", "org_id": org_id}, headers=admin_h)
            query_ok = c.get(f"/ledger/candidates/{cid}/coding-rounds", headers=org_h)

            c.delete(f"/candidates/{cid}", headers=admin_h)
            query_after_erase = c.get(f"/ledger/candidates/{cid}/coding-rounds", headers=org_h)

        checks = {
            "org created with one-time key": bool(org_key),
            "submit without write consent 403": refused.status_code == 403,
            "submit with consent 200": submitted.status_code == 200,
            "submitted result has percentile": submitted.status_code == 200
            and submitted.json().get("percentile") == 88.0,
            "query without read consent 403": query_denied.status_code == 403,
            "query with read consent returns 1 result": query_ok.status_code == 200
            and len(query_ok.json()) == 1,
            "query after DPDP erasure 404": query_after_erase.status_code == 404,
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"  {'OK  ' if ok else 'FAIL'} {name}")
        if failed:
            return 1
        print("\nSMOKE OK")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=15)


if __name__ == "__main__":
    sys.exit(main())
