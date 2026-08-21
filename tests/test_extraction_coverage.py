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


from app.candidates.coverage import blocks, is_header_shaped, looks_academic, looks_dated_role


def test_header_shaped_accepts_real_headers_and_rejects_content():
    assert is_header_shaped("EXPERIENCE")
    assert is_header_shaped("Career History")
    assert is_header_shaped("Work Experience:")
    # Content lines are not headers.
    assert not is_header_shaped("- Senior Data Engineer, Acme Analytics (2019 - Present)")
    assert not is_header_shaped("priya@example.com")
    assert not is_header_shaped(
        "Built the ingestion pipeline handling four million events a day for the team"
    )


def test_blocks_groups_content_under_its_header():
    text = "Priya Sharma\n\nCAREER HISTORY\n- Engineer, Acme (2015 - 2019)\n"
    got = blocks(text)
    # "Priya Sharma" IS header-shaped (short, title-cased, undated) -- the same
    # blind spot the module docstring names: an identity line reads exactly
    # like a section header to this crude a detector. blocks() is a mechanical
    # splitter (plan ruling R4) and does not special-case it; the empty block
    # it opens is harmless because R3's evidence gate on section_unrecognized
    # is what keeps a bare name line from ever becoming assess_coverage() noise.
    assert got[0] == (None, [])
    assert got[1] == ("Priya Sharma", [])
    assert got[2][0] == "CAREER HISTORY"
    assert got[2][1] == ["- Engineer, Acme (2015 - 2019)"]


def test_dated_role_needs_two_points_or_a_present_marker():
    assert looks_dated_role("Senior Data Engineer, Acme Analytics (2019 - Present)")
    assert looks_dated_role("- Data Engineer, Foo Systems (2015 - 2019)")
    assert not looks_dated_role("Data Engineer, Foo Systems")
    assert not looks_dated_role("Shipped 2019 revenue dashboards")  # one year, no range


def test_academic_lines_are_not_counted_as_roles():
    assert looks_academic("B.Tech in Computer Science, NIT Trichy, 2014 - 2018")
    assert looks_academic("Bachelor of Technology, VIT Vellore, 2015")
    assert looks_academic("CGPA: 8.6/10")
    assert not looks_academic("Senior Data Engineer, Acme Analytics (2019 - Present)")
