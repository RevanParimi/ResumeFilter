"""S5.2 comp blend engine — static prior shrinkage + benchmark positioning."""

from collections import namedtuple
from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.comp.estimate import estimate_comp, benchmark_comp
from app.comp.schema import RoleSignal, SeniorityBand
from app.matching.schema import CompBand

Point = namedtuple("Point", ["total_ctc", "offered_at"])
NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)
SIG = RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.MID, city_tier="metro")
CELL = (1_584_000.0, 1_800_000.0, 2_016_000.0, 0.12)  # mid=18L fixed, var 12%


def _s() -> Settings:
    return Settings()


def test_static_only_when_below_k():
    s = _s()
    pts = [Point(3_000_000.0, NOW)] * 3  # 3 < comp_min_observations (5)
    est = estimate_comp(SIG, CELL, pts, now=NOW, settings=s)
    assert est.sources == ("static",)
    assert est.n_observed == 0
    assert est.confidence == s.comp_confidence_floor
    # p50 == static total mid = 18L * 1.12
    assert round(est.p50) == round(1_800_000.0 * 1.12)
    assert est.p25 < est.p50 < est.p75


def test_observed_blend_shifts_toward_observed_and_raises_confidence():
    s = _s()
    static_total_mid = 1_800_000.0 * 1.12
    pts = [Point(3_000_000.0, NOW)] * 6  # 6 >= k, all well above static
    est = estimate_comp(SIG, CELL, pts, now=NOW, settings=s)
    assert est.sources == ("static", "observed")
    assert est.n_observed == 6
    assert est.p50 > static_total_mid           # pulled up toward 30L
    assert est.p50 < 3_000_000.0                # but shrunk by the prior
    assert est.confidence > s.comp_confidence_floor
    assert est.p25 < est.p50 < est.p75


def test_recency_downweights_old_offers():
    s = _s()
    old = NOW - timedelta(days=5 * 365)  # ~5 half-lives -> tiny weight
    recent = [Point(3_000_000.0, NOW)] * 5
    with_old = recent + [Point(500_000.0, old)]  # one stale low offer
    est_recent = estimate_comp(SIG, CELL, recent, now=NOW, settings=s)
    est_mixed = estimate_comp(SIG, CELL, with_old, now=NOW, settings=s)
    # the stale low offer barely moves p50
    assert abs(est_mixed.p50 - est_recent.p50) < 0.02 * est_recent.p50


def test_benchmark_positions():
    s = _s()
    est = estimate_comp(SIG, CELL, [], now=NOW, settings=s)  # static-only
    p50 = est.p50
    at = benchmark_comp(est, CompBand(ctc_min=p50 * 0.97, ctc_max=p50 * 1.03), settings=s)
    below = benchmark_comp(est, CompBand(ctc_min=p50 * 0.5, ctc_max=p50 * 0.6), settings=s)
    above = benchmark_comp(est, CompBand(ctc_min=p50 * 1.4, ctc_max=p50 * 1.5), settings=s)
    none = benchmark_comp(est, None, settings=s)
    assert at.position == "at"
    assert below.position == "below" and below.delta_pct < 0
    assert above.position == "above" and above.delta_pct > 0
    assert none.position is None and none.requisition_band is None
