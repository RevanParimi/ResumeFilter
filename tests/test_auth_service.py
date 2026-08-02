"""AuthService: signup, login, the claim, and the resolvers (S8.2).

Every clock is injected. CaptureEmail makes the whole OTP path deterministic
with no network and no provider.
"""

from __future__ import annotations

import json
import random
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.schema import (
    AuthPlane, LoginPurpose, PrincipalKind, PrincipalVia,
)
from app.auth.service import (
    AuthService, ChallengeRefused, EmailUnavailableError, build_auth_service,
)
from app.auth.store import AuthStore
from app.candidates.models import CandidateRow
from app.ledger.store import LedgerStore
from app.services.email import CaptureEmail, NullEmail
from tests.conftest import make_candidate_store

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _rng() -> random.Random:
    return random.Random(1234)


class _Fixture:
    """Bundles the service with the capture file so a test can read the code."""

    def __init__(self, service, capture_path, candidates, ledger):
        self.service = service
        self.capture_path = capture_path
        self.candidates = candidates
        self.ledger = ledger

    def code(self) -> str:
        line = json.loads(
            self.capture_path.read_text(encoding="utf-8").splitlines()[-1]
        )
        return re.search(r"\b(\d{6})\b", line["body"]).group(1)

    def sent_count(self) -> int:
        if not self.capture_path.exists():
            return 0
        return len(self.capture_path.read_text(encoding="utf-8").splitlines())


@pytest.fixture
def auth(settings, tmp_path) -> _Fixture:
    capture = tmp_path / "mail.jsonl"
    cfg = settings.model_copy(update={
        "email_provider": "capture", "email_capture_path": str(capture),
    })
    candidates = make_candidate_store()
    ledger = LedgerStore(candidates._session_factory, settings=cfg)
    service = build_auth_service(
        cfg, candidates=candidates, ledger=ledger, email=CaptureEmail(cfg)
    )
    return _Fixture(service, capture, candidates, ledger)


@pytest.fixture
def auth_no_email(settings) -> AuthService:
    candidates = make_candidate_store()
    ledger = LedgerStore(candidates._session_factory, settings=settings)
    return build_auth_service(
        settings, candidates=candidates, ledger=ledger, email=NullEmail(settings)
    )


def _existing_candidate(auth: _Fixture, email: str) -> str:
    """A candidate created the way orgs create them: from an uploaded resume,
    with only a contact hash tying them to a human."""
    email_hash = auth.service._hash_email(email)
    with auth.candidates._session_factory() as s:
        row = CandidateRow(email_hash=email_hash, full_name="Priya S")
        s.add(row)
        s.commit()
        return row.id


# ── org self-onboard ────────────────────────────────────────────────────────


def test_org_signup_then_verify_creates_an_org_and_a_session(auth):
    assert auth.service.request_code(
        email="ops@acme.in", plane=AuthPlane.ORG, purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": "Acme Staffing"}, at=NOW, rng=_rng(),
    ) is True
    token, csrf, principal = auth.service.verify_code(
        email="ops@acme.in", plane=AuthPlane.ORG, code=auth.code(), at=NOW
    )
    assert token and csrf
    assert principal.kind == PrincipalKind.ORG
    assert principal.via == PrincipalVia.SESSION
    assert principal.org_id and principal.org_user_id and principal.session_id


def test_org_signup_is_atomic_on_a_taken_name(auth):
    """Either both rows land or neither: an org nobody can log into could only
    be fixed by an operator, which is what self-onboarding exists to avoid."""
    auth.service.request_code(
        email="a@one.in", plane=AuthPlane.ORG, purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": "Acme"}, at=NOW, rng=_rng(),
    )
    auth.service.verify_code(
        email="a@one.in", plane=AuthPlane.ORG, code=auth.code(), at=NOW
    )
    auth.service.request_code(
        email="b@two.in", plane=AuthPlane.ORG, purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": "Acme"}, at=NOW, rng=_rng(),
    )
    with pytest.raises(ChallengeRefused):
        auth.service.verify_code(
            email="b@two.in", plane=AuthPlane.ORG, code=auth.code(), at=NOW
        )
    assert auth.service._store.org_user_by_email(
        auth.service._hash_email("b@two.in")
    ) is None


