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

Fix round (post-review): the first cut of this guard had two escape hatches of
its own -- the exact "a guard nobody has watched fail is a green light, not a
check" problem one level up.

1. ``SANCTIONED in source`` was a whole-FUNCTION substring test: one mention
   of ``.screening_scope`` anywhere in a handler -- a comment, a docstring, an
   unrelated branch -- silenced every ``FORBIDDEN`` check in that function.
   Fixed by checking one physical line at a time: a line matching FORBIDDEN is
   a violation unless THAT line goes through the sanctioned door.
2. The guard inspected only ``inspect.getsource(route.endpoint)`` -- the
   handler body -- and missed reads delegated to a same-module helper, which
   is this codebase's own anti-duplication convention (``_ingest_one`` is
   shared by the admin and org upload routes for exactly that reason). Fixed
   by resolving bare, same-module function calls made directly in the handler
   and inspecting those too -- ONE hop, not a full call graph: a helper
   calling a helper calling an unscoped read is a real but much rarer shape,
   and unbounded traversal would make the guard fragile (attribute a
   violation to which frame? recurse into the whole app?) for a gain the one
   hop already covers for this codebase's actual shape.

Also folded in: FORBIDDEN now requires the access to be off a ``services``-ish
receiver (``services.candidates`` / ``_services(request).candidates``), not
any object with a same-named attribute -- a future unrelated ``.candidates``
on some other object should not trip a tenancy guard.
"""

from __future__ import annotations

import ast
import inspect
import re

from app.api.routes import require_org
from app.main import create_app
from tests.test_route_table_guard import _resolvers_on, _walk

#: Reads that bypass tenancy scoping, qualified to the services container so a
#: same-named attribute on an unrelated object can't trip this. Two spellings
#: cover the two styles the routes module uses: ``services = _services(request)``
#: then ``services.X``, or the inline ``_services(request).X``.
FORBIDDEN = (
    r"(?:\bservices\.report_store\b|_services\(request\)\.report_store\b)",
    r"(?:\bservices\.candidates\b|_services\(request\)\.candidates\b)",
)

#: The sanctioned door, qualified the same way.
SANCTIONED = re.compile(r"\bservices\.screening_scope\b|_services\(request\)\.screening_scope\b")

#: Narrow, LINE-level exemptions -- not function-level, so one entry can't
#: silence a neighboring genuine violation the way the old whole-function
#: SANCTIONED check did. Keyed by a distinctive substring of the exact
#: offending line: if the line changes, the key stops matching and the access
#: has to be re-justified rather than grandfathered in forever.
#:
#: All five entries are in ``_ingest_one`` (app/api/routes.py), reached one hop
#: from ``screening_create_candidate`` (POST /screening/candidates). Read
#: closely: the rule this guard enforces is about READS that can cross a
#: tenant boundary and REACH an org caller unredacted, not "any store access"
#: -- a write that stamps org_id is the S8.4 ownership mechanism itself, and a
#: cross-tenant read whose output is redacted before an org sees it is a
#: different failure mode than the one this guard exists to catch.
ALLOWLISTED_LINES = {
    "services.candidates.ingest(result, text, org_id=org_id)": (
        "a WRITE that stamps org_id -- the S8.4 ownership mechanism itself, "
        "not a cross-tenant read."
    ),
    "services.report_store.save(report, org_id=org_id)": (
        "a WRITE that stamps org_id -- same as above."
    ),
    "services.candidates.save_fingerprint(": (
        "a WRITE of a content fingerprint keyed by resume_id/candidate_id "
        "this SAME call's own ingest() just produced (see above); it returns "
        "nothing to the caller, so there is nothing to leak across a tenant "
        "boundary."
    ),
    "services.candidates.get_candidate(outcome.candidate_id) is None": (
        "reads a candidate row by an id THIS SAME request's own org-scoped "
        "write produced moments earlier (never a caller-supplied id), and "
        "only returns a boolean -- a post-write erasure-race check, not a "
        "lookup of someone else's data."
    ),
    "matches, corpus = services.candidates.similar_resumes(": (
        "cross-tenant BY DESIGN, not a bug: farm/fraud detection has to scan "
        "the WHOLE platform's fingerprints, not just this org's own, to catch "
        "a resume seeded across customers -- excluding only the uploader's "
        "own candidate would defeat the check. This line was found and left "
        "RED on purpose by the prior review round (it named a real leak: the "
        "response carried these ids to an org caller unredacted). It is now "
        "allowlisted because the leak is fixed at the boundary, not because "
        "the read changed: screening_create_candidate calls "
        "redact_ingest_response_for_org (app/screening/projection.py) on the "
        "return value of _ingest_one before answering the org caller, which "
        "strips candidate_id/resume_id from every match in BOTH the "
        "top-level resume_farm and the embedded report's own resume_farm. "
        "The admin route (POST /candidates) returns this same read "
        "unredacted on purpose -- that is the operator's cross-tenant "
        "support view -- and is not reached by this guard because it is not "
        "gated by require_org."
    ),
}


def _org_plane_endpoints(app):
    """Every route that establishes its principal via require_org."""
    for route, inherited in _walk(app.routes):
        if getattr(route, "endpoint", None) is None:
            continue
        if require_org in _resolvers_on(route, inherited):
            yield route


def _strip_comment(line: str) -> str:
    """Best-effort: drop a trailing ``#`` comment.

    Not a real tokenizer -- a ``#`` inside a string literal would cut early --
    but every pattern this guard looks for is a plain, unquoted attribute
    access, so this is enough to stop a comment or docstring line from forging
    the sanctioned door for a neighboring line that doesn't actually call it.
    """
    return line.split("#", 1)[0]


def _violations_in(source: str) -> list[str]:
    """FORBIDDEN patterns matched one physical LINE at a time.

    A line is a violation only if that line itself doesn't go through the
    sanctioned door and isn't on the narrow allowlist above. Checking the
    whole function for ``SANCTIONED`` (the pre-fix-round behavior) let one
    mention anywhere silence every other line in the function -- this is the
    per-statement replacement for that.
    """
    hits = []
    for line in source.splitlines():
        code = _strip_comment(line)
        if SANCTIONED.search(code):
            continue
        stripped = code.strip()
        if any(key in stripped for key in ALLOWLISTED_LINES):
            continue
        for pattern in FORBIDDEN:
            if re.search(pattern, code):
                hits.append(pattern)
    return hits


def _called_helper_names(source: str) -> set[str]:
    """Bare, same-module function names called directly in this source.

    Only plain-identifier calls (``_ingest_one(...)``), not attribute calls
    (``x.method()``) -- those are store/service calls FORBIDDEN/SANCTIONED
    already look at directly. Used to find the ONE hop from a handler to a
    helper it delegates to.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - handler source always parses
        return set()
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _one_hop_sources(route) -> list[tuple[str, str]]:
    """(label, source) pairs to inspect for this route: its own handler, plus
    any same-module helper function it calls directly.

    ONE hop, not a full call graph: a helper calling a helper calling an
    unscoped read is a real but rarer shape, and unbounded traversal would
    make the guard fragile -- which frame owns a violation, and does the walk
    ever terminate for code that isn't a strict DAG? One hop already covers
    this codebase's actual anti-duplication shape: routes.py extracts a
    handler's body into a module-level ``_helper`` shared by two routes
    (``_ingest_one`` is exactly this), and that is the shape a future
    violation would arrive through -- a helper extracted from a route that
    used the facade, reused by a new route that forgets to.
    """
    endpoint = route.endpoint
    module = inspect.getmodule(endpoint)
    own_source = inspect.getsource(endpoint)
    sources = [(endpoint.__qualname__, own_source)]
    for name in _called_helper_names(own_source):
        helper = getattr(module, name, None)
        if helper is None or not inspect.isfunction(helper):
            continue
        if inspect.getmodule(helper) is not module:
            continue
        sources.append((f"{endpoint.__qualname__} -> {name}", inspect.getsource(helper)))
    return sources


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
        for label, source in _one_hop_sources(route):
            for pattern in _violations_in(source):
                offenders.append(
                    f"{sorted(route.methods)} {route.path} ({label}) "
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
        "    services = _services(request)\n"
        "    return services.report_store.get('anything')\n"
    )
    assert not SANCTIONED.search(unscoped_source)
    assert _violations_in(unscoped_source), (
        "the FORBIDDEN patterns no longer match a genuinely unscoped read"
    )


