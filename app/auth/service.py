"""AuthService (S8.2) -- signup, login, and the ONE resolver per plane.

Every gate lives here rather than on a route. That is not style: a rule applied
at one entry point and not the other has shipped as a real defect in S7.1, S7.2
and S7.3, and sessions add a SECOND entry point to every plane in this repo.

The resolver takes raw credential VALUES, not a Request, so this module has no
FastAPI import and no HTTP vocabulary. Routes translate; the service decides.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.auth import challenges as challenge_logic
from app.auth import csrf as csrf_logic
from app.auth.challenges import ChallengeScope, VerifyOutcome
from app.auth.schema import (
    AuthPlane, LoginPurpose, OrgUserRole, Principal, PrincipalKind, PrincipalVia,
    SessionStatus, SessionView,
)
from app.auth.store import AuthStore, OrgNameTaken
from app.candidates.hashing import contact_hash, normalize_email
from app.candidates.store import CandidateStore
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ledger.store import LedgerStore
from app.services.email import EmailClient, EmailSendFailed, EmailUnavailable

log = get_logger(__name__)

#: Which plane a PrincipalKind logs in through. They are 1:1 today and the map
#: exists so a future plane cannot silently reuse another plane's challenges.
_PLANE_FOR_KIND = {
    PrincipalKind.CANDIDATE: AuthPlane.CANDIDATE,
    PrincipalKind.ORG: AuthPlane.ORG,
    PrincipalKind.ADMIN: AuthPlane.ADMIN,
}
_KIND_FOR_PLANE = {plane: kind for kind, plane in _PLANE_FOR_KIND.items()}


class AuthError(Exception):
    """Base for the service's refusals."""


class EmailUnavailableError(AuthError):
    """No email provider configured -- the caller returns 503, never a fake 202
    that leaves someone waiting for a code that will never arrive."""


