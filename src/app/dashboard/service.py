"""Employer dashboard service (S5.3). Pure composition over JobStore +
CompService. Owns no tables and holds no state; the board assembles existing
reads into a render-ready contract. Advisory."""

from __future__ import annotations

from typing import Optional

from app.comp.service import CompService, build_comp_service
from app.core.config import Settings, get_settings
from app.dashboard.schema import RequisitionBoard
from app.ledger.store import LedgerStore, build_ledger_store
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


def build_dashboard_service(
    settings: Optional[Settings] = None, *, jobs: Optional[JobStore] = None,
    comp: Optional[CompService] = None, ledger: Optional[LedgerStore] = None,
) -> DashboardService:
    settings = settings or get_settings()
    if ledger is None and comp is not None:
        ledger = comp._ledger
    if jobs is None:
        jobs = build_job_store(settings, session_factory=ledger._session_factory if ledger is not None else None)
    if ledger is None:
        ledger = build_ledger_store(settings, session_factory=jobs._session_factory)
    return DashboardService(
        jobs,
        comp if comp is not None else build_comp_service(settings, ledger=ledger),
        ledger,
        settings=settings,
    )
