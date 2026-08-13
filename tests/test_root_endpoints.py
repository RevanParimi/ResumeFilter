"""GET / advertises the caller's entry points, DERIVED (S8.6 §6).

The filter is an explicit rule, not a taste judgement: every APIRoute, minus
FastAPI's own documentation paths, minus "/" itself, minus any Mount.

The admin plane is INCLUDED. The list has always advertised admin routes, and
hiding them would be security by obscurity on a plane that is already
credential-gated -- while making the list wrong again, which is the defect
being fixed.

This test does NOT re-implement the filter. A second derivation agreeing with
the first by construction is the SweepTarget.knob test the Phase B plan
correctly deleted. It asserts the CONSEQUENCES instead.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

DOC_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}


def _endpoints(services) -> list[str]:
    return TestClient(create_app(services)).get("/").json()["endpoints"]


def test_the_derivation_is_not_vacuous(services):
    """A walker that returned nothing would satisfy almost every other test in
    this file -- no doc paths, no mount, no HEAD, every entry well-formed.

    Not hypothetical: a flat `for route in app.routes` sees NINE routes here,
    because FastAPI 0.138 keeps include_router behind an _IncludedRouter
    wrapper. That is the exact bug test_route_table_guard.py was written about,
    one file over, and the same recursion is what makes this list real.
    """
    assert len(_endpoints(services)) >= 60


def test_the_stale_entries_are_gone_because_it_is_derived(services):
    """The three families the hand-maintained list was missing."""
    listed = " ".join(_endpoints(services))
    assert "/screening/batches" in listed
    assert "/metrics" in listed
    assert "/portal/grievances" in listed
    assert "/admin/requests" in listed


def test_documentation_paths_are_excluded(services):
    for path in DOC_PATHS:
        assert not any(e.endswith(f" {path}") for e in _endpoints(services)), path


def test_the_root_itself_is_excluded(services):
    """A caller reading this list is already at "/"."""
    assert not any(e.endswith(" /") for e in _endpoints(services))


def test_the_mount_is_excluded(services):
    """A static mount is not an API entry point."""
    assert not any("/ui" in e for e in _endpoints(services))


def test_a_new_route_appears_without_anyone_editing_a_list(services):
    """The property the whole change exists for."""
    app = create_app(services)

    @app.get("/brand-new-surface")
    async def _new() -> dict:      # pragma: no cover - never called
        return {}

    listed = TestClient(app).get("/").json()["endpoints"]
    assert "GET /brand-new-surface" in listed


def test_the_shape_is_method_space_path(services):
    """The field's existing format, which clients may already parse."""
    for entry in _endpoints(services):
        method, _, path = entry.partition(" ")
        assert method.isupper() and path.startswith("/"), entry


def test_it_is_not_a_wall_of_head_and_options(services):
    """Derivation without a method filter would triple the list with entries
    no caller ever writes by hand. Pinned because the noise is what would push
    the next person back to a literal."""
    assert not any(e.startswith(("HEAD ", "OPTIONS ")) for e in _endpoints(services))


def test_every_advertised_path_actually_answers(services):
    """The list is only worth deriving if it points somewhere.

    A path advertised here that 404s is worse than an omission -- it sends a
    caller to a door that does not exist. Parameterised paths are skipped (an
    id would have to be invented); the check is that the ROUTER knows the path,
    not that the handler succeeds without auth.

    `with`, because these are real routes: app.state.services is populated by
    create_app's lifespan, and without it every authenticated path raises
    AttributeError before the router's verdict is visible (the same trap
    tests/test_ui_mount.py records).
    """
    with TestClient(create_app(services)) as client:
        for entry in _endpoints(services):
            method, _, path = entry.partition(" ")
            if "{" in path:
                continue
            resp = client.request(method, path)
            assert resp.status_code != 404, f"{entry} is advertised and 404s"
