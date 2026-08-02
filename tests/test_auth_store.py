"""AuthStore: sessions, login challenges, org users, operators (S8.2).

Clock injected on every call. Nothing here reads the wall clock, so no test in
this file can become the pinned-NOW time bomb that detonated during S8.1.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.auth.challenges import ChallengeScope
from app.auth.schema import (
    AuthPlane, LoginPurpose, OrgUserRole, PrincipalKind, SessionStatus,
)
from app.auth.store import AuthStore
from app.candidates.models import CandidateRow
from app.ledger.models import OrganizationRow
from tests.conftest import make_candidate_store

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store_fixture(settings):
    """(candidates, auth_store, candidate_id, organization_id)."""
    candidates = make_candidate_store()
    store = AuthStore(candidates._session_factory, settings=settings)
    with candidates._session_factory() as s:
        cand = CandidateRow(email_hash="hash-1")
        org = OrganizationRow(name="Acme")
        s.add_all([cand, org])
        s.commit()
        return candidates, store, cand.id, org.id


def _scope(**over) -> ChallengeScope:
    kw = dict(email_hash="h", purpose=LoginPurpose.LOGIN, plane=AuthPlane.CANDIDATE)
    kw.update(over)
    return ChallengeScope(**kw)


# ── sessions ────────────────────────────────────────────────────────────────


def test_create_session_returns_plaintext_once_and_stores_only_a_hash(store_fixture):
    _, store, cid, _ = store_fixture
    raw, view = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    assert raw and len(raw) > 20
    resolved = store.session_by_token(raw, at=NOW)
    assert resolved.status == SessionStatus.ACTIVE
    assert resolved.id == view.id
    assert resolved.candidate_id == cid
    assert raw not in repr(resolved)      # the plaintext is never handed back


def test_an_unknown_token_resolves_to_nothing(store_fixture):
    _, store, _, _ = store_fixture
    assert store.session_by_token("nope", at=NOW) is None
    assert store.session_by_token("", at=NOW) is None


def test_revoked_session_reads_revoked_immediately(store_fixture):
    _, store, cid, _ = store_fixture
    raw, view = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    assert store.revoke(view.id, at=NOW) is True
    assert store.session_by_token(raw, at=NOW).status == SessionStatus.REVOKED


def test_revoking_twice_is_harmless(store_fixture):
    _, store, cid, _ = store_fixture
    _, view = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    assert store.revoke(view.id, at=NOW) is True
    assert store.revoke(view.id, at=NOW) is False


def test_expiry_and_idle_are_read_time_not_written(store_fixture):
    """Nothing wrote a status; the same stored row reads differently as the
    clock moves. That is the S7.1 effective_status precedent."""
    _, store, cid, _ = store_fixture
    raw, _ = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    assert store.session_by_token(
        raw, at=NOW + timedelta(minutes=121)
    ).status == SessionStatus.IDLE_EXPIRED
    assert store.session_by_token(
        raw, at=NOW + timedelta(hours=13)
    ).status == SessionStatus.EXPIRED
    assert store.session_by_token(raw, at=NOW).status == SessionStatus.ACTIVE


def test_touch_is_throttled(store_fixture):
    _, store, cid, _ = store_fixture
    raw, view = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    store.touch(view.id, at=NOW + timedelta(seconds=5))
    assert store.session_by_token(raw, at=NOW).last_seen_at == NOW
    store.touch(view.id, at=NOW + timedelta(seconds=90))
    assert store.session_by_token(
        raw, at=NOW
    ).last_seen_at == NOW + timedelta(seconds=90)


def test_erasing_the_candidate_kills_the_session(store_fixture):
    candidates, store, cid, _ = store_fixture
    raw, _ = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    candidates.delete_candidate(cid)
    assert store.session_by_token(raw, at=NOW) is None


def test_sessions_for_lists_only_that_principal(store_fixture):
    candidates, store, cid, _ = store_fixture
    with candidates._session_factory() as s:
        other = CandidateRow(email_hash="hash-2")
        s.add(other)
        s.commit()
        other_id = other.id
    _, mine = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=other_id, csrf_token="c", at=NOW
    )
    listed = store.sessions_for(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, at=NOW, current_id=mine.id
    )
    assert [v.id for v in listed] == [mine.id]
    assert listed[0].current is True


def test_sessions_for_omits_dead_ones(store_fixture):
    _, store, cid, _ = store_fixture
    _, live = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    _, dead = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    store.revoke(dead.id, at=NOW)
    listed = store.sessions_for(kind=PrincipalKind.CANDIDATE, subject_id=cid, at=NOW)
    assert [v.id for v in listed] == [live.id]


def test_an_org_session_hangs_off_the_org_USER_not_the_org(store_fixture):
    _, store, _, org_id = store_fixture
    user = store.create_org_user(
        organization_id=org_id, email_hash="oh", role=OrgUserRole.OWNER
    )
    raw, _ = store.create_session(
        kind=PrincipalKind.ORG, subject_id=user.id, csrf_token="c", at=NOW
    )
    resolved = store.session_by_token(raw, at=NOW)
    assert resolved.org_user_id == user.id
    assert resolved.candidate_id is None


# ── login challenges ────────────────────────────────────────────────────────


def test_challenge_upsert_supersedes_rather_than_accumulating(store_fixture):
    """A resend must not hand the attacker a fresh attempt budget beside the
    old one -- that is what makes the cap meaningful."""
    _, store, _, _ = store_fixture
    scope = _scope()
    store.upsert_challenge(
        scope, code_hash="a", expires_at=NOW + timedelta(minutes=10), payload={}, at=NOW
    )
    store.bump_attempts(scope)
    store.upsert_challenge(
        scope, code_hash="b", expires_at=NOW + timedelta(minutes=10), payload={}, at=NOW
    )
    row = store.get_challenge(scope)
    assert row.code_hash == "b"
    assert row.attempts == 0


def test_challenges_are_scoped_by_plane_and_purpose(store_fixture):
    _, store, _, _ = store_fixture
    a = _scope()
    b = _scope(plane=AuthPlane.ORG)
    c = _scope(purpose=LoginPurpose.SIGNUP)
    for scope, code in ((a, "a"), (b, "b"), (c, "c")):
        store.upsert_challenge(
            scope, code_hash=code, expires_at=NOW + timedelta(minutes=10),
            payload={}, at=NOW,
        )
    assert store.get_challenge(a).code_hash == "a"
    assert store.get_challenge(b).code_hash == "b"
    assert store.get_challenge(c).code_hash == "c"


def test_bump_attempts_counts(store_fixture):
    _, store, _, _ = store_fixture
    scope = _scope()
    store.upsert_challenge(
        scope, code_hash="a", expires_at=NOW + timedelta(minutes=10), payload={}, at=NOW
    )
    store.bump_attempts(scope)
    store.bump_attempts(scope)
    assert store.get_challenge(scope).attempts == 2


def test_payload_survives_the_round_trip(store_fixture):
    _, store, _, _ = store_fixture
    scope = _scope(purpose=LoginPurpose.SIGNUP, plane=AuthPlane.ORG)
    store.upsert_challenge(
        scope, code_hash="a", expires_at=NOW + timedelta(minutes=10),
        payload={"organization_name": "Acme"}, at=NOW,
    )
    assert store.get_challenge(scope).payload == {"organization_name": "Acme"}


def test_delete_challenge_consumes_it(store_fixture):
    _, store, _, _ = store_fixture
    scope = _scope()
    store.upsert_challenge(
        scope, code_hash="a", expires_at=NOW + timedelta(minutes=10), payload={}, at=NOW
    )
    store.delete_challenge(scope)
    assert store.get_challenge(scope) is None


def test_delete_challenges_for_email_covers_every_plane_and_purpose(store_fixture):
    """DELETE /portal/me relies on this: login_challenges has no FK, so nothing
    cascades and an outstanding challenge would outlive the person."""
    _, store, _, _ = store_fixture
    for plane in (AuthPlane.CANDIDATE, AuthPlane.ORG):
        for purpose in (LoginPurpose.LOGIN, LoginPurpose.SIGNUP):
            store.upsert_challenge(
                _scope(plane=plane, purpose=purpose), code_hash="x",
                expires_at=NOW + timedelta(minutes=10), payload={}, at=NOW,
            )
    assert store.delete_challenges_for_email("h") == 4
    assert store.get_challenge(_scope()) is None


def test_purge_expired_leaves_live_challenges_alone(store_fixture):
    _, store, _, _ = store_fixture
    live = _scope()
    stale = _scope(plane=AuthPlane.ORG)
    store.upsert_challenge(
        live, code_hash="a", expires_at=NOW + timedelta(minutes=10), payload={}, at=NOW
    )
    store.upsert_challenge(
        stale, code_hash="b", expires_at=NOW - timedelta(minutes=1), payload={}, at=NOW
    )
    store.purge_expired_for_email("h", at=NOW)
    assert store.get_challenge(live) is not None
    assert store.get_challenge(stale) is None


# ── org users and operators ─────────────────────────────────────────────────


def test_org_user_create_and_lookup(store_fixture):
    _, store, _, org_id = store_fixture
    created = store.create_org_user(
        organization_id=org_id, email_hash="oh", role=OrgUserRole.OWNER
    )
    found = store.org_user_by_email("oh")
    assert found.id == created.id
    assert found.organization_id == org_id
    assert found.role == OrgUserRole.OWNER
    assert store.org_user_by_email("nobody") is None


def test_admin_user_create_list_and_delete(store_fixture):
    _, store, _, _ = store_fixture
    created = store.create_admin_user(email_hash="ah", label="ops")
    assert store.admin_user_by_email("ah").id == created.id
    assert [a.id for a in store.list_admin_users()] == [created.id]
    assert store.delete_admin_user(created.id) is True
    assert store.admin_user_by_email("ah") is None
    assert store.delete_admin_user(created.id) is False


def test_a_disabled_principal_is_not_returned(store_fixture):
    """Disabling is how an operator loses access without destroying the audit
    trail that names them."""
    _, store, _, org_id = store_fixture
    admin = store.create_admin_user(email_hash="ah", label="ops")
    user = store.create_org_user(
        organization_id=org_id, email_hash="oh", role=OrgUserRole.OWNER
    )
    store.disable_admin_user(admin.id)
    store.disable_org_user(user.id)
    assert store.admin_user_by_email("ah") is None
    assert store.org_user_by_email("oh") is None


# ── candidate lookup: the machinery behind the claim decision ───────────────


def test_candidate_lookup_and_bare_creation(store_fixture):
    candidates, _, cid, _ = store_fixture
    assert candidates.find_by_email_hash("hash-1") == cid
    assert candidates.find_by_email_hash("nobody") is None
    assert candidates.find_by_email_hash("") is None
    new_id = candidates.create_bare_candidate(email_hash="fresh")
    assert candidates.find_by_email_hash("fresh") == new_id
    assert new_id != cid


def test_email_hash_for_feeds_the_erasure_path(store_fixture):
    candidates, _, cid, _ = store_fixture
    assert candidates.email_hash_for(cid) == "hash-1"
    assert candidates.email_hash_for("no-such-candidate") is None
