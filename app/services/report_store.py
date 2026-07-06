"""Report store — durable reports + human outcome records.

Reports must survive a process restart (FR-6) and human reviewers close the
flywheel loop by recording outcomes against them (FR-7/FR-8). Same shape as the
other services: a Protocol, a real implementation, and an in-memory fake.

SQLite (stdlib) is the M1 store: one file, zero infrastructure, WAL for
concurrent readers. The full Report is stored as a JSON blob — schema evolution
stays Pydantic's job, not SQL's. The resume text itself is never persisted
(DPDP / NFR-4): the Report schema does not contain it, only derived claims.
``delete`` supports erasure requests.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional, Protocol

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.schemas.report import Report


class OutcomeLabel(StrEnum):
    """How a human closed the loop on a report/claim."""

    VERIFIED_GENUINE = "verified_genuine"
    VERIFIED_FABRICATED = "verified_fabricated"
    CANDIDATE_CLARIFIED = "candidate_clarified"
    INCONCLUSIVE = "inconclusive"


class OutcomeRecord(BaseModel):
    """One human judgment; claim_id=None means it applies to the whole report."""

    report_id: str
    claim_id: Optional[str] = None
    outcome: OutcomeLabel
    notes: str = ""
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReportStore(Protocol):
    def save(self, report: Report) -> None: ...
    def get(self, report_id: str) -> Optional[Report]: ...
    def add_outcome(self, rec: OutcomeRecord) -> None: ...
    def outcomes(self, report_id: str) -> list[OutcomeRecord]: ...
    def delete(self, report_id: str) -> bool: ...
    def for_candidate(self, candidate_id: str) -> list[Report]: ...
    def delete_for_candidate(self, candidate_id: str) -> int: ...


class SqliteReportStore:
    """Single-file durable store. WAL + a process-wide lock for writes."""

    def __init__(self, path: Optional[str] = None, settings: Optional[Settings] = None) -> None:
        settings = settings or get_settings()
        self.path = path or settings.report_db_path
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS reports ("
            " id TEXT PRIMARY KEY, domain TEXT, created_at TEXT,"
            " depth_band TEXT, candidate_id TEXT, body TEXT NOT NULL)"
        )
        # Pre-S1.3 DBs lack candidate_id; this store is stdlib-sqlite (not
        # Alembic-managed), so upgrade in place. Fresh DBs hit the except.
        try:
            self._conn.execute("ALTER TABLE reports ADD COLUMN candidate_id TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_candidate ON reports(candidate_id)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS outcomes ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT, report_id TEXT NOT NULL,"
            " claim_id TEXT, outcome TEXT NOT NULL, notes TEXT,"
            " recorded_at TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcomes_report ON outcomes(report_id)"
        )
        self._conn.commit()

    def save(self, report: Report) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO reports"
                " (id, domain, created_at, depth_band, candidate_id, body)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    report.id,
                    report.domain,
                    report.created_at.isoformat(),
                    report.depth_band.value,
                    report.candidate_id,
                    report.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get(self, report_id: str) -> Optional[Report]:
        row = self._conn.execute(
            "SELECT body FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        return Report.model_validate_json(row[0]) if row else None

    def add_outcome(self, rec: OutcomeRecord) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO outcomes (report_id, claim_id, outcome, notes, recorded_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (rec.report_id, rec.claim_id, rec.outcome.value, rec.notes,
                 rec.recorded_at.isoformat()),
            )
            self._conn.commit()

    def outcomes(self, report_id: str) -> list[OutcomeRecord]:
        rows = self._conn.execute(
            "SELECT report_id, claim_id, outcome, notes, recorded_at FROM outcomes"
            " WHERE report_id = ? ORDER BY id",
            (report_id,),
        ).fetchall()
        return [
            OutcomeRecord(
                report_id=r[0], claim_id=r[1], outcome=OutcomeLabel(r[2]),
                notes=r[3] or "", recorded_at=datetime.fromisoformat(r[4]),
            )
            for r in rows
        ]

    def delete(self, report_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
            self._conn.execute("DELETE FROM outcomes WHERE report_id = ?", (report_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def for_candidate(self, candidate_id: str) -> list[Report]:
        rows = self._conn.execute(
            "SELECT body FROM reports WHERE candidate_id = ? ORDER BY created_at",
            (candidate_id,),
        ).fetchall()
        return [Report.model_validate_json(r[0]) for r in rows]

    def delete_for_candidate(self, candidate_id: str) -> int:
        """DPDP: erase every report derived from this candidate (+ outcomes)."""
        with self._lock:
            ids = [
                r[0]
                for r in self._conn.execute(
                    "SELECT id FROM reports WHERE candidate_id = ?", (candidate_id,)
                ).fetchall()
            ]
            if ids:
                marks = ",".join("?" * len(ids))
                self._conn.execute(
                    f"DELETE FROM outcomes WHERE report_id IN ({marks})", ids
                )
                self._conn.execute(
                    "DELETE FROM reports WHERE candidate_id = ?", (candidate_id,)
                )
            self._conn.commit()
            return len(ids)


class InMemoryReportStore:
    """Test/inspection store; dict-backed, same surface."""

    def __init__(self) -> None:
        self._reports: dict[str, Report] = {}
        self._outcomes: list[OutcomeRecord] = []

    def save(self, report: Report) -> None:
        self._reports[report.id] = report

    def get(self, report_id: str) -> Optional[Report]:
        return self._reports.get(report_id)

    def add_outcome(self, rec: OutcomeRecord) -> None:
        self._outcomes.append(rec)

    def outcomes(self, report_id: str) -> list[OutcomeRecord]:
        return [o for o in self._outcomes if o.report_id == report_id]

    def delete(self, report_id: str) -> bool:
        existed = self._reports.pop(report_id, None) is not None
        self._outcomes = [o for o in self._outcomes if o.report_id != report_id]
        return existed

    def for_candidate(self, candidate_id: str) -> list[Report]:
        linked = [r for r in self._reports.values() if r.candidate_id == candidate_id]
        return sorted(linked, key=lambda r: r.created_at)

    def delete_for_candidate(self, candidate_id: str) -> int:
        ids = [rid for rid, r in self._reports.items() if r.candidate_id == candidate_id]
        for rid in ids:
            self.delete(rid)
        return len(ids)


def build_report_store(settings: Optional[Settings] = None) -> ReportStore:
    return SqliteReportStore(settings=settings or get_settings())
