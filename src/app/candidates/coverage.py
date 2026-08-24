"""Extraction coverage (S9.2): what the resume evidently says that the
extracted profile does not carry.

THIS MODULE DOES NOT SHARE THE EXTRACTOR'S EYES, and that is the whole design.
An instrument that detects evidence with the same code the extractor parses
with cannot see that code's blind spot: point this file at `_DEGREE` and the
moment S9.2 widens `_DEGREE` the education check stops firing, while leaving it
narrow makes the check agree with the extractor that there was nothing there.
Either way it reports `complete` on the exact resume it exists to catch.

So every scanner below is deliberately cruder than the extractor's: broad word
lists and a bare four-digit-year regex, owned here. `app.candidates.extractor`
and `app.candidates.dates` must never appear in this file's imports --
tests/test_extraction_coverage_independence.py fails the build if they do.

The one thing it does import is SECTION_ALIASES, which is a DECLARATION rather
than detection logic (plan ruling R1): the `section_unrecognized` gap is defined
in terms of what the extractor recognizes, so it cannot avoid knowing the list.
That gap is a HINT, not a detector -- if header handling breaks, the check that
actually fires is `experience_not_extracted`, which consults no table at all.
"""

from __future__ import annotations

import re
from typing import Optional

from app.candidates.schema import CandidateProfile
from app.candidates.sections import SECTION_ALIASES
from app.schemas.extraction import (
    CoverageBand,
    CoverageGap,
    ExtractionCoverage,
    GapSeverity,
)

#: Our own year scanner. Deliberately not app.candidates.dates.date_points.
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_PRESENT = re.compile(r"\b(?:present|current|till date|to date|ongoing|now)\b", re.IGNORECASE)
#: Broader than the extractor's _DEGREE on purpose -- this is the check that has
#: to still fire when the extractor's regex is the thing that is wrong. It keeps
#: four tokens the extractor has never had ("degree", "graduation", "post
#: graduate", "doctorate"), which is what "broader" means here.
#:
#: MATCHED ON WORD BOUNDARIES, NOT AS SUBSTRINGS. This was a tuple tested with
#: `w in low`, and `b.com` lives inside `github.com` -- so every resume carrying
#: a GitHub link read as degree-bearing and raised a false
#: `education_not_extracted` whenever education was genuinely absent. In a
#: tech-hiring product that is most resumes. The same bug reached `b.sc` inside
#: `web.scan` and `m.a` inside `team.access`.
#:
#: The two-letter abbreviations REQUIRE their dot. Spelling them with an
#: OPTIONAL dot would match the bare English words "be" and "ma", trading a URL
#: false positive for a much commoner prose one.
_DEGREE_PATTERN = re.compile(
    r"\b(?:"
    r"bachelors?|masters?|doctorate|"
    r"b\.?\s?tech|m\.?\s?tech|"
    r"b\.?\s?sc|m\.?\s?sc|b\.?\s?com|m\.?\s?com|"
    r"bca|mca|mba|bba|ph\.?\s?d|"
    r"diploma|degree|graduation|post[\s-]?graduate"
    r")\b"
    r"|\b(?:b\.e|m\.e|b\.a|m\.a)\b",
    re.IGNORECASE,
)

#: Stripped before the degree test. An explicit URL or an email address cannot
#: be a degree, and its host half is exactly where the substring bug lived.
#: BARE domains are deliberately NOT stripped: "B.Com" is indistinguishable from
#: one, so a bare-domain rule would delete the very degree this is looking for.
#: Word boundaries already cover bare `github.com` -- there is no boundary
#: between the "u" and the "b".
_LINKISH = re.compile(r"(?:https?://|www\.)\S+|[^\s@]+@[^\s@]+\.[A-Za-z]{2,}", re.IGNORECASE)
_GRADEISH = re.compile(r"\b(?:cgpa|gpa|percentage|marks)\b|\d{2,3}(?:\.\d+)?\s*%", re.IGNORECASE)
_EMAILISH = re.compile(r"[^\s@]+@[^\s@]+\.[A-Za-z]{2,}")
_PHONEISH = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)")
_PHONE_MIN_DIGITS = 10
_BULLETISH = re.compile(r"^[-•*·]\s*")
_EDU_HEADER = re.compile(r"education|academic|qualification", re.IGNORECASE)
_SKILL_HEADER = re.compile(r"skill|technolog|competenc|tech stack", re.IGNORECASE)
#: Plan ruling R10: a delimited list ("Python, SQL, Pandas", "Title | City")
#: is content, never a header. No SECTION_ALIASES entry contains any of these
#: ("licenses & certifications" uses "&", which stays allowed).
_LIST_DELIMITERS = ",;|·"


