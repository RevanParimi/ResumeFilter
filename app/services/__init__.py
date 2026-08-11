"""Service container — the dependency bundle nodes close over.

Node factories receive a :class:`Services` instance (never global singletons),
so tests inject fakes (FakeLLM, InMemoryVectorStore, InMemoryFlywheel) trivially.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import sessionmaker

from app.candidates.store import CandidateStore, build_candidate_store
from app.core.config import Settings, get_settings
from app.ledger.store import LedgerStore, build_ledger_store
from app.metrics.registry import Metrics, build_metrics
from app.services.flywheel import Flywheel, build_flywheel
from app.services.github import GitHubClient, GitHubService
from app.services.email import EmailClient, build_email
from app.services.llm import LLMClient, build_llm
from app.reports.store import ReportStore, build_report_store
from app.screening.ingest import IngestDeps
from app.screening.scope import OrgScopedAccess, build_org_scoped_access
from app.screening.service import ScreeningService, build_screening_service
from app.services.speech import SpeechClient, build_speech
from app.services.vectorstore import VectorStore, build_vectorstore

if TYPE_CHECKING:  # avoid a features.store -> features.context -> services cycle
    from app.auth.service import AuthService
    from app.comp.service import CompService
    from app.curation.service import CurationService
    from app.dashboard.service import DashboardService
    from app.features.store import FeatureStore
    from app.interview.service import InterviewService
    from app.matching.store import JobStore
    from app.portal.service import PortalService
    from app.profile_sources.service import ProfileSourceService
    from app.verification.service import VerificationService


@dataclass
class Services:
    settings: Settings
    llm: LLMClient
    speech: SpeechClient
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
    verification: VerificationService
    interview: InterviewService
    email: EmailClient
    auth: AuthService
    screening_scope: OrgScopedAccess
    # The batch STORE is deliberately absent: no handler should be able to
    # reach an unscoped batch read, and what is not on the container cannot be
    # reached from a handler.
    screening: ScreeningService
    # Per-app, never a module global: a shared registry would be written by
    # every test in the suite and the first ordering-dependent assertion
    # would be an unreproducible flake (S8.3 Phase A).
    metrics: Metrics
    # THE database, named. Every store in the repo builds its engine from
    # `candidates_db_url` (measured S8.3 Phase B), so this is not a new engine
    # -- it is the candidate store's own factory given a name. The retention
    # sweep needs a session factory rather than a store, because it operates
    # across eleven data classes owned by seven different stores, and a handler
    # reaching into `some_store._session_factory` would be reading a private
    # to say something the container can say plainly.
    session_factory: sessionmaker


def build_default_services(settings: Optional[Settings] = None) -> Services:
    # Function-local import: at call time every module is fully loaded, so this
    # sidesteps the import cycle the top-level import would create.
    from app.auth.service import build_auth_service
    from app.comp.service import build_comp_service
    from app.curation.service import build_curation_service
    from app.dashboard.service import build_dashboard_service
    from app.features.store import build_feature_store
    from app.interview.service import build_interview_service
    from app.matching.store import build_job_store
    from app.portal.service import build_portal_service
    from app.profile_sources.service import build_profile_source_service
    from app.verification.service import build_verification_service

    settings = settings or get_settings()
    # FIRST: every limiter built below takes it, so that a rate-limit decision
    # is countable from the moment the first one is made.
    metrics = build_metrics()
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
    # Built AFTER profile_sources (whose canonical employers corroborate a
    # submitted document) and BEFORE the portal (whose my_data view reads
    # identity assurance and claim evidence).
    verification = build_verification_service(
        settings, candidates=candidates, ledger=ledger,
        profile_sources=profile_sources,
    )
    # Built AFTER verification (whose assurance number is the proxy hook) and
    # BEFORE the portal (whose my_data view lists interview summaries).
    llm = build_llm(settings)
    speech = build_speech(settings)
    interview = build_interview_service(
        settings, candidates=candidates, ledger=ledger, report_store=report_store,
        verification=verification, llm=llm, speech=speech, metrics=metrics,
    )
    # Auth is built LAST among the stateful services: it resolves every plane's
    # principal, so it needs candidates + ledger already standing.
    email = build_email(settings)
    auth = build_auth_service(
        settings, candidates=candidates, ledger=ledger, email=email, metrics=metrics
    )
    # Late, and only after candidates/report_store/llm are bound: those four
    # objects are everything ingestion needs (app/screening/ingest.py).
    screening = build_screening_service(
        settings,
        deps=IngestDeps(
            candidates=candidates, reports=report_store, llm=llm, settings=settings
        ),
        metrics=metrics,
    )
    return Services(
        settings=settings,
        llm=llm,
        speech=speech,
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
            verification=verification, interview=interview, auth=auth,
        ),
        verification=verification,
        interview=interview,
        email=email,
        auth=auth,
        screening_scope=build_org_scoped_access(report_store, candidates),
        screening=screening,
        metrics=metrics,
        session_factory=candidates._session_factory,
    )


__all__ = ["Services", "build_default_services"]
