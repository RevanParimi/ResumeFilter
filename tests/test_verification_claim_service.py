"""S7.2 orchestration: parse -> assess -> one audited claim row, and the
document does not survive the call."""

import base64
from datetime import datetime, timezone

import pytest

from app.candidates.schema import (
    CandidateProfile, DateRange, ExperienceEntry, ExtractionResult,
)
from app.ledger.schema import ConsentPurpose
from app.ledger.store import LedgerStore
from app.verification.documents import DocumentParseError
from app.verification.schema import (
    AssuranceLevel, ClaimStrength, DocumentType, VerificationMethod,
    VerificationStatus, VerificationSubject,
)
from app.verification.service import DocumentTooLargeError, VerificationService
from app.verification.store import VerificationStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)

LETTER = b"""ACME TECHNOLOGIES PRIVATE LIMITED
hr@acme.com
This is to certify that A Candidate (Employee ID ACM-1) was employed with Acme
Technologies as a Senior Software Engineer from March 2021 to January 2024.
Head of Human Resources
"""


def _ingest(candidates, *experience):
    """A candidate WITH a resume on file, so the forensics have something to
    corroborate against. Without one every document reads
    `no_profile_to_compare` and nothing can ever fail."""
    profile = CandidateProfile(
        experience=[
            ExperienceEntry(employer=emp, title=title,
                            dates=DateRange(start=start, end=end))
            for emp, title, start, end in experience
        ]
    )
    outcome = candidates.ingest(
        ExtractionResult(profile=profile, method="heuristic"), "resume text")
    return outcome.candidate_id


@pytest.fixture
def svc(settings):
    candidates = make_candidate_store()
    ledger = LedgerStore(candidates._session_factory,
                         default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
                         settings=settings)
    store = VerificationStore(candidates._session_factory, ledger=ledger, settings=settings)
    service = VerificationService(store, candidates, ledger, settings=settings)
    cid = _ingest(candidates,
                  ("Acme Technologies", "Senior Software Engineer", "2021-03", "2024-01"))
    return service, ledger, cid


def _b64(data=LETTER):
    return base64.b64encode(data).decode("ascii")


def test_submitting_a_letter_writes_one_claim_verification(svc):
    service, _, cid = svc
    v, findings, evidence = service.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)
    assert v.subject is VerificationSubject.EMPLOYMENT_CLAIM
    assert v.method is VerificationMethod.EXPERIENCE_LETTER
    assert v.status is VerificationStatus.VERIFIED
    assert evidence.strength is ClaimStrength.DOCUMENTED
    assert isinstance(findings, list)


def test_the_evidence_digest_is_stored_and_the_document_is_not(svc):
    service, _, cid = svc
    v, _, _ = service.submit_document(cid, DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)
    assert v.evidence_digest and len(v.evidence_digest) == 64
    stored = str(service._store.get_verification(v.id).model_dump())
    assert "ACME TECHNOLOGIES" not in stored
    assert "hr@acme.com" not in stored


def test_a_claim_submission_never_lifts_identity_assurance(svc):
    service, _, cid = svc
    service.submit_document(cid, DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)
    assert service.assurance_for_candidate(cid, at=NOW).level is AssuranceLevel.NONE


def test_a_document_with_hard_findings_fails_but_does_not_lower_anything(svc):
    service, _, cid = svc
    service.submit_document(cid, DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)
    v, _, evidence = service.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER,
        _b64(b"Employed with Globex Corp as an Engineer. Head of Human Resources."),
        at=NOW)
    assert v.status is VerificationStatus.FAILED
    assert evidence.strength is ClaimStrength.DOCUMENTED   # the good one still holds


def test_a_payslip_never_stores_a_salary_or_a_uan(svc):
    """Spec section 5, enforced end to end rather than only in the pure layer."""
    service, _, cid = svc
    slip = (b"ACME TECHNOLOGIES PRIVATE LIMITED\nPayslip for March 2023\n"
            b"UAN: 100234567890\nGross Salary: 100000\nTotal Deductions: 22000\n"
            b"Net Pay: 78000\n")
    v, _, _ = service.submit_document(cid, DocumentType.PAYSLIP, _b64(slip), at=NOW)
    stored = str(service._store.get_verification(v.id).model_dump())
    for secret in ("100234567890", "100000", "78000", "22000"):
        assert secret not in stored


def test_an_oversize_body_is_refused_before_it_is_decoded(svc, settings, monkeypatch):
    service, _, cid = svc
    monkeypatch.setattr(settings, "doc_max_b64_chars", 32)
    with pytest.raises(DocumentTooLargeError):
        service.submit_document(cid, DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)


def test_an_unparseable_body_raises_a_parse_error(svc):
    service, _, cid = svc
    with pytest.raises(DocumentParseError):
        service.submit_document(cid, DocumentType.EXPERIENCE_LETTER, "!!!", at=NOW)


def test_an_unknown_candidate_is_a_lookup_error(svc):
    service, _, _ = svc
    with pytest.raises(LookupError):
        service.submit_document("nope", DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)


def test_a_rejected_submission_writes_no_row_at_all(svc):
    """An unparseable body must not leave a dangling pending verification."""
    service, _, cid = svc
    with pytest.raises(DocumentParseError):
        service.submit_document(cid, DocumentType.EXPERIENCE_LETTER, "!!!", at=NOW)
    assert service._store.verifications_for_candidate(cid) == []


def test_epfo_stays_inert_even_with_an_identity_verify_grant(svc):
    """Same shape as the government_id test. Lawful, but no vendor exists."""
    service, ledger, cid = svc
    ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.IDENTITY_VERIFY,
                         org_id=None)
    with pytest.raises(NotImplementedError):
        service.start(cid, VerificationMethod.EPFO_EMPLOYMENT, at=NOW)
    assert service.claims_for_candidate(cid, at=NOW).strength is ClaimStrength.NONE


def test_a_single_role_produces_no_concurrent_advisory(svc):
    service, _, cid = svc
    assert service.claims_for_candidate(cid, at=NOW).concurrent_employment is None


def test_the_claim_roll_up_carries_the_concurrent_advisory(settings):
    """Derived read-time from the resume: it appears with no document ever
    submitted, and it is not evidence FOR anything -- strength stays NONE."""
    candidates = make_candidate_store()
    ledger = LedgerStore(candidates._session_factory,
                         default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
                         settings=settings)
    store = VerificationStore(candidates._session_factory, ledger=ledger, settings=settings)
    service = VerificationService(store, candidates, ledger, settings=settings)
    cid = _ingest(candidates,
                  ("Acme Technologies", "Engineer", "2021-01", "2023-12"),
                  ("Globex Corp", "Engineer", "2022-01", "2023-12"))

    evidence = service.claims_for_candidate(cid, at=NOW)
    assert evidence.concurrent_employment is not None
    assert evidence.concurrent_employment.periods == ["2022-01..2023-12"]
    assert evidence.concurrent_employment.advisory is True
    assert evidence.strength is ClaimStrength.NONE
