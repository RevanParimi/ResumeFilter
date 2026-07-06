"""Schema contracts for the candidate extraction models (S1.1)."""

import pytest
from pydantic import ValidationError

from app.candidates.schema import DateRange, ExtractedStr, SourceSpan


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


from app.candidates.schema import (  # noqa: E402
    CandidateProfile,
    EducationEntry,
    EmploymentType,
    ExperienceEntry,
    ExtractionResult,
)


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
