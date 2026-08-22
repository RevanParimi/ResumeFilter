"""Deterministic date parsing for resume career lines.

Handles the formats Indian resumes actually use: 'Jun 2021 - Present',
'January 2020 to March 2022', '2014 - 2018', '03/2021 - 06/2023'. Points are
kept as "YYYY-MM"/"YYYY" strings (see DateRange). No LLM anywhere.
"""

from __future__ import annotations

import re

from app.candidates.schema import DateRange

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_YEAR = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_NUMERIC_MY = re.compile(r"\b(0?[1-9]|1[0-2])[/-]((?:19|20)\d{2})\b")
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_PRESENT = re.compile(r"\b(present|current|till date|ongoing|now)\b", re.IGNORECASE)


def date_spans(text: str) -> list[tuple[int, int, str]]:
    """All (start, end, 'YYYY-MM'|'YYYY') date tokens, in order of appearance.

    Superset of date_points() that also carries the match's END offset, which
    date_points() drops -- extractor.py's role-vs-duty check (S9.2 fix 1, C2
    review) needs the end of the LAST date token to see what, if anything,
    trails it in the line.
    """
    found: list[tuple[int, int, str]] = []  # (start, end, value)
    for m in _MONTH_YEAR.finditer(text):
        month = _MONTHS[m.group(1).lower()[:3]]
        found.append((m.start(), m.end(), f"{m.group(2)}-{month:02d}"))
    for m in _NUMERIC_MY.finditer(text):
        found.append((m.start(), m.end(), f"{m.group(2)}-{int(m.group(1)):02d}"))
    covered = [(s, e) for s, e, _ in found]
    for m in _YEAR.finditer(text):
        if not any(s <= m.start() < e for s, e in covered):
            found.append((m.start(), m.end(), m.group(1)))
    found.sort()
    return found


def date_points(text: str) -> list[tuple[int, str]]:
    """All (position, 'YYYY-MM'|'YYYY') date tokens, in order of appearance."""
    return [(s, v) for s, _, v in date_spans(text)]


def parse_date_range(text: str) -> DateRange:
    points = date_points(text)
    current = bool(_PRESENT.search(text))
    if not points:
        return DateRange(is_current=current)
    start = points[0][1]
    end = points[1][1] if len(points) > 1 else None
    return DateRange(start=start, end=end, is_current=current and end is None)


def has_date_range(text: str) -> bool:
    """True when a line reads like a dated career entry: two date points, or
    one point plus a 'Present'-style marker."""
    points = date_points(text)
    return len(points) >= 2 or (len(points) == 1 and bool(_PRESENT.search(text)))
