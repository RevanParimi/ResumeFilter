"""Redemption and erasure commit in one address order, across connections."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import event, select, text

from app.auth.challenges import ChallengeScope
from app.auth.models import AuthSessionRow, OrgUserRow
from app.auth.schema import AuthPlane, LoginPurpose
from app.auth.service import ChallengeRefused, build_auth_service
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.ledger.store import LedgerStore
from app.ledger.models import AuditLogRow, OrganizationRow
from app.services.email import CaptureEmail
from tests.conftest import ADMIN_HEADERS
from tests.test_portal_sessions import _signup, capture_path, cfg, client, services
from tests.test_report_erasure_concurrency import database

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)
EMAIL = "redeem@example.in"


def setup_auth(factory, settings, tmp_path):
    cfg = settings.model_copy(update={"email_provider": "capture",
        "email_capture_path": str(tmp_path / "mail.jsonl")})
    candidates = CandidateStore(factory)
    auth = build_auth_service(cfg, candidates=candidates, email=CaptureEmail(cfg),
                              ledger=LedgerStore(factory, settings=cfg))
    return auth, candidates


def assert_blocked(engine, future, pids):
    if engine.dialect.name == "postgresql":
        deadline = monotonic() + 10
        with engine.connect() as connection:
            while monotonic() < deadline:
                if connection.scalar(text("SELECT cardinality(pg_blocking_pids(:pid))"),
                                     {"pid": pids[0]}):
                    assert not future.done()
                    return
        pytest.fail("competing connection never blocked")
    with pytest.raises(TimeoutError):
        future.result(timeout=0.2)


@pytest.mark.parametrize("stage", ["consume", "principal", "session"])
@pytest.mark.parametrize("plane", list(AuthPlane))
def test_erasure_after_consume_cannot_recreate_candidate(database, settings, tmp_path, monkeypatch, stage, plane):
    engine, factory = database
    auth, candidates = setup_auth(factory, settings, tmp_path)
    digest = auth.hash_email(EMAIL)
    cid = candidates.create_bare_candidate(email_hash=digest)
    if plane == AuthPlane.ORG:
        auth._store.create_org_with_owner(name="Surviving org", email_hash=digest)
    elif plane == AuthPlane.ADMIN:
        auth._store.create_admin_user(email_hash=digest)
    _, code = auth.issue_code(email=EMAIL, plane=plane,
                             purpose=LoginPurpose.LOGIN, at=NOW)
    ready, release, started = Event(), Event(), Event()
    owner, method = {"consume": (auth._store, "consume_challenge"),
                     "principal": (auth, "_establish"),
                     "session": (auth._store, "create_session")}[stage]
    actual = getattr(owner, method)

    def consume(*args, **kwargs):
        result = actual(*args, **kwargs)
        ready.set()
        assert release.wait(20)
        return result

    monkeypatch.setattr(owner, method, consume)
    eraser_factory = make_session_factory(engine)
    pids = []

    def begin(session, transaction, connection):
        if engine.dialect.name == "postgresql":
            pids.append(connection.scalar(text("SELECT pg_backend_pid()")))
        started.set()

    event.listen(eraser_factory, "after_begin", begin)
    with ThreadPoolExecutor(max_workers=2) as pool:
        verify = pool.submit(auth.verify_code, email=EMAIL, plane=plane,
                             code=code, at=NOW)
        try:
            assert ready.wait(20)
            erase = pool.submit(CandidateStore(eraser_factory).delete_candidate, cid)
            assert started.wait(20)
            assert_blocked(engine, erase, pids)
        finally:
            release.set()
        token, _, principal = verify.result(timeout=20)
        assert erase.result(timeout=20)
    assert candidates.find_by_email_hash(digest) is None
    if plane == AuthPlane.CANDIDATE:
        assert auth._store.session_by_token(token, at=NOW) is None
        assert principal.candidate_id == cid
    else:
        assert auth._store.session_by_token(token, at=NOW) is not None
    assert candidates.get_candidate("b") is not None


@pytest.mark.parametrize("plane", [AuthPlane.CANDIDATE, AuthPlane.ORG])
def test_failed_redemption_rolls_back_new_principal_and_consume(database, settings, tmp_path, monkeypatch, plane):
    _, factory = database
    auth, candidates = setup_auth(factory, settings, tmp_path)
    _, code = auth.issue_code(email=EMAIL, plane=plane,
                             purpose=LoginPurpose.SIGNUP, at=NOW,
                             payload={"organization_name": "Fresh org"})
    digest = auth.hash_email(EMAIL)
    scope = ChallengeScope(digest, LoginPurpose.LOGIN if plane == AuthPlane.CANDIDATE
                           else LoginPurpose.SIGNUP, plane)
    real_create = auth._store.create_session

    def fail(**kwargs):
        real_create(**kwargs)
        # Include the audit INSERT in the failed transaction, not only the
        # pending ORM object, so rollback proves all persisted state is gone.
        kwargs["session"].flush()
        raise RuntimeError("synthetic interruption after session creation")

    monkeypatch.setattr(auth._store, "create_session", fail)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        auth.verify_code(email=EMAIL, plane=plane, code=code, at=NOW)
    assert candidates.find_by_email_hash(digest) is None
    assert auth._store.get_challenge(scope) is not None
    with factory() as session:
        assert list(session.scalars(select(AuthSessionRow))) == []
        assert list(session.scalars(select(AuditLogRow))) == []
        assert list(session.scalars(select(OrganizationRow))) == []
        assert list(session.scalars(select(OrgUserRow))) == []
    monkeypatch.setattr(auth._store, "create_session", real_create)
    token, _, _ = auth.verify_code(email=EMAIL, plane=plane, code=code, at=NOW)
    assert auth._store.session_by_token(token, at=NOW) is not None
    with pytest.raises(ChallengeRefused):
        auth.verify_code(email=EMAIL, plane=plane, code=code, at=NOW)
    with factory() as session:
        assert len(list(session.scalars(select(AuthSessionRow)))) == 1
        audits = list(session.scalars(select(AuditLogRow)))
        assert len(audits) == (1 if plane == AuthPlane.CANDIDATE else 0)
        if audits:
            assert audits[0].action == "auth.session.create"


@pytest.mark.parametrize("door", ["portal", "admin"])
@pytest.mark.parametrize("plane", list(AuthPlane))
def test_http_stale_verifier_is_refused_after_erasure(client, services, capture_path, monkeypatch, door, plane):
    csrf = _signup(client, capture_path, EMAIL)
    cid = client.get("/portal/me").json()["candidate_id"]
    auth = services.auth
    digest = auth.hash_email(EMAIL)
    auth._settings.login_otp_cooldown_seconds = 0
    if plane == AuthPlane.ORG:
        auth._store.create_org_with_owner(name="Surviving org", email_hash=digest)
    elif plane == AuthPlane.ADMIN:
        auth._store.create_admin_user(email_hash=digest)
    _, code = auth.issue_code(email=EMAIL, plane=plane, purpose=LoginPurpose.LOGIN,
                             at=datetime.now(timezone.utc))
    real_scopes = auth._live_scopes

    stale = real_scopes(digest, plane, None)
    path = "/portal/me" if door == "portal" else f"/candidates/{cid}"
    headers = {"X-CSRF-Token": csrf} if door == "portal" else ADMIN_HEADERS
    assert client.delete(path, headers=headers).status_code == 200
    monkeypatch.setattr(auth, "_live_scopes", lambda *args: stale)
    refused = client.post(f"/auth/{plane}/verify", json={"email": EMAIL, "code": code})
    assert refused.status_code == 400
    assert "set-cookie" not in refused.headers
    assert services.candidates.find_by_email_hash(digest) is None
    monkeypatch.setattr(auth, "_live_scopes", real_scopes)
    unknown = client.post(f"/auth/{plane}/verify", json={"email": "unknown@example.in", "code": code})
    assert unknown.status_code == 400 and unknown.json() == refused.json()
    assert client.post(f"/auth/{plane}/login", json={"email": EMAIL}).status_code == 202
    from tests.test_portal_sessions import _code
    assert client.post(f"/auth/{plane}/verify", json={"email": EMAIL, "code": _code(capture_path)}).status_code == 200


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("plane", list(AuthPlane))
def test_redemption_waits_for_erasure_commit_or_rollback(database, settings, tmp_path, monkeypatch, rollback, plane):
    engine, factory = database
    auth, candidates = setup_auth(factory, settings, tmp_path)
    digest = auth.hash_email(EMAIL)
    cid = candidates.create_bare_candidate(email_hash=digest)
    if plane == AuthPlane.ORG:
        auth._store.create_org_with_owner(name="Surviving org", email_hash=digest)
    elif plane == AuthPlane.ADMIN:
        auth._store.create_admin_user(email_hash=digest)
    _, code = auth.issue_code(email=EMAIL, plane=plane, purpose=LoginPurpose.LOGIN, at=NOW)
    stale = auth._live_scopes(digest, plane, None)
    monkeypatch.setattr(auth, "_live_scopes", lambda *args: stale)
    ready, release, started = Event(), Event(), Event()
    pids = []
    eraser = make_session_factory(engine)

    def pause(*args):
        ready.set()
        assert release.wait(20)
        if rollback:
            raise RuntimeError("synthetic erasure rollback")

    def begin(session, transaction, connection):
        if engine.dialect.name == "postgresql":
            pids.append(connection.scalar(text("SELECT pg_backend_pid()")))
        started.set()

    event.listen(eraser, "after_flush", pause)
    event.listen(factory, "after_begin", begin)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            erase = pool.submit(CandidateStore(eraser).delete_candidate, cid)
            try:
                assert ready.wait(20)
                verify = pool.submit(auth.verify_code, email=EMAIL, plane=plane, code=code, at=NOW)
                assert started.wait(20)
                assert_blocked(engine, verify, pids)
            finally:
                release.set()
            if rollback:
                with pytest.raises(RuntimeError, match="synthetic erasure rollback"):
                    erase.result(timeout=20)
                token, _, _ = verify.result(timeout=20)
                assert auth._store.session_by_token(token, at=NOW) is not None
            else:
                assert erase.result(timeout=20)
                with pytest.raises(ChallengeRefused):
                    verify.result(timeout=20)
    finally:
        event.remove(eraser, "after_flush", pause)
        event.remove(factory, "after_begin", begin)
    assert (candidates.find_by_email_hash(digest) == cid) is rollback
    assert candidates.get_candidate("b") is not None


@pytest.mark.parametrize("plane", list(AuthPlane))
def test_competing_verifiers_commit_only_one_session(database, settings, tmp_path, monkeypatch, plane):
    from threading import Barrier

    engine, factory = database
    auth, candidates = setup_auth(factory, settings, tmp_path)
    digest = auth.hash_email(EMAIL)
    candidates.create_bare_candidate(email_hash=digest)
    if plane == AuthPlane.ORG:
        auth._store.create_org_with_owner(name="Competing org", email_hash=digest)
    elif plane == AuthPlane.ADMIN:
        auth._store.create_admin_user(email_hash=digest)
    _, code = auth.issue_code(email=EMAIL, plane=plane,
                             purpose=LoginPurpose.LOGIN, at=NOW)
    other, _ = setup_auth(make_session_factory(engine), settings, tmp_path)
    barrier = Barrier(2)
    actual = auth._live_scopes

    def scopes(*args):
        rows = actual(*args)
        barrier.wait(timeout=20)
        return rows

    monkeypatch.setattr(auth, "_live_scopes", scopes)
    monkeypatch.setattr(other, "_live_scopes", scopes)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.verify_code, email=EMAIL, plane=plane,
                               code=code, at=NOW) for service in (auth, other)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=20))
            except ChallengeRefused:
                outcomes.append(None)
    assert sum(result is not None for result in outcomes) == 1
    with factory() as session:
        assert len(list(session.scalars(select(AuthSessionRow)))) == 1
