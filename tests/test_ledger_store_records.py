"""S3.1 LedgerStore records/events: consent-gated writes + DPDP cascade proof."""

from datetime import datetime, timedelta, timezone

import pytest

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
from app.candidates.models import CandidateRow
from app.candidates.store import CandidateStore
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.store import ConsentError, LedgerStore

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture()
def store(session_factory):
    return LedgerStore(session_factory, default_consent_ttl_days=365)


@pytest.fixture()
def candidate_id(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.commit()
        return cand.id


@pytest.fixture()
def org(store):
    return store.create_organization("Acme Talent")


def test_submit_without_consent_is_refused(store, org, candidate_id):
    with pytest.raises(ConsentError):
        store.submit_interview_record(
            org_id=org.id, candidate_id=candidate_id, stage="tech",
            outcome="advanced", interviewed_at=NOW, now=NOW,
        )
    assert store.records_for_candidate(candidate_id) == []


def test_submit_with_consent_links_grant(store, org, candidate_id):
    g = store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            org_id=org.id, now=NOW)
    rec = store.submit_interview_record(
        org_id=org.id, candidate_id=candidate_id, stage="tech",
        outcome="advanced", interviewed_at=NOW, summary="solid round", now=NOW,
    )
    assert rec.consent_id == g.id
    assert rec.stage == "tech" and rec.outcome == "advanced"
    assert [r.id for r in store.records_for_candidate(candidate_id)] == [rec.id]


def test_submit_unknown_org_or_candidate(store, org, candidate_id):
    with pytest.raises(LookupError):
        store.submit_interview_record(org_id="nope", candidate_id=candidate_id,
                                      stage="tech", outcome="advanced",
                                      interviewed_at=NOW)
    with pytest.raises(LookupError):
        store.submit_interview_record(org_id=org.id, candidate_id="nope",
                                      stage="tech", outcome="advanced",
                                      interviewed_at=NOW)


def test_revocation_blocks_future_submissions(store, org, candidate_id):
    g = store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            org_id=org.id, now=NOW)
    store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                  stage="screen", outcome="advanced",
                                  interviewed_at=NOW, now=NOW)
    store.revoke_consent(g.id, now=NOW + timedelta(hours=1))
    with pytest.raises(ConsentError):
        store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                      stage="tech", outcome="advanced",
                                      interviewed_at=NOW,
                                      now=NOW + timedelta(hours=2))
    # the pre-revocation record legitimately remains (revocation ≠ erasure)
    assert len(store.records_for_candidate(candidate_id)) == 1


def test_events_append_and_read(store, org, candidate_id):
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        org_id=org.id, now=NOW)
    rec = store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                        stage="coding", outcome="advanced",
                                        interviewed_at=NOW, now=NOW)
    e1 = store.append_event(rec.id, event_type="score",
                            payload={"scale": 5, "value": 4})
    e2 = store.append_event(rec.id, event_type="note")
    assert e1.candidate_id == candidate_id and e1.payload == {"scale": 5, "value": 4}
    assert e2.payload == {}
    assert [e.id for e in store.events_for_record(rec.id)] == [e1.id, e2.id]
    with pytest.raises(LookupError):
        store.append_event("nope", event_type="score")


def test_record_and_event_writes_are_audited(store, org, candidate_id):
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        org_id=org.id, now=NOW)
    rec = store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                        stage="hm", outcome="offer",
                                        interviewed_at=NOW, now=NOW)
    store.append_event(rec.id, event_type="note")
    entries = store.audit_for_candidate(candidate_id)
    actions = [a.action for a in entries]
    assert actions == ["consent.grant", "record.submit", "event.append"]
    submit = entries[1]
    assert submit.actor_type == "org" and submit.actor_id == org.id
    assert submit.details["stage"] == "hm" and submit.details["outcome"] == "offer"


def test_dpdp_erasure_sweeps_ledger(store, session_factory, org, candidate_id):
    """The REAL erasure path: CandidateStore.delete_candidate cascades ledger rows."""
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        org_id=org.id, now=NOW)
    rec = store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                        stage="tech", outcome="hired",
                                        interviewed_at=NOW, now=NOW)
    store.append_event(rec.id, event_type="score", payload={"value": 5})
    assert CandidateStore(session_factory).delete_candidate(candidate_id) is True

    assert store.records_for_candidate(candidate_id) == []
    assert store.events_for_record(rec.id) == []
    assert store.audit_for_candidate(candidate_id) == []
    # after deletion, consent_status raises LookupError for unknown candidate
    with pytest.raises(LookupError):
        store.consent_status(candidate_id, org_id=org.id,
                             purpose="ledger_write", at=NOW)
    # the org itself survives erasure
    assert store.get_organization(org.id) is not None
