"""``EvaluationState`` — the single object threaded through the LangGraph.

Each node reads what it needs and returns a partial dict of updates. The
pipeline is linear and every field is written at most once, so default
LastValue channel semantics are correct (no custom reducers needed).

This state is DOMAIN-AGNOSTIC: ``domain`` selects a DomainModel at runtime;
no GenAI specifics appear here.
"""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field

from app.candidates.schema import CandidateProfile
from app.schemas.claims import CandidateContext, Claim
from app.schemas.extraction import ExtractionCoverage
from app.schemas.fabrication import AIGenerationAssessment, CrossFieldAssessment, FabricationRiskAssessment, ResumeFarmAssessment
from app.schemas.report import CoherenceVerdict, DepthBand, Report


class EvaluationState(BaseModel):
    """Mutable evaluation context carried across all graph nodes."""

    model_config = {"arbitrary_types_allowed": True}

    # --- identity / inputs ----------------------------------------------------
    evaluation_id: str = Field(default_factory=lambda: f"eval_{uuid.uuid4().hex[:12]}")
    domain: str = "genai"
    # Exactly one of these is provided by the caller.
    raw_resume_text: Optional[str] = None
    resume_pdf_b64: Optional[str] = None
    # First-party links the candidate chose to share (consent-clean).
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    # S2.2: the extracted profile, when the caller already has one
    # (POST /candidates). None => cross_field derives a heuristic profile.
    candidate_profile: Optional[CandidateProfile] = None
    # S2.3: resume-farm assessment computed by the API layer. Detection needs
    # the candidate store AND the uploader's candidate_id for self-exclusion —
    # the graph deliberately sees neither, so this arrives as an input.
    # None => not assessed (ad-hoc POST /evaluate runs).
    resume_farm: Optional[ResumeFarmAssessment] = None
    # S9.2: extraction coverage, computed in extract_profile (both doors) and
    # handed in the way resume_farm is -- the graph never re-derives it.
    extraction_coverage: Optional[ExtractionCoverage] = None

    # --- ingest ---------------------------------------------------------------
    resume_text: Optional[str] = None  # normalized, parsed text

    # --- ai_signals (S2.1) ------------------------------------------------------
    # Advisory AI-generation assessment; None when resume text never arrived.
    ai_generation: Optional[AIGenerationAssessment] = None

    # --- cross_field (S2.2) -----------------------------------------------------
    # Advisory cross-field forensics; None when resume text never arrived.
    cross_field: Optional[CrossFieldAssessment] = None

    # --- claim_extraction -----------------------------------------------------
    candidate_context: CandidateContext = Field(default_factory=CandidateContext)
    claims: list[Claim] = Field(default_factory=list)

    # --- provenance -----------------------------------------------------------
    # claim_id -> list of human-readable grounding strings fetched/retrieved.
    provenance: dict[str, list[str]] = Field(default_factory=dict)

    # --- plausibility / probe / scoring ---------------------------------------
    # Verdicts are built incrementally: plausibility seeds them, probe_generation
    # attaches questions, scoring finalizes status/score.
    verdicts: list[CoherenceVerdict] = Field(default_factory=list)

    # --- scoring (aggregate) --------------------------------------------------
    depth_score: float = 0.0
    overall_confidence: float = 0.0
    depth_band: DepthBand = DepthBand.INSUFFICIENT_SIGNAL
    # S2.4: unified advisory fabrication risk, fused in the calibration stage
    # (scoring node) from ai_generation + cross_field + resume_farm. None when
    # none of the three was ever assessed. Never affects depth or verdicts.
    fabrication_risk: Optional[FabricationRiskAssessment] = None

    # --- report ---------------------------------------------------------------
    report: Optional[Report] = None

    # --- diagnostics ----------------------------------------------------------
    errors: list[str] = Field(default_factory=list)
