"""S7.1 smoke: boot uvicorn on a migrated scratch DB and walk the verification
spine end to end — self-attest (L1), contact-control OTP (L2) including the
destination-binding and wrong-code refusals, consent-gated org disclosure
(403 -> grant -> 200 -> revoke -> 403), operator manual review (L3), and DPDP
erasure (org read 404s afterward). No network, no LLM.

The OTP code is read back via the DOUBLE-GUARDED debug echo (env == "local" AND
DEE_VERIF_OTP_DEBUG_ECHO=true), which is the only way to drive the two-step
flow over plain HTTP. Production cannot echo a code.

Run from repo root: python scripts/smoke_s71.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from _smoke import base_env, wait_healthy

PORT = 8071
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
EMAIL = "dev@example.com"
RESUME = f"Dev\nEmail: {EMAIL}\nSKILLS\nPython\n"



def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s71.db").as_posix()
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
        "DEE_VERIF_OTP_DEBUG_ECHO": "true",
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

            # 1. candidate + key; no verification yet -> level none
            cid = c.post("/candidates", headers=admin_h,
                         json={"resume_text": RESUME, "evaluate": False}).json()["candidate_id"]
            key = c.post(f"/candidates/{cid}/auth-key", headers=admin_h).json()["access_key"]
            ch = {"X-Candidate-Key": key}
            me = c.get("/portal/me", headers=ch).json()
            checks["me_starts_unverified"] = me["identity"]["level"] == 0
            checks["retention_has_verifications_window"] = any(
                w["data_class"] == "verifications" for w in me["retention"]["windows"]
            )

            # 2. self-attest -> L1
            sa = c.post("/portal/verifications", headers=ch, json={"method": "self_attested"})
            checks["self_attest_verified"] = (
                sa.status_code == 200 and sa.json()["verification"]["status"] == "verified"
            )
            checks["level_self_attested"] = (
                c.get("/portal/verifications", headers=ch).json()["assurance"]["level"] == 1
            )

            # 3. OTP destination binding: a contact NOT on file is refused
            bad_dest = c.post("/portal/verifications", headers=ch,
                              json={"method": "otp_email", "destination": "attacker@example.com"})
            checks["wrong_destination_400"] = bad_dest.status_code == 400

            # 4. OTP with the real contact -> code echoed (double-guarded)
            started = c.post("/portal/verifications", headers=ch,
                             json={"method": "otp_email", "destination": EMAIL})
            body = started.json()
            vid = body["verification"]["id"]
            code = body.get("debug_code")
            checks["otp_started_with_code"] = started.status_code == 200 and bool(code)

            # 5. wrong code refused, correct code verifies -> L2
            wrong = "0" * len(code) if code != "0" * len(code) else "1" * len(code)
            checks["wrong_code_400"] = c.post(
                f"/portal/verifications/{vid}/confirm", headers=ch, json={"code": wrong}
            ).status_code == 400
            ok = c.post(f"/portal/verifications/{vid}/confirm", headers=ch, json={"code": code})
            checks["correct_code_verifies"] = (
                ok.status_code == 200 and ok.json()["status"] == "verified"
            )
            checks["level_contact_control"] = (
                c.get("/portal/verifications", headers=ch).json()["assurance"]["level"] == 2
            )

            # 6. the ladder cannot be climbed by asking. manual_review means an
            # operator looked; government_id has no adapter behind it. Note the
            # self-granted consent: a candidate CAN grant themselves
            # identity_verify from this plane, so consent alone must not open it.
            self_award = c.post("/portal/verifications", headers=ch,
                                json={"method": "manual_review"})
            checks["candidate_cannot_self_award_review"] = self_award.status_code == 403

            c.post("/portal/consents", headers=ch, json={"purpose": "identity_verify"})
            gov = c.post("/portal/verifications", headers=ch,
                         json={"method": "government_id"})
            checks["government_id_inert_even_with_consent"] = gov.status_code == 422
            checks["level_still_contact_control"] = (
                c.get("/portal/verifications", headers=ch).json()["assurance"]["level"] == 2
            )

            # 7. org disclosure is consent-gated on the NEW purpose
            org = c.post("/ledger/orgs", headers=admin_h, json={"name": "Acme"}).json()
            org_id, org_key = org["org"]["id"], org["api_key"]
            org_h = {"X-Org-Key": org_key}
            path = f"/verification/candidates/{cid}/assurance"
            checks["org_read_403_without_consent"] = c.get(path, headers=org_h).status_code == 403

            gid = c.post(f"/ledger/candidates/{cid}/consent", headers=admin_h,
                         json={"purpose": "verification_read", "org_id": org_id}).json()["id"]
            granted = c.get(path, headers=org_h)
            checks["org_read_200_with_consent"] = (
                granted.status_code == 200 and granted.json()["level"] == 2
            )
            checks["org_sees_no_evidence_internals"] = (
                "evidence_digest" not in granted.json()
                and "destination_hash" not in granted.json()
            )

            c.post(f"/ledger/consent/{gid}/revoke", headers=admin_h)
            checks["org_read_403_after_revoke"] = c.get(path, headers=org_h).status_code == 403

            # 8. operator manual review on the ADMIN plane -> L3
            mr = c.post(f"/candidates/{cid}/verifications/manual-review", headers=admin_h,
                        json={"outcome": "verified", "note": "passport seen in person"})
            checks["manual_review_recorded"] = mr.status_code == 200
            checks["level_reviewed"] = (
                c.get("/portal/verifications", headers=ch).json()["assurance"]["level"] == 3
            )

            # 9. DPDP erasure sweeps it; the org read can no longer disclose
            c.delete("/portal/me", headers=ch)
            checks["org_read_404_after_erase"] = c.get(path, headers=org_h).status_code == 404
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    ok_count = sum(checks.values())
    for name, passed in checks.items():
        print(f"  [{'OK' if passed else 'XX'}] {name}")
    print(f"{ok_count}/{len(checks)} checks OK")
    return 0 if ok_count == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
