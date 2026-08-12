"""RightsStore (S8.3 Phase B): the only thing that touches the request table."""

from datetime import datetime, timezone

import pytest

from app.candidates.models import CandidateRow
from app.core.db import Base, make_engine, make_session_factory
from app.rights.schema import CorrectionField, RequestKind, RequestStatus, ResolvedBy
from app.rights.store import RightsStore

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


@pytest.fixture
def store():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return RightsStore(make_session_factory(engine))


def _candidate(store, name="Asha R") -> str:
    with store._session_factory() as s:
        row = CandidateRow(full_name=name)
        s.add(row)
        s.commit()
        return row.id


def _resolve_kwargs(**over):
    base = dict(
        status=RequestStatus.RESOLVED, resolution="done", applied=False,
        resolved_by=ResolvedBy.OPERATOR_KEY, resolved_by_admin_user_id=None,
        now=NOW,
    )
    base.update(over)
    return base


def test_a_new_request_is_open_and_unapplied(store):
    cid = _candidate(store)
    view = store.create(
        cid, kind=RequestKind.CORRECTION, field=CorrectionField.FULL_NAME,
        current_value="Asha R", requested_value="Asha Rao", note="",
    )
    assert view.status is RequestStatus.OPEN
    assert view.applied is False
    assert view.requested_value == "Asha Rao"
    assert view.current_value == "Asha R"
    assert view.resolved_by is None
    assert view.resolved_at is None


def test_a_candidate_sees_only_their_own(store):
    a, b = _candidate(store), _candidate(store, "Bilal K")
    store.create(a, kind=RequestKind.GRIEVANCE, field=None, current_value="",
                 requested_value="", note="nobody answered")
    assert [v.note for v in store.for_candidate(a)] == ["nobody answered"]
    assert store.for_candidate(b) == []


def test_resolve_records_the_decision_the_authorship_and_the_time(store):
    cid = _candidate(store)
    view = store.create(cid, kind=RequestKind.CORRECTION,
                        field=CorrectionField.FULL_NAME, current_value="Asha R",
                        requested_value="Asha Rao", note="")
    assert store.resolve(
        view.id, **_resolve_kwargs(resolution="name updated", applied=True)
    ) is True
    again = store.for_candidate(cid)[0]
    assert again.status is RequestStatus.RESOLVED
    assert again.applied is True
    assert again.resolution == "name updated"
    assert again.resolved_at == NOW
    assert again.resolved_by is ResolvedBy.OPERATOR_KEY


def test_resolving_an_already_resolved_request_is_refused_at_the_STORE(store):
    """The conditional UPDATE is the guard, not a read-then-write: two
    operators clicking Resolve on the same request must not both apply it, and
    an applied correction applied twice is a second write onto a person's row
    on the strength of one decision."""
    cid = _candidate(store)
    view = store.create(cid, kind=RequestKind.GRIEVANCE, field=None,
                        current_value="", requested_value="", note="x")
    assert store.resolve(view.id, **_resolve_kwargs()) is True
    assert store.resolve(view.id, **_resolve_kwargs()) is False


def test_a_REJECTED_request_is_equally_closed_to_a_second_decision(store):
    """The guard is `status == OPEN`, not `resolved_at IS NULL`: a rejection
    that could be quietly upgraded to an applied correction would make the
    written reason a draft."""
    cid = _candidate(store)
    view = store.create(cid, kind=RequestKind.CORRECTION,
                        field=CorrectionField.FULL_NAME, current_value="Asha R",
                        requested_value="Someone Else", note="")
    assert store.resolve(
        view.id, **_resolve_kwargs(status=RequestStatus.REJECTED, resolution="no")
    ) is True
    assert store.resolve(view.id, **_resolve_kwargs(applied=True)) is False


def test_resolving_an_unknown_id_is_False_not_an_exception(store):
    assert store.resolve("nope", **_resolve_kwargs()) is False


def test_get_returns_the_view_and_its_owner(store):
    cid = _candidate(store)
    view = store.create(cid, kind=RequestKind.GRIEVANCE, field=None,
                        current_value="", requested_value="", note="x")
    found = store.get(view.id)
    assert found is not None
    got, owner = found
    assert got.id == view.id and owner == cid
    assert store.get("nope") is None


def test_list_by_status_filters_and_None_means_all(store):
    cid = _candidate(store)
    open_one = store.create(cid, kind=RequestKind.GRIEVANCE, field=None,
                            current_value="", requested_value="", note="a")
    closed = store.create(cid, kind=RequestKind.GRIEVANCE, field=None,
                          current_value="", requested_value="", note="b")
    store.resolve(closed.id, **_resolve_kwargs(status=RequestStatus.REJECTED))
    assert [v.id for v in store.list_by_status(RequestStatus.OPEN, limit=50)] == \
           [open_one.id]
    assert len(store.list_by_status(None, limit=50)) == 2


def test_list_by_status_respects_its_limit(store):
    cid = _candidate(store)
    for i in range(4):
        store.create(cid, kind=RequestKind.GRIEVANCE, field=None,
                     current_value="", requested_value="", note=f"n{i}")
    assert len(store.list_by_status(None, limit=2)) == 2


def test_erasing_the_candidate_takes_their_requests_with_them(store):
    """CASCADE, and the opposite call from S8.5's outcomes.org_id -- a
    correction request is wholly the subject's own, and erasure is the
    stronger right."""
    cid = _candidate(store)
    store.create(cid, kind=RequestKind.GRIEVANCE, field=None, current_value="",
                 requested_value="", note="x")
    with store._session_factory() as s:
        s.delete(s.get(CandidateRow, cid))
        s.commit()
    assert store.for_candidate(cid) == []
