"""Shared request helpers and principal/CSRF boundaries for every API router."""
from __future__ import annotations

from typing import Optional
from fastapi import HTTPException, Request

from app.auth.csrf import csrf_matches
from app.auth.schema import Principal, PrincipalKind, PrincipalVia
from app.candidates.hashing import contact_hash
from app.core.blocking import ExecutionPending, ExecutionUnavailable
from app.ratelimit.service import RateLimited
from app.services import Services


def _services(request: Request) -> Services:
    return request.app.state.services


# Paths that establish no principal, by definition. Everything else must go
# through one of the four resolvers below, and tests/test_route_table_guard.py
# fails the build if it does not. WIDENING THIS SET IS THE REVIEWABLE ACT —
# it is how "someone forgot a gate" becomes "someone edited a named list".
PUBLIC_PATHS: set[str] = {
    "/", "/healthz", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json",
    "/auth/org/signup", "/auth/org/login", "/auth/org/verify",
    "/auth/candidate/signup", "/auth/candidate/login", "/auth/candidate/verify",
    "/auth/admin/login", "/auth/admin/verify",
    # S8.3 Phase B. DPDP requires the grievance mechanism to be PUBLISHED, and
    # a contact reachable only after login is not reachable by the person whose
    # complaint is that they cannot log in. It discloses four operator-chosen
    # fields and reads nothing about any data principal.
    "/grievance",
}


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _accept(request: Request, principal: Principal) -> Principal:
    """Record the principal and enforce CSRF in ONE place.

    CSRF lives inside the resolvers rather than beside them as its own
    dependency, and that is a correctness decision, not tidiness: FastAPI runs
    router-level dependencies BEFORE route-level ones, so a separate
    ``Depends(require_csrf)`` on ``org_router`` would execute before
    ``require_org`` had established the principal, read ``via`` as unset, and
    skip the check on every request — a fail-open that tests using cookies
    would never notice. Here the ordering cannot be got wrong.

    The exemption keys on ``principal.via``, NEVER on "was a header present":
    otherwise a browser carrying a session cookie plus an attacker-supplied
    ``X-Org-Key`` would skip CSRF entirely. ``AuthService.resolve`` prefers the
    session when both arrive, so the stronger requirement always wins.
    """
    request.state.principal = principal
    if request.method not in _SAFE_METHODS and principal.via == PrincipalVia.SESSION:
        settings = _services(request).settings
        if not csrf_matches(
            request.cookies.get(settings.csrf_cookie_name),
            request.headers.get("X-CSRF-Token"),
        ):
            raise HTTPException(
                status_code=403, detail="missing or invalid CSRF token"
            )
    return principal


async def require_api_key(request: Request) -> Principal:
    """Admin-plane gate (FR-15). Fail-CLOSED since S8.1; session-capable since S8.2.

    Since S8.2 every plane resolves through ONE service call, so a gate cannot
    be forgotten at a second door — the bug shape that shipped as a real defect
    in S7.1, S7.2 and S7.3, and which sessions would otherwise multiply by two.

    An unset ``DEE_API_AUTH_KEY`` is still the MOST refusing state (enforced in
    ``AuthService._from_key``), and ``verify_launch_config`` stops the process
    before it can serve in that state at all.
    """
    principal = await _resolve(request,
        kind=PrincipalKind.ADMIN,
        session_token=_session_cookie(request),
        header_key=request.headers.get("X-API-Key"),
    )
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or missing admin credential")
    return _accept(request, principal)


async def require_org(request: Request) -> str:
    """Resolve the caller to ONE organization (S3.2), by session or by key.

    The return type is unchanged — every handler still receives ``org_id: str``
    — which is why sessions reached all 63 endpoints without editing one.
    """
    principal = await _resolve(request,
        kind=PrincipalKind.ORG,
        session_token=_session_cookie(request),
        header_key=request.headers.get("X-Org-Key"),
    )
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or missing X-Org-Key")
    return _accept(request, principal).org_id


