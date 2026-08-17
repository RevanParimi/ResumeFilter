"""ORM row for job requisitions (S5.1). Postgres-shaped on SQLite.

Org-owned demand-side object: CASCADEs on its organization, and is NOT
candidate-linked, so DPDP candidate erasure never touches it. Match disclosure
is audited in the shared audit_log (candidate-linked, CASCADE) — not here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobRequisitionRow(Base):
    """One role an organization is hiring for."""

    __tablename__ = "job_requisitions"
    __table_args__ = (
        Index("ix_job_requisitions_org_id", "org_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=False
    )
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    must_have_skills: Mapped[list] = mapped_column(JSON, default=list)
    nice_to_have_skills: Mapped[list] = mapped_column(JSON, default=list)
    min_years_experience: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_degree_level: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    max_notice_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location_tiers: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    min_skill_coverage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    comp_band: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    weights: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