def test_org_login_works_after_signup(auth):
    auth.service.request_code(
        email="ops@acme.in", plane=AuthPlane.ORG, purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": "Acme"}, at=NOW, rng=_rng(),
    )
    _, _, first = auth.service.verify_code(
        email="ops@acme.in", plane=AuthPlane.ORG, code=auth.code(), at=NOW
    )
    later = NOW + timedelta(hours=2)
    assert auth.service.request_code(
        email="ops@acme.in", plane=AuthPlane.ORG, purpose=LoginPurpose.LOGIN,
        at=later, rng=_rng(),
    ) is True
    _, _, second = auth.service.verify_code(
        email="ops@acme.in", plane=AuthPlane.ORG, code=auth.code(), at=later
    )
    assert second.org_user_id == first.org_user_id
    assert second.session_id != first.session_id


# ── no enumeration ──────────────────────────────────────────────────────────


def test_org_login_for_an_unknown_address_sends_nothing(auth):
    assert auth.service.request_code(
        email="nobody@nowhere.in", plane=AuthPlane.ORG,
        purpose=LoginPurpose.LOGIN, at=NOW, rng=_rng(),
    ) is False
    assert auth.sent_count() == 0


def test_org_signup_for_a_taken_address_sends_nothing(auth):
    """And deliberately does NOT quietly send a login code instead -- silently
    changing what the caller asked for is how confused-deputy bugs start."""
    auth.service.request_code(
        email="ops@acme.in", plane=AuthPlane.ORG, purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": "Acme"}, at=NOW, rng=_rng(),
    )
    auth.service.verify_code(
        email="ops@acme.in", plane=AuthPlane.ORG, code=auth.code(), at=NOW
    )
    before = auth.sent_count()
    assert auth.service.request_code(
        email="ops@acme.in", plane=AuthPlane.ORG, purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": "Acme Again"}, at=NOW, rng=_rng(),
    ) is False
    assert auth.sent_count() == before


def test_the_candidate_plane_treats_signup_and_login_as_the_same_act(auth):
    """A candidates row is NOT an account.

    Most were created by an org uploading a resume, about someone who has never
    touched this system. Refusing signup because "a record exists" made
    decision 0.4's claim unreachable in exactly the case it exists for -- caught
    by smoke_s82, not by any unit test, which is why this one is here now.

    Treating both purposes identically also makes the plane uniform: known and
    unknown addresses get the same answer and the same email, so there is
    nothing to enumerate.
    """
    _existing_candidate(auth, "known@example.in")
    for email in ("known@example.in", "stranger@example.in"):
        for purpose in (LoginPurpose.SIGNUP, LoginPurpose.LOGIN):
            auth.service._store.delete_challenges_for_email(
                auth.service._hash_email(email)
            )
            assert auth.service.request_code(
                email=email, plane=AuthPlane.CANDIDATE, purpose=purpose,
                at=NOW, rng=_rng(),
            ) is True


def test_there_is_no_admin_signup(auth):
    assert auth.service.request_code(
        email="attacker@evil.in", plane=AuthPlane.ADMIN,
        purpose=LoginPurpose.SIGNUP, at=NOW, rng=_rng(),
    ) is False
    assert auth.sent_count() == 0


# ── the claim (decision 0.4) ────────────────────────────────────────────────


