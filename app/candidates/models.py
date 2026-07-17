"""ORM rows for the candidate store (S1.2). Postgres-shaped on SQLite.

``*Row`` naming keeps ORM classes distinct from the Pydantic contracts in
``app.candidates.schema``: the profile payload stays Pydantic's to validate,
SQL only stores it (JSON column). ``resumes.raw_text`` deliberately persists
the submitted resume — S1.1 SourceSpan offsets index into it, and the DPDP
delete paths in the store erase it on request.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CandidateRow(Base):
    """One human. Identity = salted email/phone hashes (S1.1 hashing module)."""

    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    phone_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    full_name: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    resumes: Mapped[list["ResumeRow"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )


class ResumeRow(Base):
    """One submitted resume text, versioned per candidate (1, 2, ...)."""

    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("candidate_id", "version", name="uq_resumes_candidate_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    candidate: Mapped[CandidateRow] = relationship(back_populates="resumes")
    extractions: Mapped[list["ExtractionRow"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", passive_deletes=True
    )


class ExtractionRow(Base):
    """One extractor run over one resume — full CandidateProfile as JSON."""

    __tablename__ = "extractions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resume_id: Mapped[str] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(16))  # "llm" | "heuristic"
    profile: Mapped[dict] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    resume: Mapped[ResumeRow] = relationship(back_populates="extractions")


class FingerprintRow(Base):
    """MinHash signature of one resume's contact-masked content (S2.3).

    One row per resume per algo id — rows only ever join on an exact algo so
    incompatible signatures are never compared. DPDP: cascades away with the
    resume/candidate, like every other derived row."""

    __tablename__ = "resume_fingerprints"
    __table_args__ = (
        UniqueConstraint("resume_id", "algo", name="uq_fingerprints_resume_algo"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resume_id: Mapped[str] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    algo: Mapped[str] = mapped_column(String(32), index=True)
    signature: Mapped[list] = mapped_column(JSON)
    shingle_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
