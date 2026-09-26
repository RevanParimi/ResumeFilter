"""A send already in flight must not restore a challenge after erasure."""

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import random
import importlib.util
from pathlib import Path
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import event, select, text
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.auth.challenges import ChallengeScope
from app.auth.models import LoginIssuanceRow
from app.auth.schema import AuthPlane, LoginPurpose
from app.auth.service import ChallengeRefused, EmailUnavailableError
from app.auth.store import AuthStore
from app.candidates.models import CandidateRow
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.services.email import EmailSendFailed, EmailUnavailable
from app.retention.sweep import run_sweep
from tests.conftest import ADMIN_HEADERS
from tests.test_portal_sessions import _signup, capture_path, cfg, client, services
from tests.test_report_erasure_concurrency import database

NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def activate(store, scope, token, at=NOW):
    return store.activate_issuance(scope, issuance_id=token, code_hash="new-digest",
                                  expires_at=NOW + timedelta(minutes=10), payload={}, at=at)


def pending_ids(factory):
    with factory() as session:
        return set(session.scalars(select(LoginIssuanceRow.id)))


@pytest.mark.parametrize("door", ["portal", "admin"])
@pytest.mark.parametrize("plane", list(AuthPlane))
def test_send_crossing_erasure_cannot_restore_login(client, services, capture_path, monkeypatch, door, plane):
    email = "erased@example.in"
    csrf = _signup(client, capture_path, email)
    cid = client.get("/portal/me").json()["candidate_id"]
    auth = services.auth
    digest = auth.hash_email(email)
    if plane == AuthPlane.ORG:
        auth._store.create_org_with_owner(name="Surviving org", email_hash=digest)
    elif plane == AuthPlane.ADMIN:
        auth._store.create_admin_user(email_hash=digest)
    actual_send = auth._email.send

    def send(**kwargs):
        actual_send(**kwargs)
        path = "/portal/me" if door == "portal" else f"/candidates/{cid}"
        headers = {"X-CSRF-Token": csrf} if door == "portal" else ADMIN_HEADERS
        assert client.delete(path, headers=headers).status_code == 200

    monkeypatch.setattr(auth._email, "send", send)
    sent, code = auth.issue_code(email=email, plane=plane, purpose=LoginPurpose.LOGIN,
                                at=datetime.now(timezone.utc) + timedelta(minutes=2),
                                rng=random.Random(999))
    scope = ChallengeScope(digest, LoginPurpose.LOGIN, plane)
    assert auth._store.get_challenge(scope) is None
    assert (sent, code) == (False, None)
    assert services.candidates.get_candidate(cid) is None
    assert not pending_ids(services.candidates._session_factory)
    monkeypatch.setattr(auth._email, "send", actual_send)
    sent, code = auth.issue_code(email=email, plane=plane, purpose=LoginPurpose.LOGIN,
                                at=datetime.now(timezone.utc) + timedelta(minutes=3))
    assert sent and code
    _, _, principal = auth.verify_code(email=email, plane=plane, code=code,
                                      at=datetime.now(timezone.utc) + timedelta(minutes=3))
    if plane == AuthPlane.CANDIDATE:
        assert principal.candidate_id != cid


@pytest.mark.parametrize("failure", [EmailSendFailed, EmailUnavailable, RuntimeError])
def test_send_failure_preserves_old_code_and_cancels_only_own_reservation(services, monkeypatch, failure):
    auth = services.auth
    email = "survives@example.in"
    scope = ChallengeScope(auth.hash_email(email), LoginPurpose.LOGIN, AuthPlane.CANDIDATE)
    auth.issue_code(email=email, plane=scope.plane, purpose=scope.purpose, at=NOW)
    old = auth._store.get_challenge(scope)
    auth._store.bump_attempts(scope, challenge_id=old.id)
    other = auth._store.reserve_issuance(scope, expires_at=NOW + timedelta(minutes=10))

    def fail(**kwargs):
        raise failure("synthetic provider failure")

    monkeypatch.setattr(auth._email, "send", fail)
    expected = {EmailSendFailed: ChallengeRefused, EmailUnavailable: EmailUnavailableError,
                RuntimeError: RuntimeError}[failure]
    with pytest.raises(expected):
        auth.issue_code(email=email, plane=scope.plane, purpose=scope.purpose,
                        at=NOW + timedelta(minutes=2))
    still = auth._store.get_challenge(scope)
    assert (still.id, still.code_hash, still.last_sent_at, still.attempts) == (
        old.id, old.code_hash, old.last_sent_at, 1)
    assert pending_ids(services.candidates._session_factory) == {other}


