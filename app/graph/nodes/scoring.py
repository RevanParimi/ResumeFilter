"""scoring — apply calibration to finalize per-claim status + aggregate depth.

Per-claim: run the conservative classifier over (coherence, confidence).
Aggregate: confidence-weighted depth score + advisory depth band. No new
judgments here — only calibration of plausibility's output.
"""

from __future__ import annotations

from app.core.calibration import aggregate_depth, classify
from app.core.logging import get_logger
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

        log.info("scored", depth=round(depth, 3), band=band, confidence=round(overall_conf, 3))
        return {
            "verdicts": verdicts,
            "depth_score": depth,
            "overall_confidence": overall_conf,
            "depth_band": band,
        }

    return scoring
