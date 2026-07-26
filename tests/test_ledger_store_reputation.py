"""S3.4 LedgerStore reputation: consent-gated read + audit, inclusion, reliability."""

from datetime import datetime, timezone

import pytest

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
from app.candidates.models import CandidateRow
from app.core.config import Settings
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.schema import ReputationBand
from app.ledger.store import ConsentError, LedgerStore

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _settings() -> Settings:
    import os
    os.environ.setdefault("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture()
def store(session_factory):
    return LedgerStore(session_factory, default_consent_ttl_days=365, settings=_settings())


@pytest.fixture()
def candidate_id(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.commit()
        return cand.id


def _org(store, name):
    return store.create_organization(name)


def _write_grant(store, cid, org):
    return store.grant_consent(candidate_id=cid, purpose="ledger_write",
                               org_id=org.id, now=NOW)


def _read_grant(store, cid, org):
    return store.grant_consent(candidate_id=cid, purpose="ledger_read",
                               org_id=org.id, now=NOW)


def test_reputation_without_read_consent_is_refused_and_audited(store, candidate_id):
    org = _org(store, "Reader Co")
    with pytest.raises(ConsentError):
        store.reputation_for_org(org_id=org.id, candidate_id=candidate_id, at=NOW)
    actions = [a.action for a in store.audit_for_candidate(candidate_id)]
    assert "reputation.query" in actions  # denied attempt is observable
    denied = [a for a in store.audit_for_candidate(candidate_id)
              if a.action == "reputation.query"][-1]
    assert denied.details.get("allowed") is False


def test_reputation_with_read_consent_aggregates_two_orgs(store, candidate_id):
    a = _org(store, "Org A")
    b = _org(store, "Org B")
    reader = _org(store, "Reader")
    for org in (a, b):
        _write_grant(store, candidate_id, org)
        for _ in range(3):
            store.submit_interview_record(
                org_id=org.id, candidate_id=candidate_id, stage="hm",
                outcome="hired", interviewed_at=NOW, now=NOW,
            )
    _read_grant(store, candidate_id, reader)
    rep = store.reputation_for_org(org_id=reader.id, candidate_id=candidate_id, at=NOW)
    assert rep.distinct_orgs == 2
    assert rep.band is ReputationBand.STRONG
    assert rep.score > 0.5 and rep.advisory is True
    allowed = [x for x in store.audit_for_candidate(candidate_id)
               if x.action == "reputation.query"][-1]
    assert allowed.details.get("allowed") is True
    assert allowed.details.get("band") == "strong"


def test_reputation_excludes_withdrawn_and_bare_coding(store, candidate_id):
    org = _org(store, "Org A")
    reader = _org(store, "Reader")
    _write_grant(store, candidate_id, org)
    store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                  stage="tech", outcome="withdrawn",
                                  interviewed_at=NOW, now=NOW)
    store.submit_coding_round(org_id=org.id, candidate_id=candidate_id,
                              platform="internal", score=500.0, taken_at=NOW, now=NOW)
    _read_grant(store, candidate_id, reader)
    rep = store.reputation_for_org(org_id=reader.id, candidate_id=candidate_id, at=NOW)
    assert rep.total_observations == 0
    assert rep.excluded_observations == 2
    assert rep.band is ReputationBand.INSUFFICIENT_DATA


def test_reputation_honors_reliability_weight(store, candidate_id):
    org = _org(store, "Org A")
    reader = _org(store, "Reader")
    _write_grant(store, candidate_id, org)
    for _ in range(4):
        store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                      stage="hm", outcome="hired",
                                      interviewed_at=NOW, now=NOW)
    _read_grant(store, candidate_id, reader)
    base = store.reputation_for_org(org_id=reader.id, candidate_id=candidate_id, at=NOW)
    store.set_org_reliability(org.id, 0.25)  # down-weight org A's evidence
    down = store.reputation_for_org(org_id=reader.id, candidate_id=candidate_id, at=NOW)
    assert down.evidence_mass < base.evidence_mass
    assert down.score < base.score  # less pull away from the 0.5 prior


def test_reputation_unknown_org_or_candidate(store, candidate_id):
    org = _org(store, "Org A")
    with pytest.raises(LookupError):
        store.reputation_for_org(org_id="nope", candidate_id=candidate_id, at=NOW)
    with pytest.raises(LookupError):
        store.reputation_for_org(org_id=org.id, candidate_id="nope", at=NOW)


def test_set_org_reliability_validates_and_audits(store):
    org = _org(store, "Org A")
    updated = store.set_org_reliability(org.id, 1.5)
    assert updated.reliability_weight == 1.5
    assert store.get_organization(org.id).reliability_weight == 1.5
    with pytest.raises(ValueError):
        store.set_org_reliability(org.id, -0.1)
    with pytest.raises(LookupError):
        store.set_org_reliability("nope", 1.0)
