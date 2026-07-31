"""S7.1 pure assurance folding. No I/O, no clock -- `at` is always injected."""

from datetime import datetime, timedelta, timezone

from app.verification.assurance import compute_assurance, effective_status, is_expired
from app.verification.schema import (
    AssuranceLevel, Verification, VerificationMethod, VerificationStatus,
)

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
