"""Email notifier adapter; keep delivery imports out of shared pure OTP math."""
import structlog

from app.services.email import EmailClient, EmailSendFailed, EmailUnavailable
from app.verification.otp import DeliveryUnavailable

log = structlog.get_logger(__name__)


class EmailNotifier:
    """Share login's email client, without adding an implicit SMS provider."""

    def __init__(self, email: EmailClient):
        self.email = email

    def check_available(self, *, channel: str) -> None:
        if channel != "email" or not self.email.available:
            raise DeliveryUnavailable(channel)

    def send(self, destination: str, code: str, *, channel: str) -> None:
        self.check_available(channel=channel)
        try:
            self.email.send(to=destination, subject="Verify your Veritas contact",
                body=f"Your contact verification code is {code}\n\n"
                     "This code verifies control of the contact on your candidate record; "
                     "it is not a sign-in code or evidence of employment. "
                     "If you did not request this check, ignore this message.")
        except EmailUnavailable:
            raise DeliveryUnavailable("email") from None
        except Exception as exc:
            log.warning("verification.otp.delivery_failed", error_type=type(exc).__name__)
            raise EmailSendFailed("email_send_failed") from None
        log.info("verification.otp.dispatched", channel=channel)
