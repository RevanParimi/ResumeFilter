"""S3.1 pure consent logic: purpose/org scope, expiry, revocation, tz coercion."""

from datetime import datetime, timedelta, timezone

from app.ledger.consent import as_utc, check_consent, is_grant_active
from app.ledger.schema import ConsentGrant, ConsentPurpose

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def grant(**over) -> ConsentGrant:
    base = dict(
        id="g1", candidate_id="c1", org_id=None, purpose="ledger_write",
        granted_at=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=364),
        revoked_at=None,
    )
    base.update(over)
    return ConsentGrant(**base)


def test_active_grant_allows():
    assert is_grant_active(grant(), org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_purpose_must_match():
    assert not is_grant_active(grant(), org_id="o1", purpose=ConsentPurpose.LEDGER_READ, at=NOW)


def test_org_scoped_grant_only_covers_that_org():
    g = grant(org_id="o1")
    assert is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)
    assert not is_grant_active(g, org_id="o2", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_null_org_covers_any_org():
    assert is_grant_active(grant(org_id=None), org_id="o2",
                           purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_not_yet_granted_is_inactive():
    g = grant(granted_at=NOW + timedelta(hours=1))
    assert not is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_expiry_boundary_is_inactive():
    g = grant(expires_at=NOW)  # expires_at <= at -> inactive
    assert not is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_revoked_before_at_is_inactive():
    g = grant(revoked_at=NOW - timedelta(hours=1))
    assert not is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_point_in_time_before_revocation_is_active():
    """Historical queries (PI-4 point-in-time correctness) see pre-revocation truth."""
    g = grant(revoked_at=NOW + timedelta(hours=1))
    assert is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_naive_datetimes_are_treated_as_utc():
    """SQLite returns naive datetimes; they must compare as UTC, not crash."""
    g = grant(granted_at=(NOW - timedelta(days=1)).replace(tzinfo=None),
              expires_at=(NOW + timedelta(days=1)).replace(tzinfo=None))
    assert is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE,
                           at=NOW.replace(tzinfo=None))
    assert as_utc(NOW.replace(tzinfo=None)) == NOW


def test_check_consent_picks_first_active_grant():
    inactive = grant(id="g0", revoked_at=NOW - timedelta(days=1))
    active = grant(id="g2")
    d = check_consent([inactive, active], org_id="o1",
                      purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)
    assert d.allowed and d.grant_id == "g2"


def test_check_consent_denies_with_reason():
    d = check_consent([], org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)
    assert not d.allowed and d.grant_id is None
    assert "ledger_write" in d.reason
