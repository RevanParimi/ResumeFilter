"""Auth persistence (S8.2): sessions, login challenges, org users, operators.

All SQL for the four tables lives here; the service above holds the policy and
the routes above that hold nothing at all. Datetimes are normalized with
``as_utc`` on write because SQLite drops tzinfo on refetch -- the S3.1 lesson,
where an IST-written revocation would otherwise land 5.5 hours late and open a
fail-open window.

Nothing in this module reads a wall clock: every method that needs "now" takes
``at``. That is what keeps the whole login path reproducible offline.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth import sessions as session_logic
from app.auth.challenges import ChallengeScope
from app.auth.models import (
    AdminUserRow, AuthSessionRow, LoginChallengeRow, OrgUserRow,
)
from app.auth.schema import (
    AdminUser, OrgUser, OrgUserRole, PrincipalKind, ResolvedSession,
    SessionStatus, SessionView,
)
from app.core.config import Settings, get_settings
from app.ledger.consent import as_utc
from app.ledger.models import OrganizationRow

#: Which nullable FK column carries the principal for each plane.
_PRINCIPAL_COLUMN = {
    PrincipalKind.CANDIDATE: "candidate_id",
    PrincipalKind.ORG: "org_user_id",
    PrincipalKind.ADMIN: "admin_user_id",
}


def _org_user(row: OrgUserRow) -> OrgUser:
    return OrgUser(
        id=row.id,
        organization_id=row.organization_id,
        email_hash=row.email_hash,
        role=OrgUserRole(row.role),
        created_at=as_utc(row.created_at),
        disabled_at=as_utc(row.disabled_at) if row.disabled_at else None,
    )


def _admin_user(row: AdminUserRow) -> AdminUser:
    return AdminUser(
        id=row.id,
        email_hash=row.email_hash,
        label=row.label or "",
        created_at=as_utc(row.created_at),
        disabled_at=as_utc(row.disabled_at) if row.disabled_at else None,
    )


class OrgNameTaken(Exception):
    """Signup named an organization that already exists."""


class AuthStore:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        ledger=None,
        settings: Optional[Settings] = None,
    ) -> None:
        self._session_factory = session_factory
        self._ledger = ledger
        self._settings = settings or get_settings()

    def _audit_candidate(
        self, session: Session, *, action: str, entity_id: str, candidate_id: str
    ) -> None:
        """Audit in the SAME transaction as the write (the LedgerStore rule), so
        an outcome can never exist without its trail.

        Only candidate-subject events are written: `audit_log` is candidate-
        scoped by design, so an org-user or operator login has no subject to
        attribute the row to. Those are structured-logged instead, and widening
        the table is a recorded follow-up rather than a silent omission.
        """
        if self._ledger is None:
            return
        self._ledger._audit(
            session,
            actor_type="candidate",
            actor_id=candidate_id,
            action=action,
            entity_type="auth_session",
            entity_id=entity_id,
            candidate_id=candidate_id,
        )

    # -- sessions ------------------------------------------------------------

    def _status_of(self, row: AuthSessionRow, at: datetime) -> SessionStatus:
        return session_logic.effective_status(
            expires_at=row.expires_at,
            last_seen_at=row.last_seen_at,
            revoked_at=row.revoked_at,
            idle_timeout_minutes=self._settings.session_idle_timeout_minutes,
            at=at,
        )

    def _view(
        self, row: AuthSessionRow, at: datetime, current_id: Optional[str] = None
    ) -> SessionView:
        return SessionView(
            id=row.id,
            issued_at=as_utc(row.issued_at),
            expires_at=as_utc(row.expires_at),
            last_seen_at=as_utc(row.last_seen_at),
            status=self._status_of(row, at),
            user_agent=row.user_agent,
            current=(current_id is not None and row.id == current_id),
        )

    def create_session(
        self,
        *,
        kind: PrincipalKind,
        subject_id: str,
        csrf_token: str,
        at: datetime,
        user_agent: Optional[str] = None,
        ip_hash: Optional[str] = None,
    ) -> tuple[str, SessionView]:
        """Mint a session and return (PLAINTEXT token, view).

        The plaintext is returned exactly once and never stored -- only its
        sha256 -- mirroring ``CandidateStore.issue_access_key``.

        ``subject_id`` is the ORG_USER id for the org plane, not the org id: a
        session belongs to a person, and the org is derived from them.
        """
        raw = session_logic.generate_token(self._settings.session_token_bytes)
        issued = as_utc(at)
        row = AuthSessionRow(
            token_hash=session_logic.hash_token(raw),
            issued_at=issued,
            expires_at=issued + timedelta(minutes=self._settings.session_ttl_minutes),
            last_seen_at=issued,
            csrf_token=csrf_token,
            user_agent=user_agent,
            ip_hash=ip_hash,
            **{_PRINCIPAL_COLUMN[kind]: subject_id},
        )
        with self._session_factory() as session:
            session.add(row)
            session.flush()
            if kind == PrincipalKind.CANDIDATE:
                self._audit_candidate(
                    session,
                    action="auth.session.create",
                    entity_id=row.id,
                    candidate_id=subject_id,
                )
            session.commit()
            return raw, self._view(row, at, current_id=row.id)

    def session_by_token(self, raw: str, *, at: datetime) -> Optional[ResolvedSession]:
        """Resolve a plaintext token. None when no such session exists -- which
        includes the erased-principal case, since the row CASCADEd away."""
        if not (raw or "").strip():
            return None
        digest = session_logic.hash_token(raw)
        with self._session_factory() as session:
            row = session.execute(
                select(AuthSessionRow).where(AuthSessionRow.token_hash == digest)
            ).scalars().first()
            if row is None:
                return None
            return ResolvedSession(
                id=row.id,
                status=self._status_of(row, at),
                candidate_id=row.candidate_id,
                org_user_id=row.org_user_id,
                admin_user_id=row.admin_user_id,
                csrf_token=row.csrf_token or "",
                last_seen_at=as_utc(row.last_seen_at),
            )

    def touch(self, session_id: str, *, at: datetime) -> None:
        """Advance the idle clock, but only when it is stale enough to be worth
        a write (see sessions.should_write_last_seen -- the naive version is a
        row lock plus a WAL entry on every authenticated request)."""
        with self._session_factory() as session:
            row = session.get(AuthSessionRow, session_id)
            if row is None:
                return
            if not session_logic.should_write_last_seen(
                row.last_seen_at,
                self._settings.session_last_seen_write_seconds,
                at=at,
            ):
                return
            row.last_seen_at = as_utc(at)
            session.commit()

    def revoke(self, session_id: str, *, at: datetime) -> bool:
        """True when this call did the revoking. Already-revoked returns False
        so a caller can tell 'I closed it' from 'it was already closed'."""
        with self._session_factory() as session:
            row = session.get(AuthSessionRow, session_id)
            if row is None or row.revoked_at is not None:
                return False
            row.revoked_at = as_utc(at)
            session.commit()
            return True

    def revoke_owned(
        self, session_id: str, *, kind: PrincipalKind, subject_id: str, at: datetime
    ) -> bool:
        """Revoke only if this principal owns the session.

        Ownership is enforced HERE rather than in the route, so every entry
        point inherits it -- the rule this sprint exists to make structural.
        """
        with self._session_factory() as session:
            row = session.get(AuthSessionRow, session_id)
            if row is None:
                return False
            if getattr(row, _PRINCIPAL_COLUMN[kind]) != subject_id:
                return False        # not owned -> indistinguishable from absent
            if row.revoked_at is not None:
                return False
            row.revoked_at = as_utc(at)
            if row.candidate_id:
                self._audit_candidate(
                    session,
                    action="auth.session.revoke",
                    entity_id=row.id,
                    candidate_id=row.candidate_id,
                )
            session.commit()
            return True

    def sessions_for(
        self,
        *,
        kind: PrincipalKind,
        subject_id: str,
        at: datetime,
        current_id: Optional[str] = None,
    ) -> list[SessionView]:
        """This principal's LIVE sessions, newest first. Dead ones are omitted:
        a device list is for revoking things, and listing corpses invites
        someone to 'revoke' a session that already ended."""
        column = getattr(AuthSessionRow, _PRINCIPAL_COLUMN[kind])
        with self._session_factory() as session:
            rows = session.execute(
                select(AuthSessionRow)
                .where(column == subject_id)
                .order_by(AuthSessionRow.issued_at.desc())
            ).scalars().all()
            return [
                self._view(row, at, current_id=current_id)
                for row in rows
                if self._status_of(row, at) == SessionStatus.ACTIVE
            ]

    # -- login challenges ----------------------------------------------------

    @staticmethod
    def _scope_filter(scope: ChallengeScope):
        return (
            (LoginChallengeRow.email_hash == scope.email_hash)
            & (LoginChallengeRow.purpose == str(scope.purpose))
            & (LoginChallengeRow.plane == str(scope.plane))
        )

    def upsert_challenge(
        self,
        scope: ChallengeScope,
        *,
        code_hash: str,
        expires_at: datetime,
        payload: dict,
        at: datetime,
    ) -> None:
        """Supersede any live challenge for this scope.

        Delete-then-insert rather than update, so a resend resets ``attempts``
        WITH the code. Leaving the old budget in place beside a new code would
        make the attempt cap decorative.
        """
        with self._session_factory() as session:
            session.execute(delete(LoginChallengeRow).where(self._scope_filter(scope)))
            session.add(
                LoginChallengeRow(
                    email_hash=scope.email_hash,
                    purpose=str(scope.purpose),
                    plane=str(scope.plane),
                    code_hash=code_hash,
                    payload=dict(payload or {}),
                    created_at=as_utc(at),
                    expires_at=as_utc(expires_at),
                    attempts=0,
                    last_sent_at=as_utc(at),
                )
            )
            session.commit()

    def get_challenge(self, scope: ChallengeScope) -> Optional[LoginChallengeRow]:
        with self._session_factory() as session:
            return session.execute(
                select(LoginChallengeRow).where(self._scope_filter(scope))
            ).scalars().first()

    def bump_attempts(self, scope: ChallengeScope) -> None:
        with self._session_factory() as session:
            row = session.execute(
                select(LoginChallengeRow).where(self._scope_filter(scope))
            ).scalars().first()
            if row is None:
                return
            row.attempts = (row.attempts or 0) + 1
            session.commit()

    def delete_challenge(self, scope: ChallengeScope) -> None:
        """Consume it. Short-TTL secret material is deleted on paths that
        already run -- hygiene, not a retention policy (the S7.1 precedent)."""
        with self._session_factory() as session:
            session.execute(delete(LoginChallengeRow).where(self._scope_filter(scope)))
            session.commit()

    def delete_challenges_for_email(self, email_hash: str) -> int:
        """Every purpose and every plane. The erasure path calls this because
        login_challenges has no FK and therefore cannot cascade."""
        if not email_hash:
            return 0
        with self._session_factory() as session:
            result = session.execute(
                delete(LoginChallengeRow).where(
                    LoginChallengeRow.email_hash == email_hash
                )
            )
            session.commit()
            return int(result.rowcount or 0)

    def purge_expired_for_email(self, email_hash: str, *, at: datetime) -> None:
        """Opportunistic hygiene on a path that already runs, so abandoned
        challenges do not accumulate without inventing a scheduler."""
        with self._session_factory() as session:
            session.execute(
                delete(LoginChallengeRow).where(
                    (LoginChallengeRow.email_hash == email_hash)
                    & (LoginChallengeRow.expires_at <= as_utc(at))
                )
            )
            session.commit()

    # -- org users -----------------------------------------------------------

    def create_org_user(
        self, *, organization_id: str, email_hash: str, role: OrgUserRole
    ) -> OrgUser:
        with self._session_factory() as session:
            row = OrgUserRow(
                organization_id=organization_id,
                email_hash=email_hash,
                role=str(role),
            )
            session.add(row)
            session.commit()
            return _org_user(row)

    def create_org_with_owner(
        self, *, name: str, email_hash: str
    ) -> tuple[str, OrgUser]:
        """Create the organization AND its first owner in ONE transaction.

        Atomicity is the point: an org that exists with nobody able to log into
        it can only be fixed by an operator, which is exactly the hand-holding
        self-onboarding is meant to remove. Either both rows land or neither
        does, so a failed signup leaves nothing behind to collide with a retry.
        """
        from app.ledger.models import OrganizationRow  # local: avoids a cycle

        with self._session_factory() as session:
            org = OrganizationRow(name=name)
            session.add(org)
            try:
                session.flush()
            except IntegrityError as exc:
                session.rollback()
                raise OrgNameTaken(
                    f"organization name already exists: {name!r}"
                ) from exc
            user = OrgUserRow(
                organization_id=org.id,
                email_hash=email_hash,
                role=str(OrgUserRole.OWNER),
            )
            session.add(user)
            session.commit()
            return org.id, _org_user(user)

    def organization_name_exists(self, name: str) -> bool:
        """Is this organization name already taken?

        Used to refuse a signup BEFORE a code is sent (S8.4 §2.1). This leaks
        nothing: org names are not secret, and the uniqueness constraint
        already discloses the same fact to anyone who completes a signup. The
        property that IS protected -- whether an email address has an account
        -- is untouched, because this never looks at the address.
        """
        with self._session_factory() as session:
            return session.execute(
                select(OrganizationRow.id)
                # lower(), matching uq_organizations_name_ci EXACTLY. A check
                # stricter or looser than its constraint is how the Phase A
                # lockout comes back: the check refuses, the insert succeeds
                # anyway, and two orgs share one name.
                .where(func.lower(OrganizationRow.name) == name.strip().lower())
                .limit(1)
            ).scalars().first() is not None

    def org_user_by_email(self, email_hash: str) -> Optional[OrgUser]:
        """Enabled org users only -- a disabled row must not authenticate.

        Ordered by `created_at` because the schema permits ONE address to hold
        a login at two organizations (uniqueness is per-org, so a consultant at
        two client firms is legal). No code path creates that state today --
        there are no invites in S8.2 -- but an unordered `.first()` is
        implementation-defined on Postgres, so this would become a login that
        silently lands in a different org depending on the plan the optimizer
        chose. Deterministic now; see AUTH.md section 9 for the real fix when
        invites land.
        """
        if not email_hash:
            return None
        with self._session_factory() as session:
            row = session.execute(
                select(OrgUserRow)
                .where(
                    (OrgUserRow.email_hash == email_hash)
                    & (OrgUserRow.disabled_at.is_(None))
                )
                .order_by(OrgUserRow.created_at, OrgUserRow.id)
            ).scalars().first()
            return _org_user(row) if row else None

    def org_user_by_id(self, org_user_id: str) -> Optional[OrgUser]:
        with self._session_factory() as session:
            row = session.get(OrgUserRow, org_user_id)
            if row is None or row.disabled_at is not None:
                return None
            return _org_user(row)

    def disable_org_user(self, org_user_id: str, *, at: Optional[datetime] = None) -> bool:
        with self._session_factory() as session:
            row = session.get(OrgUserRow, org_user_id)
            if row is None:
                return False
            row.disabled_at = as_utc(at) if at else datetime.now().astimezone()
            session.commit()
            return True

    # -- operators -----------------------------------------------------------

    def create_admin_user(self, *, email_hash: str, label: str = "") -> AdminUser:
        with self._session_factory() as session:
            row = AdminUserRow(email_hash=email_hash, label=label or "")
            session.add(row)
            session.commit()
            return _admin_user(row)

    def admin_user_by_email(self, email_hash: str) -> Optional[AdminUser]:
        if not email_hash:
            return None
        with self._session_factory() as session:
            # email_hash is UNIQUE on admin_users, so at most one row can
            # match; the ordering is belt-and-braces against a future migration
            # relaxing that constraint.
            row = session.execute(
                select(AdminUserRow)
                .where(
                    (AdminUserRow.email_hash == email_hash)
                    & (AdminUserRow.disabled_at.is_(None))
                )
                .order_by(AdminUserRow.created_at, AdminUserRow.id)
            ).scalars().first()
            return _admin_user(row) if row else None

    def admin_user_by_id(self, admin_user_id: str) -> Optional[AdminUser]:
        with self._session_factory() as session:
            row = session.get(AdminUserRow, admin_user_id)
            if row is None or row.disabled_at is not None:
                return None
            return _admin_user(row)

    def list_admin_users(self) -> list[AdminUser]:
        with self._session_factory() as session:
            rows = session.execute(
                select(AdminUserRow).order_by(AdminUserRow.created_at)
            ).scalars().all()
            return [_admin_user(r) for r in rows]

    def delete_admin_user(self, admin_user_id: str) -> bool:
        """A hard delete: their sessions CASCADE away with them."""
        with self._session_factory() as session:
            row = session.get(AdminUserRow, admin_user_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    def disable_admin_user(
        self, admin_user_id: str, *, at: Optional[datetime] = None
    ) -> bool:
        """Softer than delete: the operator stops authenticating but the audit
        trail that names them keeps resolving."""
        with self._session_factory() as session:
            row = session.get(AdminUserRow, admin_user_id)
            if row is None:
                return False
            row.disabled_at = as_utc(at) if at else datetime.now().astimezone()
            session.commit()
            return True
