"""Deterministic AI-generated-resume detectors (S2.1) — pure, offline.

Each detector looks for one stylistic tell of LLM-drafted resumes and returns
an AISignal when it fires. Thresholds are deliberately conservative: false
positives are the existential risk, and AI-assisted resume writing is common
and legitimate. Detectors only run when the text gives them enough to measure
(word/bullet minimums); confidence grows with how many could run.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from app.core.config import Settings
from app.schemas.fabrication import AILikelihoodBand, AISignal

# Stylistic tells common in LLM-drafted resume prose (lowercase substrings).
TEMPLATE_PHRASES = [
    "results-driven", "results driven", "dynamic professional",
    "proven track record", "passionate about", "cutting-edge",
    "spearheaded", "leveraged", "leveraging", "synergy",
    "fast-paced environment", "meticulous", "seamless", "delve",
    "honed", "testament to", "fostering", "impactful",
    "innovative solutions", "state-of-the-art", "thought leadership",
    "cross-functional collaboration", "committed to excellence",
    "exceeding expectations", "transformative", "showcasing",
    "underscoring", "pivotal", "robust and scalable",
]

_BULLET_PREFIXES = ("-", "•", "*", "–", "‣")
_METRIC_RE = re.compile(r"\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?x\b")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")

_MIN_WORDS = 60    # below this, phrase density is noise
_MIN_BULLETS = 6   # below this, bullet statistics are noise
_MIN_RUNS = 3      # need >= 3 job entries to call the structure "templated"


def extract_bullets(text: str) -> list[str]:
    """Bullet-prefixed lines, prefix stripped. Short stubs are skipped."""
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(_BULLET_PREFIXES) and len(s) > 8:
            out.append(s.lstrip("".join(_BULLET_PREFIXES)).strip())
    return out


def bullet_runs(text: str) -> list[int]:
    """Sizes of consecutive bullet-line groups (≈ bullets per job entry)."""
    runs: list[int] = []
    current = 0
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(_BULLET_PREFIXES) and len(s) > 8:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return runs


def detect_template_phrases(text: str) -> AISignal | None:
    """Density of stock LLM-resume phrases per 100 words."""
    words = len(text.split())
    if words < _MIN_WORDS:
        return None
    low = text.lower()
    hits = {p: low.count(p) for p in TEMPLATE_PHRASES if p in low}
    total = sum(hits.values())
    if total < 3:
        return None
    density = total / (words / 100)
    return AISignal(
        id="template_phrases",
        score=min(1.0, density / 3.0),
        detail=(
            f"{total} template-phrase hits in {words} words "
            f"({density:.1f}/100 words): {', '.join(sorted(hits)[:6])}"
        ),
    )


def detect_uniform_bullets(bullets: list[str]) -> AISignal | None:
    """Near-identical bullet lengths AND uniform past-tense verb openers."""
    if len(bullets) < _MIN_BULLETS:
        return None
    lengths = [len(b) for b in bullets]
    mean = statistics.mean(lengths)
    cv = (statistics.pstdev(lengths) / mean) if mean else 1.0
    verb_frac = sum(
        1 for b in bullets if b.split() and b.split()[0].lower().endswith("ed")
    ) / len(bullets)
    if cv >= 0.22 or verb_frac < 0.85:
        return None
    return AISignal(
        id="uniform_bullets",
        score=min(1.0, (1 - cv / 0.22) * 0.6 + verb_frac * 0.4),
        detail=(
            f"{len(bullets)} bullets with near-identical shape: length CV "
            f"{cv:.2f}, {verb_frac:.0%} open with a past-tense verb"
        ),
    )


def detect_metric_saturation(bullets: list[str]) -> AISignal | None:
    """Nearly every bullet quantified, with suspiciously round numbers."""
    if len(bullets) < _MIN_BULLETS:
        return None
    quantified = [b for b in bullets if _METRIC_RE.search(b)]
    frac = len(quantified) / len(bullets)
    if frac < 0.7:
        return None
    percents = [float(m.group(1)) for b in bullets for m in _PERCENT_RE.finditer(b)]
    round_frac = (
        sum(1 for p in percents if p % 5 == 0) / len(percents) if percents else 0.0
    )
    return AISignal(
        id="metric_saturation",
        score=min(1.0, frac * (0.7 + 0.3 * round_frac)),
        detail=(
            f"{len(quantified)}/{len(bullets)} bullets carry a %/x metric; "
            f"{round_frac:.0%} of percentages are multiples of 5"
        ),
    )


def detect_symmetric_structure(runs: list[int]) -> AISignal | None:
    """>= 3 job entries with IDENTICAL bullet counts — template shape."""
    if len(runs) < _MIN_RUNS:
        return None
    if len(set(runs)) != 1 or runs[0] < 3:
        return None
    return AISignal(
        id="symmetric_structure",
        score=min(1.0, 0.55 + 0.10 * len(runs)),
        detail=(
            f"{len(runs)} experience entries with identical bullet counts "
            f"({runs[0]} each)"
        ),
    )


@dataclass
class DeterministicAssessment:
    """Outcome of the pure pass: which tells fired + how much text we had."""

    signals: list[AISignal] = field(default_factory=list)
    likelihood: float = 0.0
    confidence: float = 0.0
    evaluated: int = 0  # detectors that had enough text to run (max 4)


def assess_deterministic(text: str) -> DeterministicAssessment:
    """Run every detector that has enough text; non-fired ones count as 0."""
    words = len(text.split())
    bullets = extract_bullets(text)
    runs = bullet_runs(text)

    signals: list[AISignal] = []
    scores: list[float] = []

    def _run(fired: AISignal | None) -> None:
        scores.append(fired.score if fired else 0.0)
        if fired:
            signals.append(fired)

    if words >= _MIN_WORDS:
        _run(detect_template_phrases(text))
    if len(bullets) >= _MIN_BULLETS:
        _run(detect_uniform_bullets(bullets))
        _run(detect_metric_saturation(bullets))
    if len(runs) >= _MIN_RUNS:
        _run(detect_symmetric_structure(runs))

    evaluated = len(scores)
    if not evaluated:
        return DeterministicAssessment()
    return DeterministicAssessment(
        signals=signals,
        likelihood=sum(scores) / evaluated,
        confidence=min(0.9, 0.30 + 0.15 * evaluated),
        evaluated=evaluated,
    )


def fuse_pairs(pairs: list[tuple[float, float]]) -> tuple[float, float]:
    """Confidence-weighted fusion of (likelihood, confidence) pairs.

    Same math as plausibility's _fuse, but the empty case is (0.0, 0.0):
    zero confidence means banding says INSUFFICIENT_TEXT, never a score.
    """
    if not pairs:
        return 0.0, 0.0
    weight = sum(c for _, c in pairs)
    if weight == 0:
        return sum(lk for lk, _ in pairs) / len(pairs), 0.0
    likelihood = sum(lk * c for lk, c in pairs) / weight
    confidence = min(1.0, weight / len(pairs))
    return likelihood, confidence


def band_for(
    likelihood: float, confidence: float, fired_deterministic: int, settings: Settings
) -> AILikelihoodBand:
    """Conservative banding. LIKELY needs >= 2 independent deterministic tells."""
    if confidence < settings.ai_min_confidence:
        return AILikelihoodBand.INSUFFICIENT_TEXT
    if likelihood >= settings.ai_likely_threshold:
        if fired_deterministic >= 2:
            return AILikelihoodBand.LIKELY
        return AILikelihoodBand.POSSIBLE  # the LLM alone can never say LIKELY
    if likelihood >= settings.ai_possible_threshold:
        return AILikelihoodBand.POSSIBLE
    return AILikelihoodBand.UNLIKELY
