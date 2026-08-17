"""Static comp prior + deterministic role-signal resolution (S5.2).

ILLUSTRATIVE, LICENSE-CLEAN SEED DATA. The per-role figures below are
hand-authored, order-of-magnitude annual FIXED CTC (INR) for the IT launch
vertical -- NOT scraped or licensed. An operator replaces them by pointing
`comp_bands_path` at a JSON file keyed "role_family|seniority|city_tier" ->
[fixed_low, fixed_mid, fixed_high, variable_fraction]. The engine is
source-agnostic; only this module knows the numbers.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from app.candidates.normalize.text import norm_key
from app.core.config import Settings, get_settings
from app.comp.schema import (
    CITY_TIERS, DEFAULT_ROLE_FAMILY, ROLE_FAMILIES, RoleSignal, SeniorityBand,
)
from app.matching.schema import JobRequisition

CompCell = tuple[float, float, float, float]  # fixed_low, fixed_mid, fixed_high, var_frac

# Per-role metro MID fixed CTC (annual INR). Illustrative seed.
_ROLE_METRO_MID_FIXED: dict[str, float] = {
    "backend_engineer": 1_800_000.0,
    "frontend_engineer": 1_600_000.0,
    "fullstack_engineer": 1_800_000.0,
    "data_engineer": 1_900_000.0,
    "data_scientist": 2_000_000.0,
    "ml_engineer": 2_200_000.0,
    "devops_sre": 2_000_000.0,
    "qa_engineer": 1_300_000.0,
    "mobile_engineer": 1_700_000.0,
    "engineering_manager": 3_200_000.0,
}
_SENIORITY_MULT: dict[SeniorityBand, float] = {
    SeniorityBand.JUNIOR: 0.55,
    SeniorityBand.MID: 1.0,
    SeniorityBand.SENIOR: 1.7,
    SeniorityBand.LEAD: 2.6,
}
_TIER_MULT: dict[str, float] = {"metro": 1.0, "tier_2": 0.75}
_VARIABLE_FRACTION: dict[str, float] = {"engineering_manager": 0.20}
_DEFAULT_VARIABLE_FRACTION = 0.12
_SPREAD = 0.22  # low = mid*(1-spread), high = mid*(1+spread)

# Title substrings -> role family, most specific first (first hit wins).
_TITLE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("engineering manager", "engineering_manager"),
    ("data engineer", "data_engineer"),
    ("data scientist", "data_scientist"),
    ("data science", "data_scientist"),
    ("machine learning", "ml_engineer"),
    ("ml engineer", "ml_engineer"),
    ("mlops", "ml_engineer"),
    ("devops", "devops_sre"),
    ("site reliability", "devops_sre"),
    ("sre", "devops_sre"),
    ("platform engineer", "devops_sre"),
    ("sdet", "qa_engineer"),
    ("test engineer", "qa_engineer"),
    ("quality", "qa_engineer"),
    (" qa", "qa_engineer"),
    ("mobile", "mobile_engineer"),
    ("android", "mobile_engineer"),
    ("ios", "mobile_engineer"),
    ("full stack", "fullstack_engineer"),
    ("fullstack", "fullstack_engineer"),
    ("full-stack", "fullstack_engineer"),
    ("front end", "frontend_engineer"),
    ("frontend", "frontend_engineer"),
    ("front-end", "frontend_engineer"),
    ("backend", "backend_engineer"),
    ("back-end", "backend_engineer"),
    ("manager", "engineering_manager"),
)

# norm_key(skill) -> role family, for the secondary (skill-signature) vote.
_SKILL_FAMILY: dict[str, str] = {
    norm_key(k): v
    for k, v in {
        "react": "frontend_engineer", "angular": "frontend_engineer",
        "vue": "frontend_engineer", "css": "frontend_engineer",
        "html": "frontend_engineer", "typescript": "frontend_engineer",
        "kubernetes": "devops_sre", "docker": "devops_sre",
        "terraform": "devops_sre", "ansible": "devops_sre", "jenkins": "devops_sre",
        "spark": "data_engineer", "hadoop": "data_engineer",
        "airflow": "data_engineer", "kafka": "data_engineer",
        "pandas": "data_scientist", "numpy": "data_scientist",
        "scikit learn": "data_scientist", "statistics": "data_scientist",
        "pytorch": "ml_engineer", "tensorflow": "ml_engineer", "nlp": "ml_engineer",
        "android": "mobile_engineer", "kotlin": "mobile_engineer",
        "swift": "mobile_engineer", "flutter": "mobile_engineer",
        "python": "backend_engineer", "java": "backend_engineer",
        "golang": "backend_engineer", "node": "backend_engineer",
        "django": "backend_engineer", "spring": "backend_engineer",
    }.items()
}


@lru_cache(maxsize=8)
def _load_override(path: str) -> dict[tuple[str, str, str], CompCell]:
    """Parse an operator override JSON. Missing/broken file -> empty (seed wins)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return {}
    out: dict[tuple[str, str, str], CompCell] = {}
    for key, cell in raw.items():
        parts = key.split("|")
        if len(parts) == 3 and isinstance(cell, list) and len(cell) == 4:
            out[(parts[0], parts[1], parts[2])] = (
                float(cell[0]), float(cell[1]), float(cell[2]), float(cell[3])
            )
    return out


