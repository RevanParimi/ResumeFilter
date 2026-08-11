"""S8.3 Phase A: the pure layer. No session, no clock of its own -- every
function takes what it needs, so a window is testable without waiting."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

from app.ratelimit.schema import (
    LimitScope, RateRule, bucket_key, retry_after, window_start,
)

NOW = datetime(2026, 8, 10, 14, 37, 12, tzinfo=timezone.utc)


def test_bucket_key_does_not_contain_the_identity():
    """The row would otherwise hold a raw email beside a raw IP for every login
    attempt on the platform -- a worse disclosure than the thing defended."""
    key = bucket_key(
        rule="login_request", scope=LimitScope.EMAIL,
        identity="priya@example.com", salt="s",
    )
    assert "priya" not in key
    assert "@" not in key
    assert len(key) == 64  # sha256 hex


def test_bucket_key_separates_rules_scopes_and_identities():
    common = dict(salt="s")
    a = bucket_key(rule="login_request", scope=LimitScope.EMAIL, identity="x", **common)
    b = bucket_key(rule="login_verify", scope=LimitScope.EMAIL, identity="x", **common)
    c = bucket_key(rule="login_request", scope=LimitScope.IP, identity="x", **common)
    d = bucket_key(rule="login_request", scope=LimitScope.EMAIL, identity="y", **common)
    assert len({a, b, c, d}) == 4


def test_bucket_key_is_salted():
    """Same salt as email_hash/phone_hash: an unsalted hash of an email is a
    rainbow-table lookup away from the email."""
    assert bucket_key(
        rule="r", scope=LimitScope.EMAIL, identity="x", salt="one"
    ) != bucket_key(rule="r", scope=LimitScope.EMAIL, identity="x", salt="two")


def test_window_start_floors_to_the_window():
    hour = 3600
    assert window_start(NOW, hour) == int(
        datetime(2026, 8, 10, 14, 0, 0, tzinfo=timezone.utc).timestamp()
    )


def test_two_times_in_one_window_share_a_start():
    hour = 3600
    assert window_start(NOW, hour) == window_start(NOW + timedelta(minutes=20), hour)


def test_the_next_window_has_a_different_start():
    hour = 3600
    assert window_start(NOW, hour) != window_start(NOW + timedelta(hours=1), hour)


def test_retry_after_is_the_seconds_left_in_the_window():
    hour = 3600
    ws = window_start(NOW, hour)
    # 14:37:12 -> 22m48s remain of the 14:00 window
    assert retry_after(NOW, ws, hour) == 22 * 60 + 48


def test_retry_after_is_never_zero_or_negative():
    """A Retry-After of 0 invites an immediate retry that will also be refused,
    which reads to a client author like the header is broken."""
    hour = 3600
    ws = window_start(NOW, hour)
    assert retry_after(NOW.replace(minute=59, second=59), ws, hour) >= 1


def test_a_rule_is_frozen():
    rule = RateRule(name="r", limit=5, window_seconds=60, scope=LimitScope.IP)
    assert dataclasses.is_dataclass(rule)
    try:
        rule.limit = 9  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("RateRule must be frozen")
