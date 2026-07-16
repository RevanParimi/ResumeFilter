"""S2.1 contracts: conservative defaults, bounds, JSON round-trip."""

import pytest
from pydantic import ValidationError

from app.schemas.fabrication import (
    AIGenerationAssessment,
    AILikelihoodBand,
    AISignal,
    SignalSource,
)


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