def test_candidate_signup_claims_an_existing_record(auth):
    """The sprint's most security-consequential behaviour: OTP against the
    email_hash already on file connects the data principal to the record built
    from a resume someone ELSE uploaded."""
    cid = _existing_candidate(auth, "priya@example.in")
    auth.service.request_code(
        email="priya@example.in", plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.LOGIN, at=NOW, rng=_rng(),
    )
    _, _, principal = auth.service.verify_code(
        email="priya@example.in", plane=AuthPlane.CANDIDATE, code=auth.code(), at=NOW
    )
    assert principal.candidate_id == cid       # claimed, not duplicated


def test_the_claim_normalizes_the_address(auth):
    """The resume said 'Priya@Example.in '; they type 'priya@example.in'. Both
    must hash identically or the claim silently forks a duplicate person."""
    cid = _existing_candidate(auth, "Priya@Example.in ")
    auth.service.request_code(
        email="priya@example.in", plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.LOGIN, at=NOW, rng=_rng(),
    )
    _, _, principal = auth.service.verify_code(
        email="priya@example.in", plane=AuthPlane.CANDIDATE, code=auth.code(), at=NOW
    )
    assert principal.candidate_id == cid


def test_candidate_signup_with_an_unknown_address_creates_a_bare_record(auth):
    auth.service.request_code(
        email="new@person.in", plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.SIGNUP, at=NOW, rng=_rng(),
    )
    _, _, principal = auth.service.verify_code(
        email="new@person.in", plane=AuthPlane.CANDIDATE, code=auth.code(), at=NOW
    )
    assert principal.candidate_id
    assert auth.candidates.find_by_email_hash(
        auth.service._hash_email("new@person.in")
    ) == principal.candidate_id


def test_signup_does_not_create_a_second_candidate(auth):
    """The regression this decision exists to prevent."""
    _existing_candidate(auth, "priya@example.in")
    auth.service.request_code(
        email="priya@example.in", plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.LOGIN, at=NOW, rng=_rng(),
    )
    auth.service.verify_code(
        email="priya@example.in", plane=AuthPlane.CANDIDATE, code=auth.code(), at=NOW
    )
    with auth.candidates._session_factory() as s:
        from sqlalchemy import func, select
        assert s.execute(select(func.count()).select_from(CandidateRow)).scalar() == 1


# ── the adversarial OTP cases ───────────────────────────────────────────────


def test_wrong_code_refuses(auth):
    auth.service.request_code(
        email="a@b.in", plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
        at=NOW, rng=_rng(),
    )
    with pytest.raises(ChallengeRefused):
        auth.service.verify_code(
            email="a@b.in", plane=AuthPlane.CANDIDATE, code="000000", at=NOW
        )


def test_reused_code_refuses(auth):
    auth.service.request_code(
        email="a@b.in", plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
        at=NOW, rng=_rng(),
    )
    code = auth.code()
    auth.service.verify_code(
        email="a@b.in", plane=AuthPlane.CANDIDATE, code=code, at=NOW
    )
    with pytest.raises(ChallengeRefused):
        auth.service.verify_code(
            email="a@b.in", plane=AuthPlane.CANDIDATE, code=code, at=NOW
        )


def test_expired_code_refuses(auth):
    auth.service.request_code(
        email="a@b.in", plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
        at=NOW, rng=_rng(),
    )
    with pytest.raises(ChallengeRefused):
        auth.service.verify_code(
            email="a@b.in", plane=AuthPlane.CANDIDATE, code=auth.code(),
            at=NOW + timedelta(minutes=11),
        )


def test_over_attempted_code_refuses_even_when_finally_correct(auth):
    """The cap must bite BEFORE the code is checked, or an attacker simply
    keeps guessing until the right one lands."""
    auth.service.request_code(
        email="a@b.in", plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
        at=NOW, rng=_rng(),
    )
    code = auth.code()
    for _ in range(5):
        with pytest.raises(ChallengeRefused):
            auth.service.verify_code(
                email="a@b.in", plane=AuthPlane.CANDIDATE, code="000000", at=NOW
            )
    with pytest.raises(ChallengeRefused):
        auth.service.verify_code(
            email="a@b.in", plane=AuthPlane.CANDIDATE, code=code, at=NOW
        )


