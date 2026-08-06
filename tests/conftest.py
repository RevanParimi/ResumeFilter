"""Shared test fixtures — fully offline (NullLLM, in-memory stores, fake GitHub).

The genuine vs. fabricated assertions are driven by the DETERMINISTIC rule
registry, so tests don't depend on any network or API key. A FakeLLM is provided
for the few tests that exercise the LLM path explicitly.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, text

import app.ledger.models  # noqa: F401 — populate Base.metadata with ledger tables
import app.features.models  # noqa: F401 — populate Base.metadata with feature tables
import app.matching.models  # noqa: F401 — populate Base.metadata with matching tables
import app.profile_sources.models  # noqa: F401 — populate Base.metadata with profile-source table
import app.curation.models  # noqa: F401 — populate Base.metadata with the curation table
import app.verification.models  # noqa: F401 — populate Base.metadata with verification tables
import app.interview.models  # noqa: F401 — populate Base.metadata with interview tables
import app.reports.models  # noqa: F401 — populate Base.metadata with report tables
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
from app.reports.store import SqlReportStore
from app.services.email import build_email
from app.services.speech import NullSpeech, SpeechClient, Transcript
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


class FakeSpeech(SpeechClient):
    """Scripted ASR: returns canned text and records what it was handed.

    Opt-in per test -- the default fixture services use NullSpeech, so the suite
    proves the no-key path unless a test deliberately asks for audio."""

    def __init__(
        self,
        text: str = "I built the ingestion path myself and it held under load",
        settings: Settings | None = None,
        fail: Exception | None = None,
    ) -> None:
        super().__init__(settings or Settings(_env_file=None, openrouter_api_key=""))
        self.text = text
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def atranscribe(self, *, audio_b64: str, mime: str) -> Transcript:
        self.calls.append((audio_b64, mime))
        if self.fail is not None:
            raise self.fail
        return Transcript(text=self.text, duration_seconds=30.0, model="fake-asr")


#: The suite runs against a CONFIGURED admin key (S8.1). Before this, the whole
#: suite ran fail-open, so no test could tell "authorized" from "unguarded".
ADMIN_KEY = "test-admin-key"
ADMIN_HEADERS = {"X-API-Key": ADMIN_KEY}


@pytest.fixture
def settings(monkeypatch) -> Settings:
    # Hermetic: bypass both .env and config.yaml so tests run on code defaults,
    # independent of any local config the developer may have changed.
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(
        _env_file=None, openrouter_api_key="", api_auth_key=SecretStr(ADMIN_KEY)
    )


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return dict(ADMIN_HEADERS)


@pytest.fixture(autouse=True)
def _reset_curation_overlay():
    from app.candidates.normalize.skills import clear_curated_overlay
    clear_curated_overlay()
    yield
    clear_curated_overlay()


@pytest.fixture
def flywheel() -> InMemoryFlywheel:
    return InMemoryFlywheel()


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


def make_candidate_store() -> CandidateStore:
    """In-memory candidate store for tests. create_all is a TEST convenience;
    real deployments migrate via Alembic (S1.2 decision).

    DEE_TEST_DB_URL runs the SAME suite against Postgres (S8.1). Each store gets
    a throwaway schema, so tests stay as isolated as a fresh in-memory SQLite
    database makes them.
    """
    url = os.environ.get("DEE_TEST_DB_URL", "").strip()
    if not url:
        engine = make_engine("sqlite://")
    else:
        schema = f"s_{uuid.uuid4().hex[:8]}"
        bootstrap = create_engine(url)
        with bootstrap.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        bootstrap.dispose()
        engine = create_engine(
            url, pool_pre_ping=True,
            connect_args={"options": f"-csearch_path={schema}"},
        )
    Base.metadata.create_all(engine)
    return CandidateStore(make_session_factory(engine))


@pytest.fixture(scope="session", autouse=True)
def _drop_postgres_test_schemas():
    """Throwaway schemas are cheap to make and must not accumulate."""
    yield
    url = os.environ.get("DEE_TEST_DB_URL", "").strip()
    if not url:
        return
    engine = create_engine(url)
    with engine.begin() as conn:
        names = [
            n for (n,) in conn.execute(
                text(r"SELECT nspname FROM pg_namespace WHERE nspname LIKE 's\_%'")
            )
        ]
        for name in names:
            conn.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
    engine.dispose()


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
    profile_sources=None,
    curation=None,
    portal=None,
    verification=None,
    speech=None,
    interview=None,
    email=None,
    auth=None,
    screening_scope=None,
) -> Services:
    candidates = candidates or make_candidate_store()
    github = github or FakeGitHub()
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
    if curation is None:
        from app.curation.service import CurationService
        from app.curation.store import CurationStore
        curation = CurationService(
            store=CurationStore(candidates._session_factory), settings=settings
        )
    if profile_sources is None:
        from app.profile_sources.service import ProfileSourceService
        from app.profile_sources.store import ProfileSourceStore
        profile_sources = ProfileSourceService(
            github=github,
            store=ProfileSourceStore(candidates._session_factory),
            candidates=candidates, settings=settings, curation=curation,
        )
    report_store = SqlReportStore(candidates._session_factory)
    if verification is None:
        from app.verification.service import VerificationService
        from app.verification.store import VerificationStore
        verification = VerificationService(
            VerificationStore(candidates._session_factory, ledger=ledger, settings=settings),
            candidates, ledger, profile_sources=profile_sources, settings=settings,
        )
    # Default to the REFUSING speech client: the suite proves the no-key path
    # unless a test deliberately injects FakeSpeech.
    speech = speech or NullSpeech(settings)
    llm = llm or NullLLM(settings)
    if interview is None:
        from app.interview.service import InterviewService
        from app.interview.store import InterviewStore
        interview = InterviewService(
            InterviewStore(candidates._session_factory, ledger=ledger,
                           settings=settings),
            candidates, ledger, report_store,
            verification=verification, llm=llm, speech=speech, settings=settings,
        )
    # Honour settings.email_provider exactly as build_default_services does.
    # The default is "null", so the suite still proves the REFUSING path
    # (mirroring NullSpeech) -- but a test that configures capture gets
    # capture, instead of silently getting a client that refuses everything.
    email = email or build_email(settings)
    if auth is None:
        from app.auth.service import build_auth_service
        auth = build_auth_service(
            settings, candidates=candidates, ledger=ledger, email=email
        )
    # Built BEFORE the portal, which composes it for MyData.sessions and
    # for erasing login challenges (they carry no FK and cannot cascade).
    if portal is None:
        from app.portal.service import PortalService
        portal = PortalService(
            candidates, ledger, report_store, profile_sources,
            verification=verification, interview=interview, auth=auth,
            settings=settings,
        )
    if screening_scope is None:
        from app.screening.scope import build_org_scoped_reads
        screening_scope = build_org_scoped_reads(report_store, candidates)
    return Services(
        settings=settings,
        llm=llm,
        speech=speech,
        vectorstore=InMemoryVectorStore(),
        github=github,
        flywheel=flywheel or InMemoryFlywheel(),
        report_store=report_store,
        candidates=candidates,
        ledger=ledger,
        features=features,
        jobs=jobs,
        comp=comp,
        dashboard=dashboard,
        profile_sources=profile_sources,
        curation=curation,
        portal=portal,
        verification=verification,
        interview=interview,
        email=email,
        auth=auth,
        screening_scope=screening_scope,
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
