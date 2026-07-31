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
