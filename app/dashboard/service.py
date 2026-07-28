"""Employer dashboard service (S5.3). Pure composition over JobStore +
CompService + LedgerStore. Owns no tables and holds no state; each method
assembles an existing, already-audited read into a render-ready contract.
The card catches ConsentError per section (LookupError propagates). Advisory."""

from __future__ import annotations

from typing import Optional

from app.comp.service import CompService, build_comp_service
from app.core.config import Settings, get_settings
from app.dashboard.schema import (
    CandidateCard, CodingRoundsSection, DashboardOverview, RecordsSection,
    ReputationSection, RequisitionBoard, RequisitionSummary, SectionStatus,
)
from app.ledger.store import ConsentError, LedgerStore, build_ledger_store
from app.matching.store import JobStore, build_job_store


class DashboardService:
    def __init__(
        self,
        jobs: JobStore,
        comp: CompService,
        ledger: LedgerStore,
        *,
        settings: Optional[Settings] = None,
    ) -> None:
        self._jobs = jobs
        self._comp = comp
        self._ledger = ledger
        self._settings = settings or get_settings()

    def overview(self, org_id: str) -> DashboardOverview:
        reqs = self._jobs.list_requisitions(org_id)
        by_status: dict[str, int] = {}
        summaries: list[RequisitionSummary] = []
        for r in reqs:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
            summaries.append(
                RequisitionSummary(
                    id=r.id,
                    title=r.title,
                    status=r.status,
                    must_have_skill_count=len(r.must_have_skills),
                    has_comp_band=r.comp_band is not None,
                    has_skill_coverage_gate=r.min_skill_coverage is not None,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
            )
        return DashboardOverview(
            total_requisitions=len(reqs),
            by_status=by_status,
            requisitions=tuple(summaries),
        )


def build_dashboard_service(settings: Optional[Settings] = None) -> DashboardService:
    settings = settings or get_settings()
    return DashboardService(
        build_job_store(settings),
        build_comp_service(settings),
        build_ledger_store(settings),
        settings=settings,
    )
