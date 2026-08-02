"""Auth contracts (S8.2). Pure -- no DB, no HTTP."""

from __future__ import annotations

from datetime import datetime, timezone

from app.auth.schema import (
    AdminUser, AuthPlane, LoginPurpose, OrgUser, OrgUserRole, Principal,
    PrincipalKind, PrincipalVia, SessionStatus, SessionView,
)

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
