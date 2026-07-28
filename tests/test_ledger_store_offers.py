"""S5.2 LedgerStore observed offers: consent-gated write + de-identified aggregate."""

from datetime import datetime, timedelta, timezone

import pytest

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
from app.candidates.models import CandidateRow
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.models import AuditLogRow, ObservedOfferRow
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError, LedgerStore

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture()
def store(session_factory):
    return LedgerStore(session_factory, default_consent_ttl_days=365)


def _new_candidate(session_factory) -> str:
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.commit()
        return cand.id


def _grant_write(store, cand_id, org_id, *, now=NOW, days=90):
    return store.grant_consent(
        candidate_id=cand_id, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org_id,
        expires_at=now + timedelta(days=days), now=now,
    )


def _submit(store, org_id, cand_id, *, role="backend_engineer", seniority="senior",
            tier="metro", fixed=2_500_000.0, variable=300_000.0, offered_at=NOW):
    return store.submit_observed_offer(
        org_id=org_id, candidate_id=cand_id, role_family=role, seniority=seniority,
        city_tier=tier, ctc_fixed=fixed, ctc_variable=variable, offered_at=offered_at, now=NOW,
    )


def test_submit_requires_write_consent(store, session_factory):
    org = store.create_organization("Acme")
    cand = _new_candidate(session_factory)
    with pytest.raises(ConsentError):
        _submit(store, org.id, cand)


def test_submit_stamps_consent_and_audits(store, session_factory):
    org = store.create_organization("Acme")
    cand = _new_candidate(session_factory)
    grant = _grant_write(store, cand, org.id)
    offer = _submit(store, org.id, cand)
    assert offer.consent_id == grant.id
    assert offer.ctc_fixed == 2_500_000.0
    actions = [a.action for a in store.audit_for_candidate(cand)]
    assert "offer.submit" in actions


def test_submit_unknown_candidate_raises_lookup(store):
    org = store.create_organization("Acme")
    with pytest.raises(LookupError):
        store.submit_observed_offer(
            org_id=org.id, candidate_id="nope", role_family="backend_engineer",
            seniority="mid", city_tier="metro", ctc_fixed=1.0, offered_at=NOW, now=NOW,
        )


def test_offer_cascades_on_candidate_erasure(store, session_factory):
    org = store.create_organization("Acme")
    cand = _new_candidate(session_factory)
    _grant_write(store, cand, org.id)
    _submit(store, org.id, cand)
    with session_factory() as s:  # DPDP erasure via candidate delete
        s.delete(s.get(CandidateRow, cand))
        s.commit()
        assert s.query(ObservedOfferRow).count() == 0
