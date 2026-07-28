"""S5.2 comp contracts — vocabulary + model validation."""

import pytest
from pydantic import ValidationError

from app.comp.schema import (
    ROLE_FAMILIES, CITY_TIERS, DEFAULT_ROLE_FAMILY,
    SeniorityBand, RoleSignal, CompBandEstimate, CompBenchmark,
)
from app.matching.schema import CompBand


def test_vocabulary_constants():
    assert DEFAULT_ROLE_FAMILY in ROLE_FAMILIES
    assert set(CITY_TIERS) == {"metro", "tier_2"}
    assert "backend_engineer" in ROLE_FAMILIES


def test_role_signal_validates_family_and_tier():
    ok = RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.SENIOR, city_tier="metro")
    assert ok.seniority is SeniorityBand.SENIOR
    with pytest.raises(ValidationError):
        RoleSignal(role_family="astronaut", seniority=SeniorityBand.MID, city_tier="metro")
    with pytest.raises(ValidationError):
        RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.MID, city_tier="mars")


def test_estimate_and_benchmark_defaults():
    est = CompBandEstimate(
        p25=10.0, p50=12.0, p75=14.0, confidence=0.3,
        role_family="backend_engineer", seniority=SeniorityBand.MID, city_tier="metro",
    )
    assert est.advisory is True
    assert est.sources == ("static",)
    assert est.currency == "INR"
    bench = CompBenchmark(estimate=est, requisition_band=CompBand(ctc_min=8.0, ctc_max=10.0))
    assert bench.advisory is True
    assert bench.position is None  # unset until benchmark_comp fills it
