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
