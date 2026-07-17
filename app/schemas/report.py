"""Report-side contracts: explainable, advisory output.

Design mandates encoded here:
  * EXPLAINABILITY — no bare "fake"/"real". Every verdict carries a coherence
    score, confidence, an evidence trail, reasoning, and probe questions.
  * HUMAN-IN-LOOP — :class:`Report.human_review_required` is always True and the
    system is advisory; it never carries an auto-reject decision.
  * CALIBRATION — :class:`VerdictStatus` includes DEFER, used whenever confidence
    is too low to assert anything.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.claims import CandidateContext
from app.schemas.fabrication import AIGenerationAssessment, CrossFieldAssessment


class EvidenceSource(StrEnum):
    RULE = "rule"            # DomainModel rule registry
    LLM = "llm"              # domain-expert model reasoning
    GITHUB = "github"        # provenance fetch
    VECTORSTORE = "vectorstore"  # retrieved grounding


class Polarity(StrEnum):
    SUPPORTS = "supports"        # raises coherence
    CONTRADICTS = "contradicts"  # lowers coherence (a "tell")
    NEUTRAL = "neutral"


class Evidence(BaseModel):
    """One item in a claim's evidence trail — always human-readable."""

    source: EvidenceSource
    polarity: Polarity
    detail: str
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    ref: Optional[str] = None  # rule id, repo url, doc id, ...


class VerdictStatus(StrEnum):
    """Per-claim outcome. Conservative by construction."""

    COHERENT = "coherent"        # claim hangs together
    INCOHERENT = "incoherent"    # flagged: low coherence AND high confidence
    DEFER = "defer"              # not confident enough to assert — human decides
    UNVERIFIED = "unverified"    # no evidence either way (e.g. no anchor, LLM off)


class CoherenceVerdict(BaseModel):
    """The explainable unit: one claim, fully reasoned."""

    claim_id: str
    claim_text: str
    claim_type: str
    status: VerdictStatus = VerdictStatus.UNVERIFIED
    coherence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str = ""
    # What a genuine version of this claim would exhibit vs. what's absent.
    expected_signals: list[str] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    probes: list[str] = Field(default_factory=list)


class DepthBand(StrEnum):
    """Aggregate, advisory band. INSUFFICIENT_SIGNAL when we can't responsibly say."""

    INSUFFICIENT_SIGNAL = "insufficient_signal"
    SUPERFICIAL = "superficial"
    EMERGING = "emerging"
    SOLID = "solid"
    DEEP = "deep"


class Report(BaseModel):
    """The advisory assessment returned by the API and persisted."""

    id: str = Field(default_factory=lambda: f"rep_{uuid.uuid4().hex[:12]}")
    domain: str = "genai"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # PI-1 linkage: which stored candidate this report evaluates. None for
    # ad-hoc POST /evaluate runs that never touched the candidate store.
    candidate_id: Optional[str] = None

    candidate_context: CandidateContext = Field(default_factory=CandidateContext)
    verdicts: list[CoherenceVerdict] = Field(default_factory=list)

    depth_score: float = Field(default=0.0, ge=0.0, le=1.0)
    depth_band: DepthBand = DepthBand.INSUFFICIENT_SIGNAL
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Mandates, made explicit on the wire.
    advisory: bool = True
    human_review_required: bool = True
    summary: str = ""

    # Claims the reviewer should look at first (incoherent or deferred).
    flagged_claim_ids: list[str] = Field(default_factory=list)
    deferred_claim_ids: list[str] = Field(default_factory=list)

    # S2.1: advisory AI-generation signals (stylistic context, never a verdict;
    # fusion into calibration is S2.4). None for pre-S2.1 stored reports.
    ai_generation: Optional[AIGenerationAssessment] = None

    # S2.2: advisory cross-field forensics (timeline/coherence observations for
    # the reviewer, never a verdict; fusion into calibration is S2.4). None for
    # pre-S2.2 stored reports.
    cross_field: Optional[CrossFieldAssessment] = None
