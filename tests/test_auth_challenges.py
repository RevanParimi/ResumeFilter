"""Login-OTP policy (S8.2), layered over S7.1's pure mechanics."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.auth.challenges import (
    ChallengeScope, VerifyOutcome, evaluate_verification, may_send, mint_code,
)
from app.auth.schema import AuthPlane, LoginPurpose

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _scope(**over) -> ChallengeScope:
    kw = dict(email_hash="h1", purpose=LoginPurpose.LOGIN, plane=AuthPlane.CANDIDATE)
    kw.update(over)
    return ChallengeScope(**kw)


def test_scope_is_hashable_and_includes_the_plane():
    """One address can legitimately be both a candidate and an org user;
    collapsing the planes would let activity on one lock the other out."""
    a, b = _scope(), _scope(plane=AuthPlane.ORG)
    assert a != b
    assert len({a, b}) == 2


def test_scope_separates_signup_from_login():
    assert _scope() != _scope(purpose=LoginPurpose.SIGNUP)


def test_mint_code_is_deterministic_under_an_injected_rng():
    code, digest = mint_code(6, salt="s", rng=random.Random(7))
    again, again_digest = mint_code(6, salt="s", rng=random.Random(7))
    assert code == again and digest == again_digest
    assert len(code) == 6 and code.isdigit()
    assert len(digest) == 64 and digest != code


def test_mint_code_salts_the_digest():
    """Two installs with different salts must not share a rainbow table."""
    code_a, digest_a = mint_code(6, salt="salt-a", rng=random.Random(7))
    code_b, digest_b = mint_code(6, salt="salt-b", rng=random.Random(7))
    assert code_a == code_b
    assert digest_a != digest_b


def test_may_send_respects_cooldown():
    assert may_send(last_sent_at=None, cooldown_seconds=60, at=NOW) is True
    assert may_send(
        last_sent_at=NOW - timedelta(seconds=30), cooldown_seconds=60, at=NOW
    ) is False
    assert may_send(
        last_sent_at=NOW - timedelta(seconds=61), cooldown_seconds=60, at=NOW
    ) is True


def test_cooldown_can_be_disabled():
    assert may_send(last_sent_at=NOW, cooldown_seconds=0, at=NOW) is True


def _verify(**over) -> VerifyOutcome:
    kw = dict(
        stored_hash="d", supplied_hash="d",
        expires_at=NOW + timedelta(minutes=5),
        attempts=0, max_attempts=5, at=NOW,
    )
    kw.update(over)
    return evaluate_verification(**kw)


def test_no_challenge_is_not_found():
    assert _verify(stored_hash=None) == VerifyOutcome.NOT_FOUND


def test_correct_code_passes():
    assert _verify() == VerifyOutcome.OK


def test_wrong_code_fails():
    assert _verify(supplied_hash="x") == VerifyOutcome.WRONG_CODE


def test_expired_beats_correct():
    """An expired challenge must not be redeemable even with the right code."""
    assert _verify(expires_at=NOW) == VerifyOutcome.EXPIRED


def test_exhausted_beats_correct():
    """Ordering is load-bearing: checking the code first would let an attacker
    keep guessing past the cap so long as the final guess happened to be right
    -- which is exactly the guess a brute-forcer is making."""
    assert _verify(attempts=5, max_attempts=5) == VerifyOutcome.EXHAUSTED


def test_exhausted_beats_expired():
    assert _verify(
        attempts=5, max_attempts=5, expires_at=NOW
    ) == VerifyOutcome.EXHAUSTED


def test_naive_expiry_is_coerced():
    assert _verify(expires_at=datetime(2026, 8, 2, 12, 5)) == VerifyOutcome.OK


def test_a_dead_challenge_reports_why_instead_of_wrong_code():
    """What the state-before-code ordering actually buys.

    Both orderings refuse a correct code once the cap is hit, so the guarantee
    does not hinge on this. Checking state first means an exhausted or expired
    challenge reports what is really wrong -- and, crucially, the caller stops
    bumping the attempt counter on a dead row, which would otherwise be
    unbounded writes on an attacker's schedule.
    """
    assert _verify(
        supplied_hash="wrong", attempts=5, max_attempts=5
    ) == VerifyOutcome.EXHAUSTED
    assert _verify(supplied_hash="wrong", expires_at=NOW) == VerifyOutcome.EXPIRED


def test_mint_code_for_defaults_to_a_cryptographic_rng(settings):
    """`random.Random` is a Mersenne Twister: its internal state is
    recoverable from enough observed output, so codes an attacker has already
    seen would predict the next one. No unit test can distinguish the two
    statistically, so the assertion is on the source itself.
    """
    from app.auth import challenges as challenge_logic

    cfg = settings.model_copy(update={"login_otp_static_code": None})
    seen: list[random.Random] = []
    real = challenge_logic.otp_logic.generate_code

    def _record(length, *, rng):
        seen.append(rng)
        return real(length, rng=rng)

    original = challenge_logic.otp_logic.generate_code
    challenge_logic.otp_logic.generate_code = _record
    try:
        challenge_logic.mint_code_for(cfg)
    finally:
        challenge_logic.otp_logic.generate_code = original

    assert seen and isinstance(seen[0], random.SystemRandom)


def test_no_production_path_mints_a_login_code_from_a_seeded_rng():
    """The companion to the single-mint-door scan.

    One door minting from `SystemRandom` is worth nothing if a caller upstream
    supplies its own `random.Random()` -- the same "rule at one entry point and
    not the other" shape this repo has hit in every PI.
    """
    import pathlib
    import re

    src_root = pathlib.Path(__file__).resolve().parent.parent / "src" / "app"
    offenders = []
    for path in (src_root / "auth").rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\brandom\.Random\s*\(", line):
                offenders.append(f"{path.name}:{i}: {line.strip()}")

    assert offenders == [], (
        "a seeded-by-default RNG on the login OTP path: " + "; ".join(offenders)
    )
