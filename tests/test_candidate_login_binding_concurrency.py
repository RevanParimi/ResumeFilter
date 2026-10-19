"""Observe real competing transactions at the verified mailbox boundary."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import event, select, text, update

from app.auth.models import AuthSessionRow
from app.auth.schema import AuthPlane, LoginPurpose
from app.auth.service import ChallengeRefused
from app.candidates.models import CandidateRow
from app.core.db import make_session_factory
from tests.test_login_redemption_erasure import setup_auth
from tests.test_report_erasure_concurrency import database  # noqa: F401
from tests.test_auth_service import NOW


def blocked(engine, future, owner_pid, pids):
    if engine.dialect.name == 'postgresql':
        deadline = monotonic() + 15
        with engine.connect() as observer:
            while monotonic() < deadline:
                if any(owner_pid in observer.scalar(text('SELECT pg_blocking_pids(:pid)'), {'pid': pid}) for pid in list(pids)):
                    assert not future.done()
                    return
        pytest.fail('competing transaction did not block on the controlled owner')
    else:
        with pytest.raises(TimeoutError):
            future.result(timeout=0.2)


@pytest.mark.parametrize('rollback', [False, True])
def test_claim_waits_for_hint_write_and_uses_current_row(database, settings, tmp_path, rollback):
    engine, factory = database
    auth, candidates = setup_auth(factory, settings, tmp_path)
    email = 'owner@example.in'
    with factory.begin() as session:
        session.get(CandidateRow, 'a').email_hash = auth.hash_email(email)
    _, code = auth.issue_code(email=email, plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.LOGIN, at=NOW)
    ready, release, started = Event(), Event(), Event()
    pids, owner = [], []
    writer_factory = make_session_factory(engine)

    def record(session, transaction, connection):
        if engine.dialect.name == 'postgresql':
            pids.append(connection.scalar(text('SELECT pg_backend_pid()')))
        started.set()

    def write():
        with writer_factory() as session:
            session.execute(update(CandidateRow).where(CandidateRow.id == 'a').values(email_hash=auth.hash_email('other@example.in')))
            if engine.dialect.name == 'postgresql':
                owner.append(session.connection().scalar(text('SELECT pg_backend_pid()')))
            ready.set()
            assert release.wait(20)
            session.rollback() if rollback else session.commit()

    event.listen(factory, 'after_begin', record)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(write)
            try:
                assert ready.wait(20)
                proof = pool.submit(auth.verify_code, email=email, plane=AuthPlane.CANDIDATE, code=code, at=NOW)
                assert started.wait(20)
                blocked(engine, proof, owner[0] if owner else None, pids)
            finally:
                release.set()
            writer.result(timeout=20)
            _, _, principal = proof.result(timeout=20)
    finally:
        event.remove(factory, 'after_begin', record)
    assert (principal.candidate_id == 'a') is rollback
    with factory() as session:
        bound = session.scalar(select(CandidateRow).where(CandidateRow.login_email_hash == auth.hash_email(email)))
        assert bound.id == principal.candidate_id
        if not rollback:
            assert session.get(CandidateRow, 'a').login_email_hash is None


def test_same_mailbox_competing_redemptions_bind_and_create_session_once(database, settings, tmp_path, monkeypatch):
    engine, factory = database
    auth, candidates = setup_auth(factory, settings, tmp_path)
    email = 'once@example.in'
    with factory.begin() as session:
        session.get(CandidateRow, 'a').email_hash = auth.hash_email(email)
    _, code = auth.issue_code(email=email, plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.LOGIN, at=NOW)
    ready, release, started = Event(), Event(), Event()
    real = auth._store.create_session
    owner, pids = [], []

    def pause(**kwargs):
        result = real(**kwargs)
        if engine.dialect.name == 'postgresql':
            owner.append(kwargs['session'].connection().scalar(text('SELECT pg_backend_pid()')))
        ready.set()
        assert release.wait(20)
        return result

    def record(session, transaction, connection):
        if engine.dialect.name == 'postgresql':
            pids.append(connection.scalar(text('SELECT pg_backend_pid()')))
        started.set()

    def verify():
        return auth.verify_code(email=email, plane=AuthPlane.CANDIDATE, code=code, at=NOW)

    monkeypatch.setattr(auth._store, 'create_session', pause)
    event.listen(factory, 'after_begin', record)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(verify)
            try:
                assert ready.wait(20)
                started.clear()
                pids.clear()
                second = pool.submit(verify)
                assert started.wait(20)
                blocked(engine, second, owner[0] if owner else None, pids)
            finally:
                release.set()
            assert first.result(timeout=20)[2].candidate_id == 'a'
            with pytest.raises(ChallengeRefused):
                second.result(timeout=20)
    finally:
        event.remove(factory, 'after_begin', record)
    with factory() as session:
        assert len(session.scalars(select(AuthSessionRow)).all()) == 1
        assert session.get(CandidateRow, 'a').login_email_hash == auth.hash_email(email)


@pytest.mark.parametrize('rollback', [False, True])
def test_erasure_serializes_proved_address_even_after_hint_changes(database, settings, tmp_path, monkeypatch, rollback):
    from app.candidates.store import CandidateStore

    engine, factory = database
    auth, candidates = setup_auth(factory, settings, tmp_path)
    email = 'erase-proof@example.in'
    with factory.begin() as session:
        session.get(CandidateRow, 'a').email_hash = auth.hash_email(email)
    _, code = auth.issue_code(email=email, plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.LOGIN, at=NOW)
    old_token, _, _ = auth.verify_code(email=email, plane=AuthPlane.CANDIDATE, code=code, at=NOW)
    with factory.begin() as session:
        session.get(CandidateRow, 'a').email_hash = auth.hash_email('changed-hint@example.in')
    _, code = auth.issue_code(email=email, plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.LOGIN, at=NOW)
    stale = auth._live_scopes(auth.hash_email(email), AuthPlane.CANDIDATE, None)
    monkeypatch.setattr(auth, '_live_scopes', lambda *args: stale)
    eraser = make_session_factory(engine)
    ready, release, started = Event(), Event(), Event()
    owner, pids = [], []

    def pause(session, context):
        if engine.dialect.name == 'postgresql':
            owner.append(session.connection().scalar(text('SELECT pg_backend_pid()')))
        ready.set()
        assert release.wait(20)
        if rollback:
            raise RuntimeError('synthetic erasure rollback')

    def record(session, transaction, connection):
        if engine.dialect.name == 'postgresql':
            pids.append(connection.scalar(text('SELECT pg_backend_pid()')))
        started.set()

    event.listen(eraser, 'after_flush', pause)
    event.listen(factory, 'after_begin', record)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            erase = pool.submit(CandidateStore(eraser).delete_candidate, 'a')
            try:
                assert ready.wait(20)
                proof = pool.submit(auth.verify_code, email=email, plane=AuthPlane.CANDIDATE, code=code, at=NOW)
                assert started.wait(20)
                blocked(engine, proof, owner[0] if owner else None, pids)
            finally:
                release.set()
            if rollback:
                with pytest.raises(RuntimeError, match='synthetic erasure rollback'):
                    erase.result(timeout=20)
                assert proof.result(timeout=20)[2].candidate_id == 'a'
                assert auth._store.session_by_token(old_token, at=NOW) is not None
            else:
                assert erase.result(timeout=20)
                with pytest.raises(ChallengeRefused):
                    proof.result(timeout=20)
                assert candidates.get_candidate('a') is None
                assert auth._store.session_by_token(old_token, at=NOW) is None
    finally:
        event.remove(eraser, 'after_flush', pause)
        event.remove(factory, 'after_begin', record)
    assert candidates.get_candidate('b') is not None
