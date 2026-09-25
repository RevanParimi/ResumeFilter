"""Existing login state shares candidate erasure's commit/rollback boundary."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import event, select, text

from app.auth.challenges import ChallengeScope
from app.auth.models import AuthSessionRow, LoginChallengeRow
from app.auth.schema import AuthPlane, LoginPurpose, PrincipalKind
from app.auth.store import AuthStore
from app.candidates.models import CandidateRow
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from tests.conftest import ADMIN_HEADERS
from tests.test_portal_sessions import (
    _code, _signup, capture_path, cfg, client, services,
)
from tests.test_report_erasure_concurrency import database
from tests.test_report_store import _report


def seed_challenges(store, email_hash):
    now = datetime.now(timezone.utc)
    for plane in AuthPlane:
        for purpose in LoginPurpose:
            store.upsert_challenge(
                ChallengeScope(email_hash, purpose, plane), code_hash="synthetic",
                expires_at=now + timedelta(minutes=10), payload={}, at=now,
            )


def challenge_ids(factory, email_hash):
    with factory() as session:
        return set(session.scalars(select(LoginChallengeRow.id).where(
            LoginChallengeRow.email_hash == email_hash)))


@pytest.mark.parametrize("finish", ["commit", "rollback"])
def test_competing_reader_sees_whole_state_until_erasure_commits(database, finish):
    engine, factory = database
    with factory() as session:
        session.get(CandidateRow, "a").email_hash = "a-hash"
        session.get(CandidateRow, "b").email_hash = "b-hash"
        session.commit()
    auth = AuthStore(factory)
    for cid in ("a", "b"):
        seed_challenges(auth, cid + "-hash")
        auth.create_session(kind=PrincipalKind.CANDIDATE, subject_id=cid,
                            csrf_token="synthetic", at=datetime.now(timezone.utc))
    before_a, before_b = challenge_ids(factory, "a-hash"), challenge_ids(factory, "b-hash")
    ready, release = Event(), Event()
    writer_factory = make_session_factory(engine)

    def pause(session, *_):
        ready.set()
        assert release.wait(20), "reader did not release erasure"
        if finish == "rollback":
            raise RuntimeError("synthetic interruption")

    event.listen(writer_factory, "after_flush", pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(CandidateStore(writer_factory).delete_candidate, "a")
            try:
                assert ready.wait(20), "candidate deletion did not flush"
                # A separate connection sees the entire old committed state.
                assert challenge_ids(factory, "a-hash") == before_a
                with factory() as session:
                    assert session.get(CandidateRow, "a") is not None
                    assert session.scalars(select(AuthSessionRow).where(
                        AuthSessionRow.candidate_id == "a")).first() is not None
            finally:
                release.set()
            if finish == "rollback":
                with pytest.raises(RuntimeError, match="synthetic interruption"):
                    pending.result(timeout=20)
                assert challenge_ids(factory, "a-hash") == before_a
                assert CandidateStore(factory).get_candidate("a") is not None
            else:
                assert pending.result(timeout=20)
                assert challenge_ids(factory, "a-hash") == set()
    finally:
        event.remove(writer_factory, "after_flush", pause)

    # Retry after failure, or retry an already completed deletion.
    assert CandidateStore(factory).delete_candidate("a") is (finish == "rollback")
    assert challenge_ids(factory, "a-hash") == set()
    assert challenge_ids(factory, "b-hash") == before_b
    with factory() as session:
        assert session.get(CandidateRow, "a") is None
        assert session.get(CandidateRow, "b") is not None
        assert list(session.scalars(select(AuthSessionRow.candidate_id))) == ["b"]


@pytest.mark.parametrize("door", ["portal", "admin"])
@pytest.mark.parametrize("failure", ["candidate_delete", "challenge_delete"])
def test_both_doors_rollback_and_retry(client, capture_path, services, door, failure):
    csrf = _signup(client, capture_path, "erased@example.in")
    cid = client.get("/portal/me").json()["candidate_id"]
    factory = services.candidates._session_factory
    store = services.auth._store
    digest = services.auth.hash_email("erased@example.in")
    keeper = services.candidates.create_bare_candidate(email_hash="keep-hash")
    services.report_store.save(_report(candidate_id=cid))
    now = datetime.now(timezone.utc)
    _, owner = store.create_org_with_owner(name="Synthetic survivor", email_hash=digest)
    operator = store.create_admin_user(email_hash=digest)
    survivors = [store.create_session(kind=kind, subject_id=subject,
                                     csrf_token="synthetic", at=now)[0]
                 for kind, subject in [(PrincipalKind.ORG, owner.id),
                                       (PrincipalKind.ADMIN, operator.id),
                                       (PrincipalKind.CANDIDATE, keeper)]]
    for value in (digest, "keep-hash"):
        seed_challenges(store, value)
    before = challenge_ids(factory, digest)
    keep_before = challenge_ids(factory, "keep-hash")
    path = "/portal/me" if door == "portal" else f"/candidates/{cid}"
    headers = {"X-CSRF-Token": csrf} if door == "portal" else ADMIN_HEADERS
    table = "candidates" if failure == "candidate_delete" else "login_challenges"

    def fail(conn, cursor, statement, params, context, executemany):
        if statement.lower().startswith("delete from " + table):
            raise RuntimeError("synthetic database failure")

    engine = factory.kw["bind"]
    event.listen(engine, "before_cursor_execute", fail)
    try:
        assert client.delete(path, headers=headers).status_code == 500
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert challenge_ids(factory, digest) == before
    assert client.get("/portal/me").status_code == 200
    assert services.candidates.get_candidate(cid) is not None
    assert len(services.report_store.for_candidate(cid)) == 1
    assert challenge_ids(factory, "keep-hash") == keep_before

    response = client.delete(path, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"candidate_id": cid, "deleted": True, "reports_deleted": 1}
    assert client.get("/portal/me").status_code == 401
    assert challenge_ids(factory, digest) == set()
    assert services.candidates.get_candidate(keeper) is not None
    assert challenge_ids(factory, "keep-hash") == keep_before
    assert services.report_store.for_candidate(cid) == []
    assert store.org_user_by_email(digest).id == owner.id
    assert store.admin_user_by_email(digest).id == operator.id
    assert all(store.session_by_token(token, at=now) is not None for token in survivors)
    assert services.portal.erase(cid)["deleted"] is False

    # The erased email is free to sign up again; the retained unrelated email
    # has the same public response. No policy of permanent address suppression.
    response = client.post("/auth/candidate/signup", json={"email": "erased@example.in"})
    assert response.status_code == 202
    code = _code(capture_path)
    verified = client.post("/auth/candidate/verify", json={"email": "erased@example.in", "code": code})
    assert verified.status_code == 200
    assert client.get("/portal/me").json()["candidate_id"] != cid


@pytest.mark.parametrize("email_hash", [None, ""])
def test_no_contact_does_not_erase_unassociated_challenges(database, email_hash):
    _, factory = database
    with factory() as session:
        session.get(CandidateRow, "a").email_hash = email_hash
        session.commit()
    seed_challenges(AuthStore(factory), "")
    before = challenge_ids(factory, "")
    assert CandidateStore(factory).delete_candidate("a")
    assert not CandidateStore(factory).delete_candidate("a")
    assert challenge_ids(factory, "") == before


@pytest.mark.parametrize("finish", ["commit", "rollback"])
def test_postgres_consume_waits_for_whole_erasure(database, finish):
    engine, factory = database
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL lock inspection")
    with factory() as session:
        session.get(CandidateRow, "a").email_hash = "a-hash"
        session.commit()
    auth = AuthStore(factory)
    seed_challenges(auth, "a-hash")
    scope = ChallengeScope("a-hash", LoginPurpose.LOGIN, AuthPlane.CANDIDATE)
    challenge = auth.get_challenge(scope)
    writer, consumer = make_session_factory(engine), make_session_factory(engine)
    ready, release, consuming = Event(), Event(), Event()
    pids = []

    def pause(session, *_):
        ready.set()
        assert release.wait(20)
        if finish == "rollback":
            raise RuntimeError("synthetic interruption")

    def pid(session, transaction, connection):
        pids.append(connection.scalar(text("SELECT pg_backend_pid()")))
        consuming.set()

    event.listen(writer, "after_flush", pause)
    event.listen(consumer, "after_begin", pid)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            erasing = pool.submit(CandidateStore(writer).delete_candidate, "a")
            try:
                assert ready.wait(20)
                consuming_code = pool.submit(AuthStore(consumer).consume_challenge,
                    scope, challenge_id=challenge.id, code_hash=challenge.code_hash)
                assert consuming.wait(20)
                blocked = False
                deadline = monotonic() + 10
                with engine.connect() as connection:
                    while monotonic() < deadline:
                        if connection.scalar(text("SELECT cardinality(pg_blocking_pids(:pid))"), {"pid": pids[0]}):
                            blocked = True
                            break
                assert blocked and not consuming_code.done()
            finally:
                release.set()
            if finish == "rollback":
                with pytest.raises(RuntimeError, match="synthetic interruption"):
                    erasing.result(timeout=20)
            else:
                assert erasing.result(timeout=20)
            assert consuming_code.result(timeout=20) is (finish == "rollback")
    finally:
        event.remove(writer, "after_flush", pause)
        event.remove(consumer, "after_begin", pid)
    assert (CandidateStore(factory).get_candidate("a") is None) is (finish == "commit")
    assert len(challenge_ids(factory, "a-hash")) == (5 if finish == "rollback" else 0)
