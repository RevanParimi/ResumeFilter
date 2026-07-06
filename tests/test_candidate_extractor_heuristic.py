"""Deterministic extractor path (S1.1) — must work with zero LLM."""

from pathlib import Path

import pytest

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import EmploymentType, LinkType

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def full_resume() -> str:
    return (FIXTURES / "full_profile_resume.txt").read_text(encoding="utf-8")


def test_identity_and_contact(full_resume):
    p = heuristic_profile(full_resume)
    assert p.full_name is not None and p.full_name.value == "Arjun Mehta"
    assert p.headline is not None and "Data Engineer" in p.headline.value
    assert p.contact.email is not None
    assert p.contact.email.value == "arjun.mehta@example.com"
    assert p.contact.email.confidence >= 0.9
    assert p.contact.phone is not None and "98765" in p.contact.phone.value


def test_education_entry(full_resume):
    p = heuristic_profile(full_resume)
    assert len(p.education) == 1
    edu = p.education[0]
    assert edu.degree == "B.Tech"
    assert edu.field_of_study == "Computer Science"
    assert edu.institution == "NIT Trichy"
    assert edu.grade_value == 8.6 and edu.grade_scale == "cgpa_10"
    assert edu.dates.start == "2014" and edu.dates.end == "2018"


def test_experience_entries(full_resume):
    p = heuristic_profile(full_resume)
    assert len(p.experience) == 2
    first, second = p.experience
    assert first.title == "Senior Data Engineer" and first.employer == "Flipkart"
    assert first.seniority == "senior"
    assert first.dates.start == "2021-06" and first.dates.is_current is True
    assert second.employer == "Infosys"
    assert second.dates.start == "2018-07" and second.dates.end == "2021-05"
    # Bullet lines under an entry are NOT separate entries.
    assert all(e.employment_type == EmploymentType.UNKNOWN for e in p.experience)


def test_skills_projects_certifications_links(full_resume):
    p = heuristic_profile(full_resume)
    skills = {s.name for s in p.skills}
    assert {"Python", "SQL", "Kafka", "AWS"} <= skills
    assert len(p.projects) == 1
    prj = p.projects[0]
    assert prj.name == "open-lineage-tracker"
    assert prj.url == "https://github.com/arjun-mehta/open-lineage-tracker"
    assert prj.description is not None and "lineage" in prj.description.lower()
    assert len(p.certifications) == 1
    crt = p.certifications[0]
    assert crt.year == 2022 and crt.issuer == "Amazon Web Services"
    link_types = {l.type for l in p.links}
    assert LinkType.GITHUB in link_types and LinkType.LINKEDIN in link_types


def test_every_span_slices_back_into_the_resume(full_resume):
    p = heuristic_profile(full_resume)
    entries = (
        list(p.education) + list(p.experience) + list(p.projects)
        + list(p.certifications) + list(p.links)
    )
    assert entries, "extractor produced nothing"
    for e in entries:
        assert e.span is not None
        assert full_resume[e.span.start : e.span.end] == e.span.text
    assert p.contact.email is not None and p.contact.email.span is not None
    s = p.contact.email.span
    assert full_resume[s.start : s.end] == s.text


def test_unstructured_resume_degrades_gracefully(full_resume):
    # No section headers at all → still finds contact + links, crashes never.
    p = heuristic_profile("Reach me at someone@example.com or +91 98765 43210")
    assert p.contact.email is not None
    assert p.education == [] and p.experience == []
