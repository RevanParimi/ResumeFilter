"""ORM rows for AI interviews (S7.3). Postgres-shaped on SQLite.

Two tables: a session (durable outcome + plan) and its turns. Note the absent
columns -- nothing here can hold audio. The one audio field is a sha256 digest,
so "we never store the recording" is structural rather than procedural, exactly
as in S7.1/S7.2.

`transcript` IS stored, deliberately (spec section 0.1): it is first-party
content the candidate produced in order to be evaluated, and an advisory score
whose basis nobody can read is worse for the candidate than the PII cost. It is
candidate-visible and never disclosed to an org in v0.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewSessionRow(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    domain: Mapped[str] = mapped_column(String(32))
    # Which depth report supplied the probes. Still NOT a FK: since S8.1 the
    # constraint IS expressible (reports are in this database now), but adding
    # it needs a batch_alter_table on a live table plus a decision about what a
    # deleted report should do to a finished interview. Deferred deliberately --
    # see the S8.1 spec's follow-ups.
    report_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    # The S7.1 hook, stamped when the session STARTED and never recomputed: a
    # candidate must not be able to verify themselves afterwards and rewrite
    # what the session was worth.
    assurance_level_at_start: Mapped[int] = mapped_column(Integer, default=0)
    planned_questions: Mapped[list] = mapped_column(JSON, default=list)
    # Computed ONCE at completion and stored. Unlike IdentityAssurance and
    # ClaimEvidence -- which depend on the clock and on rows that arrive later,
    # so storing them would store a lie -- an assessment is a closed fact about
    # a finished session, and recomputing it would re-hit a paid model.
    assessment: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    scorer_version: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InterviewTurnRow(Base):
    __tablename__ = "interview_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    question_id: Mapped[str] = mapped_column(String(36))
    # Bounded on purpose: a question is platform-authored, so the transcript
    # stays the ONE unbounded column on either table and a reviewer scanning
    # for "where could bytes live" finds a single answer.
    question_text: Mapped[str] = mapped_column(String(512))
    question_source: Mapped[str] = mapped_column(String(24))
    expected_signals: Mapped[list] = mapped_column(JSON, default=list)
    channel: Mapped[str] = mapped_column(String(8))
    #: The candidate's own words. The ONLY unbounded column on either table.
    transcript: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    #: sha256 of the submitted audio. The bytes are discarded with the request.
    audio_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    audio_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
