"""Assemble a FeatureContext from the live stores (PI-4 / S4.1).

The only part of app/features that touches stores. Assembles the *current*
snapshot (``as_of = now``) with a coarse ``created_at <= as_of`` cutoff on
time-stamped rows. Full point-in-time correctness (versioned resumes/reports,
consent-validity-at-as_of) is S4.2's materialization job — this is the seam.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.candidates.store import CandidateStore
from app.features.schema import FeatureContext
from app.ledger.store import LedgerStore
from app.services.report_store import ReportStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_context(
    candidate_id: str,
    *,
    candidate_store: CandidateStore,
    report_store: ReportStore,
    ledger_store: LedgerStore,
    as_of: Optional[datetime] = None,
) -> Optional[FeatureContext]:
    if candidate_store.get_candidate(candidate_id) is None:
        return None
    moment = as_of or _utcnow()

    profile = candidate_store.latest_profile(candidate_id)

    reports = [r for r in report_store.for_candidate(candidate_id) if r.created_at <= moment]
    report = max(reports, key=lambda r: r.created_at) if reports else None

    records = tuple(
        r for r in ledger_store.records_for_candidate(candidate_id)
        if r.interviewed_at <= moment
    )
    coding = tuple(
        c for c in ledger_store.coding_rounds_for_candidate(candidate_id)
        if c.taken_at <= moment
    )

    return FeatureContext(
        candidate_id=candidate_id, as_of=moment,
        profile=profile, report=report,
        interview_records=records, coding_rounds=coding,
    )
