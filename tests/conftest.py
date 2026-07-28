"""Shared test fixtures — fully offline (NullLLM, in-memory stores, fake GitHub).

The genuine vs. fabricated assertions are driven by the DETERMINISTIC rule
registry, so tests don't depend on any network or API key. A FakeLLM is provided
for the few tests that exercise the LLM path explicitly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.ledger.models  # noqa: F401 — populate Base.metadata with ledger tables
import app.features.models  # noqa: F401 — populate Base.metadata with feature tables
import app.matching.models  # noqa: F401 — populate Base.metadata with matching tables
import app.profile_sources.models  # noqa: F401 — populate Base.metadata with profile-source table
from sqlalchemy import select as _select

from app.candidates.models import ExtractionRow as _ExtractionRow
from app.candidates.store import CandidateStore
from app.core.config import Settings
from app.core.db import Base, make_engine, make_session_factory
from app.features.store import FeatureStore
from app.ledger.store import LedgerStore
from app.services import Services
from app.services.flywheel import InMemoryFlywheel
from app.services.github import GitHubRepoRaw, GitHubUserRaw
from app.services.llm import LLMClient, NullLLM
from app.services.report_store import InMemoryReportStore
from app.services.vectorstore import InMemoryVectorStore

FIXTURES = Path(__file__).parent / "fixtures"


class FakeGitHub:
    """Canned GitHub provenance + user signals; no network."""

    def __init__(
        self,
        evidence: dict[tuple[str, str], list[str]] | None = None,
        user_signals: dict[str, GitHubUserRaw] | None = None,
    ) -> None:
        self._evidence = evidence or {}
        self._user_signals = user_signals or {}
        self.calls: list[tuple[str, str]] = []
        self.user_calls: list[str] = []

    async def gather_repo_evidence(self, owner: str, repo: str) -> list[str]:
        self.calls.append((owner, repo))
        return self._evidence.get(
            (owner, repo),
            [f"Repo {owner}/{repo} exists: primary_language=Python, recent commits found."],
        )

    async def gather_user_signal(self, login: str) -> GitHubUserRaw:
        self.user_calls.append(login)
        return self._user_signals.get(
            login,
            GitHubUserRaw(
                login=login, available=True, public_repos=1, followers=0,
                repos=[GitHubRepoRaw(name="demo", language="Python",
                                     languages={"Python": 10000}, stargazers_count=3,
                                     pushed_at="2025-01-01T00:00:00Z")],
            ),
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
def settings(monkeypatch) -> Settings:
    # Hermetic: bypass both .env and config.yaml so tests run on code defaults,
    # independent of any local config the developer may have changed.
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


@pytest.fixture
def flywheel() -> InMemoryFlywheel:
    return InMemoryFlywheel()


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


def make_candidate_store() -> CandidateStore:
    """In-memory candidate store for tests. create_all is a TEST convenience;
    real deployments migrate via Alembic (S1.2 decision)."""
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return CandidateStore(make_session_factory(engine))


def set_extraction_created_at(store, candidate_id, when):
    """Test util: pin every extraction row's created_at so point-in-time tests
    can control the profile axis (ingest itself stamps wall-clock now)."""
    with store._session_factory() as s:
        rows = s.execute(
            _select(_ExtractionRow).where(_ExtractionRow.candidate_id == candidate_id)
        ).scalars().all()
        for r in rows:
            r.created_at = when
        s.commit()


def make_services(
    settings: Settings,
    *,
    llm: LLMClient | None = None,
    github: FakeGitHub | None = None,
    flywheel: InMemoryFlywheel | None = None,
    candidates: CandidateStore | None = None,
    ledger: LedgerStore | None = None,
    features: FeatureStore | None = None,
    jobs=None,
    comp=None,
    dashboard=None,
) -> Services:
    candidates = candidates or make_candidate_store()
    ledger = ledger or LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        settings=settings,
    )
    features = features or FeatureStore(candidates._session_factory)
    if jobs is None:
        from app.matching.store import JobStore
        jobs = JobStore(
            candidates._session_factory,
            candidate_store=candidates, feature_store=features, settings=settings,
        )
    if comp is None:
        from app.comp.service import CompService
        comp = CompService(ledger, settings=settings)
    if dashboard is None:
        from app.dashboard.service import DashboardService
        dashboard = DashboardService(jobs, comp, ledger, settings=settings)
    return Services(
        settings=settings,
        llm=llm or NullLLM(settings),
        vectorstore=InMemoryVectorStore(),
        github=github or FakeGitHub(),
        flywheel=flywheel or InMemoryFlywheel(),
        report_store=InMemoryReportStore(),
        candidates=candidates,
        ledger=ledger,
        features=features,
        jobs=jobs,
        comp=comp,
        dashboard=dashboard,
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


@pytest.fixture
def ai_resume() -> str:
    return (FIXTURES / "ai_generated_genai_resume.txt").read_text(encoding="utf-8")


@pytest.fixture
def inconsistent_resume() -> str:
    return (FIXTURES / "inconsistent_genai_resume.txt").read_text(encoding="utf-8")


@pytest.fixture
def farm_resume_a() -> str:
    return (FIXTURES / "farm_genai_resume_a.txt").read_text(encoding="utf-8")


@pytest.fixture
def farm_resume_b() -> str:
    return (FIXTURES / "farm_genai_resume_b.txt").read_text(encoding="utf-8")
