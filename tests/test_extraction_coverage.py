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