class ChallengeRefused(AuthError):
    """A code could not be issued or redeemed.

    Carries `reason` for logging and for the cooldown case, which the HTTP layer
    treats differently. It deliberately carries NOTHING that distinguishes
    expired from wrong from exhausted to a caller who did not already know --
    that distinction is a brute-forcing oracle.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AuthService:
    def __init__(
        self,
        store: AuthStore,
        candidates: CandidateStore,
        ledger: LedgerStore,
        *,
        email: EmailClient,
        settings: Optional[Settings] = None,
    ) -> None:
        self._store = store
        self._candidates = candidates
        self._ledger = ledger
        self._email = email
        self._settings = settings or get_settings()

    # -- helpers -------------------------------------------------------------

    def _hash_email(self, email: str) -> str:
        """The SAME salted function that wrote `candidates.email_hash`.

        If this ever diverges, the claim in `_principal_for_candidate` silently
        stops matching and every self-registration forks a duplicate person --
        a failure with no error and no log line, so it is worth stating here.
        """
        return contact_hash(
            normalize_email(email or ""), self._settings.contact_hash_salt
        )

    @staticmethod
    def _scope_purpose(plane: AuthPlane, purpose: LoginPurpose) -> LoginPurpose:
        """The purpose a CHALLENGE is filed under.

        On the candidate plane signup and login are the same act, so they must
        share ONE scope. Filing them separately let two live challenges exist
        for one address, and `verify_code` checked signup first -- so an
        unauthenticated attacker could request a signup code for any candidate's
        address and SHADOW that person's real login code until it expired.
        Reproduced before this existed; regression-tested in
        test_auth_service.py::test_a_stale_signup_challenge_cannot_shadow_a_login.
        """
        return LoginPurpose.LOGIN if plane == AuthPlane.CANDIDATE else purpose

    def _subject_exists(self, plane: AuthPlane, email_hash: str) -> bool:
        if plane == AuthPlane.ORG:
            return self._store.org_user_by_email(email_hash) is not None
        if plane == AuthPlane.ADMIN:
            return self._store.admin_user_by_email(email_hash) is not None
        return self._candidates.find_by_email_hash(email_hash) is not None

    # -- issuing a code ------------------------------------------------------

    def request_code(
        self,
        *,
        email: str,
        plane: AuthPlane,
        purpose: LoginPurpose,
        payload: Optional[dict] = None,
        at: datetime,
        rng: Optional[random.Random] = None,
    ) -> bool:
        """Mint and send a login code. Returns True when one was actually sent.

        Returns False -- WITHOUT raising -- when there is deliberately nothing
        to send:
          * login for an address with no account, and
          * signup for an address that already has one.
        The HTTP layer answers 202 either way, so neither case is distinguishable
        from success. An endpoint that reveals which addresses are registered is
        an enumeration oracle, and this is the only place that decision is made.

        Signup on a taken address deliberately does NOT quietly send a login
        code instead: silently changing what the caller asked for is how
        confused-deputy bugs start.
        """
        # Probe the provider FIRST, before any account lookup. Otherwise a
        # broken provider answers 503 for an address that exists and 202 for one
        # that does not -- an enumeration oracle that appears only when email is
        # misconfigured, which is exactly when nobody is watching for it.
        if not self._email.available:
            raise EmailUnavailableError(
                "no email provider is configured; set email_provider=smtp"
            )

        email_hash = self._hash_email(email)
        scope = ChallengeScope(
            email_hash=email_hash,
            purpose=self._scope_purpose(plane, purpose),
            plane=plane,
        )

        # Opportunistic hygiene on a path that already runs -- no scheduler.
        self._store.purge_expired_for_email(email_hash, at=at)

        # On the CANDIDATE plane, signup and login are the SAME act and both
        # always send.
        #
        # A candidates row is not an account. Most of them were created by an
        # org uploading a resume, about a person who has never touched this
        # system -- so "a record exists" says nothing about whether they have
        # signed up, and refusing signup on that basis makes decision 0.4's
        # claim UNREACHABLE in precisely the case it exists for. (Caught by
        # scripts/smoke_s82.py, which is the only place the org-upload-then-
        # candidate-signup sequence is exercised end to end.)
        #
        # Treating the two purposes identically here also removes the
        # enumeration difference outright on the plane with the most people in
        # it: every address gets the same answer and the same email.
        if plane != AuthPlane.CANDIDATE:
            exists = self._subject_exists(plane, email_hash)
            if purpose == LoginPurpose.LOGIN and not exists:
                log.info(
                    "auth.request_code.noop", plane=str(plane), reason="no_account"
                )
                return False
            if purpose == LoginPurpose.SIGNUP and exists:
                log.info(
                    "auth.request_code.noop", plane=str(plane), reason="already_exists"
                )
                return False
            if purpose == LoginPurpose.SIGNUP and plane == AuthPlane.ADMIN:
                # Operators are created BY an operator; there is no admin signup.
                log.info(
                    "auth.request_code.noop", plane="admin", reason="no_admin_signup"
                )
                return False

        existing = self._store.get_challenge(scope)
        if existing is not None and not challenge_logic.may_send(
            last_sent_at=existing.last_sent_at,
            cooldown_seconds=self._settings.login_otp_cooldown_seconds,
            at=at,
        ):
            # The previously sent code is still live and still in their inbox,
            # so refusing costs the user nothing.
            raise ChallengeRefused("cooldown")

        code, digest = challenge_logic.mint_code(
            self._settings.login_otp_length,
            salt=self._settings.contact_hash_salt,
            rng=rng or random.Random(),
        )

        # SEND FIRST, persist second. A provider outage must not consume or
        # supersede anything: a retry has to be free, so an SMTP failure never
        # costs someone their login.
        try:
            self._email.send(
                to=normalize_email(email),
                subject="Your veritas sign-in code",
                body=(
                    f"Your sign-in code is {code}\n\n"
                    f"It expires in {self._settings.login_otp_ttl_seconds // 60} "
                    "minutes. If you did not request it, ignore this message."
                ),
            )
        except EmailUnavailable as exc:
            raise EmailUnavailableError(str(exc)) from exc
        except EmailSendFailed as exc:
            raise ChallengeRefused("send_failed") from exc

        self._store.upsert_challenge(
            scope,
            code_hash=digest,
            expires_at=at + timedelta(seconds=self._settings.login_otp_ttl_seconds),
            payload=payload or {},
            at=at,
        )
        return True

    # -- redeeming a code ----------------------------------------------------

    def _live_scopes(
        self, email_hash: str, plane: AuthPlane, purpose: Optional[LoginPurpose]
    ) -> list[tuple[ChallengeScope, object]]:
        """EVERY live challenge for this address on this plane, not just the
        first.

        Returning only the first let one scope SHADOW another: a stale signup
        challenge was checked before the login challenge, so a correct login
        code was evaluated against the wrong hash and refused. `_scope_purpose`
        now collapses the candidate plane to one scope so this cannot arise
        there, and returning all of them keeps it from arising anywhere else.
        """
        purposes = (
            [self._scope_purpose(plane, purpose)] if purpose is not None
            else [LoginPurpose.SIGNUP, LoginPurpose.LOGIN]
        )
        found = []
        for candidate_purpose in dict.fromkeys(purposes):   # de-dup, keep order
            scope = ChallengeScope(
                email_hash=email_hash, purpose=candidate_purpose, plane=plane
            )
            row = self._store.get_challenge(scope)
            if row is not None:
                found.append((scope, row))
        return found

    def verify_code(
        self,
        *,
        email: str,
        plane: AuthPlane,
        code: str,
        at: datetime,
        purpose: Optional[LoginPurpose] = None,
        user_agent: Optional[str] = None,
        ip_hash: Optional[str] = None,
    ) -> tuple[str, str, Principal]:
        """Redeem a code and issue a session. Returns (token, csrf, principal)."""
        email_hash = self._hash_email(email)
        live = self._live_scopes(email_hash, plane, purpose)
        if not live:
            raise ChallengeRefused("not_found")

        supplied = challenge_logic.hash_supplied(
            code, salt=self._settings.contact_hash_salt
        )
        # Evaluate EVERY live challenge before refusing. Accepting the first
        # match -- rather than the first challenge -- is what stops one scope
        # shadowing another and locking a real user out with a correct code.
        outcomes = [
            (
                scope,
                row,
                challenge_logic.evaluate_verification(
                    stored_hash=row.code_hash,
                    supplied_hash=supplied,
                    expires_at=row.expires_at,
                    attempts=row.attempts or 0,
                    max_attempts=self._settings.login_otp_max_attempts,
                    at=at,
                ),
            )
            for scope, row in live
        ]
        winner = next(
            ((s, r) for s, r, o in outcomes if o == VerifyOutcome.OK), None
        )
        if winner is None:
            # Only now is this a real failure, so only now does it cost an
            # attempt -- and only on the challenges the code was actually
            # wrong for, never on one that was merely expired or exhausted.
            for scope, _, outcome in outcomes:
                if outcome == VerifyOutcome.WRONG_CODE:
                    self._store.bump_attempts(scope)
            raise ChallengeRefused(str(outcomes[0][2]))
        scope, row = winner

        # Consume BEFORE minting the session: a code is single-use, and a crash
        # after this point costs a login rather than leaving a reusable code.
        payload = dict(row.payload or {})
        self._store.delete_challenge(scope)

        principal_kind = _KIND_FOR_PLANE[plane]
        subject_id, principal = self._establish(
            plane=plane, email_hash=email_hash, payload=payload, purpose=scope.purpose
        )

        csrf_token = csrf_logic.generate_csrf_token(self._settings.csrf_token_bytes)
        token, view = self._store.create_session(
            kind=principal_kind,
            subject_id=subject_id,
            csrf_token=csrf_token,
            at=at,
            user_agent=user_agent,
            ip_hash=ip_hash,
        )
        return token, csrf_token, principal.model_copy(
            update={"session_id": view.id}
        )

    def _establish(
        self,
        *,
        plane: AuthPlane,
        email_hash: str,
        payload: dict,
        purpose: LoginPurpose,
    ) -> tuple[str, Principal]:
        """Resolve (or create) the principal this verified address belongs to.

        Returns (session subject id, principal). For the org plane the subject
        is the ORG_USER, not the org: a session belongs to a person.
        """
        if plane == AuthPlane.ORG:
            user = self._store.org_user_by_email(email_hash)
            if user is None:
                name = (payload.get("organization_name") or "").strip()
                if not name:
                    raise ChallengeRefused("missing_organization_name")
                try:
                    org_id, user = self._store.create_org_with_owner(
                        name=name, email_hash=email_hash
                    )
                except OrgNameTaken as exc:
                    raise ChallengeRefused("org_name_taken") from exc
            return user.id, Principal(
                kind=PrincipalKind.ORG,
                via=PrincipalVia.SESSION,
                org_id=user.organization_id,
                org_user_id=user.id,
            )

        if plane == AuthPlane.ADMIN:
            admin = self._store.admin_user_by_email(email_hash)
            if admin is None:
                # There is no admin signup. Reachable only by racing an operator
                # deletion between request_code and verify_code.
                raise ChallengeRefused("no_such_operator")
            return admin.id, Principal(
                kind=PrincipalKind.ADMIN,
                via=PrincipalVia.SESSION,
                admin_user_id=admin.id,
            )

        # -- candidate: THE CLAIM (spec 6.2, decision 0.4) --------------------
        # A verified mailbox connects the data principal to the record built
        # about them from a resume someone else uploaded. Refusing to link would
        # make the portal's access, correction and erasure rights unreachable
        # for every candidate an org ever uploaded -- which is all of them.
        #
        # Same trust boundary as S7.1's L2 otp_email, and the same one as every
        # OTP login on the internet. Stated rather than buried because the blast
        # radius here is a full depth report, not a mailing list.
        #
        # It grants NO identity assurance: logging in is not being verified, and
        # fusing the two would repeat S7.2's two-ladders mistake.
        candidate_id = self._candidates.find_by_email_hash(email_hash)
        if candidate_id is None:
            candidate_id = self._candidates.create_bare_candidate(
                email_hash=email_hash
            )
            log.info("auth.candidate.created", purpose=str(purpose))
        else:
            log.info("auth.candidate.claimed", purpose=str(purpose))
        return candidate_id, Principal(
            kind=PrincipalKind.CANDIDATE,
            via=PrincipalVia.SESSION,
            candidate_id=candidate_id,
        )

    # -- resolving a principal ----------------------------------------------

    def resolve(
        self,
        *,
        kind: PrincipalKind,
        session_token: Optional[str],
        header_key: Optional[str],
        at: Optional[datetime] = None,
    ) -> Optional[Principal]:
        """THE resolver. Session cookie first, then the plane's header key.

        Returns None when neither establishes a principal; the caller turns that
        into a 401. Nothing downstream can tell which credential was used except
        by reading `Principal.via` -- which is exactly what CSRF must do.
        """
        at = at or datetime.now(timezone.utc)
        principal = self._from_session(kind=kind, token=session_token, at=at)
        if principal is not None:
            return principal
        return self._from_key(kind=kind, key=header_key)

    def _from_session(
        self, *, kind: PrincipalKind, token: Optional[str], at: datetime
    ) -> Optional[Principal]:
        if not token:
            return None
        resolved = self._store.session_by_token(token, at=at)
        if resolved is None or resolved.status != SessionStatus.ACTIVE:
            return None

        if kind == PrincipalKind.CANDIDATE:
            if not resolved.candidate_id:
                return None      # kind is checked, not merely presence
            self._store.touch(resolved.id, at=at)
            return Principal(
                kind=kind, via=PrincipalVia.SESSION,
                candidate_id=resolved.candidate_id, session_id=resolved.id,
            )
        if kind == PrincipalKind.ORG:
            if not resolved.org_user_id:
                return None
            user = self._store.org_user_by_id(resolved.org_user_id)
            if user is None:
                return None      # disabled between requests
            self._store.touch(resolved.id, at=at)
            return Principal(
                kind=kind, via=PrincipalVia.SESSION, org_id=user.organization_id,
                org_user_id=user.id, session_id=resolved.id,
            )
        if not resolved.admin_user_id:
            return None
        admin = self._store.admin_user_by_id(resolved.admin_user_id)
        if admin is None:
            return None
        self._store.touch(resolved.id, at=at)
        return Principal(
            kind=kind, via=PrincipalVia.SESSION, admin_user_id=admin.id,
            session_id=resolved.id,
        )

    def _from_key(
        self, *, kind: PrincipalKind, key: Optional[str]
    ) -> Optional[Principal]:
        if kind == PrincipalKind.ADMIN:
            expected = self._settings.api_auth_key.get_secret_value()
            # Fail-CLOSED (S8.1): an unset credential is the MOST refusing
            # state. No knob restores the old behaviour.
            import hmac

            if not expected or not hmac.compare_digest(key or "", expected):
                return None
            # admin_user_id stays None: the shared secret is a machine, not a
            # person, and that difference is what makes attribution possible.
            return Principal(kind=kind, via=PrincipalVia.KEY)

        if kind == PrincipalKind.ORG:
            org_id = self._ledger.authenticate_org(key or "")
            if org_id is None:
                return None
            return Principal(kind=kind, via=PrincipalVia.KEY, org_id=org_id)

        candidate_id = self._candidates.authenticate_candidate(key or "")
        if candidate_id is None:
            return None
        return Principal(kind=kind, via=PrincipalVia.KEY, candidate_id=candidate_id)

    def resolve_any(
        self, *, session_token: Optional[str], at: Optional[datetime] = None
    ) -> Optional[Principal]:
        """Any principal, SESSION only -- for the cross-plane session-lifecycle
        routes. A header key has no session to list or revoke, so it resolves to
        nothing here rather than to something that pretends to work."""
        at = at or datetime.now(timezone.utc)
        for kind in (PrincipalKind.CANDIDATE, PrincipalKind.ORG, PrincipalKind.ADMIN):
            principal = self._from_session(kind=kind, token=session_token, at=at)
            if principal is not None:
                return principal
        return None

    # -- session lifecycle ---------------------------------------------------

    @staticmethod
    def _subject_of(principal: Principal) -> Optional[str]:
        return (
            principal.candidate_id
            or principal.org_user_id
            or principal.admin_user_id
        )

    def logout(self, principal: Principal, *, at: Optional[datetime] = None) -> bool:
        if not principal.session_id:
            return False
        return self._store.revoke(
            principal.session_id, at=at or datetime.now(timezone.utc)
        )

    def sessions_for(
        self, principal: Principal, *, at: Optional[datetime] = None
    ) -> list[SessionView]:
        subject = self._subject_of(principal)
        if subject is None:
            return []
        return self._store.sessions_for(
            kind=principal.kind,
            subject_id=subject,
            at=at or datetime.now(timezone.utc),
            current_id=principal.session_id,
        )

    def revoke_session(
        self, principal: Principal, session_id: str, *, at: Optional[datetime] = None
    ) -> bool:
        """False when unknown OR not owned -- the caller returns the same 404 for
        both, so a session id cannot be probed (the S6.4 rule)."""
        subject = self._subject_of(principal)
        if subject is None:
            return False
        return self._store.revoke_owned(
            session_id,
            kind=principal.kind,
            subject_id=subject,
            at=at or datetime.now(timezone.utc),
        )

    # -- operator accounts ---------------------------------------------------
    # Thin pass-throughs so the route layer never reaches into the store. The
    # admin plane is the one place a human account is created rather than
    # self-registered, and keeping it behind the service means the hashing rule
    # (_hash_email) can never drift between here and login.

    def hash_email(self, email: str) -> str:
        return self._hash_email(email)

    def organization_name_available(self, name: str) -> bool:
        """True when `name` is free. Routes talk to the service, not the store."""
        return not self._store.organization_name_exists(name)

    def find_admin_user(self, email_hash: str):
        return self._store.admin_user_by_email(email_hash)

    def create_admin_user(self, *, email_hash: str, label: str = ""):
        return self._store.create_admin_user(email_hash=email_hash, label=label)

    def list_admin_users(self):
        return self._store.list_admin_users()

    def delete_admin_user(self, admin_user_id: str) -> bool:
        return self._store.delete_admin_user(admin_user_id)

    def erase_login_state(self, candidate_id: str) -> int:
        """Delete every login challenge for this candidate's address.

        Sessions CASCADE with the candidate row; login_challenges cannot,
        because they carry no FK (at signup time no principal exists). This
        lives on the SERVICE so both erasure entry points -- the portal and the
        admin plane -- inherit it, rather than each remembering a line.
        """
        email_hash = self._candidates.email_hash_for(candidate_id)
        if not email_hash:
            return 0
        return self._store.delete_challenges_for_email(email_hash)


def build_auth_service(
    settings: Optional[Settings] = None,
    *,
    candidates: CandidateStore,
    ledger: LedgerStore,
    email: Optional[EmailClient] = None,
) -> AuthService:
    from app.services.email import build_email

    settings = settings or get_settings()
    store = AuthStore(candidates._session_factory, ledger=ledger, settings=settings)
    return AuthService(
        store,
        candidates,
        ledger,
        email=email or build_email(settings),
        settings=settings,
    )
