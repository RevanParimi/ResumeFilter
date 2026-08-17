"""Screening batches: the pure types (S8.4 Phase B).

No I/O, no session, no clock beyond what a caller hands in. Everything here is
either a wire shape or a pure function over one.

The rule this module exists to enforce is DPDP, not tidiness: ``ItemSignals``
holds SCALARS ONLY. ``batch_items.candidate_id`` is ``ON DELETE SET NULL`` --
deliberately, so that a candidate erasing themselves does not silently rewrite
an organisation's record of how many resumes it screened -- which means
anything stored beside it OUTLIVES the person it describes. A band and a score
attached to a null candidate are not personal data. A copied reasoning string
that quotes claim text would be, and it would be exactly the orphan S8.1's fold
of the report store existed to make impossible.

So the one-line reason the queue shows is COMPOSED from the scalars at read
time (``compose_reason``), never copied. The full reasoning stays in the
``Report``, which CASCADEs from its candidate.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field

from app.candidates.store import MatchedOn
from app.schemas.fabrication import DuplicationBand, FabricationRiskBand
from app.schemas.report import DepthBand, Report


class ItemStatus(StrEnum):
    """Stored on the item. Contrast BatchStatus, which is derived."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class BatchStatus(StrEnum):
    """DERIVED at read time from the item counts (spec §4.4), never stored."""

    EMPTY = "empty"
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    PARTIAL = "partial"  # nothing left to do, but something failed


class ItemSignals(BaseModel):
    """Closed facts about ONE finished evaluation. Scalars only -- see module docstring.

    Storing these is consistent with the derived-status rule rather than an
    exception to it (S7.3 drew the line): a fact that depends on the clock or on
    later rows must be derived, and a finished evaluation's score depends on
    neither. ``matched_existing`` is not even recomputable -- it is a fact about
    the moment of ingest.
    """

    risk_band: FabricationRiskBand = FabricationRiskBand.INSUFFICIENT_DATA
    risk_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    depth_band: DepthBand = DepthBand.INSUFFICIENT_SIGNAL
    depth_score: float = Field(default=0.0, ge=0.0, le=1.0)
    #: One of the three fixed component ids, never free text.
    loudest_signal: Optional[str] = None
    loudest_band: Optional[str] = None
    n_components: int = 0
    farm_band: DuplicationBand = DuplicationBand.INSUFFICIENT_DATA
    farm_score: float = Field(default=0.0, ge=0.0, le=1.0)
    #: A COUNT of fingerprinted resumes compared against -- never their ids.
    farm_corpus_size: int = 0
    matched_existing: bool = False
    matched_on: Optional[MatchedOn] = None
    duplicate_resume: bool = False
    flagged_claims: int = 0


def signals_from_report(
    report: Report,
    *,
    matched_existing: bool,
    matched_on: Optional[MatchedOn],
    duplicate_resume: bool,
) -> ItemSignals:
    """Stamp the closed facts of a finished evaluation onto an item.

    Deliberately drops ``fabrication_risk.reasoning``, every ``verdict``, and
    ``resume_farm.matches[]``. The first is prose about a person; the last is
    the counterparty identity Phase A's projection exists to strip -- and not
    holding it is a stronger guarantee than redacting it.
    """
    fab = report.fabrication_risk
    farm = report.resume_farm

    loudest = None
    if fab is not None and fab.components:
        # Heaviest wins; ties broken by risk then id so two identical reports
        # never render a different "loudest".
        loudest = sorted(
            fab.components, key=lambda c: (-c.weight, -c.risk, c.id)
        )[0]

    return ItemSignals(
        risk_band=fab.band if fab is not None else FabricationRiskBand.INSUFFICIENT_DATA,
        risk_confidence=fab.confidence if fab is not None else 0.0,
        depth_band=report.depth_band,
        depth_score=report.depth_score,
        loudest_signal=loudest.id if loudest is not None else None,
        loudest_band=loudest.band if loudest is not None else None,
        n_components=len(fab.components) if fab is not None else 0,
        farm_band=farm.band if farm is not None else DuplicationBand.INSUFFICIENT_DATA,
        farm_score=farm.score if farm is not None else 0.0,
        farm_corpus_size=farm.corpus_size if farm is not None else 0,
        matched_existing=matched_existing,
        matched_on=matched_on,
        duplicate_resume=duplicate_resume,
        flagged_claims=len(report.flagged_claim_ids),
    )


_SIGNAL_LABELS = {
    "ai_generation": "AI-generation signals",
    "cross_field": "cross-field inconsistency",
    "resume_farm": "resume farm / near-duplicate",
}


