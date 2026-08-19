"""The label seam (S9.1 Task 6, spec 4).

TWO GROUND TRUTHS EXIST AND THEY ARE NOT INTERCHANGEABLE. `OutcomeLabel` is a
FRAUD vocabulary, `InterviewOutcome` a HIRING one. Scoring `depth_score`
against VERIFIED_FABRICATED is not a weak measurement -- it is a category error
that still produces a plausible-looking AUC. So a source declares the kind it
emits and the service refuses a mismatch rather than computing it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.reports.store import SqlReportStore
from app.schemas.report import Report
from app.signal_quality.labels import LabeledReport, OutcomesLabelSource
from app.signal_quality.schema import LabelKind
from tests.conftest import make_candidate_store


@pytest.fixture
def store():
    return SqlReportStore(make_candidate_store()._session_factory)


def _saved(store, *, created_at=None) -> Report:
    rep = Report(domain="genai", created_at=created_at or datetime.now(timezone.utc))
    store.save(rep)
    return rep


def _judge(store, rep, label, *, source=OutcomeSource.ORGANIZATION, lag_days=1):
    store.add_outcome(OutcomeRecord(
        report_id=rep.id, outcome=label, recorded_by=source,
        recorded_at=rep.created_at + timedelta(days=lag_days),
    ))


def _judged(store, label, **kw) -> Report:
    rep = _saved(store)
    _judge(store, rep, label, **kw)
    return rep


def test_source_declares_the_fraud_kind(store):
    src = OutcomesLabelSource(store)
    assert src.kind is LabelKind.FRAUD
    assert src.name == "outcomes"


def test_fabricated_is_positive_and_genuine_is_negative(store):
    _judged(store, OutcomeLabel.VERIFIED_FABRICATED)
    _judged(store, OutcomeLabel.VERIFIED_GENUINE)
    labeled = OutcomesLabelSource(store).labeled()
    assert sorted(x.positive for x in labeled) == [False, True]
    assert all(isinstance(x, LabeledReport) for x in labeled)


def test_clarified_and_inconclusive_are_excluded_not_coerced(store):
    """Forcing these to 0 or 1 manufactures a judgment a human declined to
    give, and it would inflate n while doing it."""
    _judged(store, OutcomeLabel.CANDIDATE_CLARIFIED)
    _judged(store, OutcomeLabel.INCONCLUSIVE)
    assert OutcomesLabelSource(store).labeled() == []


def test_operator_labels_are_excluded_by_default(store):
    """PI-9 must never train on our own operator's self-labels believing a
    customer produced them; that is circular."""
    _judged(store, OutcomeLabel.VERIFIED_FABRICATED, source=OutcomeSource.OPERATOR)
    assert OutcomesLabelSource(store).labeled() == []
    assert len(OutcomesLabelSource(store, include_operator_labels=True).labeled()) == 1


def test_an_outcome_recorded_before_its_report_is_not_a_label(store):
    """Leakage. A judgment predating the prediction cannot have been informed
    by it, and a row that FED the prediction must never become its label."""
    _judged(store, OutcomeLabel.VERIFIED_FABRICATED, lag_days=-1)
    assert OutcomesLabelSource(store).labeled() == []


def test_an_outcome_exactly_on_as_of_is_excluded(store):
    """STRICTLY after, matching build_label's rule exactly."""
    _judged(store, OutcomeLabel.VERIFIED_FABRICATED, lag_days=0)
    assert OutcomesLabelSource(store).labeled() == []


def test_one_label_per_report_and_it_is_the_earliest(store):
    """A report can carry contradictory outcomes from different orgs. The
    earliest qualifying one wins: it is the judgment closest to the prediction,
    and it is the only rule under which recording a NEW outcome tomorrow does
    not silently change a measurement taken today."""
    rep = _saved(store)
    _judge(store, rep, OutcomeLabel.VERIFIED_GENUINE, lag_days=5)
    _judge(store, rep, OutcomeLabel.VERIFIED_FABRICATED, lag_days=1)

    labeled = OutcomesLabelSource(store).labeled()
    assert len(labeled) == 1
    assert labeled[0].positive is True  # the day-1 FABRICATED, not the day-5 GENUINE
    assert labeled[0].labeled_at == rep.created_at + timedelta(days=1)


def test_an_excluded_label_does_not_block_a_later_qualifying_one(store):
    """'Earliest' means earliest QUALIFYING -- an excluded row must not consume
    the report's one slot."""
    rep = _saved(store)
    _judge(store, rep, OutcomeLabel.INCONCLUSIVE, lag_days=1)
    _judge(store, rep, OutcomeLabel.VERIFIED_FABRICATED, lag_days=2)

    labeled = OutcomesLabelSource(store).labeled()
    assert len(labeled) == 1 and labeled[0].positive is True


def test_an_operator_row_does_not_consume_the_slot_either(store):
    """The same argument as the excluded-label case, one filter over: a report
    an operator judged first and a customer judged second is labelled by the
    CUSTOMER, not dropped."""
    rep = _saved(store)
    _judge(store, rep, OutcomeLabel.VERIFIED_GENUINE,
           source=OutcomeSource.OPERATOR, lag_days=1)
    _judge(store, rep, OutcomeLabel.VERIFIED_FABRICATED, lag_days=2)

    labeled = OutcomesLabelSource(store).labeled()
    assert len(labeled) == 1 and labeled[0].positive is True


def test_labels_carry_their_own_report(store):
    """The harness scores signals off the REPORT BODY, so the label has to hand
    back the artifact the human actually saw -- not just an id."""
    rep = _judged(store, OutcomeLabel.VERIFIED_FABRICATED)
    (labeled,) = OutcomesLabelSource(store).labeled()
    assert labeled.report.id == rep.id
    assert labeled.report.domain == "genai"
