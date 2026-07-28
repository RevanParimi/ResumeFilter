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

    def board(self, org_id: str, req_id: str) -> Optional[RequisitionBoard]:
        req = self._jobs.get_requisition(org_id, req_id)
        if req is None:
            return None
        comp = self._comp.benchmark(req, org_id=org_id)
        match = self._jobs.run_match(
            org_id, req_id, as_of=None, limit=self._settings.dash_board_top_n
        )
        if match is None:  # req is owned, so run_match found it — defensive only
            return None
        return RequisitionBoard(requisition=req, comp=comp, match=match)

    def card(self, org_id: str, candidate_id: str) -> CandidateCard:
        # Section order matters only for the unknown-candidate case: the first
        # reused read raises LookupError, which we let propagate (-> 404). For a
        # known candidate each section is independently consent-gated + audited.
        return CandidateCard(
            candidate_id=candidate_id,
            reputation=self._reputation_section(org_id, candidate_id),
            coding_rounds=self._coding_rounds_section(org_id, candidate_id),
            records=self._records_section(org_id, candidate_id),
        )

    def _reputation_section(self, org_id: str, candidate_id: str) -> ReputationSection:
        try:
            rep = self._ledger.reputation_for_org(org_id=org_id, candidate_id=candidate_id)
        except ConsentError:
            return ReputationSection(status=SectionStatus.CONSENT_REQUIRED, data=None)
        status = (
            SectionStatus.NO_DATA if rep.total_observations == 0 else SectionStatus.AVAILABLE
        )
        return ReputationSection(status=status, data=rep)

    def _coding_rounds_section(self, org_id: str, candidate_id: str) -> CodingRoundsSection:
        try:
            rounds = self._ledger.query_coding_rounds_for_org(
                org_id=org_id, candidate_id=candidate_id
            )
        except ConsentError:
            return CodingRoundsSection(status=SectionStatus.CONSENT_REQUIRED, data=())
        status = SectionStatus.AVAILABLE if rounds else SectionStatus.NO_DATA
        return CodingRoundsSection(status=status, data=tuple(rounds))

    def _records_section(self, org_id: str, candidate_id: str) -> RecordsSection:
        try:
            records = self._ledger.query_records_for_org(
                org_id=org_id, candidate_id=candidate_id
            )
        except ConsentError:
            return RecordsSection(status=SectionStatus.CONSENT_REQUIRED, data=())
        status = SectionStatus.AVAILABLE if records else SectionStatus.NO_DATA
        return RecordsSection(status=status, data=tuple(records))


def build_dashboard_service(settings: Optional[Settings] = None) -> DashboardService:
    settings = settings or get_settings()
    return DashboardService(
        build_job_store(settings),
        build_comp_service(settings),
        build_ledger_store(settings),
        settings=settings,
    )
