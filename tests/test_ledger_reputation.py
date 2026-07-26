"""S3.4 pure reputation aggregation: math, gates, determinism. Fully offline."""

from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.ledger.reputation import assess_reputation
from app.ledger.schema import (
    CodingRoundResult, InterviewRecord, ReputationBand,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _settings() -> Settings:
    # Hermetic: code defaults, independent of config.yaml/.env.
    import os
    os.environ.setdefault("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


def _rec(outcome, org="orgA", at=NOW, stage="tech"):
    return InterviewRecord(
        id=f"r-{outcome}-{org}-{at.isoformat()}", org_id=org, candidate_id="c1",
        consent_id="g1", stage=stage, outcome=outcome, interviewed_at=at,
        created_at=at,
    )


def _coding(org="orgA", at=NOW, score=88.0, max_score=None, percentile=None):
    return CodingRoundResult(
        id=f"cr-{org}-{at.isoformat()}-{score}", org_id=org, candidate_id="c1",
        consent_id="g1", platform="hackerrank", score=score, max_score=max_score,
        percentile=percentile, taken_at=at, created_at=at,
    )


def test_no_evidence_returns_neutral_prior_insufficient():
    a = assess_reputation([], [], now=NOW, settings=_settings())
    assert a.score == 0.5
    assert a.band is ReputationBand.INSUFFICIENT_DATA
    assert a.total_observations == 0 and a.distinct_orgs == 0
    assert a.advisory is True


def test_withdrawn_is_excluded_from_evidence():
    a = assess_reputation([_rec("withdrawn")], [], now=NOW, settings=_settings())
    assert a.total_observations == 0
    assert a.excluded_observations == 1
    assert a.score == 0.5  # nothing moved the prior


def test_coding_normalization_percentile_then_maxscore_then_excluded():
    s = _settings()
    # percentile wins
    a = assess_reputation([], [_coding(percentile=90.0, score=1.0, max_score=2.0)],
                          now=NOW, settings=s)
    assert a.components[0].mean_value == 0.9
    # max_score path
    b = assess_reputation([], [_coding(score=740.0, max_score=1000.0)], now=NOW, settings=s)
    assert round(b.components[0].mean_value, 4) == 0.74
    # bare score excluded
    c = assess_reputation([], [_coding(score=740.0)], now=NOW, settings=s)
    assert c.total_observations == 0 and c.excluded_observations == 1


def test_recency_halves_weight_at_halflife():
    s = _settings()  # halflife 365 days
    old = NOW - timedelta(days=365)
    a = assess_reputation([_rec("hired", at=old)], [], now=NOW, settings=s)
    # one hired (value 1.0), weight 0.5: score = (2 + 0.5*1)/(4 + 0.5) = 2.5/4.5
    assert round(a.score, 4) == round(2.5 / 4.5, 4)
    assert round(a.evidence_mass, 4) == 0.5


def test_reliability_weight_scales_a_contribution():
    s = _settings()
    a = assess_reputation([_rec("hired")], [], now=NOW,
                          reliability_by_org={"orgA": 2.0}, settings=s)
    # weight 2.0: score = (2 + 2*1)/(4 + 2) = 4/6
    assert round(a.score, 4) == round(4 / 6, 4)


def test_single_source_high_caps_at_favorable_not_strong():
    s = _settings()
    recs = [_rec("hired", org="orgA") for _ in range(6)]
    a = assess_reputation(recs, [], now=NOW, settings=s)
    assert a.distinct_orgs == 1
    assert a.score >= s.rep_strong_threshold          # score qualifies for STRONG
    assert a.band is ReputationBand.FAVORABLE          # but single-source caps it


def test_two_orgs_high_unlocks_strong():
    s = _settings()
    recs = [_rec("hired", org="orgA") for _ in range(3)] + \
           [_rec("hired", org="orgB") for _ in range(3)]
    a = assess_reputation(recs, [], now=NOW, settings=s)
    assert a.distinct_orgs == 2
    assert a.band is ReputationBand.STRONG


def test_single_source_low_caps_at_mixed_not_guarded():
    s = _settings()
    recs = [_rec("rejected", org="orgA") for _ in range(6)]
    a = assess_reputation(recs, [], now=NOW, settings=s)
    assert a.score <= s.rep_guarded_threshold
    assert a.distinct_orgs == 1
    assert a.band is ReputationBand.MIXED              # one org can't brand


def test_two_orgs_low_unlocks_guarded():
    s = _settings()
    recs = [_rec("rejected", org="orgA") for _ in range(3)] + \
           [_rec("rejected", org="orgB") for _ in range(3)]
    a = assess_reputation(recs, [], now=NOW, settings=s)
    assert a.distinct_orgs == 2
    assert a.band is ReputationBand.GUARDED
    assert a.advisory is True


def test_thin_evidence_stays_insufficient():
    s = _settings()
    a = assess_reputation([_rec("hired")], [], now=NOW, settings=s)  # mass 1
    assert a.confidence < s.rep_min_confidence
    assert a.band is ReputationBand.INSUFFICIENT_DATA


def test_components_split_by_evidence_type():
    s = _settings()
    a = assess_reputation([_rec("hired", org="orgA"), _rec("advanced", org="orgB")],
                          [_coding(org="orgA", percentile=80.0)], now=NOW, settings=s)
    ids = {c.id for c in a.components}
    assert ids == {"interview_records", "coding_rounds"}
    assert a.total_observations == 3 and a.distinct_orgs == 2


def test_deterministic():
    s = _settings()
    recs = [_rec("hired", org="orgA"), _rec("rejected", org="orgB")]
    a = assess_reputation(recs, [], now=NOW, settings=s)
    b = assess_reputation(recs, [], now=NOW, settings=s)
    assert a.model_dump() == b.model_dump()
