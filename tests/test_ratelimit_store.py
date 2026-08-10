"""S8.3 Phase A: the counter row and the atomic increment."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.ratelimit.models import RateLimitCounterRow
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
