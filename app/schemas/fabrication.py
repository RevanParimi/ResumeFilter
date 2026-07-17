"""Fabrication-defense contracts (PI-2).

S2.1 — AI-generated-resume signals. ADVISORY ONLY: an AI-likelihood band is
stylistic context for a human reviewer, never a rejection signal. AI-assisted
resume WRITING is common and legitimate; whether the claims survive depth
evaluation is a separate question (S2.4 fuses these signals there).
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
