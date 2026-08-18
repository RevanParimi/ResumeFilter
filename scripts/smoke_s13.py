"""S1.3 smoke: the real HTTP surface end to end.

Migrates a scratch candidate DB with Alembic, boots uvicorn with env-overridden
store paths, then drives: POST /candidates (auto depth-eval) → identity match on
re-upload → candidate/resume/report reads → DPDP resume + candidate deletes →
verifies linked reports are erased. Works with a live key (LLM extraction) and
without one (heuristic floor + rule-driven eval). Run from the repo root:
    python scripts/smoke_s13.py
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
PORT = 8013
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"   # S8.1: the admin plane fails closed


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s13.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = base_env()
    env.update(
        {
            "DEE_API_AUTH_KEY": ADMIN,
            "DEE_CANDIDATES_DB_URL": url,
            "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
            "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
            # Chroma init can hang on some machines; the smoke stays bounded.
            "DEE_VECTORSTORE_BACKEND": "memory",
            # Key-less BY CONSTRUCTION. This repo's .env carries a real key, so
            # without this a bare run makes live BILLED calls (~72s/candidate)
            # from a smoke that claims to prove the no-key path. S7.3 recorded
            # exactly this trap once already; twice is how it becomes permanent.
            "DEE_OPENROUTER_API_KEY": "",
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    try:
        with httpx.Client(base_url=BASE, headers={"X-API-Key": ADMIN}, timeout=httpx.Timeout(180, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            text = FIXTURE.read_text(encoding="utf-8")
            first = c.post("/candidates", json={"resume_text": text}).json()
            cid = first["candidate_id"]
            print(
                f"POST /candidates #1 [{first['extraction_method']}]: "
                f"candidate={cid[:8]} v{first['resume_version']} "
                f"report={first['report']['id']}"
            )

            second = c.post(
                "/candidates",
                json={"resume_text": text + "\n\nUpdate: AWS certification added."},
            ).json()
            print(
                f"POST /candidates #2: matched={second['matched_existing']} "
                f"on={second['matched_on']} v{second['resume_version']}"
            )

            detail = c.get(f"/candidates/{cid}").json()
            resumes = c.get(f"/candidates/{cid}/resumes").json()
            reports = c.get(f"/candidates/{cid}/reports").json()

            del_resume = c.delete(
                f"/candidates/{cid}/resumes/{second['resume_id']}"
            )
            del_cand = c.delete(f"/candidates/{cid}")
            report_after = c.get(f"/report/{first['report']['id']}")
            cand_after = c.get(f"/candidates/{cid}")

        checks = {
            "upload created candidate + advisory report": bool(cid)
            and first["report"]["advisory"] is True
            and first["report"]["human_review_required"] is True,
            "report linked to candidate": first["report"]["candidate_id"] == cid,
            "re-upload matched identity": second["candidate_id"] == cid
            and second["matched_existing"] is True,
            "re-upload became resume v2": second["resume_version"] == 2,
            "detail exposes latest profile": detail["latest_profile"] is not None,
            "two resume versions listed": [
                r["version"] for r in resumes["resumes"]
            ] == [1, 2],
            "both reports listed for candidate": len(reports) == 2,
            "DPDP resume delete ok": del_resume.status_code == 200,
            "DPDP candidate delete erased reports": del_cand.status_code == 200
            and del_cand.json()["reports_deleted"] == 2,
            "linked report 404 after erasure": report_after.status_code == 404,
            "candidate 404 after erasure": cand_after.status_code == 404,
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
