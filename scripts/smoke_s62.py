"""S6.2 smoke: boot uvicorn on a migrated scratch DB, create a candidate, ingest
a LinkedIn export (base64 zip built in-script), list it, verify canonical skills +
corroboration + canonical employers, then bad-base64 -> 422 and DPDP-erase ->
sources 404. No network, no LLM. Run from repo root: python scripts/smoke_s62.py
"""

import base64
import io
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from _smoke import base_env, wait_healthy

PORT = 8062
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
RESUME = "Dev\nEmail: dev@example.com\nSKILLS\nPython\n"


def _export_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Skills.csv", "Name\nPython\nDjango\nLeadership\n")
        zf.writestr(
            "Positions.csv",
            "Company Name,Title,Description,Started On,Finished On\n"
            "Infosys,Python Developer,Built Django APIs,Jan 2020,Dec 2021\n"
            "TCS,Engineer,Kubernetes work,Jan 2022,\n",
        )
        zf.writestr("Education.csv", "School Name,Degree Name\nIIT Madras,B.Tech\n")
        zf.writestr("Profile.csv", "Headline,Industry\nSenior Python Engineer,Information Technology\n")
    return base64.b64encode(buf.getvalue()).decode()



def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s62.db").as_posix()
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
    admin_h = {"X-API-Key": ADMIN}
    checks: dict[str, bool] = {}

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(60, connect=5)) as c:
            if not wait_healthy(c):
                print("FAIL server never became healthy")
                return 1

            cid = c.post("/candidates", json={"resume_text": RESUME, "evaluate": False},
                         headers=admin_h).json()["candidate_id"]

            r = c.post(f"/candidates/{cid}/sources/linkedin",
                       json={"export_b64": _export_b64()}, headers=admin_h)
            checks["POST linkedin -> 200"] = r.status_code == 200
            body = r.json() if r.status_code == 200 else {}
            checks["method == export"] = body.get("method") == "export"
            skills = {s["name"]: s for s in body.get("skills", [])}
            checks["python canonical"] = skills.get("Python", {}).get("canonical") == "python"
            checks["python corroborated (0.6)"] = skills.get("Python", {}).get("confidence") == 0.6
            checks["leadership base (0.4)"] = skills.get("Leadership", {}).get("confidence") == 0.4
            act = body.get("activity", {})
            checks["employers canonicalized"] = act.get("employers") == ["Infosys", "TCS"]
            checks["institutions canonicalized"] = act.get("institutions") == ["IIT Madras"]
            checks["current_positions == 1"] = act.get("current_positions") == 1

            lst = c.get(f"/candidates/{cid}/sources?source_type=linkedin_export", headers=admin_h)
            checks["GET linkedin sources -> 1 row"] = (
                lst.status_code == 200 and len(lst.json()["sources"]) == 1
            )

            bad = c.post(f"/candidates/{cid}/sources/linkedin",
                         json={"export_b64": "!!!not base64!!!"}, headers=admin_h)
            checks["bad base64 -> 422"] = bad.status_code == 422

            deleted = c.delete(f"/candidates/{cid}", headers=admin_h)
            checks["DPDP delete candidate -> 200"] = deleted.status_code == 200

            after = c.get(f"/candidates/{cid}/sources", headers=admin_h)
            checks["sources 404 after erasure"] = after.status_code == 404
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if any(not ok for ok in checks.values()):
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
