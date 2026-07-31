"""Pure assurance folding (S7.1). No I/O, no clock -- the caller passes `at`,
exactly like app/ledger/consent.py.

Expiry is computed at READ time rather than written by a job. There is no
scheduler in this system, so a stored `expired` status would simply be a lie
that nobody corrects; deriving it keeps the answer true at every moment.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from app.ledger.consent import as_utc
from app.verification.schema import (
    METHOD_LEVEL, AssuranceLevel, IdentityAssurance, Verification,
    VerificationMethod, VerificationStatus,
)


def is_expired(v: Verification, *, at: datetime) -> bool:
    """True once `expires_at` has passed. A null expiry never lapses."""
    if v.expires_at is None:
        return False
    return as_utc(v.expires_at) <= as_utc(at)


def effective_status(v: Verification, *, at: datetime) -> VerificationStatus:
    """The status as of `at` -- a stored `verified` past its expiry reads
    EXPIRED, so callers never act on a lapsed outcome."""
    if v.status is VerificationStatus.VERIFIED and is_expired(v, at=at):
        return VerificationStatus.EXPIRED
    return v.status


def compute_assurance(
    candidate_id: str, verifications: Sequence[Verification], *, at: datetime
) -> IdentityAssurance:
    """Fold a candidate's verifications into one advisory assurance.

    Contributing = status VERIFIED and not lapsed. Lapsed methods are reported
    separately (rather than silently dropped) so the portal can prompt a
    re-verify instead of showing an unexplained downgrade.
    """
    level = AssuranceLevel.NONE
    methods: list[VerificationMethod] = []
    expired_methods: list[VerificationMethod] = []
    verified_at: Optional[datetime] = None

    for v in verifications:
        status = effective_status(v, at=at)
        if status is VerificationStatus.VERIFIED:
            if v.method not in methods:
                methods.append(v.method)
            level = max(level, METHOD_LEVEL[v.method])
            if v.completed_at is not None:
                moment = as_utc(v.completed_at)
                if verified_at is None or moment > verified_at:
                    verified_at = moment
        elif status is VerificationStatus.EXPIRED:
            if v.method not in expired_methods:
                expired_methods.append(v.method)

    # A method that is currently held is not "expired" even if an older
    # attempt of the same method lapsed.
    expired_methods = [m for m in expired_methods if m not in methods]

    return IdentityAssurance(
        candidate_id=candidate_id,
        level=level,
        methods=methods,
        verified_at=verified_at,
        expired_methods=expired_methods,
    )
