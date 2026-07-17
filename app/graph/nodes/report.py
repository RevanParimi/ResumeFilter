"""report — assemble the explainable, advisory report; feed the flywheel.

Mandates enforced here: human_review_required + advisory are always set; the
report never carries an auto-reject. Every (claim → probe → verdict) record is
logged to the flywheel with an open ``outcome`` field for later feedback.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.graph.state import EvaluationState
from app.schemas.fabrication import AILikelihoodBand
from app.schemas.report import Report, VerdictStatus
from app.services import Services


def make_report_node(services: Services):
    log = get_logger("node.report")

    async def report(state: EvaluationState) -> dict:
        verdicts = state.verdicts
        flagged = [v.claim_id for v in verdicts if v.status == VerdictStatus.INCOHERENT]
        deferred = [v.claim_id for v in verdicts if v.status == VerdictStatus.DEFER]

        summary = (
            f"{len(verdicts)} claims assessed: {len(flagged)} flagged incoherent, "
            f"{len(deferred)} deferred for human review. Depth band: "
            f"{state.depth_band.value} (score {state.depth_score:.2f}, "
            f"confidence {state.overall_confidence:.2f}). ADVISORY ONLY — a human "
            f"reviewer makes the decision; this system never auto-rejects."
        )
        ai = state.ai_generation
        if ai is not None and ai.band in (AILikelihoodBand.POSSIBLE, AILikelihoodBand.LIKELY):
            summary += (
                f" AI-generation signals: {ai.band.value} "
                f"(likelihood {ai.likelihood:.2f}, confidence {ai.confidence:.2f}) — "
                f"stylistic context only; AI-assisted writing is common and this "
                f"is never a rejection signal."
            )

        rep = Report(
            id=f"rep_{state.evaluation_id.split('_', 1)[-1]}",
            domain=state.domain,
            candidate_context=state.candidate_context,
            verdicts=verdicts,
            depth_score=state.depth_score,
            depth_band=state.depth_band,
            overall_confidence=state.overall_confidence,
            advisory=True,
            human_review_required=True,
            summary=summary,
            flagged_claim_ids=flagged,
            deferred_claim_ids=deferred,
            ai_generation=state.ai_generation,
        )

        # Flywheel: one record per claim, outcome left open for later feedback.
        for v in verdicts:
            services.flywheel.log(
                {
                    "evaluation_id": state.evaluation_id,
                    "report_id": rep.id,
                    "domain": state.domain,
                    "claim_id": v.claim_id,
                    "claim_text": v.claim_text,
                    "claim_type": v.claim_type,
                    "coherence_score": v.coherence_score,
                    "confidence": v.confidence,
                    "status": v.status.value,
                    "probes": v.probes,
                    "evidence_count": len(v.evidence),
                    "outcome": None,  # closed later by human/hiring signal
                }
            )

        if state.ai_generation is not None:
            services.flywheel.log(
                {
                    "record_type": "ai_signals",
                    "evaluation_id": state.evaluation_id,
                    "report_id": rep.id,
                    "domain": state.domain,
                    "band": state.ai_generation.band.value,
                    "likelihood": state.ai_generation.likelihood,
                    "confidence": state.ai_generation.confidence,
                    "signal_ids": [s.id for s in state.ai_generation.signals],
                    "outcome": None,  # closed later by human/hiring signal
                }
            )

        log.info("report_ready", report_id=rep.id, flagged=len(flagged), deferred=len(deferred))
        return {"report": rep}

    return report
