"""Pure session mechanics (S8.2). No I/O, no ambient clock, no ambient RNG.

Expiry -- absolute AND idle -- is computed at READ time and never written by a
job. That is the S7.1 `effective_status` precedent and it holds for the same
reason: no scheduler exists in this repo, so a stored `expired` would be a lie
that nothing ever corrects.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from app.auth.schema import SessionStatus
from app.ledger.consent import as_utc


def generate_token(nbytes: int) -> str:
    """A URL-safe opaque token, returned to the caller ONCE.

    Only its hash is stored, mirroring CandidateStore.issue_access_key. Opaque
    and server-side rather than a JWT, because a JWT stays valid after a
    candidate revokes consent or erases their account (PI-8 decision 0.2).
    """
    return secrets.token_urlsafe(nbytes)


def hash_token(raw: str) -> str:
    """Tolerates empty: an absent cookie must hash to something that matches no
    row, rather than raising inside the resolver on every anonymous request."""
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def effective_status(
    *,
    expires_at: datetime,
    last_seen_at: datetime,
    revoked_at: Optional[datetime],
    idle_timeout_minutes: int,
    at: datetime,
) -> SessionStatus:
    """Revoked beats expired beats idle beats active.

    Revocation is checked FIRST and unconditionally: a revoked session must read
    as revoked even once it would also have expired, because the two answer
    different questions -- "was it taken away?" versus "did it lapse?" -- and
    only the first one is a security event worth seeing in an audit log.
    """
    now = as_utc(at)
    if revoked_at is not None:
        return SessionStatus.REVOKED
    if as_utc(expires_at) <= now:      # inclusive: dead the instant it expires
        return SessionStatus.EXPIRED
    if idle_timeout_minutes > 0:
        idle_deadline = as_utc(last_seen_at) + timedelta(minutes=idle_timeout_minutes)
        if idle_deadline <= now:
            return SessionStatus.IDLE_EXPIRED
    return SessionStatus.ACTIVE


def should_write_last_seen(
    last_seen_at: datetime, throttle_seconds: int, *, at: datetime
) -> bool:
    """Whether the idle-timeout clock is stale enough to be worth a write.

    The idle timeout needs `last_seen_at`, but writing it on every request turns
    each authenticated GET into a row lock plus a WAL entry on the hottest path
    in the system. The staleness this admits is bounded by the knob and is two
    orders of magnitude below the idle window, so it cannot change a timeout
    decision -- it only changes how often the row is touched.
    """
    if throttle_seconds <= 0:
        return True
    return as_utc(at) >= as_utc(last_seen_at) + timedelta(seconds=throttle_seconds)
