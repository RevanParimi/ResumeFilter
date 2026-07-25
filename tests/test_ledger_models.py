"""S3.1 ORM rows: defaults, constraints, FK enforcement on SQLite."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import app.candidates.models  # noqa: F401 — candidates table is an FK target
from app.candidates.models import CandidateRow
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.models import (
    AuditLogRow,
    ConsentGrantRow,
    EvaluationEventRow,
    InterviewRecordRow,
    OrganizationRow,
    _utcnow,
)


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_tablenames():
    assert OrganizationRow.__tablename__ == "organizations"
    assert ConsentGrantRow.__tablename__ == "consent_grants"
    assert InterviewRecordRow.__tablename__ == "interview_records"
    assert EvaluationEventRow.__tablename__ == "evaluation_events"
    assert AuditLogRow.__tablename__ == "audit_log"


def test_org_defaults_and_unique_name(session_factory):
    with session_factory() as s:
        org = OrganizationRow(name="Acme Talent")
        s.add(org)
        s.commit()
        assert len(org.id) == 36 and org.status == "active"
        assert org.created_at is not None
        s.add(OrganizationRow(name="Acme Talent"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_grant_requires_existing_candidate(session_factory):
    with session_factory() as s:
        s.add(ConsentGrantRow(candidate_id="nope", purpose="ledger_write",
                              expires_at=_utcnow()))
        with pytest.raises(IntegrityError):
            s.commit()


def test_grant_org_id_nullable_and_revoked_default(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.flush()
        g = ConsentGrantRow(candidate_id=cand.id, purpose="ledger_write",
                            expires_at=_utcnow())
        s.add(g)
        s.commit()
        assert g.org_id is None and g.revoked_at is None
        assert g.granted_at is not None


def test_candidate_delete_cascades_ledger_rows(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        org = OrganizationRow(name="Beta Corp")
        s.add_all([cand, org])
        s.flush()
        g = ConsentGrantRow(candidate_id=cand.id, org_id=org.id,
                            purpose="ledger_write", expires_at=_utcnow())
        s.add(g)
        s.flush()
        rec = InterviewRecordRow(org_id=org.id, candidate_id=cand.id,
                                 consent_id=g.id, stage="tech",
                                 outcome="advanced", interviewed_at=_utcnow())
        s.add(rec)
        s.flush()
        s.add(EvaluationEventRow(record_id=rec.id, candidate_id=cand.id,
                                 event_type="score", payload={"value": 4}))
        s.add(AuditLogRow(actor_type="org", actor_id=org.id,
                          action="record.submit", entity_type="interview_record",
                          entity_id=rec.id, candidate_id=cand.id))
        s.commit()

        s.delete(cand)
        s.commit()
        for row_cls in (ConsentGrantRow, InterviewRecordRow, EvaluationEventRow):
            assert s.execute(select(row_cls)).scalars().all() == []
        assert s.execute(select(AuditLogRow)).scalars().all() == []
        # the org itself survives erasure
        assert s.execute(select(OrganizationRow)).scalars().all() != []


def test_audit_row_defaults(session_factory):
    with session_factory() as s:
        a = AuditLogRow(actor_type="system", action="org.create",
                        entity_type="organization", entity_id="o1")
        s.add(a)
        s.commit()
        assert a.actor_id is None and a.candidate_id is None
        assert a.details == {} and a.created_at is not None


def test_coding_round_row_defaults_and_cascade(session_factory):
    from app.ledger.models import CodingRoundResultRow
    with session_factory() as s:
        cand = CandidateRow()
        org = OrganizationRow(name="Coding Corp")
        s.add_all([cand, org])
        s.flush()
        g = ConsentGrantRow(candidate_id=cand.id, org_id=org.id,
                            purpose="ledger_write", expires_at=_utcnow())
        s.add(g)
        s.flush()
        row = CodingRoundResultRow(
            org_id=org.id, candidate_id=cand.id, consent_id=g.id,
            platform="hackerrank", score=740.0, taken_at=_utcnow(),
        )
        s.add(row)
        s.commit()
        assert len(row.id) == 36
        assert row.problem_tags == [] and row.raw == {}
        assert row.max_score is None and row.percentile is None
        assert row.created_at is not None

        s.delete(cand)   # DPDP erasure cascades the coding-round row
        s.commit()
        assert s.execute(select(CodingRoundResultRow)).scalars().all() == []
        # the org survives erasure
        assert s.execute(select(OrganizationRow)).scalars().all() != []
