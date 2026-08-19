"""S2.2 smoke: cross-field forensics visible over the real HTTP surface.

Boots uvicorn on a scratch environment and exercises BOTH profile paths:
POST /candidates (extracted profile passed into the graph) and POST /evaluate
(heuristic-profile fallback inside the cross_field node). The inconsistent
fixture must surface explained findings on report.cross_field; the genuine
fixture must never reach major_issues; advisory mandates must hold. Works with
a live key (LLM extraction) and without one (heuristic floor). Run from the
repo root:
    python scripts/smoke_s22.py
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

INCONSISTENT_FIXTURE = Path("tests/fixtures/inconsistent_genai_resume.txt")
GENUINE_FIXTURE = Path("tests/fixtures/genuine_genai_resume.txt")
PORT = 8022
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"   # S8.1: the admin plane fails closed


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s22.db").as_posix()
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
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    try:
        with httpx.Client(base_url=BASE, headers={"X-API-Key": ADMIN}, timeout=httpx.Timeout(600, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            bad_text = INCONSISTENT_FIXTURE.read_text(encoding="utf-8")
            good_text = GENUINE_FIXTURE.read_text(encoding="utf-8")

            cand = c.post(
                "/candidates",
                json={"resume_text": bad_text, "domain": "genai", "evaluate": True},
            ).json()
            cand_rep = cand.get("report") or {}
            print(
                f"POST /candidates (inconsistent): candidate={cand.get('candidate_id', '?')} "
                f"extraction={cand.get('extraction_method', '?')} report={cand_rep.get('id', '?')}"
            )
            eval_rep = c.post(
                "/evaluate", json={"resume_text": bad_text, "domain": "genai"}
            ).json()
            print(f"POST /evaluate (inconsistent, heuristic fallback): report={eval_rep.get('id', '?')}")
            good_rep = c.post(
                "/evaluate", json={"resume_text": good_text, "domain": "genai"}
            ).json()
            print(f"POST /evaluate (genuine): report={good_rep.get('id', '?')}")

        cxf = cand_rep.get("cross_field") or {}
        exf = eval_rep.get("cross_field") or {}
        gxf = good_rep.get("cross_field") or {}
        checks = {
            "/candidates path: assessment present": bool(cxf),
            "/candidates path: band minor/major issues": cxf.get("band")
            in {"minor_issues", "major_issues"},
            "/candidates path: >=2 findings, all explained": len(cxf.get("findings", [])) >= 2
            and all(f.get("detail") for f in cxf.get("findings", [])),
            "/candidates path: timeline_overlap among findings": "timeline_overlap"
            in {f.get("id") for f in cxf.get("findings", [])},
            "/evaluate path (no stored profile): assessment present": bool(exf),
            "/evaluate path: major issues via heuristic fallback": exf.get("band")
            == "major_issues",
            "major band carries the advisory summary note": (
                "never a rejection signal" in eval_rep.get("summary", "")
                if exf.get("band") == "major_issues"
                else True
            ),
            "genuine fixture: never major_issues": gxf.get("band") != "major_issues",
            "mandates hold (advisory + human review)": eval_rep.get("advisory") is True
            and eval_rep.get("human_review_required") is True,
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
