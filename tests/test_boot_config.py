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
    ok = settings.model_copy(update={
        "api_auth_key": SecretStr("a-real-key"),
        "env": "prod",
        "candidates_db_url": "postgresql+psycopg://u:p@h:5432/db",
    })
    assert verify_launch_config(ok) is None


def test_local_on_sqlite_launches(settings):
    ok = settings.model_copy(update={"api_auth_key": SecretStr("a-real-key")})
    assert verify_launch_config(ok) is None
