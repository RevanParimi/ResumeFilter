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


def test_contact_execution_defaults_yaml_and_environment(monkeypatch):
    import yaml
    with open('config.yaml', encoding='utf-8') as file:
        raw = yaml.safe_load(file)
    settings = Settings(_env_file=None)
    assert settings.contact_code_max_concurrent_requests == raw['contact_code_max_concurrent_requests'] == 2
    assert settings.contact_code_wait_seconds == raw['contact_code_wait_seconds'] == 20
    monkeypatch.setenv('DEE_CONTACT_CODE_MAX_CONCURRENT_REQUESTS', '3')
    monkeypatch.setenv('DEE_CONTACT_CODE_WAIT_SECONDS', '.5')
    assert Settings(_env_file=None).contact_code_max_concurrent_requests == 3
    assert Settings(_env_file=None).contact_code_wait_seconds == .5


@pytest.mark.parametrize('name,value', [('contact_code_max_concurrent_requests', 0),
    ('contact_code_max_concurrent_requests', -1), ('contact_code_wait_seconds', 0),
    ('contact_code_wait_seconds', -1), ('contact_code_wait_seconds', float('inf')),
    ('contact_code_wait_seconds', float('nan'))])
def test_contact_execution_bounds_are_positive_and_finite(name, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})


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
