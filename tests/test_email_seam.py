"""The email delivery seam (S8.2).

The shape mirrors llm.py / speech.py and the tests pin the same property those
seams pin: the no-provider path REFUSES loudly rather than appearing to work.
"""

from __future__ import annotations

import json

import pytest

from app.services.email import (
    CaptureEmail, EmailClient, EmailUnavailable, NullEmail, SMTPEmail, build_email,
)


def test_null_email_refuses(settings):
    with pytest.raises(EmailUnavailable):
        NullEmail(settings).send(to="a@b.com", subject="s", body="b")


def test_null_email_logs_neither_code_nor_destination(settings, log_output):
    """S7.1's NullNotifier posture: an OTP in a log file is an OTP leak, and so
    is the address it was going to.

    ASSERTED ON RENDERED OUTPUT, not on caplog. The caplog version of this test
    passed for eight PIs while checking nothing: structlog writes through
    PrintLoggerFactory to stdout and never touches stdlib logging, so
    `caplog.text` was always "" and the assertion read `"123456" not in ""`.
    Proved by mutation -- a NullEmail logging BOTH the code and the address
    passed the old test 10/10.
    """
    with pytest.raises(EmailUnavailable):
        NullEmail(settings).send(to="someone@example.in", subject="s", body="code 123456")
    rendered = log_output.text
    assert "email.dispatch.refused" in rendered, "the attempt must still be logged"
    assert "123456" not in rendered
    assert "someone@example.in" not in rendered


def test_capture_email_writes_json_lines(settings, tmp_path):
    path = tmp_path / "mail.jsonl"
    client = CaptureEmail(settings.model_copy(update={"email_capture_path": str(path)}))
    client.send(to="a@b.com", subject="Your code", body="code 123456")
    client.send(to="c@d.com", subject="Your code", body="code 654321")
    lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert [l["to"] for l in lines] == ["a@b.com", "c@d.com"]
    assert "123456" in lines[0]["body"]


def test_capture_email_creates_its_parent_directory(settings, tmp_path):
    path = tmp_path / "nested" / "deeper" / "mail.jsonl"
    CaptureEmail(
        settings.model_copy(update={"email_capture_path": str(path)})
    ).send(to="a@b.com", subject="s", body="b")
    assert path.exists()


def test_build_email_defaults_to_the_refusing_client(settings):
    assert isinstance(build_email(settings), NullEmail)


def test_build_email_never_falls_back_to_capture(settings, tmp_path):
    """Selecting capture by accident would be PI-8 section 1's bug again: a test
    harness reachable in production because nobody configured the real one.
    A capture PATH being set must not be enough -- the provider must say so."""
    misconfigured_smtp = settings.model_copy(update={
        "email_provider": "smtp",
        "email_smtp_host": "",                       # the operator forgot it
        "email_capture_path": str(tmp_path / "m.jsonl"),
    })
    assert isinstance(build_email(misconfigured_smtp), NullEmail)


def test_build_email_selects_smtp_when_configured(settings):
    configured = settings.model_copy(update={
        "email_provider": "smtp", "email_smtp_host": "smtp.example.com",
    })
    assert isinstance(build_email(configured), SMTPEmail)


def test_build_email_selects_capture_only_when_asked(settings, tmp_path):
    asked = settings.model_copy(update={
        "email_provider": "capture", "email_capture_path": str(tmp_path / "m.jsonl"),
    })
    assert isinstance(build_email(asked), CaptureEmail)


def test_capture_without_a_path_refuses(settings):
    """A capture client with nowhere to write is a silent black hole, which is
    exactly the 'appears to succeed' failure this seam exists to prevent."""
    pathless = settings.model_copy(update={"email_provider": "capture"})
    assert isinstance(build_email(pathless), NullEmail)


def test_every_client_satisfies_the_protocol(settings):
    for client in (NullEmail(settings), CaptureEmail(settings), SMTPEmail(settings)):
        assert isinstance(client, EmailClient)
