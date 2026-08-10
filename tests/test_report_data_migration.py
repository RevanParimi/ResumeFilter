"""One-shot import of the pre-S8.1 reports.db into the main database.

Deliberately NOT an Alembic step: a migration must not read a filesystem path
out of Settings, must not need a second database engine to be reachable, and
must stay runnable on a fresh deployment that never had a reports.db.
"""

from __future__ import annotations

import sqlite3

from sqlalchemy import select

from app.candidates.models import CandidateRow
from app.reports.models import OutcomeRow, ReportRow
from scripts.migrate_reports_into_main_db import migrate
from tests.conftest import make_candidate_store


def _candidate(store, cid: str = "cand_1") -> str:
    with store._session_factory() as s:
        s.add(CandidateRow(id=cid))
        s.commit()
    return cid


def _old_db(tmp_path, rows):
    """A pre-S8.1 reports.db, built with the exact schema that store created."""
    path = str(tmp_path / "reports.db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE reports (id TEXT PRIMARY KEY, domain TEXT, created_at TEXT,"
        " depth_band TEXT, candidate_id TEXT, body TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE outcomes (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " report_id TEXT NOT NULL, claim_id TEXT, outcome TEXT NOT NULL,"
        " notes TEXT, recorded_at TEXT NOT NULL)"
    )
    for r in rows:
        conn.execute("INSERT INTO reports VALUES (?,?,?,?,?,?)", r)
    conn.execute(
        "INSERT INTO outcomes (report_id, claim_id, outcome, notes, recorded_at)"
        " VALUES ('rep_live', NULL, 'inconclusive', '', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()
    return path


def test_missing_old_db_is_a_clean_no_op(tmp_path):
    store = make_candidate_store()
    result = migrate(str(tmp_path / "absent.db"), store._session_factory)
    assert result == {"imported": 0, "orphaned": 0, "outcomes": 0}


def test_imports_linked_reports_and_drops_orphans(tmp_path):
    store = make_candidate_store()
    cid = _candidate(store)
    path = _old_db(tmp_path, [
        ("rep_live", "genai", "2026-01-01T00:00:00+00:00", "solid", cid,
         '{"id": "rep_live", "domain": "genai", "depth_band": "solid"}'),
        # The old convention's actual failures: a report whose candidate is
        # already erased. No FK caught this; nothing ever would have.
        ("rep_orphan", "genai", "2026-01-01T00:00:00+00:00", "solid", "gone",
         '{"id": "rep_orphan"}'),
        # Ad-hoc POST /evaluate output: never personal data, always kept.
        ("rep_free", "genai", "2026-01-01T00:00:00+00:00", "solid", None,
         '{"id": "rep_free"}'),
    ])

    result = migrate(path, store._session_factory)

    assert result == {"imported": 2, "orphaned": 1, "outcomes": 1}
    with store._session_factory() as s:
        ids = {r.id for r in s.execute(select(ReportRow)).scalars()}
        assert ids == {"rep_live", "rep_free"}
        assert len(s.execute(select(OutcomeRow)).scalars().all()) == 1


def test_an_orphans_outcomes_are_dropped_with_it(tmp_path):
    store = make_candidate_store()
    path = _old_db(tmp_path, [
        ("rep_orphan", "genai", "2026-01-01T00:00:00+00:00", "solid", "gone",
         '{"id": "rep_orphan"}'),
    ])
    # The fixture's single outcome belongs to rep_live, which is not in this DB.
    result = migrate(path, store._session_factory)

    assert result == {"imported": 0, "orphaned": 1, "outcomes": 0}
    with store._session_factory() as s:
        assert s.execute(select(OutcomeRow)).scalars().all() == []


def test_second_run_is_a_no_op(tmp_path):
    store = make_candidate_store()
    cid = _candidate(store)
    path = _old_db(tmp_path, [
        ("rep_live", "genai", "2026-01-01T00:00:00+00:00", "solid", cid,
         '{"id": "rep_live"}'),
    ])

    migrate(path, store._session_factory)
    again = migrate(path, store._session_factory)

    assert again["imported"] == 0
    with store._session_factory() as s:
        assert len(s.execute(select(ReportRow)).scalars().all()) == 1
        assert len(s.execute(select(OutcomeRow)).scalars().all()) == 1


def test_imported_outcomes_are_stamped_operator(tmp_path):
    """S8.5 regression pin, and the reason it exists is worth keeping: this
    importer is a THIRD writer to `outcomes`, beside the operator's route and
    the customer's, and it is the one nobody thinks of. `recorded_by` is NOT
    NULL with no server default, so the full suite -- not the design -- is what
    caught it.

    `operator` is a fact about these rows and not a guess: they come from the
    pre-S8.1 reports database, which predates the org plane entirely.
    """
    store = make_candidate_store()
    cid = _candidate(store)
    path = _old_db(tmp_path, [
        ("rep_live", "genai", "2026-01-01T00:00:00+00:00", "solid", cid,
         '{"id": "rep_live"}'),
    ])

    migrate(path, store._session_factory)

    with store._session_factory() as s:
        row = s.execute(select(OutcomeRow)).scalars().one()
        assert row.recorded_by == "operator"
        assert row.org_id is None


def test_imported_reports_then_cascade_like_any_other(tmp_path):
    """An imported report is not a second-class row: erasure sweeps it."""
    store = make_candidate_store()
    cid = _candidate(store)
    path = _old_db(tmp_path, [
        ("rep_live", "genai", "2026-01-01T00:00:00+00:00", "solid", cid,
         '{"id": "rep_live"}'),
    ])
    migrate(path, store._session_factory)

    store.delete_candidate(cid)

    with store._session_factory() as s:
        assert s.execute(select(ReportRow)).scalars().all() == []
        assert s.execute(select(OutcomeRow)).scalars().all() == []
