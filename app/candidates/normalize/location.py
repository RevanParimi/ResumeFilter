"""Indian city gazetteer + notice-period parsing (S1.4).

Both scanners work on RAW text and return character offsets, so the
extractor can attach SourceSpan provenance. City tiers ("metro"/"tier_2")
are talent-market metadata, not judgments. Notice period: days=0 means
immediate joiner; days=None means stated but unquantified ("serving
notice"); a missing statement returns None outright.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional


class CityFind(NamedTuple):
    city: str   # canonical display name
    tier: str   # "metro" | "tier_2"
    start: int
    end: int
    text: str   # matched substring, verbatim


class NoticeFind(NamedTuple):
    days: Optional[int]
    start: int
    end: int
    text: str


# canonical display name: (tier, aliases). Aliases are matched as whole
# words, case-insensitively, against raw text.
_CITIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "Bengaluru": ("metro", ("bengaluru", "bangalore")),
    "Mumbai": ("metro", ("mumbai", "bombay", "navi mumbai")),
    "Delhi": ("metro", ("new delhi", "delhi")),
    "Gurugram": ("metro", ("gurugram", "gurgaon")),
    "Noida": ("metro", ("noida",)),
    "Hyderabad": ("metro", ("hyderabad", "secunderabad")),
    "Chennai": ("metro", ("chennai", "madras")),
    "Kolkata": ("metro", ("kolkata", "calcutta")),
    "Pune": ("metro", ("pune",)),
    "Ahmedabad": ("metro", ("ahmedabad",)),
    "Jaipur": ("tier_2", ("jaipur",)),
    "Lucknow": ("tier_2", ("lucknow",)),
    "Indore": ("tier_2", ("indore",)),
    "Bhopal": ("tier_2", ("bhopal",)),
    "Nagpur": ("tier_2", ("nagpur",)),
    "Chandigarh": ("tier_2", ("chandigarh", "mohali", "panchkula")),
    "Kochi": ("tier_2", ("kochi", "cochin", "ernakulam")),
    "Thiruvananthapuram": ("tier_2", ("thiruvananthapuram", "trivandrum")),
    "Coimbatore": ("tier_2", ("coimbatore",)),
    "Mysuru": ("tier_2", ("mysuru", "mysore")),
    "Visakhapatnam": ("tier_2", ("visakhapatnam", "vizag")),
    "Bhubaneswar": ("tier_2", ("bhubaneswar",)),
    "Surat": ("tier_2", ("surat",)),
    "Vadodara": ("tier_2", ("vadodara", "baroda")),
    "Trichy": ("tier_2", ("trichy", "tiruchirappalli")),
    "Madurai": ("tier_2", ("madurai",)),
    "Kanpur": ("tier_2", ("kanpur",)),
    "Patna": ("tier_2", ("patna",)),
    "Guwahati": ("tier_2", ("guwahati",)),
    "Dehradun": ("tier_2", ("dehradun",)),
    "Nashik": ("tier_2", ("nashik",)),
    "Mangaluru": ("tier_2", ("mangaluru", "mangalore")),
}

_ALIAS_TO_CITY: dict[str, tuple[str, str]] = {
    alias: (city, tier)
    for city, (tier, aliases) in _CITIES.items()
    for alias in aliases
}

# Longest alias first so "new delhi" wins over "delhi" at the same position.
# Aliases are strictly [a-z ] (asserted below), so no re.escape is needed —
# re.escape would backslash the spaces and break the \s+ substitution.
assert all(a.replace(" ", "").isalpha() for a in _ALIAS_TO_CITY)
_CITY_RE = re.compile(
    r"\b(?:"
    + "|".join(
        a.replace(" ", r"\s+")
        for a in sorted(_ALIAS_TO_CITY, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)


def find_city(text: str) -> Optional[CityFind]:
    m = _CITY_RE.search(text or "")
    if not m:
        return None
    alias = re.sub(r"\s+", " ", m.group(0).lower())
    city, tier = _ALIAS_TO_CITY[alias]
    return CityFind(city=city, tier=tier, start=m.start(), end=m.end(), text=m.group(0))


_UNIT_DAYS = {"day": 1, "week": 7, "month": 30}

_NP_LABELLED = re.compile(
    r"notice\s*period\s*[:\-–]?\s*"
    r"(?:(?P<imm>immediate(?:ly)?)|(?P<num>\d{1,3})\s*(?P<unit>day|week|month)s?)",
    re.IGNORECASE,
)
_NP_INLINE = re.compile(
    r"\b(?P<num>\d{1,3})\s*(?P<unit>day|week|month)s?['’]?\s*(?:of\s+)?notice\b",
    re.IGNORECASE,
)
_NP_IMMEDIATE = re.compile(
    r"\b(?:immediate\s+joiner|available\s+immediately|immediately\s+available)\b",
    re.IGNORECASE,
)
_NP_SERVING = re.compile(
    r"\bserving\s+(?:my\s+)?notice(?:\s+period)?\b", re.IGNORECASE
)
# Whole-string bare value ("30 days", "Immediate") — how an LLM-extracted
# notice_period.value arrives. Anchored, so resume-body scans never hit it.
_NP_BARE = re.compile(
    r"^\s*(?:(?P<imm>immediate(?:ly)?(?:\s+joiner)?)"
    r"|(?P<num>\d{1,3})\s*(?P<unit>day|week|month)s?)\s*$",
    re.IGNORECASE,
)


def _days(m: re.Match) -> Optional[int]:
    if m.groupdict().get("imm"):
        return 0
    return int(m.group("num")) * _UNIT_DAYS[m.group("unit").lower()]


def parse_notice_period(text: str) -> Optional[NoticeFind]:
    text = text or ""
    for pattern in (_NP_LABELLED, _NP_INLINE):
        m = pattern.search(text)
        if m:
            return NoticeFind(days=_days(m), start=m.start(), end=m.end(), text=m.group(0))
    m = _NP_IMMEDIATE.search(text)
    if m:
        return NoticeFind(days=0, start=m.start(), end=m.end(), text=m.group(0))
    m = _NP_SERVING.search(text)
    if m:
        return NoticeFind(days=None, start=m.start(), end=m.end(), text=m.group(0))
    m = _NP_BARE.match(text)
    if m:
        return NoticeFind(days=_days(m), start=m.start(), end=m.end(), text=m.group(0))
    return None
