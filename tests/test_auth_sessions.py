"""Pure session mechanics (S8.2). Clock injected on every call -- no wall clock,
so none of these can become the pinned-NOW time bomb S8.1 defused."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.auth.schema import SessionStatus
from app.auth.sessions import (
    effective_status, generate_token, hash_token, should_write_last_seen,
)

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _status(**over) -> SessionStatus:
    kw = dict(
        expires_at=NOW + timedelta(hours=1),
        last_seen_at=NOW - timedelta(minutes=5),
        revoked_at=None,
        idle_timeout_minutes=120,
        at=NOW,
    )
    kw.update(over)
    return effective_status(**kw)


def test_a_fresh_session_is_active():
    assert _status() == SessionStatus.ACTIVE


def test_absolute_expiry():
    assert _status(expires_at=NOW - timedelta(seconds=1)) == SessionStatus.EXPIRED


def test_expiry_is_inclusive_at_the_boundary():
    """Dead the instant it expires -- the is_challenge_expired convention."""
    assert _status(expires_at=NOW) == SessionStatus.EXPIRED


def test_idle_timeout():
    assert _status(last_seen_at=NOW - timedelta(minutes=121)) == SessionStatus.IDLE_EXPIRED


def test_idle_boundary_is_inclusive():
    assert _status(last_seen_at=NOW - timedelta(minutes=120)) == SessionStatus.IDLE_EXPIRED
    assert _status(last_seen_at=NOW - timedelta(minutes=119)) == SessionStatus.ACTIVE


def test_idle_timeout_can_be_disabled():
    assert _status(
        last_seen_at=NOW - timedelta(days=30), idle_timeout_minutes=0
    ) == SessionStatus.ACTIVE


def test_revocation_beats_everything():
    """Revoked and expired answer different questions -- 'was it taken away?'
    versus 'did it lapse?' -- so revocation is checked first and unconditionally."""
    assert _status(revoked_at=NOW - timedelta(days=1)) == SessionStatus.REVOKED
    assert _status(
        revoked_at=NOW - timedelta(days=1), expires_at=NOW - timedelta(days=1)
    ) == SessionStatus.REVOKED
    assert _status(
        revoked_at=NOW - timedelta(days=1), last_seen_at=NOW - timedelta(days=1)
    ) == SessionStatus.REVOKED


def test_naive_datetimes_are_coerced_to_utc():
    """SQLite refetch drops tzinfo. An uncoerced compare raises, or -- worse --
    silently mis-windows a row written in IST (the S3.1 as_utc lesson)."""
    assert _status(expires_at=datetime(2026, 8, 2, 13, 0)) == SessionStatus.ACTIVE
    assert _status(expires_at=datetime(2026, 8, 2, 11, 0)) == SessionStatus.EXPIRED


def test_tokens_are_distinct_and_long():
    a, b = generate_token(32), generate_token(32)
    assert a != b
    assert len(a) >= 32


def test_hash_token_is_stable_sha256_hex():
    assert hash_token("abc") == hash_token("abc")
    assert len(hash_token("abc")) == 64
    assert hash_token("abc") != hash_token("abd")


def test_hash_token_tolerates_empty():
    """An absent cookie must hash to something that simply matches no row,
    rather than raising inside the resolver on every anonymous request."""
    assert len(hash_token("")) == 64


def test_last_seen_write_is_throttled():
    assert should_write_last_seen(NOW - timedelta(seconds=5), 60, at=NOW) is False
    assert should_write_last_seen(NOW - timedelta(seconds=60), 60, at=NOW) is True
    assert should_write_last_seen(NOW - timedelta(seconds=61), 60, at=NOW) is True


def test_last_seen_throttle_can_be_disabled():
    assert should_write_last_seen(NOW, 0, at=NOW) is True
