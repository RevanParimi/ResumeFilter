"""ORM row for the DPDP request queue (S8.3 Phase B). Postgres-shaped on SQLite.

``candidate_id`` CASCADES, and the contrast with S8.5's ``outcomes.org_id``
(SET NULL) is the reasoning rather than an inconsistency: an outcome is a label
the PLATFORM learns from and legitimately outlives the org that recorded it,
while a correction request is wholly the subject's own. Erasure is the stronger
right, and a request about a person who no longer exists is personal data with
no subject.

``status`` and ``applied`` are TWO FACTS. ``status`` is what the operator
decided; ``applied`` is whether that decision changed stored data. Collapsing
them into one four-member enum would leave "is an applied correction also
resolved?" answerable two ways, and the subject's own view of their request is
the last place to be vague about whether anything changed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataPrincipalRequestRow(Base):
    __tablename__ = "data_principal_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    #: Did the resolution WRITE anything? Never true for a grievance, and never
    #: true for an email/phone correction, which are handled out of band.
    applied: Mapped[bool] = mapped_column(Boolean, default=False)

    field: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    #: Frozen at request time. The operator reviews the pair the SUBJECT saw.
    current_value: Mapped[str] = mapped_column(Text, default="")
    requested_value: Mapped[str] = mapped_column(Text, default="")
    #: Bounded by max_request_note_chars in the service -- the S8.5 outcome
    #: notes argument, one table over: free text about a named person, typed
    #: into an unbounded Text column, is unbounded input.
    note: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution: Mapped[str] = mapped_column(Text, default="")
    #: WHO decided, in TWO columns for the S8.5 reason: a null FK alone would
    #: conflate "an operator used the shared machine key" with "the admin who
    #: decided this has since been deleted". Both are NULL while open.
    resolved_by: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    resolved_by_admin_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
