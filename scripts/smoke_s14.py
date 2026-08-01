"""S1.4 smoke: India normalization visible over the real HTTP surface.

Migrates a scratch DB, boots uvicorn, uploads the fixture resume (with a
notice-period line injected into the header), then verifies the stored
latest_profile carries canonical skills / degree / CGPA / institution /
employer / city / notice-period. evaluate=false — S1.4 is extraction +
normalization, so no depth-eval tokens are spent. Works with a live key
(LLM extraction) and without one (heuristic floor). Run from the repo root:
    python scripts/smoke_s14.py
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
PORT = 8014
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"   # S8.1: the admin plane fails closed


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s14.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
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

            base_text = FIXTURE.read_text(encoding="utf-8")
            text = base_text.replace(
                "\n\nEXPERIENCE", "\nNotice Period: 30 days\n\nEXPERIENCE", 1
            )
            created = c.post(
                "/candidates", json={"resume_text": text, "evaluate": False}
            ).json()
            cid = created["candidate_id"]
            print(
                f"POST /candidates [{created['extraction_method']}]: candidate={cid[:8]}"
            )

            detail = c.get(f"/candidates/{cid}").json()
            lp = detail["latest_profile"]
            edu = (lp.get("education") or [{}])[0]
            contact = lp.get("contact") or {}
            skills = {s.get("canonical") for s in lp.get("skills") or []}
            employers = {
                e.get("employer_canonical") for e in lp.get("experience") or []
            }

            deleted = c.delete(f"/candidates/{cid}")
            gone = c.get(f"/candidates/{cid}")

        checks = {
            "degree canonicalized (btech / bachelor)": edu.get("degree_canonical")
            == "btech"
            and edu.get("degree_level") == "bachelor",
            "CGPA normalized on 10-point scale": edu.get("grade_cgpa_10") == 8.6,
            "institution canonical + tier": edu.get("institution_canonical")
            == "NIT Trichy"
            and edu.get("institution_tier") == "tier_2",
            "employers canonicalized": {"Flipkart", "Infosys"} <= employers,
            "skills mapped to taxonomy": {
                "python", "sql", "apache_spark", "kafka", "airflow", "aws"
            } <= skills,
            "city normalized (Bengaluru metro)": contact.get("location_city")
            == "Bengaluru"
            and contact.get("location_tier") == "metro",
            "notice period parsed (30 days)": lp.get("notice_period_days") == 30,
            "DPDP delete still green": deleted.status_code == 200
            and gone.status_code == 404,
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
