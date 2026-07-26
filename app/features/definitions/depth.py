"""Depth-evaluation report features (source DEPTH, first-party, no consent)."""

from __future__ import annotations

from app.features.registry import register_feature
from app.features.schema import FeatureContext, FeatureDType, FeatureSource
from app.schemas.report import VerdictStatus

_DEPTH_BANDS = ("insufficient_signal", "superficial", "emerging", "solid", "deep")


@register_feature(
    name="depth.depth_score", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.DEPTH,
    description="Aggregate depth score from the latest report.",
    valid_range=(0.0, 1.0),
)
def depth_score(ctx: FeatureContext) -> float | None:
    return ctx.report.depth_score if ctx.report else None


@register_feature(
    name="depth.overall_confidence", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.DEPTH,
    description="Overall evaluation confidence from the latest report.",
    valid_range=(0.0, 1.0),
)
def overall_confidence(ctx: FeatureContext) -> float | None:
    return ctx.report.overall_confidence if ctx.report else None


@register_feature(
    name="depth.depth_band", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.DEPTH,
    description="Advisory depth band from the latest report.",
    categories=_DEPTH_BANDS,
)
def depth_band(ctx: FeatureContext) -> str | None:
    return ctx.report.depth_band.value if ctx.report else None


@register_feature(
    name="depth.verdict_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.DEPTH,
    description="Number of claim verdicts in the latest report.",
)
def verdict_count(ctx: FeatureContext) -> int | None:
    return len(ctx.report.verdicts) if ctx.report else None


@register_feature(
    name="depth.flagged_claim_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.DEPTH,
    description="Number of flagged (incoherent) claims.",
)
def flagged_claim_count(ctx: FeatureContext) -> int | None:
    return len(ctx.report.flagged_claim_ids) if ctx.report else None


@register_feature(
    name="depth.deferred_claim_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.DEPTH,
    description="Number of deferred (low-confidence) claims.",
)
def deferred_claim_count(ctx: FeatureContext) -> int | None:
    return len(ctx.report.deferred_claim_ids) if ctx.report else None


@register_feature(
    name="depth.coherent_claim_ratio", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.DEPTH,
    description="Fraction of verdicts that are coherent.",
    valid_range=(0.0, 1.0),
)
def coherent_claim_ratio(ctx: FeatureContext) -> float | None:
    if ctx.report is None or not ctx.report.verdicts:
        return None
    coherent = sum(1 for v in ctx.report.verdicts if v.status == VerdictStatus.COHERENT)
    return round(coherent / len(ctx.report.verdicts), 4)