def is_header_shaped(line: str) -> bool:
    """A short, capitalised, undated line that reads like a section header."""
    s = _BULLETISH.sub("", line).strip().rstrip(":").strip()
    if not s or len(s) > 48:
        return False
    if _YEAR.search(s) or "@" in s:
        return False
    if any(ch in s for ch in _LIST_DELIMITERS):
        return False
    words = s.split()
    if not 1 <= len(words) <= 5:
        return False
    alpha = [w for w in words if w[:1].isalpha()]
    if not alpha:
        return False
    if s.isupper():
        return True
    return all(w[:1].isupper() for w in alpha)


def normalized_header(line: str) -> str:
    """Crude, coverage-owned header normalization: strip decoration and case.

    Intentionally NOT the extractor's version. If the two disagree, the
    disagreement is itself information (see the module docstring on R1).
    """
    s = _BULLETISH.sub("", line).strip().rstrip(":").strip()
    s = re.sub(r"\([^)]*\)", "", s)          # "WORK EXPERIENCE (5 YEARS)"
    s = re.sub(r"[ـ_\-–—=~]{2,}", "", s)      # "Experience ------"
    return " ".join(s.split()).strip(" :.-–—").lower()


def _is_strong_header_signal(
    line: str, aliases: dict[str, str], next_line: Optional[str] = None
) -> bool:
    """A second gate on top of is_header_shaped() (S9.2 C1/I3 review).

    is_header_shaped() alone also accepts short Title-Case content lines
    with no year and no list delimiter -- a single bullet item ("- Python"),
    a lone degree-name line ("B.Tech Computer Science") -- and each one
    silently opened its own EMPTY block, stealing the real section's
    content out from under its real header. A line only OPENS a block when
    it also carries a strong signal that it IS a header: ALL-CAPS, a
    trailing colon in the source line, a name the extractor itself
    recognizes, or (see the fourth door below) a bare list sitting under it.

    NEW-1 (S9.2 final review fix-wave regression): the three doors above
    left a Title-Case, unaliased header with no trailing colon -- "Tech
    Stack" over "Python, Django, PostgreSQL" -- opening no block at all, so
    checks 3 and 5 went silent under it. Measured: skills=[], band=complete,
    gaps=[] on a resume whose skills section was entirely dropped -- the
    exact failure this module exists to catch, back under a narrower
    trigger.

    Fourth door: a header-shaped Title-Case line counts as a header when the
    very next non-empty line is NOT itself header-shaped. A run of
    same-shape lines is a LIST, not a series of headers -- "- Python" / "-
    Java" / "- Kubernetes" under KEY SKILLS must stay a list (C1), and
    "Academic Credentials" / "B.Tech Computer Science" / "VIT Vellore" must
    stay unpromoted (I3), because each line's successor is itself
    header-shaped. The door also does not open when the next line, though
    not header-shaped, is a dated-role or academic CONTINUATION of the
    current line's own record rather than an unrelated list item -- "B.Tech
    Computer Science" over "VIT Vellore | 2019 - 2023" must not promote the
    degree line to a header, because that would hide it from check 2 and
    make the dated line under it misread as an unclaimed role (I3's exact
    original shape). One sub-case this does NOT fix, deliberately: "Key
    Skills" (Title-Case) over a bare one-per-line list ("Python" / "Java" /
    "Kubernetes") -- the next line IS itself header-shaped, so the door
    stays closed and check 3 stays silent there. See CANDIDATES.md's
    "Known limits" for why that is left as a recorded gap, not contorted
    away.
    """
    stripped = _BULLETISH.sub("", line).strip()
    if not stripped:
        return False
    if stripped.isupper():
        return True
    if stripped.endswith(":"):
        return True
    if normalized_header(line) in aliases:
        return True
    if next_line is None or is_header_shaped(next_line):
        return False
    return not (looks_dated_role(next_line) or looks_academic(next_line))


def blocks(text: str) -> list[tuple[Optional[str], list[str]]]:
    """[(header or None, [content lines])]. The first block's header is None.

    A line only opens a new block when it is header-SHAPED (is_header_shaped,
    the precondition) AND carries a strong header SIGNAL
    (_is_strong_header_signal). Shape alone is not enough -- see the review
    note on _is_strong_header_signal.
    """
    out: list[tuple[Optional[str], list[str]]] = [(None, [])]
    aliases = known_aliases()
    lines = [raw.strip() for raw in text.splitlines() if raw.strip()]
    for i, line in enumerate(lines):
        next_line = lines[i + 1] if i + 1 < len(lines) else None
        if is_header_shaped(line) and _is_strong_header_signal(line, aliases, next_line):
            out.append((line, []))
        else:
            out[-1][1].append(line)
    return out


def looks_academic(line: str) -> bool:
    """A degree word or a grade token -- education evidence, not a role."""
    cleaned = _LINKISH.sub(" ", line)
    return bool(_DEGREE_PATTERN.search(cleaned)) or bool(_GRADEISH.search(cleaned))


def looks_dated_role(line: str) -> bool:
    """Two year tokens, or one plus a Present-style marker."""
    years = _YEAR.findall(line)
    if len(years) >= 2:
        return True
    return len(years) == 1 and bool(_PRESENT.search(line))


