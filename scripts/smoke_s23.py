"""S2.3 smoke: resume-farm detection visible over the real HTTP surface.

Boots uvicorn on a scratch, Alembic-migrated SQLite DB and walks the farm
story end to end: first upload of a template is unique; an identity-swapped
copy from a "different" candidate lands near_duplicate with the match pointing
back at the first candidate; the uploader's own re-upload dedupes and never
matches itself (though it rightly matches B); a genuine resume stays unique;
POST /evaluate carries no farm assessment.
Works with a live key (LLM extraction) and without one (heuristic floor).
Run from the repo root:
    python scripts/smoke_s23.py
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

FARM_A = Path("tests/fixtures/farm_genai_resume_a.txt")
FARM_B = Path("tests/fixtures/farm_genai_resume_b.txt")
GENUINE = Path("tests/fixtures/genuine_genai_resume.txt")
PORT = 8023
BASE = f"http://127.0.0.1:{PORT}"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s23.db").as_posix()
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
            # Chroma init can hang on some machines; the smoke stays bounded.
            "DEE_VECTORSTORE_BACKEND": "memory",
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(600, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            text_a = FARM_A.read_text(encoding="utf-8")
            text_b = FARM_B.read_text(encoding="utf-8")
            text_g = GENUINE.read_text(encoding="utf-8")

            first = c.post("/candidates", json={"resume_text": text_a, "domain": "genai"}).json()
            print(f"upload A: candidate={first.get('candidate_id', '?')} "
                  f"farm_band={(first.get('resume_farm') or {}).get('band', '?')}")
            second = c.post("/candidates", json={"resume_text": text_b, "domain": "genai"}).json()
            print(f"upload B (identity-swapped copy): candidate={second.get('candidate_id', '?')} "
                  f"farm_band={(second.get('resume_farm') or {}).get('band', '?')}")
            re_up = c.post("/candidates", json={"resume_text": text_a, "domain": "genai"}).json()
            print(f"re-upload A: duplicate={re_up.get('duplicate_resume')} "
                  f"farm_band={(re_up.get('resume_farm') or {}).get('band', '?')}")
            genuine = c.post("/candidates", json={"resume_text": text_g, "domain": "genai"}).json()
            print(f"upload genuine: farm_band={(genuine.get('resume_farm') or {}).get('band', '?')}")
            adhoc = c.post("/evaluate", json={"resume_text": text_a, "domain": "genai"}).json()
            print(f"POST /evaluate: resume_farm={adhoc.get('resume_farm')}")

        farm_b = second.get("resume_farm") or {}
        matches = farm_b.get("matches") or [{}]
        rep_b = second.get("report") or {}
        checks = {
            "first upload: band unique (empty corpus)": (first.get("resume_farm") or {}).get("band")
            == "unique",
            "copy: two distinct candidates": second.get("candidate_id") != first.get("candidate_id"),
            "copy: band near_duplicate": farm_b.get("band") == "near_duplicate",
            "copy: match points at the first candidate": matches[0].get("candidate_id")
            == first.get("candidate_id"),
            "copy: report carries the assessment": (rep_b.get("resume_farm") or {}).get("band")
            == "near_duplicate",
            "copy: summary carries the advisory note": "never a rejection signal"
            in rep_b.get("summary", ""),
            "re-upload: same candidate, resume deduped": re_up.get("candidate_id")
            == first.get("candidate_id")
            and re_up.get("duplicate_resume") is True,
            "re-upload: self never among matches (B legitimately is)": all(
                m.get("candidate_id") != first.get("candidate_id")
                for m in (re_up.get("resume_farm") or {}).get("matches", [])
            ),
            "genuine: stays unique next to the farm": (genuine.get("resume_farm") or {}).get("band")
            == "unique",
            "/evaluate: no farm assessment (no identity)": adhoc.get("resume_farm") is None,
            "mandates hold (advisory + human review)": rep_b.get("advisory") is True
            and rep_b.get("human_review_required") is True,
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
