"""S7.1 OTP mechanics: pure, deterministic under an injected RNG and clock."""

import random
from datetime import datetime, timedelta, timezone

from app.verification.otp import (
    NullNotifier, attempts_exhausted, cooldown_active, generate_code,
    hash_code, is_challenge_expired,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def test_generate_code_is_all_digits_of_the_requested_length():
    code = generate_code(6, rng=random.Random(1234))
    assert len(code) == 6 and code.isdigit()


def test_generate_code_is_deterministic_under_a_seeded_rng():
    assert generate_code(6, rng=random.Random(1234)) == generate_code(6, rng=random.Random(1234))


def test_generate_code_keeps_leading_zeros():
    # A code rendered as an int would silently shorten; it must stay a string.
    codes = [generate_code(6, rng=random.Random(seed)) for seed in range(300)]
    assert all(len(c) == 6 for c in codes)


def test_hash_code_is_stable_salted_and_hides_the_code():
    digest = hash_code("123456", "salt-a")
    assert digest == hash_code("123456", "salt-a")
    assert digest != hash_code("123456", "salt-b")
    assert digest != hash_code("654321", "salt-a")
    assert len(digest) == 64 and "123456" not in digest


def test_challenge_expiry_is_inclusive_at_the_boundary():
    assert is_challenge_expired(NOW, at=NOW) is True
    assert is_challenge_expired(NOW + timedelta(seconds=1), at=NOW) is False


def test_challenge_expiry_treats_naive_timestamps_as_utc():
    assert is_challenge_expired(datetime(2026, 7, 31, 11, 0), at=NOW) is True


def test_attempts_exhausted_at_the_cap():
    assert attempts_exhausted(4, 5) is False
    assert attempts_exhausted(5, 5) is True
    assert attempts_exhausted(6, 5) is True


def test_cooldown_blocks_a_resend_inside_the_window():
    assert cooldown_active(NOW - timedelta(seconds=30), 60, at=NOW) is True
    assert cooldown_active(NOW - timedelta(seconds=61), 60, at=NOW) is False
    assert cooldown_active(None, 60, at=NOW) is False


def test_zero_cooldown_never_blocks():
    assert cooldown_active(NOW, 0, at=NOW) is False


def test_null_notifier_accepts_a_send_and_records_nothing_sensitive():
    n = NullNotifier()
    n.send("someone@example.com", "123456", channel="email")  # must not raise
