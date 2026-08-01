"""Launch-time configuration checks (PI-8 S8.1).

``require_api_key`` refuses every request when no credential is configured, but
a service that 401s everything looks merely broken. This module makes the
misconfiguration loud at the one moment an operator is watching: boot.

There is deliberately NO ``env`` exemption (spec 0.1). ``env`` DEFAULTS to
"local", so an env-gated escape would make a safe deploy depend on remembering
two variables instead of one -- the same fail-open shape, one indirection
deeper.
"""

from __future__ import annotations

from app.core.config import Settings


class LaunchConfigError(RuntimeError):
    """The process must not start with this configuration."""


def verify_launch_config(settings: Settings) -> None:
    """Raise :class:`LaunchConfigError` if this config must not serve traffic."""
    if not settings.api_auth_key.get_secret_value().strip():
        raise LaunchConfigError(
            "DEE_API_AUTH_KEY is not set. The admin plane -- including "
            "POST /candidates/{id}/auth-key, which mints any candidate's access "
            "key -- would be unguarded, so the service refuses to start. Set "
            "DEE_API_AUTH_KEY in the environment or .env (e.g. "
            "`openssl rand -hex 32`). There is no local-development exemption."
        )
    if settings.env == "prod" and settings.candidates_db_url.startswith("sqlite"):
        raise LaunchConfigError(
            "DEE_ENV=prod with a SQLite DEE_CANDIDATES_DB_URL. Container disks "
            "are ephemeral (every row is lost on redeploy) and SQLite "
            "serializes writes across workers. Point DEE_CANDIDATES_DB_URL at "
            "Postgres."
        )
