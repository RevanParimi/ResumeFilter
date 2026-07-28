"""ORM row for stored profile-source signals (S6.1). Postgres-shaped on SQLite.

One row per fetch (append-only history). CASCADEs with the candidate so DPDP
erasure sweeps it — the same contract as resume_fingerprints/extractions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProfileSourceRow(Base):
    __tablename__ = "profile_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    identifier: Mapped[str] = mapped_column(Text)
    signal: Mapped[dict] = mapped_column(JSON)
    method: Mapped[str] = mapped_column(String(16))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
