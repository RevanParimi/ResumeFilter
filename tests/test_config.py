"""Config knob presence + env-override sanity (S5.2 comp_* additions)."""

from app.core.config import Settings
import pytest
from pydantic import ValidationError


def test_comp_defaults_present():
    s = Settings()
    assert s.comp_min_observations == 5
    assert s.comp_prior_strength == 8.0
    assert s.comp_confidence_floor == 0.30
    assert s.comp_confidence_cap == 0.90
    assert (s.comp_mid_years, s.comp_senior_years, s.comp_lead_years) == (2.0, 5.0, 9.0)
    assert s.comp_benchmark_tolerance == 0.10
    assert s.comp_currency_default == "INR"
    assert s.comp_bands_path is None


def test_comp_env_override(monkeypatch):
    monkeypatch.setenv("DEE_COMP_MIN_OBSERVATIONS", "3")
    assert Settings().comp_min_observations == 3


def test_auth_code_execution_defaults_yaml_and_env(monkeypatch):
    import yaml
    with open('config.yaml', encoding='utf-8') as file:
        raw = yaml.safe_load(file)
    settings = Settings(_env_file=None)
    assert settings.auth_code_max_concurrent_requests == raw['auth_code_max_concurrent_requests'] == 2
    assert settings.auth_code_wait_seconds == raw['auth_code_wait_seconds'] == 20
    monkeypatch.setenv('DEE_AUTH_CODE_MAX_CONCURRENT_REQUESTS', '3')
    monkeypatch.setenv('DEE_AUTH_CODE_WAIT_SECONDS', '.5')
    assert Settings(_env_file=None).auth_code_max_concurrent_requests == 3
    assert Settings(_env_file=None).auth_code_wait_seconds == .5


@pytest.mark.parametrize('name,value', [('auth_code_max_concurrent_requests', 0),
    ('auth_code_max_concurrent_requests', -1), ('auth_code_wait_seconds', 0),
    ('auth_code_wait_seconds', -1), ('auth_code_wait_seconds', float('inf')),
    ('auth_code_wait_seconds', float('nan'))])
def test_auth_code_execution_budgets_are_positive_and_finite(name, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})


def test_auth_resolution_execution_defaults_yaml_and_env(monkeypatch):
    import yaml
    with open('config.yaml', encoding='utf-8') as file:
        raw = yaml.safe_load(file)
    settings = Settings(_env_file=None)
    assert settings.auth_resolution_max_concurrent_requests == raw['auth_resolution_max_concurrent_requests'] == 8
    assert settings.auth_resolution_wait_seconds == raw['auth_resolution_wait_seconds'] == 20
    monkeypatch.setenv('DEE_AUTH_RESOLUTION_MAX_CONCURRENT_REQUESTS', '3')
    monkeypatch.setenv('DEE_AUTH_RESOLUTION_WAIT_SECONDS', '.5')
    assert Settings(_env_file=None).auth_resolution_max_concurrent_requests == 3
    assert Settings(_env_file=None).auth_resolution_wait_seconds == .5


@pytest.mark.parametrize('name,value', [('auth_resolution_max_concurrent_requests', 0),
    ('auth_resolution_max_concurrent_requests', -1), ('auth_resolution_wait_seconds', 0),
    ('auth_resolution_wait_seconds', -1), ('auth_resolution_wait_seconds', float('inf')),
    ('auth_resolution_wait_seconds', float('nan'))])
def test_auth_resolution_execution_budgets_are_positive_and_finite(name, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})


def test_request_body_budget_default_yaml_and_env(monkeypatch):
    import yaml
    with open("config.yaml", encoding="utf-8") as file:
        raw = yaml.safe_load(file)
    assert Settings(_env_file=None).max_request_body_bytes == raw["max_request_body_bytes"] == 32_000_000
    monkeypatch.setenv("DEE_MAX_REQUEST_BODY_BYTES", "2048")
    assert Settings(_env_file=None).max_request_body_bytes == 2048


def test_auth_redemption_execution_defaults_yaml_and_env(monkeypatch):
    import yaml
    with open('config.yaml', encoding='utf-8') as file:
        raw = yaml.safe_load(file)
    settings = Settings(_env_file=None)
    assert settings.auth_redemption_max_concurrent_requests == raw['auth_redemption_max_concurrent_requests'] == 2
    assert settings.auth_redemption_wait_seconds == raw['auth_redemption_wait_seconds'] == 20
    monkeypatch.setenv('DEE_AUTH_REDEMPTION_MAX_CONCURRENT_REQUESTS', '3')
    monkeypatch.setenv('DEE_AUTH_REDEMPTION_WAIT_SECONDS', '.5')
    assert Settings(_env_file=None).auth_redemption_max_concurrent_requests == 3
    assert Settings(_env_file=None).auth_redemption_wait_seconds == .5


@pytest.mark.parametrize('name,value', [('auth_redemption_max_concurrent_requests', 0),
    ('auth_redemption_max_concurrent_requests', -1), ('auth_redemption_wait_seconds', 0),
    ('auth_redemption_wait_seconds', -1), ('auth_redemption_wait_seconds', float('inf')),
    ('auth_redemption_wait_seconds', float('nan'))])
def test_auth_redemption_execution_budgets_are_positive_and_finite(name, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})


@pytest.mark.parametrize("limit", [0, -1])
def test_request_body_budget_requires_positive_limit(limit):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_request_body_bytes=limit)


def test_linkedin_source_defaults():
    from app.core.config import Settings
    s = Settings(_env_file=None, openrouter_api_key="")
    assert s.max_linkedin_b64_chars == 8_000_000
    assert s.ps_linkedin_skill_base_confidence == 0.4
    assert s.ps_linkedin_skill_corroborated_confidence == 0.6
    assert s.ps_linkedin_max_rows == 5_000


def test_s64_portal_config_defaults():
    s = Settings(_env_file=None, openrouter_api_key="")
    assert s.candidate_access_key_bytes == 32
    assert s.ret_resume_days == 1095
    assert s.ret_interview_record_days == 1825
    assert s.ret_coding_round_days == 1825
    assert s.ret_observed_offer_days == 1825
    assert s.ret_profile_source_days == 1095
    assert s.ret_audit_log_days == 2555
