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
    from app.comp.service import CompService
    from app.curation.service import CurationService
    from app.dashboard.service import DashboardService
    from app.features.store import FeatureStore
    from app.matching.store import JobStore
    from app.portal.service import PortalService
    from app.profile_sources.service import ProfileSourceService


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
    comp: CompService
    dashboard: DashboardService
    profile_sources: ProfileSourceService
    curation: CurationService
    portal: PortalService


def build_default_services(settings: Optional[Settings] = None) -> Services:
    # Function-local import: at call time every module is fully loaded, so this
    # sidesteps the import cycle the top-level import would create.
    from app.comp.service import build_comp_service
    from app.curation.service import build_curation_service
    from app.dashboard.service import build_dashboard_service
    from app.features.store import build_feature_store
    from app.matching.store import build_job_store
    from app.portal.service import build_portal_service
    from app.profile_sources.service import build_profile_source_service

    settings = settings or get_settings()
    # Hoisted so the profile-source service shares the one GitHub client + the
    # candidate store (handle derivation + existence checks) with the container.
    github = GitHubClient(settings)
    candidates = build_candidate_store(settings)
    curation = build_curation_service(settings)
    curation.refresh_overlay()  # load prior curation into the normalize_skill overlay
    ledger = build_ledger_store(settings)
    report_store = build_report_store(settings)
    profile_sources = build_profile_source_service(
        settings, github=github, candidates=candidates, curation=curation
    )
    return Services(
        settings=settings,
        llm=build_llm(settings),
        vectorstore=build_vectorstore(settings),
        github=github,
        flywheel=build_flywheel(settings),
        report_store=report_store,
        candidates=candidates,
        ledger=ledger,
        features=build_feature_store(settings),
        jobs=build_job_store(settings),
        comp=build_comp_service(settings),
        dashboard=build_dashboard_service(settings),
        profile_sources=profile_sources,
        curation=curation,
        portal=build_portal_service(
            settings, candidates=candidates, ledger=ledger,
            report_store=report_store, profile_sources=profile_sources,
        ),
    )


__all__ = ["Services", "build_default_services"]
