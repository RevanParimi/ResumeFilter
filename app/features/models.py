"""ORM row for materialized ML feature vectors (PI-4 / S4.2). Postgres-shaped.

One compact row per (candidate_id, as_of, view_name, view_version): the values a
FeatureView produced over a point-in-time context, plus which came back null and
the consent decision that governed the consent-tagged ones. Candidate-linked with
an ondelete=CASCADE FK so DPDP erasure (CandidateStore.delete_candidate) sweeps
materialized rows with the candidate -- no separate erasure path.

The JSON payload column is `feature_values` (not `values`, a reserved word).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FeatureVectorRow(Base):
    __tablename__ = "ml_feature_vectors"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "as_of", "view_name", "view_version",
            name="uq_ml_feature_vectors_cut",
        ),
        Index("ix_ml_feature_vectors_view", "view_name", "view_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    view_name: Mapped[str] = mapped_column(String(64))
    view_version: Mapped[int] = mapped_column(Integer)
    feature_values: Mapped[dict] = mapped_column(JSON, default=dict)
    missing: Mapped[list] = mapped_column(JSON, default=list)
    consent_state: Mapped[dict] = mapped_column(JSON, default=dict)
    materialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
