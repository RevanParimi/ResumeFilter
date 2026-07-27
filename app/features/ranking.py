"""Pure, deterministic talent-ranking engine (PI-4 / S4.3).

No I/O, no store, no wall clock (the app/fabrication/risk.py pattern). Operates
over already-materialized FeatureVector values + the FeatureSpecs the caller
resolves from the registry. Advisory: filters narrow, scoring orders; a
missing/consent-withheld value is dropped and never penalizes a candidate.
"""

from __future__ import annotations

from typing import Optional

from app.features.ranking_schema import (
    Contribution, FeatureFilter, FilterOp, RankedCandidate, RankingSpec, SortDirection,
)
from app.features.schema import FeatureDType, FeatureSpec, FeatureValue, FeatureVector

_NUMERIC = {FeatureDType.NUMERIC, FeatureDType.INTEGER}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _minmax(x: float, lo: float, hi: float) -> float:
    return 0.5 if hi == lo else _clamp01((x - lo) / (hi - lo))


def normalize_value(
    spec: FeatureSpec,
    value: FeatureValue,
    *,
    direction: SortDirection = SortDirection.HIGHER_BETTER,
    pool: Optional[list] = None,
) -> Optional[float]:
    """Map ``value`` to [0,1]; None -> None (the missing-term signal)."""
    if value is None:
        return None

    if spec.dtype is FeatureDType.BOOLEAN:
        norm = 1.0 if value else 0.0
    elif spec.dtype is FeatureDType.ORDINAL:
        cats = spec.categories or ()
        if value not in cats:
            raise ValueError(f"{value!r} not a category of {spec.name!r}")
        norm = 0.0 if len(cats) <= 1 else cats.index(value) / (len(cats) - 1)
    elif spec.dtype in _NUMERIC:
        x = float(value)
        if spec.valid_range is not None:
            lo, hi = spec.valid_range
            norm = _minmax(x, lo, hi)
        else:
            vals = [float(v) for v in (pool or []) if v is not None]
            norm = 0.5 if len(vals) < 2 else _minmax(x, min(vals), max(vals))
    else:  # CATEGORICAL (non-ordinal)
        raise ValueError(f"categorical feature {spec.name!r} is not rankable")

    return 1.0 - norm if direction is SortDirection.LOWER_BETTER else norm


_ORDER_OPS = {FilterOp.GT, FilterOp.GTE, FilterOp.LT, FilterOp.LTE}
_ORDERABLE = {FeatureDType.NUMERIC, FeatureDType.INTEGER, FeatureDType.ORDINAL}


def _order_key(spec: FeatureSpec, value):
    """Comparable key for ordered ops: category index for ordinal, else the value."""
    if spec.dtype is FeatureDType.ORDINAL:
        cats = spec.categories or ()
        if value not in cats:
            raise ValueError(f"{value!r} not a category of {spec.name!r}")
        return cats.index(value)
    return value


def _match(spec: FeatureSpec, value, op: FilterOp, target) -> bool:
    if op is FilterOp.EXISTS:
        return value is not None
    if op is FilterOp.MISSING:
        return value is None
    if value is None:
        return False
    if op is FilterOp.EQ:
        return value == target
    if op is FilterOp.NE:
        return value != target
    if op is FilterOp.IN:
        return value in target
    if op is FilterOp.NOT_IN:
        return value not in target
    # ordered ops
    if spec.dtype not in _ORDERABLE:
        raise ValueError(f"{op.value} is not valid on dtype {spec.dtype.value} ({spec.name!r})")
    lhs, rhs = _order_key(spec, value), _order_key(spec, target)
    if op is FilterOp.GT:
        return lhs > rhs
    if op is FilterOp.GTE:
        return lhs >= rhs
    if op is FilterOp.LT:
        return lhs < rhs
    return lhs <= rhs  # FilterOp.LTE


def apply_filters(
    vectors: list[FeatureVector],
    filters: list[FeatureFilter],
    specs_by_name: dict[str, FeatureSpec],
) -> list[FeatureVector]:
    out = list(vectors)
    for f in filters:
        spec = specs_by_name.get(f.feature)
        if spec is None:
            raise KeyError(f"unknown feature in filter: {f.feature}")
        out = [v for v in out if _match(spec, v.values.get(f.feature), f.op, f.value)]
    return out


def score(
    vectors: list[FeatureVector],
    spec: RankingSpec,
    specs_by_name: dict[str, FeatureSpec],
) -> list[RankedCandidate]:
    # Per-feature pools (present values) feed the range-less-numeric fallback.
    pools = {
        term.feature: [
            v.values.get(term.feature) for v in vectors
            if v.values.get(term.feature) is not None
        ]
        for term in spec.terms
    }
    total_weight = sum(t.weight for t in spec.terms)

    results: list[RankedCandidate] = []
    for v in vectors:
        contributions: list[Contribution] = []
        missing: list[str] = []
        present_weight = 0.0
        acc = 0.0
        for term in spec.terms:
            fspec = specs_by_name.get(term.feature)
            if fspec is None:
                raise KeyError(f"unknown feature in ranking: {term.feature}")
            raw = v.values.get(term.feature)
            norm = normalize_value(fspec, raw, direction=term.direction, pool=pools[term.feature])
            if norm is None:
                missing.append(term.feature)
                continue
            weighted = norm * term.weight
            acc += weighted
            present_weight += term.weight
            contributions.append(Contribution(
                feature=term.feature, raw=raw, normalized=norm,
                weight=term.weight, weighted=weighted,
            ))
        composite = acc / present_weight if present_weight > 0 else 0.0
        coverage = present_weight / total_weight if total_weight > 0 else 0.0
        results.append(RankedCandidate(
            candidate_id=v.candidate_id, score=composite, coverage=coverage,
            contributions=tuple(contributions), missing=tuple(missing),
        ))
    results.sort(key=lambda r: (-r.score, r.candidate_id))
    return results
