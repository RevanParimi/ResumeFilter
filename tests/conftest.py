"""Shared test fixtures — fully offline (NullLLM, in-memory stores, fake GitHub).

The genuine vs. fabricated assertions are driven by the DETERMINISTIC rule
registry, so tests don't depend on any network or API key. A FakeLLM is provided
for the few tests that exercise the LLM path explicitly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services import Services
from app.services.flywheel import InMemoryFlywheel
from app.services.llm import LLMClient, NullLLM
from app.services.vectorstore import InMemoryVectorStore

FIXTURES = Path(__file__).parent / "fixtures"


class FakeGitHub:
    """Canned GitHub provenance; no network."""

    def __init__(self, evidence: dict[tuple[str, str], list[str]] | None = None) -> None:
        self._evidence = evidence or {}
        self.calls: list[tuple[str, str]] = []

    async def gather_repo_evidence(self, owner: str, repo: str) -> list[str]:
        self.calls.append((owner, repo))
        return self._evidence.get(
            (owner, repo),
            [f"Repo {owner}/{repo} exists: primary_language=Python, recent commits found."],
        )


class FakeLLM(LLMClient):
    """Scripted LLM: returns canned JSON/text keyed by a substring of the prompt."""

    def __init__(self, script: dict[str, str] | None = None, settings: Settings | None = None):
        super().__init__(settings or Settings())
        self.script = script or {}

    async def _araw(self, *, model: str, system: str, prompt: str, max_tokens: int) -> str:
        for needle, response in self.script.items():
            if needle in prompt or needle in system:
                return response
        return ""


@pytest.fixture
def settings() -> Settings:
    # Fresh defaults, independent of any local .env.
    return Settings(_env_file=None, openrouter_api_key="")


@pytest.fixture
def flywheel() -> InMemoryFlywheel:
    return InMemoryFlywheel()


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


def make_services(
    settings: Settings,
    *,
    llm: LLMClient | None = None,
    github: FakeGitHub | None = None,
    flywheel: InMemoryFlywheel | None = None,
) -> Services:
    return Services(
        settings=settings,
        llm=llm or NullLLM(settings),
        vectorstore=InMemoryVectorStore(),
        github=github or FakeGitHub(),
        flywheel=flywheel or InMemoryFlywheel(),
    )


@pytest.fixture
def services(settings, fake_github, flywheel) -> Services:
    return make_services(settings, github=fake_github, flywheel=flywheel)


@pytest.fixture
def genuine_resume() -> str:
    return (FIXTURES / "genuine_genai_resume.txt").read_text(encoding="utf-8")


@pytest.fixture
def fabricated_resume() -> str:
    return (FIXTURES / "fabricated_genai_resume.txt").read_text(encoding="utf-8")