def test_cooldown_blocks_an_immediate_resend(auth):
    auth.service.request_code(
        email="a@b.in", plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
        at=NOW, rng=_rng(),
    )
    with pytest.raises(ChallengeRefused) as exc:
        auth.service.request_code(
            email="a@b.in", plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
            at=NOW + timedelta(seconds=30), rng=_rng(),
        )
    assert exc.value.reason == "cooldown"
    assert auth.sent_count() == 1


def test_cooldown_is_scoped_per_plane(auth):
    """One address can be both a candidate and an org user; activity on one
    plane must not lock the other."""
    auth.service.request_code(
        email="a@b.in", plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
        at=NOW, rng=_rng(),
    )
    assert auth.service.request_code(
        email="a@b.in", plane=AuthPlane.ORG, purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": "Acme"}, at=NOW, rng=_rng(),
    ) is True


def test_no_provider_refuses_loudly(auth_no_email):
    with pytest.raises(EmailUnavailableError):
        auth_no_email.request_code(
            email="a@b.in", plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
            at=NOW, rng=_rng(),
        )


def test_a_failed_send_does_not_persist_a_challenge(auth_no_email):
    """A vendor outage must never cost someone their login, so the challenge is
    written only AFTER the mail is away."""
    from app.auth.challenges import ChallengeScope

    with pytest.raises(EmailUnavailableError):
        auth_no_email.request_code(
            email="a@b.in", plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
            at=NOW, rng=_rng(),
        )
    scope = ChallengeScope(
        auth_no_email._hash_email("a@b.in"),
        LoginPurpose.SIGNUP, AuthPlane.CANDIDATE,
    )
    assert auth_no_email._store.get_challenge(scope) is None


# ── the resolvers ───────────────────────────────────────────────────────────


def _candidate_session(auth) -> tuple[str, str]:
    auth.service.request_code(
        email="a@b.in", plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
        at=NOW, rng=_rng(),
    )
    token, _, principal = auth.service.verify_code(
        email="a@b.in", plane=AuthPlane.CANDIDATE, code=auth.code(), at=NOW
    )
    return token, principal.candidate_id


def test_resolve_by_session(auth):
    token, cid = _candidate_session(auth)
    p = auth.service.resolve(
        kind=PrincipalKind.CANDIDATE, session_token=token, header_key=None, at=NOW
    )
    assert p.candidate_id == cid
    assert p.via == PrincipalVia.SESSION


def test_resolve_by_header_key_still_works(auth):
    _, cid = _candidate_session(auth)
    key = auth.candidates.issue_access_key(cid)
    p = auth.service.resolve(
        kind=PrincipalKind.CANDIDATE, session_token=None, header_key=key, at=NOW
    )
    assert p.candidate_id == cid
    assert p.via == PrincipalVia.KEY


def test_session_wins_when_both_are_present(auth):
    """The stronger requirement wins: a request carrying a cookie is CSRF-checked
    even if it also carries a key."""
    token, cid = _candidate_session(auth)
    key = auth.candidates.issue_access_key(cid)
    p = auth.service.resolve(
        kind=PrincipalKind.CANDIDATE, session_token=token, header_key=key, at=NOW
    )
    assert p.via == PrincipalVia.SESSION


def test_no_credential_resolves_to_nothing(auth):
    assert auth.service.resolve(
        kind=PrincipalKind.CANDIDATE, session_token=None, header_key=None, at=NOW
    ) is None


def test_a_revoked_session_resolves_to_nothing(auth):
    token, _ = _candidate_session(auth)
    p = auth.service.resolve(
        kind=PrincipalKind.CANDIDATE, session_token=token, header_key=None, at=NOW
    )
    auth.service.logout(p, at=NOW)
    assert auth.service.resolve(
        kind=PrincipalKind.CANDIDATE, session_token=token, header_key=None, at=NOW
    ) is None


