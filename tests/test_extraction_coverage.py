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


def test_header_shaped_rejects_delimited_lists():
    """Controller ruling R10 (review of tasks 4/5): a comma-, semicolon-,
    pipe-, or middle-dot-delimited line is content (a skills list, an inline
    "Title | City" identity line), never a section header. No entry in
    SECTION_ALIASES contains any of these four characters, so rejecting them
    costs nothing real -- a header literally written "Skills, Tools" would be
    misread as content, but that is bounded; the systematic false negative
    it replaces (Finding 1: a bare skills list stealing itself out of its own
    section) is not."""
    assert not is_header_shaped("Python, SQL, Pandas")
    assert not is_header_shaped("Python | SQL | Pandas")
    assert not is_header_shaped("Python; SQL; Pandas")
    assert not is_header_shaped("Python · SQL · Pandas")
    # "&" stays allowed -- SECTION_ALIASES has "licenses & certifications".
    assert is_header_shaped("Licenses & Certifications")


from app.candidates.coverage import assess_coverage
from app.candidates.schema import CandidateProfile, ContactInfo, EducationEntry, ExperienceEntry, ExtractedStr, SkillItem

BULLETED = """Priya Sharma
Senior Data Engineer | Bengaluru
priya@example.com  +91 98765 43210

EXPERIENCE
- Senior Data Engineer, Acme Analytics (2019 - Present)
- Data Engineer, Foo Systems (2015 - 2019)

EDUCATION
B.Tech in Computer Science, IIT Delhi, CGPA: 8.6/10
"""


def _profile(**kw) -> CandidateProfile:
    return CandidateProfile(**kw)


def test_short_text_refuses_and_carries_no_gaps():
    """The refusal is the design. An empty-looking clean result would be a lie."""
    cov = assess_coverage("Priya Sharma\npriya@example.com", _profile(), min_chars=200)
    assert cov.band is CoverageBand.INSUFFICIENT_DATA
    assert cov.gaps == []
    assert cov.checks_run == 0


def test_dropped_experience_is_a_major_gap():
    profile = _profile(
        contact=ContactInfo(email=ExtractedStr(value="priya@example.com")),
        education=[EducationEntry(degree="B.Tech")],
        skills=[SkillItem(name="Python")],
    )  # experience deliberately empty -- the measured defect
    cov = assess_coverage(BULLETED, profile, min_chars=50)
    assert cov.band is CoverageBand.MAJOR_GAPS
    ids = {g.id for g in cov.gaps}
    assert "experience_not_extracted" in ids
    gap = next(g for g in cov.gaps if g.id == "experience_not_extracted")
    assert gap.severity is GapSeverity.MAJOR
    assert gap.field == "experience"


def test_a_genuine_fresher_reports_complete():
    """No work history is not a gap. This is the false positive that would
    make the whole instrument untrustworthy, so it gets its own test."""
    text = """Anita Rao
anita@example.com  +91 98765 43210

EDUCATION
B.Tech in Computer Science, VIT Vellore, 2019 - 2023, CGPA: 8.1/10

SKILLS
Python, SQL, Pandas

PROJECTS
Campus placement portal built with Django
"""
    profile = _profile(
        contact=ContactInfo(email=ExtractedStr(value="anita@example.com")),
        education=[EducationEntry(degree="B.Tech")],
        skills=[SkillItem(name="Python")],
    )
    cov = assess_coverage(text, profile, min_chars=50)
    assert cov.band is CoverageBand.COMPLETE
    assert cov.gaps == []


def test_unrecognized_header_is_minor_when_nothing_was_dropped():
    # R5: the brief's fixture paired an empty `experience=[]` with a name
    # that claims nothing was dropped, so experience_not_extracted fired
    # alongside the hint this test is named for. Under R3's evidence gate,
    # "CAREER HISTORY"'s two dated bullet lines are real experience
    # evidence, so a genuinely empty profile.experience here is itself the
    # measured defect from test_dropped_experience_is_a_major_gap, not an
    # isolated MINOR case. Give the profile a real experience entry so the
    # only gap left is the unrecognized-header hint.
    text = BULLETED.replace("EXPERIENCE", "CAREER HISTORY")
    profile = _profile(
        contact=ContactInfo(email=ExtractedStr(value="priya@example.com")),
        education=[EducationEntry(degree="B.Tech")],
        skills=[SkillItem(name="Python")],
        experience=[ExperienceEntry(title="Senior Data Engineer", employer="Acme Analytics")],
    )
    cov = assess_coverage(text, profile, min_chars=50)
    ids = {g.id for g in cov.gaps}
    assert "section_unrecognized" in ids
    hint = next(g for g in cov.gaps if g.id == "section_unrecognized")
    assert hint.severity is GapSeverity.MINOR
    assert hint.header == "CAREER HISTORY"


