"""scoring — apply calibration to finalize per-claim status + aggregate depth.

Per-claim: run the conservative classifier over (coherence, confidence).
Aggregate: confidence-weighted depth score + advisory depth band. S2.4: fuse
the fabrication assessments into one advisory fabrication_risk — computed
here because this IS the calibration stage, but it never touches verdicts,
the depth score, or the depth band.
"""

from __future__ import annotations

from app.core.calibration import aggregate_depth, classify
from app.core.logging import get_logger
from app.fabrication.risk import assess_fabrication_risk
from app.graph.state import EvaluationState
from app.services import Services


def make_scoring_node(services: Services):
    log = get_logger("node.scoring")
    settings = services.settings

    async def scoring(state: EvaluationState) -> dict:
        verdicts = state.verdicts
        for v in verdicts:
            v.status = classify(
                coherence=v.coherence_score,
                confidence=v.confidence,
                has_evidence=bool(v.evidence),
                settings=settings,
            )

        depth, overall_conf, band = aggregate_depth(
            [(v.coherence_score, v.confidence) for v in verdicts], settings=settings
        )

        # S2.4: unified advisory fabrication risk. None when nothing was ever
        # assessed (e.g. resume text never arrived and no farm input).
        fabrication_risk = None
        if not (
            state.ai_generation is None
            and state.cross_field is None
            and state.resume_farm is None
        ):
            fabrication_risk = assess_fabrication_risk(
                state.ai_generation,
                state.cross_field,
                state.resume_farm,
                settings=settings,
            )
            log.info(
                "fabrication_risk",
                band=fabrication_risk.band.value,
                score=round(fabrication_risk.score, 3),
                components=len(fabrication_risk.components),
            )

        log.info("scored", depth=round(depth, 3), band=band, confidence=round(overall_conf, 3))
        return {
            "verdicts": verdicts,
            "depth_score": depth,
            "overall_confidence": overall_conf,
            "depth_band": band,
            "fabrication_risk": fabrication_risk,
        }

    return scoring
