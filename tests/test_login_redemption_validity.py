"""Stale login preflight cannot bypass committed budget/expiry decisions."""

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import event, select, text, update

from app.auth.models import AuthSessionRow, LoginChallengeRow
from app.auth.schema import AuthPlane, LoginPurpose
from app.auth.service import ChallengeRefused
from app.candidates.models import CandidateRow
from app.ledger.consent import as_utc
from tests.test_candidate_login_binding_concurrency import blocked
from tests.test_auth_service import NOW
from tests.test_login_redemption_erasure import setup_auth
from tests.test_report_erasure_concurrency import database  # noqa: F401


@pytest.mark.parametrize('denial', ['exhausted', 'expired'])
@pytest.mark.parametrize('plane', list(AuthPlane))
def test_committed_challenge_invalidation_after_preflight_refuses_session(database, settings, tmp_path, monkeypatch, denial, plane):
    _, factory = database
    auth, _ = setup_auth(factory, settings, tmp_path)
    email = 'a@example.in'
    if plane == AuthPlane.ORG:
        auth._store.create_org_with_owner(name='Synthetic validity org', email_hash=auth.hash_email(email))
    elif plane == AuthPlane.ADMIN:
        auth._store.create_admin_user(email_hash=auth.hash_email(email))
    _, code = auth.issue_code(email=email, plane=plane,
                             purpose=LoginPurpose.LOGIN, at=NOW)
    original = auth._live_scopes

    def invalidate(*args):
        stale = original(*args)
        with factory.begin() as session:
            for _, row in stale:
                session.execute(update(LoginChallengeRow).where(LoginChallengeRow.id == row.id).values(
                    **({'attempts': settings.login_otp_max_attempts} if denial == 'exhausted'
                       else {'expires_at': NOW})))
        return stale

    monkeypatch.setattr(auth, '_live_scopes', invalidate)
    with pytest.raises(ChallengeRefused):
        auth.verify_code(email=email, plane=plane, code=code, at=NOW)
    with factory() as session:
        assert session.scalars(select(AuthSessionRow)).all() == []
        assert all(row.login_email_hash is None for row in session.scalars(select(CandidateRow)))
        assert session.scalar(select(LoginChallengeRow)) is not None


@pytest.mark.parametrize('denial', ['exhausted', 'expired'])
@pytest.mark.parametrize('rollback', [False, True])
def test_competing_challenge_invalidation_is_rechecked_at_consume(database, settings, tmp_path, monkeypatch, denial, rollback):
    engine, factory = database
    auth, _ = setup_auth(factory, settings, tmp_path)
    email = 'a@example.in'
    _, code = auth.issue_code(email=email, plane=AuthPlane.CANDIDATE,
                             purpose=LoginPurpose.LOGIN, at=NOW)
    stale = auth._live_scopes(auth.hash_email(email), AuthPlane.CANDIDATE, None)
    monkeypatch.setattr(auth, '_live_scopes', lambda *args: stale)
    ready, release, started = Event(), Event(), Event()
    owner, pids = [], []

    def invalidate():
        with engine.connect() as connection:
            connection.execute(update(LoginChallengeRow).where(LoginChallengeRow.id == stale[0][1].id).values(
                **({'attempts': settings.login_otp_max_attempts} if denial == 'exhausted'
                   else {'expires_at': NOW})))
            if engine.dialect.name == 'postgresql':
                owner.append(connection.scalar(text('SELECT pg_backend_pid()')))
            ready.set()
            assert release.wait(20)
            connection.rollback() if rollback else connection.commit()

    def record(session, transaction, connection):
        if engine.dialect.name == 'postgresql':
            pids.append(connection.scalar(text('SELECT pg_backend_pid()')))
        started.set()

    event.listen(factory, 'after_begin', record)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(invalidate)
            try:
                assert ready.wait(20)
                proof = pool.submit(auth.verify_code, email=email, plane=AuthPlane.CANDIDATE, code=code, at=NOW)
                assert started.wait(20)
                blocked(engine, proof, owner[0] if owner else None, pids)
            finally:
                release.set()
            writer.result(timeout=20)
            if rollback:
                _, _, principal = proof.result(timeout=20)
                with factory() as session:
                    assert session.get(CandidateRow, principal.candidate_id).login_email_hash == auth.hash_email(email)
            else:
                with pytest.raises(ChallengeRefused):
                    proof.result(timeout=20)
    finally:
        event.remove(factory, 'after_begin', record)
    with factory() as session:
        assert len(session.scalars(select(AuthSessionRow)).all()) == int(rollback)
        assert (session.scalar(select(LoginChallengeRow)) is None) is rollback


@pytest.mark.parametrize('lock', ['address', 'challenge'])
def test_default_redemption_clock_is_sampled_after_login_lock(database, settings, tmp_path, monkeypatch, lock):
    _, factory = database
    auth, _ = setup_auth(factory, settings, tmp_path)
    email = 'a@example.in'
    _, code = auth.issue_code(email=email, plane=AuthPlane.CANDIDATE,
                             purpose=LoginPurpose.LOGIN, at=NOW)
    with factory() as session:
        expires = session.scalar(select(LoginChallengeRow.expires_at))
    # SQLite returns a naive timestamp; compare through the same UTC policy.
    clock = [NOW]
    monkeypatch.setattr('app.auth.service._utcnow', lambda: clock[0])
    original = auth._store.login_transaction

    @contextmanager
    def wait_then_lock(digest):
        with original(digest) as session:
            clock[0] = as_utc(expires)
            yield session

    if lock == 'address':
        monkeypatch.setattr(auth._store, 'login_transaction', wait_then_lock)
    else:
        original_read = auth._store.get_challenge

        def read_then_expire(scope, *, session=None):
            row = original_read(scope, session=session)
            if session is not None:
                clock[0] = as_utc(expires)
            return row

        monkeypatch.setattr(auth._store, 'get_challenge', read_then_expire)
    with pytest.raises(ChallengeRefused):
        auth.verify_code(email=email, plane=AuthPlane.CANDIDATE, code=code)
    with factory() as session:
        assert session.scalars(select(AuthSessionRow)).all() == []
