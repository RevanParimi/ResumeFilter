"""S7.2 roll-up. The load-bearing test in this file is the isolation one:
a payslip must never lift IdentityAssurance."""

from datetime import datetime, timedelta, timezone

from app.verification.assurance import compute_assurance
from app.verification.claims import compute_claim_evidence
from app.verification.schema import (
    AssuranceLevel, ClaimStrength, ConcurrentEmployment, DocumentFinding,
    DocumentType, Verification, VerificationMethod, VerificationStatus,
    VerificationSubject,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _claim(method=VerificationMethod.EXPERIENCE_LETTER,
           status=VerificationStatus.VERIFIED, expires=None, details=None):
    return Verification(
        id=f"v-{method.value}-{status.value}",
        candidate_id="c1",
        method=method,
        assurance_level=AssuranceLevel.NONE,
        subject=VerificationSubject.EMPLOYMENT_CLAIM,
        status=status,
        details=details or {},
        requested_at=NOW,
        completed_at=NOW,
        expires_at=expires,
    )


def _identity(method=VerificationMethod.SELF_ATTESTED):
    return Verification(
        id=f"v-id-{method.value}",
        candidate_id="c1",
        method=method,
        assurance_level=AssuranceLevel.SELF_ATTESTED,
        subject=VerificationSubject.IDENTITY,
        status=VerificationStatus.VERIFIED,
        requested_at=NOW,
        completed_at=NOW,
    )


def test_a_verified_claim_never_lifts_identity_assurance():
    """THE invariant. Same failure class as the S7.1 ladder escalation."""
    a = compute_assurance("c1", [_claim(), _claim(VerificationMethod.PAYSLIP)], at=NOW)
    assert a.level is AssuranceLevel.NONE
    assert a.methods == []


def test_an_identity_verification_never_lifts_claim_strength():
    ev = compute_claim_evidence("c1", [_identity()], at=NOW)
    assert ev.strength is ClaimStrength.NONE
    assert ev.documents == []


def test_the_two_ladders_coexist_on_one_candidate():
    rows = [_identity(), _claim()]
    assert compute_assurance("c1", rows, at=NOW).level is AssuranceLevel.SELF_ATTESTED
    assert compute_claim_evidence("c1", rows, at=NOW).strength is ClaimStrength.DOCUMENTED


def test_strength_is_the_highest_held():
    rows = [_claim(), _claim(VerificationMethod.PAYSLIP)]
    ev = compute_claim_evidence("c1", rows, at=NOW)
    assert ev.strength is ClaimStrength.DOCUMENTED
    assert set(ev.documents) == {DocumentType.EXPERIENCE_LETTER, DocumentType.PAYSLIP}


def test_a_failed_claim_contributes_nothing_but_keeps_its_findings():
    """A bad submission leaves the candidate exactly where they were."""
    failed = _claim(status=VerificationStatus.FAILED, details={
        "findings": [{"id": "payslip_arithmetic_mismatch", "severity": "hard",
                      "message": "gross minus deductions does not equal net"}]
    })
    ev = compute_claim_evidence("c1", [failed], at=NOW)
    assert ev.strength is ClaimStrength.NONE
    assert [f.id for f in ev.findings] == ["payslip_arithmetic_mismatch"]


def test_an_expired_claim_stops_contributing():
    stale = _claim(expires=NOW - timedelta(days=1))
    assert compute_claim_evidence("c1", [stale], at=NOW).strength is ClaimStrength.NONE


def test_findings_from_contributing_rows_are_surfaced():
    row = _claim(details={"findings": [
        {"id": "issuer_domain_unknown", "severity": "soft", "message": "no domain"}
    ]})
    ev = compute_claim_evidence("c1", [row], at=NOW)
    assert [f.id for f in ev.findings] == ["issuer_domain_unknown"]
    assert isinstance(ev.findings[0], DocumentFinding)


def test_malformed_stored_findings_are_skipped_not_fatal():
    """Old or hand-edited rows must not 500 a candidate's own portal."""
    row = _claim(details={"findings": [{"nope": 1}, "not-a-dict"]})
    assert compute_claim_evidence("c1", [row], at=NOW).findings == []


def test_the_concurrent_advisory_is_passed_through_untouched():
    ce = ConcurrentEmployment(periods=["2023-04..2024-02"], max_overlap_months=10,
                              severity="soft")
    ev = compute_claim_evidence("c1", [], at=NOW, concurrent=ce)
    assert ev.concurrent_employment == ce
    assert ev.strength is ClaimStrength.NONE   # an overlap is not evidence FOR a claim


def test_empty_is_none_and_advisory():
    ev = compute_claim_evidence("c1", [], at=NOW)
    assert ev.strength is ClaimStrength.NONE and ev.advisory is True


def test_an_epfo_row_could_not_reach_strength_four_without_the_spine_writing_one():
    """Belt and braces on the inert adapter: if some future path DID write a
    verified epfo row, the ladder would honour it -- which is exactly why the
    spine's `implemented=False` gate, not this function, is the protection."""
    row = _claim(VerificationMethod.EPFO_EMPLOYMENT)
    assert compute_claim_evidence("c1", [row], at=NOW).strength is (
        ClaimStrength.THIRD_PARTY_VERIFIED
    )
