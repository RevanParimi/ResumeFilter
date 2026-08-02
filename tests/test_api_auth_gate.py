"""The admin plane fails CLOSED (S8.1).

These tests assert REFUSALS. A suite that only ever sends a valid credential
cannot tell "authorized" from "unguarded" -- which is exactly how the fail-open
default survived eight PIs and four branch reviews.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.routes import require_api_key
from app.core.boot import LaunchConfigError
from app.main import create_app
from tests.conftest import ADMIN_HEADERS, ADMIN_KEY, make_services

RESUME = "Asha Rao\nEXPERIENCE\n- ML Engineer, Acme AI (2021 - Present)\n"


def _client(settings, flywheel, **client_kwargs):
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    return TestClient(app, raise_server_exceptions=False, **client_kwargs)


def test_no_configured_key_refuses_to_boot(settings, flywheel):
    """The empty key is the MOST refusing state, not the least."""
    open_settings = settings.model_copy(update={"api_auth_key": SecretStr("")})
    with pytest.raises(LaunchConfigError):
        with _client(open_settings, flywheel):
            pass


def test_absent_header_is_401(settings, flywheel):
    with _client(settings, flywheel) as client:
        assert client.post("/evaluate", json={"resume_text": RESUME}).status_code == 401
        assert client.get("/report/rep_x").status_code == 401


def test_wrong_header_is_401(settings, flywheel):
    with _client(settings, flywheel) as client:
        resp = client.post(
            "/evaluate", json={"resume_text": RESUME}, headers={"X-API-Key": "nope"}
        )
        assert resp.status_code == 401


def test_correct_header_is_allowed(settings, flywheel):
    with _client(settings, flywheel) as client:
        resp = client.post(
            "/evaluate", json={"resume_text": RESUME}, headers=ADMIN_HEADERS
        )
        assert resp.status_code == 200


def test_healthz_and_root_stay_open(settings, flywheel):
    with _client(settings, flywheel) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/").status_code == 200


def _gates(route) -> set:
    """Every dependency callable on a route, at any depth. Router-level
    dependencies and handler-parameter ones both land in the dependant tree."""
    found, stack = set(), list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        found.add(dep.call)
        stack.extend(dep.dependencies)
    return found


def test_every_admin_route_carries_the_gate():
    """Walked from the router, not listed by hand: an admin endpoint cannot be
    added outside the gate without failing here."""
    from app.api.routes import router

    assert len(router.routes) >= 27
    for route in router.routes:
        assert require_api_key in _gates(route), (
            f"{route.path} is not behind require_api_key"
        )


#: Everything reachable with NO credential of any kind.
#:
#: S8.2 made this the SAME list the route-table guard uses, rather than a second
#: copy beside it. Two hand-maintained allowlists drift, and the one that drifts
#: is always the one nobody is looking at -- which is the shape of the defect
#: this whole file exists to prevent.
#:
#: It holds `/` and `/healthz` (probes and humans), FastAPI's doc surface, and
#: the login endpoints, which by definition run BEFORE a principal exists.
from app.api.routes import PUBLIC_PATHS as OPEN_PATHS  # noqa: E402


def _walk(app):
    """Every APIRoute in the app. FastAPI 0.138 keeps included routers wrapped
    rather than flattening them into app.routes."""
    for entry in app.routes:
        inner = getattr(entry, "original_router", None)
        for route in (inner.routes if inner is not None else [entry]):
            if hasattr(route, "dependant"):
                yield route


def test_nothing_is_reachable_without_a_credential_by_accident(settings, flywheel):
    """Pins the unauthenticated surface. A new public endpoint has to be added
    to OPEN_PATHS on purpose -- it cannot arrive by forgetting a dependency."""
    from app.api.routes import (
        require_any_principal, require_candidate, require_org,
    )

    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    # require_any_principal is a real gate, not an exemption: it accepts a
    # session of ANY plane but refuses a header key and refuses anonymity.
    gates = {require_api_key, require_org, require_candidate, require_any_principal}

    ungated = {r.path for r in _walk(app) if not (_gates(r) & gates)}

    assert ungated <= OPEN_PATHS, f"unauthenticated by accident: {ungated - OPEN_PATHS}"


def test_admin_key_is_never_echoed(settings, flywheel):
    """A 401 body must not leak the expected value."""
    with _client(settings, flywheel) as client:
        body = client.get("/report/rep_x").text
        assert ADMIN_KEY not in body
