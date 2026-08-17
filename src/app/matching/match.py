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
from app.features.ranking import apply_filters, score
from app.features.ranking_schema import (
    FeatureFilter, FilterOp, RankingSpec, RankingTerm, SortDirection,
)
from app.features.schema import FeatureDType, FeatureSource, FeatureSpec, FeatureVector
from app.matching.schema import JobRequisitionInput, MatchedCandidate, SkillMatchDetail

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


def _weight(override: Optional[float], default: float) -> float:
    return override if override is not None else default


def compile_ranking(req: JobRequisitionInput, settings: Settings) -> RankingSpec:
    """Requisition -> RankingSpec of SOFT terms. skill_coverage is always present;
    each scalar term appears only when its requisition field is set. The threshold
    VALUE is not a cutoff here — it selects the dimension; scoring is monotonic."""
    w = req.weights
    terms: list[RankingTerm] = [
        RankingTerm(
            feature=SKILL_COVERAGE,
            weight=_weight(w.skill_coverage if w else None, settings.match_skill_weight),
            direction=SortDirection.HIGHER_BETTER,
        )
    ]
    if req.min_years_experience is not None:
        terms.append(RankingTerm(
            feature="candidate.years_experience",
            weight=_weight(w.years if w else None, settings.match_years_weight),
            direction=SortDirection.HIGHER_BETTER,
        ))
    if req.min_degree_level is not None:
        terms.append(RankingTerm(
            feature="candidate.highest_degree_level",
            weight=_weight(w.degree if w else None, settings.match_degree_weight),
            direction=SortDirection.HIGHER_BETTER,
        ))
    if req.max_notice_days is not None:
        terms.append(RankingTerm(
            feature="candidate.notice_period_days",
            weight=_weight(w.notice if w else None, settings.match_notice_weight),
            direction=SortDirection.LOWER_BETTER,
        ))
    if req.location_tiers and not req.remote:
        terms.append(RankingTerm(
            feature=LOCATION_FIT,
            weight=_weight(w.location if w else None, settings.match_location_weight),
            direction=SortDirection.HIGHER_BETTER,
        ))
    return RankingSpec(terms=tuple(terms))


def compile_filters(req: JobRequisitionInput) -> list[FeatureFilter]:
    """The only opt-in hard gate: a min_skill_coverage floor on the synthetic term."""
    if req.min_skill_coverage is not None:
        return [FeatureFilter(
            feature=SKILL_COVERAGE, op=FilterOp.GTE, value=req.min_skill_coverage,
        )]
    return []


def match(
    req: JobRequisitionInput,
    vectors: list[FeatureVector],
    profiles_by_candidate: dict[str, CandidateProfile],
    specs_by_name: dict[str, FeatureSpec],
    settings: Settings,
) -> list[MatchedCandidate]:
    """Compute job-relative synthetic values, inject them into a copy of each
    vector, apply the opt-in filter, and rank with the S4.3 engine."""
    specs = {**specs_by_name, **_SYNTHETIC_SPECS}
    skill_by_cand: dict[str, SkillMatchDetail] = {}
    augmented: list[FeatureVector] = []
    for v in vectors:
        profile = profiles_by_candidate.get(v.candidate_id)
        if profile is not None:
            detail = skill_coverage(req, canonical_skills(profile), settings)
            cov_value: Optional[float] = detail.coverage
            loc = location_fit(req, profile.contact.location_tier)
        else:
            # No point-in-time profile: skill/location unknown -> terms drop (no penalty).
            detail = SkillMatchDetail(
                coverage=0.0, missing_must_have=tuple(req.must_have_skills)
            )
            cov_value = None
            loc = None
        skill_by_cand[v.candidate_id] = detail
        augmented.append(v.model_copy(update={"values": {
            **v.values, SKILL_COVERAGE: cov_value, LOCATION_FIT: loc,
        }}))
    filtered = apply_filters(augmented, compile_filters(req), specs)
    ranked = score(filtered, compile_ranking(req, settings), specs)
    return [
        MatchedCandidate(
            candidate_id=rc.candidate_id,
            score=rc.score,
            coverage=rc.coverage,
            skill=skill_by_cand[rc.candidate_id],
            contributions=rc.contributions,
            missing=rc.missing,
        )
        for rc in ranked
    ]
