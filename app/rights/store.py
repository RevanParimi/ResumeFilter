"""RightsStore (S8.3 Phase B) -- the only thing that touches the request table.

Detached Pydantic views out, never an ORM row across the boundary: the same
split as every other store in this repo, and the reason is the same -- nothing
downstream should be able to reach further into the table than the contract it
was handed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.ledger.consent import as_utc
from app.rights.models import DataPrincipalRequestRow
from app.rights.schema import (
    CorrectionField, RequestKind, RequestStatus, RequestView, ResolvedBy,
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
    ) -> RequestView:
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
            session.commit()
            return _view(row)

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
            return [_view(r) for r in rows]

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
            return [_view(r) for r in rows]

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
        """
        with self._session_factory() as session:
            result = session.execute(
                update(DataPrincipalRequestRow)
                .where(
                    DataPrincipalRequestRow.id == request_id,
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
            session.commit()
            return result.rowcount == 1


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
