"""S8.4 Phase A smoke: two orgs, one deduplicated candidate, over real HTTP.

Key-less by construction. DEE_OPENROUTER_API_KEY is pinned empty because S7.3
found a developer with a real key in .env silently shipping junk to a live
vendor from a smoke that CLAIMED to prove the no-key path.

What a unit test cannot prove and this does: that ownership survives the whole
upload -> extract -> evaluate -> store -> read round trip, on the plane a real
customer uses, with two organizations racing over the same person.

The checks this sprint exists to protect:
  * taken_name_409 / taken_name_sends_no_code -- a duplicate organization name
    is refused BEFORE a code is sent, not accepted-then-rejected-as-a-bad-code
    at verify (S8.4's own fix to a signup lockout).
  * cross_org_read_404 / cross_org_read_404_matches_absent -- another org's
    report answers exactly like a report that does not exist. A 403, or a
    body that differs by one byte, would confirm the report exists.
  * cross_org_upload_top_level_redacted / _embedded_report_redacted -- THE headline
    guarantee of the sprint. A Critical cross-tenant leak was found and fixed
    during this sprint: the org upload response was returning real
    candidate_id/resume_id of another customer's candidate, in both the
    top-level resume_farm field and the embedded report's own resume_farm.
    This is the one check that would have caught it, run the way a real
    customer would trigger it -- two different orgs, the second one's upload
    response, over HTTP.
  * admin_upload_invisible_to_orgs -- a resume an operator uploads (no owner)
    belongs to nobody, not everybody; an org must not be able to read it.

Runs with email_provider=capture, so the codes land in a file instead of a
mailbox. That is selected by EXPLICIT config -- never by fallback -- and prod
refuses to boot with it (app/core/boot.py).

No network, no LLM, no API key needed (extraction falls back to heuristics).

Run from repo root:   python scripts/smoke_s84a.py
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx


from _smoke import Smoke, base_env, wait_healthy


S = Smoke("smoke_s84a")
PORT = 8084
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# GENUINE / GENUINE_V2 -- same person (same email in the contact block), two
# different resume texts, so identity resolution dedups on email_hash while
# still producing a second resume version for the second org's upload. The
# fixture ships with no contact block at all, so one is spliced in right
# after the header line -- rather than prepended -- so heuristic extraction's
# header/name parsing (which reads the first line) is unaffected.
_GENUINE_LINES = (
    (FIXTURES / "genuine_genai_resume.txt").read_text(encoding="utf-8").splitlines()
)
CANDIDATE_EMAIL = "priya.nair@example.in"
GENUINE = "\n".join(
    [_GENUINE_LINES[0], f"Email: {CANDIDATE_EMAIL}"] + _GENUINE_LINES[1:]
)
GENUINE_V2 = "\n".join(
    [_GENUINE_LINES[0], f"Email: {CANDIDATE_EMAIL}"] + _GENUINE_LINES[1:]
    + ["", "Additional note: open-sourced the evaluation harness internally."]
)

FARM_A = (FIXTURES / "farm_genai_resume_a.txt").read_text(encoding="utf-8")
FARM_B = (FIXTURES / "farm_genai_resume_b.txt").read_text(encoding="utf-8")

OTHER = """Deepak Kulkarni
Email: deepak.kulkarni@example.in

EXPERIENCE
Backend Engineer at Zeta Systems - Jun 2020 - Present

SKILLS
Java, Spring, PostgreSQL
"""




def _code_for(mailbox: Path, email: str) -> str:
    """The newest code addressed to THIS recipient.

    Deliberately not "the last line in the file": several flows interleave in
    this smoke, and reading the newest line regardless of recipient silently
    hands one person's code to another client.
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


