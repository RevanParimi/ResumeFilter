"""Deterministic interview scoring (S7.3). Pure: no I/O, no clock.

Four axes, each NEUTRAL WHEN UNKNOWN (0.5) rather than zero. That rule is the
whole ethic of this module: a scorer that treats "we have no yardstick" as "the
answer was shallow" punishes candidates for gaps in the question bank.

The targets below are module constants, not config knobs. They define what the
number MEANS; a deploy-time switch would make two stored assessments
incomparable. When they change, SCORER_VERSION changes with them, and every
stored assessment records which version produced it.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

from app.candidates.normalize.skills import normalize_skill
from app.candidates.schema import CandidateProfile
from app.core.config import Settings
from app.core.logging import get_logger
from app.interview.schema import (
    DIMENSIONS, InterviewAssessment, InterviewBand, InterviewQuestion, InterviewTurn,
    ProxyRisk, TurnScore,
)
from app.services.llm import LLMClient

log = get_logger(__name__)

#: Bump on ANY change to the maths below. Stamped on every stored assessment.
SCORER_VERSION = "s73.1"

#: Concrete tokens (numerals + recognised tools) for a full specificity score.
SPECIFICITY_TARGET = 6
#: Words at which an answer counts as fully substantive for confidence.
SUBSTANCE_TARGET_WORDS = 60

_TOKEN = re.compile(r"[A-Za-z0-9+#./\-']+")
_FIRST_SINGULAR = frozenset({"i", "my", "me", "mine", "i'd", "i'll", "i've", "i'm"})
_FIRST_PLURAL = frozenset({"we", "our", "us", "ours", "we'd", "we'll", "we've", "we're"})


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text or "")


def _alpha_words(text: str) -> list[str]:
    return [t for t in _tokens(text) if any(c.isalpha() for c in t)]


def word_count(text: str) -> int:
    return len(_alpha_words(text))


def _specificity(tokens: Sequence[str]) -> float:
    concrete = 0
    for token in tokens:
        if any(c.isdigit() for c in token):
            concrete += 1
        elif normalize_skill(token) is not None:
            concrete += 1
    return round(min(1.0, concrete / SPECIFICITY_TARGET), 4)


def _ownership(words: Sequence[str]) -> float:
    lowered = [w.casefold() for w in words]
    mine = sum(1 for w in lowered if w in _FIRST_SINGULAR)
    ours = sum(1 for w in lowered if w in _FIRST_PLURAL)
    if mine + ours == 0:
        return 0.5   # neither claimed nor disclaimed: unknown, not bad
    return round(mine / (mine + ours), 4)


def _depth(text_cf: str, expected_signals: Sequence[str]) -> float:
    signals = [s for s in expected_signals if s and s.strip()]
    if not signals:
        return 0.5   # no yardstick for this question
    matched = sum(1 for s in signals if s.strip().casefold() in text_cf)
    return round(matched / len(signals), 4)


def _profile_terms(profile: Optional[CandidateProfile]) -> list[str]:
    if profile is None:
        return []
    terms: list[str] = []
    for exp in profile.experience:
        for value in (exp.employer_canonical, exp.employer):
            if value:
                terms.append(value.casefold())
    for skill in profile.skills:
        for value in (skill.canonical, skill.name):
            if value:
                terms.append(value.casefold())
    return list(dict.fromkeys(terms))


def _consistency(text_cf: str, profile: Optional[CandidateProfile]) -> float:
    """v0 CORROBORATES; it does not contradict. Naming something on the profile
    lifts this to 1.0; naming something we never taxonomised leaves it neutral.
    A candidate must never lose points for a client they cannot name."""
    for term in _profile_terms(profile):
        if term and term in text_cf:
            return 1.0
    return 0.5


def score_turn(
    *,
    transcript: str,
    expected_signals: Sequence[str],
    profile: Optional[CandidateProfile],
    settings: Settings,
) -> TurnScore:
    """Score ONE answer. An answer below the word floor scores NOTHING (an empty
    `dimensions`), which is different from scoring zero: silence is missing
    evidence, not evidence of shallowness."""
    words = _alpha_words(transcript)
    if len(words) < settings.interview_min_answer_words:
        return TurnScore(dimensions={}, insufficient=True, codes=["insufficient_answer"])

    text_cf = (transcript or "").casefold()
    return TurnScore(
        dimensions={
            "specificity": _specificity(_tokens(transcript)),
            "ownership": _ownership(words),
            "depth": _depth(text_cf, expected_signals),
            "consistency": _consistency(text_cf, profile),
        },
        insufficient=False,
        codes=[],
    )


def band_for(overall: float, confidence: float, settings: Settings) -> InterviewBand:
    """Conservative banding: confidence gates everything, exactly like the
    ai_*/fr_*/rep_* families. Below the floor we say nothing."""
    if confidence < settings.interview_min_confidence:
        return InterviewBand.INSUFFICIENT_SIGNAL
    if overall >= settings.interview_deep_threshold:
        return InterviewBand.DEEP
    if overall >= settings.interview_solid_threshold:
        return InterviewBand.SOLID
    if overall >= settings.interview_emerging_threshold:
        return InterviewBand.EMERGING
    return InterviewBand.SUPERFICIAL


def aggregate(
    *,
    session_id: str,
    candidate_id: str,
    questions: Sequence[InterviewQuestion],
    turns: Sequence[InterviewTurn],
    proxy: ProxyRisk,
    settings: Settings,
) -> InterviewAssessment:
    """Fold scored turns into one advisory assessment.

    Confidence = coverage x substance. Both matter: three thorough answers out
    of eight planned questions is not the same evidence as eight thorough ones,
    and eight one-liners are not either.
    """
    planned = len(questions)
    answered = len(turns)
    coverage = round(answered / planned, 4) if planned else 0.0

    dimensions: dict[str, float] = {}
    for dim in DIMENSIONS:
        values = [t.score.dimensions[dim] for t in turns if dim in t.score.dimensions]
        if values:
            dimensions[dim] = round(sum(values) / len(values), 4)

    weights = {dim: getattr(settings, f"interview_weight_{dim}") for dim in dimensions}
    total_weight = sum(weights.values())
    overall = (
        round(sum(dimensions[d] * weights[d] for d in dimensions) / total_weight, 4)
        if total_weight
        else 0.0
    )

    substance = (
        sum(min(1.0, t.word_count / SUBSTANCE_TARGET_WORDS) for t in turns) / answered
        if answered
        else 0.0
    )
    confidence = round(min(0.95, coverage * substance), 4)

    return InterviewAssessment(
        session_id=session_id,
        candidate_id=candidate_id,
        band=band_for(overall, confidence, settings),
        overall=overall,
        dimensions=dimensions,
        confidence=confidence,
        coverage=coverage,
        questions_planned=planned,
        questions_answered=answered,
        proxy=proxy,
        scorer_version=SCORER_VERSION,
    )


# ── The capped LLM adjustment ───────────────────────────────────────────────

_SCORING_SYSTEM = (
    "You are grading ONE answer from a technical interview, on four axes: "
    "specificity (concrete detail), ownership (what the speaker personally did), "
    "depth (coverage of what a genuine answer must contain), and consistency. "
    "Return only dimensions you are confident differ from the given baseline. "
    "You are an adjustment, not the grader: your suggestions are clamped."
)


async def adjust_with_llm(
    llm: LLMClient,
    *,
    question_text: str,
    transcript: str,
    expected_signals: Sequence[str],
    base: TurnScore,
    settings: Settings,
) -> TurnScore:
    """Optionally nudge a deterministic score. The model can move a dimension by
    at most `interview_llm_max_delta` and can never introduce one, rescue an
    insufficient answer, or produce a band by itself. Any failure -- no key, bad
    JSON, an exception -- silently leaves the deterministic score standing,
    because degrading to rules is the designed behaviour, not an error."""
    if base.insufficient or not base.dimensions:
        return base

    excerpt = (transcript or "")[: settings.interview_llm_excerpt_chars]
    try:
        data = await llm.acomplete_json(
            tier="scoring",
            system=_SCORING_SYSTEM,
            prompt=(
                f"QUESTION: {question_text}\n"
                f"EXPECTED SIGNALS: {list(expected_signals)}\n"
                f"BASELINE: {base.dimensions}\n"
                f"ANSWER: {excerpt}\n"
                'Return JSON: {"dimensions": {"<axis>": 0.0-1.0, ...}}'
            ),
        )
    except Exception as exc:  # noqa: BLE001 -- an LLM outage is not a failure here
        log.warning("interview_scoring_llm_failed", error=str(exc))
        return base

    proposed = (data or {}).get("dimensions")
    if not isinstance(proposed, dict):
        return base

    cap = settings.interview_llm_max_delta
    adjusted = dict(base.dimensions)
    changed = False
    for dim, raw in proposed.items():
        if dim not in adjusted:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        delta = max(-cap, min(cap, value - adjusted[dim]))
        if delta:
            adjusted[dim] = round(min(1.0, max(0.0, adjusted[dim] + delta)), 4)
            changed = True

    if not changed:
        return base
    return TurnScore(
        dimensions=adjusted, insufficient=False, codes=[*base.codes, "llm_adjusted"]
    )
