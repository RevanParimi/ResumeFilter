"""Fabrication-defense features (source FABRICATION, first-party, no consent)."""

from __future__ import annotations

from app.features.registry import register_feature
from app.features.schema import FeatureContext, FeatureDType, FeatureSource
from app.schemas.fabrication import FindingSeverity

_RISK_BANDS = ("insufficient_data", "low", "moderate", "elevated")
_AI_BANDS = ("insufficient_text", "unlikely", "possible", "likely")
_FARM_BANDS = ("insufficient_data", "unique", "similar", "near_duplicate")


@register_feature(
    name="fabrication.risk_score", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.FABRICATION,
    description="Unified advisory fabrication-risk score (S2.4).",
    valid_range=(0.0, 1.0),
)
def risk_score(ctx: FeatureContext) -> float | None:
    r = ctx.report
    if r is None or r.fabrication_risk is None:
        return None
    return r.fabrication_risk.score


@register_feature(
    name="fabrication.risk_band", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.FABRICATION,
    description="Unified advisory fabrication-risk band (S2.4).",
    categories=_RISK_BANDS,
)
def risk_band(ctx: FeatureContext) -> str | None:
    r = ctx.report
    if r is None or r.fabrication_risk is None:
        return None
    return r.fabrication_risk.band.value


@register_feature(
    name="fabrication.ai_generation_band", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.FABRICATION,
    description="AI-generated-resume likelihood band (S2.1).",
    categories=_AI_BANDS,
)
def ai_generation_band(ctx: FeatureContext) -> str | None:
    r = ctx.report
    if r is None or r.ai_generation is None:
        return None
    return r.ai_generation.band.value


@register_feature(
    name="fabrication.cross_field_major_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.FABRICATION,
    description="Count of MAJOR cross-field forensic findings (S2.2).",
)
def cross_field_major_count(ctx: FeatureContext) -> int | None:
    r = ctx.report
    if r is None or r.cross_field is None:
        return None
    return sum(1 for f in r.cross_field.findings if f.severity == FindingSeverity.MAJOR)


@register_feature(
    name="fabrication.resume_farm_band", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.FABRICATION,
    description="Resume-farm near-duplicate band (S2.3).",
    categories=_FARM_BANDS,
)
def resume_farm_band(ctx: FeatureContext) -> str | None:
    r = ctx.report
    if r is None or r.resume_farm is None:
        return None
    return r.resume_farm.band.value
