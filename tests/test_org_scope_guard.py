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

Also folded in: FORBIDDEN requires the access to be off a services-ish receiver
(``services.candidates`` / ``_services(request).candidates``), not any object
with a same-named attribute -- a future unrelated ``.candidates`` on some other
object should not trip a tenancy guard.

Second fix round (post whole-branch review): qualifying to the *literal* name
``services`` meant the guard was defeated by naming the local something else.
``svc = _services(request)`` then ``svc.report_store.get(...)`` sailed straight
through -- and that is not an adversarial shape, it is a name a developer picks
without thinking. The receiver set is now resolved by AST per source: any local
bound to ``_services(request)`` counts. A second hole closed with it: a
SANCTIONED call and a FORBIDDEN call on ONE physical line (``... screening_scope
.report(...) or services.report_store.get(...)``) used to be waved through by
the sanctioned check, so the sanctioned expressions are now *removed* from the
line and the FORBIDDEN patterns are matched against what remains.

WHAT THIS GUARD DOES NOT COVER -- stated because a guard's whole value is its
honesty about its own reach:

* Exactly TWO attributes, ``report_store`` and ``candidates``.
  ``services.features`` / ``.jobs`` / ``.ledger`` / ``.portal`` /
  ``.verification`` / ``.interview`` / ``.dashboard`` / ``.comp`` are invisible
  to it. That matters: ``POST /jobs/{id}/match`` and ``GET /jobs/{id}/board``
  are org-plane routes reading the global feature store unfiltered (TENANCY.md
  §8), and this guard would not notice.
* ONE hop, within ``routes.py`` only -- helpers in other modules are skipped
  outright. A read two hops of delegation deep passes unseen.
* Line-level, not dataflow. A store handed to a local and called on a later
  line through an alias of the ATTRIBUTE (rather than of the services
  container) is caught only because ``store = _services(request).report_store``
  puts the forbidden attribute on the assignment line itself.
* Receivers are resolved for the three plain-name binding forms (``=``,
  annotated ``:`` and walrus ``:=``). NOT covered, measured: tuple unpacking
  (``svc, x = _services(request), 1``), the container passed into a helper as
  an ARGUMENT, ``getattr(services, "report_store")``, a backslash line
  continuation splitting the receiver from the attribute, and the inline
  ``_services(<name>)`` spelling when the parameter is called anything but
  ``request`` (that regex hardcodes it; the AST path is argument-agnostic, so
  only the inline form is affected).

