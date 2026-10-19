"""Candidate schema regressions, grouped by behavior."""

import pytest
from pydantic import ValidationError
from app.candidates.schema import (
    DateRange,
    ExtractedStr,
    SourceSpan,
    CandidateProfile,
    EducationEntry,
    EmploymentType,
    ExperienceEntry,
    ExtractionResult,
)
from app.candidates.dates import date_points, has_date_range, parse_date_range


# Candidate schema

def test_source_span_rejects_reversed_range():
    with pytest.raises(ValidationError):
        SourceSpan(start=10, end=5, text="x")


def test_source_span_accepts_ordered_range():
    span = SourceSpan(start=3, end=8, text="hello")
    assert (span.start, span.end, span.text) == (3, 8, "hello")


def test_extracted_str_confidence_bounds():
    with pytest.raises(ValidationError):
        ExtractedStr(value="x", confidence=1.5)
    with pytest.raises(ValidationError):
        ExtractedStr(value="x", confidence=-0.1)


def test_extracted_str_defaults():
    f = ExtractedStr(value="Arjun")
    assert f.confidence == 0.5 and f.span is None


def test_date_range_defaults_to_open():
    d = DateRange()
    assert d.start is None and d.end is None and d.is_current is False


def test_empty_profile_constructs_with_defaults():
    p = CandidateProfile()
    assert p.id.startswith("cand_")
    assert p.education == [] and p.skills == [] and p.links == []
    assert p.contact.email is None and p.contact.email_hash is None


def test_profile_json_round_trip():
    p = CandidateProfile(
        full_name=ExtractedStr(
            value="Arjun Mehta",
            confidence=0.9,
            span=SourceSpan(start=0, end=11, text="Arjun Mehta"),
        ),
        education=[
            EducationEntry(
                degree="B.Tech",
                field_of_study="Computer Science",
                institution="NIT Trichy",
                grade_value=8.6,
                grade_scale="cgpa_10",
                dates=DateRange(start="2014", end="2018"),
                confidence=0.8,
            )
        ],
        experience=[
            ExperienceEntry(
                employer="Flipkart",
                title="Senior Data Engineer",
                seniority="senior",
                employment_type=EmploymentType.FULL_TIME,
                dates=DateRange(start="2021-06", is_current=True),
                confidence=0.7,
            )
        ],
    )
    restored = CandidateProfile.model_validate_json(p.model_dump_json())
    assert restored == p
    assert restored.education[0].id.startswith("edu_")
    assert restored.experience[0].id.startswith("exp_")


def test_extraction_result_methods_are_constrained():
    with pytest.raises(ValidationError):
        ExtractionResult(profile=CandidateProfile(), method="magic")
    ok = ExtractionResult(profile=CandidateProfile(), method="heuristic")
    assert ok.warnings == []


# Candidate dates

def test_month_year_range_with_present():
    d = parse_date_range("Jun 2021 - Present")
    assert d.start == "2021-06" and d.end is None and d.is_current is True


def test_full_month_names_and_to_separator():
    d = parse_date_range("January 2020 to March 2022")
    assert d.start == "2020-01" and d.end == "2022-03" and d.is_current is False


def test_year_only_range():
    d = parse_date_range("2014 - 2018")
    assert d.start == "2014" and d.end == "2018" and d.is_current is False


def test_numeric_month_slash_year():
    d = parse_date_range("03/2021 - 06/2023")
    assert d.start == "2021-03" and d.end == "2023-06"


def test_no_dates_returns_open_range():
    d = parse_date_range("Built streaming pipelines processing 2TB/day")
    assert d.start is None and d.end is None


def test_date_points_positions_are_ordered():
    pts = date_points("Data Engineer, Infosys — Jul 2018 - May 2021")
    assert [v for _, v in pts] == ["2018-07", "2021-05"]
    assert pts[0][0] < pts[1][0]


def test_has_date_range_detects_career_lines():
    assert has_date_range("Jun 2021 - Present") is True
    assert has_date_range("2014 - 2018, CGPA: 8.6/10") is True
    assert has_date_range("Built pipelines processing 2TB/day") is False
    assert has_date_range("CGPA: 8.6/10") is False
