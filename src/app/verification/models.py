"""ORM rows for the verification spine (S7.1). Postgres-shaped on SQLite.

Two tables on purpose. `verifications` is a durable outcome; a challenge is
short-lived secret material with a create -> consume -> delete lifecycle. Their
sensitivity and their retention story are categorically different, and keeping
them apart means the challenge table can be dropped wholesale later at no cost.

NOTE the absent columns: nothing here can hold a document, image, or biometric.
The single evidence field is a sha256 digest. That is the DPDP posture made
structural rather than procedural.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VerificationRow(Base):
    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(32), index=True)
    assurance_level: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)
    # S7.2: which ladder this row feeds. Pre-S7.2 rows are identity by
    # definition -- they predate the existence of any other subject.
    subject: Mapped[str] = mapped_column(String(24), index=True, default="identity")
    # Which employment claim a document backs (employer label + interval), so
    # two letters for two employers do not collapse into one. A LABEL, never
    # document content -- the length cap is the only thing here above 64 chars
    # and the models test calls that out by name.
    claim_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Set only for third-party adapters -- the IDENTITY_VERIFY grant that
    # authorized the pull. NOT a FK: consent rows are erased on DPDP delete
    # while an audit-bearing verification row may outlive that cascade order.
    consent_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    evidence_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VerificationChallengeRow(Base):
    __tablename__ = "verification_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    verification_id: Mapped[str] = mapped_column(
        ForeignKey("verifications.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(16))
    # Salted hash of the destination the code went to (S1.1 contact_hash). The
    # raw email/phone is used transiently for delivery and never persisted.
    destination_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
