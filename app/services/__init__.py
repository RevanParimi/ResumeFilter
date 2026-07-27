"""Service container — the dependency bundle nodes close over.

Node factories receive a :class:`Services` instance (never global singletons),
so tests inject fakes (FakeLLM, InMemoryVectorStore, InMemoryFlywheel) trivially.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from app.candidates.store import CandidateStore, build_candidate_store
from app.core.config import Settings, get_settings
from app.ledger.store import LedgerStore, build_ledger_store
from app.services.flywheel import Flywheel, build_flywheel
from app.services.github import GitHubClient, GitHubService
from app.services.llm import LLMClient, build_llm
from app.services.report_store import ReportStore, build_report_store
from app.services.vectorstore import VectorStore, build_vectorstore

if TYPE_CHECKING:  # avoid a features.store -> features.context -> services cycle
    from app.features.store import FeatureStore
    from app.matching.store import JobStore


@dataclass
class Services:
    settings: Settings
    llm: LLMClient
    vectorstore: VectorStore
    github: GitHubService
    flywheel: Flywheel
    report_store: ReportStore
    candidates: CandidateStore
    ledger: LedgerStore
    features: FeatureStore
    jobs: JobStore


def build_default_services(settings: Optional[Settings] = None) -> Services:
    # Function-local import: at call time every module is fully loaded, so this
    # sidesteps the import cycle the top-level import would create.
    from app.features.store import build_feature_store
    from app.matching.store import build_job_store

    settings = settings or get_settings()
    return Services(
        settings=settings,
        llm=build_llm(settings),
        vectorstore=build_vectorstore(settings),
        github=GitHubClient(settings),
        flywheel=build_flywheel(settings),
        report_store=build_report_store(settings),
        candidates=build_candidate_store(settings),
        ledger=build_ledger_store(settings),
        features=build_feature_store(settings),
        jobs=build_job_store(settings),
    )


__all__ = ["Services", "build_default_services"]
