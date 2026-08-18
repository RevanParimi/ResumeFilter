"""S8.1 smoke: the deployable spine, proved from nothing.

Unlike every prior smoke, this one does NOT pre-migrate. It hands uvicorn an
EMPTY database and lets the app migrate itself, because that is exactly what a
fresh container does.

The three checks this sprint exists to protect:
  * boots_and_migrates_from_empty — `alembic upgrade head` ran nowhere in the
    boot path until now (blocker 1), so a fresh container started against no
    schema at all.
  * admin_without_key_401 — a forgotten DEE_API_AUTH_KEY used to make all 27
    admin endpoints public, including the one that mints any candidate's access
    key. The empty credential is now the MOST refusing state.
  * erasure_cascades_the_report — reports used to live in a second database with
    no foreign key, swept only because two route handlers each remembered to.
    Now the database does it, and this check watches it happen over HTTP.

And the boot refusal is observed the way an operator meets it: a second uvicorn
started with no admin key EXITS, rather than serving an open plane.

No network, no LLM, no API key needed (extraction falls back to heuristics).

Run from repo root:                     python scripts/smoke_s81.py
Against Postgres:  DEE_CANDIDATES_DB_URL=postgresql+psycopg://... python scripts/smoke_s81.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

from _smoke import base_env, boot_until_exit, uvicorn_argv, wait_healthy

PORT = 8081
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"

RESUME = """Asha Rao
Email: asha.rao@example.com

EXPERIENCE
Senior ML Engineer at Acme AI - Mar 2021 - Jan 2024
Data Engineer at Globex Corp - Jan 2019 - Feb 2021

SKILLS
Python, PyTorch, Spark
"""



def _boot_without_admin_key(scratch: Path) -> bool:
    """The boot refusal, seen the way an operator sees it: as an exit code."""
    env = base_env(scratch, "sqlite:///" + (scratch / "refuse.db").as_posix())
    env["DEE_API_AUTH_KEY"] = ""
    code, out = boot_until_exit(uvicorn_argv(PORT + 1), env, timeout=60)
    # `> 0`, not `!= 0`: boot_until_exit reports a process still alive at the
    # deadline as -1, and a server that STAYED UP is the guard not firing.
    return code > 0 and "DEE_API_AUTH_KEY" in out


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    # An EMPTY database, deliberately NOT migrated here.
    url = os.environ.get("DEE_CANDIDATES_DB_URL") or (
        "sqlite:///" + (scratch / "smoke_s81.db").as_posix()
    )
    print(f"unmigrated scratch DB: {url}")

    env = base_env(scratch, url)
    env["DEE_API_AUTH_KEY"] = ADMIN
    admin_h = {"X-API-Key": ADMIN}
    checks: dict[str, bool] = {}

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            # 1. THE blocker-1 check: it migrated its own empty database.
            checks["boots_and_migrates_from_empty"] = wait_healthy(c)
            if not checks["boots_and_migrates_from_empty"]:
                print("server did not become healthy")
                return 1

            # 2-4. THE fail-closed checks, from outside the process.
            checks["admin_without_key_401"] = (
                c.post("/candidates", json={"resume_text": RESUME}).status_code == 401
            )
            checks["admin_with_wrong_key_401"] = (
                c.post("/candidates", json={"resume_text": RESUME},
                       headers={"X-API-Key": "nope"}).status_code == 401
            )
            checks["healthz_stays_open"] = c.get("/healthz").status_code == 200

            created = c.post("/candidates", json={"resume_text": RESUME},
                             headers=admin_h)
            checks["admin_with_key_200"] = created.status_code == 200
            body = created.json()
            cid, rid = body["candidate_id"], body["report"]["id"]

            # 5. the report round-trips out of the MAIN database now
            checks["report_readable"] = (
                c.get(f"/report/{rid}", headers=admin_h).status_code == 200
            )

            # 6. an ad-hoc /evaluate report has no subject and must survive
            free_id = c.post("/evaluate", json={"resume_text": RESUME},
                             headers=admin_h).json()["id"]

            # 7. THE fold check: erasure sweeps the report with no report-store
            #    orchestration left in the handler.
            erased = c.delete(f"/candidates/{cid}", headers=admin_h)
            checks["erasure_reports_what_it_removed"] = (
                erased.status_code == 200 and erased.json()["reports_deleted"] == 1
            )
            checks["erasure_cascades_the_report"] = (
                c.get(f"/report/{rid}", headers=admin_h).status_code == 404
            )
            checks["unattached_report_survives"] = (
                c.get(f"/report/{free_id}", headers=admin_h).status_code == 200
            )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    # 8. and the headline: no credential => the process refuses to start.
    checks["no_admin_key_refuses_to_boot"] = _boot_without_admin_key(scratch)

    ok_count = sum(checks.values())
    for name, passed in checks.items():
        print(f"  [{'OK' if passed else 'XX'}] {name}")
    print(f"{ok_count}/{len(checks)} checks OK")
    return 0 if ok_count == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
