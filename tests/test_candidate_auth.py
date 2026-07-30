import pytest

from app.candidates.models import CandidateRow
from tests.conftest import make_candidate_store


def _new_candidate(store) -> str:
    with store._session_factory() as s:
        row = CandidateRow(full_name="Asha")
        s.add(row)
        s.commit()
        return row.id


def test_issue_and_authenticate_roundtrip():
    store = make_candidate_store()
    cid = _new_candidate(store)
    key = store.issue_access_key(cid)
    assert isinstance(key, str) and key
    assert store.authenticate_candidate(key) == cid


def test_authenticate_rejects_bad_and_empty_keys():
    store = make_candidate_store()
    cid = _new_candidate(store)
    store.issue_access_key(cid)
    assert store.authenticate_candidate("nope") is None
    assert store.authenticate_candidate("") is None
    assert store.authenticate_candidate("   ") is None


def test_issue_rotates_and_old_key_dies():
    store = make_candidate_store()
    cid = _new_candidate(store)
    k1 = store.issue_access_key(cid)
    k2 = store.issue_access_key(cid)
    assert k1 != k2
    assert store.authenticate_candidate(k1) is None   # rotated out
    assert store.authenticate_candidate(k2) == cid
    # still exactly one credential row (unique candidate_id upsert, not append)
    from app.candidates.models import CandidateCredentialRow
    from sqlalchemy import select, func
    with store._session_factory() as s:
        n = s.execute(
            select(func.count()).select_from(CandidateCredentialRow)
            .where(CandidateCredentialRow.candidate_id == cid)
        ).scalar()
    assert n == 1


def test_issue_unknown_candidate_raises():
    store = make_candidate_store()
    with pytest.raises(LookupError):
        store.issue_access_key("does-not-exist")


def test_credential_cascades_on_candidate_delete():
    store = make_candidate_store()
    cid = _new_candidate(store)
    key = store.issue_access_key(cid)
    assert store.delete_candidate(cid) is True
    assert store.authenticate_candidate(key) is None  # credential gone with candidate