def looks_like_phone(text: str) -> bool:
    """A phone-shaped token with at least _PHONE_MIN_DIGITS real digits.

    _PHONEISH's {8,} bound is a bound on the character CLASS length, which
    counts spaces/dashes/parens as well as digits -- so a bare year range
    ("2019 - 2021", 8 digits) cleared it (S9.2 I2 review). Requiring 10+
    actual digit characters in the matched token rejects any bare year
    range while keeping a 10-digit Indian mobile or an internationally
    prefixed number like "+91 98765 43210" (12 digits).
    """
    return any(
        sum(ch.isdigit() for ch in m.group(0)) >= _PHONE_MIN_DIGITS
        for m in _PHONEISH.finditer(text)
    )


def known_aliases() -> dict[str, str]:
    """alias -> section, from the shared declaration (R1)."""
    return {a: s for s, aliases in SECTION_ALIASES.items() for a in aliases}


def assess_coverage(
    text: str,
    profile: CandidateProfile,
    *,
    min_chars: int = 200,
    max_header_chars: int = 60,
    max_gaps: int = 20,
) -> ExtractionCoverage:
    """Compare the resume text with what was extracted from it.

    Every check fires on EMPTY, never on 'fewer than expected' (spec 3.3):
    telling one role spanning two lines from two roles needs a magic ratio, and
    a false positive there accuses a correct extraction.
    """
    if len((text or "").strip()) < min_chars:
        return ExtractionCoverage()  # refusal: no band, no gaps, nothing to read

    parsed = blocks(text)
    aliases = known_aliases()
    gaps: list[CoverageGap] = []

    # 1. experience --------------------------------------------------------
    role_lines = [
        line
        for header, content in parsed
        for line in content
        if not (header and _EDU_HEADER.search(header))
        and looks_dated_role(line)
        and not looks_academic(line)
    ]
    if role_lines and not profile.experience:
        gaps.append(CoverageGap(
            id="experience_not_extracted",
            detail=(
                f"the resume has {len(role_lines)} dated role-shaped line(s) but no "
                f"experience entry was extracted"
            ),
            severity=GapSeverity.MAJOR,
            field="experience",
        ))

    # 2. education ---------------------------------------------------------
    edu_lines = [
        line for _, content in parsed for line in content if looks_academic(line)
    ]
    if edu_lines and not profile.education:
        gaps.append(CoverageGap(
            id="education_not_extracted",
            detail=(
                f"the resume has {len(edu_lines)} degree- or grade-bearing line(s) but "
                f"no education entry was extracted"
            ),
            severity=GapSeverity.MAJOR,
            field="education",
        ))

    # 3. skills ------------------------------------------------------------
    skill_content = [
        content for header, content in parsed
        if header and _SKILL_HEADER.search(header) and content
    ]
    if skill_content and not profile.skills:
        gaps.append(CoverageGap(
            id="skills_not_extracted",
            detail="the resume has a populated skills section but no skill was extracted",
            severity=GapSeverity.MAJOR,
            field="skills",
        ))

    # 4. contact -----------------------------------------------------------
    has_contact_text = bool(_EMAILISH.search(text) or looks_like_phone(text))
    if has_contact_text and profile.contact.email is None and profile.contact.phone is None:
        gaps.append(CoverageGap(
            id="contact_not_extracted",
            detail="the resume carries an email or phone but neither was extracted",
            severity=GapSeverity.MAJOR,
            field="contact",
        ))

    # 5. unrecognized headers (a HINT, not a detector -- see the docstring) --
    # R3: gated on evidence. Without this, EVERY resume's identity line reads
    # as header-shaped (see test_blocks_groups_content_under_its_header), so
    # an ungated version of this check fires on almost every resume and
    # COMPLETE becomes unreachable. A block only counts as a hint if it also
    # carries the kind of evidence the other checks look for: a dated-role or
    # academic content line, or a header that itself reads as a skills
    # section (skills lines carry neither dates nor degree words, so they
    # need the header-pattern fallback).
    for header, content in parsed:
        if header is None or not content:
            continue
        if normalized_header(header) in aliases:
            continue
        has_role_or_academic_evidence = any(
            looks_dated_role(line) or looks_academic(line) for line in content
        )
        looks_like_skills_header = bool(_SKILL_HEADER.search(header))
        if not (has_role_or_academic_evidence or looks_like_skills_header):
            continue
        gaps.append(CoverageGap(
            id="section_unrecognized",
            detail="a section header the extractor does not recognize",
            severity=GapSeverity.MINOR,
            header=header.strip()[:max_header_chars],
        ))

    truncated = len(gaps) > max_gaps
    kept = gaps[:max_gaps]
    if any(g.severity is GapSeverity.MAJOR for g in kept):
        band = CoverageBand.MAJOR_GAPS
    elif kept:
        band = CoverageBand.MINOR_GAPS
    else:
        band = CoverageBand.COMPLETE
    return ExtractionCoverage(
        band=band, gaps=kept, checks_run=5, truncated=truncated, advisory=True
    )