def test_the_guard_does_not_let_one_mention_silence_a_neighboring_violation():
    """Fix-round regression pin for finding 1: a SANCTIONED mention on one
    line must not suppress a FORBIDDEN read on a different line in the same
    function. The pre-fix-round guard did exactly this with a whole-function
    substring check."""
    mixed_source = (
        "async def half_migrated(request, org_id):\n"
        "    services = _services(request)\n"
        "    ok = services.screening_scope.report(org_id, 'x')\n"
        "    # falls back through services.screening_scope on some path\n"
        "    return ok or services.report_store.get('x')\n"
    )
    assert SANCTIONED.search(mixed_source), "the sanctioned door must still be present somewhere"
    assert _violations_in(mixed_source), (
        "a real violation on its own line must not be silenced by a "
        "SANCTIONED mention elsewhere in the function"
    )


def test_the_guard_reaches_one_hop_into_a_same_module_helper():
    """Fix-round regression pin for finding 2: an unscoped read hidden in a
    helper the handler calls -- not in the handler's own body -- must still be
    caught. This is the shape ``_ingest_one`` actually has once it is walked."""
    handler_source = (
        "async def thin_wrapper(request, org_id):\n"
        "    return await _helper(request, org_id)\n"
    )
    helper_source = (
        "async def _helper(request, org_id):\n"
        "    services = _services(request)\n"
        "    return services.candidates.get_candidate('x')\n"
    )
    assert not _violations_in(handler_source), (
        "the handler's own body has no violation -- the point is that the "
        "helper it delegates to does"
    )
    assert _violations_in(helper_source), (
        "the helper itself must still read as a violation once reached"
    )
    assert _called_helper_names(handler_source) == {"_helper"}
