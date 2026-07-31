"""S7.2 routes. Cross-candidate isolation stays structural: the subject is
resolved from the key, never from the body."""

import base64

import pytest
from fastapi.testclient import TestClient

from app.candidates.hashing import contact_hash, normalize_email
from app.candidates.schema import (
    CandidateProfile, ContactInfo, DateRange, ExperienceEntry, ExtractedStr,
    ExtractionResult,
)
from app.main import create_app
from tests.conftest import make_services

EMAIL = "dev@example.com"
LETTER = (b"ACME TECHNOLOGIES PRIVATE LIMITED\nhr@acme.com\n"
          b"This is to certify that A Candidate (Employee ID ACM-1) was employed "
          b"with Acme Technologies as a Senior Software Engineer from March 2021 "
          b"to January 2024.\nHead of Human Resources\n")

PAYSLIP_BAD = (b"ACME TECHNOLOGIES PRIVATE LIMITED\nPayslip for March 2023\n"
               b"UAN: 100234567890\nGross Salary: 100000\n"
               b"Total Deductions: 22000\nNet Pay: 95000\n")


def _candidate(services, email=EMAIL, name="A Candidate", experience=None):
    """A candidate with a resume on file -- the forensics need something to
    corroborate against, and the real portal candidate always has one."""
    store = services.candidates
    profile = CandidateProfile(
        full_name=ExtractedStr(value=name),
        contact=ContactInfo(
            email_hash=contact_hash(normalize_email(email),
                                    services.settings.contact_hash_salt),
        ),
        experience=[
            ExperienceEntry(employer=emp, title=title,
                            dates=DateRange(start=start, end=end))
            for emp, title, start, end in (experience or [
                ("Acme Technologies", "Senior Software Engineer", "2021-03", "2024-01"),
            ])
        ],
    )
    outcome = store.ingest(
        ExtractionResult(profile=profile, method="heuristic"), f"resume for {email}")
    return outcome.candidate_id, store.issue_access_key(outcome.candidate_id)


@pytest.fixture
def client(settings):
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c, services


def _b64(data=LETTER):
    return base64.b64encode(data).decode("ascii")


def _submit(c, key, data=LETTER, doc_type="experience_letter"):
    return c.post("/portal/documents",
                  json={"doc_type": doc_type, "content_b64": _b64(data)},
                  headers={"X-Candidate-Key": key})


def test_documents_require_a_candidate_key(client):
    c, _ = client
    assert c.post("/portal/documents", json={"doc_type": "experience_letter",
                                             "content_b64": _b64()}).status_code == 401


def test_a_wrong_candidate_key_is_401(client):
    c, _ = client
    assert _submit(c, "not-a-real-key").status_code == 401


def test_submitting_a_letter_returns_the_verification_findings_and_claims(client):
    c, services = client
    _, key = _candidate(services)
    r = _submit(c, key)
    assert r.status_code == 200
    body = r.json()
    assert body["verification"]["subject"] == "employment_claim"
    assert body["claims"]["strength"] == 2          # DOCUMENTED
    assert isinstance(body["findings"], list)


def test_the_response_never_echoes_the_document(client):
    c, services = client
    _, key = _candidate(services)
    r = _submit(c, key)
    assert "ACME TECHNOLOGIES" not in r.text
    assert "hr@acme.com" not in r.text
    assert "ACM-1" not in r.text


def test_a_payslip_response_carries_no_salary_or_uan(client):
    c, services = client
    _, key = _candidate(services)
    r = _submit(c, key, PAYSLIP_BAD, "payslip")
    assert r.status_code == 200
    assert r.json()["verification"]["status"] == "failed"
    for secret in ("100234567890", "100000", "95000", "22000"):
        assert secret not in r.text


def test_a_claim_does_not_lift_the_identity_level_over_http(client):
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}
    _submit(c, key)
    listed = c.get("/portal/verifications", headers=h).json()
    assert listed["assurance"]["level"] == 0
    assert listed["claims"]["strength"] == 2


