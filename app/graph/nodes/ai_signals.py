"""ai_signals — advisory AI-generated-resume assessment (S2.1, PI-2).

Deterministic stylometry FIRST (app/fabrication/ai_text.py), an LLM pass
SECOND (best-effort, confidence-capped), fused conservatively. The band is
context for a human reviewer: it never touches claim verdicts or depth
scoring here (S2.4 owns fusion into calibration), and LIKELY requires at
least two independent deterministic tells — the LLM alone can never flag.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.fabrication.ai_text import assess_deterministic, band_for, fuse_pairs
from app.graph.state import EvaluationState
from app.schemas.fabrication import AIGenerationAssessment, AISignal, SignalSource
from app.services import Services

# Stylometry-by-LLM is weak evidence — capped below plausibility's 0.85.
_LLM_MAX_CONFIDENCE = 0.75


async def _llm_assessment(
    services: Services, text: str
) -> tuple[tuple[float, float] | None, list[AISignal], str]:
    """Returns ((likelihood, confidence) | None, llm signals, reasoning)."""
    excerpt = text[: services.settings.ai_llm_excerpt_chars]
    system = (
        "You are a forensic writing analyst. Judge whether this resume TEXT "
        "reads as LLM-generated (phrasing, uniformity, template structure) — "
        "NOT whether its claims are true. AI-assisted resume writing is common "
        "and legitimate, so be conservative. Return strict JSON only."
    )
    prompt = (
        f"RESUME:\n{excerpt}\n\n"
        "Return JSON: {likelihood: 0..1, confidence: 0..1, "
        "indicators: [str], reasoning: str}."
    )
    # FAST tier on purpose: this opinion is architecturally non-decisive
    # (confidence-capped, can never produce LIKELY alone), so it doesn't earn
    # flagship-model spend the way plausibility's per-claim reasoning does.
    try:
        data = await services.llm.acomplete_json(tier="parsing", system=system, prompt=prompt)
    except Exception:
        return None, [], ""
    if not data or "likelihood" not in data:
        return None, [], ""
    likelihood = max(0.0, min(1.0, float(data.get("likelihood", 0.0))))
    confidence = max(0.0, min(_LLM_MAX_CONFIDENCE, float(data.get("confidence", 0.0))))
    signals = [
        AISignal(id="llm_indicator", detail=str(i), score=likelihood, source=SignalSource.LLM)
        for i in list(data.get("indicators", []))[:5]
        if str(i).strip()
    ]
    return (likelihood, confidence), signals, str(data.get("reasoning", "")).strip()


def make_ai_signals_node(services: Services):
    log = get_logger("node.ai_signals")

    async def ai_signals(state: EvaluationState) -> dict:
        text = (state.resume_text or "").strip()
        if not text:
            return {}

        det = assess_deterministic(text)
        pairs: list[tuple[float, float]] = []
        if det.evaluated:
            pairs.append((det.likelihood, det.confidence))

        llm_pair, llm_signals, llm_reasoning = await _llm_assessment(services, text)
        if llm_pair is not None:
            pairs.append(llm_pair)

        likelihood, confidence = fuse_pairs(pairs)
        band = band_for(likelihood, confidence, len(det.signals), services.settings)

        parts = []
        if det.evaluated:
            parts.append(
                f"[deterministic] {len(det.signals)}/{det.evaluated} tells fired"
            )
        if llm_reasoning:
            parts.append(f"[llm] {llm_reasoning}")

        assessment = AIGenerationAssessment(
            likelihood=likelihood,
            confidence=confidence,
            band=band,
            signals=det.signals + llm_signals,
            reasoning=" ".join(parts),
            advisory=True,
        )
        log.info(
            "ai_signals_done",
            band=band.value,
            likelihood=round(likelihood, 3),
            confidence=round(confidence, 3),
            signals=len(assessment.signals),
        )
        return {"ai_generation": assessment}

    return ai_signals
