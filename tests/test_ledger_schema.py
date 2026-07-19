"""S3.1 contracts: ledger taxonomies + Pydantic models."""

from datetime import datetime, timedelta, timezone

from app.ledger.schema import (
    AuditEntry,
    ConsentDecision,
    ConsentGrant,
    ConsentPurpose,
    EvaluationEvent,
    InterviewOutcome,
    InterviewRecord,
    InterviewStage,
    Organization,
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
