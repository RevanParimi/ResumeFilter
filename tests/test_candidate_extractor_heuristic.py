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


def test_parenthetical_body_line_does_not_become_a_section_header():
    """I1 (S9.2 final review): _HEADER_DECORATION stripped `(...)` before the
    alias lookup unconditionally, so a body line shaped "<alias> (...)" --
    e.g. "Technologies (Python, Django, PostgreSQL)" under PROJECTS, which
    normalizes to the "technologies" skills alias once its parenthetical is
    stripped -- was silently consumed as a SKILLS header and never stored.
    Measured before the fix: projects=['Placement Portal'] (the technology
    list deleted), skills=['Built for 4000 students', 'Go', 'Rust'] (the
    project description re-parented into skills)."""
    text = """Priya Sharma
priya@example.com

PROJECTS
Placement Portal
Technologies (Python, Django, PostgreSQL)
Built for 4000 students

SKILLS
Go, Rust
"""
    p = heuristic_profile(text)
    names = [prj.name for prj in p.projects]
    assert names == [
        "Placement Portal",
        "Technologies (Python, Django, PostgreSQL)",
        "Built for 4000 students",
    ]
    assert [s.name for s in p.skills] == ["Go", "Rust"]


def test_all_caps_parenthetical_header_still_resolves():
    """The other direction I1 must not break: "WORK EXPERIENCE (5 YEARS)"
    must still strip its parenthetical and resolve to the experience alias
    -- the fix bounds when stripping applies, it does not remove it."""
    text = """Priya Sharma
priya@example.com

WORK EXPERIENCE (5 YEARS)
Senior Data Engineer, Acme Analytics (2019 - Present)
"""
    p = heuristic_profile(text)
    assert len(p.experience) == 1
    assert p.experience[0].employer == "Acme Analytics"


def _edu(section_lines: str):
    """Heuristic profile for a resume whose EDUCATION section is `section_lines`."""
    return heuristic_profile(
        "Priya Nair\n\nEXPERIENCE\n"
        "Senior Data Engineer, Acme Analytics (2019 - Present)\n\n"
        f"EDUCATION\n{section_lines}\n"
    ).education


def test_an_english_word_in_the_education_section_is_not_a_degree():
    r"""`_DEGREE` spelled the two-letter abbreviations `b\.?e\b`, so the DOT was
    optional and the bare English words "be", "me", "ma" and "ba" each matched.

    A prose line in an education section then became an EducationEntry whose
    `degree` was the whole sentence -- the extractor inventing a credential
    nobody claimed. S9.2's ruling R13 settled the principle for roles
    ("inventing one is worse than missing one"); this is the same call for
    degrees, and R14 already dropped `bs`/`ms` for matching "MS Office".
    """
    assert _edu("This programme will be announced later") == []
    assert _edu("Please contact me for transcripts") == []
    assert _edu("Completed ma jor coursework") == []
    assert _edu("Covered ba sic statistics") == []


def test_real_two_letter_degrees_still_extract_dotted_or_not():
    """The fix must not cost the degrees themselves. `BE` and `ME` (Bachelor /
    Master of Engineering) and `BA` / `MA` are ordinary on Indian resumes,
    written with dots or without -- so the dotless forms stay legal in
    UPPERCASE, which is what separates the degree `BE` from the word `be`.
    """
    for line, degree in [
        ("B.E in Information Technology, COEP, 2025", "B.E"),
        ("BE in Information Technology, COEP, 2025", "BE"),
        ("M.A in Economics, JNU, 2013", "M.A"),
        ("MA in Economics, JNU, 2013", "MA"),
        ("ME in Mechanical Engineering, VJTI, 2011", "ME"),
        ("BA in English, Fergusson College, 2009", "BA"),
    ]:
        got = _edu(line)
        assert len(got) == 1, f"{line!r} produced {len(got)} entries"
        assert got[0].degree == degree, f"{line!r} -> {got[0].degree!r}"
