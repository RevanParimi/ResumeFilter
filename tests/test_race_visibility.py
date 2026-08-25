"""Six IntegrityError handlers do correct race handling and say nothing.

Each one is right: somebody else won the insert, so roll back and take their
row. But a race going from one a day to a thousand a minute is currently
undetectable, and that shift is the signal -- not the individual event, which
is why these log at INFO rather than warning.
"""

from __future__ import annotations

import pytest

from app.auth.store import OrgNameTaken


def _races(events):
    return [e for e in events if e.get("event") == "integrity_race"]


def test_a_duplicate_org_name_race_is_logged(services, log_events):
    store = services.auth._store
    store.create_org_with_owner(name="Acme Staffing", email_hash="hash-a")
    with pytest.raises(OrgNameTaken):
        store.create_org_with_owner(name="Acme Staffing", email_hash="hash-b")

    hits = _races(log_events)
    assert hits, "the race must leave a line"
    assert hits[0]["where"] == "AuthStore.create_org_with_owner"


def test_the_race_line_is_info_not_warning(services, log_events):
    """These races are EXPECTED and handled correctly. At warning they would be
    noise that trains an operator to ignore the channel -- and the channel is
    the one carrying real refusals since S9.3."""
    store = services.auth._store
    store.create_org_with_owner(name="Acme Staffing", email_hash="hash-a")
    with pytest.raises(OrgNameTaken):
        store.create_org_with_owner(name="Acme Staffing", email_hash="hash-b")
    assert _races(log_events)[0]["log_level"] == "info"


def test_the_refusal_behaviour_is_unchanged(services):
    """Only a log line was added. If this moves, the sprint changed behaviour
    in a store, which it has no business doing."""
    store = services.auth._store
    org_id, user = store.create_org_with_owner(name="Unique Name", email_hash="h")
    assert org_id and user is not None


def test_every_where_label_names_its_real_enclosing_method():
    """The label must be greppable, and NOTHING checked that it was.

    Found in the pre-merge review: FIVE of the six labels were taken from the
    implementation plan's table rather than read off the code, so they named
    methods that do not exist -- `record_request` for `RightsStore.create`,
    `open_window` for `RateLimitStore.hit`, and three more. OPERATING.md §10d
    tells an operator to watch these by rate and then find the site; a label
    that greps to nothing makes the line unactionable, and `where` is the only
    field on it that carries meaning.

    An AST guard rather than a fixed list, because a fixed list is a second
    copy of the same names and would drift exactly as the first one did.
    """
    import ast
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent / "src" / "app"
    checked = 0
    for path in root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        if "integrity_race" not in src:
            continue
        tree = ast.parse(src)
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            for fn in [n for n in cls.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                seg = ast.get_source_segment(src, fn) or ""
                for m in re.finditer(r'where="([^"]+)"', seg):
                    checked += 1
                    assert m.group(1) == f"{cls.name}.{fn.name}", (
                        f"{path.name}: label {m.group(1)!r} does not name its "
                        f"enclosing method {cls.name}.{fn.name!r}"
                    )
    assert checked == 6, f"expected 6 race labels, found {checked}"
