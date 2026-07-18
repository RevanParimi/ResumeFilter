"""S2.4 — unified fabrication risk: fuse ai_generation + cross_field + resume_farm.

Pure functions, no I/O, no LLM. ADVISORY ONLY: the fused band is reviewer
context computed in the calibration stage — it never changes a verdict, the
depth score, or the depth band, and it is never a rejection signal.

Conservative by construction: absent/insufficient subsystem signals are
excluded from fusion (absence of signal is not evidence of risk); ELEVATED
requires >= 2 components at their top band; fusion over a single subsystem
never clears the confidence floor, so it never asserts.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.schemas.fabrication import (
    AIGenerationAssessment,
    AILikelihoodBand,
    ConsistencyBand,
    CrossFieldAssessment,
    DuplicationBand,
    FabricationRiskAssessment,
    FabricationRiskBand,
    ResumeFarmAssessment,
    RiskComponent,
)

# Band -> component risk. Insufficient bands are absent on purpose: they are
# excluded from fusion entirely. Code constants, not config — change deliberately.
_AI_RISK = {
    AILikelihoodBand.UNLIKELY: 0.10,
    AILikelihoodBand.POSSIBLE: 0.45,
    AILikelihoodBand.LIKELY: 0.75,
}
_XF_RISK = {
    ConsistencyBand.CONSISTENT: 0.10,
    ConsistencyBand.MINOR_ISSUES: 0.40,
    ConsistencyBand.MAJOR_ISSUES: 0.75,
}
_RF_RISK = {
    DuplicationBand.UNIQUE: 0.10,
    DuplicationBand.SIMILAR: 0.45,
    DuplicationBand.NEAR_DUPLICATE: 0.80,
}

# A pure weighted mean lets clean subsystems dilute one strong signal; a pure
# max ignores corroboration. The 70/30 blend keeps a single strong signal
# visible (MODERATE) while ELEVATED still needs corroborating components.
_MEAN_WEIGHT = 0.7
_MAX_WEIGHT = 0.3


def build_components(
    ai: AIGenerationAssessment | None,
    cross_field: CrossFieldAssessment | None,
    resume_farm: ResumeFarmAssessment | None,
    *,
    settings: Settings | None = None,
) -> list[RiskComponent]:
    """One RiskComponent per assessment that has data; insufficient bands are
    excluded entirely — absence of signal is not evidence of risk."""
    s = settings or get_settings()
    out: list[RiskComponent] = []
    if ai is not None and ai.band in _AI_RISK:
        out.append(
            RiskComponent(
                id="ai_generation",
                band=ai.band.value,
                risk=_AI_RISK[ai.band],
                confidence=ai.confidence,
                weight=s.fr_weight_ai * ai.confidence,
                flagged=ai.band is AILikelihoodBand.LIKELY,
            )
        )
    if cross_field is not None and cross_field.band in _XF_RISK:
        out.append(
            RiskComponent(
                id="cross_field",
                band=cross_field.band.value,
                risk=_XF_RISK[cross_field.band],
                confidence=cross_field.confidence,
                weight=s.fr_weight_cross_field * cross_field.confidence,
                flagged=cross_field.band is ConsistencyBand.MAJOR_ISSUES,
            )
        )
    if resume_farm is not None and resume_farm.band in _RF_RISK:
        out.append(
            RiskComponent(
                id="resume_farm",
                band=resume_farm.band.value,
                risk=_RF_RISK[resume_farm.band],
                confidence=resume_farm.confidence,
                weight=s.fr_weight_farm * resume_farm.confidence,
                flagged=resume_farm.band is DuplicationBand.NEAR_DUPLICATE,
            )
        )
    return out


def fuse_components(components: list[RiskComponent]) -> tuple[float, float]:
    """(score, confidence). Score blends the weighted mean with the max
    component risk (70/30); confidence follows coverage, same shape as
    S2.1/S2.2: min(0.9, 0.30 + 0.15 * evaluated). One component -> 0.45,
    which sits below fr_min_confidence — single-subsystem fusion never asserts."""
    if not components:
        return 0.0, 0.0
    total_weight = sum(c.weight for c in components)
    if total_weight > 0:
        mean = sum(c.risk * c.weight for c in components) / total_weight
    else:  # defensive: evaluable components with zero confidence
        mean = sum(c.risk for c in components) / len(components)
    score = _MEAN_WEIGHT * mean + _MAX_WEIGHT * max(c.risk for c in components)
    # Coverage-count confidence is safe only because every subsystem floors its
    # own confidence before emitting an evaluable band (ai/xf >= 0.50, rf >= 0.60)
    # — a component can never arrive here as evaluable-but-worthless.
    confidence = min(0.9, round(0.30 + 0.15 * len(components), 2))
    return score, confidence


def band_for_risk(
    score: float,
    confidence: float,
    flagged_count: int,
    *,
    settings: Settings | None = None,
) -> FabricationRiskBand:
    """Conservative banding: never assert under the confidence floor; ELEVATED
    requires corroboration (>= 2 components at their top band), mirroring
    S2.1's 'LIKELY needs >= 2 deterministic tells'."""
    s = settings or get_settings()
    if confidence < s.fr_min_confidence:
        return FabricationRiskBand.INSUFFICIENT_DATA
    if score >= s.fr_elevated_threshold and flagged_count >= 2:
        return FabricationRiskBand.ELEVATED
    if score >= s.fr_moderate_threshold:
        return FabricationRiskBand.MODERATE
    return FabricationRiskBand.LOW


def assess_fabrication_risk(
    ai: AIGenerationAssessment | None,
    cross_field: CrossFieldAssessment | None,
    resume_farm: ResumeFarmAssessment | None,
    *,
    settings: Settings | None = None,
) -> FabricationRiskAssessment:
    """Fuse whatever subsystems produced an assessable signal into one advisory
    band. Excluded subsystems (absent or insufficient) never count as risk."""
    s = settings or get_settings()
    components = build_components(ai, cross_field, resume_farm, settings=s)
    if not components:
        return FabricationRiskAssessment(
            band=FabricationRiskBand.INSUFFICIENT_DATA,
            reasoning=(
                "No fabrication subsystem produced an assessable signal; nothing to "
                "fuse. Advisory only — never a rejection signal."
            ),
        )
    score, confidence = fuse_components(components)
    flagged = sum(1 for c in components if c.flagged)
    band = band_for_risk(score, confidence, flagged, settings=s)
    parts = ", ".join(f"{c.id}={c.band}" for c in components)
    reasoning = (
        f"Fused {len(components)} fabrication signal(s): {parts}. Unified risk "
        f"{score:.2f} (confidence {confidence:.2f}) -> {band.value}. Advisory "
        f"context for a human reviewer — fabrication signals never change "
        f"verdicts or depth scores, and are never a rejection signal."
    )
    return FabricationRiskAssessment(
        score=score,
        confidence=confidence,
        band=band,
        components=components,
        reasoning=reasoning,
    )
