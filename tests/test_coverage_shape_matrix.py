"""The regression corpus (S9.2 final review fix-wave): one row per resume
SHAPE this sprint discovered, table-driven, so the next predicate change in
extractor.py or coverage.py has to satisfy every one of them at once instead
of quietly breaking one while a single named test elsewhere still goes green.

This file exists because of how NEW-1 and NEW-2 happened: each earlier fix
wave changed a predicate (`_looks_like_role`'s word cap, the strong-header-
signal gate) to close ONE finding and broke a DIFFERENT shape that had no
test at all. A table that runs all known shapes together is the guard against
that pattern repeating a third time.

Fixtures live in tests/fixtures/shapes/*.txt (ruling R6, same convention as
tests/test_extractor_shape_corpus.py) rather than as inline strings, so a
future fixture can also be picked up by scripts/smoke_s92.py without a second
copy.
"""

from pathlib import Path

import pytest

from app.candidates.coverage import assess_coverage
from app.candidates.extractor import heuristic_profile
from app.schemas.extraction import CoverageBand

SHAPES = Path(__file__).parent / "fixtures" / "shapes"


def _load(name: str) -> str:
    return (SHAPES / f"{name}.txt").read_text(encoding="utf-8")


def _gap_ids(cov):
    return {g.id for g in cov.gaps}


# --- one check function per row -------------------------------------------


def _bulleted_roles():
    text = _load("bulleted_roles")
    p = heuristic_profile(text)
    assert len(p.experience) == 2
    cov = assess_coverage(text, p, min_chars=50)
    assert cov.band is CoverageBand.COMPLETE


def _career_history_header():
    text = _load("career_history_header")
    p = heuristic_profile(text)
    assert len(p.experience) == 2
    cov = assess_coverage(text, p, min_chars=50)
    assert cov.band is CoverageBand.COMPLETE


def _spelled_out_degrees():
    text = _load("spelled_out_degrees")
    p = heuristic_profile(text)
    assert len(p.education) == 2
    cov = assess_coverage(text, p, min_chars=50)
    assert cov.band is CoverageBand.COMPLETE


def _labelled_skills():
    text = _load("labelled_skills")
    p = heuristic_profile(text)
    names = [s.name for s in p.skills]
    assert not any(":" in n for n in names), f"category label survived: {names}"
    assert "Python" in names and "PostgreSQL" in names
    cov = assess_coverage(text, p, min_chars=50)
    assert cov.band is CoverageBand.COMPLETE


def _undated_role_dated_achievements():
    """An undated role line with dated achievement bullets under it: the
    EXTRACTOR correctly opens no fabricated entry (C2) -- 0 experience is the
    honest result, not a defect. But coverage.py is deliberately blind to
    that role/duty distinction (the module's whole independence argument): a
    dated-looking bullet reads as role evidence to `looks_dated_role`
    regardless of why the extractor declined it, so this shape reports
    `major_gaps` with `experience_not_extracted` even though the extraction
    is correct. That is a known, accepted false positive of an advisory
    instrument, not a bug -- see CANDIDATES.md's "Known limits"."""
    text = _load("undated_role_dated_achievements")
    p = heuristic_profile(text)
    assert p.experience == []
    cov = assess_coverage(text, p, min_chars=50)
    assert cov.band is CoverageBand.MAJOR_GAPS
    assert "experience_not_extracted" in _gap_ids(cov)


def _long_bulleted_role_heads():
    """NEW-2: multi-word employer names (TCS, Larsen and Toubro) must not be
    dropped by the word-count axis that used to gate _looks_like_role."""
    text = _load("long_bulleted_role_heads")
    p = heuristic_profile(text)
    assert len(p.experience) == 2


def _key_skills_bulleted():
    text = _load("key_skills_bulleted")
    p = heuristic_profile(text)
    assert p.skills == []
    cov = assess_coverage(text, p, min_chars=50)
    assert cov.band is CoverageBand.MAJOR_GAPS
    assert "skills_not_extracted" in _gap_ids(cov)


def _tech_stack_comma_list():
    """NEW-1: a Title-Case, unaliased "Tech Stack" header over a bare comma
    list must still open a block, so check 3 can see the dropped skills."""
    text = _load("tech_stack_comma_list")
    p = heuristic_profile(text)
    assert p.skills == []
    cov = assess_coverage(text, p, min_chars=50)
    assert cov.band is CoverageBand.MAJOR_GAPS
    assert "skills_not_extracted" in _gap_ids(cov)


def _academic_credentials_two_line():
    text = _load("academic_credentials_two_line")
    p = heuristic_profile(text)
    assert p.education == []
    cov = assess_coverage(text, p, min_chars=50)
    assert cov.band is CoverageBand.MAJOR_GAPS
    assert "education_not_extracted" in _gap_ids(cov)


