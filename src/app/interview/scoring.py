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
from typing import Annotated, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

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
SCORER_VERSION = "s73.2"

#: Distinct substantive clauses, never repeated tool/numeral tokens.
SPECIFICITY_TARGET = 3
#: Historical v1 aggregation only. New confidence never uses word count.
SUBSTANCE_TARGET_WORDS = 60

_TOKEN = re.compile(r"[A-Za-z0-9+#./\-']+")
_FIRST_SINGULAR = frozenset({"i", "my", "me", "mine", "i'd", "i'll", "i've", "i'm"})


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text or "")


def _alpha_words(text: str) -> list[str]:
    return [t for t in _tokens(text) if any(c.isalpha() for c in t)]


def word_count(text: str) -> int:
    return len(_alpha_words(text))


# Explicit, bounded development rubric, not a semantic accuracy claim. These
# are reported actions with objects; listing the nouns/imperatives earns nothing.
_INVESTIGATE = frozenset("analyzed analysed compared measured identified traced diagnosed isolated checked reviewed reproduced evaluated validated audited surveyed tested investigated".split())
_CHANGE = frozenset("designed changed built implemented replaced pinned restored rewrote rewritten rebuilt rolled reverted migrated negotiated scheduled trained selected chose reduced increased cut recovered fixed deployed improved removed moved handled shipped".split())
_OUTCOME = frozenset("confirmed showed demonstrated disappeared recovered prevented reduced increased cut improved restored resolved".split())
_VERBS = _INVESTIGATE | _CHANGE | _OUTCOME
_CLAUSES = re.compile(
    r"(?<!\d)\.(?!\d)|[!?;\n]+|(?:,\s*|\s+(?:and|but|so)\s+)"
    r"(?=(?:[\w'-]+\s+){0,3}(?:" + "|".join(sorted(_VERBS)) + r")\b)",
    re.IGNORECASE,
)
_STOP = frozenset(("a an the this that these those i my me mine we our us ours you your it its they their them "
    "is are was were be been being am did do does had have has of on in at by for from with to and or but so "
    "then than as after before over under into through myself itself ourselves what how why which when "
    "there here one specific problem thing things work worked made better well overall team personally "
    "describe walk hardest done tried first instead tell explain could would should can will not no").split())
_QUESTION_STOP = _STOP | frozenset("diagnose recover solve solved cause found change broke list engineer engineering role title failed failing failure debug debugging trade-off rollback outcome result constraint difficult example".split())


def _terms(text: str) -> set[str]:
    return {w[:-1] if w.endswith("s") and len(w) > 3 else w
            for w in (t.casefold().strip("./-'") for t in _tokens(text)) if any(c.isalpha() for c in w)}


def _signal_covered(words: set[str], signal: str) -> bool:
    groups = {
        "debug": _INVESTIGATE | {"debug", "debugged", "diagnosis"},
        "rollback": {"rollback", "reverted", "restored", "pinned"},
        "fail": {"fail", "failed", "failing", "failure", "broke", "broken", "error"},
        "trade-off": {"trade-off", "tradeoff", "because", "instead", "constraint"},
        "latency": {"latency", "delay", "response"},
        "cost": {"cost", "expense", "spend", "budget"},
    }
    signal_terms = _terms(signal)
    if signal.strip().casefold() in groups:
        return bool(words & groups[signal.strip().casefold()])
    return bool(signal_terms) and signal_terms <= words


def _evidence(transcript: str, question_text: str):
    prompt = _terms(question_text)
    units, seen = [], set()
    for clause in _CLAUSES.split(transcript or ""):
        words = _terms(clause)
        # Exclude echoed question clauses before counting content or confidence.
        if prompt and words and words <= prompt:
            continue
        actions = words & _VERBS
        objects = words - _STOP - _VERBS
        if not actions or len(objects) < 2:
            continue
        fingerprint = frozenset(words - _STOP)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        units.append(words)
    return units


