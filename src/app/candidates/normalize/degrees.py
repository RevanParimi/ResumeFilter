"""Indian degree canonicalization + grade normalization (S1.4).

Canonical grade scale is CGPA on the 10-point scale: cgpa_10 passes through,
cgpa_4 scales by 2.5, percentage divides by 9.5 (the CBSE convention) and
clamps to 10. Out-of-range or unknown-scale claims return None — the raw
claim stays untouched on the profile for PI-2 forensics.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

from app.candidates.normalize.text import norm_key


class DegreeMatch(NamedTuple):
    canonical: str
    level: str  # "diploma" | "bachelor" | "master" | "doctorate"


# canonical_id: (level, aliases). Indexed via norm_key ("B.E." -> "b e").
_DEGREES: dict[str, tuple[str, tuple[str, ...]]] = {
    "btech": ("bachelor", ("b.tech", "btech", "b tech", "bachelor of technology")),
    "be": ("bachelor", ("b.e", "b.e.", "be", "bachelor of engineering")),
    "bsc": ("bachelor", ("b.sc", "bsc", "bachelor of science")),
    "bca": ("bachelor", ("bca", "bachelor of computer applications")),
    "bcom": ("bachelor", ("b.com", "bcom", "bachelor of commerce")),
    "ba": ("bachelor", ("b.a", "ba", "bachelor of arts")),
    "bba": ("bachelor", ("bba", "bachelor of business administration")),
    "mtech": ("master", ("m.tech", "mtech", "m tech", "master of technology")),
    "me": ("master", ("m.e", "m.e.", "me", "master of engineering")),
    "msc": ("master", ("m.sc", "msc", "master of science")),
    "ms": ("master", ("m.s", "ms")),
    "mca": ("master", ("mca", "master of computer applications")),
    "mba": ("master", ("mba", "master of business administration")),
    "pgdm": ("master", ("pgdm", "post graduate diploma in management")),
    "mcom": ("master", ("m.com", "mcom", "master of commerce")),
    "ma": ("master", ("m.a", "ma", "master of arts")),
    "phd": ("doctorate", ("ph.d", "phd", "ph d", "doctor of philosophy")),
    "diploma": ("diploma", ("diploma", "polytechnic", "polytechnic diploma")),
}


def _build_index() -> dict[str, DegreeMatch]:
    index: dict[str, DegreeMatch] = {}
    for canonical, (level, aliases) in _DEGREES.items():
        match = DegreeMatch(canonical=canonical, level=level)
        for alias in aliases:
            key = norm_key(alias)
            existing = index.get(key)
            if existing is not None and existing != match:  # taxonomy bug
                raise ValueError(
                    f"degree alias {alias!r} claimed by {existing.canonical} and {canonical}"
                )
            index[key] = match
    return index


_INDEX = _build_index()
_KEYS_BY_LENGTH = sorted(_INDEX, key=len, reverse=True)


def normalize_degree(degree: str) -> Optional[DegreeMatch]:
    key = norm_key(degree or "")
    if not key:
        return None
    hit = _INDEX.get(key)
    if hit:
        return hit
    # Degree strings often carry the field inline ("B.Tech in CS"): fall back
    # to the LONGEST known alias found as a whole word inside the key.
    for alias_key in _KEYS_BY_LENGTH:
        if re.search(rf"(?<![\w+#]){re.escape(alias_key)}(?![\w+#])", key):
            return _INDEX[alias_key]
    return None


def normalize_grade(value: Optional[float], scale: Optional[str]) -> Optional[float]:
    """Claimed grade -> canonical CGPA/10, or None when it can't be trusted."""
    if value is None or scale is None:
        return None
    if scale == "cgpa_10":
        return round(value, 2) if 0 <= value <= 10 else None
    if scale == "cgpa_4":
        return round(value * 2.5, 2) if 0 <= value <= 4 else None
    if scale == "percentage":
        return round(min(value / 9.5, 10.0), 2) if 0 <= value <= 100 else None
    return None
