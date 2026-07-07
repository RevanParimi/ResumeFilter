"""Report ⇄ candidate linkage: schema field, store queries, legacy-DB upgrade."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from app.schemas.report import Report
from app.services.report_store import (
    InMemoryReportStore,
    OutcomeLabel,
    OutcomeRecord,
    SqliteReportStore,
)


def _store(tmp_path) -> SqliteReportStore:
    return SqliteReportStore(path=(tmp_path / "reports.db").as_posix())


def test_report_candidate_id_defaults_none():
    assert Report().candidate_id is None
    assert Report(candidate_id="cand-1").candidate_id == "cand-1"


def test_sqlite_roundtrip_and_for_candidate_ordering(tmp_path):
    store = _store(tmp_path)
    now = datetime.now(timezone.utc)
    newer = Report(candidate_id="cand-1", created_at=now)
    older = Report(candidate_id="cand-1", created_at=now - timedelta(hours=1))
    other = Report(candidate_id="cand-2")
    unlinked = Report()  # ad-hoc /evaluate report
    for r in (newer, older, other, unlinked):
        store.save(r)

    assert store.get(newer.id).candidate_id == "cand-1"
    listed = store.for_candidate("cand-1")
    assert [r.id for r in listed] == [older.id, newer.id]  # ascending created_at
    assert store.for_candidate("cand-nope") == []


def test_sqlite_delete_for_candidate_cascades_outcomes(tmp_path):
    store = _store(tmp_path)
    linked_a, linked_b, other = (
        Report(candidate_id="cand-1"),
        Report(candidate_id="cand-1"),
        Report(candidate_id="cand-2"),
    )
    for r in (linked_a, linked_b, other):
        store.save(r)
    store.add_outcome(
        OutcomeRecord(report_id=linked_a.id, outcome=OutcomeLabel.INCONCLUSIVE)
    )

    assert store.delete_for_candidate("cand-1") == 2
    assert store.get(linked_a.id) is None
    assert store.outcomes(linked_a.id) == []
    assert store.get(other.id) is not None
    assert store.delete_for_candidate("cand-1") == 0


def test_legacy_reports_db_upgraded_in_place(tmp_path):
    """Opening a pre-S1.3 reports.db must add the candidate_id column, not crash."""
    path = (tmp_path / "legacy.db").as_posix()
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE reports (id TEXT PRIMARY KEY, domain TEXT, created_at TEXT,"
        " depth_band TEXT, body TEXT NOT NULL)"
    )
    old = Report()
    legacy_body = old.model_dump(mode="json")
    legacy_body.pop("candidate_id")  # pre-S1.3 bodies never had the key
    conn.execute(
        "INSERT INTO reports VALUES (?, ?, ?, ?, ?)",
        (old.id, old.domain, old.created_at.isoformat(), old.depth_band.value,
         json.dumps(legacy_body)),
    )
    conn.commit()
    conn.close()

    store = SqliteReportStore(path=path)
    assert store.get(old.id) is not None          # legacy rows still readable
    store.save(Report(candidate_id="cand-9"))     # new column usable
    assert [r.candidate_id for r in store.for_candidate("cand-9")] == ["cand-9"]


def test_inmemory_store_candidate_queries():
    store = InMemoryReportStore()
    linked, other = Report(candidate_id="cand-1"), Report(candidate_id="cand-2")
    store.save(linked)
    store.save(other)
    store.add_outcome(
        OutcomeRecord(report_id=linked.id, outcome=OutcomeLabel.INCONCLUSIVE)
    )
    assert [r.id for r in store.for_candidate("cand-1")] == [linked.id]
    assert store.delete_for_candidate("cand-1") == 1
    assert store.get(linked.id) is None
    assert store.outcomes(linked.id) == []
    assert store.get(other.id) is not None
