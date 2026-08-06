"""S8.4 Phase A: the tenancy backstop (spec §3.3).

Type signatures make OrgScopedReads scope by org; this guard makes sure org
handlers actually go THROUGH it. Like tests/test_route_table_guard.py it walks
the live route table, so it covers routes nobody has written yet -- which is
the property that makes a guard worth more than any number of hand-written
per-route tests.

The lesson inherited from that file, and the reason for the floor assertion
below: FastAPI 0.138 stores an ``_IncludedRouter`` wrapper rather than
flattening ``include_router``, so a naive walk sees NINE routes and misses all
of them. A guard that inspects nothing passes everything.
"""

from __future__ import annotations

import inspect
import re

from app.api.routes import require_org
from app.main import create_app
from tests.test_route_table_guard import _resolvers_on, _walk

#: Reads that bypass tenancy scoping. An org handler touching one of these is
#: reading across customers unless it filters by hand -- and "unless it filters
#: by hand" is the whole failure mode this guard exists to prevent.
FORBIDDEN = (
    r"\.report_store\b",
    r"\.candidates\b",
)

#: The sanctioned door.
SANCTIONED = ".screening_scope"


def _org_plane_endpoints(app):
    """Every route that establishes its principal via require_org."""
    for route, inherited in _walk(app.routes):
        if getattr(route, "endpoint", None) is None:
            continue
        if require_org in _resolvers_on(route, inherited):
            yield route


def test_the_walker_actually_finds_the_org_plane(services):
    """Non-vacuity. Without this the guard below can pass having seen nothing."""
    app = create_app(services)
    found = list(_org_plane_endpoints(app))
    assert len(found) >= 20, (
        f"only {len(found)} org-plane routes inspected -- the walker is broken, "
        f"and a guard that inspects nothing passes everything"
    )


def test_no_org_handler_reads_candidates_or_reports_unscoped(services):
    app = create_app(services)
    offenders = []
    for route in _org_plane_endpoints(app):
        source = inspect.getsource(route.endpoint)
        if SANCTIONED in source:
            continue
        for pattern in FORBIDDEN:
            if re.search(pattern, source):
                offenders.append(
                    f"{sorted(route.methods)} {route.path} "
                    f"reads {pattern} directly -- use services.screening_scope"
                )
    assert not offenders, "\n".join(offenders)


def test_the_guard_catches_an_unscoped_handler():
    """Prove the patterns can FAIL something. A guard nobody has seen go red is
    a green light, not a check.

    This pins the DETECTOR against a handler written the wrong way. Step 3 of
    this task additionally proves the guard red against the real route table --
    both matter, because a detector that matches nothing and a walker that
    finds nothing fail identically: silently, and green.
    """
    unscoped_source = (
        "async def bad_handler(request, org_id):\n"
        "    return _services(request).report_store.get('anything')\n"
    )
    assert SANCTIONED not in unscoped_source
    assert any(re.search(p, unscoped_source) for p in FORBIDDEN), (
        "the FORBIDDEN patterns no longer match a genuinely unscoped read"
    )
