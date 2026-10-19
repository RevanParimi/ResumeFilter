"""Email-OTP authentication and session lifecycle on all three account planes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.dependencies import _client_ip_hash, _rate_limited, _services, require_any_principal
from app.auth.schema import AuthPlane, LoginPurpose, Principal, SessionView
from app.auth.service import ChallengeRefused, EmailUnavailableError, RegistrationRefused
from app.ratelimit.service import RateLimited


# Login routes are public; session routes establish their principal explicitly.
auth_router = APIRouter()


class SessionRevokedResponse(BaseModel):
    session_id: str
    revoked: bool


class CodeRequestAccepted(BaseModel):
    """The 202 from every signup/login on all three planes. IDENTICAL for known
    and unknown addresses on purpose -- see AUTH.md's anti-enumeration rule."""

    status: str = "accepted"
    #: local env + login_otp_debug_echo ONLY; production can never echo. Every
    #: code-issuing route sets response_model_exclude_none, so a real deployment
    #: answers `{"status": "accepted"}` with the key ABSENT, not null -- the
    #: uniform body this model exists to guarantee is unchanged by the knob.
    debug_code: Optional[str] = None


class SessionEstablished(BaseModel):
    """A verified code. The session token is a cookie; the CSRF token is in the
    body because a JS client has to echo it in a header."""

    principal: str
    csrf_token: str
    organization_id: Optional[str] = None


class AuthMeResponse(BaseModel):
    kind: str
    organization_id: Optional[str] = None
    session_id: Optional[str] = None


class LogoutResponse(BaseModel):
    logged_out: bool


# ── Auth: email-OTP signup / login / sessions (S8.2) ─────────────────────────
# Every route below either sits in PUBLIC_PATHS (it runs BEFORE a principal
# exists) or depends on require_any_principal. The route-table guard enforces
# that there is no third option.


class OrgSignupRequest(BaseModel):
    email: str
    organization_name: str = Field(min_length=1, max_length=200)


class EmailOnlyRequest(BaseModel):
    email: str


class VerifyRequest(BaseModel):
    email: str
    code: str


#: Signup and login always answer 202, whether or not the address is known. An
#: endpoint that reveals which addresses are registered is an enumeration
#: oracle, and it is the kind only an attacker ever notices.
_ACCEPTED = {"status": "accepted"}


def _set_session_cookies(
    response: Response, *, token: str, csrf: str, settings
) -> None:
    """One helper for both cookies so their flags cannot drift between planes.

    The session cookie is httpOnly, so XSS cannot read it. The CSRF cookie
    deliberately is NOT, because the browser client has to read it to echo it
    back in X-CSRF-Token. That asymmetry IS the double-submit scheme, not an
    oversight -- a reviewer seeing httponly=False here should read on, not fix.
    """
    common = dict(
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_minutes * 60,
        path="/",
    )
    response.set_cookie(settings.session_cookie_name, token, httponly=True, **common)
    response.set_cookie(settings.csrf_cookie_name, csrf, httponly=False, **common)


def _request_code(
    request: Request,
    *,
    email: str,
    plane: AuthPlane,
    purpose: LoginPurpose,
    payload: Optional[dict] = None,
) -> CodeRequestAccepted:
    """Shared signup/login handler for all three planes."""
    services = _services(request)
    code: Optional[str] = None
    try:
        _sent, code = services.auth.issue_code(
            email=email,
            plane=plane,
            purpose=purpose,
            payload=payload,
            at=datetime.now(timezone.utc),
            ip_hash=_client_ip_hash(request),
        )
    except RateLimited as exc:
        # The opaque-detail reasoning that used to live here now lives on
        # `_rate_limited`, where all five call sites can read it.
        raise _rate_limited(exc) from exc
    except EmailUnavailableError as exc:
        # An honest 503 rather than a 202 that leaves someone waiting forever for
        # a code that was never sent (the NullSpeech posture from S7.3).
        raise HTTPException(status_code=503, detail="email_unavailable") from exc
    except ChallengeRefused:
        # Includes the cooldown case, and answering 202 anyway keeps the response
        # uniform. A cooldown can only be triggered by an address that HAS an
        # account, so surfacing it would be the enumeration oracle by another
        # door. The previously sent code is still live and still in their inbox,
        # so the user loses nothing.
        pass

    # Double-guarded: local env AND the knob -- the verif_otp_debug_echo shape
    # from S7.1. Every code-issuing route funnels through here, so the echo
    # cannot be live on one plane and missing on another.
    #
    # This IS an enumeration oracle: `code` is None precisely when no code was
    # sent, so the echoed body distinguishes a registered address from an
    # unregistered one -- the very thing the uniform 202 above exists to hide.
    # That is acceptable only because it cannot leave a developer's laptop:
    # prod REFUSES TO BOOT with the knob on (app/core/boot.py), and staging
    # ignores it.
    if (
        code is not None
        and services.settings.env == "local"
        and services.settings.login_otp_debug_echo
    ):
        return CodeRequestAccepted(debug_code=code)
    return CodeRequestAccepted()


def _verify(
    request: Request, response: Response, *, email: str, code: str, plane: AuthPlane
) -> SessionEstablished:
    services = _services(request)
    try:
        token, csrf, principal = services.auth.verify_code(
            email=email,
            plane=plane,
            code=code,
            user_agent=request.headers.get("user-agent"),
            ip_hash=_client_ip_hash(request),
        )
    except RateLimited as exc:
        raise _rate_limited(exc) from exc
    except RegistrationRefused as exc:
        # The code was RIGHT. This is a registration failure, and reporting it
        # as invalid_code is what locked users out of their own signup.
        raise HTTPException(status_code=409, detail=exc.reason) from exc
    except ChallengeRefused as exc:
        # ONE status and ONE detail for every CODE failure mode. Distinguishing
        # expired from wrong from exhausted tells a brute-forcer which of their
        # assumptions was right, which is precisely the help not to give.
        raise HTTPException(status_code=400, detail="invalid_code") from exc
    _set_session_cookies(response, token=token, csrf=csrf, settings=services.settings)
    return SessionEstablished(
        principal=principal.kind.value,
        csrf_token=csrf,
        organization_id=principal.org_id,
    )


