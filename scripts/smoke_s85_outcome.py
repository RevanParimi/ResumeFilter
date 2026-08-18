"""S8.5 smoke: the customer closes the loop, over real HTTP, in a browser's posture.

`POST /report/{id}/outcome` is the OPERATOR's route. Until this sprint an
organisation that screened 400 resumes and formed a judgment had nowhere to put
it -- and that judgment is PI-9's calibration input.

Key-less by construction. DEE_OPENROUTER_API_KEY is pinned empty because S7.3
found a developer with a real key in .env silently shipping junk to a live
vendor from a smoke that CLAIMED to prove the no-key path. Four sprints running
now.

What a unit test cannot prove and this does:

  * a real session, a real CSRF token and a real cookie jar. S8.4 Phase B's
    smoke found that one client which signs up and THEN sends X-Org-Key still
    holds a session cookie, so CSRF -- which keys on how the principal was
    established, not on which header arrived -- refuses every POST with 403.
    The unit tests here all use X-Org-Key on a cookie-less client; this one
    drives the route the way the wired UI does.
  * `recorded_by_org_user_id` is a REAL org_user id here, not None. Every unit
    test in this sprint uses a machine credential, which has no human behind
    it -- so the human-attribution half of the provenance decision is only ever
    exercised end to end.
  * a 404 on a WRITE for another org's report, over HTTP, byte-identical to an
    unknown id.
  * the operator's note stays invisible to the customer while the operator's
    own view still shows both.
  * erasure destroys the judgment through the real foreign keys.

Runs with email_provider=capture, so the codes land in a file instead of a
mailbox. That is selected by EXPLICIT config -- never by fallback -- and prod
refuses to boot with it (app/core/boot.py).

Run from repo root:   python scripts/smoke_s85_outcome.py
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx


from _smoke import Smoke, base_env, wait_healthy


S = Smoke("smoke_s85_outcome")
PORT = 8085
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# The fixture ships with no contact block, so one is spliced in AFTER the
# header line -- heuristic extraction reads line 0 for the name.
_LINES = (FIXTURES / "genuine_genai_resume.txt").read_text(encoding="utf-8").splitlines()
CANDIDATE_EMAIL = "priya.nair@example.in"
GENUINE = "\n".join([_LINES[0], f"Email: {CANDIDATE_EMAIL}"] + _LINES[1:])

OTHER = """Deepak Kulkarni
Email: deepak.kulkarni@example.in

EXPERIENCE
Backend Engineer at Zeta Systems - Jun 2020 - Present

