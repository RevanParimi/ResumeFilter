"""S8.4 Phase B: the OpenAPI document is the client contract, so it is tested.

The wiring session had to DISCOVER the 401/403/404/409 forks by measurement
because the schema did not describe them. This file is the standing answer:
every property a generated client depends on is asserted over the LIVE schema,
so a route added next sprint inherits the requirement instead of quietly
opting out.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from app.main import create_app
from tests.test_route_table_guard import _walk


@pytest.fixture
def app(services):
    """Built the way tests/test_route_table_guard.py builds it -- from the test
    container, so nothing here reaches a real database or a real vendor."""
    return create_app(services)


def _api_routes(app):
    return [r for r, _ in _walk(app.routes) if isinstance(r, APIRoute)]


def test_every_route_has_an_explicit_operation_id(app):
    """Auto-derived ids are unique but unusable -- a generated client method
    called list_candidate_reports_candidates__candidate_id__reports_get is not
    a client anyone will keep."""
    for route in _api_routes(app):
        assert route.operation_id, f"{route.path} has no explicit operation_id"
        assert route.operation_id == route.name, (
            f"{route.path}: operation_id should be the handler name"
        )


def test_operation_ids_are_unique(app):
    """Two handlers sharing a name would silently collapse into one client
    method. This is the assertion the loop in create_app cannot make itself."""
    ids = [r.operation_id for r in _api_routes(app)]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate operation_ids: {sorted(dupes)}"


def test_every_route_declares_a_response_model(app):
    for route in _api_routes(app):
        assert route.response_model is not None, f"{route.path} declares no response_model"


def _is_untyped_object(schema: dict) -> bool:
    """The shape `-> dict` generates. `-> list[dict]` wraps the same shape in
    an array, so the check recurses through `items` -- the review found two
    routes (`GET /domains`, `GET /admin/users`) hiding behind an array while
    the object-only version of this test passed."""
    if schema.get("type") == "object" and schema.get("additionalProperties") is True:
        return True
    if schema.get("type") == "array":
        return _is_untyped_object(schema.get("items", {}))
    return False


def test_no_success_response_is_an_untyped_object(app):
    """`-> dict` generates Record<string, any> and puts the caller back to
    guessing. MEASURED at 38 of 90 before this sprint."""
    spec = app.openapi()
    untyped = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            for code, resp in op.get("responses", {}).items():
                if not code.startswith("2"):
                    continue
                schema = resp.get("content", {}).get("application/json", {}).get("schema", {})
                if _is_untyped_object(schema):
                    untyped.append(f"{method.upper()} {path}")
    assert not untyped, f"untyped success schemas: {untyped}"


def test_the_schema_covers_every_route(app):
    """Non-vacuity, in the S8.2 tradition: a walk that sees nothing passes
    everything. 90 routes existed when this was written."""
    spec = app.openapi()
    operations = sum(len(m) for m in spec["paths"].values())
    assert operations >= 88, f"only {operations} operations inspected"
