"""LLM client resilience config (FR-21): retries reach the OpenAI SDK client."""

from __future__ import annotations

from pydantic import SecretStr

from app.services.llm import OpenRouterLLM


def test_settings_default_retries(settings):
    assert settings.llm_max_retries == 2


def test_openrouter_client_gets_retries_and_timeout(settings):
    live = settings.model_copy(
        update={
            "openrouter_api_key": SecretStr("sk-or-test"),
            "llm_max_retries": 5,
        }
    )
    client = OpenRouterLLM(live)._client
    assert client.max_retries == 5
    assert client.timeout == live.llm_timeout_seconds
