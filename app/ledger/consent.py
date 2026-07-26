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


def _selection_key(grant: ConsentGrant) -> tuple[bool, float, str]:
    # Sort ascending: org-specific (False) before wildcard (True); most recent
    # grant first (negated epoch); lowest id as the final deterministic tiebreak.
    return (grant.org_id is None, -as_utc(grant.granted_at).timestamp(), grant.id)


def check_consent(
    grants: Sequence[ConsentGrant], *, org_id: str, purpose: ConsentPurpose, at: datetime
) -> ConsentDecision:
    active = [
        g for g in grants if is_grant_active(g, org_id=org_id, purpose=purpose, at=at)
    ]
    if not active:
        return ConsentDecision(
            allowed=False,
            reason=f"no active consent for purpose '{purpose.value}'",
        )
    best = min(active, key=_selection_key)
    return ConsentDecision(
        allowed=True,
        reason=f"active grant {best.id} covers purpose '{purpose.value}'",
        grant_id=best.id,
    )


def has_any_active(
    grants: Sequence[ConsentGrant], *, purpose: ConsentPurpose, at: datetime
) -> ConsentDecision:
    """Org-agnostic active-grant check for platform-internal materialization.

    Unlike ``check_consent`` this ignores grant.org_id: the candidate opting any
    reader in (org-specific or wildcard) is a sufficient basis for the platform's
    own feature materialization. Same active-window rules and deterministic
    ``_selection_key`` tie-break."""
    moment = as_utc(at)
    active = [
        g for g in grants
        if g.purpose == purpose
        and as_utc(g.granted_at) <= moment
        and as_utc(g.expires_at) > moment
        and (g.revoked_at is None or as_utc(g.revoked_at) > moment)
    ]
    if not active:
        return ConsentDecision(
            allowed=False,
            reason=f"no active consent for purpose '{purpose.value}'",
        )
    best = min(active, key=_selection_key)
    return ConsentDecision(
        allowed=True,
        reason=f"active grant {best.id} covers purpose '{purpose.value}' (any org)",
        grant_id=best.id,
    )
