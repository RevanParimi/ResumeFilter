"""Auth schema regressions, grouped by behavior."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from app.auth.schema import (
    AdminUser,
    AuthPlane,
    LoginPurpose,
    OrgUser,
    OrgUserRole,
    Principal,
    PrincipalKind,
    PrincipalVia,
    SessionStatus,
    SessionView,
)
from app.auth.csrf import csrf_matches, generate_csrf_token
from app.auth.sessions import effective_status, generate_token, hash_token, should_write_last_seen


# Auth schema

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def test_taxonomies_are_strings():
    assert PrincipalKind.CANDIDATE == "candidate"
    assert PrincipalKind.ORG == "org"
    assert PrincipalKind.ADMIN == "admin"
    assert AuthPlane.CANDIDATE == "candidate"
    assert LoginPurpose.SIGNUP == "signup"
    assert LoginPurpose.LOGIN == "login"
    assert OrgUserRole.OWNER == "owner"


def test_principal_records_how_it_was_established():
    """CSRF enforcement reads `via`. Without it on the object the exemption
    inevitably gets written as 'was a header present?', which is the bypass."""
    p = Principal(kind=PrincipalKind.ORG, via=PrincipalVia.KEY, org_id="org-1")
    assert p.via == PrincipalVia.KEY
    assert p.org_user_id is None    # a shared key is not a person
    assert p.session_id is None


def test_a_session_principal_names_the_human():
    p = Principal(
        kind=PrincipalKind.ORG, via=PrincipalVia.SESSION,
        org_id="org-1", org_user_id="ou-1", session_id="s-1",
    )
    assert p.org_user_id == "ou-1"
    assert p.session_id == "s-1"


def test_an_admin_key_principal_is_deliberately_anonymous():
    """This is what makes attribution possible: admin_user_id being None is the
    difference between 'an operator did it' and 'the shared secret did it'."""
    machine = Principal(kind=PrincipalKind.ADMIN, via=PrincipalVia.KEY)
    human = Principal(
        kind=PrincipalKind.ADMIN, via=PrincipalVia.SESSION, admin_user_id="au-1"
    )
    assert machine.admin_user_id is None
    assert human.admin_user_id == "au-1"


def test_session_view_never_carries_the_token():
    assert "token" not in SessionView.model_fields
    assert "token_hash" not in SessionView.model_fields
    assert "csrf_token" not in SessionView.model_fields


def test_session_view_round_trips():
    v = SessionView(
        id="s-1", issued_at=NOW, expires_at=NOW, last_seen_at=NOW,
        status=SessionStatus.ACTIVE, user_agent="ua", current=True,
    )
    assert SessionView.model_validate(v.model_dump()) == v


def test_session_statuses():
    assert set(SessionStatus) == {
        SessionStatus.ACTIVE, SessionStatus.EXPIRED,
        SessionStatus.IDLE_EXPIRED, SessionStatus.REVOKED,
    }


def test_org_user_defaults_to_member():
    u = OrgUser(
        id="u", organization_id="o", email_hash="h", created_at=NOW
    )
    assert u.role == OrgUserRole.MEMBER
    assert u.disabled_at is None


def test_admin_user_has_no_organization():
    a = AdminUser(id="a", email_hash="h", created_at=NOW)
    assert not hasattr(a, "organization_id")


# Auth csrf

def test_tokens_are_distinct():
    assert generate_csrf_token(32) != generate_csrf_token(32)


def test_matching_tokens_pass():
    token = generate_csrf_token(32)
    assert csrf_matches(token, token) is True


def test_mismatched_tokens_fail():
    assert csrf_matches(generate_csrf_token(32), generate_csrf_token(32)) is False


def test_absent_or_empty_never_matches():
    """THE trap in a double-submit implementation: two empty strings are equal,
    so a naive compare passes a request carrying neither cookie nor header --
    which is every CSRF attack."""
    assert csrf_matches("", "") is False
    assert csrf_matches(None, None) is False
    assert csrf_matches("tok", "") is False
    assert csrf_matches("", "tok") is False
    assert csrf_matches("tok", None) is False
    assert csrf_matches(None, "tok") is False


# Auth sessions

def _status(**over) -> SessionStatus:
    kw = dict(
        expires_at=NOW + timedelta(hours=1),
        last_seen_at=NOW - timedelta(minutes=5),
        revoked_at=None,
        idle_timeout_minutes=120,
        at=NOW,
    )
    kw.update(over)
    return effective_status(**kw)


def test_a_fresh_session_is_active():
    assert _status() == SessionStatus.ACTIVE


def test_absolute_expiry():
    assert _status(expires_at=NOW - timedelta(seconds=1)) == SessionStatus.EXPIRED


def test_expiry_is_inclusive_at_the_boundary():
    """Dead the instant it expires -- the is_challenge_expired convention."""
    assert _status(expires_at=NOW) == SessionStatus.EXPIRED


def test_idle_timeout():
    assert _status(last_seen_at=NOW - timedelta(minutes=121)) == SessionStatus.IDLE_EXPIRED


def test_idle_boundary_is_inclusive():
    assert _status(last_seen_at=NOW - timedelta(minutes=120)) == SessionStatus.IDLE_EXPIRED
    assert _status(last_seen_at=NOW - timedelta(minutes=119)) == SessionStatus.ACTIVE


def test_idle_timeout_can_be_disabled():
    assert _status(
        last_seen_at=NOW - timedelta(days=30), idle_timeout_minutes=0
    ) == SessionStatus.ACTIVE


def test_revocation_beats_everything():
    """Revoked and expired answer different questions -- 'was it taken away?'
    versus 'did it lapse?' -- so revocation is checked first and unconditionally."""
    assert _status(revoked_at=NOW - timedelta(days=1)) == SessionStatus.REVOKED
    assert _status(
        revoked_at=NOW - timedelta(days=1), expires_at=NOW - timedelta(days=1)
    ) == SessionStatus.REVOKED
    assert _status(
        revoked_at=NOW - timedelta(days=1), last_seen_at=NOW - timedelta(days=1)
    ) == SessionStatus.REVOKED


def test_naive_datetimes_are_coerced_to_utc():
    """SQLite refetch drops tzinfo. An uncoerced compare raises, or -- worse --
    silently mis-windows a row written in IST (the S3.1 as_utc lesson)."""
    assert _status(expires_at=datetime(2026, 8, 2, 13, 0)) == SessionStatus.ACTIVE
    assert _status(expires_at=datetime(2026, 8, 2, 11, 0)) == SessionStatus.EXPIRED


def test_tokens_are_distinct_and_long():
    a, b = generate_token(32), generate_token(32)
    assert a != b
    assert len(a) >= 32


def test_hash_token_is_stable_sha256_hex():
    assert hash_token("abc") == hash_token("abc")
    assert len(hash_token("abc")) == 64
    assert hash_token("abc") != hash_token("abd")


def test_hash_token_tolerates_empty():
    """An absent cookie must hash to something that simply matches no row,
    rather than raising inside the resolver on every anonymous request."""
    assert len(hash_token("")) == 64


def test_last_seen_write_is_throttled():
    assert should_write_last_seen(NOW - timedelta(seconds=5), 60, at=NOW) is False
    assert should_write_last_seen(NOW - timedelta(seconds=60), 60, at=NOW) is True
    assert should_write_last_seen(NOW - timedelta(seconds=61), 60, at=NOW) is True


def test_last_seen_throttle_can_be_disabled():
    assert should_write_last_seen(NOW, 0, at=NOW) is True