def test_header_quote_is_bounded():
    # R5: the brief's 21-word header ("Career " + "History " * 20) is not
    # header-shaped at all (is_header_shaped caps at 5 words), so no block
    # ever opens under it and no gap ever carries a `header` -- the
    # assertion loop below ran zero times. Build a header that IS
    # header-shaped (3 words, title-cased) but longer than max_header_chars,
    # over a block with a dated line so R3's evidence gate actually opens.
    long_header = "Professional Journey History"
    assert len(long_header) > 20  # longer than the max_header_chars used below
    text = (
        "Priya Sharma\n"
        "priya@example.com\n"
        "\n"
        f"{long_header}\n"
        "Led the platform team (2019 - Present)\n"
    )
    cov = assess_coverage(text, _profile(), min_chars=50, max_header_chars=20)
    quoted_headers = [gap.header for gap in cov.gaps if gap.header is not None]
    assert quoted_headers, "expected at least one gap to carry a header"
    for header in quoted_headers:
        assert len(header) <= 20


def test_gaps_are_capped_and_say_so():
    # R5: the brief's "Section N" / "content N" blocks carry no dated or
    # academic evidence, so under R3's gate none of them produced a gap and
    # the cap was never reached. Give each block a dated content line so
    # every one of the 30 blocks trips section_unrecognized.
    text = BULLETED + "\n" + "\n".join(
        f"Section {i}\ncontent {i} role (2019 - 2020)" for i in range(30)
    )
    cov = assess_coverage(text, _profile(), min_chars=50, max_gaps=3)
    assert len(cov.gaps) == 3
    assert cov.truncated is True


def test_education_not_extracted_fires_on_real_evidence():
    """Positive-fire coverage for check 2 (review finding 2): real academic
    evidence in the text, paired with a genuinely empty profile.education."""
    text = """Anita Rao
anita@example.com

EDUCATION
B.Tech in Computer Science, VIT Vellore, 2019 - 2023, CGPA: 8.1/10
"""
    profile = _profile(
        contact=ContactInfo(email=ExtractedStr(value="anita@example.com")),
        skills=[SkillItem(name="Python")],
        education=[],  # deliberately empty -- the check under test
    )
    cov = assess_coverage(text, profile, min_chars=50)
    ids = {g.id for g in cov.gaps}
    assert "education_not_extracted" in ids
    gap = next(g for g in cov.gaps if g.id == "education_not_extracted")
    assert gap.severity is GapSeverity.MAJOR
    assert gap.field == "education"


def test_skills_not_extracted_fires_on_a_bare_comma_list():
    """Positive-fire coverage for check 3, and the regression test for the
    reviewer's Finding 1. Before R10, "Python, SQL, Pandas" read as
    header-shaped itself: it opened its own (empty-content) block, stealing
    the text out from under the SKILLS block, so skill_content was always
    empty and check 3 could never fire -- assess_coverage reported
    `complete` on a resume with a populated skills section and an empty
    profile.skills. This test fails against that bug and passes once
    is_header_shaped() rejects comma-delimited lines."""
    text = """Anita Rao
anita@example.com

SKILLS
Python, SQL, Pandas
"""
    profile = _profile(
        contact=ContactInfo(email=ExtractedStr(value="anita@example.com")),
        education=[EducationEntry(degree="B.Tech")],
        skills=[],  # deliberately empty -- the check under test
    )
    cov = assess_coverage(text, profile, min_chars=50)
    ids = {g.id for g in cov.gaps}
    assert "skills_not_extracted" in ids
    gap = next(g for g in cov.gaps if g.id == "skills_not_extracted")
    assert gap.severity is GapSeverity.MAJOR
    assert gap.field == "skills"


