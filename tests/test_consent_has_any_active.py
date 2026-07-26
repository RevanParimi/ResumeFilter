from datetime import datetime, timezone

from app.ledger.consent import has_any_active
from app.ledger.schema import ConsentGrant, ConsentPurpose


def _grant(**kw):
    base = dict(
        id="g1", candidate_id="c1", org_id=None, purpose=ConsentPurpose.LEDGER_READ,
        granted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc), revoked_at=None,
    )
    base.update(kw)
    return ConsentGrant(**base)


AT = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_active_grant_allows():
    d = has_any_active([_grant()], purpose=ConsentPurpose.LEDGER_READ, at=AT)
    assert d.allowed and d.grant_id == "g1"


def test_org_specific_grant_still_counts():
    d = has_any_active([_grant(org_id="orgX")], purpose=ConsentPurpose.LEDGER_READ, at=AT)
    assert d.allowed  # org-agnostic: any org's grant is enough for platform materialization


def test_expired_grant_denied():
    d = has_any_active([_grant()], purpose=ConsentPurpose.LEDGER_READ,
                       at=datetime(2028, 1, 1, tzinfo=timezone.utc))
    assert not d.allowed and d.grant_id is None


def test_revoked_before_at_denied():
    g = _grant(revoked_at=datetime(2026, 3, 1, tzinfo=timezone.utc))
    assert not has_any_active([g], purpose=ConsentPurpose.LEDGER_READ, at=AT).allowed


def test_point_in_time_before_revocation_allows():
    g = _grant(revoked_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    at = datetime(2026, 3, 1, tzinfo=timezone.utc)  # asked before the revocation instant
    assert has_any_active([g], purpose=ConsentPurpose.LEDGER_READ, at=at).allowed


def test_wrong_purpose_excluded():
    g = _grant(purpose=ConsentPurpose.LEDGER_WRITE)
    assert not has_any_active([g], purpose=ConsentPurpose.LEDGER_READ, at=AT).allowed
