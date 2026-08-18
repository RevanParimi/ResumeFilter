"""S6.1 smoke: boot uvicorn on a migrated scratch DB, create a candidate, ingest
a GitHub profile source (handle=octocat), list it, then DPDP-erase the candidate
and confirm the sources 404. Hits the LIVE public GitHub API; robust to
rate-limit/offline (asserts the endpoint returns 200 with method in {api,
unavailable} and that erasure sweeps the source). Run from repo root:
python scripts/smoke_s61.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from _smoke import base_env, wait_healthy

PORT = 8061
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
RESUME = "Dev\nEmail: dev@example.com\nSKILLS\nPython\n"



def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s61.db").as_posix()
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

            r = c.post(f"/candidates/{cid}/sources/github",
                       json={"handle": "octocat"}, headers=admin_h)
            checks["POST github source -> 200"] = r.status_code == 200
            body = r.json() if r.status_code == 200 else {}
            method = body.get("method")
            checks["method in {api, unavailable}"] = method in {"api", "unavailable"}
            if method == "api":
                checks["api signal has activity.public_repos >= 0"] = (
                    body.get("activity", {}).get("public_repos", -1) >= 0
                )
            else:
                print("  NOTE  live GitHub fetch unavailable (rate-limit/offline) — "
                      "endpoint contract still verified")

            lst = c.get(f"/candidates/{cid}/sources", headers=admin_h)
            checks["GET sources -> 200, one row"] = (
                lst.status_code == 200 and len(lst.json()["sources"]) == 1
            )

            no_handle = c.post(f"/candidates/{cid}/sources/github", json={}, headers=admin_h)
            checks["no-handle (no github link) -> 400"] = no_handle.status_code == 400

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
