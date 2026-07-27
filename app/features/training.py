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
from app.features.training_schema import TrainingExample, TrainingLabel
from app.ledger.consent import as_utc
from app.ledger.schema import CodingRoundResult, InterviewOutcome, InterviewRecord

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
