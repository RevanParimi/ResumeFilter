"""Curation store (S6.3) — the unmapped-term review queue, on the candidates DB.

Candidate-agnostic; no delete path (taxonomy-gap metadata survives candidate
erasure by design). Upsert by norm_key. Datetimes are coerced to UTC because
SQLite refetches naive.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import sessionmaker

from app.candidates.normalize.skills import SkillMatch
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.curation.models import UnmappedTermRow
from app.curation.schema import CurationAction, CurationStatus, UnmappedTerm


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_term(row: UnmappedTermRow) -> UnmappedTerm:
    return UnmappedTerm(
        norm_key=row.norm_key,
        display_name=row.display_name,
        source_types=list(row.source_types or []),
        occurrences=row.occurrences,
        first_seen=_as_utc(row.first_seen),
        last_seen=_as_utc(row.last_seen),
        status=CurationStatus(row.status),
        action=CurationAction(row.action) if row.action else None,
        canonical=row.canonical,
        category=row.category,
        note=row.note,
        decided_by=row.decided_by,
        decided_at=_as_utc(row.decided_at) if row.decided_at else None,
    )


class CurationStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def record_unmapped(
        self, norm_key: str, display_name: str, *, source_type: str, now: datetime
    ) -> None:
        now = _as_utc(now)
        with self._session_factory() as session:
            row = session.execute(
                select(UnmappedTermRow).where(UnmappedTermRow.norm_key == norm_key)
            ).scalar_one_or_none()
            if row is None:
                session.add(UnmappedTermRow(
                    norm_key=norm_key, display_name=display_name,
                    source_types=[source_type], occurrences=1,
                    first_seen=now, last_seen=now,
                    status=CurationStatus.PENDING.value,
                ))
                session.commit()
                return
            if row.status != CurationStatus.PENDING.value:
                return  # resolved/ignored terms are final; never re-queue or recount
            row.occurrences += 1
            row.last_seen = now
            row.display_name = display_name
            if source_type not in (row.source_types or []):
                row.source_types = list(row.source_types or []) + [source_type]
            session.commit()

    def list_terms(
        self,
        status: Optional[CurationStatus] = None,
        limit: int = 200,
        *,
        cursor: Optional[str] = None,
    ) -> tuple[list[UnmappedTerm], Optional[str]]:
        """Keyset-paged over (occurrences, last_seen, norm_key) -- the existing
        order, plus norm_key to break ties into a total order."""
        from app.screening.pagination import (
            decode_cursor, encode_cursor, iso_datetime,
        )

        with self._session_factory() as session:
            q = select(UnmappedTermRow)
            if status is not None:
                q = q.where(UnmappedTermRow.status == status.value)
            if cursor is not None:
                occ, seen, key = decode_cursor(
                    cursor, arity=3, types=((int, float), str, str)
                )
                cut = iso_datetime(seen)
                q = q.where(
                    or_(
                        UnmappedTermRow.occurrences < occ,
                        and_(
                            UnmappedTermRow.occurrences == occ,
                            or_(
                                UnmappedTermRow.last_seen < cut,
                                and_(
                                    UnmappedTermRow.last_seen == cut,
                                    UnmappedTermRow.norm_key > key,
                                ),
                            ),
                        ),
                    )
                )
            rows = session.execute(
                q.order_by(
                    UnmappedTermRow.occurrences.desc(),
                    UnmappedTermRow.last_seen.desc(),
                    UnmappedTermRow.norm_key,
                ).limit(limit + 1)
            ).scalars().all()

            more = len(rows) > limit
            rows = rows[:limit]
            next_cursor = (
                encode_cursor((rows[-1].occurrences, rows[-1].last_seen, rows[-1].norm_key))
                if more and rows else None
            )
            return [_to_term(r) for r in rows], next_cursor

    def get_term(self, norm_key: str) -> Optional[UnmappedTerm]:
        with self._session_factory() as session:
            row = session.execute(
                select(UnmappedTermRow).where(UnmappedTermRow.norm_key == norm_key)
            ).scalar_one_or_none()
            return _to_term(row) if row else None

    def resolve(
        self, norm_key: str, *, action: CurationAction, canonical: Optional[str],
        category: Optional[str], note: Optional[str], decided_by: Optional[str],
        now: datetime,
    ) -> UnmappedTerm:
        now = _as_utc(now)
        with self._session_factory() as session:
            row = session.execute(
                select(UnmappedTermRow).where(UnmappedTermRow.norm_key == norm_key)
            ).scalar_one_or_none()
            if row is None:
                raise LookupError(f"unmapped term {norm_key!r} not found")
            row.action = action.value
            row.status = (
                CurationStatus.IGNORED if action == CurationAction.IGNORE
                else CurationStatus.RESOLVED
            ).value
            row.canonical = None if action == CurationAction.IGNORE else canonical
            row.category = None if action == CurationAction.IGNORE else category
            row.note = note
            row.decided_by = decided_by
            row.decided_at = now
            session.commit()
            return _to_term(row)

    def load_overlay(self) -> dict[str, SkillMatch]:
        with self._session_factory() as session:
            rows = session.execute(
                select(UnmappedTermRow).where(
                    UnmappedTermRow.status == CurationStatus.RESOLVED.value
                )
            ).scalars().all()
            overlay: dict[str, SkillMatch] = {}
            for r in rows:
                if r.canonical and r.category:
                    overlay[r.norm_key] = SkillMatch(canonical=r.canonical, category=r.category)
            return overlay


def build_curation_store(settings: Optional[Settings] = None) -> CurationStore:
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return CurationStore(make_session_factory(engine))