def test_an_expired_and_an_idle_session_resolve_to_nothing(auth):
    token, _ = _candidate_session(auth)
    assert auth.service.resolve(
        kind=PrincipalKind.CANDIDATE, session_token=token, header_key=None,
        at=NOW + timedelta(minutes=121),
    ) is None
    assert auth.service.resolve(
        kind=PrincipalKind.CANDIDATE, session_token=token, header_key=None,
        at=NOW + timedelta(hours=13),
    ) is None


def test_kind_is_checked_not_merely_presence(auth):
    """A candidate session must not authenticate on the org plane. Without this
    any valid session would authenticate everywhere."""
    token, _ = _candidate_session(auth)
    assert auth.service.resolve(
        kind=PrincipalKind.ORG, session_token=token, header_key=None, at=NOW
    ) is None
    assert auth.service.resolve(
        kind=PrincipalKind.ADMIN, session_token=token, header_key=None, at=NOW
    ) is None


def test_admin_key_resolves_anonymously(auth, settings):
    """admin_user_id stays None: the shared secret is a machine, not a person,
    and that difference is what makes attribution possible."""
    p = auth.service.resolve(
        kind=PrincipalKind.ADMIN, session_token=None,
        header_key=settings.api_auth_key.get_secret_value(), at=NOW,
    )
    assert p.via == PrincipalVia.KEY
    assert p.admin_user_id is None


def test_admin_fails_closed_without_a_configured_key(settings, tmp_path):
    """S8.1's rule, now enforced inside the resolver so every entry point --
    key OR session -- inherits it."""
    cfg = settings.model_copy(update={"api_auth_key": __import__(
        "pydantic", fromlist=["SecretStr"]).SecretStr("")})
    candidates = make_candidate_store()
    ledger = LedgerStore(candidates._session_factory, settings=cfg)
    service = build_auth_service(
        cfg, candidates=candidates, ledger=ledger, email=NullEmail(cfg)
    )
    assert service.resolve(
        kind=PrincipalKind.ADMIN, session_token=None, header_key="", at=NOW
    ) is None
    assert service.resolve(
        kind=PrincipalKind.ADMIN, session_token=None, header_key="anything", at=NOW
    ) is None


def test_resolve_any_accepts_a_session_of_any_kind(auth):
    token, cid = _candidate_session(auth)
    p = auth.service.resolve_any(session_token=token, at=NOW)
    assert p.kind == PrincipalKind.CANDIDATE
    assert p.candidate_id == cid


def test_resolve_any_refuses_a_header_key(auth):
    """A key has no session to list or revoke, so it resolves to nothing here
    rather than to something that pretends to work."""
    _, cid = _candidate_session(auth)
    auth.candidates.issue_access_key(cid)
    assert auth.service.resolve_any(session_token=None, at=NOW) is None


# ── session lifecycle + erasure ─────────────────────────────────────────────


def test_sessions_for_lists_only_the_callers_own(auth):
    token_a, _ = _candidate_session(auth)
    p_a = auth.service.resolve(
        kind=PrincipalKind.CANDIDATE, session_token=token_a, header_key=None, at=NOW
    )
    listed = auth.service.sessions_for(p_a, at=NOW)
    assert [v.id for v in listed] == [p_a.session_id]
    assert listed[0].current is True


def test_revoking_an_unowned_session_fails_indistinguishably(auth):
    token_a, _ = _candidate_session(auth)
    p_a = auth.service.resolve(
        kind=PrincipalKind.CANDIDATE, session_token=token_a, header_key=None, at=NOW
    )
    assert auth.service.revoke_session(p_a, "no-such-session", at=NOW) is False


