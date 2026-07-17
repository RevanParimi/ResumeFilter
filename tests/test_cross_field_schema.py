"""S2.2 contracts: conservative defaults, bounds, JSON round-trip."""

import pytest
from pydantic import ValidationError

from app.schemas.fabrication import (
    ConsistencyBand,
    CrossFieldAssessment,
    CrossFieldFinding,
    FindingSeverity,
)


def test_defaults_are_conservative():
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


def test_round_trips_through_json():
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
