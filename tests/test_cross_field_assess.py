"""Cross-field assessment + structural banding — pure, offline."""

from datetime import date

import pytest

from app.candidates.extractor import heuristic_profile
from app.candidates.normalize import normalize_profile
from app.candidates.schema import (
    CandidateProfile,
    DateRange,
    EducationEntry,
    EmploymentType,
    ExperienceEntry,
)
from app.fabrication.cross_field import assess_cross_field, band_for_findings
from app.schemas.fabrication import ConsistencyBand, CrossFieldFinding, FindingSeverity

TODAY = date(2026, 7, 1)


def _consistent_profile() -> CandidateProfile:
    return CandidateProfile(
        education=[
            EducationEntry(degree="B.Tech", degree_level="bachelor",
                           dates=DateRange(start="2014", end="2018")),
        ],
        experience=[
            ExperienceEntry(title="Software Engineer", employer="A",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2019-01", end="2020-12")),
            ExperienceEntry(title="Senior Engineer", employer="B",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2021-02", end="2023-06")),
        ],
    )


def test_inconsistent_fixture_lands_in_major_issues(inconsistent_resume, settings):
    profile = normalize_profile(heuristic_profile(inconsistent_resume))
    a = assess_cross_field(profile, settings, today=TODAY)
    assert a.band is ConsistencyBand.MAJOR_ISSUES
    assert a.confidence == pytest.approx(0.9)  # all four checks had enough data
    ids = {f.id for f in a.findings}
    assert {"timeline_overlap", "education_employment_overlap",
            "seniority_vs_tenure"} <= ids
    assert a.score > 0.4
    assert all(f.detail for f in a.findings)
    assert a.advisory is True


def test_consistent_profile_is_consistent(settings):
    a = assess_cross_field(_consistent_profile(), settings, today=TODAY)
    assert a.findings == []
    assert a.band is ConsistencyBand.CONSISTENT
    assert a.score == 0.0
    assert a.confidence >= settings.xf_min_confidence


def test_empty_profile_is_insufficient(settings):
    a = assess_cross_field(CandidateProfile(), settings, today=TODAY)
    assert a.band is ConsistencyBand.INSUFFICIENT_DATA
    assert a.confidence == 0.0


def test_minor_findings_never_reach_major_band(settings):
    minor = CrossFieldFinding(id="timeline_gap", detail="d", score=0.4,
                              severity=FindingSeverity.MINOR)
    assert band_for_findings([minor], 0.9, settings) is ConsistencyBand.MINOR_ISSUES
    major = CrossFieldFinding(id="timeline_overlap", detail="d", score=0.8,
                              severity=FindingSeverity.MAJOR)
    assert band_for_findings([major], 0.9, settings) is ConsistencyBand.MAJOR_ISSUES
    assert band_for_findings([], 0.9, settings) is ConsistencyBand.CONSISTENT


def test_low_confidence_never_asserts(settings):
    major = CrossFieldFinding(id="timeline_overlap", detail="d", score=0.9,
                              severity=FindingSeverity.MAJOR)
    assert band_for_findings([major], 0.3, settings) is ConsistencyBand.INSUFFICIENT_DATA


def test_reasoning_names_the_findings(settings):
    profile = _consistent_profile()
    profile.experience.append(
        ExperienceEntry(title="Engineer", employer="C",
                        employment_type=EmploymentType.FULL_TIME,
                        dates=DateRange(start="2021-06", end="2023-06"))
    )
    a = assess_cross_field(profile, settings, today=TODAY)
    assert "timeline_overlap" in a.reasoning


def test_settings_expose_xf_knobs(settings):
    assert settings.xf_min_confidence == 0.50
    assert settings.xf_overlap_months_min == 3
    assert settings.xf_gap_months_min == 12
    assert settings.xf_edu_overlap_months_min == 12
    assert settings.xf_senior_min_months == 24
    assert settings.xf_lead_min_months == 48
