"""Launch-time refusals (S8.1). A misconfigured admin plane must stop the
process, not quietly serve an open one."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.core.boot import LaunchConfigError, verify_launch_config


def test_empty_admin_key_refuses_launch(settings):
    locked = settings.model_copy(update={"api_auth_key": SecretStr("")})
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(locked)
    assert "DEE_API_AUTH_KEY" in str(exc.value)


def test_whitespace_admin_key_is_treated_as_unset(settings):
    locked = settings.model_copy(update={"api_auth_key": SecretStr("   ")})
    with pytest.raises(LaunchConfigError):
        verify_launch_config(locked)


def test_configured_admin_key_launches(settings):
    ok = settings.model_copy(update={"api_auth_key": SecretStr("a-real-key")})
    assert verify_launch_config(ok) is None


def test_no_local_exemption(settings):
    """env defaults to 'local'; the guard must not care (spec 0.1)."""
    for env in ("local", "staging", "prod"):
        locked = settings.model_copy(
            update={"api_auth_key": SecretStr(""), "env": env}
        )
        with pytest.raises(LaunchConfigError):
            verify_launch_config(locked)


def test_prod_on_sqlite_refuses_launch(settings):
    """A prod container on SQLite loses every row on redeploy (ephemeral disk)
    and serializes writes across workers."""
    locked = settings.model_copy(update={
        "api_auth_key": SecretStr("a-real-key"),
        "env": "prod",
        "candidates_db_url": "sqlite:///./data/veritas.db",
    })
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(locked)
    assert "DEE_CANDIDATES_DB_URL" in str(exc.value)


def test_prod_on_postgres_launches(settings):
    # S8.3 Phase B: a prod config must now also publish a grievance contact,
    # so this "sound prod config" case gets one. The refusal itself is tested
    # further down, in isolation.
    ok = settings.model_copy(update={
        "api_auth_key": SecretStr("a-real-key"),
        "env": "prod",
        "candidates_db_url": "postgresql+psycopg://u:p@h:5432/db",
        "grievance_officer_email": "dpo@example.com",
    })
    assert verify_launch_config(ok) is None


def test_local_on_sqlite_launches(settings):
    ok = settings.model_copy(update={"api_auth_key": SecretStr("a-real-key")})
    assert verify_launch_config(ok) is None


# ── S8.2: a browser-facing deployment has three more ways to be wrong ────────
# All prod-only, and that is NOT S8.1's rejected escape: there the refusal would
# have keyed on `env` DEFAULTING to the safe value. Here the refusing state IS
# the deployed one, so a forgotten variable still lands on the strict side.


def _prod(settings, **over):
    """Prod-shaped and passing S8.1's two refusals, so each test below isolates
    exactly the new refusal it names."""
    base = {
        "api_auth_key": SecretStr("a-real-key"),
        "env": "prod",
        "candidates_db_url": "postgresql+psycopg://u:p@h:5432/db",
        # S8.3 Phase B added the SEVENTH refusal, and this helper's whole job is
        # to satisfy every prior one so each test isolates the refusal it names.
        "grievance_officer_email": "dpo@example.com",
    }
    base.update(over)
    return settings.model_copy(update=base)


def test_prod_refuses_insecure_session_cookie(settings):
    """SameSite=None requires Secure in every browser, and a session cookie over
    plain HTTP is a session token in the clear."""
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(_prod(settings, session_cookie_secure=False))
    assert "session_cookie_secure" in str(exc.value)


def test_prod_refuses_wildcard_cors_origin(settings):
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(_prod(settings, cors_allowed_origins=["*"]))
    assert "cors_allowed_origins" in str(exc.value)


def test_prod_refuses_wildcard_even_beside_real_origins(settings):
    """A wildcard hiding in a list of legitimate origins is the likelier
    mistake, and it is just as fatal."""
    with pytest.raises(LaunchConfigError):
        verify_launch_config(
            _prod(settings, cors_allowed_origins=["https://app.example.com", "*"])
        )


def test_prod_refuses_capture_email_provider(settings):
    """CaptureEmail writes login codes to a file in plaintext -- an OTP leak
    wearing a test harness's clothes."""
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(_prod(settings, email_provider="capture"))
    assert "capture" in str(exc.value)


def test_prod_accepts_a_sound_browser_facing_config(settings):
    ok = _prod(settings, cors_allowed_origins=["https://app.example.com"])
    assert verify_launch_config(ok) is None


def test_local_may_use_capture_and_insecure_cookies(settings):
    """The key-less smoke runs over http://localhost and reads codes from a
    capture file. Both must stay possible outside prod."""
    ok = settings.model_copy(update={
        "api_auth_key": SecretStr("a-real-key"),
        "session_cookie_secure": False,
        "session_cookie_samesite": "lax",
        "email_provider": "capture",
    })
    assert verify_launch_config(ok) is None


def test_prod_refuses_to_boot_with_rate_limiting_disabled(settings):
    """No knob restores fail-open admin auth (S8.1); an unthrottled OTP
    endpoint on a public host is the same class of thing."""
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(_prod(settings, rate_limit_enabled=False))
    assert "rate_limit_enabled" in str(exc.value)


def test_local_may_disable_rate_limiting(settings):
    """The refusal is prod-only: local development and the test suite need the
    switch, and `env` defaults to local so a forgotten variable still lands on
    the strict side in a real deploy."""
    ok = settings.model_copy(update={
        "api_auth_key": SecretStr("a-real-key"),
        "rate_limit_enabled": False,
    })
    assert verify_launch_config(ok) is None


def test_prod_refuses_to_boot_without_a_published_grievance_contact(settings):
    """The SEVENTH refusal. DPDP requires the grievance mechanism to be
    PUBLISHED; GET /grievance would answer 200 with an empty contact, which is
    worse than 404 because it looks answered. It is also the RFP blocker GTM
    §8.1 names, and a boot failure is the only form of 'remember this' that
    works."""
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(_prod(settings, grievance_officer_email=""))
    assert "grievance" in str(exc.value).lower()


def test_a_whitespace_grievance_email_is_treated_as_unset(settings):
    with pytest.raises(LaunchConfigError):
        verify_launch_config(_prod(settings, grievance_officer_email="   "))


def test_a_published_contact_boots(settings):
    assert verify_launch_config(
        _prod(settings, grievance_officer_email="dpo@example.com")
    ) is None


def test_the_grievance_refusal_does_NOT_fire_outside_prod(settings):
    """It sits AFTER boot.py's `if settings.env != "prod": return`, or every
    local run and the whole test suite would break -- the same placement Phase
    A's rate-limit refusal needed."""
    ok = settings.model_copy(update={
        "api_auth_key": SecretStr("a-real-key"),
        "grievance_officer_email": "",
    })
    assert verify_launch_config(ok) is None


def test_rate_limiting_defaults_to_on(settings):
    """The default has to be the safe one: a deploy that forgets the variable
    gets a limiter, not an open OTP surface."""
    assert settings.rate_limit_enabled is True
    assert settings.rate_limit_trusted_proxy_hops == 0


def test_auth_defaults_are_closed(settings):
    """Defaults must be the refusing ones: no origin may call cross-site and no
    email provider is configured until someone says so."""
    assert settings.session_cookie_secure is True
    assert settings.session_cookie_samesite == "none"
    assert settings.cors_allowed_origins == []
    assert settings.email_provider == "null"
