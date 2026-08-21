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

from app.candidates.sections import SECTION_ALIASES

#: Our own year scanner. Deliberately not app.candidates.dates.date_points.
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_PRESENT = re.compile(r"\b(?:present|current|till date|to date|ongoing|now)\b", re.IGNORECASE)
#: Broader than the extractor's _DEGREE on purpose -- this is the check that has
#: to still fire when the extractor's regex is the thing that is wrong.
_DEGREE_WORDS = (
    "bachelor", "master", "b.tech", "btech", "m.tech", "mtech", "b.e", "b.sc",
    "m.sc", "bca", "mca", "mba", "bba", "b.com", "m.com", "b.a", "m.a",
    "phd", "ph.d", "diploma", "degree", "graduation", "post graduate",
)
_GRADEISH = re.compile(r"\b(?:cgpa|gpa|percentage|marks)\b|\d{2,3}(?:\.\d+)?\s*%", re.IGNORECASE)
_EMAILISH = re.compile(r"[^\s@]+@[^\s@]+\.[A-Za-z]{2,}")
_PHONEISH = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)")
_BULLETISH = re.compile(r"^[-•*·]\s*")


def is_header_shaped(line: str) -> bool:
    """A short, capitalised, undated line that reads like a section header."""
    s = _BULLETISH.sub("", line).strip().rstrip(":").strip()
    if not s or len(s) > 48:
        return False
    if _YEAR.search(s) or "@" in s:
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


def blocks(text: str) -> list[tuple[Optional[str], list[str]]]:
    """[(header or None, [content lines])]. The first block's header is None."""
    out: list[tuple[Optional[str], list[str]]] = [(None, [])]
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if is_header_shaped(line):
            out.append((line, []))
        else:
            out[-1][1].append(line)
    return out


def looks_academic(line: str) -> bool:
    """A degree word or a grade token -- education evidence, not a role."""
    low = line.lower()
    return any(w in low for w in _DEGREE_WORDS) or bool(_GRADEISH.search(line))


def looks_dated_role(line: str) -> bool:
    """Two year tokens, or one plus a Present-style marker."""
    years = _YEAR.findall(line)
    if len(years) >= 2:
        return True
    return len(years) == 1 and bool(_PRESENT.search(line))


def known_aliases() -> dict[str, str]:
    """alias -> section, from the shared declaration (R1)."""
    return {a: s for s, aliases in SECTION_ALIASES.items() for a in aliases}
