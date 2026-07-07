"""Service container — the dependency bundle nodes close over.

Node factories receive a :class:`Services` instance (never global singletons),
so tests inject fakes (FakeLLM, InMemoryVectorStore, InMemoryFlywheel) trivially.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.candidates.store import CandidateStore, build_candidate_store
from app.core.config import Settings, get_settings
from app.services.flywheel import Flywheel, build_flywheel
from app.services.github import GitHubClient, GitHubService
from app.services.llm import LLMClient, build_llm
from app.services.report_store import ReportStore, build_report_store
from app.services.vectorstore import VectorStore, build_vectorstore


@dataclass
class Services:
    settings: Settings
    llm: LLMClient
    vectorstore: VectorStore
    github: GitHubService
    flywheel: Flywheel
    report_store: ReportStore
    candidates: CandidateStore


def build_default_services(settings: Optional[Settings] = None) -> Services:
    settings = settings or get_settings()
    return Services(
        settings=settings,
        llm=build_llm(settings),
        vectorstore=build_vectorstore(settings),
        github=GitHubClient(settings),
        flywheel=build_flywheel(settings),
        report_store=build_report_store(settings),
        candidates=build_candidate_store(settings),
    )


__all__ = ["Services", "build_default_services"]
