"""S9.2 extraction coverage: what the resume says that the profile does not carry."""

from app.schemas.extraction import (
    CoverageBand,
    CoverageGap,
    ExtractionCoverage,
    GapSeverity,
)


def test_default_assessment_is_a_refusal():
    """The default must be 'we could not say', never 'we looked and it was clean'.

    Same posture as CrossFieldAssessment, whose band defaults to
    INSUFFICIENT_DATA -- a result that could not be taken must not read as a
    result that came back fine.
    """
    cov = ExtractionCoverage()
    assert cov.band is CoverageBand.INSUFFICIENT_DATA
    assert cov.gaps == []
    assert cov.checks_run == 0
    assert cov.truncated is False
    assert cov.advisory is True


def test_gap_defaults_to_minor():
    gap = CoverageGap(id="section_unrecognized", detail="header 'Career History' not recognized")
    assert gap.severity is GapSeverity.MINOR
    assert gap.field is None


from app.core.config import Settings


def test_coverage_knobs_have_conservative_defaults():
    s = Settings(_env_file=None)
    assert s.coverage_min_chars == 200
    assert s.coverage_max_header_chars == 60
    assert s.coverage_max_gaps == 20


import pytest
from pydantic import ValidationError


def test_coverage_max_gaps_rejects_zero():
    """coverage_max_gaps=0 would produce a refusal-shaped lie: an empty gaps
    list with truncated=True, indistinguishable from a clean assessment."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, coverage_max_gaps=0)


def test_coverage_min_chars_rejects_negative():
    """A negative coverage_min_chars disables the refusal this sprint is
    built on -- every document would clear the floor."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, coverage_min_chars=-1)