async def require_candidate(request: Request) -> str:
    """Resolve the caller to ONE candidate (S6.4), by session or by key.

    Always enforced — the portal is the data principal's private surface, and
    cross-candidate isolation stays structural because handlers still receive
    the id from here rather than from a path or body param.
    """
    principal = await _resolve(request,
        kind=PrincipalKind.CANDIDATE,
        session_token=_session_cookie(request),
        header_key=request.headers.get("X-Candidate-Key"),
    )
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or missing X-Candidate-Key")
    return _accept(request, principal).candidate_id


async def require_any_principal(request: Request) -> Principal:
    """The cross-plane resolver, for the session-lifecycle routes only.

    A candidate, an org user and an operator all need to see and revoke their
    own sessions through one route. Without a name for that, those four routes
    would need three copies each or would sit outside the route-table guard —
    and a route outside the guard is the entire problem.

    SESSION ONLY: a header key has no session to list or revoke, so it 401s
    here rather than resolving to something that pretends to work.
    """
    principal = await _resolve(request, session_token=_session_cookie(request))
    if principal is None:
        raise HTTPException(status_code=401, detail="a session is required")
    return _accept(request, principal)


async def _resolve(request: Request, **credentials) -> Optional[Principal]:
    services = _services(request)
    # Only raw credential values cross the thread boundary. The resolver owns
    # every SQL session through its final touch/close; request state and CSRF
    # remain on the caller, and run only after an admitted successful result.
    resolver = services.auth.resolve if 'kind' in credentials else services.auth.resolve_any
    try:
        return await services.auth_resolution.run(resolver, **credentials)
    except ExecutionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={'Retry-After': '1'}) from None
    except ExecutionPending:
        # A late last-seen write may commit. No principal reaches a handler
        # after this refusal, and the original request is never replayed.
        raise HTTPException(status_code=503, detail='auth_resolution_pending',
                            headers={'Retry-After': '1'}) from None


def _session_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(_services(request).settings.session_cookie_name)


def _client_ip(request: Request) -> Optional[str]:
    """The caller's address, or None.

    ``X-Forwarded-For`` is IGNORED unless ``rate_limit_trusted_proxy_hops``
    says how many proxies sit in front of us. This is the decision that
    determines whether the per-IP scope is worth anything: the header is
    entirely attacker-controlled, so trusting it by default would hand every
    caller a free reset of their own scope, and the limiter would pass its
    tests while bounding nothing.

    With ``hops = n`` we take the n-th entry FROM THE RIGHT -- the rightmost
    entries are the ones our own infrastructure appended, and everything to the
    left of them was supplied by the client.
    """
    settings = _services(request).settings
    hops = settings.rate_limit_trusted_proxy_hops
    if hops > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else None


def _rate_limited(exc: RateLimited) -> HTTPException:
    """The ONE translation of a refused bound into HTTP (S8.3).

    It was four byte-identical copies before Phase B was about to add a fifth,
    which is how "a rule applied at one entry point and not the other" starts.
    The next copy would be the one that forgets `Retry-After`, and a 429 with
    no header reads to a client author as "stop forever".

    ONE OPAQUE DETAIL, deliberately. Which rule and which scope refused is
    operator information and goes to the log line the limiter already emits --
    telling a brute-forcer which of their two axes tripped is telling them
    which one to change.
    """
    return HTTPException(
        status_code=429,
        detail="rate_limited",
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


def _client_ip_hash(request: Request) -> Optional[str]:
    """`_client_ip`, hashed. Nothing downstream ever sees a raw address --
    the `email_hash`/`phone_hash` precedent (PI-8 §7): store what identifies,
    never what re-identifies."""
    ip = _client_ip(request)
    if not ip:
        return None
    return contact_hash(ip, _services(request).settings.contact_hash_salt)
