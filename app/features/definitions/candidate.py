"""Candidate-profile features (source CANDIDATE, first-party, no consent)."""

from __future__ import annotations

from app.candidates.schema import LinkType
from app.features.registry import register_feature
from app.features.schema import FeatureContext, FeatureDType, FeatureSource

_DEGREE_LEVELS = ("none", "diploma", "bachelor", "master", "doctorate")
_INST_TIERS = ("none", "tier_2", "tier_1")
_LOC_TIERS = ("unknown", "tier_2", "metro")


def _month_index(ym: str, *, end: bool) -> int | None:
    """'YYYY-MM' or 'YYYY' -> absolute month index. Year-only: Jan (start) / Dec (end)."""
    parts = ym.split("-")
    try:
        year = int(parts[0])
    except (ValueError, IndexError):
        return None
    if len(parts) >= 2 and parts[1].isdigit():
        month = int(parts[1])
    else:
        month = 12 if end else 1
    month = min(12, max(1, month))
    return year * 12 + (month - 1)


@register_feature(
    name="candidate.years_experience", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.CANDIDATE,
    description="Total non-overlapping months of professional experience, in years.",
    valid_range=(0.0, 60.0),
)
def years_experience(ctx: FeatureContext) -> float | None:
    p = ctx.profile
    if p is None:
        return None
    as_of_idx = ctx.as_of.year * 12 + (ctx.as_of.month - 1)
    intervals: list[tuple[int, int]] = []
    for exp in p.experience:
        d = exp.dates
        if not d.start:
            continue
        lo = _month_index(d.start, end=False)
        if lo is None:
            continue
        if d.is_current or not d.end:
            hi = as_of_idx
        else:
            hi = _month_index(d.end, end=True)
            if hi is None:
                hi = as_of_idx
        if hi < lo:
            continue
        intervals.append((lo, hi))
    if not intervals:
        return None
    intervals.sort()
    merged = [list(intervals[0])]
    for lo, hi in intervals[1:]:
        if lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    total_months = sum(hi - lo + 1 for lo, hi in merged)
    return min(60.0, round(total_months / 12.0, 2))


@register_feature(
    name="candidate.num_experiences", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Count of experience entries.",
)
def num_experiences(ctx: FeatureContext) -> int | None:
    return len(ctx.profile.experience) if ctx.profile else None


@register_feature(
    name="candidate.num_projects", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Count of project entries.",
)
def num_projects(ctx: FeatureContext) -> int | None:
    return len(ctx.profile.projects) if ctx.profile else None


@register_feature(
    name="candidate.num_certifications", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Count of certification entries.",
)
def num_certifications(ctx: FeatureContext) -> int | None:
    return len(ctx.profile.certifications) if ctx.profile else None


@register_feature(
    name="candidate.num_skills", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Count of listed skills.",
)
def num_skills(ctx: FeatureContext) -> int | None:
    return len(ctx.profile.skills) if ctx.profile else None


@register_feature(
    name="candidate.num_canonical_skills", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Count of skills mapped to the S1.4 taxonomy.",
)
def num_canonical_skills(ctx: FeatureContext) -> int | None:
    if ctx.profile is None:
        return None
    return sum(1 for s in ctx.profile.skills if s.canonical)


@register_feature(
    name="candidate.highest_degree_level", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.CANDIDATE,
    description="Highest normalized degree level attained.",
    categories=_DEGREE_LEVELS,
)
def highest_degree_level(ctx: FeatureContext) -> str | None:
    if ctx.profile is None:
        return None
    best = 0
    for edu in ctx.profile.education:
        lvl = (edu.degree_level or "").lower()
        if lvl in _DEGREE_LEVELS:
            best = max(best, _DEGREE_LEVELS.index(lvl))
    return _DEGREE_LEVELS[best]


@register_feature(
    name="candidate.max_cgpa_10", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.CANDIDATE,
    description="Highest canonical CGPA on the 10-point scale.",
    valid_range=(0.0, 10.0),
)
def max_cgpa_10(ctx: FeatureContext) -> float | None:
    if ctx.profile is None:
        return None
    vals = [e.grade_cgpa_10 for e in ctx.profile.education if e.grade_cgpa_10 is not None]
    return max(vals) if vals else None


@register_feature(
    name="candidate.top_institution_tier", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.CANDIDATE,
    description="Best institution tier across education entries.",
    categories=_INST_TIERS,
)
def top_institution_tier(ctx: FeatureContext) -> str | None:
    if ctx.profile is None:
        return None
    best = 0
    for edu in ctx.profile.education:
        tier = (edu.institution_tier or "").lower()
        if tier in _INST_TIERS:
            best = max(best, _INST_TIERS.index(tier))
    return _INST_TIERS[best]


@register_feature(
    name="candidate.notice_period_days", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Normalized notice-period days (0 = immediate joiner).",
    valid_range=(0.0, 365.0),
)
def notice_period_days(ctx: FeatureContext) -> int | None:
    if ctx.profile is None or ctx.profile.notice_period_days is None:
        return None
    return max(0, min(365, ctx.profile.notice_period_days))


@register_feature(
    name="candidate.location_tier", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.CANDIDATE,
    description="Candidate city tier (metro > tier_2 > unknown).",
    categories=_LOC_TIERS,
)
def location_tier(ctx: FeatureContext) -> str | None:
    if ctx.profile is None:
        return None
    tier = (ctx.profile.contact.location_tier or "").lower()
    return tier if tier in ("tier_2", "metro") else "unknown"


@register_feature(
    name="candidate.has_github", version=1,
    dtype=FeatureDType.BOOLEAN, source=FeatureSource.CANDIDATE,
    description="Whether the candidate shared a GitHub link.",
)
def has_github(ctx: FeatureContext) -> bool | None:
    if ctx.profile is None:
        return None
    return any(link.type == LinkType.GITHUB for link in ctx.profile.links)
