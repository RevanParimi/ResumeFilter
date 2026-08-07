"""S8.4 Phase A: the org-plane wedge routes. Two agencies, one candidate."""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _key(services, name):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _with_email(resume: str, email: str = "priya.nair@example.in") -> str:
    """The shipped fixtures carry NO contact block, so identity resolution can
    never match on them -- every upload would fork a new candidate and any
    dedup assertion built on the bare fixture would be inert. Splice a contact
    line in AFTER the header so heuristic name parsing (which reads line 0) is
    unaffected, exactly as scripts/smoke_s84a.py does."""
    lines = resume.splitlines()
    return "\n".join([lines[0], f"Email: {email}"] + lines[1:])


def test_org_can_upload_and_read_its_own_report(services, genuine_resume):
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        up = c.post("/screening/candidates", headers={"X-Org-Key": key},
                    json={"resume_text": genuine_resume, "domain": "genai"})
        assert up.status_code == 200, up.text
        body = up.json()
        report_id = body["report"]["id"]

        got = c.get(f"/screening/reports/{report_id}", headers={"X-Org-Key": key})
        assert got.status_code == 200
        assert got.json()["id"] == report_id


def test_another_orgs_report_is_404_not_403(services, genuine_resume):
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        up = c.post("/screening/candidates", headers={"X-Org-Key": key_a},
                    json={"resume_text": genuine_resume, "domain": "genai"})
        report_id = up.json()["report"]["id"]

        theirs = c.get(f"/screening/reports/{report_id}", headers={"X-Org-Key": key_b})
        absent = c.get("/screening/reports/does-not-exist", headers={"X-Org-Key": key_b})

        assert theirs.status_code == 404
        assert absent.status_code == 404
        assert theirs.json() == absent.json(), (
            "a 403 -- or a different body -- would confirm the report exists"
        )


def test_screening_routes_require_an_org_credential(services):
    with _client(services) as c:
        assert c.get("/screening/reports/x").status_code == 401
        assert c.post("/screening/candidates", json={}).status_code == 401


def test_reports_for_a_candidate_are_scoped_to_the_caller(services, genuine_resume):
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        up = c.post("/screening/candidates", headers={"X-Org-Key": key_a},
                    json={"resume_text": genuine_resume, "domain": "genai"})
        cand = up.json()["candidate_id"]

        mine = c.get(f"/screening/candidates/{cand}/reports", headers={"X-Org-Key": key_a})
        theirs = c.get(f"/screening/candidates/{cand}/reports", headers={"X-Org-Key": key_b})

        assert mine.status_code == 200 and len(mine.json()) == 1
        assert theirs.status_code == 200 and theirs.json() == [], (
            "an empty list, not a 404: 'I have no reports on them' is not "
            "'they do not exist'"
        )


def test_reports_for_a_nonexistent_candidate_are_an_empty_list_not_404(services):
    """A wholly nonexistent candidate id must read the same as one this org has
    simply never uploaded: 200 with []. 'I have no reports on them' and 'they
    do not exist' are different facts, and only the first is this org's
    business -- the facade must not leak the second."""
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        resp = c.get(
            "/screening/candidates/does-not-exist/reports", headers={"X-Org-Key": key}
        )
        assert resp.status_code == 200
        assert resp.json() == []


def test_the_org_report_is_redacted_but_complete(services, farm_resume_a, farm_resume_b):
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        c.post("/screening/candidates", headers={"X-Org-Key": key},
               json={"resume_text": farm_resume_a, "domain": "genai"})
        second = c.post("/screening/candidates", headers={"X-Org-Key": key},
                        json={"resume_text": farm_resume_b, "domain": "genai"})
        report_id = second.json()["report"]["id"]

        body = c.get(f"/screening/reports/{report_id}",
                     headers={"X-Org-Key": key}).json()
        for m in body["resume_farm"]["matches"]:
            assert m["candidate_id"] is None and m["resume_id"] is None
            assert m["similarity"] > 0
        # The org still gets the full report.
        assert "verdicts" in body and "fabrication_risk" in body


def test_org_upload_response_does_not_leak_counterparty_identity(
    services, farm_resume_a, farm_resume_b
):
    """The UPLOAD response -- not just the later GET -- must not carry another
    org's candidate_id/resume_id. _ingest_one's resume_farm scan
    (services.candidates.similar_resumes) is genuinely cross-tenant: fraud
    detection has to see the whole platform's fingerprints, not just this
    org's own. The same assessment appears TWICE in the response (the
    top-level resume_farm and the embedded report's own resume_farm) and both
    must be redacted before screening_create_candidate returns."""
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        c.post("/screening/candidates", headers={"X-Org-Key": key_a},
               json={"resume_text": farm_resume_a, "domain": "genai"})
        up_b = c.post("/screening/candidates", headers={"X-Org-Key": key_b},
                      json={"resume_text": farm_resume_b, "domain": "genai"})
        assert up_b.status_code == 200, up_b.text
        body = up_b.json()

        top_matches = body["resume_farm"]["matches"]
        assert top_matches, "expected a cross-tenant near-duplicate match"
        for m in top_matches:
            assert m["similarity"] > 0
            assert m["candidate_id"] is None
            assert m["resume_id"] is None

        report_matches = body["report"]["resume_farm"]["matches"]
        assert report_matches, "the embedded report carries the same assessment"
        for m in report_matches:
            assert m["similarity"] > 0
            assert m["candidate_id"] is None
            assert m["resume_id"] is None


