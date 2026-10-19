"""Pure OTP mechanics + the delivery seam (S7.1).

No I/O and no ambient randomness: the caller injects `rng` and `at`, so every
path is reproducible under test. Codes are stored only as salted sha256
digests -- the plaintext exists just long enough to hand to a notifier.

Email delivery uses the shared configured client. Unsupported delivery refuses;
phone requires an explicitly injected notifier with that capability.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from typing import Optional, Protocol

from app.ledger.consent import as_utc


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
    """Delivery seam. Production implementations must never retain raw codes."""

    def check_available(self, *, channel: str) -> None: ...
    def send(self, destination: str, code: str, *, channel: str) -> None: ...


class DeliveryUnavailable(Exception):
    def __init__(self, channel: str):
        self.detail = "email_unavailable" if channel == "email" else "phone_unavailable"
        super().__init__(self.detail)


class NullNotifier:
    """No delivery capability; refuse without creating or exposing a code."""

    def check_available(self, *, channel: str) -> None:
        raise DeliveryUnavailable(channel)

    def send(self, destination: str, code: str, *, channel: str) -> None:
        self.check_available(channel=channel)
