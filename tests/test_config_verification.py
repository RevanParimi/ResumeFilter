"""S7.1 config knobs exist with the documented defaults and bounds."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_verification_defaults(settings):
    assert settings.verif_otp_length == 6
    assert settings.verif_otp_ttl_minutes == 10
    assert settings.verif_otp_max_attempts == 5
    assert settings.verif_otp_resend_cooldown_seconds == 60
    assert settings.verif_outcome_ttl_days == 365
    assert settings.verif_otp_debug_echo is False
    assert settings.ret_verification_days == 1095


def test_otp_length_has_a_floor_so_codes_cannot_be_trivially_guessable():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, verif_otp_length=3)


def test_max_attempts_must_be_at_least_one():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, verif_otp_max_attempts=0)


def test_s72_document_knobs_have_conservative_defaults(settings):
    assert settings.doc_max_b64_chars == 8_000_000
    assert settings.doc_max_pages == 20
    assert settings.doc_metadata_skew_days == 1
    # Deliberately higher than xf_overlap_months_min (3): a short overlap is a
    # notice period, not a second job.
    assert settings.moonlight_min_overlap_months == 12
    assert settings.moonlight_min_overlap_months > settings.xf_overlap_months_min


def test_document_knobs_have_floors():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, doc_max_pages=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, moonlight_min_overlap_months=0)
