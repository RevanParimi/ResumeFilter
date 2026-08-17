"""India normalization (S1.4) — deterministic enrichment of CandidateProfile.

Pure functions over curated lookup tables; no LLM anywhere (nothing to
degrade). Claimed values are NEVER overwritten: canonical values land in
sibling fields and stay None when a value isn't in the tables — advisory
system, never guess.
"""

from __future__ import annotations

from app.candidates.normalize.degrees import normalize_degree, normalize_grade
from app.candidates.normalize.location import find_city, parse_notice_period
from app.candidates.normalize.orgs import (
    canonicalize_employer,
    canonicalize_institution,
)
from app.candidates.normalize.skills import normalize_skill
from app.candidates.schema import CandidateProfile


def normalize_profile(profile: CandidateProfile) -> CandidateProfile:
    """Enrich in place (and return) — one call after any extraction path."""
    for skill in profile.skills:
        match = normalize_skill(skill.name)
        if match:
            skill.canonical, skill.category = match.canonical, match.category
    for edu in profile.education:
        if edu.degree:
            deg = normalize_degree(edu.degree)
            if deg:
                edu.degree_canonical, edu.degree_level = deg.canonical, deg.level
        edu.grade_cgpa_10 = normalize_grade(edu.grade_value, edu.grade_scale)
        if edu.institution:
            inst = canonicalize_institution(edu.institution)
            if inst:
                edu.institution_canonical = inst.canonical
                edu.institution_tier = inst.tier
    for exp in profile.experience:
        if exp.employer:
            exp.employer_canonical = canonicalize_employer(exp.employer)
    location = profile.contact.location
    if location and location.value:
        city = find_city(location.value)
        if city:
            profile.contact.location_city = city.city
            profile.contact.location_tier = city.tier
    if profile.notice_period and profile.notice_period.value:
        found = parse_notice_period(profile.notice_period.value)
        if found:
            profile.notice_period_days = found.days
    return profile


__all__ = ["normalize_profile"]
