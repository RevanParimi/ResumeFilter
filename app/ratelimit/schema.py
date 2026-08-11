"""Rate limiting: the pure types (S8.3 Phase A).

No I/O, no session, no clock beyond what a caller hands in -- the same split as
app/screening/schema.py, and the reason is the same: a window is only testable
without waiting if ``now`` is an argument.

The identity is HASHED into the bucket key and never stored. A counter table
keyed on raw emails and raw IPs would hold, for every login attempt on the
platform, exactly the pair of identifiers an attacker wants -- a worse
disclosure than the brute-forcing it defends against. The salt is
``contact_hash_salt``, the same one behind email_hash/phone_hash: precedent,
not invention.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional


class LimitScope(StrEnum):
    """WHAT a rule counts per.

    A rule names one; a caller may evaluate several (see ``RateLimiter.check``)
    -- that is what "dual-scoped" means.
    """

    EMAIL = "email"
    IP = "ip"
    ORG = "org"
    CANDIDATE = "candidate"


@dataclass(frozen=True)
class RateRule:
    """``limit`` events per ``window_seconds``, counted per ``scope``."""

    name: str
    limit: int
    window_seconds: int
    scope: LimitScope


@dataclass(frozen=True)
class LimitDecision:
    """``scope`` names the scope that REFUSED, and is None when allowed."""

    allowed: bool
    rule: str
    scope: Optional[LimitScope] = None
    retry_after_seconds: int = 0


def bucket_key(*, rule: str, scope: LimitScope, identity: str, salt: str) -> str:
    """One counter's identity, as a salted sha256 hex digest."""
    material = f"{salt}|{rule}|{scope.value}|{identity}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def window_start(now: datetime, window_seconds: int) -> int:
    """The epoch second at which the current fixed window opened.

    An INTEGER, not a datetime, and that is deliberate: this value is only ever
    compared for exact equality (the WHERE of the conditional UPDATE), and
    epoch seconds carry no timezone semantics for two dialects to disagree
    about. ``expires_at`` on the row stays a real timestamp, because S8.3 Phase
    B's retention sweep reads it like every other retention column.

    Fixed windows admit a burst of up to 2x the limit across a window edge. For
    a 20/hour OTP bound that is irrelevant, and OPERATING.md says so rather
    than leaving a reader to discover it.
    """
    return int(now.timestamp()) // window_seconds * window_seconds


def retry_after(now: datetime, window_start_epoch: int, window_seconds: int) -> int:
    """Whole seconds until this window closes, never less than 1.

    Zero would invite an immediate retry that is also refused, which reads to a
    client author like the header is broken.
    """
    remaining = window_start_epoch + window_seconds - int(now.timestamp())
    return max(1, remaining)