class OrgSession:
    """One org-user's browser: a cookie-jar client plus its CSRF token."""

    def __init__(self, client: httpx.Client, csrf: str, org_id: str) -> None:
        self.client = client
        self.csrf = csrf
        self.org_id = org_id

    def post(self, path: str, json_body: dict) -> httpx.Response:
        return self.client.post(
            path, json=json_body, headers={"X-CSRF-Token": self.csrf}
        )

    def get(self, path: str) -> httpx.Response:
        return self.client.get(path)


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    mailbox = scratch / "mailbox.jsonl"
    url = "sqlite:///" + (scratch / "smoke_s84a.db").as_posix()
    print(f"scratch DB: {url}")
    print(f"mailbox:    {mailbox}")

    env = base_env()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        # Pinned EMPTY on purpose: this smoke claims the no-key path works end
        # to end, and a developer with a real key in .env would otherwise ship
        # live calls from a test run (the S7.3 lesson).
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

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    opened: list[httpx.Client] = []

    def _client() -> httpx.Client:
        timeout = httpx.Timeout(180, connect=5)
        c = httpx.Client(base_url=BASE, timeout=timeout)
        opened.append(c)
        return c

    def signup_and_verify(email: str, org_name: str) -> "OrgSession | None":
        c = _client()
        r = c.post(
            "/auth/org/signup",
            json={"email": email, "organization_name": org_name},
        )
        if r.status_code != 202:
            print(f"    signup for {org_name} failed: {r.status_code} {r.text}")
            return None
        v = c.post(
            "/auth/org/verify",
            json={"email": email, "code": _code_for(mailbox, email)},
        )
        if v.status_code != 200:
            print(f"    verify for {org_name} failed: {v.status_code} {v.text}")
            return None
        body = v.json()
        return OrgSession(c, body["csrf_token"], body["organization_id"])

    try:
        boot_client = _client()
        booted = wait_healthy(boot_client)
        S.check("healthz", booted)
        if not booted:
            print("server did not become healthy")
            return 1

        admin = _client()

        # 1-3. Org A onboards end to end, no operator involved.
        org_a = signup_and_verify("ops@agency-a.example", "Agency A")
        S.check("org_a_session", org_a is not None)
        if org_a is None:
            print("aborting: org A could not onboard")
            return 1

        # 4-5. THE LOCKOUT: Org B tries Org A's name. Refused before any code
        #      is sent -- not accepted then rejected as invalid_code at verify.
        before = _sent(mailbox)
        taken = httpx.post(
            f"{BASE}/auth/org/signup",
            json={"email": "ops@agency-b.example", "organization_name": "Agency A"},
        )
        S.check(
            "taken_name_409",
            taken.status_code == 409
            and taken.json().get("detail") == "organization_name_taken",
            f"got {taken.status_code} {taken.text}",
        )
        S.check("taken_name_sends_no_code", _sent(mailbox) == before)

        # 6. Org B onboards under its own name.
        org_b = signup_and_verify("ops@agency-b.example", "Agency B")
        S.check("org_b_session", org_b is not None)
        if org_b is None:
            print("aborting: org B could not onboard")
            return 1

        # 7-8. Org A uploads and reads its own report.
        up_a = org_a.post(
            "/screening/candidates", {"resume_text": GENUINE, "domain": "genai"}
        )
        S.check("org_a_upload", up_a.status_code == 200, up_a.text if up_a.status_code != 200 else "")
        up_a_body = up_a.json()
        report_id_a = up_a_body["report"]["id"]
        candidate_id = up_a_body["candidate_id"]
        S.check(
            "org_a_reads_own_report",
            org_a.get(f"/screening/reports/{report_id_a}").status_code == 200,
        )

        # 9-10. THE ISOLATION: Org B cannot read it, and cannot tell it exists.
        theirs = org_b.get(f"/screening/reports/{report_id_a}")
        absent = org_b.get("/screening/reports/no-such-report")
        S.check("cross_org_read_404", theirs.status_code == 404)
        S.check(
            "cross_org_read_404_matches_absent",
            # Assert the absent side's status too: without it this check leans
            # entirely on the one above for its floor, and two identical 500s
            # would read as "indistinguishable".
            absent.status_code == 404 and theirs.text == absent.text,
            f"theirs={theirs.status_code} absent={absent.status_code}",
        )

        # 11-12. Dedup held: one person, two owners, each seeing only its own.
        up_b = org_b.post(
            "/screening/candidates", {"resume_text": GENUINE_V2, "domain": "genai"}
        )
        S.check("org_b_upload", up_b.status_code == 200, up_b.text if up_b.status_code != 200 else "")
        S.check(
            "candidate_deduplicated",
            up_b.json().get("candidate_id") == candidate_id,
            f"a={candidate_id} b={up_b.json().get('candidate_id')}",
        )
        reports_a = org_a.get(f"/screening/candidates/{candidate_id}/reports")
        reports_b = org_b.get(f"/screening/candidates/{candidate_id}/reports")
        report_id_b = (up_b.json().get("report") or {}).get("id")
        S.check(
            "each_org_sees_only_its_own_report",
            reports_a.status_code == 200 and reports_b.status_code == 200
            and [r["id"] for r in reports_a.json()] == [report_id_a]
            # Assert WHICH report, not just how many: a swap bug (A gets B's,
            # B gets A's) is 1/1 either way and would pass a length check.
            and [r["id"] for r in reports_b.json()] == [report_id_b],
            f"a={[r['id'] for r in reports_a.json()]} b={[r['id'] for r in reports_b.json()]}",
        )

        # 13. The redaction, on a report that really has matches -- same org,
        #     GET path (both fixtures uploaded by Agency A).
        org_a.post("/screening/candidates", {"resume_text": FARM_A, "domain": "genai"})
        farm_same_org = org_a.post(
            "/screening/candidates", {"resume_text": FARM_B, "domain": "genai"}
        )
        farm_report = org_a.get(
            f"/screening/reports/"
            f"{(farm_same_org.json().get('report') or {}).get('id')}"
        ).json()
        # `or {}` rather than a .get default: resume_farm is Optional and
        # serialises as JSON null, not as an absent key, so a .get default
        # never fires and `None.get(...)` would raise -- turning a named FAIL
        # into a traceback in exactly the state these checks exist to catch.
        farm_matches = (farm_report.get("resume_farm") or {}).get("matches", [])
        S.check(
            "farm_matches_redacted_on_get",
            bool(farm_matches)
            and all(
                m["candidate_id"] is None and m["resume_id"] is None
                and m["similarity"] > 0
                for m in farm_matches
            ),
        )

        # 14-15. THE HEADLINE GUARANTEE: the near-duplicate pair uploaded by
        #        TWO DIFFERENT orgs. Org C uploads FARM_A, org D (a near
        #        duplicate of the same template) uploads FARM_B, and org D's
        #        UPLOAD RESPONSE -- not a later GET -- must carry no other
        #        customer's candidate_id/resume_id, in either copy of the
        #        assessment it appears in. This is the exact shape of the
        #        Critical leak found and fixed during this sprint.
        org_c = signup_and_verify("ops@agency-c.example", "Agency C")
        org_d = signup_and_verify("ops@agency-d.example", "Agency D")
        S.check("org_c_session", org_c is not None)
        S.check("org_d_session", org_d is not None)
        if org_c is not None and org_d is not None:
            org_c.post(
                "/screening/candidates", {"resume_text": FARM_A, "domain": "genai"}
            )
            cross_up = org_d.post(
                "/screening/candidates", {"resume_text": FARM_B, "domain": "genai"}
            )
            cross_body = cross_up.json()
            top_matches = (cross_body.get("resume_farm") or {}).get("matches", [])
            embedded_matches = (
                ((cross_body.get("report") or {}).get("resume_farm") or {})
                .get("matches", [])
            )
            S.check(
                "cross_org_upload_top_level_redacted",
                bool(top_matches)
                and all(
                    m["candidate_id"] is None and m["resume_id"] is None
                    and m["similarity"] > 0
                    for m in top_matches
                ),
                f"matches={top_matches}",
            )
            S.check(
                "cross_org_upload_embedded_report_redacted",
                bool(embedded_matches)
                and all(
                    m["candidate_id"] is None and m["resume_id"] is None
                    and m["similarity"] > 0
                    for m in embedded_matches
                ),
                f"matches={embedded_matches}",
            )
        else:
            S.check("cross_org_upload_top_level_redacted", False, "org C/D did not onboard")
            S.check("cross_org_upload_embedded_report_redacted", False, "org C/D did not onboard")

        # 16-17. Admin uploads stay unowned: readable by the operator plane,
        #        invisible on the org plane.
        adm = admin.post("/candidates", json={"resume_text": OTHER, "domain": "genai"}, headers=ADMIN_H)
        S.check("admin_upload", adm.status_code == 200, adm.text if adm.status_code != 200 else "")
        report_id_adm = (adm.json().get("report") or {}).get("id")
        S.check(
            "admin_still_reads_its_own",
            admin.get(f"/report/{report_id_adm}", headers=ADMIN_H).status_code == 200,
        )
        S.check(
            "admin_upload_invisible_to_orgs",
            org_a.get(f"/screening/reports/{report_id_adm}").status_code == 404,
        )

        # 18-20. THE SET NULL CONTRACT, over HTTP. An organisation offboarding
        #        must NOT destroy a person's resume -- that is the load-bearing
        #        FK choice of this whole sprint, and the one a CASCADE typo
        #        would destroy silently.
        #
        #        This was originally skipped on a FALSE PREMISE: the plan, the
        #        smoke and TENANCY.md all said there was no HTTP route to
        #        delete an organisation. DELETE /ledger/orgs/{id} has existed
        #        the whole time, on the admin plane. Proving it here means the
        #        sprint's load-bearing decision is verified the way an operator
        #        would actually trigger it, not only in a unit test.
        #
        #        Org B is the victim: it uploaded GENUINE_V2 earlier, so it
        #        owns a resume AND a report. Deleting it last keeps every
        #        earlier check's session valid.
        cand_before = admin.get(f"/candidates/{candidate_id}", headers=ADMIN_H)
        killed = admin.delete(f"/ledger/orgs/{org_b.org_id}", headers=ADMIN_H)
        S.check(
            "org_offboarded",
            killed.status_code == 200,
            killed.text if killed.status_code != 200 else "",
        )
        cand_after = admin.get(f"/candidates/{candidate_id}", headers=ADMIN_H)
        S.check(
            "offboarding_leaves_the_person_intact",
            cand_before.status_code == 200 and cand_after.status_code == 200,
            f"before={cand_before.status_code} after={cand_after.status_code}",
        )
        # The report org B commissioned survives the org that paid for it, and
        # is now unowned -- readable by the operator, invisible to every org.
        # A CASCADE typo makes this a 404 and fails the check.
        S.check(
            "offboarded_orgs_report_survives_unowned",
            admin.get(f"/report/{report_id_b}", headers=ADMIN_H).status_code == 200
            and org_a.get(f"/screening/reports/{report_id_b}").status_code == 404,
            f"report_id_b={report_id_b}",
        )
    finally:
        proc.terminate()
        proc.wait(timeout=30)
        for c in opened:
            try:
                c.close()
            except Exception:
                pass

    return S.summary()


if __name__ == "__main__":
    raise SystemExit(main())
