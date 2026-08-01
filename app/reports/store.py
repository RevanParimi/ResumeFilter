"""Report store — durable reports + human outcome records, on the MAIN database.

Reports must survive a process restart (FR-6) and human reviewers close the
flywheel loop by recording outcomes against them (FR-7/FR-8). The resume text
itself is never persisted (DPDP / NFR-4): the Report schema does not contain it,
only derived claims.

S8.1 moved this off raw stdlib sqlite3 in a second database file. Erasure is no
longer a convention two route handlers remember -- it is
``reports.candidate_id -> candidates.id ON DELETE CASCADE``, which is why this
module has no ``delete_for_candidate`` at all.
"""

from __future__ import annotations

from typing import Optional, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.ledger.consent import as_utc
from app.reports.models import OutcomeRow, ReportRow
from app.reports.schema import OutcomeLabel, OutcomeRecord
from app.schemas.report import Report


class SubjectErasedError(RuntimeError):
    """save() refused: the candidate this report names no longer exists.

    A real race -- an evaluation in flight when an erasure lands. Before S8.1
    the orphan was written and a compensating delete in the route had to
    remember to remove it; now the foreign key refuses it outright.
    """


class ReportStore(Protocol):
    def save(self, report: Report) -> None: ...
    def get(self, report_id: str) -> Optional[Report]: ...
    def add_outcome(self, rec: OutcomeRecord) -> None: ...
    def outcomes(self, report_id: str) -> list[OutcomeRecord]: ...
    def delete(self, report_id: str) -> bool: ...
    def for_candidate(self, candidate_id: str) -> list[Report]: ...


class SqlReportStore:
    """SQLAlchemy-backed, sharing the main database's session factory."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def save(self, report: Report) -> None:
        """Upsert. (The old store used ``INSERT OR REPLACE``, which Postgres
        does not have -- the SQL had to be rewritten whatever we did here.)"""
        with self._session_factory() as s:
            row = s.get(ReportRow, report.id)
            if row is None:
                row = ReportRow(id=report.id)
                s.add(row)
            row.domain = report.domain
            row.depth_band = report.depth_band.value
            row.candidate_id = report.candidate_id
            row.body = report.model_dump(mode="json")
            row.created_at = as_utc(report.created_at)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                if report.candidate_id is None:
                    raise
                # The only FK on this row is the candidate, so an integrity
                # failure here means the subject was erased mid-flight.
                raise SubjectErasedError(report.candidate_id) from None

    def get(self, report_id: str) -> Optional[Report]:
        with self._session_factory() as s:
            row = s.get(ReportRow, report_id)
            return Report.model_validate(row.body) if row is not None else None

    def add_outcome(self, rec: OutcomeRecord) -> None:
        with self._session_factory() as s:
            s.add(OutcomeRow(
                report_id=rec.report_id, claim_id=rec.claim_id,
                outcome=rec.outcome.value, notes=rec.notes,
                recorded_at=as_utc(rec.recorded_at),
            ))
            s.commit()

    def outcomes(self, report_id: str) -> list[OutcomeRecord]:
        with self._session_factory() as s:
            rows = s.execute(
                select(OutcomeRow)
                .where(OutcomeRow.report_id == report_id)
                .order_by(OutcomeRow.id)
            ).scalars().all()
            return [
                OutcomeRecord(
                    report_id=r.report_id, claim_id=r.claim_id,
                    outcome=OutcomeLabel(r.outcome), notes=r.notes or "",
                    recorded_at=as_utc(r.recorded_at),
                )
                for r in rows
            ]

    def delete(self, report_id: str) -> bool:
        """Delete one report; its outcomes CASCADE in the database."""
        with self._session_factory() as s:
            row = s.get(ReportRow, report_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    def for_candidate(self, candidate_id: str) -> list[Report]:
        with self._session_factory() as s:
            rows = s.execute(
                select(ReportRow)
                .where(ReportRow.candidate_id == candidate_id)
                .order_by(ReportRow.created_at)
            ).scalars().all()
            return [Report.model_validate(r.body) for r in rows]


def build_report_store(settings: Optional[Settings] = None) -> ReportStore:
    """Store on the shared candidates DB URL (one metadata root, one Alembic
    env). Schema is Alembic's job, NOT the builder's."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return SqlReportStore(make_session_factory(engine))
