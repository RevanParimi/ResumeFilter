"""Pure role-conditioned matching engine (PI-5 / S5.1).

No I/O, no store, no wall clock (the app/features/ranking.py pattern). Compiles a
JobRequisition into an S4.3 RankingSpec + filters, computes two job-relative
synthetic values (skill coverage, location fit) per candidate, injects them into
a copy of each FeatureVector, and reuses ranking.score(). Advisory: a missing
value drops its term, never the candidate.
"""

from __future__ import annotations

from typing import Optional

from app.candidates.schema import CandidateProfile
from app.core.config import Settings
from app.features.schema import FeatureDType, FeatureSource, FeatureSpec
from app.matching.schema import JobRequisitionInput, SkillMatchDetail

SKILL_COVERAGE = "match.skill_coverage"
LOCATION_FIT = "match.location_fit"

_SYNTHETIC_SPECS: dict[str, FeatureSpec] = {
    SKILL_COVERAGE: FeatureSpec(
        name=SKILL_COVERAGE, version=1, dtype=FeatureDType.NUMERIC,
        source=FeatureSource.CANDIDATE,
        description="Job-relative fraction of the requisition's skills the candidate has.",
        valid_range=(0.0, 1.0),
    ),
    LOCATION_FIT: FeatureSpec(
        name=LOCATION_FIT, version=1, dtype=FeatureDType.NUMERIC,
        source=FeatureSource.CANDIDATE,
        description="1.0 if the candidate's city tier is one of the requisition's target tiers.",
        valid_range=(0.0, 1.0),
    ),
}


def canonical_skills(profile: CandidateProfile) -> set[str]:
    """The candidate's canonical (S1.4 taxonomy) skill ids; uncanonical skills drop."""
    return {s.canonical for s in profile.skills if s.canonical}


def skill_coverage(
    req: JobRequisitionInput, have: set[str], settings: Settings
) -> SkillMatchDetail:
    must = list(req.must_have_skills)
    nice = list(req.nice_to_have_skills)
    matched_must = [s for s in must if s in have]
    matched_nice = [s for s in nice if s in have]
    missing_must = [s for s in must if s not in have]
    must_frac = (len(matched_must) / len(must)) if must else None
    nice_frac = (len(matched_nice) / len(nice)) if nice else None
    f = settings.match_nice_to_have_fraction
    if must_frac is not None and nice_frac is not None:
        cov = must_frac * (1.0 - f) + nice_frac * f
    elif must_frac is not None:
        cov = must_frac
    else:
        cov = nice_frac if nice_frac is not None else 0.0
    return SkillMatchDetail(
        matched=tuple(matched_must + matched_nice),
        missing_must_have=tuple(missing_must),
        matched_nice_to_have=tuple(matched_nice),
        coverage=cov,
    )


def location_fit(req: JobRequisitionInput, location_tier: Optional[str]) -> Optional[float]:
    """None (term drops, no penalty) when remote / no target tiers / unknown tier;
    else 1.0 in-tier, 0.0 out-of-tier."""
    if req.remote or not req.location_tiers:
        return None
    if not location_tier:
        return None
    return 1.0 if location_tier in req.location_tiers else 0.0
