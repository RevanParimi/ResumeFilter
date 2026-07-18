"""S2.4 contracts: unified fabrication-risk band + assessment schema."""

import pytest
from pydantic import ValidationError

from app.schemas.fabrication import (
    FabricationRiskAssessment,
    FabricationRiskBand,
    RiskComponent,
)


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
