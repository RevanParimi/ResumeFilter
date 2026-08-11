"""S8.3 Phase A: the rate-limit knobs. Defaults are the SAFE ones -- enabled,
and trusting no proxy -- because the wrong default here fails OPEN."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def test_rate_limiting_is_on_by_default():
    assert _settings().rate_limit_enabled is True


def test_no_proxy_is_trusted_by_default():
    """X-Forwarded-For is attacker-controlled. Trusting it by default would
    hand every caller a free reset of their own per-IP scope."""
    assert _settings().rate_limit_trusted_proxy_hops == 0


def test_default_limits_are_the_spec_values():
    s = _settings()
    assert s.rate_limit_login_per_hour_per_email == 20
    assert s.rate_limit_login_per_hour_per_ip == 100
    assert s.rate_limit_verify_per_hour_per_email == 30
    assert s.rate_limit_verify_per_hour_per_ip == 200
    assert s.rate_limit_process_per_hour_per_org == 400
    assert s.rate_limit_asr_per_hour_per_candidate == 60


@pytest.mark.parametrize(
    "field",
    [
        "rate_limit_login_per_hour_per_email",
        "rate_limit_login_per_hour_per_ip",
        "rate_limit_verify_per_hour_per_email",
        "rate_limit_verify_per_hour_per_ip",
        "rate_limit_process_per_hour_per_org",
        "rate_limit_asr_per_hour_per_candidate",
    ],
)
def test_a_limit_of_zero_is_refused_at_config_time(field):
    """A zero limit denies every caller including the operator. If somebody
    wants the limiter off, rate_limit_enabled is the honest switch."""
    with pytest.raises(ValidationError):
        _settings(**{field: 0})


def test_negative_proxy_hops_are_refused():
    with pytest.raises(ValidationError):
        _settings(rate_limit_trusted_proxy_hops=-1)
