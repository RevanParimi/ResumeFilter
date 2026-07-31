"""S7.2 smoke: boot uvicorn on a migrated scratch DB and walk employment-claim
document forensics end to end — a clean experience letter (DOCUMENTED), a letter
naming an employer the resume never claimed (FAILED, strength unchanged), a
payslip whose arithmetic does not add up (hard finding), the concurrent-
employment advisory derived from overlapping resume intervals, consent-gated org
disclosure (403 -> grant -> 200 -> revoke -> 403), and DPDP erasure (404 after).

The two checks this sprint exists to protect:
  * identity_level_still_zero — a payslip must never lift IdentityAssurance;
  * epfo_422_even_with_self_granted_consent — a candidate can grant themselves
    identity_verify from this very plane, so consent must never be sufficient.

No network, no LLM, no API key needed (extraction falls back to heuristics).

Run from repo root: python scripts/smoke_s72.py
"""

import base64
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

PORT = 8072
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
EMAIL = "dev@example.com"

RESUME = f"""Dev Kumar
Email: {EMAIL}

EXPERIENCE
Senior Software Engineer at Acme Technologies - Mar 2021 - Jan 2024

SKILLS
Python
"""

# A second candidate whose resume carries two overlapping PRIMARY roles.
MOONLIGHT_RESUME = """Mo Nair
Email: moon@example.com

EXPERIENCE
Engineer at Acme Technologies - Jan 2021 - Dec 2023
Engineer at Globex Corp - Jan 2022 - Dec 2023

SKILLS
Python
"""

CLEAN_LETTER = b"""ACME TECHNOLOGIES PRIVATE LIMITED
hr@acme.com

TO WHOM IT MAY CONCERN

This is to certify that Dev Kumar (Employee ID ACM-4471) was employed with
Acme Technologies as a Senior Software Engineer from March 2021 to January 2024.

Sincerely,
R. Sharma
Head of Human Resources
"""

MISMATCHED_LETTER = b"""GLOBEX CORP
hr@globex.com

This is to certify that Dev Kumar (Employee ID GX-9) was employed with Globex
Corp as a Staff Engineer from March 2021 to January 2024.

Head of Human Resources
"""

BAD_PAYSLIP = b"""ACME TECHNOLOGIES PRIVATE LIMITED
Payslip for March 2023
Employee: Dev Kumar     UAN: 100234567890
Gross Salary: 100000
Total Deductions: 22000
Net Pay: 95000
"""

