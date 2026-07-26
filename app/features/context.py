"""Assemble a FeatureContext from the live stores (PI-4 / S4.1).

The only part of app/features that touches stores. Assembles a point-in-time
snapshot: the profile is the newest extraction at/before ``as_of``
(``profile_as_of``, S4.2), and reports/interview records/coding rounds are cut at
their own ``created_at``/``interviewed_at``/``taken_at`` <= ``as_of``. Reputation
decays relative to ``as_of``. Consent policy is NOT applied here — this stays a
raw platform-internal assembler; the materializer (``materialize.py``) masks
consent-tagged features.
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

    profile = candidate_store.profile_as_of(candidate_id, moment)

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
