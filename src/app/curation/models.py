"""ORM row for the skill-curation review queue (S6.3). Postgres-shaped on SQLite.

Candidate-AGNOSTIC by design: NO candidate FK. It is taxonomy-gap metadata, so
DPDP erasure of a candidate must NOT remove a known taxonomy gap. Keyed by a
unique norm_key (the upsert key); a surrogate id PK matches the other tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
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