def test_erase_login_state_clears_challenges_that_cannot_cascade(auth):
    from app.auth.challenges import ChallengeScope

    cid = _existing_candidate(auth, "priya@example.in")
    auth.service.request_code(
        email="priya@example.in", plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.LOGIN, at=NOW, rng=_rng(),
    )
    assert auth.service.erase_login_state(cid) == 1
    scope = ChallengeScope(
        auth.service._hash_email("priya@example.in"),
        LoginPurpose.LOGIN, AuthPlane.CANDIDATE,
    )
    assert auth.service._store.get_challenge(scope) is None


def test_session_creation_is_audited_for_a_candidate(auth):
    """It shows up in the candidate's own DPDP access log, like every other
    touch of their data."""
    _, cid = _candidate_session(auth)
    actions = [e.action for e in auth.ledger.audit_for_candidate(cid)]
    assert "auth.session.create" in actions


def _org_session(auth) -> str:
    auth.service.request_code(
        email="ops@acme.in", plane=AuthPlane.ORG, purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": "Acme"}, at=NOW, rng=_rng(),
    )
    token, _, _ = auth.service.verify_code(
        email="ops@acme.in", plane=AuthPlane.ORG, code=auth.code(), at=NOW
    )
    return token


def test_no_session_authenticates_on_a_plane_it_does_not_belong_to(auth):
    """Every direction, not just the convenient one.

    Found by mutation testing: an earlier version of this file only checked a
    CANDIDATE token against the org and admin resolvers, so deleting the kind
    check inside the CANDIDATE branch broke nothing. That branch is the one an
    org session would slip through.
    """
    candidate_token, _ = _candidate_session(auth)
    org_token = _org_session(auth)

    for token, allowed in ((candidate_token, PrincipalKind.CANDIDATE),
                           (org_token, PrincipalKind.ORG)):
        for kind in PrincipalKind:
            resolved = auth.service.resolve(
                kind=kind, session_token=token, header_key=None, at=NOW
            )
            if kind == allowed:
                assert resolved is not None, f"{kind} should accept its own session"
            else:
                assert resolved is None, f"{kind} accepted a {allowed} session"


def test_a_principal_is_never_returned_without_its_subject_id(auth):
    """The shape mutation 2 produced: a candidate Principal carrying
    candidate_id=None, which every downstream handler would treat as a real
    principal and then query with None."""
    candidate_token, _ = _candidate_session(auth)
    org_token = _org_session(auth)
    for token in (candidate_token, org_token):
        for kind in PrincipalKind:
            p = auth.service.resolve(
                kind=kind, session_token=token, header_key=None, at=NOW
            )
            if p is None:
                continue
            subject = p.candidate_id or p.org_user_id or p.admin_user_id
            assert subject, f"{kind} principal has no subject id"


def test_a_stale_signup_challenge_cannot_shadow_a_login(auth):
    """An unauthenticated LOGIN-LOCKOUT, found in whole-branch review.

    Once the candidate plane started sending for BOTH purposes, one address
    could hold two live challenges. verify_code checked SIGNUP first, so a
    correct LOGIN code was evaluated against the signup hash and refused --
    every time, until the shadowing challenge expired.

    That made it an unauthenticated denial of service: anyone could fire a
    signup code at any candidate's address and lock that person out of their
    own account for the challenge TTL, repeatably.

    Two fixes, both pinned here: the candidate plane files signup and login
    under ONE scope so the state cannot arise, and verify_code evaluates every
    live challenge before refusing so it cannot arise on another plane either.
    """
    email = "victim@example.in"
    _existing_candidate(auth, email)

    # Attacker fires a signup code at the victim's address.
    auth.service.request_code(
        email=email, plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
        at=NOW, rng=_rng(),
    )
    attacker_code = auth.code()

    # The victim requests their own login code, past the cooldown.
    later = NOW + timedelta(seconds=61)
    auth.service.request_code(
        email=email, plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.LOGIN,
        at=later, rng=random.Random(999),
    )
    victim_code = auth.code()
    assert victim_code != attacker_code

    # It works -- the whole point.
    _, _, principal = auth.service.verify_code(
        email=email, plane=AuthPlane.CANDIDATE, code=victim_code, at=later
    )
    assert principal.candidate_id

    # And the superseded code is dead, not merely deprioritised.
    with pytest.raises(ChallengeRefused):
        auth.service.verify_code(
            email=email, plane=AuthPlane.CANDIDATE, code=attacker_code, at=later
        )


