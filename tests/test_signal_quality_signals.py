"""The twelve measured signals (S9.1 Task 8, spec 4.1).

A SIGNAL DECLARES ITS OWN METRIC SET. Computing four numbers for everything and
letting the reader work out which are nonsense puts a Brier score on an
unbounded count and an AUC on an ordinal cast to a float to make it fit. Both
look exactly like measurements.
"""

from __future__ import annotations

import pytest

from app.schemas.fabrication import (
    AIGenerationAssessment, AILikelihoodBand, CrossFieldAssessment,
    CrossFieldFinding, FabricationRiskAssessment, FabricationRiskBand,
    FindingSeverity,
)
from app.schemas.report import DepthBand, Report
from app.signal_quality.schema import LabelKind, MetricKind
from app.signal_quality.signals import SIGNALS, by_name


def test_all_twelve_signals_are_registered():
    assert len(SIGNALS) == 12
    names = {s.name for s in SIGNALS}
    assert {"fabrication_risk.score", "ai_generation.likelihood",
            "cross_field.major_findings", "depth_score"} <= names


def test_signal_names_are_unique():
    """by_name returns the FIRST match, so a duplicate would silently shadow."""
    names = [s.name for s in SIGNALS]
    assert len(names) == len(set(names))


def test_fraud_and_hire_signals_are_split_nine_and_three():
    fraud = [s for s in SIGNALS if s.kind is LabelKind.FRAUD]
    hire = [s for s in SIGNALS if s.kind is LabelKind.HIRE]
    assert (len(fraud), len(hire)) == (9, 3)


def test_a_band_gets_lift_and_never_brier():
    """Brier is undefined on anything not constrained to [0,1], and an ordinal
    encoded as a float would produce one anyway."""
    for spec in SIGNALS:
        if spec.band:
            assert spec.metrics == frozenset({MetricKind.LIFT}), spec.name


def test_only_bands_are_flagged_as_bands(): 
    """The `band` flag and the metric set must agree in BOTH directions --
    a numeric signal wrongly flagged would be routed to lift and never
    checked by the test above."""
    for spec in SIGNALS:
        assert spec.band == (spec.metrics == frozenset({MetricKind.LIFT})), spec.name


def test_an_unbounded_count_gets_auc_and_lift_but_never_brier():
    spec = by_name("cross_field.major_findings")
    assert MetricKind.BRIER not in spec.metrics
    assert {MetricKind.AUC, MetricKind.LIFT} <= spec.metrics


def test_extract_reads_the_score_off_the_report_body():
    rep = Report(
        depth_score=0.42,
        fabrication_risk=FabricationRiskAssessment(
            score=0.77, band=FabricationRiskBand.ELEVATED),
        ai_generation=AIGenerationAssessment(
            likelihood=0.31, band=AILikelihoodBand.POSSIBLE),
    )
    assert by_name("depth_score").extract(rep) == 0.42
    assert by_name("fabrication_risk.score").extract(rep) == 0.77
    assert by_name("ai_generation.likelihood").extract(rep) == 0.31
    assert by_name("fabrication_risk.band").extract(rep) == "elevated"


def test_extract_returns_none_when_the_assessment_is_absent():
    """Pre-S2.4 stored reports and ad-hoc runs carry None. Those rows drop out
    of THAT signal's sample and must not become a 0.0, which would read as a
    confident 'no risk'."""
    rep = Report(depth_score=0.5)
    assert rep.fabrication_risk is None
    assert by_name("fabrication_risk.score").extract(rep) is None
    assert by_name("fabrication_risk.band").extract(rep) is None
    assert by_name("resume_farm.score").extract(rep) is None
    assert by_name("cross_field.major_findings").extract(rep) is None
    assert by_name("depth_score").extract(rep) == 0.5


def test_depth_band_extracts_the_enum_value():
    rep = Report(depth_band=DepthBand.INSUFFICIENT_SIGNAL)
    assert by_name("depth_band").extract(rep) == "insufficient_signal"


def test_major_findings_counts_only_major_ones():
    rep = Report(cross_field=CrossFieldAssessment(
        score=0.4,
        findings=[
            CrossFieldFinding(id="f1", detail="a", score=0.5,
                              severity=FindingSeverity.MAJOR),
            CrossFieldFinding(id="f2", detail="b", score=0.5,
                              severity=FindingSeverity.MINOR),
            CrossFieldFinding(id="f3", detail="c", score=0.5,
                              severity=FindingSeverity.MAJOR),
        ],
    ))
    assert by_name("cross_field.major_findings").extract(rep) == 2.0


def test_an_assessment_with_no_findings_is_zero_not_none():
    """A report that WAS assessed and found nothing is a real 0, and it belongs
    in the sample -- unlike a report that was never assessed at all."""
    rep = Report(cross_field=CrossFieldAssessment(score=0.0, findings=[]))
    assert by_name("cross_field.major_findings").extract(rep) == 0.0


def test_by_name_refuses_an_unknown_signal():
    with pytest.raises(KeyError):
        by_name("nope.not.a.signal")
