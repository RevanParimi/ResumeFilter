"""S8.2 smoke: a real org and a real candidate get in with NO operator.

That sentence is the sprint, so the smoke proves it over HTTP rather than in
process. The three things worth watching:

  * org_session_reaches_the_org_plane -- an authenticated call carrying NO
    X-Org-Key at all. Every one of the 63 endpoints gained session mode without
    a handler edit, and this is that claim from outside the process.
  * candidate_claims_the_uploaded_resume -- the candidate signs up with the
    address on a resume an ORG uploaded, and /portal/me shows them that resume.
    This is decision 0.4, and it is the most security-consequential line in the
    sprint.
  * csrf_without_token_403 -- the cookie is present and valid; only the CSRF
    token is missing. A pass here means the double-submit layer is live, not
    merely written.

Also pinned: signup on an unknown address and on a known one are
indistinguishable (no account enumeration), and erasure kills every session.

Runs with email_provider=capture, so the codes land in a file instead of a
mailbox. That is selected by EXPLICIT config -- never by fallback -- and prod
refuses to boot with it (app/core/boot.py).

No network, no LLM, no API key needed (extraction falls back to heuristics).

Run from repo root:   python scripts/smoke_s82.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

PORT = 8082
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}

CANDIDATE_EMAIL = "priya.sharma@example.in"
RESUME = f"""Priya Sharma
Email: {CANDIDATE_EMAIL}

EXPERIENCE
Senior ML Engineer at Acme AI - Mar 2021 - Jan 2024
Data Engineer at Globex Corp - Jan 2019 - Feb 2021

