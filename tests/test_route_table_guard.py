"""The structural answer to PI-8's highest regression risk (S8.2 spec 2.4).

Sessions add a SECOND entry point to every plane. Hand-written session twins
would only cover routes that existed on the day someone wrote them; this guard
walks the live FastAPI route table, so it fails the moment a NEW route
establishes a principal any other way.

Same shape as the metadata drift guard in test_migrations.py, which caught a
real migration-vs-ORM drift in S7.1 precisely because nobody had to remember to
extend it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from app.api.routes import (
    PUBLIC_PATHS, require_any_principal, require_api_key, require_candidate,
    require_org,
)
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]

#: The ONLY functions permitted to establish a principal.
RESOLVERS = {require_api_key, require_org, require_candidate, require_any_principal}

#: Mounts are a SECOND way to widen the unauthenticated surface, and until S8.6
#: nothing watched it. A Mount has no `.methods`, so `_guarded_routes` skips it,
#: and `include_router` dependencies do not apply to it -- so a mount is
#: unauthenticated AND invisible to the guard above. PUBLIC_PATHS exists so
#: that widening the public surface happens in a diff someone reads; this is
#: the same ritual for the other mechanism.
MOUNTS: set[str] = {
    # S8.6. The UI shell, served same-origin. Unauthenticated ON PURPOSE: a
    # login page reachable only after login is not reachable by the person who
    # needs it. It serves frontend/ and holds no data-principal information --
    # tests/test_ui_mount.py pins the root it is given.
    "/ui",
}


def _walk(routes, inherited=frozenset()):
    """Yield (route, inherited_dependency_callables) for every real endpoint.

    FastAPI 0.138 does not flatten ``include_router`` into ``app.routes``: it
    stores an ``_IncludedRouter`` wrapper holding the original router, so a
    naive ``for route in app.routes`` sees NINE routes and silently misses all
    63 real ones. A guard that inspects nothing passes everything, so this
    recursion is the part that makes the whole test mean something.
    """
    for route in routes:
        context = getattr(route, "include_context", None)
        original = getattr(route, "original_router", None)
        if original is not None:
            # Dependencies attached at include_router(...) time apply to every
            # child and do not appear on the child's own dependant.
            added = frozenset(
                d.dependency for d in getattr(context, "dependencies", []) or []
            )
            yield from _walk(original.routes, inherited | added)
        else:
            yield route, inherited


def _flat_dependency_calls(dependant) -> set:
    """Every dependency callable reachable from ``dependant``, at any depth.

    THIS REPLACES ``fastapi.dependencies.utils.get_flat_dependant``, which this
    guard imported until FastAPI 0.141 DELETED it -- taking five test modules
    down at COLLECTION time and turning CI red while local stayed green, because
    `requirements.txt` said `fastapi>=0.115.0` and the two machines resolved
    different versions. `fastapi.dependencies.utils` was never public API, so
    the guard's correctness rested on an internal that was free to vanish.

    Reading FastAPI 0.138's implementation, the old helper appended each direct
    sub-dependant AND extended with that sub-dependant's own flattened
    dependencies -- so ``get_flat_dependant(d).dependencies`` was every
    TRANSITIVE descendant, excluding ``d`` itself. That is reproduced exactly
    here; the only dependency now is the ``Dependant`` dataclass having
    ``.dependencies`` and ``.call``, which is far more stable than a helper's
    name.

    ``seen`` keys on identity, which the original lacked at its default
    ``skip_repeats=False``: a dependency reachable by two paths would otherwise
    be walked twice. It terminates either way, but repeating work in a guard
    that walks 60+ routes is pointless.
    """
    calls: set = set()
    stack = list(dependant.dependencies)
    seen: set[int] = set()
    while stack:
        sub = stack.pop()
        if id(sub) in seen:
            continue
        seen.add(id(sub))
        calls.add(sub.call)
        stack.extend(sub.dependencies)
    return calls


def _resolvers_on(route, inherited=frozenset()) -> set:
    """Every dependency callable that runs for this route.

    The flattening folds in router-level dependencies -- verified: an admin
    route reports ``require_api_key`` even though the decorator never mentions
    it -- which is exactly how the route inherits its gate at runtime.
    """
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return set(inherited)
    return _flat_dependency_calls(dependant) | set(inherited)


def _guarded_routes(app):
    for route, inherited in _walk(app.routes):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or methods is None or path in PUBLIC_PATHS:
            continue
        yield route, path, methods, inherited


def _mounts(app) -> list[Mount]:
    """Every Mount on the app. Walks the way _guarded_routes does, NOT a flat
    scan of app.routes.

    APIRouter inherits .mount() from Starlette's Router, so a mount inside an
    included router sits behind the same _IncludedRouter wrapper that made a
    naive scan miss 54 of this app's 63 routes. A guard whose whole claim is
    "no mount widens the public surface silently" cannot have one silent path.

    THE ONE mount-discovery idiom for the suite. It returns the Mount objects
    rather than their paths because the two other files that need them read
    `.app.directory` off the object -- and each had grown its own flat scan,
    the exact shape this docstring calls broken, in the same branch that wrote
    this docstring. tests/test_image_contents.py and tests/test_ui_mount.py
    import it, the way test_openapi_contract and test_org_scope_guard already
    import `_walk`.
    """
    return [r for r, _ in _walk(app.routes) if isinstance(r, Mount)]


def _mount_paths(app) -> set[str]:
    return {m.path for m in _mounts(app)}


def test_every_non_public_route_uses_a_sanctioned_resolver(services):
    app = create_app(services)
    checked = list(_guarded_routes(app))
    # A guard that inspected nothing would pass vacuously, which is the exact
    # failure mode the fail-open admin gate had for eight PIs.
    assert len(checked) >= 60, f"only {len(checked)} routes inspected -- walker is broken"
    unguarded = [
        f"{sorted(methods)} {path}"
        for route, path, methods, inherited in checked
        if not (_resolvers_on(route, inherited) & RESOLVERS)
    ]
    assert unguarded == [], (
        "these routes establish a principal outside the sanctioned resolvers, "
        "or are missing a gate entirely: " + ", ".join(unguarded)
    )


def test_the_guard_would_catch_a_new_unguarded_route(services):
    """The guard must actually fail for the thing it exists to catch.

    A guard nobody has seen fail is a guard nobody knows works -- which is how
    the fail-open admin gate survived eight PIs and four branch reviews.
    """
    app = create_app(services)

    @app.get("/totally-unguarded")
    async def _sneaky() -> dict:      # pragma: no cover - never called
        return {}

    unguarded = [
        path for route, path, _, inherited in _guarded_routes(app)
        if not (_resolvers_on(route, inherited) & RESOLVERS)
    ]
    assert "/totally-unguarded" in unguarded


def test_mounts_are_an_explicit_short_list(services):
    """Every mount is unauthenticated by construction. If one appears here
    without appearing in MOUNTS, someone added a public surface without saying
    so."""
    app = create_app(services)
    assert _mount_paths(app) == MOUNTS


def test_the_guard_would_catch_a_new_mount(services):
    """A guard nobody has seen fail is a guard nobody knows works -- the reason
    the fail-open admin gate survived eight PIs and four branch reviews."""
    from starlette.staticfiles import StaticFiles

    app = create_app(services)
    app.mount("/sneaky", StaticFiles(directory="."), name="sneaky")
    assert _mount_paths(app) != MOUNTS
    assert "/sneaky" in _mount_paths(app)


def test_the_guard_catches_nested_mounts_inside_included_routers(services):
    """Mounts inside an included router were invisible to a flat scan of
    app.routes, just like 54 of this app's 63 routes are. A guard that misses
    them cannot claim "no mount widens the public surface silently".

    This test verifies the nested case survives include_router, so the guard
    built on _walk (not a flat scan) is complete.
    """
    from fastapi import APIRouter
    from starlette.staticfiles import StaticFiles

    app = create_app(services)
    router = APIRouter()
    router.mount("/nested-sneaky", StaticFiles(directory="."), name="nested")
    app.include_router(router)

    # The nested mount should be visible to _walk but would have been invisible
    # to a flat scan of app.routes.
    assert "/nested-sneaky" in _mount_paths(app)


def test_public_paths_is_an_explicit_short_list():
    """Widening this set is the reviewable act. If it grows silently, the guard
    above stops meaning anything, so the list is pinned literally."""
    assert PUBLIC_PATHS == {
        "/", "/healthz", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json",
        "/auth/org/signup", "/auth/org/login", "/auth/org/verify",
        "/auth/candidate/signup", "/auth/candidate/login", "/auth/candidate/verify",
        "/auth/admin/login", "/auth/admin/verify",
        # S8.3 Phase B. The one entry that is not an auth handshake or a doc
        # page, and it is deliberate: DPDP requires the grievance mechanism to
        # be PUBLISHED, and a contact reachable only after login is not
        # reachable by the person whose complaint is that they cannot log in.
        # It discloses four operator-chosen config fields and reads nothing
        # about any data principal.
        "/grievance",
    }


def test_every_public_auth_path_actually_exists(services):
    """A stale entry in PUBLIC_PATHS is a hole waiting for a future route to
    reuse that path and inherit an exemption nobody granted it."""
    app = create_app(services)
    live = {getattr(r, "path", None) for r, _ in _walk(app.routes)}
    for path in PUBLIC_PATHS:
        assert path in live, f"PUBLIC_PATHS lists {path}, which no route serves"


def test_the_session_lifecycle_routes_are_session_only(services):
    """require_any_principal is permitted ONLY on the four cross-plane routes.
    Anywhere else it would be a way to reach a plane without its own gate."""
    app = create_app(services)
    allowed = {
        "/auth/me", "/auth/logout", "/auth/sessions",
        "/auth/sessions/{session_id}/revoke",
    }
    for route, path, _, inherited in _guarded_routes(app):
        if require_any_principal in _resolvers_on(route, inherited):
            assert path in allowed, f"{path} must not use require_any_principal"


def test_mount_discovery_sees_a_mount_inside_an_included_router():
    """The reason :func:`_mounts` exists, made EXECUTABLE rather than asserted
    in a docstring -- and the reason two other files may not hand-roll it.

    ``APIRouter`` inherits ``.mount()`` from Starlette's ``Router``, so a
    nested mount sits behind the same ``_IncludedRouter`` wrapper that hides
    the 54 routes ``_walk`` was written for. Measured on FastAPI 0.138: the
    flat scan finds ZERO mounts in the app below. A guard written that way
    reports a clean public surface for an app that just grew a public one.
    """
    inner = APIRouter()
    inner.mount("/nested", StaticFiles(directory=str(ROOT / "frontend")), name="n")
    app = FastAPI()
    app.include_router(inner)

    assert [r for r in app.routes if isinstance(r, Mount)] == []
    assert {m.path for m in _mounts(app)} == {"/nested"}
