"""Education↔employment coherence + seniority-vs-tenure — pure, offline."""

from datetime import date

from app.candidates.schema import DateRange, EducationEntry, EmploymentType, ExperienceEntry
from app.fabrication.cross_field import (
    check_education_overlap,
    check_seniority_vs_tenure,
    is_bachelor,
)
from app.schemas.fabrication import FindingSeverity

TODAY = date(2026, 7, 1)


def _exp(start, end, *, etype=EmploymentType.FULL_TIME, title="Engineer"):
    return ExperienceEntry(
        title=title,
        employer="Acme",
        employment_type=etype,
        dates=DateRange(start=start, end=end),
    )


def _btech(start="2018", end="2022", level="bachelor"):
    return EducationEntry(
        degree="B.Tech in Computer Science",
        institution="NIT Trichy",
        degree_level=level,
        dates=DateRange(start=start, end=end),
    )


def test_is_bachelor_uses_canonical_level_and_keyword_fallback():
    assert is_bachelor(_btech()) is True
    assert is_bachelor(_btech(level=None)) is True  # falls back to "B.Tech" keyword
    master = EducationEntry(degree="M.Tech", degree_level="master")
    assert is_bachelor(master) is False


def test_edu_overlap_fires_on_fulltime_role_inside_bachelors():
    # Bachelor's 2018–2022 narrows to Dec 2018 .. Jan 2022; the role covers
    # Jun 2020 .. Jan 2022 of it = 20 months >= 12 -> minor (< 24).
    edu = _btech()
    exp = _exp("2020-06", "2022-08")
    findings = check_education_overlap([edu], [exp], today=TODAY, min_months=12)
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "education_employment_overlap"
    assert f.severity is FindingSeverity.MINOR
    assert set(f.entry_ids) == {edu.id, exp.id}
    assert "20 months" in f.detail


def test_edu_overlap_major_at_two_years():
    edu = _btech(start="2018-07", end="2022-05")
    exp = _exp("2019-01", "2021-06")  # 30 months inside the degree
    findings = check_education_overlap([edu], [exp], today=TODAY, min_months=12)
    assert len(findings) == 1
    assert findings[0].severity is FindingSeverity.MAJOR


def test_edu_overlap_ignores_masters_and_internships():
    # Part-time/executive master's programmes are common; internships during a
    # bachelor's are normal. Neither may fire.
    master = EducationEntry(degree="M.Tech", degree_level="master",
                            dates=DateRange(start="2019", end="2023"))
    intern = _exp("2020-06", "2021-08", etype=EmploymentType.INTERNSHIP)
    assert check_education_overlap([master], [_exp("2020-01", "2022-01")],
                                   today=TODAY, min_months=12) == []
    assert check_education_overlap([_btech()], [intern],
                                   today=TODAY, min_months=12) == []


def test_lead_title_with_thin_span_is_major():
    a = _exp("2020-06", "2022-08", title="Lead AI Engineer")
    b = _exp("2021-01", "2022-08")
    findings = check_seniority_vs_tenure(
        [a, b], today=TODAY, senior_min_months=24, lead_min_months=48
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "seniority_vs_tenure"
    assert f.severity is FindingSeverity.MAJOR  # lead-level claim, 27-month span
    assert f.entry_ids == [a.id]
    assert "27 months" in f.detail


def test_senior_title_with_thin_span_is_minor_only():
    # Title inflation at "senior" is common; keep it context, not accusation.
    a = _exp("2021-06", "2022-08", title="Senior Engineer")
    b = _exp("2022-01", "2022-12", title="Senior Engineer")
    findings = check_seniority_vs_tenure(
        [a, b], today=TODAY, senior_min_months=24, lead_min_months=48
    )
    assert len(findings) == 1
    assert findings[0].severity is FindingSeverity.MINOR


def test_adequate_span_is_silent():
    a = _exp("2018-01", "2021-12", title="Senior Engineer")
    b = _exp("2022-01", "2024-06", title="Lead Engineer")  # 78-month span
    assert check_seniority_vs_tenure(
        [a, b], today=TODAY, senior_min_months=24, lead_min_months=48
    ) == []


def test_seniority_needs_two_dated_entries():
    # One dated entry could be a truncated resume -> conservative: skip.
    a = _exp("2024-01", "2025-06", title="Lead Engineer")
    assert check_seniority_vs_tenure(
        [a], today=TODAY, senior_min_months=24, lead_min_months=48
    ) == []


def test_plain_titles_never_fire():
    a = _exp("2023-01", "2023-12", title="Software Engineer")
    b = _exp("2024-01", "2024-12", title="ML Engineer")
    assert check_seniority_vs_tenure(
        [a, b], today=TODAY, senior_min_months=24, lead_min_months=48
    ) == []
