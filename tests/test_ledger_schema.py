"""S3.1 contracts: ledger taxonomies + Pydantic models."""

from datetime import datetime, timedelta, timezone

from app.ledger.schema import (
    AuditEntry,
    CodingPlatform,
    CodingRoundResult,
    ConsentDecision,
    ConsentGrant,
    ConsentPurpose,
    EvaluationEvent,
    InterviewOutcome,
    InterviewRecord,
    InterviewStage,
    Organization,
    ReputationAssessment,
    ReputationBand,
    ReputationComponent,
)

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def test_stage_taxonomy():
    assert [s.value for s in InterviewStage] == ["screen", "tech", "coding", "hm"]


def test_outcome_taxonomy():
    assert [o.value for o in InterviewOutcome] == [
        "advanced", "rejected", "offer", "hired", "withdrawn", "no_show",
    ]


def test_consent_purposes():
    assert ConsentPurpose.LEDGER_WRITE == "ledger_write"
    assert ConsentPurpose.LEDGER_READ == "ledger_read"


def test_grant_defaults_and_scope():
    g = ConsentGrant(
        id="g1", candidate_id="c1", purpose="ledger_write",
        granted_at=NOW, expires_at=NOW + timedelta(days=365),
    )
    assert g.org_id is None          # None = any member org
    assert g.revoked_at is None
    assert g.purpose is ConsentPurpose.LEDGER_WRITE  # str coerces to enum


def test_decision_shape():
    d = ConsentDecision(allowed=False, reason="no active consent")
    assert d.grant_id is None
    ok = ConsentDecision(allowed=True, reason="active grant", grant_id="g1")
    assert ok.allowed and ok.grant_id == "g1"


def test_record_coerces_taxonomies():
    r = InterviewRecord(
        id="r1", org_id="o1", candidate_id="c1", consent_id="g1",
        stage="tech", outcome="advanced", interviewed_at=NOW, created_at=NOW,
    )
    assert r.stage is InterviewStage.TECH
    assert r.outcome is InterviewOutcome.ADVANCED
    assert r.summary is None


def test_event_and_audit_defaults():
    e = EvaluationEvent(id="e1", record_id="r1", candidate_id="c1",
                        event_type="score", created_at=NOW)
    assert e.payload == {}
    a = AuditEntry(id="a1", actor_type="org", action="record.submit",
                   entity_type="interview_record", entity_id="r1", created_at=NOW)
    assert a.actor_id is None and a.candidate_id is None and a.details == {}


def test_record_round_trips_json():
    r = InterviewRecord(
        id="r1", org_id="o1", candidate_id="c1", consent_id="g1",
        stage="coding", outcome="offer", interviewed_at=NOW,
        summary="strong systems round", created_at=NOW,
    )
    assert InterviewRecord.model_validate_json(r.model_dump_json()) == r


# ── S3.3 coding-round contracts ──────────────────────────────────────────────


def test_coding_platform_taxonomy():
    assert [p.value for p in CodingPlatform] == [
        "hackerrank", "codility", "leetcode", "codesignal",
        "hackerearth", "internal", "other",
    ]


def test_coding_round_result_defaults_and_coercion():
    r = CodingRoundResult(
        id="cr1", org_id="o1", candidate_id="c1", consent_id="g1",
        platform="hackerrank", score=740.0, taken_at=NOW, created_at=NOW,
    )
    assert r.platform is CodingPlatform.HACKERRANK  # str coerces to enum
    assert r.platform_name is None and r.assessment_name is None
    assert r.max_score is None and r.percentile is None
    assert r.problem_tags == [] and r.raw == {}


def test_coding_round_result_rejects_out_of_range():
    import pytest
    from pydantic import ValidationError
    common = dict(id="cr1", org_id="o1", candidate_id="c1", consent_id="g1",
                  platform="other", taken_at=NOW, created_at=NOW)
    with pytest.raises(ValidationError):  # percentile above 100
        CodingRoundResult(score=10.0, percentile=101, **common)
    with pytest.raises(ValidationError):  # negative score
        CodingRoundResult(score=-1.0, **common)
    with pytest.raises(ValidationError):  # negative max_score
        CodingRoundResult(score=10.0, max_score=-5.0, **common)


def test_coding_round_result_round_trips_json():
    r = CodingRoundResult(
        id="cr1", org_id="o1", candidate_id="c1", consent_id="g1",
        platform="codility", platform_name=None, assessment_name="Backend Screen",
        score=88.0, max_score=100.0, percentile=92.5,
        problem_tags=["arrays", "dynamic-programming"],
        taken_at=NOW, raw={"attempts": 1}, created_at=NOW,
    )
    assert CodingRoundResult.model_validate_json(r.model_dump_json()) == r


def test_reputation_band_taxonomy():
    assert [b.value for b in ReputationBand] == [
        "insufficient_data", "guarded", "mixed", "favorable", "strong",
    ]


def test_reputation_assessment_defaults_are_neutral_and_advisory():
    a = ReputationAssessment()
    assert a.score == 0.5  # neutral prior
    assert a.band is ReputationBand.INSUFFICIENT_DATA
    assert a.advisory is True
    assert a.components == [] and a.distinct_orgs == 0


def test_reputation_component_bounds():
    import pytest
    from pydantic import ValidationError
    ReputationComponent(id="interview_records", observations=3,
                        effective_weight=2.5, mean_value=0.8)
    with pytest.raises(ValidationError):
        ReputationComponent(id="x", mean_value=1.5)   # > 1
    with pytest.raises(ValidationError):
        ReputationComponent(id="x", effective_weight=-0.1)


def test_organization_reliability_weight_defaults_to_one():
    o = Organization(id="o1", name="Acme", created_at=NOW)
    assert o.reliability_weight == 1.0
