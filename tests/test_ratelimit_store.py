"""S8.3 Phase A: the counter row and the atomic increment."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import event, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ratelimit.models import RateLimitCounterRow
from app.ratelimit.store import RateLimitStore
from tests.conftest import make_candidate_store


@pytest.fixture
def session_factory():
    """A real SQLite schema, built the way every other store test builds one."""
    return make_candidate_store()._session_factory


def test_one_counter_per_key_and_window(session_factory):
    """The unique constraint is what makes the INSERT race resolvable: the
    loser gets an IntegrityError instead of a second row nobody counts."""
    with session_factory() as session:
        session.add(RateLimitCounterRow(
            bucket_key="k", window_start=100, count=1, expires_at=None,
        ))
        session.commit()
    with session_factory() as session:
        session.add(RateLimitCounterRow(
            bucket_key="k", window_start=100, count=1, expires_at=None,
        ))
        with pytest.raises(IntegrityError):
            session.commit()


def test_the_same_key_in_a_later_window_is_a_different_row(session_factory):
    with session_factory() as session:
        session.add(RateLimitCounterRow(bucket_key="k", window_start=100, count=1))
        session.add(RateLimitCounterRow(bucket_key="k", window_start=200, count=1))
        session.commit()
        assert session.query(RateLimitCounterRow).count() == 2


def _store(session_factory) -> RateLimitStore:
    return RateLimitStore(session_factory)


def test_the_first_hit_is_allowed_and_creates_the_row(session_factory):
    store = _store(session_factory)
    assert store.hit(bucket_key="k", window_start=100, limit=3, expires_at=None)
    with session_factory() as session:
        assert session.query(RateLimitCounterRow).one().count == 1


def test_hits_are_allowed_up_to_the_limit_then_refused(session_factory):
    store = _store(session_factory)
    assert [
        store.hit(bucket_key="k", window_start=100, limit=3, expires_at=None)
        for _ in range(5)
    ] == [True, True, True, False, False]


def test_a_refused_hit_does_not_increment_past_the_limit(session_factory):
    """Otherwise the count climbs forever under attack, and the number is what
    the deny metric reports."""
    store = _store(session_factory)
    for _ in range(6):
        store.hit(bucket_key="k", window_start=100, limit=2, expires_at=None)
    with session_factory() as session:
        assert session.query(RateLimitCounterRow).one().count == 2


def test_a_new_window_starts_a_fresh_count(session_factory):
    store = _store(session_factory)
    for _ in range(3):
        store.hit(bucket_key="k", window_start=100, limit=3, expires_at=None)
    assert store.hit(bucket_key="k", window_start=100, limit=3, expires_at=None) is False
    assert store.hit(bucket_key="k", window_start=200, limit=3, expires_at=None) is True


def test_opening_a_new_window_purges_the_old_row_for_that_key(session_factory):
    """Bounded housekeeping on a path that already runs -- the S7.1 challenge
    hygiene precedent. The Phase B sweep still owns the general case, for keys
    that are never seen again."""
    store = _store(session_factory)
    store.hit(bucket_key="k", window_start=100, limit=3, expires_at=None)
    store.hit(bucket_key="k", window_start=200, limit=3, expires_at=None)
    with session_factory() as session:
        rows = session.query(RateLimitCounterRow).all()
        assert [r.window_start for r in rows] == [200]


def test_keys_do_not_share_a_counter(session_factory):
    store = _store(session_factory)
    for _ in range(3):
        store.hit(bucket_key="a", window_start=100, limit=3, expires_at=None)
    assert store.hit(bucket_key="a", window_start=100, limit=3, expires_at=None) is False
    assert store.hit(bucket_key="b", window_start=100, limit=3, expires_at=None) is True


def test_a_limit_of_zero_refuses_without_creating_a_row(session_factory):
    """Config forbids 0 (ge=1), so this is defence in depth -- but the naive
    implementation would INSERT count=1 and ALLOW, which is the opposite of
    what a zero limit means."""
    store = _store(session_factory)
    assert store.hit(bucket_key="k", window_start=100, limit=0, expires_at=None) is False
    with session_factory() as session:
        assert session.query(RateLimitCounterRow).count() == 0


def test_expires_at_is_written_for_the_phase_b_sweep(session_factory):
    store = _store(session_factory)
    when = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
    store.hit(bucket_key="k", window_start=100, limit=3, expires_at=when)
    with session_factory() as session:
        assert session.query(RateLimitCounterRow).one().expires_at is not None


def test_the_conditional_update_refuses_a_row_already_at_its_limit(session_factory):
    """THE RACE, built directly on the seam.

    S8.4 Phase B measured this exact trap: two mutants on ScreeningStore's
    claim SURVIVED every end-to-end test, because the race they defend against
    is unreachable through two sequential public calls -- the second call's own
    read filters the row out long before the UPDATE matters. So the conditional
    UPDATE is driven here directly, in the one state where ONLY its
    `count < limit` clause can refuse.
    """
    store = _store(session_factory)
    store.hit(bucket_key="k", window_start=100, limit=1, expires_at=None)
    with session_factory() as session:
        assert store._try_increment(
            session, bucket_key="k", window_start=100, limit=1
        ) is False
        # ...and the same row IS incrementable under a higher limit, which is
        # what proves the refusal came from the clause and not from the row
        # being missing.
        assert store._try_increment(
            session, bucket_key="k", window_start=100, limit=5
        ) is True


def test_a_colliding_insert_is_RECOVERED_and_never_escapes_hit(session_factory):
    """The `except IntegrityError` arm of `hit`, which nothing else reaches.

    The dangerous thing about that arm is not the rollback -- it is what comes
    AFTER it. `hit` calls `session.commit()` on a session whose failed INSERT
    was still pending, and if SQLAlchemy did not expunge that pending row on
    rollback the commit would re-flush it and raise a SECOND IntegrityError,
    out of `hit`, past every 429 handler, to the client as a 500. A limiter
    that answers 500 under exactly the concurrency it exists for is worse than
    no limiter, because the error looks like a bug in the endpoint.

    The collision is planted on the session's OWN connection. A rival on a
    genuinely separate connection is not constructible on SQLite -- measured
    during the S8.3 review: an in-memory database shares one connection through
    StaticPool, and a file database in WAL mode answers `OperationalError:
    database is locked` rather than letting the rival commit. The
    IntegrityError arm is therefore the POSTGRES shape of this race, which is
    the deployment target (prod refuses to boot on SQLite). What this test
    pins is the recovery, which is dialect-independent.
    """
    store = RateLimitStore(session_factory)
    fired: list[bool] = []

    @event.listens_for(Session, "before_flush")
    def plant_the_collision(session, flush_context, instances):
        if fired or not any(
            isinstance(obj, RateLimitCounterRow) for obj in session.new
        ):
            return
        fired.append(True)
        session.connection().execute(
            insert(RateLimitCounterRow.__table__).values(
                id="rival", bucket_key="k", window_start=100,
                count=1, expires_at=None,
            )
        )

    try:
        allowed = store.hit(
            bucket_key="k", window_start=100, limit=3, expires_at=None
        )
    finally:
        event.remove(Session, "before_flush", plant_the_collision)

    assert fired, "the collision never fired; this test proved nothing"
    assert allowed in (True, False), "hit must answer, not raise"

    # AN ALLOWED HIT IS A COUNTED HIT. Whatever the arm decides, the decision
    # and the table have to agree -- an arm that simply returned True would
    # hand out an allowance no counter ever recorded, so the next caller would
    # be allowed too, and the bucket would never fill.
    with session_factory() as session:
        counted = sum(
            row.count for row in session.query(RateLimitCounterRow)
            .filter_by(bucket_key="k", window_start=100)
        )
    assert counted >= 1 if allowed else counted == 0


def test_a_recovered_collision_leaves_no_half_written_row(session_factory):
    """The rollback in the middle of `hit` must take the whole attempt with it.

    A row left behind by the failed INSERT would be a counter nobody ever
    increments again -- it holds the bucket at a count that no longer tracks
    anything, and every later hit in that window would be measured against a
    number that came from a crash.
    """
    store = RateLimitStore(session_factory)
    fired: list[bool] = []

    @event.listens_for(Session, "before_flush")
    def plant_the_collision(session, flush_context, instances):
        if fired or not any(
            isinstance(obj, RateLimitCounterRow) for obj in session.new
        ):
            return
        fired.append(True)
        session.connection().execute(
            insert(RateLimitCounterRow.__table__).values(
                id="rival", bucket_key="k", window_start=100,
                count=1, expires_at=None,
            )
        )

    try:
        store.hit(bucket_key="k", window_start=100, limit=3, expires_at=None)
    finally:
        event.remove(Session, "before_flush", plant_the_collision)

    with session_factory() as session:
        rows = session.query(RateLimitCounterRow).all()
        assert len(rows) <= 1, "the failed INSERT left a duplicate behind"
        # And the store is still usable afterwards: a session left in a failed
        # transaction would raise PendingRollbackError on the very next hit.
        assert store.hit(
            bucket_key="k", window_start=100, limit=3, expires_at=None
        ) in (True, False)
