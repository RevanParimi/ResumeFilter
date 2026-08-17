"""cross_field — advisory cross-field forensics (S2.2, PI-2).

Purely deterministic date/structure checks over the extracted profile —
NO LLM by design (the convention demands fallbacks for LLM steps, not LLMs
everywhere; month arithmetic needs no model). When the caller supplied an
extracted CandidateProfile (POST /candidates), that profile is used; otherwise
the node derives one with the deterministic heuristic extractor, so
POST /evaluate gets the same forensics at heuristic-extraction quality.
Findings never touch claim verdicts or depth scoring (S2.4 owns fusion)."""

from __future__ import annotations

from app.candidates.extractor import heuristic_profile
from app.candidates.normalize import normalize_profile
from app.core.logging import get_logger
from app.fabrication.cross_field import assess_cross_field
from app.graph.state import EvaluationState
from app.services import Services


def make_cross_field_node(services: Services):
    log = get_logger("node.cross_field")

    async def cross_field(state: EvaluationState) -> dict:
        text = (state.resume_text or "").strip()
        if not text:
            return {}

        profile = state.candidate_profile
        source = "extracted"
        if profile is None:
            profile = normalize_profile(heuristic_profile(text))
            source = "heuristic"

        assessment = assess_cross_field(profile, services.settings)
        log.info(
            "cross_field_done",
            band=assessment.band.value,
            findings=len(assessment.findings),
            confidence=round(assessment.confidence, 3),
            profile_source=source,
        )
        return {"cross_field": assessment}

    return cross_field
