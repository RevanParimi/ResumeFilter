"""Login-OTP POLICY (S8.2), layered over app/verification/otp.py's MECHANICS.

Login reuses the FUNCTIONS, not the TABLE: `verification_challenges` is
candidate-scoped identity verification and stays that way, while a login
challenge belongs to a principal that may not exist yet (at signup time there
is nothing to point a foreign key at).

Cooldown and attempt caps are scoped to email_hash + purpose + PLANE, applying
S7.1's own review finding verbatim -- a limit scoped to a row that the flow
re-mints limits nothing. `plane` is added on top of PI-8 section 4.4 because one
address can legitimately be both a candidate and an org user, and collapsing
those would let activity on one plane lock the other out.
"""

from __future__ import annotations

import hmac
import random
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional

from app.auth.schema import AuthPlane, LoginPurpose
from app.verification import otp as otp_logic


@dataclass(frozen=True)
class ChallengeScope:
    """The unit a cooldown and an attempt cap apply to. Frozen so it can be a
    dict key and can never drift between the send path and the verify path."""

    email_hash: str
    purpose: LoginPurpose
    plane: AuthPlane


class VerifyOutcome(StrEnum):
    OK = "ok"
    WRONG_CODE = "wrong_code"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"
    NOT_FOUND = "not_found"


def mint_code(length: int, *, salt: str, rng: random.Random) -> tuple[str, str]:
    """Return (plaintext, digest).

    The plaintext exists only long enough to hand to the email client; only the
    digest is ever written. `rng` is injected so every test path is reproducible
    without patching the module.
    """
    code = otp_logic.generate_code(length, rng=rng)
    return code, otp_logic.hash_code(code, salt)


def hash_supplied(code: str, *, salt: str) -> str:
    """Digest a code the user typed, so the caller compares digests and never
    handles a stored plaintext (there isn't one) or an unsalted hash."""
    return otp_logic.hash_code(code or "", salt)


def may_send(
    *, last_sent_at: Optional[datetime], cooldown_seconds: int, at: datetime
) -> bool:
    """Whether a (re)send is outside the cooldown window."""
    return not otp_logic.cooldown_active(last_sent_at, cooldown_seconds, at=at)


def evaluate_verification(
    *,
    stored_hash: Optional[str],
    supplied_hash: str,
    expires_at: datetime,
    attempts: int,
    max_attempts: int,
    at: datetime,
) -> VerifyOutcome:
    """Decide a verification attempt.

    Exhaustion and expiry are checked BEFORE the code. Both orderings still
    refuse a correct code once the cap is hit -- the guarantee does not hinge on
    this -- but checking state first means an exhausted or expired challenge
    reports what is actually wrong instead of reporting WRONG_CODE and bumping
    the counter forever. A caller that keeps incrementing a dead challenge is
    doing unbounded writes on an attacker's schedule.
    """
    if stored_hash is None:
        return VerifyOutcome.NOT_FOUND
    if otp_logic.attempts_exhausted(attempts, max_attempts):
        return VerifyOutcome.EXHAUSTED
    if otp_logic.is_challenge_expired(expires_at, at=at):
        return VerifyOutcome.EXPIRED
    if not hmac.compare_digest(stored_hash, supplied_hash):
        return VerifyOutcome.WRONG_CODE
    return VerifyOutcome.OK
