"""Pure consent decision logic (S3.1). No I/O, no clock — caller passes ``at``.

SQLite returns naive datetimes even from ``DateTime(timezone=True)`` columns,
so every comparison coerces to aware UTC first (naive ⇒ assume UTC, matching
how the store writes rows). A grant is active at time ``at`` iff: purpose
matches, the asking org is in scope (grant.org_id is None or equals it),
``granted_at <= at < expires_at``, and it was not revoked at or before
``at`` — so historical (point-in-time) checks still see pre-revocation truth.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from app.ledger.schema import ConsentDecision, ConsentGrant, ConsentPurpose


def as_utc(dt: datetime) -> datetime:
    """Aware-UTC view of any datetime; naive values are assumed UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_grant_active(
    grant: ConsentGrant, *, org_id: str, purpose: ConsentPurpose, at: datetime
) -> bool:
    if grant.purpose != purpose:
        return False
    if grant.org_id is not None and grant.org_id != org_id:
        return False
    moment = as_utc(at)
    if as_utc(grant.granted_at) > moment:
        return False
    if as_utc(grant.expires_at) <= moment:
        return False
    if grant.revoked_at is not None and as_utc(grant.revoked_at) <= moment:
        return False
    return True


def check_consent(
    grants: Sequence[ConsentGrant], *, org_id: str, purpose: ConsentPurpose, at: datetime
) -> ConsentDecision:
    for grant in grants:
        if is_grant_active(grant, org_id=org_id, purpose=purpose, at=at):
            return ConsentDecision(
                allowed=True,
                reason=f"active grant {grant.id} covers purpose '{purpose.value}'",
                grant_id=grant.id,
            )
    return ConsentDecision(
        allowed=False,
        reason=f"no active consent for purpose '{purpose.value}'",
    )