def test_bad_base64_is_a_400(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post("/portal/documents", json={"doc_type": "experience_letter",
                                          "content_b64": "!!!"},
               headers={"X-Candidate-Key": key})
    assert r.status_code == 400


def test_an_unknown_doc_type_is_a_422(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post("/portal/documents", json={"doc_type": "affidavit",
                                          "content_b64": _b64()},
               headers={"X-Candidate-Key": key})
    assert r.status_code == 422


def test_an_oversize_body_is_a_422(client, monkeypatch):
    c, services = client
    monkeypatch.setattr(services.settings, "doc_max_b64_chars", 32)
    _, key = _candidate(services)
    r = _submit(c, key)
    assert r.status_code == 422


def test_epfo_over_http_is_422_even_after_a_self_granted_consent(client):
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}
    assert c.post("/portal/consents", json={"purpose": "identity_verify"},
                  headers=h).status_code == 200
    r = c.post("/portal/verifications", json={"method": "epfo_employment"}, headers=h)
    assert r.status_code == 422
    assert c.get("/portal/verifications", headers=h).json()["claims"]["strength"] == 0


def test_one_candidates_document_cannot_appear_in_anothers_claims(client):
    c, services = client
    _, key_a = _candidate(services)
    _, key_b = _candidate(services, email="other@example.com", name="Other")
    _submit(c, key_a)
    other = c.get("/portal/verifications", headers={"X-Candidate-Key": key_b}).json()
    assert other["claims"]["strength"] == 0
    assert other["verifications"] == []


def test_a_claim_ref_in_the_body_cannot_redirect_the_row_to_another_candidate(client):
    """claim_ref is a free-text LABEL. It must not be able to act as a subject
    selector -- the candidate always comes from the key."""
    c, services = client
    cid_a, key_a = _candidate(services)
    cid_b, key_b = _candidate(services, email="other@example.com", name="Other")
    r = c.post("/portal/documents",
               json={"doc_type": "experience_letter", "content_b64": _b64(),
                     "claim_ref": cid_b},
               headers={"X-Candidate-Key": key_a})
    assert r.status_code == 200
    assert r.json()["verification"]["candidate_id"] == cid_a
    assert c.get("/portal/verifications",
                 headers={"X-Candidate-Key": key_b}).json()["verifications"] == []


# ── Review regressions (whole-branch review, 2026-07-31) ────────────────────
# Both were reproduced over HTTP with nothing but a candidate's own key.


@pytest.mark.parametrize("method", ["experience_letter", "payslip"])
def test_a_claim_method_cannot_be_started_through_the_identity_route(client, method):
    """REVIEW / CRITICAL. `POST /portal/verifications` accepts any
    VerificationMethod, and S7.2's claim adapters declare `instant=True`
    ("assessment IS the evidence") — true of submit_document, false here where
    no document exists. As first built this returned 200 `verified` with
    `subject: identity`, and every later read of the candidate's own portal
    then 500'd on a KeyError, permanently. Same failure class as the S7.1
    escalation: a gate applied at one entry point and not the other."""
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}

    assert c.post("/portal/verifications", json={"method": method},
                  headers=h).status_code == 403

    listed = c.get("/portal/verifications", headers=h)
    assert listed.status_code == 200            # not a 500, and not bricked
    assert listed.json()["assurance"]["level"] == 0
    assert listed.json()["claims"]["strength"] == 0
    assert listed.json()["verifications"] == []


def test_epfo_still_answers_422_and_not_the_subject_gate(client):
    """The subject gate sits AFTER `implemented`, so a declared-but-inert
    method answers the same way at every door: `epfo_employment` stays
    indistinguishable from `government_id` (spec section 3)."""
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}
    c.post("/portal/consents", json={"purpose": "identity_verify"}, headers=h)
    assert c.post("/portal/verifications", json={"method": "epfo_employment"},
                  headers=h).status_code == 422
    assert c.post("/portal/verifications", json={"method": "government_id"},
                  headers=h).status_code == 422


