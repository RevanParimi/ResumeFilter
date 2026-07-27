"""Pure, deterministic talent-ranking engine (PI-4 / S4.3).

No I/O, no store, no wall clock (the app/fabrication/risk.py pattern). Operates
over already-materialized FeatureVector values + the FeatureSpecs the caller
resolves from the registry. Advisory: filters narrow, scoring orders; a
missing/consent-withheld value is dropped and never penalizes a candidate.
"""

from __future__ import annotations

from typing import Optional

from app.features.ranking_schema import SortDirection
from app.features.schema import FeatureDType, FeatureSpec, FeatureValue

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
