"""Comp intelligence service (S5.2) -- wires the pure engine to the ledger's
observed-offer read. Holds no tables; reads offers via LedgerStore. Advisory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.core.config import Settings, get_settings
from app.comp import bands
from app.comp.estimate import benchmark_comp, estimate_comp
from app.comp.schema import CompBandEstimate, CompBenchmark, RoleSignal
from app.ledger.store import LedgerStore, build_ledger_store
from app.matching.schema import JobRequisition


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompService:
    def __init__(self, ledger_store: LedgerStore, *, settings: Optional[Settings] = None) -> None:
        self._ledger = ledger_store
        self._settings = settings or get_settings()

    def estimate(
        self, signal: RoleSignal, *, org_id: str, as_of: Optional[datetime] = None
    ) -> CompBandEstimate:
        now = as_of or _utcnow()
        cell = bands.lookup_cell(signal, self._settings)
        points = self._ledger.observed_offers_for_comp(
            requesting_org_id=org_id, role_family=signal.role_family,
            seniority=signal.seniority.value, city_tier=signal.city_tier, at=now,
        )
        return estimate_comp(signal, cell, points, now=now, settings=self._settings)

    def benchmark(
        self, req: JobRequisition, *, org_id: str, as_of: Optional[datetime] = None
    ) -> CompBenchmark:
        signal = bands.role_signal_from_requisition(req, self._settings)
        est = self.estimate(signal, org_id=org_id, as_of=as_of)
        return benchmark_comp(est, req.comp_band, settings=self._settings)


def build_comp_service(settings: Optional[Settings] = None) -> CompService:
    settings = settings or get_settings()
    return CompService(build_ledger_store(settings), settings=settings)
