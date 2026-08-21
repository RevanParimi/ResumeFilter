"""report — assemble the explainable, advisory report; feed the flywheel.

Mandates enforced here: human_review_required + advisory are always set; the
report never carries an auto-reject. Every (claim → probe → verdict) record is
logged to the flywheel with an open ``outcome`` field for later feedback.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.graph.state import EvaluationState
from app.schemas.extraction import CoverageBand
from app.schemas.fabrication import AILikelihoodBand, ConsistencyBand, DuplicationBand, FabricationRiskBand, FindingSeverity
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
        xf = state.cross_field
        if xf is not None and xf.band is ConsistencyBand.MAJOR_ISSUES:
            majors = sum(1 for f in xf.findings if f.severity is FindingSeverity.MAJOR)
            summary += (
                f" Cross-field consistency: {xf.band.value} ({majors} major of "
                f"{len(xf.findings)} findings) — timeline observations for the "
                f"reviewer to probe in conversation; never a rejection signal."
            )
        rf = state.resume_farm
        if rf is not None and rf.band is DuplicationBand.NEAR_DUPLICATE:
            summary += (
                f" Resume-farm signals: {len(rf.matches)} stored resume(s) from "
                f"other candidates share up to {rf.score:.0%} estimated content "
                f"overlap — shared templates are common and legitimate; reviewer "
                f"context only, never a rejection signal."
            )
        risk = state.fabrication_risk
        if risk is not None and risk.band in (
            FabricationRiskBand.MODERATE,
            FabricationRiskBand.ELEVATED,
        ):
            summary += (
                f" Unified fabrication risk: {risk.band.value} (score "
                f"{risk.score:.2f}, confidence {risk.confidence:.2f}) across "
                f"{len(risk.components)} signal(s) — fused advisory context for "
                f"the reviewer; it never changes the depth evaluation and is "
                f"never a rejection signal."
            )
        cov = state.extraction_coverage
        if cov is not None and cov.band is CoverageBand.MAJOR_GAPS:
            fields = sorted({g.field for g in cov.gaps if g.field})
            summary += (
                f" Extraction coverage: parts of this resume could not be read — "
                f"{', '.join(fields) or 'some sections'} appear in the document but "
                f"were not extracted, so checks over those fields report "
                f"insufficient data for a reason about the PARSER, not the candidate."
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
            cross_field=state.cross_field,
            resume_farm=state.resume_farm,
            fabrication_risk=state.fabrication_risk,
            extraction_coverage=state.extraction_coverage,
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

        if state.cross_field is not None:
            services.flywheel.log(
                {
                    "record_type": "cross_field",
                    "evaluation_id": state.evaluation_id,
                    "report_id": rep.id,
                    "domain": state.domain,
                    "band": state.cross_field.band.value,
                    "score": state.cross_field.score,
                    "confidence": state.cross_field.confidence,
                    "finding_ids": [f.id for f in state.cross_field.findings],
                    "outcome": None,  # closed later by human/hiring signal
                }
            )

        if state.resume_farm is not None:
            services.flywheel.log(
                {
                    "record_type": "resume_farm",
                    "evaluation_id": state.evaluation_id,
                    "report_id": rep.id,
                    "domain": state.domain,
                    "band": state.resume_farm.band.value,
                    "score": state.resume_farm.score,
                    "confidence": state.resume_farm.confidence,
                    "match_count": len(state.resume_farm.matches),
                    "corpus_size": state.resume_farm.corpus_size,
                    "outcome": None,  # closed later by human/hiring signal
                }
            )

        if state.fabrication_risk is not None:
            services.flywheel.log(
                {
                    "record_type": "fabrication_risk",
                    "evaluation_id": state.evaluation_id,
                    "report_id": rep.id,
                    "domain": state.domain,
                    "band": state.fabrication_risk.band.value,
                    "score": state.fabrication_risk.score,
                    "confidence": state.fabrication_risk.confidence,
                    "components": {c.id: c.band for c in state.fabrication_risk.components},
                    "outcome": None,  # closed later by human/hiring signal
                }
            )

        log.info("report_ready", report_id=rep.id, flagged=len(flagged), deferred=len(deferred))
        return {"report": rep}

    return report
