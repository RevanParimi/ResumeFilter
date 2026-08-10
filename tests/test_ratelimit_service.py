"""S8.3 Phase A: dual scoping. ALL scopes are counted; ANY denial denies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.ratelimit.models import RateLimitCounterRow
from app.ratelimit.schema import LimitScope, RateRule
from app.ratelimit.service import RateLimited, RateLimiter, build_rate_limiter
from tests.conftest import make_candidate_store

NOW = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def session_factory():
    return make_candidate_store()._session_factory


@pytest.fixture
def rl_settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


@pytest.fixture
def limiter(rl_settings, session_factory) -> RateLimiter:
    return build_rate_limiter(rl_settings, session_factory)


def _rules(email_limit: int, ip_limit: int) -> list[RateRule]:
    return [
        RateRule("r", email_limit, 3600, LimitScope.EMAIL),
        RateRule("r", ip_limit, 3600, LimitScope.IP),
    ]


def test_the_email_scope_can_deny_on_its_own(limiter):
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    rules = _rules(email_limit=2, ip_limit=100)
    for _ in range(2):
        assert limiter.check(rules, ids, now=NOW).allowed
    denied = limiter.check(rules, ids, now=NOW)
    assert denied.allowed is False
    assert denied.scope == LimitScope.EMAIL


def test_the_ip_scope_can_deny_on_its_own(limiter):
    """Spraying ONE guess across many addresses never trips a per-email
    counter. This is the half a per-email limit cannot see."""
    rules = _rules(email_limit=100, ip_limit=2)
    for i in range(2):
        assert limiter.check(
            rules, {LimitScope.EMAIL: f"{i}@x", LimitScope.IP: "1.1.1.1"}, now=NOW
        ).allowed
    denied = limiter.check(
        rules, {LimitScope.EMAIL: "third@x", LimitScope.IP: "1.1.1.1"}, now=NOW
    )
    assert denied.allowed is False
    assert denied.scope == LimitScope.IP


def test_one_address_from_many_ips_still_trips_the_email_scope(limiter):
    """The botnet half. A per-IP limit alone would let this through."""
    rules = _rules(email_limit=2, ip_limit=100)
    for i in range(2):
        assert limiter.check(
            rules, {LimitScope.EMAIL: "a@x", LimitScope.IP: f"10.0.0.{i}"}, now=NOW
        ).allowed
    assert limiter.check(
        rules, {LimitScope.EMAIL: "a@x", LimitScope.IP: "10.0.0.9"}, now=NOW
    ).allowed is False


def test_every_scope_is_counted_even_when_an_earlier_one_denies(
    limiter, session_factory
):
    """A limiter that stops counting at the first denial under-reports the
    attacker who tripped it -- and the second scope's window then looks clean
    to whoever reads the metrics."""
    rules = _rules(email_limit=1, ip_limit=100)
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    limiter.check(rules, ids, now=NOW)   # allowed
    limiter.check(rules, ids, now=NOW)   # denied by email
    with session_factory() as session:
        counts = sorted(r.count for r in session.query(RateLimitCounterRow).all())
    assert counts == [1, 2], "the IP scope must have counted both attempts"


def test_a_missing_identity_skips_that_scope_and_keeps_the_others(limiter):
    """No client IP is determinable under some ASGI transports. A partial bound
    is correct; refusing a legitimate caller for a reason they cannot act on is
    not, and neither is skipping the whole rule."""
    rules = _rules(email_limit=1, ip_limit=1)
    assert limiter.check(
        rules, {LimitScope.EMAIL: "a@x", LimitScope.IP: None}, now=NOW
    ).allowed
    denied = limiter.check(
        rules, {LimitScope.EMAIL: "a@x", LimitScope.IP: None}, now=NOW
    )
    assert denied.allowed is False
    assert denied.scope == LimitScope.EMAIL


def test_a_later_window_is_a_clean_slate(limiter):
    rules = _rules(email_limit=1, ip_limit=100)
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    assert limiter.check(rules, ids, now=NOW).allowed
    assert limiter.check(rules, ids, now=NOW).allowed is False
    assert limiter.check(rules, ids, now=NOW + timedelta(hours=1)).allowed


def test_the_decision_carries_a_usable_retry_after(limiter):
    rules = _rules(email_limit=1, ip_limit=100)
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    limiter.check(rules, ids, now=NOW)
    denied = limiter.check(rules, ids, now=NOW + timedelta(minutes=20))
    assert denied.retry_after_seconds == 40 * 60


def test_disabled_means_allowed_without_touching_the_table(
    rl_settings, session_factory
):
    off = rl_settings.model_copy(update={"rate_limit_enabled": False})
    limiter = build_rate_limiter(off, session_factory)
    rules = _rules(email_limit=1, ip_limit=1)
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    for _ in range(5):
        assert limiter.check(rules, ids, now=NOW).allowed
    with session_factory() as session:
        assert session.query(RateLimitCounterRow).count() == 0


def test_enforce_raises_with_the_scope_and_the_wait(limiter):
    rules = _rules(email_limit=1, ip_limit=100)
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    limiter.enforce(rules, ids, now=NOW)
    with pytest.raises(RateLimited) as exc:
        limiter.enforce(rules, ids, now=NOW)
    assert exc.value.scope == LimitScope.EMAIL
    assert exc.value.retry_after_seconds > 0


def test_rules_for_reads_the_configured_limits(rl_settings, session_factory):
    tuned = rl_settings.model_copy(update={
        "rate_limit_login_per_hour_per_email": 7,
        "rate_limit_login_per_hour_per_ip": 9,
    })
    limiter = build_rate_limiter(tuned, session_factory)
    by_scope = {r.scope: r for r in limiter.rules_for("login_request")}
    assert by_scope[LimitScope.EMAIL].limit == 7
    assert by_scope[LimitScope.IP].limit == 9
    assert by_scope[LimitScope.EMAIL].window_seconds == 3600


def test_every_named_rule_resolves(limiter):
    """A call site naming a rule that does not exist must fail loudly here, not
    silently limit nothing."""
    for name in ("login_request", "login_verify", "screening_process",
                 "asr_transcribe"):
        assert limiter.rules_for(name), name
    with pytest.raises(KeyError):
        limiter.rules_for("no_such_rule")
