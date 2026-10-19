"""Production email wiring, honest refusals and delivery privacy, all offline."""
from datetime import datetime, timedelta, timezone
import json
import random
import re
import smtplib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.candidates.hashing import contact_hash, normalize_email, normalize_phone
from app.candidates.models import CandidateRow
from app.core.db import Base, make_engine
from app.main import create_app
from app.services import build_default_services
from app.services.email import EmailClient, EmailSendFailed, SMTPEmail
from app.verification.models import VerificationChallengeRow
from app.verification.schema import VerificationMethod, VerificationStatus

EMAIL = "synthetic-contact@example.com"
PHONE = "+919876543210"
NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


class MemoryEmail(EmailClient):
    def __init__(self, settings):
        super().__init__(settings)
        self.messages = []
        self.fail = False

    def send(self, *, to, subject, body):
        self.messages.append({"to": to, "subject": subject, "body": body})
        if self.fail:
            raise EmailSendFailed(f"private provider payload {to} {body}")


def production(settings, tmp_path, monkeypatch, *, provider="capture", email=None):
    configured = settings.model_copy(update={
        "candidates_db_url": f"sqlite:///{(tmp_path / 'app.db').as_posix()}",
        "vectorstore_backend": "memory", "email_provider": provider,
        "email_capture_path": str(tmp_path / "mail.jsonl"),
    })
    Base.metadata.create_all(make_engine(configured.candidates_db_url))
    if email is not None:
        monkeypatch.setattr("app.services.build_email", lambda _s: email)
    services = build_default_services(configured)
    with services.candidates._session_factory.begin() as session:
        row = CandidateRow(full_name="Synthetic Contact",
            email_hash=contact_hash(normalize_email(EMAIL), configured.contact_hash_salt),
            phone_hash=contact_hash(normalize_phone(PHONE), configured.contact_hash_salt))
        session.add(row)
        session.flush()
        cid = row.id
    return services, cid, {"X-Candidate-Key": services.candidates.issue_access_key(cid)}


def code(message):
    return re.search(r"\b(\d{6})\b", message["body"])[1]


def test_production_capture_delivers_confirmable_code_without_debug_echo(settings, tmp_path, monkeypatch, log_output):
    services, cid, headers = production(settings, tmp_path, monkeypatch)
    with TestClient(create_app(services)) as http:
        start = http.post("/portal/verifications", headers=headers,
                          json={"method": "otp_email", "destination": "  SYNTHETIC-CONTACT@Example.COM "})
        assert start.status_code == 200
        assert start.json().get("debug_code") is None
        messages = [json.loads(line) for line in (tmp_path / "mail.jsonl").read_text().splitlines()] if (tmp_path / "mail.jsonl").exists() else []
        assert len(messages) == 1, "production must deliver the verification code through its email capability"
        assert messages[0]["to"] == EMAIL
        otp = code(messages[0])
        vid = start.json()["verification"]["id"]
        confirmed = http.post(f"/portal/verifications/{vid}/confirm", headers=headers, json={"code": otp})
        assert confirmed.status_code == 200 and confirmed.json()["status"] == "verified"
        assert http.get("/portal/verifications", headers=headers).json()["assurance"]["level"] == 2
        assert http.get("/portal/me", headers=headers).json()["identity"]["methods"] == ["otp_email"]
        assert http.post(f"/portal/verifications/{vid}/confirm", headers=headers, json={"code": otp}).status_code == 400
    assert EMAIL not in log_output.text and otp not in log_output.text


@pytest.mark.parametrize("method,destination,detail", [("otp_email", EMAIL, "email_unavailable"),
                                                       ("otp_phone", PHONE, "phone_unavailable")])
def test_unavailable_delivery_refuses_before_creating_rows(settings, tmp_path, monkeypatch, method, destination, detail):
    services, cid, headers = production(settings, tmp_path, monkeypatch, provider="null")
    with TestClient(create_app(services)) as http:
        response = http.post("/portal/verifications", headers=headers, json={"method": method, "destination": destination})
        assert response.status_code == 503
        assert response.json() == {"detail": detail}
        assert services.verification._store.verifications_for_candidate(cid) == []


def test_provider_failure_has_safe_http_error_and_no_confirmable_secret(settings, tmp_path, monkeypatch, log_output):
    mail = MemoryEmail(settings)
    mail.fail = True
    services, cid, headers = production(settings, tmp_path, monkeypatch, email=mail)
    with TestClient(create_app(services)) as http:
        response = http.post("/portal/verifications", headers=headers, json={"method": "otp_email", "destination": EMAIL})
        assert response.status_code == 503 and response.json() == {"detail": "email_send_failed"}
        rows = services.verification._store.verifications_for_candidate(cid)
        assert len(rows) == 1 and rows[0].status is VerificationStatus.FAILED
        with services.candidates._session_factory() as session:
            assert session.scalar(select(VerificationChallengeRow)) is None
        assert http.post(f"/portal/verifications/{rows[0].id}/confirm", headers=headers,
                         json={"code": code(mail.messages[0])}).status_code == 400
        mail.fail = False
        retry = http.post("/portal/verifications", headers=headers, json={"method": "otp_email", "destination": EMAIL})
        assert retry.status_code == 200, "an unsent attempt must not create a resend cooldown"
    assert EMAIL not in log_output.text and code(mail.messages[0]) not in log_output.text


def test_failed_resend_preserves_previous_secret_and_attempt_state(settings, tmp_path, monkeypatch):
    mail = MemoryEmail(settings)
    services, cid, _ = production(settings, tmp_path, monkeypatch, email=mail)
    service = services.verification
    first, first_code = service.start(cid, VerificationMethod.OTP_EMAIL, destination=EMAIL, at=NOW, rng=random.Random(7))
    assert len(mail.messages) == 1
    with services.candidates._session_factory() as session:
        old = session.scalar(select(VerificationChallengeRow))
        old_id, old_hash = old.id, old.code_hash
    mail.fail = True
    later = NOW + timedelta(seconds=settings.verif_otp_resend_cooldown_seconds + 1)
    with pytest.raises(EmailSendFailed):
        service.start(cid, VerificationMethod.OTP_EMAIL, destination=EMAIL, at=later, rng=random.Random(8))
    with services.candidates._session_factory() as session:
        surviving = session.scalar(select(VerificationChallengeRow))
        assert (surviving.id, surviving.code_hash, surviving.attempts) == (old_id, old_hash, 0)
    assert service.confirm(cid, first.id, first_code, at=later).status is VerificationStatus.VERIFIED


def test_smtp_failure_logs_and_exception_do_not_disclose_contact_or_code(settings, monkeypatch, log_output):
    otp = "907153"
    class BrokenSMTP:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def starttls(self): pass
        def send_message(self, message):
            raise smtplib.SMTPException(f"rejected {message['To']} {otp}")
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: BrokenSMTP())
    with pytest.raises(EmailSendFailed) as failure:
        SMTPEmail(settings).send(to=EMAIL, subject="Synthetic verification", body=f"code {otp}")
    assert EMAIL not in log_output.text and otp not in log_output.text
    assert EMAIL not in str(failure.value) and otp not in str(failure.value)