def test_only_one_live_challenge_per_address_on_the_candidate_plane(auth):
    """The structural half of the fix: signup and login share one scope, so a
    second request supersedes rather than sitting beside the first."""
    from app.auth.challenges import ChallengeScope

    email = "one@example.in"
    auth.service.request_code(
        email=email, plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
        at=NOW, rng=_rng(),
    )
    auth.service.request_code(
        email=email, plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.LOGIN,
        at=NOW + timedelta(seconds=61), rng=random.Random(7),
    )
    email_hash = auth.service.hash_email(email)
    live = [
        p for p in (LoginPurpose.SIGNUP, LoginPurpose.LOGIN)
        if auth.service._store.get_challenge(
            ChallengeScope(email_hash, p, AuthPlane.CANDIDATE)
        ) is not None
    ]
    assert live == [LoginPurpose.LOGIN]


def test_a_wrong_code_does_not_burn_an_unrelated_challenges_attempts(auth):
    """Attempts are spent only on the challenge the code was actually wrong
    for -- never on one that was merely expired or exhausted."""
    from app.auth.challenges import ChallengeScope

    email = "org@example.in"
    auth.service.request_code(
        email=email, plane=AuthPlane.ORG, purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": "Acme"}, at=NOW, rng=_rng(),
    )
    with pytest.raises(ChallengeRefused):
        auth.service.verify_code(
            email=email, plane=AuthPlane.ORG, code="000000", at=NOW
        )
    scope = ChallengeScope(
        auth.service.hash_email(email), LoginPurpose.SIGNUP, AuthPlane.ORG
    )
    assert auth.service._store.get_challenge(scope).attempts == 1


def test_verify_accepts_the_matching_challenge_not_the_first_one(auth):
    """Defense in depth, exercised directly.

    `_scope_purpose` collapses the candidate plane so two live challenges
    cannot arise there -- which means the "evaluate every live challenge" layer
    is never reached through the public API, and a mutation test showed it was
    therefore untested. So this drives the store directly to construct the
    two-live-challenge state and proves the correct code still wins.

    Without this, a future plane that legitimately files two purposes would
    silently reintroduce the login lockout.
    """
    from app.auth.challenges import ChallengeScope, mint_code

    email_hash = auth.service.hash_email("two@example.in")
    salt = auth.service._settings.contact_hash_salt
    expires = NOW + timedelta(minutes=10)

    shadow_code, shadow_digest = mint_code(6, salt=salt, rng=random.Random(11))
    real_code, real_digest = mint_code(6, salt=salt, rng=random.Random(22))
    assert shadow_code != real_code

    # SIGNUP is the one _live_scopes looks at first -- the shadow position.
    auth.service._store.upsert_challenge(
        ChallengeScope(email_hash, LoginPurpose.SIGNUP, AuthPlane.CANDIDATE),
        code_hash=shadow_digest, expires_at=expires, payload={}, at=NOW,
    )
    auth.service._store.upsert_challenge(
        ChallengeScope(email_hash, LoginPurpose.LOGIN, AuthPlane.CANDIDATE),
        code_hash=real_digest, expires_at=expires, payload={}, at=NOW,
    )

    # The code belonging to the SECOND challenge must still be accepted.
    _, _, principal = auth.service.verify_code(
        email="two@example.in", plane=AuthPlane.CANDIDATE, code=real_code, at=NOW
    )
    assert principal.candidate_id
