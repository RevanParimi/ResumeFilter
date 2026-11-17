"""Config defaults and environment overrides."""

from app.core.config import Settings
import pytest
from pydantic import ValidationError


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


@pytest.mark.parametrize('prefix', ['auth_redemption', 'auth_session', 'candidate_record', 'candidate_ingest', 'report_record', 'outcome_record', 'evaluation_record', 'batch_read', 'batch_registration', 'batch_mutation', 'batch_admission', 'portal_read', 'portal_write'])
def test_sql_execution_defaults_yaml_and_env(monkeypatch, prefix):
    import yaml
    with open('config.yaml', encoding='utf-8') as file:
        raw = yaml.safe_load(file)
    settings = Settings(_env_file=None)
    capacity, wait = f'{prefix}_max_concurrent_requests', f'{prefix}_wait_seconds'
    assert getattr(settings, capacity) == raw[capacity] == (4 if prefix == 'batch_read' else 2)
    assert getattr(settings, wait) == raw[wait] == 20
    monkeypatch.setenv('DEE_' + capacity.upper(), '3')
    monkeypatch.setenv('DEE_' + wait.upper(), '.5')
    assert getattr(Settings(_env_file=None), capacity) == 3
    assert getattr(Settings(_env_file=None), wait) == .5


@pytest.mark.parametrize('name,value', [('auth_redemption_max_concurrent_requests', 0),
    ('auth_redemption_max_concurrent_requests', -1), ('auth_redemption_wait_seconds', 0),
    ('auth_redemption_wait_seconds', -1), ('auth_redemption_wait_seconds', float('inf')),
    ('auth_redemption_wait_seconds', float('nan'))])
@pytest.mark.parametrize('prefix', ['auth_redemption', 'auth_session', 'candidate_record', 'candidate_ingest', 'report_record', 'outcome_record', 'evaluation_record', 'batch_read', 'batch_registration', 'batch_mutation', 'batch_admission', 'portal_read', 'portal_write'])
def test_sql_execution_budgets_are_positive_and_finite(name, value, prefix):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name.replace('auth_redemption', prefix): value})


@pytest.mark.parametrize("limit", [0, -1])
def test_request_body_budget_requires_positive_limit(limit):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_request_body_bytes=limit)


def test_s64_portal_config_defaults():
    s = Settings(_env_file=None, openrouter_api_key="")
    assert s.candidate_access_key_bytes == 32
    assert s.ret_resume_days == 1095
    assert s.ret_audit_log_days == 2555