def test_expiry_scope_binding_and_single_activation(database):
    _, factory = database
    store = AuthStore(factory)
    scope = ChallengeScope("a-hash", LoginPurpose.LOGIN, AuthPlane.CANDIDATE)
    token = store.reserve_issuance(scope, expires_at=NOW + timedelta(minutes=1))
    wrong = ChallengeScope("b-hash", LoginPurpose.LOGIN, AuthPlane.CANDIDATE)
    assert not activate(store, wrong, token)
    assert activate(store, scope, token)
    assert not activate(store, scope, token)
    expired = store.reserve_issuance(scope, expires_at=NOW)
    assert not activate(store, scope, expired)
    other = store.reserve_issuance(wrong, expires_at=NOW)
    store.purge_expired_for_email("a-hash", at=NOW)
    assert pending_ids(factory) == {other}


def test_erasure_of_candidate_created_during_unknown_address_send(database):
    _, factory = database
    store = AuthStore(factory)
    scope = ChallengeScope("new-hash", LoginPurpose.SIGNUP, AuthPlane.ORG)
    token = store.reserve_issuance(scope, expires_at=NOW + timedelta(minutes=10))
    cid = CandidateStore(factory).create_bare_candidate(email_hash="new-hash")
    assert CandidateStore(factory).delete_candidate(cid)
    assert not activate(store, scope, token)
    fresh = store.reserve_issuance(scope, expires_at=NOW + timedelta(minutes=10))
    assert activate(store, scope, fresh)


@pytest.mark.parametrize("first", ["erase", "activate", "erase_then_reserve"])
@pytest.mark.parametrize("rollback", [False, True])
def test_competing_cleanup_and_activation(database, first, rollback):
    engine, factory = database
    with factory() as session:
        session.get(CandidateRow, "a").email_hash = "a-hash"
        session.commit()
    scope = ChallengeScope("a-hash", LoginPurpose.LOGIN, AuthPlane.CANDIDATE)
    store = AuthStore(factory)
    token = store.reserve_issuance(scope, expires_at=NOW + timedelta(minutes=10))
    survivor = store.reserve_issuance(
        ChallengeScope("b-hash", LoginPurpose.LOGIN, AuthPlane.CANDIDATE),
        expires_at=NOW + timedelta(minutes=10))
    writer, follower = make_session_factory(engine), make_session_factory(engine)
    ready, release, started = Event(), Event(), Event()
    pids = []

    def pause(session, *_):
        ready.set()
        assert release.wait(20)
        if rollback:
            raise RuntimeError("synthetic rollback")

    def begin(session, transaction, connection):
        if engine.dialect.name == "postgresql":
            pids.append(connection.scalar(text("SELECT pg_backend_pid()")))
        started.set()

    event.listen(writer, "after_flush", pause)
    event.listen(follower, "after_begin", begin)
    erase_first = first != "activate"
    leading = (lambda: CandidateStore(writer).delete_candidate("a")) if erase_first else (
        lambda: activate(AuthStore(writer), scope, token))
    following = (lambda: activate(AuthStore(follower), scope, token)) if erase_first else (
        lambda: CandidateStore(follower).delete_candidate("a"))
    if first == "erase_then_reserve":
        following = lambda: AuthStore(follower).reserve_issuance(
            scope, expires_at=NOW + timedelta(minutes=10))
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(leading)
            try:
                assert ready.wait(20)
                b = pool.submit(following)
                assert started.wait(20)
                # PG must actually wait on the competing connection's lock.
                if engine.dialect.name == "postgresql":
                    blocked = False
                    deadline = monotonic() + 10
                    with engine.connect() as connection:
                        while monotonic() < deadline:
                            if connection.scalar(text("SELECT cardinality(pg_blocking_pids(:pid))"),
                                                 {"pid": pids[0]}):
                                blocked = True
                                break
                    assert blocked and not b.done()
            finally:
                release.set()
            if rollback:
                with pytest.raises(RuntimeError, match="synthetic rollback"):
                    a.result(timeout=20)
            else:
                assert a.result(timeout=20)
            result = b.result(timeout=20)
            if first != "erase_then_reserve":
                assert result is (rollback if erase_first else True)
    finally:
        event.remove(writer, "after_flush", pause)
        event.remove(follower, "after_begin", begin)
    if first == "erase_then_reserve":
        assert isinstance(result, str) and result != token
        assert pending_ids(factory) == ({survivor, token, result} if rollback else {survivor, result})
        assert activate(store, scope, result)
        assert (CandidateStore(factory).get_candidate("a") is not None) is rollback
        return
    if erase_first and rollback:
        assert store.get_challenge(scope) is not None
        assert CandidateStore(factory).delete_candidate("a")
    assert store.get_challenge(scope) is None
    assert pending_ids(factory) == {survivor}