def _computed_cell(signal: RoleSignal) -> CompCell:
    base = _ROLE_METRO_MID_FIXED.get(signal.role_family, _ROLE_METRO_MID_FIXED[DEFAULT_ROLE_FAMILY])
    mid = base * _SENIORITY_MULT[signal.seniority] * _TIER_MULT[signal.city_tier]
    var = _VARIABLE_FRACTION.get(signal.role_family, _DEFAULT_VARIABLE_FRACTION)
    return (mid * (1 - _SPREAD), mid, mid * (1 + _SPREAD), var)


def lookup_cell(signal: RoleSignal, settings: Optional[Settings] = None) -> CompCell:
    s = settings or get_settings()
    if s.comp_bands_path:
        override = _load_override(s.comp_bands_path)
        cell = override.get((signal.role_family, signal.seniority.value, signal.city_tier))
        if cell is not None:
            return cell
    return _computed_cell(signal)


def resolve_role_family(
    skills: tuple[str, ...], title: Optional[str], settings: Optional[Settings] = None
) -> str:
    if title:
        low = title.lower()
        for kw, fam in _TITLE_KEYWORDS:
            if kw in low:
                return fam
    votes: dict[str, int] = {}
    for sk in skills:
        fam = _SKILL_FAMILY.get(norm_key(sk))
        if fam:
            votes[fam] = votes.get(fam, 0) + 1
    if votes:
        top = max(votes.values())
        return sorted(f for f, c in votes.items() if c == top)[0]  # deterministic tie-break
    return DEFAULT_ROLE_FAMILY


def resolve_seniority(
    years: Optional[float], settings: Optional[Settings] = None
) -> SeniorityBand:
    s = settings or get_settings()
    if years is None:
        return SeniorityBand.MID  # unknown -> neutral
    if years < s.comp_mid_years:
        return SeniorityBand.JUNIOR
    if years < s.comp_senior_years:
        return SeniorityBand.MID
    if years < s.comp_lead_years:
        return SeniorityBand.SENIOR
    return SeniorityBand.LEAD


def resolve_city_tier(
    location_tiers: Optional[tuple[str, ...]], remote: bool, settings: Optional[Settings] = None
) -> str:
    if location_tiers:
        t = location_tiers[0]
        if t in CITY_TIERS:
            return t
    return "metro"  # remote / unknown -> metro baseline


def role_signal_from_input(
    *,
    skills: tuple[str, ...] = (),
    title: Optional[str] = None,
    years: Optional[float] = None,
    location_tiers: Optional[tuple[str, ...]] = None,
    remote: bool = False,
    role_family: Optional[str] = None,
    seniority: Optional[SeniorityBand] = None,
    settings: Optional[Settings] = None,
) -> RoleSignal:
    s = settings or get_settings()
    if role_family is not None and role_family not in ROLE_FAMILIES:
        raise ValueError(f"role_family must be one of {ROLE_FAMILIES}")
    rf = role_family or resolve_role_family(tuple(skills), title, s)
    sen = seniority or resolve_seniority(years, s)
    tier = resolve_city_tier(tuple(location_tiers) if location_tiers else None, remote, s)
    return RoleSignal(role_family=rf, seniority=sen, city_tier=tier)


def role_signal_from_requisition(
    req: JobRequisition, settings: Optional[Settings] = None
) -> RoleSignal:
    s = settings or get_settings()
    return RoleSignal(
        role_family=resolve_role_family(tuple(req.must_have_skills), req.title, s),
        seniority=resolve_seniority(req.min_years_experience, s),
        city_tier=resolve_city_tier(
            tuple(req.location_tiers) if req.location_tiers else None, req.remote, s
        ),
    )