None of those are defended against here, and this list is the point: a guard
whose reach is overstated is worse than a narrow one, because the overstatement
is what stops somebody adding the check that would have caught the next bug.
"""

from __future__ import annotations

import ast
import inspect
import io
import re
import textwrap
import tokenize

from app.api.routes import require_org
from app.main import create_app
from tests.test_route_table_guard import _resolvers_on, _walk

#: Store attributes that bypass tenancy scoping when read off the services
#: container. Qualified to a services-ish receiver so a same-named attribute on
#: an unrelated object can't trip this.
WATCHED_ATTRS = ("report_store", "candidates")

#: The sanctioned doors. Both take org_id as the first argument of every method
#: and neither exposes an unscoped read: `screening_scope` (Phase A, reports and
#: candidates) and `screening` (Phase B, batches). The batch STORE is
#: deliberately not on `Services` at all, so there is nothing unscoped for a
#: handler to reach in the first place.
SCOPED_ATTRS = ("screening_scope", "screening")

#: The conventional receiver name, always in the set even when the source never
#: spells the assignment out (e.g. an inline ``_services(request).X``).
_DEFAULT_RECEIVER = "services"


def _is_services_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_services"
    )


def _service_receivers(source: str) -> set[str]:
    """Every local name bound to ``_services(request)`` in this source.

    This is the fix for the alias bypass: the guard used to hardcode the name
    ``services``, so renaming the local to ``svc`` -- an ordinary choice, not an
    attack -- disabled every check in the handler.

    All three binding forms Python offers for a plain name are covered:
    ``svc = _services(request)`` (Assign), ``svc: Services = _services(request)``
    (AnnAssign -- this codebase does annotate locals), and
    ``if (svc := _services(request))`` (NamedExpr). Tuple unpacking is not, and
    is disclosed in the module docstring rather than silently missing.
    """
    names = {_DEFAULT_RECEIVER}
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:  # pragma: no cover - handler source always parses
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_services_call(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and _is_services_call(node.value):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
        elif isinstance(node, ast.NamedExpr) and _is_services_call(node.value):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
    return names


def _code_lines(source: str) -> list[str]:
    """Source lines with comments AND string literals blanked out.

    Docstrings are the reason. This codebase documents its own rules densely --
    a handler docstring reading "never read services.report_store; use
    services.screening_scope" is entirely plausible, and under the residue
    technique below it would read as a violation. A guard that fires on correct
    code gets switched off within a sprint, so prose cannot be allowed to forge
    either a violation or the sanctioned door.

    ``tokenize`` rather than a regex: it handles triple-quoted docstrings
    spanning many lines, a ``#`` inside a string, and a quote inside a comment,
    none of which a line-wise regex gets right.
    """
    text = textwrap.dedent(source)
    rows = [list(line) for line in text.splitlines()]
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # pragma: no cover - fall back to the cruder comment strip
        return [line.split("#", 1)[0] for line in text.splitlines()]
    for tok in tokens:
        if tok.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        for row_index in range(srow - 1, min(erow, len(rows))):
            row = rows[row_index]
            start = scol if row_index == srow - 1 else 0
            end = ecol if row_index == erow - 1 else len(row)
            for col in range(start, min(end, len(row))):
                row[col] = " "
    return ["".join(row) for row in rows]


def _receiver_alternation(receivers: set[str]) -> str:
    return "|".join(re.escape(name) for name in sorted(receivers))


def _forbidden_res(receivers: set[str]) -> list[tuple[str, re.Pattern[str]]]:
    alt = _receiver_alternation(receivers)
    return [
        (
            attr,
            re.compile(rf"(?:\b(?:{alt})\.{attr}\b|_services\(request\)\.{attr}\b)"),
        )
        for attr in WATCHED_ATTRS
    ]


def _sanctioned_re(receivers: set[str]) -> re.Pattern[str]:
    alt = _receiver_alternation(receivers)
    # `screening_scope` FIRST in the alternation: `screening` alone would match
    # its prefix, and while the trailing \b happens to save us today (`_` is a
    # word character), depending on that is exactly the kind of accident that
    # turns a guard off without anyone noticing.
    doors = "|".join(sorted(SCOPED_ATTRS, key=len, reverse=True))
    return re.compile(
        rf"\b(?:{alt})\.(?:{doors})\b|_services\(request\)\.(?:{doors})\b"
    )

#: EMPTY, and that is the point (S8.4 Phase B, Task 6). Every entry here was a
#: line of `_ingest_one`, which moved to app/screening/ingest.py -- so the guard
#: now runs with NO exemptions at all. A content-keyed allowlist whose keys no
#: longer exist is not harmless: it is a silent exemption waiting to match an
#: unrelated future line that happens to contain the same text.
#:
#: The exemptions were never the bound anyway. The one genuinely cross-tenant
#: read among them, `similar_resumes` (fraud detection must scan the WHOLE
#: platform's fingerprints or a resume seeded across customers goes unseen), is
#: still bounded exactly where it was: at the org-plane boundary, by
#: `redact_ingest_response_for_org`.
ALLOWLISTED_LINES: dict[str, str] = {}


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
    """Watched attribute reads, matched one physical LINE at a time.

    A line is a violation unless it is on the narrow allowlist. Checking the
    whole function for the sanctioned door (the original behavior) let one
    mention anywhere silence every other line in the function; checking whether
    the LINE mentions it (the first fix round) still let one line do both. So
    the sanctioned expressions are DELETED from the line and the watched
    patterns are matched against the residue: a line that only reaches the
    facade has nothing left to match, and a line that reaches the facade AND a
    store still shows the store.

    The receiver set is resolved from this source, so an aliased container
    (``svc = _services(request)``) is caught like the conventional name.
    """
    receivers = _service_receivers(source)
    sanctioned = _sanctioned_re(receivers)
    forbidden = _forbidden_res(receivers)

    hits = []
    for code in _code_lines(source):
        # Remove the sanctioned door AND any allowlisted expression, then see
        # what is left. Both are removals rather than whole-line skips for the
        # same reason: a line that reaches an exempt thing AND a store still
        # reaches a store.
        residue = sanctioned.sub("", code)
        for key in ALLOWLISTED_LINES:
            if key in residue:
                residue = residue.replace(key, "")
        for _attr, pattern in forbidden:
            found = pattern.search(residue)
            if found:
                # Report what was actually written, not a canonical spelling --
                # a developer greps for the text in their file.
                hits.append(found.group(0))
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
            for read in _violations_in(source):
                offenders.append(
                    f"{sorted(route.methods)} {route.path} ({label}) "
                    f"reads {read} directly -- use services.screening_scope"
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
    assert not _sanctioned_re(_service_receivers(unscoped_source)).search(unscoped_source)
    assert _violations_in(unscoped_source), (
        "the watched patterns no longer match a genuinely unscoped read"
    )


def test_the_guard_does_not_let_one_mention_silence_a_neighboring_violation():
    """Fix-round regression pin for finding 1: a sanctioned mention on one
    line must not suppress a watched read on a different line in the same
    function. The pre-fix-round guard did exactly this with a whole-function
    substring check."""
    mixed_source = (
        "async def half_migrated(request, org_id):\n"
        "    services = _services(request)\n"
        "    ok = services.screening_scope.report(org_id, 'x')\n"
        "    # falls back through services.screening_scope on some path\n"
        "    return ok or services.report_store.get('x')\n"
    )
    assert _sanctioned_re(_service_receivers(mixed_source)).search(mixed_source), (
        "the sanctioned door must still be present somewhere"
    )
    assert _violations_in(mixed_source), (
        "a real violation on its own line must not be silenced by a "
        "sanctioned mention elsewhere in the function"
    )


def test_the_guard_survives_a_renamed_services_local():
    """Second-fix-round pin: the guard used to hardcode the receiver name
    ``services``, so calling the local anything else disabled every check in
    the handler. That is not an adversarial shape -- it is a name somebody
    picks without thinking, which makes it the likeliest way this guard would
    ever have failed silently."""
    for alias in ("svc", "s", "container"):
        source = (
            "async def bad_handler(request, org_id):\n"
            f"    {alias} = _services(request)\n"
            f"    return {alias}.report_store.get('anything')\n"
        )
        assert alias in _service_receivers(source), (
            f"{alias!r} is bound to _services(request) and must count as a receiver"
        )
        assert _violations_in(source), (
            f"an unscoped read through a local named {alias!r} must still be caught"
        )


def test_the_guard_catches_a_violation_sharing_a_line_with_the_facade():
    """Second-fix-round pin: one physical line doing BOTH -- reaching the
    facade and falling back to the store -- was waved through, because the
    line mentioned the sanctioned door. The sanctioned expressions are now
    removed before the watched patterns are matched."""
    one_liner = (
        "async def sneaky(request, org_id):\n"
        "    services = _services(request)\n"
        "    return services.screening_scope.report(org_id, 'x')"
        " or services.report_store.get('x')\n"
    )
    assert _violations_in(one_liner), (
        "a store read sharing a line with a facade call is still a store read"
    )


def test_every_plain_name_binding_form_resolves_the_receiver():
    """Re-review pin: the resolver handled only ``=``, so an ANNOTATED local --
    a form this codebase already uses (``report: Optional[Report] = None``) --
    slipped through, as did a walrus. That is the same
    a-name-somebody-picks-without-thinking shape the alias fix was about."""
    forms = {
        "plain": "    svc = _services(request)\n",
        "annotated": "    svc: Services = _services(request)\n",
        "walrus": "    if (svc := _services(request)) is None:\n        return None\n",
    }
    for label, binding in forms.items():
        source = (
            "async def bad_handler(request, org_id):\n"
            f"{binding}"
            "    return svc.report_store.get('anything')\n"
        )
        assert "svc" in _service_receivers(source), f"{label} binding not resolved"
        assert _violations_in(source), f"{label}: unscoped read must be caught"


def test_prose_cannot_forge_a_violation_or_the_sanctioned_door():
    """Re-review pin: the residue technique made a DOCSTRING naming both doors
    read as a violation. This codebase documents its own rules densely, so that
    is the plausible way this guard gets switched off -- and the converse
    (prose mentioning screening_scope silencing a real read) is how it goes
    quietly blind."""
    documented = (
        "async def good_handler(request, org_id):\n"
        '    """Never read services.report_store here; use'
        ' services.screening_scope."""\n'
        "    svc = _services(request)\n"
        "    return svc.screening_scope.report(org_id, 'x')\n"
    )
    assert not _violations_in(documented), (
        "a docstring quoting the rule is not a breach of it"
    )

    prose_shield = (
        "async def sneaky(request, org_id):\n"
        '    """We go through services.screening_scope, honest."""\n'
        "    services = _services(request)\n"
        "    return services.report_store.get('x')\n"
    )
    assert _violations_in(prose_shield), (
        "prose must not stand in for actually calling the facade"
    )


