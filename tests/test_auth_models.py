"""Auth ORM rows and their structural guarantees (S8.2).

Every cascade test here passes with NO service and NO route orchestration at
all -- the database is the guarantee. That ordering is the point, and it is the
S8.1 fold lesson reapplied: a rule that lives in a handler is a convention, and
a third entry point forgetting one line breaks it silently.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.auth.models import (
    AdminUserRow, AuthSessionRow, LoginChallengeRow, OrgUserRow,
)
from app.candidates.models import CandidateRow
from app.ledger.models import OrganizationRow
from tests.conftest import make_candidate_store

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(hours=1)


def _factory():
    return make_candidate_store()._session_factory


def _session_kwargs(**over) -> dict:
    kw = dict(token_hash="tok", issued_at=NOW, expires_at=LATER, last_seen_at=NOW)
    kw.update(over)
    return kw


def test_session_cascades_when_its_candidate_is_erased():
    sf = _factory()
    with sf() as s:
        cand = CandidateRow(email_hash="h")
        s.add(cand)
        s.flush()
        s.add(AuthSessionRow(**_session_kwargs(candidate_id=cand.id)))
        s.commit()
        cid = cand.id
    with sf() as s:
        s.delete(s.get(CandidateRow, cid))
        s.commit()
    with sf() as s:
        assert s.execute(sa.select(AuthSessionRow)).scalars().all() == []


def test_session_and_org_user_cascade_when_the_org_is_deleted():
    sf = _factory()
    with sf() as s:
        org = OrganizationRow(name="Acme")
        s.add(org)
        s.flush()
        ou = OrgUserRow(organization_id=org.id, email_hash="h", role="owner")
        s.add(ou)
        s.flush()
        s.add(AuthSessionRow(**_session_kwargs(org_user_id=ou.id, token_hash="t2")))
        s.commit()
        oid = org.id
    with sf() as s:
        s.delete(s.get(OrganizationRow, oid))
        s.commit()
    with sf() as s:
        assert s.execute(sa.select(AuthSessionRow)).scalars().all() == []
        assert s.execute(sa.select(OrgUserRow)).scalars().all() == []


def test_session_cascades_when_its_operator_is_deleted():
    sf = _factory()
    with sf() as s:
        admin = AdminUserRow(email_hash="a", label="ops")
        s.add(admin)
        s.flush()
        s.add(AuthSessionRow(**_session_kwargs(admin_user_id=admin.id, token_hash="t3")))
        s.commit()
        aid = admin.id
    with sf() as s:
        s.delete(s.get(AdminUserRow, aid))
        s.commit()
    with sf() as s:
        assert s.execute(sa.select(AuthSessionRow)).scalars().all() == []


def test_a_session_with_no_principal_is_rejected():
    sf = _factory()
    with sf() as s:
        s.add(AuthSessionRow(**_session_kwargs()))
        with pytest.raises(IntegrityError):
            s.commit()


def test_a_session_with_two_principals_is_rejected():
    """The exclusive arc is a CHECK, not a convention. A session that is both a
    candidate and an operator would authorize as whichever one the reader
    happened to ask about."""
    sf = _factory()
    with sf() as s:
        cand = CandidateRow(email_hash="h")
        admin = AdminUserRow(email_hash="a", label="ops")
        s.add_all([cand, admin])
        s.flush()
        s.add(AuthSessionRow(
            **_session_kwargs(candidate_id=cand.id, admin_user_id=admin.id)
        ))
        with pytest.raises(IntegrityError):
            s.commit()


def test_token_hash_is_unique():
    """Two sessions sharing a token hash would make one token authenticate as
    two different people, depending on row order."""
    sf = _factory()
    with sf() as s:
        a, b = CandidateRow(email_hash="a"), CandidateRow(email_hash="b")
        s.add_all([a, b])
        s.flush()
        s.add(AuthSessionRow(**_session_kwargs(candidate_id=a.id, token_hash="same")))
        s.add(AuthSessionRow(**_session_kwargs(candidate_id=b.id, token_hash="same")))
        with pytest.raises(IntegrityError):
            s.commit()


def test_org_user_email_is_unique_within_an_org_but_not_across_orgs():
    """A consultant may hold a login at two client firms; the same address twice
    inside ONE org is a duplicate account."""
    sf = _factory()
    with sf() as s:
        one, two = OrganizationRow(name="One"), OrganizationRow(name="Two")
        s.add_all([one, two])
        s.flush()
        s.add(OrgUserRow(organization_id=one.id, email_hash="h", role="owner"))
        s.add(OrgUserRow(organization_id=two.id, email_hash="h", role="owner"))
        s.commit()   # across orgs: fine
        s.add(OrgUserRow(organization_id=one.id, email_hash="h", role="member"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_login_challenges_have_no_foreign_key():
    """At signup time no principal exists, so there is nothing to point at --
    which is exactly why erasure must delete them explicitly (spec 8.1)."""
    assert list(LoginChallengeRow.__table__.foreign_keys) == []


def test_login_challenge_scope_is_unique():
    """One live challenge per (email, purpose, plane): a second must supersede
    the first, not sit beside it with its own fresh attempt budget."""
    sf = _factory()
    with sf() as s:
        for _ in range(2):
            s.add(LoginChallengeRow(
                email_hash="h", purpose="login", plane="candidate",
                code_hash="c", payload={}, created_at=NOW, expires_at=LATER,
                attempts=0, last_sent_at=NOW,
            ))
        with pytest.raises(IntegrityError):
            s.commit()


def test_no_auth_table_can_store_a_plaintext_credential():
    """Structural, in the S7.1 'no column can hold a document' style: the only
    credential-shaped columns are fixed-width hashes, so storing a plaintext
    token would need a migration a reviewer would see."""
    for table, column in (
        (AuthSessionRow, "token_hash"),
        (LoginChallengeRow, "code_hash"),
    ):
        col = table.__table__.columns[column]
        assert col.type.length == 64          # sha256 hex, nothing longer fits
    assert "token" not in AuthSessionRow.__table__.columns
    assert "code" not in LoginChallengeRow.__table__.columns