def test_admin_upload_response_keeps_counterparty_identity(
    services, admin_headers, farm_resume_a, farm_resume_b
):
    """The admin plane's cross-tenant view is unchanged: operators need the
    real ids for fraud support, so the redaction must be org-plane only."""
    _, key_a = _key(services, "Agency A")
    with _client(services) as c:
        c.post("/screening/candidates", headers={"X-Org-Key": key_a},
               json={"resume_text": farm_resume_a, "domain": "genai"})
        up = c.post("/candidates", headers=admin_headers,
                    json={"resume_text": farm_resume_b, "domain": "genai"})
        assert up.status_code == 200, up.text
        body = up.json()

        matches = body["resume_farm"]["matches"]
        assert matches, "expected a cross-tenant near-duplicate match"
        for m in matches:
            assert m["candidate_id"] is not None
            assert m["resume_id"] is not None


def test_two_orgs_uploading_the_same_resume_each_own_it(services, genuine_resume):
    """The most likely real input this product sees: two agencies handed the
    SAME PDF for the same person. One candidate row, one report each, and
    BOTH orgs see her in their own queue -- spec §0.1. The rule has to hold
    over HTTP too, not just at the store: this repo's recurring bug shape is a
    rule that holds at one entry point and lapses at the other."""
    org_a, key_a = _key(services, "Agency A")
    org_b, key_b = _key(services, "Agency B")
    same_pdf = _with_email(genuine_resume)
    with _client(services) as c:
        up_a = c.post("/screening/candidates", headers={"X-Org-Key": key_a},
                      json={"resume_text": same_pdf, "domain": "genai"})
        up_b = c.post("/screening/candidates", headers={"X-Org-Key": key_b},
                      json={"resume_text": same_pdf, "domain": "genai"})
        assert up_a.status_code == 200 and up_b.status_code == 200, up_b.text
        a, b = up_a.json(), up_b.json()

        assert b["candidate_id"] == a["candidate_id"], "one person, one candidate row"
        assert b["duplicate_resume"] is True, "the same bytes were seen before"
        assert b["resume_id"] != a["resume_id"], "each agency owns its own upload"

        assert services.candidates.org_owns_candidate(org_a, a["candidate_id"])
        assert services.candidates.org_owns_candidate(org_b, b["candidate_id"]), (
            "org B uploaded her -- she must not be invisible to the org that "
            "just paid to screen her"
        )

        mine = c.get(f"/screening/candidates/{a['candidate_id']}/reports",
                     headers={"X-Org-Key": key_b})
        assert mine.status_code == 200 and len(mine.json()) == 1


def test_ownership_is_recorded_without_a_report_to_fall_back_on(
    services, genuine_resume
):
    """evaluate=False leaves NO report to stamp, so the resume row is the only
    ownership record there is. If ingest drops org_id on the duplicate branch,
    this upload leaves zero trace of who uploaded it."""
    org_a, key_a = _key(services, "Agency A")
    org_b, key_b = _key(services, "Agency B")
    same_pdf = _with_email(genuine_resume)
    with _client(services) as c:
        c.post("/screening/candidates", headers={"X-Org-Key": key_a},
               json={"resume_text": same_pdf, "domain": "genai",
                     "evaluate": False})
        up_b = c.post("/screening/candidates", headers={"X-Org-Key": key_b},
                      json={"resume_text": same_pdf, "domain": "genai",
                            "evaluate": False})
        assert up_b.status_code == 200, up_b.text
        body = up_b.json()
        assert body["report"] is None

        assert services.candidates.org_owns_candidate(org_b, body["candidate_id"]), (
            "no report exists to carry the ownership -- the resume row must"
        )
        assert services.candidates.org_owns_candidate(org_a, body["candidate_id"])


def test_admin_upload_stays_unowned_and_invisible_to_orgs(services, genuine_resume,
                                                          admin_headers):
    org_id, key = _key(services, "Agency A")
    with _client(services) as c:
        up = c.post("/candidates", headers=admin_headers,
                    json={"resume_text": genuine_resume, "domain": "genai"})
        report_id = up.json()["report"]["id"]

        assert c.get(f"/report/{report_id}", headers=admin_headers).status_code == 200
        assert c.get(f"/screening/reports/{report_id}",
                     headers={"X-Org-Key": key}).status_code == 404
