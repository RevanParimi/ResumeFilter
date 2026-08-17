"""ORM rows for auth (S8.2). Postgres-shaped on SQLite.

``auth_sessions`` uses an EXCLUSIVE ARC -- three nullable FKs plus a CHECK that
exactly one is non-null -- rather than a polymorphic ``subject_type`` +
``subject_id``. A polymorphic id column CANNOT carry a foreign key, so erasure
would stop cascading, silently breaking the guarantee that has held for eight
PIs. Three nullable FKs keep the cascade in the database, where it belongs, and
``DELETE /portal/me`` then kills every session of that candidate for free.

Three separate session tables would give the same guarantee with three times
the surface and three places for a gate to be forgotten -- which is exactly the
bug shape this sprint exists to close.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrgUserRow(Base):
    """A human who logs into an organization.

    The org's ``X-Org-Key`` is a MACHINE credential and is unaffected: both
    modes are permanent (PI-8 decision 0.4), because the long-lived key IS the
    API product, not a legacy path.
    """

    __tablename__ = "org_users"
    __table_args__ = (
        # Across orgs the same address is fine -- a consultant may hold a login
        # at two client firms. Twice inside ONE org is a duplicate account.
        UniqueConstraint("organization_id", "email_hash", name="uq_org_users_org_email"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email_hash: Mapped[str] = mapped_column(String(64), index=True)
    # owner | member. The invite ENDPOINTS are a non-goal for S8.2, but the
    # column ships now so adding them later needs no migration.
    role: Mapped[str] = mapped_column(String(16), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    disabled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AdminUserRow(Base):
    """A platform operator (PI-8 decision 0.5).

    No FK: operators are not data principals in the DPDP sense, and there is
    nothing for them to cascade from. They exist so an admin action can be
    attributed to a PERSON -- a shared secret cannot, and S7.1's review already
    caught one audit misattribution.
    """

    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    disabled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuthSessionRow(Base):
    """One opaque server-side session. Exactly one principal, always."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN candidate_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN org_user_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN admin_user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_auth_sessions_exactly_one_principal",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True, index=True
    )
    org_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("org_users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    admin_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # sha256 of the token. The plaintext is returned ONCE and never stored,
    # mirroring CandidateStore.issue_access_key. Unique, because two rows
    # sharing a hash would make one token authenticate as two different people.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    csrf_token: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # A hash, never a raw IP. The precedent is email_hash/phone_hash on
    # candidates: store what identifies, not what re-identifies.
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class LoginChallengeRow(Base):
    """A pending email-OTP signup or login.

    NO foreign key, deliberately: at signup time no principal exists yet, so
    there is nothing to point at. That is precisely why the erasure path must
    delete these explicitly by email_hash -- the one guarantee in this sprint
    that is not structural, and therefore the one that gets a direct test.
    """

    __tablename__ = "login_challenges"
    __table_args__ = (
        # One live challenge per scope: a second SUPERSEDES the first rather
        # than sitting beside it with its own fresh attempt budget, which would
        # make the attempt cap meaningless.
        UniqueConstraint(
            "email_hash", "purpose", "plane", name="uq_login_challenges_scope"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email_hash: Mapped[str] = mapped_column(String(64), index=True)
    purpose: Mapped[str] = mapped_column(String(16))    # signup | login
    plane: Mapped[str] = mapped_column(String(16))      # candidate | org | admin
    code_hash: Mapped[str] = mapped_column(String(64))
    # Signup-only data that must survive the OTP round trip (today: the
    # organization name). Never read on a `login` purpose.
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
