from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.portal.retention import RETENTION_KNOBS, build_retention_policy, retained_until


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def test_retained_until_adds_ttl():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert retained_until(base, 10) == base + timedelta(days=10)


def test_retained_until_coerces_naive_to_utc():
    naive = datetime(2026, 1, 1)  # SQLite-style naive
    out = retained_until(naive, 5)
    assert out.tzinfo is not None
    assert out == datetime(2026, 1, 6, tzinfo=timezone.utc)


def test_build_policy_covers_every_class_ttl_always_shown():
    policy = build_retention_policy({}, _settings())
    classes = {w.data_class for w in policy.windows}
    assert classes == set(RETENTION_KNOBS)          # every class present as posture
    assert all(w.ttl_days >= 1 for w in policy.windows)
    assert all(w.retained_until is None for w in policy.windows)  # no items


def test_sweep_active_is_DERIVED_from_the_config_not_a_literal():
    """THE POINT OF PHASE B. Until now the portal told every data principal
    that no mechanical purge runs. A second hardcoded literal is a promise that
    goes stale the day an operator flips the knob -- and it goes stale in the
    direction of telling a person nothing is deleted while the cron deletes."""
    on = build_retention_policy({}, _settings())
    off = build_retention_policy(
        {}, Settings(_env_file=None, openrouter_api_key="",
                     retention_sweep_enabled=False)
    )
    assert on.sweep_active is True          # config.yaml ships it enabled
    assert off.sweep_active is False


def test_build_policy_computes_retained_until_where_oldest_known():
    oldest = datetime(2026, 1, 1, tzinfo=timezone.utc)
    policy = build_retention_policy({"resumes": oldest}, _settings())
    resumes = next(w for w in policy.windows if w.data_class == "resumes")
    assert resumes.oldest_item_at == oldest
    assert resumes.retained_until == oldest + timedelta(days=resumes.ttl_days)
    # a class with no oldest stays policy-only
    audit = next(w for w in policy.windows if w.data_class == "audit_log")
    assert audit.retained_until is None