def _fresher_education_two_line():
    """I3: a fresher's two-line education block ("B.Tech Computer Science" /
    "VIT Vellore | 2019 - 2023") must not misread its own institution/date
    line as an unclaimed role."""
    text = _load("fresher_education_two_line")
    p = heuristic_profile(text)
    assert p.experience == []
    cov = assess_coverage(text, p, min_chars=50)
    assert "experience_not_extracted" not in _gap_ids(cov)


def _technologies_in_projects():
    """I1: "Technologies (Python, Django, PostgreSQL)" under PROJECTS must
    survive as project content, not vanish as a mis-parsed SKILLS header."""
    text = _load("technologies_in_projects")
    p = heuristic_profile(text)
    names = [prj.name for prj in p.projects]
    assert "Technologies (Python, Django, PostgreSQL)" in names
    assert [s.name for s in p.skills] == ["Go", "Rust"]


def _anonymised_no_contact():
    """No email, no phone, nothing phone-shaped in the whole document -- the
    absence of contact evidence must not itself read as a dropped field."""
    text = _load("anonymised_no_contact")
    p = heuristic_profile(text)
    cov = assess_coverage(text, p, min_chars=50)
    assert "contact_not_extracted" not in _gap_ids(cov)


def _key_skills_bare_list_known_limit():
    """KNOWN LIMIT, asserted at its ACTUAL current behaviour -- not a desired
    one. "Key Skills" (Title-Case) over a bare one-per-line list ("Python" /
    "Java" / "Kubernetes") is NOT fixed by NEW-1's fourth door: the next line
    after "Key Skills" is itself header-shaped (a single Title-Case word), so
    the door stays closed exactly as it must for the KEY SKILLS-bulleted and
    Academic-Credentials cases above, and "Key Skills" never opens a block.
    Its list lands as unclaimed content in the top (None-header) block,
    profile.skills stays empty, and check 3 has no SKILLS-shaped header to
    fire under -- coverage reports `complete` despite the dropped skills.
    This is the recorded gap CANDIDATES.md's "Known limits" names; do not
    "fix" this test by contorting the predicate to catch it (the brief is
    explicit that doing so breaks the shapes above)."""
    text = _load("key_skills_bare_list")
    p = heuristic_profile(text)
    assert p.skills == []
    cov = assess_coverage(text, p, min_chars=50)
    assert cov.band is CoverageBand.COMPLETE
    assert cov.gaps == []


def _github_link_no_education():
    """A GitHub link is not a degree, and a resume with no degree has no
    education GAP to report -- there is no evidence a section was dropped.

    `_DEGREE_WORDS` used to be matched with `w in low`, and `b.com` sits inside
    `github.com`, so this shape reported a false `education_not_extracted`. In
    a tech-hiring product most resumes carry this link, which made it the
    likeliest false positive the instrument could produce.
    """
    text = _load("github_link_no_education")
    p = heuristic_profile(text)
    assert len(p.education) == 0, "this fixture deliberately has no degree line"
    cov = assess_coverage(text, p, min_chars=50)
    assert "education_not_extracted" not in _gap_ids(cov)
    assert cov.band is CoverageBand.COMPLETE


ROWS = [
    ("GitHub link + no education -> no false education gap", _github_link_no_education),
    ("bulleted roles -> 2 experience, complete", _bulleted_roles),
    ("CAREER HISTORY header -> 2 experience, complete", _career_history_header),
    ("spelled-out degrees -> 2 education, complete", _spelled_out_degrees),
    ("labelled skills -> no category labels, complete", _labelled_skills),
    ("undated role + dated achievements -> 0 experience, major_gaps", _undated_role_dated_achievements),
    ("long bulleted role heads (TCS/L&T) -> 2 experience", _long_bulleted_role_heads),
    ("KEY SKILLS bulleted -> major_gaps, skills_not_extracted", _key_skills_bulleted),
    ("Tech Stack comma list -> major_gaps, skills_not_extracted", _tech_stack_comma_list),
    ("ACADEMIC CREDENTIALS two-line -> education gap fires", _academic_credentials_two_line),
    ("fresher education two-line -> no experience_not_extracted (I3)", _fresher_education_two_line),
    ("Technologies(...) in PROJECTS -> line survives, skills=[Go,Rust]", _technologies_in_projects),
    ("anonymised, no contact line -> no contact_not_extracted", _anonymised_no_contact),
    ("Key Skills + bare list -> complete (KNOWN LIMIT, not desired)", _key_skills_bare_list_known_limit),
]


@pytest.mark.parametrize("description,check", ROWS, ids=[r[0] for r in ROWS])
def test_shape_matrix(description, check):
    check()