def compose_reason(
    signals: Optional[ItemSignals], status: ItemStatus, error: Optional[str]
) -> str:
    """The queue's one-line reason, GENERATED from scalars (module docstring).

    Never asserts more than the numbers support: an ``insufficient_data`` band
    says so plainly rather than being rendered as a low risk, because
    "we could not say" and "we looked and it is fine" are different answers
    (UI.md §1).
    """
    if status is ItemStatus.PENDING:
        return "not screened yet"
    if status is ItemStatus.PROCESSING:
        return "screening in progress"
    if status is ItemStatus.FAILED:
        return f"could not be screened: {error or 'unknown_error'}"
    if signals is None:
        return "screened, but the stored signals could not be read"

    if signals.risk_band is FabricationRiskBand.INSUFFICIENT_DATA:
        return "insufficient signal to assess fabrication risk"

    label = _SIGNAL_LABELS.get(signals.loudest_signal or "", "no single dominant signal")
    tail = (
        f"{label} is the loudest of {signals.n_components}"
        if signals.loudest_signal
        else label
    )
    return (
        f"{signals.risk_band.value} fabrication risk — {tail}; "
        f"confidence {signals.risk_confidence:.2f}"
    )


class BatchCounts(BaseModel):
    """Item counts by status. The stale-``processing`` reinterpretation has
    already been applied by the store, so ``processing`` here means genuinely
    in flight."""

    pending: int = 0
    processing: int = 0
    done: int = 0
    failed: int = 0

    @property
    def total(self) -> int:
        return self.pending + self.processing + self.done + self.failed


def derive_status(counts: BatchCounts) -> BatchStatus:
    """Spec §4.4: a batch's status is a READ over its items, never a column.

    ``processing`` is tested BEFORE ``pending``: an item genuinely in flight is
    the more informative fact, and ``pending`` is reserved for "registered, but
    nothing has started". A batch that reported `pending` while a call was
    actively screening it would make the UI's poll look like a stall.
    """
    if counts.total == 0:
        return BatchStatus.EMPTY
    if counts.processing:
        return BatchStatus.PROCESSING
    if counts.pending:
        return BatchStatus.PENDING
    return BatchStatus.PARTIAL if counts.failed else BatchStatus.COMPLETE


class BatchView(BaseModel):
    """A batch in a list."""

    id: str
    name: str = ""
    domain: str
    created_at: datetime
    created_by_org_user_id: Optional[str] = None
    counts: BatchCounts = Field(default_factory=BatchCounts)
    status: BatchStatus = BatchStatus.EMPTY


class BatchDetail(BatchView):
    """Identical today; a distinct type so the detail read can grow fields the
    list must not pay for."""


class QueueRow(BaseModel):
    """One resume in the fraud-screen queue.

    Every field comes from this item's own row (design §2.3). No Report is on
    this path, which is why there is nothing here to redact.
    """

    item_id: str
    status: ItemStatus
    created_at: datetime
    processed_at: Optional[datetime] = None
    candidate_id: Optional[str] = None
    resume_id: Optional[str] = None
    report_id: Optional[str] = None
    risk_score: Optional[float] = None
    signals: Optional[ItemSignals] = None
    reason: str = ""
    error: Optional[str] = None
    advisory: bool = True
    human_review_required: bool = True


class QueuePage(BaseModel):
    rows: list[QueueRow] = Field(default_factory=list)
    next_cursor: Optional[str] = None


class BatchPage(BaseModel):
    batches: list[BatchView] = Field(default_factory=list)
    next_cursor: Optional[str] = None


class SignalCount(BaseModel):
    signal: str
    count: int


class BatchSummary(BaseModel):
    """UI.md screen C -- the screenshot-able roll-up.

    Counts and enum members only: a summary that quoted its riskiest row would
    re-open every question the FIELD table answers (design §2.4).
    """

    batch_id: str
    name: str = ""
    domain: str
    status: BatchStatus
    counts: BatchCounts
    n_screened: int = 0
    by_risk_band: dict[str, int] = Field(default_factory=dict)
    top_signals: list[SignalCount] = Field(default_factory=list)
    advisory: bool = True
    human_review_required: bool = True


class ProcessResult(BaseModel):
    """What one bounded `process` call did."""

    batch_id: str
    processed: int = 0
    failed: int = 0
    remaining: int = 0
    status: BatchStatus = BatchStatus.EMPTY


class RetryResult(BaseModel):
    """What one `retry` call re-queued (S8.3 Phase A).

    `skipped` is not padding. An item whose ``raw_text`` is gone cannot be
    retried -- it either succeeded (text cleared on success) or failed as
    ``empty_resume`` and would fail identically -- and reporting it as requeued
    would be a promise the next ``process`` call breaks.
    """

    batch_id: str
    requeued: int = 0
    skipped: int = 0
