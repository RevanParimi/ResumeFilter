"""ORM rows for reports + outcomes (S8.1). Postgres-shaped on SQLite.

``candidate_id`` is nullable AND cascading, and both halves are deliberate:
``POST /evaluate`` produces reports with no candidate attached (it predates the
candidate backbone), while an ATTACHED report must die with its subject. An
unattached report was never personal data.

``body`` is the serialized Report. Schema evolution stays Pydantic's job, not
SQL's -- the same call the raw-sqlite3 store made, kept.

The resume text itself is never persisted here (DPDP / NFR-4): the Report schema
does not contain it, only derived claims.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ReportRow(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    domain: Mapped[str] = mapped_column(String(32))
    depth_band: Mapped[str] = mapped_column(String(32))
    candidate_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True
    )
    body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Composite: `for_candidate` filters on candidate_id and orders by
    # created_at, and the leftmost column serves the plain lookup too.
    __table_args__ = (
        Index("ix_reports_candidate_created", "candidate_id", "created_at"),
    )


class OutcomeRow(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True
    )
    claim_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(Text, default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
