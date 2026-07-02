"""LLM wrapper — tiered, config-driven, key never hardcoded.

Inference goes through OpenRouter (OpenAI-wire-compatible), so the engine stays
vendor-neutral and economical: any model OpenRouter fronts is reachable by id.

Nodes ask for a logical *tier* ("reasoning" | "reasoning_hard" | "parsing" |
"bulk"); this module resolves it to a concrete model id via settings. The
abstract :class:`LLMClient` lets tests inject a fake with zero network.

When no API key is configured, :func:`build_llm` returns a :class:`NullLLM`
that abstains (empty text / empty dict) so the pipeline degrades to rule-only
reasoning instead of crashing.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Literal, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

Tier = Literal["reasoning", "reasoning_hard", "parsing", "bulk"]
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Best-effort: parse a JSON object out of a model response."""
    if not text:
        return {}
    fenced = text.strip()
    if fenced.startswith("```"):
        fenced = fenced.strip("`")
        fenced = fenced.split("\n", 1)[-1] if "\n" in fenced else fenced
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        m = _JSON_BLOCK.search(text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return {}
    return {}


class LLMClient(ABC):
    """Tiered text/JSON completion surface."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def _model(self, tier: Tier) -> str:
        return self.settings.model_for_tier(tier)

    @abstractmethod
    async def _araw(self, *, model: str, system: str, prompt: str, max_tokens: int) -> str:
        ...

    async def acomplete_text(
        self, *, tier: Tier, system: str, prompt: str, max_tokens: Optional[int] = None
    ) -> str:
        return await self._araw(
            model=self._model(tier),
            system=system,
            prompt=prompt,
            max_tokens=max_tokens or self.settings.llm_max_tokens,
        )

    async def acomplete_json(
        self, *, tier: Tier, system: str, prompt: str, max_tokens: Optional[int] = None
    ) -> dict:
        text = await self.acomplete_text(
            tier=tier,
            system=system + "\n\nRespond with a single valid JSON object and nothing else.",
            prompt=prompt,
            max_tokens=max_tokens,
        )
        return _extract_json(text)


class OpenRouterLLM(LLMClient):
    """Live OpenRouter client via the OpenAI-compatible AsyncOpenAI SDK."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        super().__init__(settings)
        from openai import AsyncOpenAI  # local import; optional at test time

        headers: dict[str, str] = {}
        if self.settings.openrouter_app_url:
            headers["HTTP-Referer"] = self.settings.openrouter_app_url
        if self.settings.openrouter_app_title:
            headers["X-Title"] = self.settings.openrouter_app_title

        self._client = AsyncOpenAI(
            api_key=self.settings.openrouter_api_key.get_secret_value(),
            base_url=self.settings.openrouter_base_url,
            timeout=self.settings.llm_timeout_seconds,
            max_retries=self.settings.llm_max_retries,
            default_headers=headers or None,
        )

    async def _araw(self, *, model: str, system: str, prompt: str, max_tokens: int) -> str:
        resp = await self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""


class NullLLM(LLMClient):
    """No-key fallback: abstains so rule-based reasoning still runs."""

    async def _araw(self, *, model: str, system: str, prompt: str, max_tokens: int) -> str:
        return ""


def build_llm(settings: Optional[Settings] = None) -> LLMClient:
    settings = settings or get_settings()
    if settings.has_openrouter_key:
        return OpenRouterLLM(settings)
    log.warning("llm_no_api_key", detail="Falling back to NullLLM; rules will drive.")
    return NullLLM(settings)
