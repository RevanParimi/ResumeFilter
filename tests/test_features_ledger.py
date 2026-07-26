from datetime import datetime, timezone
from app.features.schema import FeatureContext
import app.features.definitions.ledger as led
from app.ledger.schema import (
    CodingPlatform, CodingRoundResult, InterviewOutcome, InterviewRecord, InterviewStage,
)

AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _rec(org):
    return InterviewRecord(
        org_id=org, candidate_id="c1", consent_id="g1",
        stage=InterviewStage.HM, outcome=InterviewOutcome.HIRED,
        interviewed_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
    )


def _coding(org, pct):
    return CodingRoundResult(
        org_id=org, candidate_id="c1", consent_id="g1",
        platform=CodingPlatform.HACKERRANK, score=90.0, max_score=100.0, percentile=pct,
        taken_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
    )


def _ctx(records=(), coding=()):
    return FeatureContext(candidate_id="c1", as_of=AS_OF,
                          interview_records=tuple(records), coding_rounds=tuple(coding))


def test_counts_and_distinct_orgs():
    ctx = _ctx([_rec("A"), _rec("B")], [_coding("A", 92.0)])
    assert led.interview_record_count(ctx) == 2
    assert led.coding_round_count(ctx) == 1
    assert led.distinct_orgs(ctx) == 2
    assert led.best_coding_percentile(ctx) == 92.0


def test_empty_ledger_defaults():
    ctx = _ctx()
    assert led.interview_record_count(ctx) == 0
    assert led.distinct_orgs(ctx) == 0
    assert led.best_coding_percentile(ctx) is None
    assert led.reputation_band(ctx) == "insufficient_data"
    assert 0.0 <= led.reputation_score(ctx) <= 1.0


def test_reputation_features_use_context_assessment():
    ctx = _ctx([_rec("A"), _rec("B")], [_coding("A", 92.0), _coding("B", 88.0)])
    assert led.reputation_band(ctx) in {"favorable", "strong", "mixed"}
    assert led.reputation_score(ctx) > 0.5


def test_all_ledger_features_require_consent():
    from app.features.registry import _DEFAULT_REGISTRY
    import app.features.definitions.ledger  # noqa: F401 ensure registered
    for (name, _), rf in _DEFAULT_REGISTRY._by_key.items():
        if rf.spec.source.value in ("ledger", "reputation"):
            assert rf.spec.requires_consent is True
