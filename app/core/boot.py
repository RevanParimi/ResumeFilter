"""Launch-time configuration checks (PI-8, S8.1 + S8.2).

``require_api_key`` refuses every request when no credential is configured, but
a service that 401s everything looks merely broken. This module makes the
misconfiguration loud at the one moment an operator is watching: boot.

S8.2 adds three prod-only refusals for the browser-facing surface. They belong
here for the same reason: a session cookie sent in the clear, a wildcard CORS
origin, or a capture email provider each produce a service that *works* while
being unsafe, which is the failure mode a boot check exists to catch.

S8.3 adds a sixth and a seventh, on the same argument. A disabled rate limiter
serves every request perfectly while leaving the OTP endpoints -- the
brute-force surface PI-8 itself created -- unthrottled on a public host. And an
unpublished grievance officer leaves ``GET /grievance`` answering 200 with an
empty contact, which is worse than a 404 because it looks answered.

S8.6 adds an eighth. ``config.yaml`` ships ``email_provider: "null"``, so a
prod deploy on the shipped defaults boots clean and then answers 503
``email_unavailable`` to every signup and login on all three auth planes --
while ``/healthz`` reports the service healthy. This check asks
``build_email(settings)`` whether it can actually deliver, rather than
pattern-matching ``email_provider``, because ``build_email`` also falls back to
``NullEmail`` for ``provider=smtp`` with an empty host; a string check would
miss that case and pass a deploy that still 503s every login.

There is deliberately NO ``env`` exemption (spec 0.1). ``env`` DEFAULTS to
"local", so an env-gated escape would make a safe deploy depend on remembering
two variables instead of one -- the same fail-open shape, one indirection
deeper.
"""

from __future__ import annotations

from app.core.config import Settings
from app.services.email import build_email


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

    # -- S8.2: the three ways a BROWSER-FACING deployment is misconfigured -----
    # These are prod-only, and that is not the escape 0.1 rejected: there the
    # refusal would have keyed on `env` DEFAULTING to the safe value. Here the
    # refusing state IS the deployed one, so a forgotten variable still lands on
    # the strict side.
    if settings.env != "prod":
        return
    if not settings.session_cookie_secure:
        raise LaunchConfigError(
            "DEE_ENV=prod with session_cookie_secure=false. The session cookie "
            "would travel in the clear, and SameSite=None (required, because "
            "the UI is separately hosted) is rejected by every browser without "
            "Secure. Set session_cookie_secure=true and serve over HTTPS."
        )
    if "*" in settings.cors_allowed_origins:
        raise LaunchConfigError(
            'DEE_ENV=prod with "*" in cors_allowed_origins. This API is called '
            "with credentials, so a wildcard origin is never correct — browsers "
            "reject the combination, and relying on that as the guard leaves a "
            "defect waiting to be 'fixed' by silencing the console error. List "
            "the UI's exact origins."
        )
    if settings.email_provider == "capture":
        raise LaunchConfigError(
            "DEE_ENV=prod with email_provider=capture. CaptureEmail writes login "
            "codes to email_capture_path in plaintext — that is an OTP leak "
            "wearing a test harness's clothes. Use email_provider=smtp."
        )
    if not settings.rate_limit_enabled:
        raise LaunchConfigError(
            "DEE_ENV=prod with rate_limit_enabled=false. The OTP endpoints are "
            "the brute-force surface this PI created, and they would be "
            "unthrottled on a public host. No knob restores fail-open admin "
            "auth (S8.1); this is the same class of thing. Set "
            "rate_limit_enabled=true."
        )
    if not settings.grievance_officer_email.strip():
        raise LaunchConfigError(
            "DEE_ENV=prod with an empty grievance_officer_email. DPDP requires "
            "the grievance mechanism to be PUBLISHED, and GET /grievance would "
            "answer 200 with an empty contact -- worse than a 404, because it "
            "looks answered. It is also the RFP blocker the GTM analysis names. "
            "Set grievance_officer_email (and the name and phone beside it)."
        )

    # -- S8.6: the EIGHTH refusal -- a deployment nobody can log into ---------
    # This ASKS THE BUILDER rather than testing `email_provider`, and that is
    # the whole design. `build_email` returns NullEmail for provider="smtp"
    # with an empty host, so a string check would pass that config and the
    # service would 503 every login anyway -- the rule applied at one entry
    # point and not the other, which has shipped as a real defect in S7.1,
    # S7.2, S7.3, S8.4 Phase B and S8.5. `EmailClient.available` already exists
    # for exactly this question and is False only on NullEmail, so there is one
    # predicate and no second copy to drift. It opens no socket.
    #
    # `capture` is NOT caught here -- it IS available, and its fault is that it
    # writes OTPs to a file. It keeps its own refusal above, so each check
    # isolates one fault.
    if not build_email(settings).available:
        raise LaunchConfigError(
            "DEE_ENV=prod with no working email provider "
            f"(email_provider={settings.email_provider!r}, "
            f"email_smtp_host={'set' if settings.email_smtp_host else 'EMPTY'}). "
            "Signup and login on all three planes answer 503 "
            "email_unavailable, so org self-onboard (PI-8 blocker 5) and "
            "candidate self-registration (blocker 4) do not work at all -- "
            "while /healthz reports the service healthy. Set "
            "email_provider=smtp with email_smtp_host and the DEE_EMAIL_SMTP_* "
            "credentials. There is no provider that 'works well enough' for a "
            "login code: it either arrives or the account is unreachable."
        )
