"""The label seam (S9.1, spec 4).

TWO GROUND TRUTHS EXIST AND THEY ARE NOT INTERCHANGEABLE. ``OutcomeLabel`` is a
FRAUD vocabulary (verified_genuine / verified_fabricated / ...) and
``InterviewOutcome`` is a HIRING one (hired / offer / rejected / ...). Scoring
``depth_score`` against ``VERIFIED_FABRICATED`` is not a weak measurement -- it
is a category error that still produces a plausible-looking AUC. So a source
DECLARES the kind it emits, a signal declares the kind it can be scored by, and
``service.py`` refuses the mismatch rather than computing it.

``outcomes`` is the DEFAULT because it is what the fraud-screen wedge actually
collects. The ledger needs N organisations before it holds anything, and the
GTM keeps it off the pitch -- so a ledger-only harness would still be empty
after the launch PI-9 was gated on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from app.features.training import build_label
from app.ledger.consent import as_utc
from app.reports.schema import OutcomeLabel, OutcomeSource
from app.schemas.report import Report
from app.signal_quality.schema import LabelKind

#: CANDIDATE_CLARIFIED and INCONCLUSIVE appear in NEITHER set, deliberately.
#: Forcing them to 0 or 1 manufactures a judgment a human declined to give, and
#: it would inflate `n` while doing it. CANDIDATE_CLARIFIED may be the wedge's
#: most interesting label and it deserves its own analysis, not a coin flip.
_POSITIVE: frozenset[OutcomeLabel] = frozenset({OutcomeLabel.VERIFIED_FABRICATED})
_NEGATIVE: frozenset[OutcomeLabel] = frozenset({OutcomeLabel.VERIFIED_GENUINE})


@dataclass(frozen=True)
class LabeledReport:
    """One report and the single human judgment that scores it.

    Carries the REPORT, not a report id: every signal this harness measures is
    read off the report body, which is the artifact the human actually saw when
    they recorded the judgment.
    """

    report: Report
    positive: bool
    labeled_at: datetime


class LabelSource(Protocol):
    name: str
    kind: LabelKind

    def labeled(self) -> list[LabeledReport]: ...


def _binary(label: OutcomeLabel) -> Optional[bool]:
    """True / False / None, where None means "this row is not a label"."""
    if label in _POSITIVE:
        return True
    if label in _NEGATIVE:
        return False
    return None


class OutcomesLabelSource:
    """Human fraud judgments from the ``outcomes`` table.

    Reads through ``report_level_outcomes()``, which already drops per-claim
    rows and orders by ``(report_id, recorded_at, id)`` -- so "earliest wins"
    below is a first-survivor scan rather than a second sort with its own
    tie-breaking opinion.
    """

    name = "outcomes"
    kind = LabelKind.FRAUD

    def __init__(self, report_store, *, include_operator_labels: bool = False) -> None:
        self._store = report_store
        self.include_operator_labels = include_operator_labels

    def labeled(self) -> list[LabeledReport]:
        chosen: dict[str, LabeledReport] = {}
        for report, rec in self._store.report_level_outcomes():
            if (
                not self.include_operator_labels
                and rec.recorded_by is OutcomeSource.OPERATOR
            ):
                continue

            # LEAKAGE, the same rule build_label uses: STRICTLY after. A
            # judgment at or before the report's creation cannot have been
            # informed by it, and a row that FED the prediction must never
            # become its label.
            recorded_at, as_of = as_utc(rec.recorded_at), as_utc(report.created_at)
            if recorded_at <= as_of:
                continue

            positive = _binary(rec.outcome)
            if positive is None:
                continue

            # Earliest QUALIFYING wins -- so an excluded row (operator,
            # leaking, or a label we decline to binarise) never consumes the
            # report's one slot. It is also the only rule under which recording
            # a new outcome tomorrow cannot silently change a measurement taken
            # today.
            if report.id not in chosen:
                chosen[report.id] = LabeledReport(
                    report=report, positive=positive, labeled_at=recorded_at
                )
        return list(chosen.values())


class LedgerLabelSource:
    """Hiring outcomes from the PI-3 ledger, via S4.4's ``build_label``.

    ``build_label`` IS NOT EDITED BY THIS SPRINT. It is pure, consent-gated,
    audited and leakage-free, and already answers exactly the question this
    source needs; wrapping it keeps ONE implementation of the strict-after rule
    rather than a second that agrees today.

    Expected to return NOTHING until real organisations submit interview
    records. That is the honest day-one state and the reason every ``depth.*``
    signal refuses.

    CONSENT IS READ, NOT ASSUMED (ruling R1). The plan passed
    ``consent_allowed=True`` as a constant; that is a bypass, and this is the
    one place in PI-9 that touches consented data. The decision is taken at
    ``report.created_at`` rather than "now", because a grant that began after
    the report was written did not authorize reading that subject at the moment
    the prediction was made.

    One consent read per report, deliberately un-cached: the decision is
    time-scoped, so two reports on the same candidate at different moments can
    legitimately differ. ``materialization_consent`` also AUDITS each call,
    which is correct -- a consent check on a data principal is an auditable
    event even when the caller is a metrics job -- but it does mean the audit
    log grows with harness runs.
    """

    name = "ledger"
    kind = LabelKind.HIRE

    def __init__(self, report_store, ledger_store) -> None:
        self._reports = report_store
        self._ledger = ledger_store

    def labeled(self) -> list[LabeledReport]:
        out: list[LabeledReport] = []
        for report in self._reports.all_reports_with_candidates():
            cid = report.candidate_id
            if cid is None:
                continue
            decision = self._ledger.materialization_consent(cid, at=report.created_at)
            label = build_label(
                as_of=report.created_at,
                interview_records=self._ledger.records_for_candidate(cid),
                coding_rounds=self._ledger.coding_rounds_for_candidate(cid),
                consent_allowed=decision.allowed,
            )
            if not label.observed or label.withheld or label.event_at is None:
                continue
            out.append(LabeledReport(
                report=report, positive=bool(label.hired), labeled_at=label.event_at,
            ))
        return out