def test_an_oversize_claim_ref_is_refused_and_nothing_is_stored(client):
    """REVIEW / CRITICAL. SQLite does not enforce VARCHAR(128), so `claim_ref`
    — the ONE column the models test excepts from its 64-char cap — was an
    unbounded text field. 5031 chars of document text, a salary and a UAN went
    straight into a verifications row, defeating the structural guarantee that
    no column can hold an artifact."""
    from app.verification.models import VerificationRow

    c, services = client
    _, key = _candidate(services)
    r = c.post("/portal/documents",
               json={"doc_type": "experience_letter", "content_b64": _b64(),
                     "claim_ref": "SALARY 100000 UAN 100234567890 " + "X" * 5000},
               headers={"X-Candidate-Key": key})
    assert r.status_code == 422

    with services.candidates._session_factory() as s:
        rows = s.query(VerificationRow).all()
    assert rows == []                            # refused before any write


def test_a_claim_ref_at_the_limit_is_accepted(client):
    """The cap is the column width, not a smaller number invented at the edge."""
    from app.verification.schema import CLAIM_REF_MAX_CHARS

    c, services = client
    _, key = _candidate(services)
    r = c.post("/portal/documents",
               json={"doc_type": "experience_letter", "content_b64": _b64(),
                     "claim_ref": "A" * CLAIM_REF_MAX_CHARS},
               headers={"X-Candidate-Key": key})
    assert r.status_code == 200


def _org(services):
    """Same helper tests/test_verification_org_api.py uses."""
    org = services.ledger.create_organization("Acme Corp")
    return org.id, services.ledger.issue_api_key(org.id)


def test_the_org_claims_read_is_consent_gated_and_leaks_no_internals(client):
    from app.ledger.schema import ConsentPurpose

    c, services = client
    cid, key = _candidate(services)
    _submit(c, key)
    org_id, org_key = _org(services)
    org_h = {"X-Org-Key": org_key}
    path = f"/verification/candidates/{cid}/claims"

    assert c.get(path, headers=org_h).status_code == 403

    services.ledger.grant_consent(candidate_id=cid,
                                  purpose=ConsentPurpose.VERIFICATION_READ,
                                  org_id=org_id)
    granted = c.get(path, headers=org_h)
    assert granted.status_code == 200
    assert granted.json()["strength"] == 2
    assert "evidence_digest" not in granted.text
    assert "ACME TECHNOLOGIES" not in granted.text


def test_the_org_claims_read_403s_again_after_the_candidate_revokes(client):
    from app.ledger.schema import ConsentPurpose

    c, services = client
    cid, key = _candidate(services)
    _submit(c, key)
    org_id, org_key = _org(services)
    org_h = {"X-Org-Key": org_key}
    path = f"/verification/candidates/{cid}/claims"

    grant = services.ledger.grant_consent(candidate_id=cid,
                                          purpose=ConsentPurpose.VERIFICATION_READ,
                                          org_id=org_id)
    assert c.get(path, headers=org_h).status_code == 200
    assert c.post(f"/portal/consents/{grant.id}/revoke",
                  headers={"X-Candidate-Key": key}).status_code == 200
    assert c.get(path, headers=org_h).status_code == 403


def test_the_org_claims_read_requires_an_org_key(client):
    c, services = client
    cid, _ = _candidate(services)
    assert c.get(f"/verification/candidates/{cid}/claims").status_code == 401


def test_an_unknown_candidate_is_a_404_for_the_org(client):
    c, services = client
    _, org_key = _org(services)
    r = c.get("/verification/candidates/nope/claims", headers={"X-Org-Key": org_key})
    assert r.status_code == 404


def test_the_org_read_404s_after_dpdp_erasure(client):
    from app.ledger.schema import ConsentPurpose

    c, services = client
    cid, key = _candidate(services)
    _submit(c, key)
    org_id, org_key = _org(services)
    services.ledger.grant_consent(candidate_id=cid,
                                  purpose=ConsentPurpose.VERIFICATION_READ,
                                  org_id=org_id)
    path = f"/verification/candidates/{cid}/claims"
    assert c.get(path, headers={"X-Org-Key": org_key}).status_code == 200

    assert c.delete("/portal/me", headers={"X-Candidate-Key": key}).status_code == 200
    assert c.get(path, headers={"X-Org-Key": org_key}).status_code == 404
