"""LLM client resilience config (FR-21): retries reach the OpenAI SDK client."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.services.llm import OpenRouterLLM, _extract_json


@pytest.mark.parametrize("raw", [
    '[]', '[{"coherence": 1}]', 'null', 'true', '1', '"text"',
    '{"coherence": NaN}', '{"confidence": Infinity}',
    '{"nested": {"value": -Infinity}}', '{"value": 1e999}',
    '[{"nested": {"confidence": 1}}]',
    'Here is the reply: [{"coherence": 1}]',
    '```json\n[{"coherence": 1}]\n```',
])
def test_json_parser_abstains_on_nonobjects_and_nonfinite(raw):
    assert _extract_json(raw) == {}


@pytest.mark.parametrize("raw", [
    '{"value": 0.9}', '```json\n{"value": 0.9}\n```',
    'Here is the reply: {"value": 0.9}',
])
def test_json_parser_retains_valid_objects(raw):
    assert _extract_json(raw) == {"value": 0.9}


def test_settings_default_retries(settings):
    assert settings.llm_max_retries == 2


async def test_openrouter_client_gets_retries_and_timeout(settings):
    live = settings.model_copy(
        update={
            "openrouter_api_key": SecretStr("sk-or-test"),
            "llm_max_retries": 5,
        }
    )
    provider = OpenRouterLLM(live)
    try:
        assert provider._client is None
        client = provider._get_client()
        assert client.max_retries == 5
        assert client.timeout == live.llm_timeout_seconds
    finally:
        await provider.aclose()
