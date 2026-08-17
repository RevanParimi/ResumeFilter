"""Comp blend engine (S5.2) -- pure, no I/O, no clock (caller passes `now`).

Mirrors app/ledger/reputation.py: a static prior shrunk by observed evidence.
Everything blends on a TOTAL-CTC basis (observed offers already carry total;
the static cell's FIXED figures are grossed up by the variable fraction first).
Advisory only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from app.core.config import Settings, get_settings
from app.comp.schema import CompBandEstimate, CompBenchmark, RoleSignal
from app.matching.schema import CompBand


def _recency_weight(at: datetime, now: datetime, halflife_days: float) -> float:
    age_days = max(0.0, (now - at).total_seconds() / 86400.0)  # future-dated -> 0 age
    return 0.5 ** (age_days / halflife_days)


def estimate_comp(
    signal: RoleSignal,
    cell: tuple[float, float, float, float],
    points: Sequence,
    *,
    now: datetime,
    settings: Optional[Settings] = None,
) -> CompBandEstimate:
    s = settings or get_settings()
    f_low, f_mid, f_high, var = cell
    gross = 1.0 + var
    t_low, t_mid, t_high = f_low * gross, f_mid * gross, f_high * gross

    n = len(points)
    include = n >= s.comp_min_observations
    if include:
        weights = [_recency_weight(p.offered_at, now, s.comp_recency_halflife_days) for p in points]
        W = sum(weights)
        mu = (sum(w * p.total_ctc for w, p in zip(weights, points)) / W) if W > 0 else t_mid
        k0 = s.comp_prior_strength
        p50 = (k0 * t_mid + W * mu) / (k0 + W)
        confidence = min(
            s.comp_confidence_cap,
            s.comp_confidence_floor + (1.0 - s.comp_confidence_floor) * (W / (W + s.comp_confidence_k)),
        )
        sources = ("static", "observed")
        n_obs = n
        reasoning = (
            f"Blended {n} consented observed offer(s) (recency-weighted mass "
            f"{W:.2f}, mean {mu:,.0f}) with the static prior ({t_mid:,.0f}) for "
            f"{signal.role_family}/{signal.seniority.value}/{signal.city_tier}: "
            f"p50 {p50:,.0f}. Advisory only."
        )
    else:
        p50 = t_mid
        confidence = s.comp_confidence_floor
        sources = ("static",)
        n_obs = 0
        reasoning = (
            f"Static prior only for {signal.role_family}/{signal.seniority.value}/"
            f"{signal.city_tier} ({n} observed offer(s) < k={s.comp_min_observations}); "
            f"p50 {p50:,.0f}. Advisory only."
        )

    p25 = p50 * (t_low / t_mid) if t_mid else p50
    p75 = p50 * (t_high / t_mid) if t_mid else p50
    return CompBandEstimate(
        currency=s.comp_currency_default,
        p25=round(p25, 2), p50=round(p50, 2), p75=round(p75, 2),
        confidence=round(confidence, 2),
        role_family=signal.role_family, seniority=signal.seniority, city_tier=signal.city_tier,
        n_observed=n_obs, sources=sources, reasoning=reasoning,
    )


def _req_mid(comp_band: Optional[CompBand]) -> Optional[float]:
    if comp_band is None:
        return None
    lo, hi = comp_band.ctc_min, comp_band.ctc_max
    if lo is not None and hi is not None:
        return (lo + hi) / 2.0
    return lo if lo is not None else hi


def benchmark_comp(
    estimate: CompBandEstimate,
    comp_band: Optional[CompBand],
    *,
    settings: Optional[Settings] = None,
) -> CompBenchmark:
    s = settings or get_settings()
    mid = _req_mid(comp_band)
    if mid is None:
        return CompBenchmark(
            estimate=estimate, requisition_band=comp_band, position=None, delta_pct=None,
            reasoning="Requisition has no comp_band to benchmark; market estimate only. Advisory.",
        )
    delta = (mid - estimate.p50) / estimate.p50 if estimate.p50 > 0 else 0.0
    if abs(delta) <= s.comp_benchmark_tolerance:
        position = "at"
    elif delta < 0:
        position = "below"
    else:
        position = "above"
    return CompBenchmark(
        estimate=estimate, requisition_band=comp_band, position=position,
        delta_pct=round(delta, 4),
        reasoning=(
            f"Requisition midpoint {mid:,.0f} is {position} the market p50 "
            f"{estimate.p50:,.0f} ({delta:+.1%}). Advisory only."
        ),
    )
