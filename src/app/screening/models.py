"""ORM rows for screening batches (S8.4 Phase B). Postgres-shaped on SQLite.

Three ondelete decisions, and they are deliberately NOT uniform:

* ``screening_batches.org_id`` CASCADEs. A batch is the organisation's own work
  product and has no meaning once the org is gone -- the exact contrast with
  ``resumes.org_id``, which SET NULLs because a resume is a PERSON's data that
  merely happened to be uploaded by that org.
* ``batch_items.batch_id`` CASCADEs. Items are parts of the batch.
* ``candidate_id`` / ``resume_id`` / ``report_id`` SET NULL. A candidate
  erasing themselves must not silently rewrite an organisation's record of how
  many resumes it screened. The item reads "subject erased"; the count stands.

``signals`` is JSON for the same reason ``reports.body`` and
``extractions.profile`` are: schema evolution is Pydantic's job, not SQL's.
``risk_score`` is a real column beside it because it is the QUEUE'S SORT KEY --
ordering by a value inside a JSON blob is dialect-specific and unindexable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON, BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScreeningBatchRow(Base):
    __tablename__ = "screening_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(32))
    # NULL for a machine caller: X-Org-Key is an organisation credential with no
    # human behind it, and inventing one would be a false audit trail.
    created_by_org_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("org_users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    items: Mapped[list["BatchItemRow"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        # The list read filters on org_id and orders by created_at.
        Index("ix_screening_batches_org_created", "org_id", "created_at"),
    )


class BatchItemRow(Base):
    __tablename__ = "batch_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("screening_batches.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")
    #: Cleared when ingest commits; subsequent retry uses ScreeningInputRow.
    #: Pre-ingest ordinary failures retain this copy. An item without either
    #: source of input is reported `skipped` by retry (SCREENING.md §7).
    raw_text: Mapped[str] = mapped_column(Text, default="")
    text_sha256: Mapped[str] = mapped_column(String(64), index=True)
    # NULL is historical/untrusted input. Never backfill inferred ownership.
    input_generation: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    candidate_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True
    )
    resume_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True
    )
    report_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )

    #: The queue's sort key. NULL until the item is evaluated.
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    #: ItemSignals. Scalars only -- see app/screening/schema.py.
    signals: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    #: A reason CODE (`empty_resume`, `pdf_parse_failed`, ...), never prose and
    #: never model output.
    error: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    batch: Mapped[ScreeningBatchRow] = relationship(back_populates="items")

    __table_args__ = (
        # The claim query filters (batch_id, status); the queue orders by
        # risk_score. Both are hot on a 500-item batch.
        Index("ix_batch_items_batch_status", "batch_id", "status"),
        Index("ix_batch_items_batch_risk", "batch_id", "risk_score"),
    )


class ScreeningInputRow(Base):
    """Private retry reference; erasure removes it without changing item counts.

    The resume owns the text. This row replaces the batch's unlinked copy in
    the same transaction as ingest, and lives only until completion or sweep.
    """

    __tablename__ = "screening_item_inputs"

    id: Mapped[str] = mapped_column(
        ForeignKey("batch_items.id", ondelete="CASCADE"), primary_key=True
    )
    resume_id: Mapped[str] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    # Bound when report save commits; deletion ends unfinished retry capability.
    report_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE", name="fk_screening_input_report"),
        nullable=True, index=True,
    )
    # Copy the item's timestamp: retry must not reset its retention window.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScreeningErasureStateRow(Base):
    """One transaction-ordering counter, containing no personal information."""

    __tablename__ = "screening_erasure_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (CheckConstraint("id = 1", name="ck_screening_erasure_singleton"),)


# ORM create_all is a test convenience; production installs this via Alembic.
# BatchItem's parents must exist before installing their deletion triggers.
BatchItemRow.__table__.add_is_dependent_on(ScreeningErasureStateRow.__table__)


@event.listens_for(BatchItemRow.__table__, "after_create")
def _install_erasure_schema(target, connection, **kwargs):
    from app.screening.erasure_schema import install
    install(connection)
