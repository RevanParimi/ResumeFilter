"""S6.4 smoke: boot uvicorn on a migrated scratch DB, mint a candidate key, walk
the DPDP portal — access (my-data + retention posture), transparency (who
accessed my data), first-party consent grant/revoke, cross-candidate isolation,
and self-service erasure (the key dies). No network, no LLM.
Run from repo root: python scripts/smoke_s64.py
"""

import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from _smoke import base_env, wait_healthy

PORT = 8064
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
RESUME = "Dev\nEmail: dev@example.com\nSKILLS\nPython\n"



def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s64.db").as_posix()
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
        # Key-less BY CONSTRUCTION: this repo's .env carries a real key,
        # so without this a bare run makes live BILLED calls from a smoke
        # that claims to prove the no-key path (S7.3 recorded this trap).
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
            if not wait_healthy(c):
                print("server did not become healthy")
                return 1

            # 1. create candidate + mint key
            cid = c.post("/candidates", headers=admin_h,
                         json={"resume_text": RESUME, "evaluate": False}).json()["candidate_id"]
            key = c.post(f"/candidates/{cid}/auth-key", headers=admin_h).json()["access_key"]
            ch = {"X-Candidate-Key": key}
            checks["mint_key"] = bool(key)

            # 2. /portal/me — access view + retention posture, reports are refs
            me = c.get("/portal/me", headers=ch).json()
            checks["me_profile_resumes"] = me["candidate_id"] == cid and len(me["resumes"]) == 1
            # sweep_active is TRUE since S8.3 Phase B -- the mechanical purge
            # exists, and this value is derived from retention_sweep_enabled
            # rather than the literal it was when this smoke was written.
            checks["me_retention_posture"] = (
                me["retention"]["sweep_active"] is True and bool(me["retention"]["windows"])
            )

            # 3. org submits + reads under consent
            org = c.post("/ledger/orgs", headers=admin_h, json={"name": "Acme"}).json()
            org_id, org_key = org["org"]["id"], org["api_key"]
            org_h = {"X-Org-Key": org_key}
            for purpose in ("ledger_write", "ledger_read"):
                c.post(f"/ledger/candidates/{cid}/consent", headers=admin_h,
                       json={"purpose": purpose, "org_id": org_id})
            c.post("/ledger/records", headers=org_h, json={
                "candidate_id": cid, "stage": "tech", "outcome": "advanced",
                "interviewed_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            })
            c.get(f"/ledger/candidates/{cid}/records", headers=org_h)

            # 4. /portal/access-log — the org's read + submit are visible, named
            log = c.get("/portal/access-log", headers=ch).json()
            actions = {e["action"] for e in log}
            q = next((e for e in log if e["action"] == "record.query"), {})
            checks["access_log_shows_disclosure"] = (
                {"record.query", "record.submit"} <= actions
                and q.get("actor_name") == "Acme" and q.get("allowed") is True
            )

            # 5. first-party grant + list + revoke
            gid = c.post("/portal/consents", headers=ch, json={"purpose": "ledger_read"}).json()["id"]
            rv = c.post(f"/portal/consents/{gid}/revoke", headers=ch).json()
            states = {v["grant"]["id"]: v["state"] for v in c.get("/portal/consents", headers=ch).json()}
            checks["grant_then_revoke"] = rv["revoked"] is True and states[gid] == "revoked"

            # 6. wrong/absent key 401; a second candidate can't touch the first
            checks["no_key_401"] = c.get("/portal/me").status_code == 401
            cid2 = c.post("/candidates", headers=admin_h,
                          json={"resume_text": RESUME.replace("dev@", "two@"), "evaluate": False}
                          ).json()["candidate_id"]
            key2 = c.post(f"/candidates/{cid2}/auth-key", headers=admin_h).json()["access_key"]
            g1 = c.post("/portal/consents", headers=ch, json={"purpose": "ledger_read"}).json()["id"]
            cross = c.post(f"/portal/consents/{g1}/revoke", headers={"X-Candidate-Key": key2})
            checks["cross_candidate_404"] = cross.status_code == 404

            # 7. self-erase → key dies, candidate gone
            d = c.delete("/portal/me", headers=ch).json()
            checks["self_erase"] = d["deleted"] is True
            checks["key_dead_after_erase"] = c.get("/portal/me", headers=ch).status_code == 401
            checks["candidate_gone"] = c.get(f"/candidates/{cid}", headers=admin_h).status_code == 404
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    ok = sum(checks.values())
    for name, passed in checks.items():
        print(f"  [{'OK' if passed else 'XX'}] {name}")
    print(f"{ok}/{len(checks)} checks OK")
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
