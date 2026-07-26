"""Persist / read materialized feature vectors (PI-4 / S4.2).

Shares candidates_db_url (one metadata root, one Alembic env). Schema is
Alembic's job. The unique cut (candidate_id, as_of, view_name, view_version) makes
re-materialization an idempotent upsert. as_of is stored + queried as naive-UTC so
the equality lookup round-trips on SQLite (which drops tzinfo).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.features.materialize import MaterializedVector
from app.features.models import FeatureVectorRow
from app.features.schema import FeatureVector
from app.ledger.consent import as_utc


def _key_dt(dt: datetime) -> datetime:
    """Naive-UTC key so an equality lookup round-trips on SQLite (tzinfo dropped)."""
    return as_utc(dt).replace(tzinfo=None)


def _to_mv(row: FeatureVectorRow) -> MaterializedVector:
    return MaterializedVector(
        vector=FeatureVector(
            candidate_id=row.candidate_id,
            as_of=as_utc(row.as_of),
            view_name=row.view_name,
            view_version=row.view_version,
            values=dict(row.feature_values or {}),
            missing=tuple(row.missing or ()),
        ),
        consent_state=dict(row.consent_state or {}),
        materialized_at=as_utc(row.materialized_at),
    )


class FeatureStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def upsert_vector(self, mv: MaterializedVector) -> str:
        v = mv.vector
        with self._session_factory() as session:
            row = session.execute(
                select(FeatureVectorRow).where(
                    FeatureVectorRow.candidate_id == v.candidate_id,
                    FeatureVectorRow.as_of == _key_dt(v.as_of),
                    FeatureVectorRow.view_name == v.view_name,
                    FeatureVectorRow.view_version == v.view_version,
                )
            ).scalar_one_or_none()
            if row is None:
                row = FeatureVectorRow(
                    candidate_id=v.candidate_id,
                    as_of=_key_dt(v.as_of),
                    view_name=v.view_name,
                    view_version=v.view_version,
                )
                session.add(row)
            row.feature_values = dict(v.values)
            row.missing = list(v.missing)
            row.consent_state = dict(mv.consent_state)
            row.materialized_at = _key_dt(mv.materialized_at)
            session.flush()
            rid = row.id
            session.commit()
            return rid

    def get_vector(
        self, candidate_id: str, *, view_name: str, view_version: int, as_of: datetime
    ) -> Optional[MaterializedVector]:
        with self._session_factory() as session:
            row = session.execute(
                select(FeatureVectorRow).where(
                    FeatureVectorRow.candidate_id == candidate_id,
                    FeatureVectorRow.as_of == _key_dt(as_of),
                    FeatureVectorRow.view_name == view_name,
                    FeatureVectorRow.view_version == view_version,
                )
            ).scalar_one_or_none()
            return _to_mv(row) if row else None

    def vectors_for_view(
        self, view_name: str, view_version: int, *, as_of: Optional[datetime] = None
    ) -> list[MaterializedVector]:
        with self._session_factory() as session:
            q = select(FeatureVectorRow).where(
                FeatureVectorRow.view_name == view_name,
                FeatureVectorRow.view_version == view_version,
            )
            if as_of is not None:
                q = q.where(FeatureVectorRow.as_of == _key_dt(as_of))
            q = q.order_by(FeatureVectorRow.candidate_id)
            return [_to_mv(r) for r in session.execute(q).scalars().all()]


def build_feature_store(settings: Optional[Settings] = None) -> FeatureStore:
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return FeatureStore(make_session_factory(engine))
