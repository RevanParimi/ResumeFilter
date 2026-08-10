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
    # S8.4: which organization COMMISSIONED this evaluation. Same nullable +
    # SET NULL reasoning as resumes.org_id -- and note the contrast with
    # candidate_id directly above, which CASCADES because an attached report
    # is the subject's personal data.
    org_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Composite: `for_candidate` filters on candidate_id and orders by
    # created_at, and the leftmost column serves the plain lookup too.
    __table_args__ = (
        Index("ix_reports_candidate_created", "candidate_id", "created_at"),
    )


class OutcomeRow(Base):
    """One human judgment. S8.5 added authorship, because customers write here
    now and an unattributed label is worth very little to a calibration harness.

    Note the third ondelete decision in this file and its contrast with the
    other two: ``org_id`` SET NULLs like ``reports.org_id`` and unlike
    ``screening_batches.org_id``, which CASCADEs. A batch is an organisation's
    own operational work product with no meaning once they are gone; an outcome
    is a LABEL about a person's record that the platform learns from, and
    destroying labels on offboarding would silently degrade the model while the
    report they judge survives.

    ``recorded_by`` is what makes that survivable: with ``org_id`` alone, NULL
    would conflate "an operator recorded this" with "the customer who did has
    offboarded".

    No index on ``org_id``: every query here is report-scoped and
    ``report_id`` already leads. An index is a write cost, not a free hedge.
    """

    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True
    )
    claim_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(Text, default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    #: OutcomeSource -- 'operator' or 'organization'. NOT NULL, no server
    #: default: the application is the source of truth (0004/0014 precedent).
    recorded_by: Mapped[str] = mapped_column(String(16))
    org_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    #: NULL for an X-Org-Key machine caller. Inventing a human would be a false
    #: audit trail (screening_batches.created_by_org_user_id, same words).
    recorded_by_org_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("org_users.id", ondelete="SET NULL"), nullable=True
    )
