"""RightsStore (S8.3 Phase B) -- the only thing that touches the request table.

Detached Pydantic views out, never an ORM row across the boundary: the same
split as every other store in this repo, and the reason is the same -- nothing
downstream should be able to reach further into the table than the contract it
was handed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth.models import AdminUserRow
from app.candidates.models import CandidateRow
from app.core.config import Settings, get_settings
from app.core.logging import get_logger

# INFO, not warning: these races are EXPECTED and each handler resolves its
# own correctly. The signal is the RATE -- one a day versus a thousand a
# minute -- and at warning they would be noise that trains an operator to
# ignore the channel now carrying real refusals (S9.3).
_log = get_logger("rights.store")
from app.core.db import make_engine, make_session_factory
from app.ledger.consent import as_utc
from app.rights.models import DataPrincipalRequestRow
from app.rights.schema import (
    CorrectionField, RequestKind, RequestRefused, RequestStatus, RequestView, ResolvedBy,
)


def _view(row: DataPrincipalRequestRow) -> RequestView:
    return RequestView(
        id=row.id,
        kind=RequestKind(row.kind),
        status=RequestStatus(row.status),
        applied=row.applied,
        field=CorrectionField(row.field) if row.field else None,
        current_value=row.current_value or "",
        requested_value=row.requested_value or "",
        note=row.note or "",
        created_at=as_utc(row.created_at),
        resolved_at=as_utc(row.resolved_at) if row.resolved_at else None,
        resolution=row.resolution or "",
        resolved_by=ResolvedBy(row.resolved_by) if row.resolved_by else None,
    )


class RightsStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def create(
        self,
        candidate_id: str,
        *,
        kind: RequestKind,
        field: Optional[CorrectionField],
        current_value: str,
        requested_value: str,
        note: str,
    ) -> Optional[RequestView]:
        """File a request. None means the candidate is gone.

        `candidate_id` is a real FK, so an erasure landing between the caller's
        read and this INSERT raises rather than returning. The cause is
        VERIFIED after the rollback rather than assumed from the exception --
        this row has a second FK (`resolved_by_admin_user_id`) and a primary
        key, and swallowing either of those as "the subject vanished" would
        turn a genuine bug into a quiet 404 (the S8.5 `save()` precedent).
        """
        with self._session_factory() as session:
            row = DataPrincipalRequestRow(
                candidate_id=candidate_id,
                kind=kind.value,
                status=RequestStatus.OPEN.value,
                applied=False,
                field=field.value if field else None,
                current_value=current_value,
                requested_value=requested_value,
                note=note,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError as exc:
                _log.info("integrity_race", where="RightsStore.create", error_type=type(exc).__name__)
                session.rollback()
                foreign_key = (getattr(exc.orig, "sqlstate", None) == "23503"
                    or getattr(exc.orig, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_FOREIGNKEY")
                if foreign_key and session.get(CandidateRow, candidate_id) is None:
                    return None
                raise
            return _view(row)

    def exists_for_candidate(self, candidate_id: str, request_id: str) -> bool:
        """Fresh subject/request snapshot after submission, not a delivery lock."""
        with self._session_factory() as session:
            return session.scalar(select(DataPrincipalRequestRow.id).join(CandidateRow).where(
                DataPrincipalRequestRow.id == request_id,
                DataPrincipalRequestRow.candidate_id == candidate_id,
            )) is not None

    def for_candidate(self, candidate_id: str) -> list[RequestView]:
        """The subject's own, newest first."""
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(DataPrincipalRequestRow)
                    .where(DataPrincipalRequestRow.candidate_id == candidate_id)
                    .order_by(
                        DataPrincipalRequestRow.created_at.desc(),
                        DataPrincipalRequestRow.id.desc(),
                    )
                )
                .scalars()
                .all()
            )
            views = [_view(r) for r in rows]
        return self._retain_existing(views)

    def _retain_existing(self, views: list[RequestView]) -> list[RequestView]:
        """Fresh erasure snapshots after materialization, not delivery locks.

        Candidate lists have no row limit. Chunk IDs to keep SQL bind counts
        finite without changing their original order or the operator's limit.
        """
        existing = set()
        ids = [view.id for view in views]
        with self._session_factory() as session:
            for start in range(0, len(ids), 500):
                existing.update(session.scalars(
                    select(DataPrincipalRequestRow.id).join(CandidateRow)
                    .where(DataPrincipalRequestRow.id.in_(ids[start:start + 500]))
                ))
        return [view for view in views if view.id in existing]

    def get(self, request_id: str) -> Optional[tuple[RequestView, str]]:
        """The view AND its owner.

        The owner comes back beside the view rather than on it: the subject has
        no use for their own id repeated back, and the operator plane needs it
        to write the audit entry onto the right person's log.
        """
        with self._session_factory() as session:
            row = session.get(DataPrincipalRequestRow, request_id)
            if row is None:
                return None
            return _view(row), row.candidate_id

    def list_by_status(
        self, status: Optional[RequestStatus], limit: int
    ) -> list[RequestView]:
        """The operator's queue. OLDEST first -- a complaint that has waited
        longest is the one that should be answered next."""
        with self._session_factory() as session:
            statement = select(DataPrincipalRequestRow)
            if status is not None:
                statement = statement.where(
                    DataPrincipalRequestRow.status == status.value
                )
            rows = (
                session.execute(
                    statement.order_by(
                        DataPrincipalRequestRow.created_at,
                        DataPrincipalRequestRow.id,
                    ).limit(limit)
                )
                .scalars()
                .all()
            )
            views = [_view(r) for r in rows]
        return self._retain_existing(views)

    def resolve(
        self,
        request_id: str,
        *,
        status: RequestStatus,
        resolution: str,
        applied: bool,
        resolved_by: ResolvedBy,
        resolved_by_admin_user_id: Optional[str],
        now: datetime,
        candidate_id: Optional[str] = None,
        before_commit: Optional[Callable[[Session], None]] = None,
    ) -> bool:
        """Close an OPEN request. True if this call is the one that closed it.

        A CONDITIONAL UPDATE whose rowcount is the decision -- the house
        solution, from ScreeningStore._try_claim. A read-then-write would let
        two operators clicking Resolve at the same moment both succeed, and an
        applied correction applied twice is a second write onto a person's row
        on the strength of one decision.

        The clause is `status == OPEN` rather than `resolved_at IS NULL`,
        because a REJECTED request is equally closed: a rejection that could be
        quietly upgraded to an applied correction would make the written reason
        a draft.

        Candidate (and optional actor) parent locks precede the request. Only
        the winning transition runs before_commit on this Session; callback
        failure rolls back the entire decision. Without a callback this stays
        the low-level request-row writer, not an identity/audit operation.
        """
        if status not in (RequestStatus.RESOLVED, RequestStatus.REJECTED):
            raise RequestRefused("a decision must resolve or reject the request")
        with self._session_factory() as session:
            owner = select(DataPrincipalRequestRow.candidate_id).where(
                DataPrincipalRequestRow.id == request_id).scalar_subquery()
            scope = CandidateRow.id == owner
            if candidate_id is not None:
                scope = scope & (CandidateRow.id == candidate_id)
            if session.bind.dialect.name == 'sqlite':
                # Start a writer before reading. Preserve identity timestamps;
                # CandidateRow.updated_at has an onupdate default.
                locked = session.execute(update(CandidateRow).where(scope).values(
                    full_name=CandidateRow.full_name, updated_at=CandidateRow.updated_at)).rowcount == 1
            else:
                if resolved_by_admin_user_id is not None:
                    # Actor deletion SET NULLs requests: parent first too.
                    session.scalar(select(AdminUserRow.id).where(
                        AdminUserRow.id == resolved_by_admin_user_id).with_for_update(read=True, key_share=True))
                # Candidate erasure locks its parent before cascading requests.
                locked = session.scalar(select(CandidateRow.id).where(scope).with_for_update()) is not None
            if not locked:
                return False
            result = session.execute(
                update(DataPrincipalRequestRow)
                .where(
                    DataPrincipalRequestRow.id == request_id,
                    DataPrincipalRequestRow.candidate_id == (candidate_id if candidate_id is not None else owner),
                    DataPrincipalRequestRow.status == RequestStatus.OPEN.value,
                )
                .values(
                    status=status.value,
                    resolution=resolution,
                    applied=applied,
                    resolved_at=now,
                    resolved_by=resolved_by.value,
                    resolved_by_admin_user_id=resolved_by_admin_user_id,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                return False
            if before_commit is not None:
                before_commit(session)
            session.commit()
            return True


def build_rights_store(
    settings: Optional[Settings] = None,
    session_factory: Optional[sessionmaker] = None,
) -> RightsStore:
    """Take the container's factory when there is one; only build an engine
    when there is not -- the `build_rate_limit_store` shape."""
    if session_factory is not None:
        return RightsStore(session_factory)
    settings = settings or get_settings()
    return RightsStore(make_session_factory(make_engine(settings.candidates_db_url)))