@auth_router.post("/auth/org/signup", status_code=202, response_model=CodeRequestAccepted,
                  response_model_exclude_none=True)
async def auth_org_signup(req: OrgSignupRequest, request: Request) -> CodeRequestAccepted:
    """Refuse a taken org name HERE, before a code is ever sent (S8.4 §2.1).

    The old behaviour answered 202, mailed a real code, and then rejected that
    CORRECT code at verify as `invalid_code` -- because org creation happens in
    `_establish`, and every ChallengeRefused collapsed into one message. The
    user burned their attempts and could not onboard.

    This does not re-open the enumeration oracle. What that oracle protects is
    whether an ADDRESS has an account, and this check never looks at the
    address: an unknown address still gets 202 exactly like a known one.
    """
    if not _services(request).auth.organization_name_available(req.organization_name):
        raise HTTPException(status_code=409, detail="organization_name_taken")
    return _request_code(
        request,
        email=req.email,
        plane=AuthPlane.ORG,
        purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": req.organization_name},
    )


@auth_router.post("/auth/org/login", status_code=202, response_model=CodeRequestAccepted,
                  response_model_exclude_none=True)
async def auth_org_login(req: EmailOnlyRequest, request: Request) -> CodeRequestAccepted:
    return _request_code(
        request, email=req.email, plane=AuthPlane.ORG, purpose=LoginPurpose.LOGIN
    )


@auth_router.post("/auth/org/verify", response_model=SessionEstablished)
async def auth_org_verify(
    req: VerifyRequest, request: Request, response: Response
) -> SessionEstablished:
    return _verify(
        request, response, email=req.email, code=req.code, plane=AuthPlane.ORG
    )


@auth_router.post("/auth/candidate/signup", status_code=202, response_model=CodeRequestAccepted,
                  response_model_exclude_none=True)
async def auth_candidate_signup(req: EmailOnlyRequest, request: Request) -> CodeRequestAccepted:
    return _request_code(
        request,
        email=req.email,
        plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.SIGNUP,
    )


@auth_router.post("/auth/candidate/login", status_code=202, response_model=CodeRequestAccepted,
                  response_model_exclude_none=True)
async def auth_candidate_login(req: EmailOnlyRequest, request: Request) -> CodeRequestAccepted:
    return _request_code(
        request,
        email=req.email,
        plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.LOGIN,
    )


@auth_router.post("/auth/candidate/verify", response_model=SessionEstablished)
async def auth_candidate_verify(
    req: VerifyRequest, request: Request, response: Response
) -> SessionEstablished:
    return _verify(
        request, response, email=req.email, code=req.code, plane=AuthPlane.CANDIDATE
    )


# NOTE: there is deliberately NO /auth/admin/signup. Operators are created by an
# existing operator through POST /admin/users, behind the shared admin key.


@auth_router.post("/auth/admin/login", status_code=202, response_model=CodeRequestAccepted,
                  response_model_exclude_none=True)
async def auth_admin_login(req: EmailOnlyRequest, request: Request) -> CodeRequestAccepted:
    return _request_code(
        request, email=req.email, plane=AuthPlane.ADMIN, purpose=LoginPurpose.LOGIN
    )


@auth_router.post("/auth/admin/verify", response_model=SessionEstablished)
async def auth_admin_verify(
    req: VerifyRequest, request: Request, response: Response
) -> SessionEstablished:
    return _verify(
        request, response, email=req.email, code=req.code, plane=AuthPlane.ADMIN
    )


# -- session lifecycle: cross-plane, session-only ----------------------------


@auth_router.get("/auth/me", response_model=AuthMeResponse)
async def auth_me(principal: Principal = Depends(require_any_principal)) -> AuthMeResponse:
    """What the browser client calls on load to learn who it is."""
    return {
        "kind": principal.kind.value,
        "organization_id": principal.org_id,
        "session_id": principal.session_id,
    }


@auth_router.post("/auth/logout", response_model=LogoutResponse)
async def auth_logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(require_any_principal),
) -> LogoutResponse:
    services = _services(request)
    revoked = services.auth.logout(principal)
    response.delete_cookie(services.settings.session_cookie_name, path="/")
    response.delete_cookie(services.settings.csrf_cookie_name, path="/")
    return {"logged_out": revoked}


@auth_router.get("/auth/sessions", response_model=list[SessionView])
async def auth_sessions(
    request: Request, principal: Principal = Depends(require_any_principal)
) -> list[SessionView]:
    """The caller's own live sessions. Ownership resolves from the session, never
    from a parameter, so another principal's devices are simply unreachable."""
    return _services(request).auth.sessions_for(principal)


@auth_router.post("/auth/sessions/{session_id}/revoke", response_model=SessionRevokedResponse)
async def auth_revoke_session(
    session_id: str,
    request: Request,
    principal: Principal = Depends(require_any_principal),
) -> SessionRevokedResponse:
    """Unknown and not-owned both 404 -- indistinguishable, so a session id
    cannot be probed (the S6.4 rule)."""
    if not _services(request).auth.revoke_session(principal, session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session_id, "revoked": True}