def test_http_cancelled_send_is_generic_and_not_debug_echoed(client, services, capture_path, monkeypatch):
    csrf = _signup(client, capture_path)
    cid = client.get("/portal/me").json()["candidate_id"]
    real_send = services.auth._email.send

    def send(**kwargs):
        real_send(**kwargs)
        services.portal.erase(cid)

    monkeypatch.setattr(services.auth._email, "send", send)
    services.auth._settings.login_otp_cooldown_seconds = 0
    services.settings.login_otp_debug_echo = True
    response = client.post("/auth/candidate/signup", json={"email": "a@b.in"})
    assert response.status_code == 202
    assert not response.json().get("debug_code")
    assert not pending_ids(services.candidates._session_factory)


def test_abandoned_reservations_follow_login_retention(database, settings):
    _, factory = database
    store = AuthStore(factory)
    scope = ChallengeScope("a-hash", LoginPurpose.LOGIN, AuthPlane.CANDIDATE)
    expired = store.reserve_issuance(scope, expires_at=NOW - timedelta(days=8))
    live = store.reserve_issuance(scope, expires_at=NOW + timedelta(minutes=10))
    preview = run_sweep(factory, settings, now=NOW, dry_run=True)
    assert next(c.affected for c in preview.by_class if c.data_class == "login_state") == 1
    assert pending_ids(factory) == {expired, live}
    result = run_sweep(factory, settings, now=NOW, dry_run=False)
    assert next(c.affected for c in result.by_class if c.data_class == "login_state") == 1
    assert pending_ids(factory) == {live}


def test_populated_issuance_migration_roundtrip_preserves_active_codes(database):
    engine, factory = database
    # The fixture owns the entire schema. Exercise actual migration operations
    # on its connection; the external runner also checks the complete chain.
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0027_login_issuances.py"
    spec = importlib.util.spec_from_file_location("login_issuance_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    store = AuthStore(factory)
    scope = ChallengeScope("a-hash", LoginPurpose.LOGIN, AuthPlane.CANDIDATE)
    store.upsert_challenge(scope, code_hash="keep", expires_at=NOW + timedelta(minutes=10),
                           payload={"synthetic": True}, at=NOW)
    original = store.get_challenge(scope)
    for action in (migration.downgrade, migration.upgrade):
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            action()
    token = store.reserve_issuance(scope, expires_at=NOW + timedelta(minutes=10))
    assert token in pending_ids(factory)
    for action in (migration.downgrade, migration.upgrade):
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            action()
    assert not pending_ids(factory)
    current = store.get_challenge(scope)
    assert (current.id, current.code_hash, current.payload) == (original.id, "keep", {"synthetic": True})
