"""Verification assurance regressions, grouped by behavior."""

from datetime import datetime, timedelta, timezone
from app.verification.assurance import compute_assurance, effective_status, is_expired
from app.verification.schema import (
    AssuranceLevel,
    Verification,
    VerificationMethod,
    VerificationStatus,
    ClaimStrength,
    ConcurrentEmployment,
    DocumentFinding,
    DocumentType,
    VerificationSubject,
)
from app.verification.claims import compute_claim_evidence


# Verification assurance

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _v(method, status=VerificationStatus.VERIFIED, *, completed=NOW, expires=None, vid="v1"):
    return Verification(
        id=vid, candidate_id="c1", method=method,
        assurance_level=AssuranceLevel.NONE,  # store stamps the real level; folding uses METHOD_LEVEL
        status=status, requested_at=completed, completed_at=completed,
        expires_at=expires,
    )


def test_no_verifications_is_level_none():
    a = compute_assurance("c1", [], at=NOW)
    assert a.level is AssuranceLevel.NONE
    assert a.methods == [] and a.verified_at is None
    assert a.advisory is True


def test_level_is_the_max_across_verified_methods():
    a = compute_assurance(
        "c1",
        [
            _v(VerificationMethod.SELF_ATTESTED, vid="v1"),
            _v(VerificationMethod.OTP_EMAIL, vid="v2"),
        ],
        at=NOW,
    )
    assert a.level is AssuranceLevel.CONTACT_CONTROL
    assert set(a.methods) == {VerificationMethod.SELF_ATTESTED, VerificationMethod.OTP_EMAIL}


def test_pending_and_failed_outcomes_never_contribute():
    a = compute_assurance(
        "c1",
        [
            _v(VerificationMethod.MANUAL_REVIEW, VerificationStatus.PENDING, vid="v1"),
            _v(VerificationMethod.OTP_PHONE, VerificationStatus.FAILED, vid="v2"),
        ],
        at=NOW,
    )
    assert a.level is AssuranceLevel.NONE
    assert a.methods == []


def test_expiry_is_evaluated_at_read_time_not_read_from_the_stored_status():
    lapsed = _v(VerificationMethod.OTP_EMAIL, expires=NOW - timedelta(days=1))
    assert is_expired(lapsed, at=NOW) is True
    # The row still SAYS verified; the effective status must disagree.
    assert lapsed.status is VerificationStatus.VERIFIED
    assert effective_status(lapsed, at=NOW) is VerificationStatus.EXPIRED

    a = compute_assurance("c1", [lapsed], at=NOW)
    assert a.level is AssuranceLevel.NONE
    assert a.methods == []
    assert a.expired_methods == [VerificationMethod.OTP_EMAIL]


def test_a_lapsed_method_downgrades_but_is_still_reported_for_re_verification():
    a = compute_assurance(
        "c1",
        [
            _v(VerificationMethod.SELF_ATTESTED, expires=NOW + timedelta(days=10), vid="v1"),
            _v(VerificationMethod.MANUAL_REVIEW, expires=NOW - timedelta(days=1), vid="v2"),
        ],
        at=NOW,
    )
    assert a.level is AssuranceLevel.SELF_ATTESTED
    assert a.methods == [VerificationMethod.SELF_ATTESTED]
    assert a.expired_methods == [VerificationMethod.MANUAL_REVIEW]


def test_a_null_expiry_never_lapses():
    assert is_expired(_v(VerificationMethod.SELF_ATTESTED, expires=None), at=NOW) is False


def test_verified_at_is_the_most_recent_contributing_outcome():
    older = _v(VerificationMethod.SELF_ATTESTED, completed=NOW - timedelta(days=5), vid="v1")
    newer = _v(VerificationMethod.OTP_EMAIL, completed=NOW - timedelta(days=1), vid="v2")
    a = compute_assurance("c1", [older, newer], at=NOW)
    assert a.verified_at == NOW - timedelta(days=1)


def test_naive_datetimes_are_treated_as_utc():
    # SQLite hands back naive datetimes even from timezone=True columns (S3.1).
    naive = Verification(
        id="v1", candidate_id="c1", method=VerificationMethod.OTP_EMAIL,
        assurance_level=AssuranceLevel.CONTACT_CONTROL,
        status=VerificationStatus.VERIFIED,
        requested_at=datetime(2026, 7, 31, 11, 0),
        completed_at=datetime(2026, 7, 31, 11, 0),
        expires_at=datetime(2026, 7, 31, 13, 0),
    )
    assert is_expired(naive, at=NOW) is False
    assert compute_assurance("c1", [naive], at=NOW).level is AssuranceLevel.CONTACT_CONTROL


def test_methods_and_expired_methods_are_deduplicated_and_deterministic():
    a = compute_assurance(
        "c1",
        [
            _v(VerificationMethod.OTP_EMAIL, vid="v1"),
            _v(VerificationMethod.OTP_EMAIL, vid="v2"),
        ],
        at=NOW,
    )
    assert a.methods == [VerificationMethod.OTP_EMAIL]


# Verification claims

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


def test_a_rogue_identity_row_for_a_claim_method_contributes_nothing_not_a_crash():
    """REVIEW. Belt and braces behind the spine's subject gate and the store's
    mismatch refusal. `compute_assurance` used to index METHOD_LEVEL directly,
    so one such row 500'd the candidate's own portal on EVERY subsequent read —
    permanently. It must degrade to "contributes nothing" instead."""
    rogue = Verification(
        id="v-rogue", candidate_id="c1",
        method=VerificationMethod.EXPERIENCE_LETTER,
        assurance_level=AssuranceLevel.NONE,
        subject=VerificationSubject.IDENTITY,      # the incoherent combination
        status=VerificationStatus.VERIFIED,
        requested_at=NOW, completed_at=NOW,
    )
    a = compute_assurance("c1", [rogue, _identity()], at=NOW)
    assert a.level is AssuranceLevel.SELF_ATTESTED     # the real row still counts
    assert a.methods == [VerificationMethod.SELF_ATTESTED]


def test_an_epfo_row_could_not_reach_strength_four_without_the_spine_writing_one():
    """Belt and braces on the inert adapter: if some future path DID write a
    verified epfo row, the ladder would honour it -- which is exactly why the
    spine's `implemented=False` gate, not this function, is the protection."""
    row = _claim(VerificationMethod.EPFO_EMPLOYMENT)
    assert compute_claim_evidence("c1", [row], at=NOW).strength is (
        ClaimStrength.THIRD_PARTY_VERIFIED
    )