SKILLS
Python, PyTorch, Spark
"""


def _wait_healthy(c) -> bool:
    for _ in range(60):
        try:
            if c.get("/healthz").status_code == 200:
                return True
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    return False


def _code_for(mailbox: Path, email: str) -> str:
    """The newest code addressed to THIS recipient.

    Deliberately not "the last line in the file": several flows interleave in
    this smoke, and reading the newest line regardless of recipient silently
    hands one person's code to another client. That produced a failure whose
    symptom was a missing cookie three steps later, which is a bad way to spend
    an afternoon.
    """
    for raw in reversed(mailbox.read_text(encoding="utf-8").splitlines()):
        msg = json.loads(raw)
        if msg["to"].strip().lower() == email.strip().lower():
            return re.search(r"\b(\d{6})\b", msg["body"]).group(1)
    raise AssertionError(f"no code was sent to {email}")


def _sent(mailbox: Path) -> int:
    if not mailbox.exists():
        return 0
    return len(mailbox.read_text(encoding="utf-8").splitlines())


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    mailbox = scratch / "mailbox.jsonl"
    url = "sqlite:///" + (scratch / "smoke_s82.db").as_posix()
    print(f"scratch DB: {url}")
    print(f"mailbox:    {mailbox}")

    env = os.environ.copy()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        # Pinned EMPTY on purpose: this smoke claims the no-key path works end to
        # end, and a developer with a real key in .env would otherwise ship live
        # calls from a test run (the S7.3 lesson).
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_API_AUTH_KEY": ADMIN,
        # Capture email, and cookies a plain-HTTP client will actually keep.
        # S8.6: samesite here now MATCHES the shipped default (lax, since the UI
        # is same-origin); only `secure` still differs, because this smoke talks
        # plain HTTP to localhost. Prod refuses to BOOT with secure=false.
        "DEE_EMAIL_PROVIDER": "capture",
        "DEE_EMAIL_CAPTURE_PATH": mailbox.as_posix(),
        "DEE_SESSION_COOKIE_SECURE": "false",
        "DEE_SESSION_COOKIE_SAMESITE": "lax",
    })

    checks: dict[str, bool] = {}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        timeout = httpx.Timeout(180, connect=5)
        with httpx.Client(base_url=BASE, timeout=timeout) as org, \
             httpx.Client(base_url=BASE, timeout=timeout) as cand, \
             httpx.Client(base_url=BASE, timeout=timeout) as cand2, \
             httpx.Client(base_url=BASE, timeout=timeout) as admin:

            checks["boots"] = _wait_healthy(org)
            if not checks["boots"]:
                print("server did not become healthy")
                return 1

            # 1-3. ORG SELF-ONBOARD, with no operator anywhere in the loop.
            checks["org_signup_202"] = org.post(
                "/auth/org/signup",
                json={"email": "ops@acme.in", "organization_name": "Acme Staffing"},
            ).status_code == 202
            verified = org.post(
                "/auth/org/verify",
                json={"email": "ops@acme.in", "code": _code_for(mailbox, "ops@acme.in")},
            )
            checks["org_verify_200"] = verified.status_code == 200
            org_csrf = verified.json().get("csrf_token", "")
            checks["session_cookie_set"] = "dee_session" in org.cookies

            # 4. THE claim of the sprint: an org-plane call with NO X-Org-Key.
            board = org.get("/dashboard/overview")
            checks["org_session_reaches_the_org_plane"] = board.status_code == 200

            # 5-6. CSRF is live, not merely written.
            checks["csrf_without_token_403"] = org.post(
                "/ledger/records",
                json={"candidate_id": "x", "stage": "screening", "outcome": "pass"},
            ).status_code == 403
            checks["csrf_with_token_not_403"] = org.post(
                "/ledger/records",
                json={"candidate_id": "x", "stage": "screening", "outcome": "pass"},
                headers={"X-CSRF-Token": org_csrf},
            ).status_code != 403

            # 7. An operator uploads a resume, creating a candidate the person
            #    themselves has never touched.
            created = admin.post(
                "/candidates", json={"resume_text": RESUME}, headers=ADMIN_H
            )
            checks["org_uploads_resume"] = created.status_code == 200
            candidate_id = created.json().get("candidate_id")

            # 8-10. THE CLAIM (decision 0.4): the candidate signs up with the
            #       address on that resume and attaches to the EXISTING record.
            checks["candidate_signup_202"] = cand.post(
                "/auth/candidate/signup", json={"email": CANDIDATE_EMAIL}
            ).status_code == 202
            checks["candidate_verify_200"] = cand.post(
                "/auth/candidate/verify",
                json={"email": CANDIDATE_EMAIL, "code": _code_for(mailbox, CANDIDATE_EMAIL)},
            ).status_code == 200
            me = cand.get("/portal/me")
            checks["candidate_claims_the_uploaded_resume"] = (
                me.status_code == 200
                and me.json().get("candidate_id") == candidate_id
                and len(me.json().get("resumes", [])) == 1
            )

            # 11. No account enumeration -- and note what "no enumeration" means
            #     on this plane: not silence, but INDISTINGUISHABILITY. A
            #     candidates row is not an account, so signup and login are the
            #     same act and both always send. Known and unknown addresses get
            #     the same status, the same body, and one email each.
            before = _sent(mailbox)
            known = cand2.post(
                "/auth/candidate/login", json={"email": CANDIDATE_EMAIL}
            )
            after_known = _sent(mailbox)
            unknown = cand2.post(
                "/auth/candidate/login", json={"email": "nobody@nowhere.in"}
            )
            after_unknown = _sent(mailbox)
            checks["known_and_unknown_are_indistinguishable"] = (
                known.status_code == unknown.status_code == 202
                and known.json() == unknown.json()
                and (after_known - before) == (after_unknown - after_known) == 1
            )

            # 12-14. Devices: a second login, then revoke the first.
            sessions = cand.get("/auth/sessions").json()
            checks["one_session_listed"] = len(sessions) == 1
            if not sessions:
                print("no session listed; aborting device checks")
                return 1
            cand2.post("/auth/candidate/login", json={"email": CANDIDATE_EMAIL})
            cand2.post(
                "/auth/candidate/verify",
                json={"email": CANDIDATE_EMAIL, "code": _code_for(mailbox, CANDIDATE_EMAIL)},
            )
            checks["two_sessions_listed"] = len(cand2.get("/auth/sessions").json()) == 2
            first_id = sessions[0]["id"]
            cand2_csrf = cand2.cookies.get("dee_csrf")
            revoked = cand2.post(
                f"/auth/sessions/{first_id}/revoke",
                headers={"X-CSRF-Token": cand2_csrf},
            )
            checks["revoke_other_device_200"] = revoked.status_code == 200
            checks["revoked_session_401s"] = cand.get("/portal/me").status_code == 401
            checks["surviving_session_still_works"] = (
                cand2.get("/portal/me").status_code == 200
            )

            # 15-16. Operator accounts: minted with the shared key, then used
            #        as a PERSON via a session.
            op = admin.post(
                "/admin/users", json={"email": "op@veritas.in", "label": "ops"},
                headers=ADMIN_H,
            )
            checks["operator_created"] = op.status_code == 200
            with httpx.Client(base_url=BASE, timeout=timeout) as operator:
                operator.post("/auth/admin/login", json={"email": "op@veritas.in"})
                operator.post(
                    "/auth/admin/verify",
                    json={"email": "op@veritas.in", "code": _code_for(mailbox, "op@veritas.in")},
                )
                checks["operator_session_reaches_admin_plane"] = (
                    operator.get("/domains").status_code == 200
                )

            # 17-18. Erasure kills every session of that person.
            erased = cand2.delete(
                "/portal/me", headers={"X-CSRF-Token": cand2_csrf}
            )
            checks["erasure_200"] = erased.status_code == 200
            checks["all_sessions_dead_after_erasure"] = (
                cand2.get("/portal/me").status_code == 401
                and cand.get("/portal/me").status_code == 401
            )
    finally:
        proc.terminate()
        proc.wait(timeout=30)

    ok = sum(1 for v in checks.values() if v)
    for name, passed in checks.items():
        print(f"{'OK  ' if passed else 'FAIL'} {name}")
    print(f"\n{ok}/{len(checks)} OK")
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
