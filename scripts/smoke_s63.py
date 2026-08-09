"""S6.3 smoke: boot uvicorn on a migrated scratch DB, ingest a LinkedIn export
containing novel skills, verify they queue for curation, resolve them
(create / map / ignore), re-ingest and confirm the overlay now maps them, then
prove the queue is candidate-agnostic (survives DPDP erasure). No network, no
LLM. Run from repo root: python scripts/smoke_s63.py
"""

import base64
import io
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

PORT = 8063
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
RESUME = "Dev\nEmail: dev@example.com\nSKILLS\nPython\n"


def _export_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Skills.csv", "Name\nPython\nCOBOL\nPyTorch Lightning\nTeam Player\n")
        zf.writestr("Profile.csv", "Headline,Industry\nEngineer,Information Technology\n")
    return base64.b64encode(buf.getvalue()).decode()


def _wait_healthy(c) -> bool:
    for _ in range(60):
        try:
            if c.get("/healthz").status_code == 200:
                return True
        except httpx.TransportError:
            time.sleep(0.5)
    return False


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s63.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        # Pinned EMPTY on purpose: this smoke ingests resumes through the
        # extractor, and a developer with a real key in .env would otherwise
        # ship live billed calls from a test run. S8.4 Phase A found five
        # smokes doing exactly that; this one was not on that list and had the
        # same hole (S8.4 Phase B, Task 10).
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_API_AUTH_KEY": ADMIN,
    })
    admin_h = {"X-API-Key": ADMIN}
    checks: dict[str, bool] = {}

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(60, connect=5)) as c:
            if not _wait_healthy(c):
                print("FAIL server never became healthy")
                return 1

            cid = c.post("/candidates", json={"resume_text": RESUME, "evaluate": False},
                         headers=admin_h).json()["candidate_id"]

            r = c.post(f"/candidates/{cid}/sources/linkedin",
                       json={"export_b64": _export_b64()}, headers=admin_h)
            checks["POST linkedin -> 200"] = r.status_code == 200

            # S8.4 Phase B: this endpoint now answers UnmappedPage{terms, next_cursor}
            # rather than a bare list -- the curation queue is cursor-paged.
            pend = c.get("/curation/skills/unmapped?status=pending", headers=admin_h).json()
            pkeys = {t["norm_key"] for t in pend["terms"]}
            checks["cobol queued pending"] = "cobol" in pkeys
            checks["pytorch lightning queued pending"] = "pytorch lightning" in pkeys
            checks["team player queued pending"] = "team player" in pkeys

            r1 = c.post("/curation/skills/resolve", headers=admin_h, json={
                "norm_key": "cobol", "action": "create",
                "canonical": "cobol", "category": "language"})
            checks["resolve create cobol -> 200"] = r1.status_code == 200
            r2 = c.post("/curation/skills/resolve", headers=admin_h, json={
                "norm_key": "pytorch lightning", "action": "map", "canonical": "pytorch"})
            checks["resolve map pytorch -> 200"] = r2.status_code == 200
            checks["map derived category ml"] = r2.json().get("category") == "ml"
            r3 = c.post("/curation/skills/resolve", headers=admin_h, json={
                "norm_key": "team player", "action": "ignore"})
            checks["resolve ignore -> 200"] = r3.status_code == 200

            bad = c.post("/curation/skills/resolve", headers=admin_h, json={
                "norm_key": "nope", "action": "ignore"})
            checks["resolve unknown -> 404"] = bad.status_code == 404
            bad2 = c.post("/curation/skills/resolve", headers=admin_h, json={
                "norm_key": "cobol", "action": "map", "canonical": "not_real"})
            # cobol is already resolved, but validation runs after existence: map to
            # unknown canonical is 422.
            checks["resolve invalid -> 422"] = bad2.status_code == 422

            # re-ingest: overlay now maps cobol + pytorch lightning; team player stays unmapped
            r = c.post(f"/candidates/{cid}/sources/linkedin",
                       json={"export_b64": _export_b64()}, headers=admin_h)
            skills = {s["name"]: s for s in r.json().get("skills", [])}
            checks["COBOL now canonical cobol"] = skills.get("COBOL", {}).get("canonical") == "cobol"
            checks["PyTorch Lightning now pytorch"] = (
                skills.get("PyTorch Lightning", {}).get("canonical") == "pytorch")
            checks["Team Player still unmapped"] = skills.get("Team Player", {}).get("canonical") is None

            still_pending = {t["norm_key"] for t in
                             c.get("/curation/skills/unmapped?status=pending",
                                   headers=admin_h).json()["terms"]}
            checks["nothing re-queued pending"] = not (
                {"cobol", "pytorch lightning", "team player"} & still_pending)

            # DPDP: erasing the candidate must NOT sweep the candidate-agnostic queue
            deleted = c.delete(f"/candidates/{cid}", headers=admin_h)
            checks["DPDP delete candidate -> 200"] = deleted.status_code == 200
            all_terms = {t["norm_key"] for t in
                         c.get("/curation/skills/unmapped", headers=admin_h).json()["terms"]}
            checks["queue survives erasure"] = {"cobol", "pytorch lightning", "team player"} <= all_terms
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