def test_an_allowlisted_line_does_not_shield_a_neighbouring_read():
    """Re-review pin: the allowlist skipped the whole line with ``continue`` --
    the identical shape already closed for the sanctioned door. An allowlisted
    expression sharing a line with a genuine read must not launder it."""
    shared_line = (
        "async def sneaky(request, org_id):\n"
        "    services = _services(request)\n"
        "    return services.candidates.save_fingerprint(f)"
        " or services.report_store.get('x')\n"
    )
    assert _violations_in(shared_line), (
        "an allowlisted call on the same line must not exempt the store read"
    )


def test_the_offender_message_names_the_real_spelling():
    """A failure reporting ``services.report_store`` for a read written
    ``svc.report_store`` sends a developer grepping for a string that is not in
    their file."""
    source = (
        "async def bad_handler(request, org_id):\n"
        "    svc = _services(request)\n"
        "    return svc.report_store.get('anything')\n"
    )
    assert _violations_in(source) == ["svc.report_store"]


def test_a_purely_scoped_handler_is_not_a_false_positive():
    """The other direction: stripping the sanctioned expressions must not
    leave residue that trips the watched patterns. A guard that cried wolf on
    correct code would be turned off within a sprint."""
    clean_source = (
        "async def good_handler(request, org_id):\n"
        "    svc = _services(request)\n"
        "    return svc.screening_scope.reports_for_candidate(org_id, 'cand')\n"
    )
    assert not _violations_in(clean_source)


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


def test_the_guard_has_no_exemptions():
    """If a line ever needs allowlisting again, this test is where a reviewer is
    forced to look at the reason."""
    assert ALLOWLISTED_LINES == {}


def test_the_batch_store_is_not_reachable_from_the_services_container():
    """Structural, not stylistic: a handler cannot forget to scope a read it
    has no way to perform."""
    from app.services import Services

    assert "screening_store" not in Services.__dataclass_fields__
    assert not hasattr(Services, "batches")
