"""Append-only store for profile-source signals (S6.1), on the candidates DB.

One row per fetch — history is retained (point-in-time materialization later).
DPDP erasure needs no delete path here: rows CASCADE with the candidate.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.candidates.models import CandidateRow
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.profile_sources.models import ProfileSourceRow
from app.profile_sources.schema import ProfileSourceSignal, ProfileSourceType


class SourceSubjectErasedError(LookupError):
    def __init__(self) -> None:
        super().__init__("candidate not found")


class SourceSignalErasedError(LookupError):
    def __init__(self) -> None:
        super().__init__("source not found")


class ProfileSourceStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def save_signal(self, candidate_id: str, signal: ProfileSourceSignal) -> str:
        with self._session_factory() as session:
            row = ProfileSourceRow(
                candidate_id=candidate_id,
                source_type=signal.source_type.value,
                identifier=signal.identifier,
                signal=signal.model_dump(mode="json"),
                method=signal.method,
                fetched_at=signal.fetched_at,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                # Only FK failures can be erasure. A concurrent deletion must
                # not hide an unrelated NOT NULL/unique failure.
                is_fk = (getattr(exc.orig, "sqlstate", None) == "23503"
                         or getattr(exc.orig, "pgcode", None) == "23503"
                         or getattr(exc.orig, "sqlite_errorcode", None) == 787)
                if is_fk and session.get(CandidateRow, candidate_id) is None:
                    raise SourceSubjectErasedError() from None
                raise
            return row.id

    def require_saved_signal(self, candidate_id: str, row_id: str) -> None:
        """Fresh response snapshot using the storage ID, not the signal JSON ID."""
        with self._session_factory() as session:
            row = session.execute(
                select(CandidateRow.id, ProfileSourceRow.candidate_id)
                .outerjoin(ProfileSourceRow, ProfileSourceRow.id == row_id)
                .where(CandidateRow.id == candidate_id)
            ).one_or_none()
            if row is None:
                raise SourceSubjectErasedError()
            if row[1] is None:
                raise SourceSignalErasedError()
            if row[1] != candidate_id:
                raise ValueError("source_candidate_mismatch")

    def signals_for_candidate(
        self, candidate_id: str, source_type: Optional[ProfileSourceType] = None
    ) -> list[ProfileSourceSignal]:
        with self._session_factory() as session:
            q = select(ProfileSourceRow).where(ProfileSourceRow.candidate_id == candidate_id)
            if source_type is not None:
                q = q.where(ProfileSourceRow.source_type == source_type.value)
            rows = (
                session.execute(
                    q.order_by(ProfileSourceRow.created_at.desc(), ProfileSourceRow.id.desc())
                )
                .scalars()
                .all()
            )
            return [ProfileSourceSignal.model_validate(r.signal) for r in rows]

    def latest_for_source(
        self, candidate_id: str, source_type: ProfileSourceType
    ) -> Optional[ProfileSourceSignal]:
        sigs = self.signals_for_candidate(candidate_id, source_type)
        return sigs[0] if sigs else None


def build_profile_source_store(settings: Optional[Settings] = None) -> ProfileSourceStore:
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return ProfileSourceStore(make_session_factory(engine))
