import pytest
from pydantic import ValidationError

from app.matching.schema import (
    CompBand, JobRequisitionInput, MatchWeights, RequisitionStatus,
)


def test_requisition_requires_at_least_one_skill():
    with pytest.raises(ValidationError):
        JobRequisitionInput(title="Backend Engineer")


def test_requisition_ok_with_must_have():
    r = JobRequisitionInput(title="BE", must_have_skills=("python", "django"))
    assert r.status is RequisitionStatus.OPEN
    assert r.remote is False


def test_bad_degree_level_rejected():
    with pytest.raises(ValidationError):
        JobRequisitionInput(title="BE", must_have_skills=("python",), min_degree_level="phd")


def test_bad_location_tier_rejected():
    with pytest.raises(ValidationError):
        JobRequisitionInput(title="BE", must_have_skills=("python",), location_tiers=("village",))


def test_compband_bounds():
    with pytest.raises(ValidationError):
        CompBand(ctc_min=30.0, ctc_max=10.0)
    assert CompBand(ctc_min=10.0, ctc_max=30.0).currency == "INR"


def test_weights_must_be_positive():
    with pytest.raises(ValidationError):
        MatchWeights(skill_coverage=0.0)
