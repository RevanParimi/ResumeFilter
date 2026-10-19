"""S4.4 — join feature vectors to leakage-free labels from ledger outcomes.

`build_label` is pure (no store, no clock — the risk.py/reputation.py pattern):
it filters a candidate's ledger to events STRICTLY after the vector's `as_of`
(`interviewed_at`/`taken_at` > as_of) and reduces them to a `TrainingLabel`.
`build_training_set` is the thin orchestrator that reads the ledger only for
consented vectors and audits each join. No leakage: a record at exactly `as_of`
fed the features and never becomes a label.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from app.features.materialize import MaterializedVector
from app.features.registry import FeatureRegistry
from app.features.serving import current_consent, mask_consent_vector
from app.features.training_schema import TrainingExample, TrainingLabel
from app.ledger.consent import as_utc
from app.ledger.schema import CodingRoundResult, InterviewOutcome, InterviewRecord
from app.ledger.store import TrainingCandidateMissingError

# Terminal-best ranking; WITHDRAWN is excluded entirely (non-signal, per S3.4).
_TERMINAL_ORDER: dict[InterviewOutcome, int] = {
    InterviewOutcome.HIRED: 5,
    InterviewOutcome.OFFER: 4,
    InterviewOutcome.ADVANCED: 3,
    InterviewOutcome.REJECTED: 2,
    InterviewOutcome.NO_SHOW: 1,
}
_HIRED_POSITIVE: set[InterviewOutcome] = {InterviewOutcome.HIRED, InterviewOutcome.OFFER}


def _withheld_label() -> TrainingLabel:
    return TrainingLabel(observed=False, withheld=True)


def build_label(
    *,
    as_of: datetime,
    interview_records: Iterable[InterviewRecord],
    coding_rounds: Iterable[CodingRoundResult],
    consent_allowed: bool,
) -> TrainingLabel:
    if not consent_allowed:
        return _withheld_label()

    cut = as_utc(as_of)

    # Best post-cut coding percentile (independent of interview observability).
    coding_pcts = [
        c.percentile
        for c in coding_rounds
        if as_utc(c.taken_at) > cut and c.percentile is not None
    ]
    coding_best = max(coding_pcts) if coding_pcts else None

    # Post-cut, non-withdrawn interview records (strict > cut = no leakage).
    post = [
        r
        for r in interview_records
        if as_utc(r.interviewed_at) > cut and r.outcome != InterviewOutcome.WITHDRAWN
    ]
    if not post:
        return TrainingLabel(
            observed=False, withheld=False, coding_best_percentile=coding_best
        )

    best_outcome = max(post, key=lambda r: _TERMINAL_ORDER[r.outcome]).outcome
    carriers = [r for r in post if r.outcome == best_outcome]
    event_at = min(as_utc(r.interviewed_at) for r in carriers)
    lag_days = (event_at - cut).total_seconds() / 86400.0

    return TrainingLabel(
        hired=best_outcome in _HIRED_POSITIVE,
        outcome=best_outcome.value,
        coding_best_percentile=coding_best,
        event_at=event_at,
        lag_days=lag_days,
        observed=True,
        withheld=False,
    )


def build_training_example(
    mv: MaterializedVector,
    *,
    interview_records: Iterable[InterviewRecord],
    coding_rounds: Iterable[CodingRoundResult],
    consent_allowed: bool,
    registry: FeatureRegistry,
) -> TrainingExample:
    """Pure assembly with an explicit boundary decision and historical ceiling.

    Store-backed callers must check present permission before reading outcomes.
    Neither a cached allowed flag nor this pure reducer authorizes a data read.
    """
    allowed = bool(mv.consent_state.get("allowed")) and consent_allowed
    label = build_label(
        as_of=mv.vector.as_of,
        interview_records=interview_records,
        coding_rounds=coding_rounds,
        consent_allowed=allowed,
    )
    vector = mask_consent_vector(mv.vector, registry=registry, allowed=allowed)
    return TrainingExample(vector=vector, label=label)


def current_training_example(
    example: TrainingExample, *, registry: FeatureRegistry, ledger_store,
    org_id: str | None = None,
) -> TrainingExample | None:
    """Revalidate assembled/cached labels without mutating or refilling them."""
    cid = example.vector.candidate_id
    allowed = current_consent(cid, ledger_store=ledger_store, org_id=org_id).allowed
    if not ledger_store.candidate_exists(cid):
        return None
    vector = mask_consent_vector(example.vector, registry=registry, allowed=allowed)
    return TrainingExample(vector=vector, label=example.label if allowed else _withheld_label())


def build_training_set(
    mvs: Iterable[MaterializedVector],
    *,
    ledger_store,
    registry: FeatureRegistry,
    org_id: str | None = None,
    audit: bool = True,
) -> list[TrainingExample]:
    """Join only with both historical and current ledger_read permission.

    Denied outcomes are never fetched; recheck after reads and for each final
    example. Audit each join's decision unless audit=False. Omit erased subjects
    even without auditing. Checks are snapshots, not locks across delivery.
    """
    out: list[TrainingExample] = []
    for mv in mvs:
        cid = mv.vector.candidate_id
        allowed = (current_consent(cid, ledger_store=ledger_store, org_id=org_id).allowed
                   and bool(mv.consent_state.get("allowed")))
        if allowed:
            irs = ledger_store.records_for_candidate(cid)
            crs = ledger_store.coding_rounds_for_candidate(cid)
        else:
            irs, crs = [], []
        # A revocation committed during the reads must invalidate their label.
        allowed = allowed and current_consent(
            cid, ledger_store=ledger_store, org_id=org_id,
        ).allowed
        if audit:
            try:
                ledger_store.audit_training_label(cid, allowed=allowed, as_of=mv.vector.as_of)
            except TrainingCandidateMissingError:
                continue
        out.append(build_training_example(mv, interview_records=irs, coding_rounds=crs,
                                         consent_allowed=allowed, registry=registry))
    # Auditing can be disabled, and an earlier subject can disappear while a
    # later one is built. Never turn a skipped audit into a stale export row.
    result = []
    for ex in out:
        checked = current_training_example(ex, registry=registry, ledger_store=ledger_store,
                                           org_id=org_id)
        if checked is not None:
            result.append(checked)
    return result
