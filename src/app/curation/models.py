"""Curation storage: legacy queue, source-owned raw observations and approved aliases.

Runtime uses owned observations and approved aliases; legacy rows are read-only. Unattributed raw text is not de-identified.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UnmappedTermRow(Base):
    __tablename__ = "unmapped_terms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    norm_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(Text)
    source_types: Mapped[list] = mapped_column(JSON, default=list)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    canonical: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Retained default also classifies writes by older application versions.
    provenance: Mapped[str] = mapped_column(
        String(32), server_default="legacy_unattributed"
    )


class CurationObservationRow(Base):
    """One raw observation; candidate and source type derive from its source.

    Keeping only source_id avoids inconsistent duplicated candidate ownership.
    Candidate -> profile_sources -> observations is a database-enforced cascade.
    created_at is the fixed lifetime origin; repeats insert separate observations.
    """

    __tablename__ = "curation_observations"
    __table_args__ = (
        CheckConstraint("length(norm_key) BETWEEN 1 AND 128", name="ck_curation_observation_key_length"),
        CheckConstraint("length(display_name) BETWEEN 1 AND 128", name="ck_curation_observation_name_length"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("profile_sources.id", ondelete="CASCADE"), index=True
    )
    norm_key: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class CurationAliasRow(Base):
    """Explicit reviewer-approved vocabulary, independent of raw contributors.

    A shared admin key has no operator identity: admin_user_id stays NULL.
    Historical resolved keys remain in unmapped_terms, never implicitly copied here.
    """

    __tablename__ = "curation_aliases"
    __table_args__ = (
        CheckConstraint("length(norm_key) BETWEEN 1 AND 128", name="ck_curation_alias_key_length"),
        CheckConstraint("length(alias) BETWEEN 1 AND 128", name="ck_curation_alias_name_length"),
        CheckConstraint("length(canonical) BETWEEN 1 AND 64", name="ck_curation_alias_canonical_length"),
        CheckConstraint("length(category) BETWEEN 1 AND 32", name="ck_curation_alias_category_length"),
        CheckConstraint("action IN ('map', 'create')", name="ck_curation_alias_action"),
    )

    norm_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    alias: Mapped[str] = mapped_column(String(128))
    canonical: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(16))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    admin_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
