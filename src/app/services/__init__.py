"""Service container — the dependency bundle nodes close over.

Node factories receive a :class:`Services` instance (never global singletons),
so tests inject fakes (FakeLLM, FakeGitHub, InMemoryFlywheel) trivially.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.candidates.store import CandidateStore, build_candidate_store
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import get_logger
from app.core.pdf_execution import PdfExecutor, PdfUnavailable
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

log = get_logger(__name__)


class ServiceCleanupError(RuntimeError):
    """Owned cleanup failed; provider/driver details stay out of the exception."""


def _cleanup_failed_build(close, resource: str) -> None:
    try:
        close()
    except Exception as exc:
        # Preserve the primary construction failure, without driver/provider text.
        log.warning("service_cleanup_failed", resource=resource, error_type=type(exc).__name__)

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
    from app.rights.service import RightsService
    from app.verification.service import VerificationService


@dataclass
class Services:
    settings: Settings
    llm: LLMClient
    speech: SpeechClient
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
    # The DPDP request queue (S8.3 Phase B). On the container rather than
    # inside the portal because BOTH planes reach it: the subject files and
    # reads, the operator lists and decides, and one service owning both keeps
    # the rules from being enforced at one door and forgotten at the other.
    rights: RightsService
    # Per-app, never a module global: a shared registry would be written by
    # every test in the suite and the first ordering-dependent assertion
    # would be an unreproducible flake (S8.3 Phase A).
    metrics: Metrics
    # One runtime factory shared by the stores and cross-store maintenance.
    # Default composition owns its engine; explicit injection borrows a factory.
    session_factory: sessionmaker
    _owned_engine: Optional[Engine] = field(default=None, repr=False, compare=False)
    _owned_clients: tuple[object, ...] = field(default=(), repr=False, compare=False)
    _close_task: Optional[asyncio.Task] = field(default=None, init=False, repr=False, compare=False)
    _pdf: Optional[PdfExecutor] = field(default=None, init=False, repr=False, compare=False)

    @property
    def pdf(self) -> PdfExecutor:
        # Accessed by async callers on the owning event loop; no resources are
        # allocated for services that never accept PDF input.
        if self._close_task is not None:
            raise PdfUnavailable('pdf_executor_closed')
        if self._pdf is None:
            self._pdf = PdfExecutor(self.settings.pdf_max_concurrent_parses)
        return self._pdf

    def dispose_sql(self) -> None:
        """Release only the SQL engine this bundle constructed, once.

        Injected factories/bundles remain their caller's responsibility.
        Provider-client lifecycle is separate from SQL ownership.
        """
        engine, self._owned_engine = self._owned_engine, None
        if engine is not None:
            engine.dispose()

    async def _close_owned(self) -> None:
        clients, self._owned_clients = self._owned_clients, ()
        failed = False
        if self._pdf is not None:
            await self._pdf.aclose()
        try:
            self.dispose_sql()
        except Exception as exc:
            failed = True
            log.warning("service_cleanup_failed", resource="sql", error_type=type(exc).__name__)

        async def close(client):
            nonlocal failed
            try:
                aclose = getattr(client, "aclose", None)
                if aclose:
                    await aclose()
                elif getattr(client, "close", None):
                    await asyncio.to_thread(client.close)
            except (Exception, asyncio.CancelledError) as exc:
                failed = True
                log.warning("service_cleanup_failed", resource=type(client).__name__, error_type=type(exc).__name__)

        # Closers have no cross-provider dependencies. One slow/failing provider
        # cannot prevent the other clients or the SQL pool from being released.
        unique = {id(client): client for client in clients}
        await asyncio.gather(*(close(client) for client in unique.values()))
        if failed:
            raise ServiceCleanupError("owned service cleanup failed") from None

    async def aclose(self) -> None:
        """Finish owned cleanup once, even if a waiting caller is canceled."""
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close_owned())
        cancelled = False
        while True:
            try:
                await asyncio.shield(self._close_task)
                break
            except asyncio.CancelledError:
                if self._close_task.cancelled():
                    raise
                cancelled = True
            except Exception:
                if cancelled:
                    raise asyncio.CancelledError() from None
                raise
        if cancelled:
            raise asyncio.CancelledError()


def build_default_services(
    settings: Optional[Settings] = None, *, session_factory: Optional[sessionmaker] = None,
    github: Optional[GitHubService] = None, llm: Optional[LLMClient] = None,
    speech: Optional[SpeechClient] = None,
) -> Services:
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
    from app.ratelimit.service import build_rate_limiter
    from app.rights.service import build_rights_service
    from app.rights.store import build_rights_store
    from app.verification.service import build_verification_service

    settings = settings or get_settings()
    # One runtime pool per app; explicit factories are borrowed. No URL-global
    # cache: separately configured apps must keep independent data/ownership.
    with ExitStack() as cleanup:
        owned_clients = []
        owned_engine = None
        if session_factory is None:
            owned_engine = make_engine(settings.candidates_db_url)
            cleanup.callback(_cleanup_failed_build, owned_engine.dispose, "sql")
            session_factory = make_session_factory(owned_engine)
        # FIRST: every limiter built below takes it, so that a rate-limit decision
        # is countable from the moment the first one is made.
        metrics = build_metrics()
        # Hoisted so the profile-source service shares the one GitHub client + the
        # candidate store (handle derivation + existence checks) with the container.
        candidates = build_candidate_store(settings, session_factory=session_factory)
        curation = build_curation_service(settings, session_factory=session_factory)
        curation.purge_expired()  # physical cleanup; fail startup if maintenance fails
        curation.refresh_overlay()  # load prior curation into the normalize_skill overlay
        # Providers allocate HTTP/SDK transports only on first use. Failed
        # synchronous composition therefore has no asynchronous transport to close.
        if github is None:
            github = GitHubClient(settings)
            owned_clients.append(github)
        ledger = build_ledger_store(settings, session_factory=session_factory)
        report_store = build_report_store(settings, session_factory=session_factory)
        features = build_feature_store(settings, session_factory=session_factory)
        jobs = build_job_store(settings, candidates=candidates, features=features, session_factory=session_factory)
        comp = build_comp_service(settings, ledger=ledger)
        profile_sources = build_profile_source_service(
            settings, github=github, candidates=candidates, curation=curation
        )
        # Built AFTER profile_sources (whose canonical employers corroborate a
        # submitted document) and BEFORE the portal (whose my_data view reads
        # identity assurance and claim evidence).
        email = build_email(settings)
        verification = build_verification_service(
            settings, candidates=candidates, ledger=ledger,
            profile_sources=profile_sources, email=email,
        )
        # Built AFTER verification (whose assurance number is the proxy hook) and
        # BEFORE the portal (whose my_data view lists interview summaries).
        if llm is None:
            llm = build_llm(settings)
            owned_clients.append(llm)
        if speech is None:
            speech = build_speech(settings)
            owned_clients.append(speech)
        interview = build_interview_service(
            settings, candidates=candidates, ledger=ledger, report_store=report_store,
            verification=verification, llm=llm, speech=speech, metrics=metrics,
        )
        # Auth is built LAST among the stateful services: it resolves every plane's
        # principal, so it needs candidates + ledger already standing.
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
        # metrics=metrics is NOT optional here. Phase A's headline finding was a
        # builder that passed it to two limiters and not the third, so one rule was
        # enforced perfectly and counted nowhere; tests/test_ratelimit_wiring.py
        # builds this container and asserts every limiter shares its metrics.
        rights = build_rights_service(
            settings,
            store=build_rights_store(settings, candidates._session_factory),
            candidates=candidates,
            ledger=ledger,
            limiter=build_rate_limiter(
                settings, candidates._session_factory, metrics=metrics
            ),
        )
        bundle = Services(
            settings=settings,
            llm=llm,
            speech=speech,
            github=github,
            flywheel=build_flywheel(settings),
            report_store=report_store,
            candidates=candidates,
            ledger=ledger,
            features=features,
            jobs=jobs,
            comp=comp,
            dashboard=build_dashboard_service(settings, jobs=jobs, comp=comp, ledger=ledger),
            profile_sources=profile_sources,
            curation=curation,
            portal=build_portal_service(
                settings, candidates=candidates, ledger=ledger,
                report_store=report_store, profile_sources=profile_sources,
                verification=verification, interview=interview, auth=auth,
                rights=rights,
            ),
            verification=verification,
            interview=interview,
            email=email,
            auth=auth,
            screening_scope=build_org_scoped_access(report_store, candidates),
            screening=screening,
            rights=rights,
            metrics=metrics,
            session_factory=session_factory,
            _owned_engine=owned_engine,
            _owned_clients=tuple(owned_clients),
        )
        cleanup.pop_all()  # Ownership transfers only after full composition.
        return bundle


__all__ = ["Services", "ServiceCleanupError", "build_default_services"]