def test_contact_not_extracted_fires_on_real_evidence():
    """Positive-fire coverage for check 4: real email/phone text, paired
    with a genuinely empty profile.contact."""
    text = """Anita Rao
anita@example.com  +91 98765 43210

EDUCATION
B.Tech in Computer Science, VIT Vellore, 2019 - 2023, CGPA: 8.1/10
"""
    profile = _profile(
        education=[EducationEntry(degree="B.Tech")],
        skills=[SkillItem(name="Python")],
        # contact deliberately left at its default (empty) -- the check under test
    )
    cov = assess_coverage(text, profile, min_chars=50)
    ids = {g.id for g in cov.gaps}
    assert "contact_not_extracted" in ids
    gap = next(g for g in cov.gaps if g.id == "contact_not_extracted")
    assert gap.severity is GapSeverity.MAJOR
    assert gap.field == "contact"


def test_unrecognized_skills_header_fires_via_header_fallback():
    """R3's gate has two doors in: dated/academic evidence in the block's
    content, or the header itself reading as a skills section. A bare tools
    list carries neither a year nor a degree word, so evidence alone would
    never catch a skills-shaped section under a name the extractor does not
    recognize -- this isolates that second door: the block's content has no
    dated or academic line at all."""
    text = (
        "Priya Sharma\n"
        "priya@example.com\n"
        "\n"
        "TECH STACK\n"
        "Python, SQL, Pandas\n"
    )
    profile = _profile(
        contact=ContactInfo(email=ExtractedStr(value="priya@example.com")),
        skills=[SkillItem(name="Python")],
    )
    cov = assess_coverage(text, profile, min_chars=50)
    ids = {g.id for g in cov.gaps}
    assert "section_unrecognized" in ids
    hint = next(g for g in cov.gaps if g.id == "section_unrecognized")
    assert hint.severity is GapSeverity.MINOR
    assert hint.header == "TECH STACK"


import json

from app.candidates.extractor import extract_profile
from app.services.llm import NullLLM
from tests.conftest import FakeLLM


@pytest.mark.asyncio
async def test_both_extraction_paths_are_measured_by_the_same_instrument():
    """The LLM path drops things too, and _is_empty is an ALL-of check that
    waves a partial LLM profile straight through. A rule applied at one door and
    not the other is this repo's signature defect (S7.1, S7.2, S7.3, S8.4a).

    S9.2 Task 8 fixed BULLETED's own defect (an all-bulleted EXPERIENCE section
    now extracts as roles, not zero entries), so the heuristic side of this
    comparison no longer shows a gap on this text -- correctly. That divergence
    is now the stronger proof: the SAME instrument, called on the SAME resume
    text, reports COMPLETE for the path that actually extracted the experience
    and MAJOR_GAPS for the path whose payload dropped it, which only happens if
    both doors are genuinely, independently measured rather than one hard-wired
    to the other."""
    settings = Settings(_env_file=None, openrouter_api_key="")

    heuristic = await extract_profile(BULLETED, llm=NullLLM(settings), settings=settings)

    # An LLM that returns a plausible profile with NO experience at all.
    payload = json.dumps({
        "full_name": {"value": "Priya Sharma", "confidence": 0.9, "source_excerpt": "Priya Sharma"},
        "contact": {"email": {"value": "priya@example.com", "confidence": 0.9,
                              "source_excerpt": "priya@example.com"}},
        "education": [{"degree": "B.Tech", "institution": "IIT Delhi", "confidence": 0.8,
                       "source_excerpt": "B.Tech"}],
        "skills": [{"name": "Python", "confidence": 0.8, "source_excerpt": "Python"}],
        "experience": [],
    })
    llm_result = await extract_profile(
        BULLETED, llm=FakeLLM({"RESUME:": payload}, settings), settings=settings
    )

    assert llm_result.method == "llm"
    assert heuristic.coverage.band is CoverageBand.COMPLETE
    assert "experience_not_extracted" not in {g.id for g in heuristic.coverage.gaps}
    assert llm_result.coverage.band is CoverageBand.MAJOR_GAPS
    assert "experience_not_extracted" in {g.id for g in llm_result.coverage.gaps}