SKILLS
Java, Spring, PostgreSQL
"""




def _code_for(mailbox: Path, email: str) -> str:
    """The newest code addressed to THIS recipient -- not the newest line in
    the file. Several flows interleave here, and reading the last line
    regardless of recipient hands one person's code to another client."""
    for raw in reversed(mailbox.read_text(encoding="utf-8").splitlines()):
        msg = json.loads(raw)
        if msg["to"].strip().lower() == email.strip().lower():
            return re.search(r"\b(\d{6})\b", msg["body"]).group(1)
    raise AssertionError(f"no code was sent to {email}")


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
    url = "sqlite:///" + (scratch / "smoke_s85.db").as_posix()
    flywheel = scratch / "flywheel.jsonl"
    print(f"scratch DB: {url}")
    print(f"mailbox:    {mailbox}")

    env = base_env()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_FLYWHEEL_PATH": flywheel.as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        # Pinned EMPTY on purpose (the S7.3 lesson): a developer with a real key
        # in .env would otherwise ship live billed calls from a smoke that
        # claims to prove the no-key path.
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_API_AUTH_KEY": ADMIN,
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
        c = httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5))
        opened.append(c)
        return c

    def signup_and_verify(email: str, org_name: str):
        c = _client()
        r = c.post("/auth/org/signup",
                   json={"email": email, "organization_name": org_name})
        if r.status_code != 202:
            print(f"    signup for {org_name} failed: {r.status_code} {r.text}")
            return None
        v = c.post("/auth/org/verify",
                   json={"email": email, "code": _code_for(mailbox, email)})
        if v.status_code != 200:
            print(f"    verify for {org_name} failed: {v.status_code} {v.text}")
            return None
        body = v.json()
        return OrgSession(c, body["csrf_token"], body["organization_id"])

    try:
        boot = _client()
        booted = wait_healthy(boot)
        S.check("healthz", booted)
        if not booted:
            print("server did not become healthy")
            return 1

        admin = _client()

        org_a = signup_and_verify("ops@agency-a.example", "Agency A")
        org_b = signup_and_verify("ops@agency-b.example", "Agency B")
        S.check("org_a_session", org_a is not None)
        S.check("org_b_session", org_b is not None)
        if org_a is None or org_b is None:
            print("aborting: an org could not onboard")
            return 1

        up = org_a.post("/screening/candidates",
                        {"resume_text": GENUINE, "domain": "genai"})
        S.check("org_a_upload", up.status_code == 200,
              up.text if up.status_code != 200 else "")
        body = up.json()
        report_id, candidate_id = body["report"]["id"], body["candidate_id"]

        # 1. Nothing recorded yet -- and that is an empty LIST, not a 404.
        empty = org_a.get(f"/screening/reports/{report_id}/outcomes")
        S.check("empty_before_any_judgment",
              empty.status_code == 200 and empty.json()["outcomes"] == [],
              f"{empty.status_code} {empty.text[:120]}")

        # 2. THE LOOP CLOSES, through a session + CSRF -- the posture the wired
        #    UI actually uses, and the one S8.4 Phase B found refuses POSTs
        #    with 403 when a cookie and X-Org-Key are mixed.
        rec = org_a.post(
            f"/screening/reports/{report_id}/outcome",
            {"outcome": "verified_fabricated",
             "notes": "the employer had never heard of them"},
        )
        S.check("org_records_an_outcome", rec.status_code == 200,
              rec.text if rec.status_code != 200 else "")

        listed = org_a.get(f"/screening/reports/{report_id}/outcomes")
        rows = listed.json().get("outcomes", []) if listed.status_code == 200 else []
        S.check("org_reads_it_back",
              len(rows) == 1 and rows[0]["outcome"] == "verified_fabricated",
              f"{listed.status_code} {listed.text[:160]}")

        # 3. THE HUMAN. Every unit test in this sprint uses X-Org-Key, which is
        #    a MACHINE credential with no human behind it -- so this is the only
        #    place the org_user attribution is exercised at all.
        S.check("a_human_is_attributed",
              bool(rows) and bool(rows[0].get("recorded_by_org_user_id")),
              f"recorded_by_org_user_id={rows[0].get('recorded_by_org_user_id') if rows else None}")
        S.check("and_the_org_is_too",
              bool(rows) and rows[0].get("org_id") == org_a.org_id
              and rows[0].get("recorded_by") == "organization",
              f"org_id={rows[0].get('org_id') if rows else None}")

        # 4-5. A claim-level judgment, and a claim that is not in the report.
        claim_id = (body["report"].get("verdicts") or [{}])[0].get("claim_id")
        if claim_id:
            ok = org_a.post(f"/screening/reports/{report_id}/outcome",
                            {"outcome": "candidate_clarified", "claim_id": claim_id})
            S.check("claim_level_outcome", ok.status_code == 200,
                  ok.text if ok.status_code != 200 else "")
        else:
            S.check("claim_level_outcome", False, "the report carried no verdicts")
        bad = org_a.post(f"/screening/reports/{report_id}/outcome",
                         {"outcome": "verified_genuine", "claim_id": "clm_not_there"})
        S.check("unknown_claim_422", bad.status_code == 422,
              f"got {bad.status_code} {bad.text[:120]}")

        # 6. The notes cap, at the customer's door.
        over = org_a.post(f"/screening/reports/{report_id}/outcome",
                          {"outcome": "inconclusive", "notes": "x" * 2001})
        S.check("notes_cap_422",
              over.status_code == 422 and "max_outcome_notes_chars" in over.text,
              f"got {over.status_code} {over.text[:120]}")

        # 7-9. THE ISOLATION, on a WRITE. The instinct on a refused write is
        #      403, and a 403 confirms the report exists to anyone guessing ids.
        theirs = org_b.post(f"/screening/reports/{report_id}/outcome",
                            {"outcome": "verified_genuine"})
        absent = org_b.post("/screening/reports/no-such-report/outcome",
                            {"outcome": "verified_genuine"})
        S.check("cross_org_write_404", theirs.status_code == 404,
              f"got {theirs.status_code}")
        S.check("cross_org_write_404_matches_absent",
              absent.status_code == 404 and theirs.text == absent.text,
              f"theirs={theirs.status_code} absent={absent.status_code}")
        theirs_get = org_b.get(f"/screening/reports/{report_id}/outcomes")
        S.check("cross_org_read_404", theirs_get.status_code == 404,
              f"got {theirs_get.status_code}")

        # 10-11. THE DOWNWARD LEAK, which is the one this route could plausibly
        #        introduce: a report has exactly ONE owning org, so nothing can
        #        leak sideways -- but the operator's internal note about a
        #        customer's report lives on that same report.
        note = "internal: this agency keeps uploading fakes"
        adm = admin.post(f"/report/{report_id}/outcome",
                         json={"outcome": "inconclusive", "notes": note},
                         headers=ADMIN_H)
        S.check("operator_can_still_record", adm.status_code == 200,
              adm.text if adm.status_code != 200 else "")
        mine = org_a.get(f"/screening/reports/{report_id}/outcomes").text
        everything = admin.get(f"/report/{report_id}/outcomes",
                               headers=ADMIN_H).json()["outcomes"]
        S.check("operator_note_invisible_to_the_customer",
              note not in mine and any(note == o["notes"] for o in everything),
              f"customer_sees={len(json.loads(mine)['outcomes'])} operator_sees={len(everything)}")

        # 12. An unowned (admin-uploaded) report is nobody's, not everybody's.
        adm_up = admin.post("/candidates",
                            json={"resume_text": OTHER, "domain": "genai"},
                            headers=ADMIN_H)
        adm_report = (adm_up.json().get("report") or {}).get("id")
        S.check("unowned_report_is_404_for_an_org",
              org_a.post(f"/screening/reports/{adm_report}/outcome",
                         {"outcome": "verified_genuine"}).status_code == 404)

        # 13. The flywheel got the label and the provenance -- and NOT the note.
        #     That file is append-only with no erasure path.
        wheel = [
            json.loads(line)
            for line in flywheel.read_text(encoding="utf-8").splitlines()
            if '"record_type": "outcome"' in line
        ] if flywheel.exists() else []
        S.check("flywheel_has_the_label_and_provenance_not_the_note",
              bool(wheel)
              and all("notes" not in r for r in wheel)
              and any(r.get("recorded_by") == "organization" for r in wheel)
              and not any("had never heard" in json.dumps(r) for r in wheel),
              f"{len(wheel)} outcome record(s)")

        # 14-15. DPDP: erasure destroys the judgment through the real FKs,
        #        with nobody remembering to (outcomes -> reports -> candidates).
        erased = admin.delete(f"/candidates/{candidate_id}", headers=ADMIN_H)
        S.check("candidate_erased", erased.status_code in (200, 204),
              f"got {erased.status_code} {erased.text[:120]}")
        gone = admin.get(f"/report/{report_id}/outcomes", headers=ADMIN_H)
        S.check("erasure_destroys_the_judgment", gone.status_code == 404,
              f"got {gone.status_code} {gone.text[:120]}")
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
