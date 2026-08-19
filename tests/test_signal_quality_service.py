"""Orchestration and the three refusals (S9.1 Task 9, spec 5).

THIS IS WHERE THE SPRINT'S CLAIM LIVES. PI-9 was gated on real organisations
submitting outcomes, on the grounds that "a harness measuring test fixtures
would have been actively misleading". That is an argument against a harness
which emits a number no matter what it is fed -- so this one cannot.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.reports.store import SqlReportStore
from app.schemas.fabrication import FabricationRiskAssessment, FabricationRiskBand
from app.schemas.report import Report
from app.signal_quality.labels import OutcomesLabelSource
from app.signal_quality.schema import (
    LabelKind, RefusalReason, SignalMeasured, SignalRefused,
)
from app.signal_quality.service import measure
from tests.conftest import make_candidate_store


@pytest.fixture
def store():
    return SqlReportStore(make_candidate_store()._session_factory)


def _seed(store, score, band, positive, *, i=0):
    now = datetime.now(timezone.utc) + timedelta(seconds=i)
    rep = Report(
        domain="genai", created_at=now,
        fabrication_risk=FabricationRiskAssessment(score=score, band=band),
    )
    store.save(rep)
    store.add_outcome(OutcomeRecord(
        report_id=rep.id,
        outcome=(OutcomeLabel.VERIFIED_FABRICATED if positive
                 else OutcomeLabel.VERIFIED_GENUINE),
        recorded_by=OutcomeSource.ORGANIZATION,
        recorded_at=now + timedelta(days=1),
    ))


def _of(report, name):
    return next(s for s in report.signals if s.signal == name)


def test_below_the_threshold_every_signal_refuses(store):
    for i in range(4):
        _seed(store, 0.5, FabricationRiskBand.ELEVATED, i % 2 == 0, i=i)
    got = measure(OutcomesLabelSource(store), min_samples=30)
    assert all(isinstance(s, SignalRefused) for s in got.signals)
    assert _of(got, "fabrication_risk.score").reason is RefusalReason.INSUFFICIENT_SAMPLES
    assert _of(got, "fabrication_risk.score").n == 4


def test_a_refusal_carries_no_metric_fields_at_all(store):
    _seed(store, 0.5, FabricationRiskBand.ELEVATED, True)
    got = measure(OutcomesLabelSource(store), min_samples=30)
    dumped = _of(got, "fabrication_risk.score").model_dump()
    assert "auc" not in dumped and "brier" not in dumped and "curve" not in dumped


def test_the_threshold_releases_at_exactly_n(store):
    """n-1 refuses, n answers. A threshold nobody has seen release is a
    threshold nobody knows the direction of."""
    for i in range(5):
        _seed(store, 0.9 if i % 2 == 0 else 0.1,
              FabricationRiskBand.ELEVATED, i % 2 == 0, i=i)
    src = OutcomesLabelSource(store)
    assert isinstance(_of(measure(src, min_samples=6), "fabrication_risk.score"),
                      SignalRefused)
    assert isinstance(_of(measure(src, min_samples=5), "fabrication_risk.score"),
                      SignalMeasured)


def test_a_degenerate_class_refuses_rather_than_reporting_one_half(store):
    """0.5 is a REAL AUC meaning 'separates nothing'. Emitting it for an
    impossible measurement is the failure this refusal exists for."""
    for i in range(10):
        _seed(store, 0.5, FabricationRiskBand.ELEVATED, True, i=i)
    got = _of(measure(OutcomesLabelSource(store), min_samples=5),
              "fabrication_risk.score")
    assert isinstance(got, SignalRefused)
    assert got.reason is RefusalReason.DEGENERATE_CLASS


def test_hire_signals_refuse_against_a_fraud_source(store):
    """The load-bearing refusal: depth_score cannot be scored by a fraud
    label, and the harness says so instead of producing a plausible number."""
    for i in range(10):
        _seed(store, 0.9 if i % 2 else 0.1,
              FabricationRiskBand.ELEVATED, i % 2 == 0, i=i)
    got = measure(OutcomesLabelSource(store), min_samples=5)
    depth = _of(got, "depth_score")
    assert isinstance(depth, SignalRefused)
    assert depth.reason is RefusalReason.LABEL_KIND_MISMATCH
    assert isinstance(_of(got, "fabrication_risk.score"), SignalMeasured)


def test_the_kind_mismatch_refusal_beats_the_sample_floor(store):
    """Order matters in the message: a depth signal on a fraud source is not
    'nearly measurable, just short of samples' -- it is not measurable at all,
    and reporting INSUFFICIENT_SAMPLES would invite someone to go collect
    more."""
    got = measure(OutcomesLabelSource(store), min_samples=30)
    assert _of(got, "depth_score").reason is RefusalReason.LABEL_KIND_MISMATCH


def test_a_perfect_signal_measures_at_auc_one(store):
    for i in range(10):
        positive = i % 2 == 0
        _seed(store, 0.9 if positive else 0.1,
              FabricationRiskBand.ELEVATED, positive, i=i)
    got = _of(measure(OutcomesLabelSource(store), min_samples=5),
              "fabrication_risk.score")
    assert isinstance(got, SignalMeasured)
    assert got.auc == 1.0
    assert got.n == 10 and got.positives == 5


def test_the_population_is_always_reported(store):
    _seed(store, 0.5, FabricationRiskBand.ELEVATED, True)
    pop = measure(OutcomesLabelSource(store), min_samples=30).population
    assert pop.label_source == "outcomes"
    assert pop.label_kind is LabelKind.FRAUD
    assert pop.include_operator_labels is False
    assert pop.labels_usable == 1
    assert pop.earliest_report is not None and pop.latest_report is not None


def test_reports_missing_an_assessment_leave_that_signals_sample(store):
    """A None must not become a 0.0 and must not inflate n."""
    now = datetime.now(timezone.utc)
    rep = Report(domain="genai", created_at=now)          # no fabrication_risk
    store.save(rep)
    store.add_outcome(OutcomeRecord(
        report_id=rep.id, outcome=OutcomeLabel.VERIFIED_FABRICATED,
        recorded_by=OutcomeSource.ORGANIZATION, recorded_at=now + timedelta(days=1),
    ))
    for i in range(6):
        _seed(store, 0.9 if i % 2 else 0.1,
              FabricationRiskBand.ELEVATED, i % 2 == 0, i=i + 1)

    got = measure(OutcomesLabelSource(store), min_samples=5)
    assert _of(got, "fabrication_risk.score").n == 6      # not 7
    assert got.population.labels_usable == 7              # the population is honest


def test_every_registered_signal_appears_exactly_once(store):
    """A report that silently dropped a signal would read as 'we measured
    everything' while measuring eleven things."""
    from app.signal_quality.signals import SIGNALS
    got = measure(OutcomesLabelSource(store), min_samples=5)
    assert [s.signal for s in got.signals] == [s.name for s in SIGNALS]
