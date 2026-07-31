from app.candidates.models import CandidateRow
from app.ledger.schema import ConsentPurpose
from app.ledger.store import LedgerStore
from tests.conftest import make_candidate_store


def _store():
    cs = make_candidate_store()
    return cs, LedgerStore(cs._session_factory, default_consent_ttl_days=365)


def _candidate(cs) -> str:
    with cs._session_factory() as s:
        row = CandidateRow(full_name="Ravi")
        s.add(row)
        s.commit()
        return row.id


def test_consents_for_candidate_lists_all_states_ordered():
    cs, ledger = _store()
    cid = _candidate(cs)
    g1 = ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ)
    g2 = ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE)
    ledger.revoke_consent(g2.id)
    grants = ledger.consents_for_candidate(cid)
    assert [g.id for g in grants] == [g1.id, g2.id]        # granted_at order
    assert grants[0].revoked_at is None
    assert grants[1].revoked_at is not None                # revoked state preserved


def test_consents_for_candidate_empty():
    cs, ledger = _store()
    cid = _candidate(cs)
    assert ledger.consents_for_candidate(cid) == []


def test_get_grant_hit_and_miss():
    cs, ledger = _store()
    cid = _candidate(cs)
    g = ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ)
    assert ledger.get_grant(g.id).id == g.id
    assert ledger.get_grant("missing") is None
