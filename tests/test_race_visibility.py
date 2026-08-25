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
    assert hits[0]["where"] == "create_org_with_owner"


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
