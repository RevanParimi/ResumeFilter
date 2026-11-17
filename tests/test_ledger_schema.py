"""S3.1 contracts: ledger taxonomies + Pydantic models."""

from datetime import datetime, timedelta, timezone

from app.ledger.schema import (
    AuditEntry,
    ConsentDecision,
    ConsentGrant,
    ConsentPurpose,
    Organization,
)

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


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


def test_audit_defaults():
    a = AuditEntry(id="a1", actor_type="org", action="record.submit",
                   entity_type="interview_record", entity_id="r1", created_at=NOW)
    assert a.actor_id is None and a.candidate_id is None and a.details == {}


def test_organization_reliability_weight_defaults_to_one():
    o = Organization(id="o1", name="Acme", created_at=NOW)
    assert o.reliability_weight == 1.0
