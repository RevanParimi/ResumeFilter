"""Pure OTP mechanics + the delivery seam (S7.1).

No I/O and no ambient randomness: the caller injects `rng` and `at`, so every
path is reproducible under test. Codes are stored only as salted sha256
digests -- the plaintext exists just long enough to hand to a notifier.

This repo has no email/SMS provider and S7.1 does not add one, so the shipped
notifier discards. Real delivery is a PI-8 concern.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from typing import Optional, Protocol

import structlog

from app.ledger.consent import as_utc

log = structlog.get_logger(__name__)


def generate_code(length: int, *, rng: random.Random) -> str:
    """A zero-padded numeric code. Kept a string end-to-end: an int would drop
    leading zeros and quietly shorten one code in ten."""
    upper = 10 ** length
    return str(rng.randrange(upper)).zfill(length)


def hash_code(code: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()


def is_challenge_expired(expires_at: datetime, *, at: datetime) -> bool:
    """Inclusive at the boundary: a challenge is dead the instant it expires."""
    return as_utc(expires_at) <= as_utc(at)


def attempts_exhausted(attempts: int, max_attempts: int) -> bool:
    return attempts >= max_attempts


def cooldown_active(
    last_sent_at: Optional[datetime], cooldown_seconds: int, *, at: datetime
) -> bool:
    """True when a resend would land inside the cooldown window."""
    if last_sent_at is None or cooldown_seconds <= 0:
        return False
    return as_utc(at) < as_utc(last_sent_at) + timedelta(seconds=cooldown_seconds)


class Notifier(Protocol):
    """Delivery seam. Implementations must never persist the code."""

    def send(self, destination: str, code: str, *, channel: str) -> None: ...


class NullNotifier:
    """Ships nothing. Logs the delivery attempt WITHOUT the code or the raw
    destination -- an OTP in the log file is an OTP leak."""

    def send(self, destination: str, code: str, *, channel: str) -> None:
        log.info("verification.otp.dispatch", channel=channel)
