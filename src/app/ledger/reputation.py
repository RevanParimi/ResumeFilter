"""S3.4 — cross-company reputation: advisory Bayesian aggregation.

Pure functions, no I/O, no LLM (the app/fabrication/risk.py pattern). ADVISORY
ONLY: the band/score is reviewer context computed on demand for a consented
read. It never changes a verdict, depth score, or depth band, and is NEVER a
rejection signal. Conservative by construction: the estimate shrinks toward a
neutral prior (sparse evidence stays neutral), older outcomes decay, and the
only negative-leaning band (GUARDED) plus the top band (STRONG) both require
corroboration across >= rep_corroboration_orgs distinct orgs, so a single org
can never brand a candidate.
"""

from __future__ import annotations

from datetime import datetime

from app.core.config import Settings, get_settings
from app.ledger.schema import (
    CodingRoundResult,
    InterviewOutcome,
    InterviewRecord,
    ReputationAssessment,
    ReputationBand,
    ReputationComponent,
)

# Outcome -> success value in [0,1]. Code constants, NOT config: changing outcome
# polarity is a reviewed schema decision. WITHDRAWN is intentionally absent —
# a candidate-initiated withdrawal is not an evaluation of the candidate, so it
# is excluded from the evidence entirely.
_OUTCOME_VALUE = {
    InterviewOutcome.HIRED: 1.00,
    InterviewOutcome.OFFER: 0.90,
    InterviewOutcome.ADVANCED: 0.65,
    InterviewOutcome.REJECTED: 0.15,
    InterviewOutcome.NO_SHOW: 0.10,
}


def _outcome_value(outcome: InterviewOutcome) -> float | None:
    return _OUTCOME_VALUE.get(outcome)


def _coding_value(cr: CodingRoundResult) -> float | None:
    """Normalize a coding round to [0,1]. percentile (a rank) is the best signal;
    else score/max_score; else un-normalizable (bare score has no cross-platform
    meaning) -> excluded."""
    if cr.percentile is not None:
        return max(0.0, min(1.0, cr.percentile / 100.0))
    if cr.max_score is not None and cr.max_score > 0:
        return max(0.0, min(1.0, cr.score / cr.max_score))
    return None


def _recency_weight(at: datetime, now: datetime, halflife_days: float) -> float:
    age_days = max(0.0, (now - at).total_seconds() / 86400.0)  # future-dated -> 0
    return 0.5 ** (age_days / halflife_days)


class _Obs:
    __slots__ = ("value", "weight", "org")

    def __init__(self, value: float, weight: float, org: str) -> None:
        self.value = value
        self.weight = weight
        self.org = org


def _component(cid: str, obs: list[_Obs]) -> ReputationComponent:
    w = sum(o.weight for o in obs)
    mean = (sum(o.weight * o.value for o in obs) / w) if w > 0 else 0.0
    return ReputationComponent(
        id=cid, observations=len(obs), effective_weight=w,
        mean_value=max(0.0, min(1.0, mean)),
    )


def _band_for(
    score: float, confidence: float, distinct_orgs: int, s: Settings
) -> ReputationBand:
    """Conservative, corroboration-gated. Never assert below the confidence
    floor. STRONG and GUARDED both require >= rep_corroboration_orgs distinct
    orgs: single-source high caps at FAVORABLE, single-source low at MIXED."""
    if confidence < s.rep_min_confidence:
        return ReputationBand.INSUFFICIENT_DATA
    corroborated = distinct_orgs >= s.rep_corroboration_orgs
    if score >= s.rep_strong_threshold and corroborated:
        return ReputationBand.STRONG
    if score >= s.rep_favorable_threshold:
        return ReputationBand.FAVORABLE
    if score <= s.rep_guarded_threshold and corroborated:
        return ReputationBand.GUARDED
    return ReputationBand.MIXED


def assess_reputation(
    records: list[InterviewRecord],
    coding_rounds: list[CodingRoundResult],
    *,
    now: datetime,
    reliability_by_org: dict[str, float] | None = None,
    settings: Settings | None = None,
) -> ReputationAssessment:
    s = settings or get_settings()
    rel = reliability_by_org or {}

    def _rel(org: str) -> float:
        w = rel.get(org, 1.0)
        return w if w >= 0 else 0.0

    interview_obs: list[_Obs] = []
    coding_obs: list[_Obs] = []
    excluded = 0

    for r in records:
        v = _outcome_value(r.outcome)
        if v is None:  # WITHDRAWN or any non-scored outcome
            excluded += 1
            continue
        w = s.rep_interview_weight * _recency_weight(
            r.interviewed_at, now, s.rep_recency_halflife_days
        ) * _rel(r.org_id)
        interview_obs.append(_Obs(v, w, r.org_id))

    for cr in coding_rounds:
        v = _coding_value(cr)
        if v is None:
            excluded += 1
            continue
        w = s.rep_coding_weight * _recency_weight(
            cr.taken_at, now, s.rep_recency_halflife_days
        ) * _rel(cr.org_id)
        coding_obs.append(_Obs(v, w, cr.org_id))

    obs = interview_obs + coding_obs
    if not obs:
        return ReputationAssessment(
            score=s.rep_prior_mean,
            confidence=0.0,
            band=ReputationBand.INSUFFICIENT_DATA,
            excluded_observations=excluded,
            reasoning=(
                "No consented, interpretable cross-company evidence to aggregate; "
                "reputation stays at the neutral prior. Advisory only — never a "
                "rejection signal."
            ),
        )

    mass = sum(o.weight for o in obs)
    alpha0 = s.rep_prior_mean * s.rep_prior_strength
    # Beta-Binomial posterior mean, shrunk toward the prior.
    score = (alpha0 + sum(o.weight * o.value for o in obs)) / (s.rep_prior_strength + mass)
    confidence = min(s.rep_confidence_cap, round(mass / (mass + s.rep_confidence_k), 2))
    distinct_orgs = len({o.org for o in obs})

    components: list[ReputationComponent] = []
    if interview_obs:
        components.append(_component("interview_records", interview_obs))
    if coding_obs:
        components.append(_component("coding_rounds", coding_obs))

    band = _band_for(score, confidence, distinct_orgs, s)
    parts = ", ".join(f"{c.id}={c.observations}" for c in components)
    reasoning = (
        f"Aggregated {len(obs)} consented cross-company observation(s) [{parts}] "
        f"from {distinct_orgs} org(s): reputation {score:.2f} (confidence "
        f"{confidence:.2f}) -> {band.value}. Bayesian shrinkage toward a neutral "
        f"prior, recency-decayed, per-org reliability weighted. Advisory context "
        f"for a human reviewer — never changes verdicts or depth scores, and is "
        f"never a rejection signal."
    )
    return ReputationAssessment(
        score=max(0.0, min(1.0, score)),
        confidence=confidence,
        band=band,
        components=components,
        total_observations=len(obs),
        distinct_orgs=distinct_orgs,
        evidence_mass=mass,
        excluded_observations=excluded,
        reasoning=reasoning,
    )
