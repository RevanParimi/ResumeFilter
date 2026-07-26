"""Ledger + reputation features (consent-gated cross-company signals).

Source LEDGER/REPUTATION, requires_consent=True: S4.2/S4.3 must hold an active
ledger_read grant to materialize/serve these. Definition-time carries no consent
obligation.
"""

from __future__ import annotations

from app.features.registry import register_feature
from app.features.schema import FeatureContext, FeatureDType, FeatureSource

_REP_BANDS = ("insufficient_data", "guarded", "mixed", "favorable", "strong")


@register_feature(
    name="ledger.interview_record_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.LEDGER,
    description="Number of consented cross-company interview records.",
    nullable=False, requires_consent=True,
)
def interview_record_count(ctx: FeatureContext) -> int:
    return len(ctx.interview_records)


@register_feature(
    name="ledger.coding_round_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.LEDGER,
    description="Number of consented cross-company coding-round results.",
    nullable=False, requires_consent=True,
)
def coding_round_count(ctx: FeatureContext) -> int:
    return len(ctx.coding_rounds)


@register_feature(
    name="ledger.distinct_orgs", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.LEDGER,
    description="Distinct organizations across records and coding rounds.",
    nullable=False, requires_consent=True,
)
def distinct_orgs(ctx: FeatureContext) -> int:
    orgs = {r.org_id for r in ctx.interview_records}
    orgs |= {c.org_id for c in ctx.coding_rounds}
    return len(orgs)


@register_feature(
    name="ledger.best_coding_percentile", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.LEDGER,
    description="Highest coding-round percentile (None if none reported).",
    valid_range=(0.0, 100.0), requires_consent=True,
)
def best_coding_percentile(ctx: FeatureContext) -> float | None:
    vals = [c.percentile for c in ctx.coding_rounds if c.percentile is not None]
    return max(vals) if vals else None


@register_feature(
    name="reputation.score", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.REPUTATION,
    description="Advisory cross-company reputation score (S3.4).",
    valid_range=(0.0, 1.0), nullable=False, requires_consent=True,
)
def reputation_score(ctx: FeatureContext) -> float:
    return ctx.reputation.score


@register_feature(
    name="reputation.confidence", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.REPUTATION,
    description="Confidence of the advisory reputation estimate (S3.4).",
    valid_range=(0.0, 1.0), nullable=False, requires_consent=True,
)
def reputation_confidence(ctx: FeatureContext) -> float:
    return ctx.reputation.confidence


@register_feature(
    name="reputation.band", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.REPUTATION,
    description="Advisory cross-company reputation band (S3.4).",
    categories=_REP_BANDS, nullable=False, requires_consent=True,
)
def reputation_band(ctx: FeatureContext) -> str:
    return ctx.reputation.band.value
