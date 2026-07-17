"""Fabrication-defense contracts (PI-2).

S2.1 — AI-generated-resume signals. ADVISORY ONLY: an AI-likelihood band is
stylistic context for a human reviewer, never a rejection signal. AI-assisted
resume WRITING is common and legitimate; whether the claims survive depth
evaluation is a separate question (S2.4 fuses these signals there).
S2.2 — cross-field forensics: deterministic timeline/coherence findings.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SignalSource(StrEnum):
    DETERMINISTIC = "deterministic"  # pure text statistics, always available
    LLM = "llm"                      # stylometry pass, best-effort


class AILikelihoodBand(StrEnum):
    """Conservative advisory bands. INSUFFICIENT_TEXT when we can't say."""

    INSUFFICIENT_TEXT = "insufficient_text"
    UNLIKELY = "unlikely"
    POSSIBLE = "possible"
    LIKELY = "likely"


class AISignal(BaseModel):
    """One stylistic tell — human-readable, with the numbers that fired it."""

    id: str  # stable detector id, e.g. "template_phrases"
    detail: str
    score: float = Field(ge=0.0, le=1.0)
    source: SignalSource = SignalSource.DETERMINISTIC


class AIGenerationAssessment(BaseModel):
    """The ai_signals node's output: fused likelihood + band + signal trail."""

    likelihood: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    band: AILikelihoodBand = AILikelihoodBand.INSUFFICIENT_TEXT
    signals: list[AISignal] = Field(default_factory=list)
    reasoning: str = ""
    advisory: bool = True  # mirrors Report: never a rejection signal


class FindingSeverity(StrEnum):
    """S2.2 — how loudly a cross-field finding should be surfaced."""

    MINOR = "minor"  # context for a reviewer; often legitimate (e.g. career gaps)
    MAJOR = "major"  # a contradiction worth probing in conversation


class ConsistencyBand(StrEnum):
    """Conservative advisory bands. INSUFFICIENT_DATA when we can't say."""

    INSUFFICIENT_DATA = "insufficient_data"
    CONSISTENT = "consistent"
    MINOR_ISSUES = "minor_issues"
    MAJOR_ISSUES = "major_issues"


class CrossFieldFinding(BaseModel):
    """One cross-field observation — human-readable, with the months behind it."""

    id: str  # stable check id, e.g. "timeline_overlap"
    detail: str
    severity: FindingSeverity = FindingSeverity.MINOR
    score: float = Field(ge=0.0, le=1.0)
    entry_ids: list[str] = Field(default_factory=list)  # profile entry ids involved


class CrossFieldAssessment(BaseModel):
    """The cross_field node's output: findings + band. Purely deterministic
    date/structure math over the extracted profile — no LLM by design."""

    score: float = Field(default=0.0, ge=0.0, le=1.0)  # fused inconsistency
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    band: ConsistencyBand = ConsistencyBand.INSUFFICIENT_DATA
    findings: list[CrossFieldFinding] = Field(default_factory=list)
    reasoning: str = ""
    advisory: bool = True  # mirrors Report: never a rejection signal
