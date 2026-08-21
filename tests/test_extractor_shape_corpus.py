"""One fixture per resume SHAPE (S9.2).

Each of these produced an empty section on main at 016f91f, measured. A future
extractor change that re-drops a shape fails here rather than in a smoke six
months later.

Fixtures live in tests/fixtures/shapes/*.txt (ruling R6) rather than as
module-level string constants: scripts/smoke_s92.py (Task 14) uploads these
same shapes over HTTP, and smokes run as `python scripts/smoke_s92.py` with
sys.path[0] == scripts/, so it cannot import from tests/. Files are readable
from both; pasting a second copy is the duplication scripts/_smoke.py exists
to end.
"""

from pathlib import Path

import pytest

from app.candidates.coverage import assess_coverage
from app.candidates.extractor import heuristic_profile
from app.schemas.extraction import CoverageBand

SHAPES = Path(__file__).parent / "fixtures" / "shapes"

BULLETED_ROLES = (SHAPES / "bulleted_roles.txt").read_text(encoding="utf-8")
CAREER_HISTORY = (SHAPES / "career_history_header.txt").read_text(encoding="utf-8")
SPELLED_OUT_DEGREES = (SHAPES / "spelled_out_degrees.txt").read_text(encoding="utf-8")
LABELLED_SKILLS = (SHAPES / "labelled_skills.txt").read_text(encoding="utf-8")


def test_bulleted_role_lines_are_extracted_as_roles():
    p = heuristic_profile(BULLETED_ROLES)
    assert len(p.experience) == 2
    assert p.experience[0].title == "Senior Data Engineer"
    assert p.experience[0].employer == "Acme Analytics"
    assert p.experience[0].dates.is_current is True
    assert p.experience[1].employer == "Foo Systems"


def test_duties_under_a_role_are_still_duties():
    """The rule that must NOT break: a bulleted line under an unbulleted dated
    role is a duty, and must not become a second employment entry."""
    text = """Priya Sharma
priya@example.com

EXPERIENCE
Senior Data Engineer, Acme Analytics (2019 - Present)
- Rebuilt the ingestion path, cutting 2019 latency in half by 2020
- Led a team of four

EDUCATION
B.Tech in Computer Science, IIT Delhi, CGPA: 8.6/10
"""
    p = heuristic_profile(text)
    assert len(p.experience) == 1


def test_bulleted_shape_now_reports_complete_coverage():
    p = heuristic_profile(BULLETED_ROLES)
    cov = assess_coverage(BULLETED_ROLES, p, min_chars=50)
    assert cov.band is not CoverageBand.MAJOR_GAPS


@pytest.mark.parametrize("header", [
    "CAREER HISTORY",
    "Employment Details",
    "ORGANIZATIONAL EXPERIENCE",
    "WORK EXPERIENCE (5 YEARS)",
    "Experience ------",
    "Work History:",
])
def test_experience_headers_real_resumes_use(header):
    text = BULLETED_ROLES.replace("EXPERIENCE", header)
    p = heuristic_profile(text)
    assert len(p.experience) == 2, f"header {header!r} lost the experience section"


def test_career_history_header_shape_now_reports_complete_coverage():
    p = heuristic_profile(CAREER_HISTORY)
    cov = assess_coverage(CAREER_HISTORY, p, min_chars=50)
    assert cov.band is not CoverageBand.MAJOR_GAPS


def test_spelled_out_degrees_are_extracted():
    p = heuristic_profile(SPELLED_OUT_DEGREES)
    assert len(p.education) == 2
    assert "Bachelor" in (p.education[0].degree or "")
    assert p.education[0].institution == "VIT Vellore"


def test_bba_and_ba_are_degrees():
    text = SPELLED_OUT_DEGREES.replace(
        "Bachelor of Technology in Computer Science", "BBA in Marketing"
    )
    p = heuristic_profile(text)
    assert len(p.education) == 2


def test_spelled_out_degrees_shape_now_reports_complete_coverage():
    p = heuristic_profile(SPELLED_OUT_DEGREES)
    cov = assess_coverage(SPELLED_OUT_DEGREES, p, min_chars=50)
    assert cov.band is not CoverageBand.MAJOR_GAPS


def test_skill_category_labels_are_dropped():
    p = heuristic_profile(LABELLED_SKILLS)
    names = [s.name for s in p.skills]
    assert "Python" in names
    assert "PostgreSQL" in names
    assert not any(":" in n for n in names), f"category label survived: {names}"


def test_a_colon_inside_a_single_skill_is_not_a_label():
    """Only a SHORT leading label before the first comma is a category.

    "Python: 5 years, Java: 3 years" is per-skill proficiency annotation, a
    common Indian-resume shape -- TWO colons, not one, so R15's label rule
    must not fire and "Python" must survive somewhere in the output rather
    than being deleted as if it were a category name."""
    text = LABELLED_SKILLS.replace(
        "Programming Languages: Python, Java, Go", "Python: 5 years, Java: 3 years"
    )
    p = heuristic_profile(text)
    names = [s.name for s in p.skills]
    assert any("Python" in n for n in names), f"Python lost entirely: {names}"


def test_a_single_skill_with_one_colon_and_no_second_item_keeps_its_text():
    """"C++: advanced" has exactly one colon but only ONE item after it (no
    comma), so it fails R15's "at least two comma-separated items" half too --
    it is not a category either. The accepted cost: it survives ugly, as one
    skill literally named "C++: advanced", rather than being destroyed."""
    text = LABELLED_SKILLS.replace(
        "Programming Languages: Python, Java, Go", "C++: advanced"
    )
    p = heuristic_profile(text)
    names = [s.name for s in p.skills]
    assert "C++: advanced" in names, f"C++ lost: {names}"


def test_labelled_skills_shape_now_reports_complete_coverage():
    p = heuristic_profile(LABELLED_SKILLS)
    cov = assess_coverage(LABELLED_SKILLS, p, min_chars=50)
    assert cov.band is not CoverageBand.MAJOR_GAPS