# Strings that must never appear in ANY response body.
LEAKS = ("ACM-4471", "hr@acme.com", "100234567890", "100000", "95000", "22000")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


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
    url = "sqlite:///" + (scratch / "smoke_s72.db").as_posix()
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
        "DEE_API_AUTH_KEY": ADMIN,
    })
    admin_h = {"X-API-Key": ADMIN}
    checks: dict[str, bool] = {}
    seen: list[str] = []   # every response body, for the leak sweep

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(60, connect=5)) as c:
            if not _wait_healthy(c):
                print("server did not become healthy")
                return 1

            def post(path, **kw):
                r = c.post(path, **kw)
                seen.append(r.text)
                return r

            def get(path, **kw):
                r = c.get(path, **kw)
                seen.append(r.text)
                return r

            # 1. candidate + key; no document yet -> no claim evidence
            cid = post("/candidates", headers=admin_h,
                       json={"resume_text": RESUME, "evaluate": False}
                       ).json()["candidate_id"]
            key = post(f"/candidates/{cid}/auth-key",
                       headers=admin_h).json()["access_key"]
            ch = {"X-Candidate-Key": key}
            listed = get("/portal/verifications", headers=ch).json()
            checks["claims_start_empty"] = listed["claims"]["strength"] == 0

            # 2. a clean letter matching the resume -> DOCUMENTED
            clean = post("/portal/documents", headers=ch,
                         json={"doc_type": "experience_letter",
                               "content_b64": _b64(CLEAN_LETTER),
                               "claim_ref": "Acme Technologies|2021-03..2024-01"})
            checks["clean_letter_documented"] = (
                clean.status_code == 200
                and clean.json()["verification"]["status"] == "verified"
                and clean.json()["claims"]["strength"] == 2
            )

            # 3. THE invariant: a document says nothing about WHO this is.
            checks["identity_level_still_zero"] = (
                get("/portal/verifications", headers=ch).json()["assurance"]["level"] == 0
            )

            # 4. a letter naming an employer the resume never claimed -> FAILED,
            #    and the strength already held is untouched (max(), never a
            #    penalty: a bad submission is not an accusation).
            bad = post("/portal/documents", headers=ch,
                       json={"doc_type": "experience_letter",
                             "content_b64": _b64(MISMATCHED_LETTER)})
            checks["mismatched_letter_fails"] = (
                bad.status_code == 200
                and bad.json()["verification"]["status"] == "failed"
                and bad.json()["claims"]["strength"] == 2
            )

            # 5. payslip arithmetic that does not reconcile -> hard finding
            slip = post("/portal/documents", headers=ch,
                        json={"doc_type": "payslip", "content_b64": _b64(BAD_PAYSLIP)})
            slip_ids = {f["id"] for f in slip.json().get("findings", [])}
            checks["payslip_arithmetic_hard_finding"] = (
                slip.status_code == 200
                and slip.json()["verification"]["status"] == "failed"
                and "payslip_arithmetic_mismatch" in slip_ids
            )

            # 6. nothing from any document has leaked into any response
            checks["no_document_content_in_any_response"] = not any(
                leak in body for leak in LEAKS for body in seen
            )

            # 7. EPFO: lawful but vendor-gated, so inert. The candidate grants
            #    themselves identity_verify from this plane first — consent is
            #    necessary and must never be sufficient.
            post("/portal/consents", headers=ch, json={"purpose": "identity_verify"})
            epfo = post("/portal/verifications", headers=ch,
                        json={"method": "epfo_employment"})
            checks["epfo_422_even_with_self_granted_consent"] = (
                epfo.status_code == 422
                and get("/portal/verifications",
                        headers=ch).json()["claims"]["strength"] == 2
            )

            # 7b. REVIEW REGRESSION. The identity start route accepts any
            #     VerificationMethod, and the claim adapters declare
            #     instant=True. As first built, POSTing a claim method here
            #     returned 200 `verified` stamped subject=identity, and every
            #     later read of the candidate's own portal 500'd forever.
            letter_via_identity = post("/portal/verifications", headers=ch,
                                       json={"method": "experience_letter"})
            after = get("/portal/verifications", headers=ch)
            checks["claim_method_refused_on_the_identity_route"] = (
                letter_via_identity.status_code == 403
                and after.status_code == 200                 # portal not bricked
                and after.json()["assurance"]["level"] == 0
            )

            # 7c. REVIEW REGRESSION. SQLite does not enforce VARCHAR(128), so an
            #     unbounded claim_ref turned the row into a text column — the
            #     one field exempted from the "nothing wider than 64" guard.
            oversize = post("/portal/documents", headers=ch,
                            json={"doc_type": "experience_letter",
                                  "content_b64": _b64(CLEAN_LETTER),
                                  "claim_ref": "UAN 100234567890 " + "X" * 5000})
            checks["oversize_claim_ref_refused"] = oversize.status_code == 422

            # 8. concurrent employment, derived read-time from a second
            #    candidate's own overlapping resume intervals
            mid = post("/candidates", headers=admin_h,
                       json={"resume_text": MOONLIGHT_RESUME, "evaluate": False}
                       ).json()["candidate_id"]
            mkey = post(f"/candidates/{mid}/auth-key",
                        headers=admin_h).json()["access_key"]
            ce = get("/portal/verifications",
                     headers={"X-Candidate-Key": mkey}).json()["claims"]
            checks["concurrent_employment_surfaced"] = (
                ce["concurrent_employment"] is not None
                and ce["concurrent_employment"]["periods"] == ["2022-01..2023-12"]
                and ce["concurrent_employment"]["advisory"] is True
            )

            # 9-12. org disclosure is consent-gated on VERIFICATION_READ
            org = post("/ledger/orgs", headers=admin_h, json={"name": "Acme"}).json()
            org_id, org_key = org["org"]["id"], org["api_key"]
            org_h = {"X-Org-Key": org_key}
            path = f"/verification/candidates/{cid}/claims"
            checks["org_claims_403_without_consent"] = (
                get(path, headers=org_h).status_code == 403
            )

            gid = post(f"/ledger/candidates/{cid}/consent", headers=admin_h,
                       json={"purpose": "verification_read", "org_id": org_id}
                       ).json()["id"]
            granted = get(path, headers=org_h)
            checks["org_claims_200_with_consent"] = (
                granted.status_code == 200 and granted.json()["strength"] == 2
            )
            body = granted.json()
            checks["org_sees_no_evidence_internals"] = (
                "evidence_digest" not in granted.text
                and "claim_ref" not in granted.text
                and set(body) == {"candidate_id", "strength", "documents",
                                  "findings", "concurrent_employment", "advisory"}
            )

            post(f"/ledger/consent/{gid}/revoke", headers=admin_h)
            checks["org_claims_403_after_revoke"] = (
                get(path, headers=org_h).status_code == 403
            )

            # 13. DPDP erasure sweeps the claim rows with the candidate
            c.delete("/portal/me", headers=ch)
            checks["org_claims_404_after_erase"] = (
                get(path, headers=org_h).status_code == 404
            )
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
