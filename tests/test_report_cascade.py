"""The point of folding reports into the main DB (PI-8 §2.1).

Before this, `reports` lived in a second SQLite database with no foreign key to
`candidates`. Erasure worked only because two route handlers each remembered to
call `delete_for_candidate` before `delete_candidate`. Nothing enforced it, no
FK could catch a third entry point forgetting, and no error would be raised --
the full depth evaluation, verdicts and fabrication analysis of an erased person
would simply be orphaned.

These tests use NO route and NO report store. If they pass, the guarantee lives
in the database.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.candidates.models import CandidateRow
from app.reports.models import OutcomeRow, ReportRow
from tests.conftest import make_candidate_store


@pytest.fixture
def store():
    return make_candidate_store()


def _candidate(store, cid: str = "cand_1") -> str:
    with store._session_factory() as s:
        s.add(CandidateRow(id=cid))
        s.commit()
    return cid


def _report(store, *, candidate_id: str | None, report_id: str = "rep_cascade_1"):
    with store._session_factory() as s:
        s.add(ReportRow(
            id=report_id, domain="genai", depth_band="solid",
            candidate_id=candidate_id, body={"id": report_id},
            created_at=datetime.now(timezone.utc),
        ))
        # Flushed before the outcome: the two rows carry no ORM relationship, so
        # nothing orders these inserts for us, and the child's FK is real.
        s.flush()
        s.add(OutcomeRow(
            report_id=report_id, claim_id=None, outcome="inconclusive",
            notes="", recorded_at=datetime.now(timezone.utc),
            # S8.5: NOT NULL with no server default, so a row must state its
            # own provenance. These tests are about the erasure FKs, and every
            # outcome that existed before that column did was an operator's.
            recorded_by="operator",
        ))
        s.commit()


def test_deleting_a_candidate_cascades_their_reports(store):
    cid = _candidate(store)
    _report(store, candidate_id=cid)

    store.delete_candidate(cid)

    with store._session_factory() as s:
        assert s.execute(select(ReportRow)).scalars().all() == []


def test_deleting_a_candidate_cascades_outcomes_too(store):
    cid = _candidate(store)
    _report(store, candidate_id=cid)

    store.delete_candidate(cid)

    with store._session_factory() as s:
        assert s.execute(select(OutcomeRow)).scalars().all() == []


def test_an_unattached_report_survives_every_erasure(store):
    """POST /evaluate makes reports with no candidate. Nullable + CASCADE is
    correct: an attached report dies with its subject, an unattached one was
    never personal data."""
    cid = _candidate(store)
    _report(store, candidate_id=None)

    store.delete_candidate(cid)

    with store._session_factory() as s:
        assert len(s.execute(select(ReportRow)).scalars().all()) == 1


def test_deleting_a_report_cascades_its_outcomes(store):
    cid = _candidate(store)
    _report(store, candidate_id=cid)

    with store._session_factory() as s:
        s.delete(s.get(ReportRow, "rep_cascade_1"))
        s.commit()

    with store._session_factory() as s:
        assert s.execute(select(OutcomeRow)).scalars().all() == []


def test_a_report_cannot_reference_a_candidate_that_does_not_exist(store):
    """The orphan the old store could not prevent is now unrepresentable."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        _report(store, candidate_id="no-such-candidate")
