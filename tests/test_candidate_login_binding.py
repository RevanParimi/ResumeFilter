"""Mailbox proof must pin ownership independently of asserted resume hints."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.auth.models import AuthSessionRow
from app.auth.challenges import ChallengeScope
from app.auth.schema import AuthPlane, LoginPurpose
from app.auth.service import ChallengeRefused, RegistrationRefused
from app.candidates.models import CandidateRow
from app.ledger.consent import as_utc
from tests.test_auth_service import NOW, _existing_candidate, _rng, auth  # noqa: F401


def claim(auth, email, *, at=NOW):
    auth.service.request_code(email=email, plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.SIGNUP, at=at, rng=_rng())
    return auth.service.verify_code(email=email, plane=AuthPlane.CANDIDATE,
                                   code=auth.code(), at=at)[2]


def test_proved_mailbox_keeps_subject_when_asserted_hint_changes_or_duplicates(auth):
    email = 'owner@example.in'
    cid = _existing_candidate(auth, email)
    assert claim(auth, email).candidate_id == cid
    with auth.candidates._session_factory.begin() as session:
        session.get(CandidateRow, cid).email_hash = auth.service.hash_email('hint@example.in')
    other = _existing_candidate(auth, email)
    again = claim(auth, email, at=NOW + timedelta(minutes=2))
    assert again.candidate_id == cid
    assert again.candidate_id != other
    with auth.candidates._session_factory() as session:
        row = session.get(CandidateRow, cid)
        assert row.login_email_hash == auth.service.hash_email(email)
        assert as_utc(row.login_email_verified_at) == NOW


def test_other_proved_mailbox_cannot_claim_subject_through_changed_hint(auth):
    cid = _existing_candidate(auth, 'owner@example.in')
    assert claim(auth, 'owner@example.in').candidate_id == cid
    with auth.candidates._session_factory.begin() as session:
        session.get(CandidateRow, cid).email_hash = auth.service.hash_email('other@example.in')
    with pytest.raises(RegistrationRefused):
        claim(auth, 'other@example.in')
    with auth.candidates._session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AuthSessionRow)) == 1


def test_ambiguous_asserted_email_refuses_claim_without_spending_code_or_session(auth):
    email = 'ambiguous@example.in'
    rows = [_existing_candidate(auth, email) for _ in range(2)]
    with pytest.raises(RegistrationRefused):
        claim(auth, email)
    with auth.candidates._session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AuthSessionRow)) == 0
    assert len(rows) == 2
    assert auth.service._store.get_challenge(ChallengeScope(
        auth.service.hash_email(email), LoginPurpose.LOGIN, AuthPlane.CANDIDATE)) is not None


@pytest.mark.parametrize('failure', ['wrong', 'expired', 'foreign_plane'])
def test_invalid_proof_never_binds(auth, failure):
    email = 'proof@example.in'
    cid = _existing_candidate(auth, email)
    _, code = auth.service.issue_code(email=email, plane=AuthPlane.CANDIDATE,
                                     purpose=LoginPurpose.LOGIN, at=NOW)
    wrong = '0' * len(code) if code != '0' * len(code) else '1' * len(code)
    with pytest.raises(ChallengeRefused):
        auth.service.verify_code(email=email, code=wrong if failure == 'wrong' else code,
            plane=AuthPlane.ORG if failure == 'foreign_plane' else AuthPlane.CANDIDATE,
            at=NOW + timedelta(seconds=auth.service._settings.login_otp_ttl_seconds) if failure == 'expired' else NOW)
    with auth.candidates._session_factory() as session:
        row = session.get(CandidateRow, cid)
        assert row.login_email_hash is row.login_email_verified_at is None
        assert session.scalar(select(func.count()).select_from(AuthSessionRow)) == 0


def test_session_failure_rolls_back_initial_binding_and_allows_exact_retry(auth, monkeypatch):
    email = 'rollback@example.in'
    cid = _existing_candidate(auth, email)
    real = auth.service._store.create_session

    def fail(**kwargs):
        real(**kwargs)
        kwargs['session'].flush()
        raise RuntimeError('synthetic session failure')

    monkeypatch.setattr(auth.service._store, 'create_session', fail)
    with pytest.raises(RuntimeError, match='synthetic session failure'):
        claim(auth, email)
    with auth.candidates._session_factory() as session:
        row = session.get(CandidateRow, cid)
        assert row.login_email_hash is row.login_email_verified_at is None
        assert session.scalar(select(func.count()).select_from(AuthSessionRow)) == 0
    assert auth.ledger.audit_for_candidate(cid) == []
    monkeypatch.setattr(auth.service._store, 'create_session', real)
    assert auth.service.verify_code(email=email, plane=AuthPlane.CANDIDATE,
                                   code=auth.code(), at=NOW)[2].candidate_id == cid
    with pytest.raises(ChallengeRefused):
        auth.service.verify_code(email=email, plane=AuthPlane.CANDIDATE, code=auth.code(), at=NOW)
    assert len(auth.ledger.audit_for_candidate(cid)) == 1


def test_review_required_subject_refuses_even_valid_proof(auth):
    cid = _existing_candidate(auth, 'legacy@example.in')
    with auth.candidates._session_factory.begin() as session:
        session.get(CandidateRow, cid).login_binding_review_required = True
    with pytest.raises(RegistrationRefused, match='candidate_identity_review_required'):
        claim(auth, 'legacy@example.in')
    with auth.candidates._session_factory() as session:
        assert session.get(CandidateRow, cid).login_email_hash is None


@pytest.mark.parametrize('erase', [False, True])
def test_cleanup_clears_distinct_proof_and_unowned_hint(auth, erase):
    email, hint = 'bound@example.in', 'asserted@example.in'
    cid = claim(auth, email).candidate_id
    with auth.candidates._session_factory.begin() as session:
        session.get(CandidateRow, cid).email_hash = auth.service.hash_email(hint)
    for address in (email, hint):
        auth.service.issue_code(email=address, plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.LOGIN, at=NOW)
    if erase:
        assert auth.candidates.delete_candidate(cid)
    else:
        assert auth.service.erase_login_state(cid) == 2
    for address in (email, hint):
        assert auth.service._store.get_challenge(ChallengeScope(
            auth.service.hash_email(address), LoginPurpose.LOGIN, AuthPlane.CANDIDATE)) is None


@pytest.mark.parametrize('erase', [False, True])
def test_cleanup_includes_proof_and_hint_but_preserves_other_proved_owner(auth, erase):
    cid = _existing_candidate(auth, 'owner@example.in')
    assert claim(auth, 'owner@example.in').candidate_id == cid
    other = claim(auth, 'survivor@example.in').candidate_id
    # A bad historical hint must never cancel the survivor's proved mailbox.
    with auth.candidates._session_factory.begin() as session:
        session.get(CandidateRow, cid).email_hash = auth.service.hash_email('survivor@example.in')
    for email in ('owner@example.in', 'survivor@example.in'):
        auth.service.issue_code(email=email, plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.LOGIN, at=NOW)
    if erase:
        assert auth.candidates.delete_candidate(cid)
    else:
        assert auth.service.erase_login_state(cid) == 1
    assert auth.service._store.get_challenge(ChallengeScope(auth.service.hash_email('owner@example.in'), LoginPurpose.LOGIN, AuthPlane.CANDIDATE)) is None
    assert auth.service._store.get_challenge(ChallengeScope(auth.service.hash_email('survivor@example.in'), LoginPurpose.LOGIN, AuthPlane.CANDIDATE)) is not None
    assert auth.candidates.get_candidate(other) is not None
