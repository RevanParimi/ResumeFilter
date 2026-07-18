"""Fabrication-defense contracts (PI-2).

S2.1 — AI-generated-resume signals. ADVISORY ONLY: an AI-likelihood band is
stylistic context for a human reviewer, never a rejection signal. AI-assisted
resume WRITING is common and legitimate; whether the claims survive depth
evaluation is a separate question (S2.4 fuses these signals there).
S2.2 — cross-field forensics: deterministic timeline/coherence findings.
S2.3 — resume-farm detection: cross-candidate near-duplicate signals (MinHash).
S2.4 — unified fabrication risk: advisory fusion of the three signals above.
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


class DuplicationBand(StrEnum):
    """Conservative advisory bands. INSUFFICIENT_DATA when we can't say."""

    INSUFFICIENT_DATA = "insufficient_data"
    UNIQUE = "unique"            # nothing similar among stored resumes
    SIMILAR = "similar"          # notable content overlap with another candidate
    NEAR_DUPLICATE = "near_duplicate"  # near-identical content, or a farm-like cluster


class ResumeMatch(BaseModel):
    """One stored resume (another candidate's) with estimated content overlap."""

    candidate_id: str
    resume_id: str
    similarity: float = Field(ge=0.0, le=1.0)  # estimated Jaccard over shingles


class ResumeFarmAssessment(BaseModel):
    """The farm-detection output: cross-candidate near-duplicate signals.

    Computed in the API layer (needs the candidate store + the uploader's
    identity for self-exclusion — the graph never sees either). Shared resume
    templates are common and legitimate; ADVISORY, never a rejection signal."""

    score: float = Field(default=0.0, ge=0.0, le=1.0)  # max match similarity
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    band: DuplicationBand = DuplicationBand.INSUFFICIENT_DATA
    matches: list[ResumeMatch] = Field(default_factory=list)
    corpus_size: int = 0  # fingerprinted resumes (other candidates) compared against
    reasoning: str = ""
    advisory: bool = True  # mirrors Report: never a rejection signal


class FabricationRiskBand(StrEnum):
    """S2.4 — conservative advisory bands. INSUFFICIENT_DATA when we can't say."""

    INSUFFICIENT_DATA = "insufficient_data"
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"


class RiskComponent(BaseModel):
    """One subsystem's contribution to the unified fabrication risk."""

    id: str          # "ai_generation" | "cross_field" | "resume_farm"
    band: str        # the component's own band value at fusion time
    risk: float = Field(ge=0.0, le=1.0)        # band-mapped component risk
    confidence: float = Field(ge=0.0, le=1.0)  # component's own confidence
    weight: float = Field(ge=0.0)              # config weight x confidence
    flagged: bool = False                      # component sits at its top band


class FabricationRiskAssessment(BaseModel):
    """S2.4 — unified advisory fusion of ai_generation + cross_field + resume_farm.

    Computed in the calibration stage (scoring node). ADVISORY ONLY: never
    changes verdicts, depth scores, or bands, and never a rejection signal."""

    score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    band: FabricationRiskBand = FabricationRiskBand.INSUFFICIENT_DATA
    components: list[RiskComponent] = Field(default_factory=list)
    reasoning: str = ""
    advisory: bool = True  # mirrors Report: never a rejection signal
