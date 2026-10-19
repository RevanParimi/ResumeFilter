"""Fabrication schema regressions, grouped by behavior."""

import pytest
from pydantic import ValidationError
from app.schemas.fabrication import (
    AIGenerationAssessment,
    AILikelihoodBand,
    AISignal,
    SignalSource,
    ConsistencyBand,
    CrossFieldAssessment,
    CrossFieldFinding,
    FindingSeverity,
    FabricationRiskAssessment,
    FabricationRiskBand,
    RiskComponent,
    DuplicationBand,
    ResumeFarmAssessment,
    ResumeMatch,
)


# Fabrication schema

def test_defaults_are_conservative():
    a = AIGenerationAssessment()
    assert a.band is AILikelihoodBand.INSUFFICIENT_TEXT
    assert a.likelihood == 0.0
    assert a.confidence == 0.0
    assert a.signals == []
    assert a.advisory is True  # hard mandate, mirrors Report


def test_signal_score_bounds_enforced():
    with pytest.raises(ValidationError):
        AISignal(id="x", detail="d", score=1.5)
    with pytest.raises(ValidationError):
        AIGenerationAssessment(likelihood=-0.1)


def test_signal_defaults_to_deterministic_source():
    s = AISignal(id="template_phrases", detail="d", score=0.9)
    assert s.source is SignalSource.DETERMINISTIC


def test_round_trips_through_json():
    a = AIGenerationAssessment(
        likelihood=0.7,
        confidence=0.8,
        band=AILikelihoodBand.LIKELY,
        signals=[AISignal(id="llm_indicator", detail="d", score=0.5, source=SignalSource.LLM)],
        reasoning="r",
    )
    again = AIGenerationAssessment.model_validate_json(a.model_dump_json())
    assert again == a


# Cross field schema

def test_cross_field_schema_defaults_are_conservative():
    a = CrossFieldAssessment()
    assert a.band is ConsistencyBand.INSUFFICIENT_DATA
    assert a.score == 0.0
    assert a.confidence == 0.0
    assert a.findings == []
    assert a.advisory is True  # hard mandate, mirrors Report


def test_finding_defaults_to_minor():
    f = CrossFieldFinding(id="timeline_gap", detail="d", score=0.3)
    assert f.severity is FindingSeverity.MINOR
    assert f.entry_ids == []


def test_score_bounds_enforced():
    with pytest.raises(ValidationError):
        CrossFieldFinding(id="x", detail="d", score=1.5)
    with pytest.raises(ValidationError):
        CrossFieldAssessment(confidence=-0.1)


def test_cross_field_schema_round_trips_through_json():
    a = CrossFieldAssessment(
        score=0.6,
        confidence=0.9,
        band=ConsistencyBand.MAJOR_ISSUES,
        findings=[
            CrossFieldFinding(
                id="timeline_overlap",
                detail="d",
                severity=FindingSeverity.MAJOR,
                score=0.8,
                entry_ids=["exp_1", "exp_2"],
            )
        ],
        reasoning="r",
    )
    again = CrossFieldAssessment.model_validate_json(a.model_dump_json())
    assert again == a


# Fabrication risk schema

def test_band_values():
    assert FabricationRiskBand.INSUFFICIENT_DATA == "insufficient_data"
    assert FabricationRiskBand.LOW == "low"
    assert FabricationRiskBand.MODERATE == "moderate"
    assert FabricationRiskBand.ELEVATED == "elevated"


def test_component_bounds():
    c = RiskComponent(id="resume_farm", band="near_duplicate", risk=0.8, confidence=0.7, weight=0.7)
    assert c.flagged is False  # default
    with pytest.raises(ValidationError):
        RiskComponent(id="x", band="b", risk=1.2, confidence=0.5, weight=0.5)
    with pytest.raises(ValidationError):
        RiskComponent(id="x", band="b", risk=0.5, confidence=0.5, weight=-0.1)


def test_assessment_defaults_are_conservative():
    a = FabricationRiskAssessment()
    assert a.band is FabricationRiskBand.INSUFFICIENT_DATA
    assert a.score == 0.0 and a.confidence == 0.0
    assert a.components == []
    assert a.advisory is True
    assert a.scorer_version == 1  # absent marker is historical, not current


def test_assessment_round_trips_json():
    a = FabricationRiskAssessment(
        score=0.55,
        confidence=0.75,
        band=FabricationRiskBand.MODERATE,
        components=[RiskComponent(id="cross_field", band="major_issues", risk=0.75, confidence=0.75, weight=0.75, flagged=True)],
        reasoning="r",
    )
    again = FabricationRiskAssessment.model_validate_json(a.model_dump_json())
    assert again == a


def test_score_and_confidence_bounded():
    with pytest.raises(ValidationError):
        FabricationRiskAssessment(score=1.5)
    with pytest.raises(ValidationError):
        FabricationRiskAssessment(confidence=-0.1)
    with pytest.raises(ValidationError):
        FabricationRiskAssessment(scorer_version=0)


# Resume farm schema

def test_resume_farm_schema_defaults_are_conservative():
    a = ResumeFarmAssessment()
    assert a.band is DuplicationBand.INSUFFICIENT_DATA
    assert a.score == 0.0
    assert a.confidence == 0.0
    assert a.matches == []
    assert a.corpus_size == 0
    assert a.advisory is True  # hard mandate, mirrors Report


def test_similarity_bounds_enforced():
    with pytest.raises(ValidationError):
        ResumeMatch(candidate_id="c", resume_id="r", similarity=1.5)
    with pytest.raises(ValidationError):
        ResumeFarmAssessment(confidence=-0.1)


def test_band_values_are_wire_stable():
    assert DuplicationBand.NEAR_DUPLICATE.value == "near_duplicate"
    assert DuplicationBand.UNIQUE.value == "unique"


def test_resume_farm_schema_round_trips_through_json():
    a = ResumeFarmAssessment(
        score=0.91,
        confidence=0.9,
        band=DuplicationBand.NEAR_DUPLICATE,
        matches=[ResumeMatch(candidate_id="c1", resume_id="r1", similarity=0.91)],
        corpus_size=4,
        reasoning="r",
    )
    again = ResumeFarmAssessment.model_validate_json(a.model_dump_json())
    assert again == a