def score_turn(
    *,
    transcript: str,
    expected_signals: Sequence[str],
    profile: Optional[CandidateProfile],
    settings: Settings,
    question_text: str = "",
) -> TurnScore:
    """Score distinct reported content. A short answer with two substantive
    clauses is usable; a long keyword list is still missing evidence. Unknown
    relevance/consistency never asserts a contradiction or fabricated history.
    """
    units = _evidence(transcript, question_text)
    if not units or len(units) < 2 and word_count(transcript) < settings.interview_min_answer_words:
        return TurnScore(dimensions={}, insufficient=True, codes=["insufficient_answer"],
                         scorer_version=SCORER_VERSION)
    words = set().union(*units)
    signals = list(dict.fromkeys(s.strip().casefold() for s in expected_signals if s and s.strip()))
    topics = _terms(question_text) - _QUESTION_STOP - _VERBS
    # A profile name is neither a required password nor independent evidence.
    if profile:
        for exp in profile.experience:
            topics -= _terms(" ".join(filter(None, (exp.employer, exp.employer_canonical, exp.title))))
        for skill in profile.skills:
            topics -= _terms(" ".join(filter(None, (skill.name, skill.canonical))))
    covered = [s for s in signals if _signal_covered(words, s)]
    generic = {"debug", "rollback", "fail", "trade-off", "latency", "cost"}
    # Generic template prompts need more than a universal verb such as
    # "compared". A specific signal or two distinct procedural concepts can
    # anchor a nameless answer without requiring profile-name repetition.
    signal_anchor = any(s not in generic for s in covered) or len(covered) >= 2
    # Question relevance and the depth yardstick are separate. An absent signal
    # list must not turn unrelated fluent prose into a confident answer.
    anchored = bool(topics & words) if topics else signal_anchor
    stages = (bool(words & _INVESTIGATE), bool(words & _CHANGE),
              bool(words & _OUTCOME) or bool(words & {"because", "constraint", "instead"}))
    depth = round(sum(stages) / 3, 4) if signals and anchored else 0.5
    # One descriptive clause is limited evidence at any length. This also keeps
    # repetition/filler crossing the word floor from creating confidence.
    confidence = min(0.95, 0.35 + len(units) * 0.2) if len(units) >= 2 else 0.0
    codes = ["consistency_unverified"]
    if len(units) < 2:
        codes.append("limited_content")
    if not any(u & _FIRST_SINGULAR for u in units):
        codes.append("ownership_unknown")
    if not signals:
        codes.append("depth_unknown")
    if not anchored:
        codes.append("relevance_unconfirmed")
        confidence = min(confidence, 0.4)
    return TurnScore(
        dimensions={
            "specificity": round(min(1.0, len(units) / SPECIFICITY_TARGET), 4),
            "ownership": 1.0 if any(u & _FIRST_SINGULAR for u in units) else 0.5,
            "depth": depth,
            "consistency": 0.5,
        },
        insufficient=False,
        codes=codes, scorer_version=SCORER_VERSION,
        evidence_confidence=round(confidence, 4),
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

    Current confidence is coverage x frozen per-turn content evidence, never
    word count. Legacy-only turns retain their original aggregation semantics;
    mixed/unknown versions cannot silently create a new scored assessment.
    """
    planned = len(questions)
    answered = len(turns)
    coverage = round(answered / planned, 4) if planned else 0.0

    versions = {t.score.scorer_version or "s73.1" for t in turns}
    legacy = bool(versions) and versions <= {"s73.1"}
    if versions and not legacy and versions != {SCORER_VERSION}:
        return InterviewAssessment(session_id=session_id, candidate_id=candidate_id,
            coverage=coverage, questions_planned=planned, questions_answered=answered,
            proxy=proxy, scorer_version="mixed/unknown")

    eligible = [t for t in turns if legacy or (
        not t.score.insufficient and t.score.evidence_confidence > 0
        and "relevance_unconfirmed" not in t.score.codes)]
    dimensions: dict[str, float] = {}
    for dim in DIMENSIONS:
        values = [t.score.dimensions[dim] for t in eligible if dim in t.score.dimensions]
        if values:
            dimensions[dim] = round(sum(values) / len(values), 4)

    weights = {dim: getattr(settings, f"interview_weight_{dim}") for dim in dimensions}
    total_weight = sum(weights.values())
    overall = (
        round(sum(dimensions[d] * weights[d] for d in dimensions) / total_weight, 4)
        if total_weight
        else 0.0
    )

    if legacy:
        substance = sum(min(1.0, t.word_count / SUBSTANCE_TARGET_WORDS) for t in turns) / answered
        confidence = round(min(0.95, coverage * substance), 4)
    else:
        # Sum/planned is coverage x mean evidence without intermediate rounding.
        # An unrelated/limited turn changes progress, never assessment evidence.
        confidence = round(min(0.95, sum(t.score.evidence_confidence for t in eligible) / planned), 4) if planned else 0.0

    return InterviewAssessment(
        session_id=session_id,
        candidate_id=candidate_id,
        band=band_for(overall, confidence, settings) if legacy or eligible else InterviewBand.INSUFFICIENT_SIGNAL,
        overall=overall,
        dimensions=dimensions,
        confidence=confidence,
        coverage=coverage,
        questions_planned=planned,
        questions_answered=answered,
        proxy=proxy,
        scorer_version="s73.1" if legacy else SCORER_VERSION,
    )


# ── The capped LLM adjustment ───────────────────────────────────────────────

_SCORING_SYSTEM = (
    "You are grading ONE answer from a technical interview, on four axes: "
    "specificity (concrete detail), ownership (what the speaker personally did), "
    "depth (coverage of what a genuine answer must contain), and consistency. "
    "Return only dimensions you are confident differ from the given baseline. "
    "Assess distinct actions, reasoning and outcomes, including paraphrases. "
    "Repeated keywords, fluency, pronoun frequency, profile-name overlap, appearance "
    "and inferred emotion are not evidence of technical depth or factual truth. "
    "You are an adjustment, not the grader: your suggestions are clamped."
)


class _AdjustmentReply(BaseModel):
    model_config = ConfigDict(strict=True)

    dimensions: dict[str, Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]]


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
        if data == {}:
            return base
        proposed = _AdjustmentReply.model_validate(data).dimensions
    except Exception as exc:  # noqa: BLE001 -- an LLM outage is not a failure here
        log.warning("interview_scoring_llm_failed", error_type=type(exc).__name__)
        return base

    cap = settings.interview_llm_max_delta
    adjusted = dict(base.dimensions)
    changed = False
    for dim, value in proposed.items():
        if dim not in adjusted:
            continue
        if base.scorer_version == SCORER_VERSION and (
            dim == "consistency" or dim == "ownership" and "ownership_unknown" in base.codes
            or dim == "depth" and any(c in base.codes for c in ("depth_unknown", "relevance_unconfirmed"))
        ):
            continue
        delta = max(-cap, min(cap, value - adjusted[dim]))
        if delta:
            adjusted[dim] = round(min(1.0, max(0.0, adjusted[dim] + delta)), 4)
            changed = True

    if not changed:
        return base
    return base.model_copy(update={"dimensions": adjusted, "codes": [*base.codes, "llm_adjusted"]})
