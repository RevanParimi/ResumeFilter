"""S2.3 contracts: conservative defaults, bounds, JSON round-trip."""

import pytest
from pydantic import ValidationError

from app.schemas.fabrication import (
    DuplicationBand,
    ResumeFarmAssessment,
    ResumeMatch,
)


def test_defaults_are_conservative():
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


def test_round_trips_through_json():
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
