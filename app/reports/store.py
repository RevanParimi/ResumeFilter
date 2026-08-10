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

from app.candidates.models import CandidateRow
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.ledger.consent import as_utc
from app.reports.models import OutcomeRow, ReportRow
from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.schemas.report import Report


class SubjectErasedError(RuntimeError):
    """save() refused: the candidate this report names no longer exists.

    A real race -- an evaluation in flight when an erasure lands. Before S8.1
    the orphan was written and a compensating delete in the route had to
    remember to remove it; now the foreign key refuses it outright.
    """


class ReportStore(Protocol):
    def save(self, report: Report, *, org_id: Optional[str] = None) -> None: ...
    def get(self, report_id: str) -> Optional[Report]: ...
    def add_outcome(self, rec: OutcomeRecord) -> None: ...
    def outcomes(self, report_id: str) -> list[OutcomeRecord]: ...
    def outcomes_for_org(
        self, org_id: str, report_id: str
    ) -> Optional[list[OutcomeRecord]]: ...
    def delete(self, report_id: str) -> bool: ...
    def for_candidate(self, candidate_id: str) -> list[Report]: ...
    def get_for_org(self, org_id: str, report_id: str) -> Optional[Report]: ...
    def for_candidate_and_org(
        self, org_id: str, candidate_id: str
    ) -> list[Report]: ...


class SqlReportStore:
    """SQLAlchemy-backed, sharing the main database's session factory."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def save(self, report: Report, *, org_id: Optional[str] = None) -> None:
        """Upsert. (The old store used ``INSERT OR REPLACE``, which Postgres
        does not have -- the SQL had to be rewritten whatever we did here.)

        ``org_id`` is a STORAGE fact and never enters ``body``: the Report
        contract is what a client receives, and ownership is not part of it.
        Supplying no ``org_id`` on a re-save LEAVES the existing owner alone --
        un-owning a report by forgetting an argument would be a silent
        cross-tenant leak in the making.
        """
        with self._session_factory() as s:
            row = s.get(ReportRow, report.id)
            if row is None:
                row = ReportRow(id=report.id)
                s.add(row)
            row.domain = report.domain
            row.depth_band = report.depth_band.value
            row.candidate_id = report.candidate_id
            if org_id is not None:
                row.org_id = org_id
            row.body = report.model_dump(mode="json")
            row.created_at = as_utc(report.created_at)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                if report.candidate_id is None:
                    # No candidate FK, so any IntegrityError is unrelated to
                    # candidate erasure.
                    raise
                # Two FKs now: candidate (CASCADE) and org (SET NULL).
                # Verify the actual cause: does the candidate still exist?
                # This is dialect-independent and checks the real precondition.
                candidate_exists = s.get(CandidateRow, report.candidate_id) is not None
                if not candidate_exists:
                    # The subject was genuinely erased mid-flight.
                    raise SubjectErasedError(report.candidate_id) from None
                # Candidate exists, so the FK failure is from org_id (or some
                # other unforeseen FK). Re-raise the original error.
                raise

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
                recorded_by=rec.recorded_by.value,
                org_id=rec.org_id,
                recorded_by_org_user_id=rec.recorded_by_org_user_id,
            ))
            s.commit()

    def outcomes(self, report_id: str) -> list[OutcomeRecord]:
        """EVERY outcome on a report, whoever wrote it. The operator's
        cross-tenant view -- see ``outcomes_for_org`` for the customer's."""
        with self._session_factory() as s:
            return self._outcomes(s, report_id)

    def outcomes_for_org(
        self, org_id: str, report_id: str
    ) -> Optional[list[OutcomeRecord]]:
        """This org's own judgments on a report it commissioned.

        ``None`` for "not yours, or absent" -- one answer, so the route can
        emit one 404 and another org's report stays indistinguishable from one
        that does not exist (TENANCY.md §6). An EMPTY LIST is a different fact:
        the report is yours and you have judged nothing yet.

        The ``org_id`` filter is not redundant with the ownership check above
        it. A report has exactly one owning org, so this cannot leak across
        tenants -- but it could leak DOWNWARD: an operator's internal note
        about a customer's report is written on that same report.
        """
        with self._session_factory() as s:
            row = s.get(ReportRow, report_id)
            if row is None or row.org_id != org_id:
                return None
            return self._outcomes(s, report_id, org_id=org_id)

    @staticmethod
    def _outcomes(
        s, report_id: str, *, org_id: Optional[str] = None
    ) -> list[OutcomeRecord]:
        """One read, one row->record mapping. Two copies of this is how the
        provenance fields would end up on one path and not the other."""
        stmt = select(OutcomeRow).where(OutcomeRow.report_id == report_id)
        if org_id is not None:
            stmt = stmt.where(OutcomeRow.org_id == org_id)
        rows = s.execute(stmt.order_by(OutcomeRow.id)).scalars().all()
        return [
            OutcomeRecord(
                report_id=r.report_id, claim_id=r.claim_id,
                outcome=OutcomeLabel(r.outcome), notes=r.notes or "",
                recorded_at=as_utc(r.recorded_at),
                recorded_by=OutcomeSource(r.recorded_by),
                org_id=r.org_id,
                recorded_by_org_user_id=r.recorded_by_org_user_id,
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

    def get_for_org(self, org_id: str, report_id: str) -> Optional[Report]:
        """One report, but only if this org commissioned it.

        A report with ``org_id IS NULL`` -- pre-S8.4, or uploaded through the
        admin plane -- belongs to NOBODY, not to everybody. Returning None here
        rather than raising is what lets the route answer 404 instead of 403:
        another org's report must be indistinguishable from one that is absent.
        """
        with self._session_factory() as s:
            row = s.get(ReportRow, report_id)
            if row is None or row.org_id != org_id:
                return None
            return Report.model_validate(row.body)

    def for_candidate_and_org(self, org_id: str, candidate_id: str) -> list[Report]:
        with self._session_factory() as s:
            rows = s.execute(
                select(ReportRow)
                .where(
                    ReportRow.candidate_id == candidate_id,
                    ReportRow.org_id == org_id,
                )
                .order_by(ReportRow.created_at)
            ).scalars().all()
            return [Report.model_validate(r.body) for r in rows]


def build_report_store(settings: Optional[Settings] = None) -> ReportStore:
    """Store on the shared candidates DB URL (one metadata root, one Alembic
    env). Schema is Alembic's job, NOT the builder's."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return SqlReportStore(make_session_factory(engine))
