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
