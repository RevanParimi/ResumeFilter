"""Email delivery seam -- config-driven, credentials never hardcoded (S8.2).

Deliberately shaped like app/services/llm.py and app/services/speech.py, which
have survived seven PIs: an abstract client, a live implementation, and a Null
that REFUSES so tests need no network and a key-less deployment still works.

The refusal matters and is not an error path to paper over. With no provider
configured, signup and login return 503 email_unavailable rather than appearing
to succeed -- the NullSpeech posture from S7.3. Nothing silently degrades.

This also closes a standing gap: S7.1's L2 contact-control assurance ships, is
tested, and has NEVER delivered an OTP to a human, because NullNotifier logs
neither the code nor the destination. SMTPEmail gives that rung a real delivery
path for the first time since 2026-07-31.
"""

from __future__ import annotations

import json
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class EmailUnavailable(Exception):
    """No email provider is configured. The caller surfaces a clear 503 -- this
    is the designed no-provider path, not a malfunction."""


class EmailSendFailed(Exception):
    """A configured provider could not deliver (bad host, auth, timeout). The
    caller must NOT consume the login challenge: a retry has to be free, so a
    vendor outage never costs someone their login."""


class EmailClient(ABC):
    #: Can this client deliver at all? Callers probe this BEFORE doing any
    #: account lookup, so a broken provider refuses identically for addresses
    #: that exist and addresses that do not. Without it, "503 for a real user,
    #: 202 for a stranger" is an account-enumeration oracle that only appears
    #: when email is misconfigured -- i.e. exactly when nobody is watching.
    available: bool = True

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    @abstractmethod
    def send(self, *, to: str, subject: str, body: str) -> None:
        ...


class NullEmail(EmailClient):
    """Ships nothing. Logs the attempt WITHOUT the address or the body.

    Both omissions are deliberate: an OTP in a log file is an OTP leak, and the
    address it was going to is the personal data this system exists to protect.
    """

    available = False

    def send(self, *, to: str, subject: str, body: str) -> None:
        log.info("email.dispatch.refused", provider="null")
        raise EmailUnavailable(
            "no email provider is configured; set email_provider=smtp"
        )


class CaptureEmail(EmailClient):
    """Writes messages as JSON lines to `email_capture_path` instead of sending.

    This is how the key-less smoke drives a real login end to end with no
    provider. It is selected ONLY by explicit config -- never by fallback -- and
    prod refuses to boot with it (app/core/boot.py), because a file full of
    plaintext login codes is an OTP leak wearing a test harness's clothes.
    """

    def send(self, *, to: str, subject: str, body: str) -> None:
        path = Path(self.settings.email_capture_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps({"to": to, "subject": subject, "body": body}) + "\n"
            )
        log.info("email.dispatch.captured")


class SMTPEmail(EmailClient):
    """Live delivery over SMTP, STARTTLS by default. Credentials come from .env
    (DEE_EMAIL_SMTP_USER / DEE_EMAIL_SMTP_PASSWORD), never from YAML."""

    def send(self, *, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.settings.email_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(
                self.settings.email_smtp_host,
                self.settings.email_smtp_port,
                timeout=15,
            ) as smtp:
                if self.settings.email_smtp_starttls:
                    smtp.starttls()
                user = self.settings.email_smtp_user.get_secret_value()
                if user:
                    smtp.login(
                        user, self.settings.email_smtp_password.get_secret_value()
                    )
                smtp.send_message(msg)
        except Exception as exc:  # noqa: BLE001 -- one failure surface for the caller
            # No address and no body in the log line, same reason as NullEmail.
            log.warning("email.dispatch.failed", error=str(exc))
            raise EmailSendFailed(f"email delivery failed: {exc}") from exc
        log.info("email.dispatch.sent")


def build_email(settings: Optional[Settings] = None) -> EmailClient:
    """Resolve the configured provider, or return the REFUSING client.

    A misconfigured smtp (no host) and a pathless capture both land on NullEmail
    rather than on something that looks like it works. Silent degradation into a
    working-looking client is PI-8 section 1's bug shape, and it is the reason
    `capture` is unreachable without someone naming it.
    """
    settings = settings or get_settings()
    if settings.email_provider == "smtp" and settings.email_smtp_host:
        return SMTPEmail(settings)
    if settings.email_provider == "capture" and settings.email_capture_path:
        return CaptureEmail(settings)
    log.warning(
        "email_unavailable",
        provider=settings.email_provider,
        detail="Signup and login will return 503 email_unavailable.",
    )
    return NullEmail(settings)
