"""S3.3 LedgerStore coding rounds: consent-gated writes/reads + DPDP cascade."""

from datetime import datetime, timezone

import pytest

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
from app.candidates.models import CandidateRow
from app.candidates.store import CandidateStore
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.store import ConsentError, LedgerStore

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


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
    return store.create_organization("Coding Corp")


def test_submit_without_consent_is_refused(store, org, candidate_id):
    with pytest.raises(ConsentError):
        store.submit_coding_round(
            org_id=org.id, candidate_id=candidate_id, platform="hackerrank",
            score=740.0, taken_at=NOW, now=NOW,
        )
    assert store.coding_rounds_for_candidate(candidate_id) == []


def test_submit_with_consent_links_grant_and_persists_fields(store, org, candidate_id):
    g = store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            org_id=org.id, now=NOW)
    cr = store.submit_coding_round(
        org_id=org.id, candidate_id=candidate_id, platform="codility",
        score=88.0, max_score=100.0, percentile=92.5, taken_at=NOW,
        assessment_name="Backend Screen", problem_tags=["arrays", "graphs"],
        raw={"attempts": 1}, now=NOW,
    )
    assert cr.consent_id == g.id
    assert cr.platform == "codility" and cr.score == 88.0 and cr.max_score == 100.0
    assert cr.percentile == 92.5 and cr.problem_tags == ["arrays", "graphs"]
    assert cr.raw == {"attempts": 1}
    assert [r.id for r in store.coding_rounds_for_candidate(candidate_id)] == [cr.id]


def test_submit_unknown_org_or_candidate(store, org, candidate_id):
    with pytest.raises(LookupError):
        store.submit_coding_round(org_id="nope", candidate_id=candidate_id,
                                  platform="leetcode", score=1.0, taken_at=NOW)
    with pytest.raises(LookupError):
        store.submit_coding_round(org_id=org.id, candidate_id="nope",
                                  platform="leetcode", score=1.0, taken_at=NOW)


def test_submit_is_audited(store, org, candidate_id):
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        org_id=org.id, now=NOW)
    store.submit_coding_round(org_id=org.id, candidate_id=candidate_id,
                              platform="hackerrank", score=740.0, taken_at=NOW, now=NOW)
    entries = store.audit_for_candidate(candidate_id)
    actions = [a.action for a in entries]
    assert actions == ["consent.grant", "coding_round.submit"]
    submit = entries[1]
    assert submit.actor_type == "org" and submit.actor_id == org.id
    assert submit.entity_type == "coding_round_result"
    assert submit.details["platform"] == "hackerrank"


def test_query_allowed_returns_results_and_audits_read(store, candidate_id):
    org = store.create_organization("ReaderCo")
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write", org_id=org.id)
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_read", org_id=org.id)
    cr = store.submit_coding_round(org_id=org.id, candidate_id=candidate_id,
                                   platform="hackerrank", score=740.0, taken_at=NOW)
    got = store.query_coding_rounds_for_org(org_id=org.id, candidate_id=candidate_id)
    assert [r.id for r in got] == [cr.id]
    reads = [a for a in store.audit_for_candidate(candidate_id)
             if a.action == "coding_round.query"]
    assert len(reads) == 1
    assert reads[0].details["allowed"] is True and reads[0].details["result_count"] == 1


def test_query_without_read_consent_denied_and_audited(store, candidate_id):
    org = store.create_organization("NosyCo")
    with pytest.raises(ConsentError):
        store.query_coding_rounds_for_org(org_id=org.id, candidate_id=candidate_id)
    reads = [a for a in store.audit_for_candidate(candidate_id)
             if a.action == "coding_round.query"]
    assert len(reads) == 1 and reads[0].details["allowed"] is False


def test_query_unknown_candidate_or_org_raises_and_writes_no_audit(store, candidate_id):
    org = store.create_organization("EdgeCo")
    with pytest.raises(LookupError):
        store.query_coding_rounds_for_org(org_id=org.id, candidate_id="no-such")
    with pytest.raises(LookupError):
        store.query_coding_rounds_for_org(org_id="no-such", candidate_id=candidate_id)
    assert [a for a in store.audit_for_candidate(candidate_id)
            if a.action == "coding_round.query"] == []


def test_dpdp_erasure_sweeps_coding_rounds(store, session_factory, org, candidate_id):
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        org_id=org.id, now=NOW)
    store.submit_coding_round(org_id=org.id, candidate_id=candidate_id,
                              platform="hackerrank", score=740.0, taken_at=NOW, now=NOW)
    assert CandidateStore(session_factory).delete_candidate(candidate_id) is True
    assert store.coding_rounds_for_candidate(candidate_id) == []
    assert store.get_organization(org.id) is not None  # org survives
