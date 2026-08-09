"""ORM rows for the evaluation ledger (S3.1). Postgres-shaped on SQLite.

``audit_log`` and ``evaluation_events`` are append-only by convention (the
store never updates or deletes them); consent revocation is an UPDATE of
``revoked_at`` so the fact of having consented survives for audit. DPDP
erasure is the one exception that trumps append-only: every candidate-linked
row carries an ``ondelete="CASCADE"`` FK to ``candidates.id`` and vanishes
with the candidate. Organizations are not candidate-linked and survive.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrganizationRow(Base):
    """One member company of the ledger network."""

    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("name", name="uq_organizations_name"),
        Index("uq_organizations_api_key_hash", "api_key_hash", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | suspended
    # sha256 hex of the org's API key; NULL until a key is issued. Only the hash
    # is ever stored — the plaintext is returned once at issuance and discarded.
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Per-org reliability multiplier for S3.4 reputation aggregation. Nullable +
    # python-default 1.0 (neutral) so existing rows read as neutral; the
    # calibrated values are a PI-8 concern.
    reliability_weight: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=1.0
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# S8.4 Phase B: "Acme Staffing" and "acme staffing" are one customer.
#
# An EXPRESSION index rather than a lowercase companion column, because a
# companion column is a second source of truth maintained by application code at
# two insert sites -- the one-rule-two-doors shape this codebase keeps being bitten
# by. Here the database computes it, so BOTH existing insert paths inherit the
# constraint with no new check: LedgerStore.create_organization and
# AuthStore.create_org_with_owner already map IntegrityError to their own refusal.
#
# MEASURED: SQLite ENFORCES this and does not REFLECT it ("SAWarning: Skipped
# unsupported reflection of expression-based index"), so tests/test_migrations.py
# cannot compare it and proves it behaviourally instead.
Index("uq_organizations_name_ci", func.lower(OrganizationRow.name), unique=True)


class ConsentGrantRow(Base):
    """One purpose-scoped, expiring, revocable consent from a candidate.

    ``org_id`` NULL = any member organization. Revocation sets ``revoked_at``;
    the row is deleted by DPDP erasure (candidate cascade) or by
    ``LedgerStore.delete_organization`` cascading grants scoped to that org
    (and, transitively, their interview records and events)."""

    __tablename__ = "consent_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InterviewRecordRow(Base):
    """One interview outcome one org submitted about one candidate."""

    __tablename__ = "interview_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    consent_id: Mapped[str] = mapped_column(
        ForeignKey("consent_grants.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(16))  # screen | tech | coding | hm
    outcome: Mapped[str] = mapped_column(String(16))
    interviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EvaluationEventRow(Base):
    """Append-only detail attached to an interview record (scores, notes)."""

    __tablename__ = "evaluation_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    record_id: Mapped[str] = mapped_column(
        ForeignKey("interview_records.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CodingRoundResultRow(Base):
    """One structured coding-assessment result one org submitted about one
    candidate (S3.3). A peer of ``interview_records`` — same consent / audit /
    DPDP machinery, but typed platform-assessment fields (platform, score,
    percentile, tags) instead of a coarse pipeline-stage outcome. Append-only;
    candidate-linked so DPDP erasure cascades it."""

    __tablename__ = "coding_round_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    consent_id: Mapped[str] = mapped_column(
        ForeignKey("consent_grants.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(32))  # CodingPlatform value
    platform_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assessment_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percentile: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    problem_tags: Mapped[list] = mapped_column(JSON, default=list)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ObservedOfferRow(Base):
    """One compensation offer one org extended to one candidate (S5.2). Peer of
    coding_round_results: same consent/audit/DPDP machinery. Candidate-linked so
    erasure cascades it; org-linked so org deletion cascades it. The composite
    index serves the comp aggregation query (role_family, seniority, city_tier)."""

    __tablename__ = "observed_offers"
    __table_args__ = (
        Index("ix_observed_offers_role_signal", "role_family", "seniority", "city_tier"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=False
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    consent_id: Mapped[str] = mapped_column(
        ForeignKey("consent_grants.id", ondelete="CASCADE"), index=False
    )
    role_family: Mapped[str] = mapped_column(String(32))
    seniority: Mapped[str] = mapped_column(String(16))
    city_tier: Mapped[str] = mapped_column(String(16))
    ctc_fixed: Mapped[float] = mapped_column(Float)
    ctc_variable: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditLogRow(Base):
    """Append-only audit of every ledger mutation.

    ``candidate_id`` is a nullable CASCADE FK so DPDP erasure also sweeps the
    candidate-linked audit rows; org-only actions (org.create) keep None and
    survive."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_type: Mapped[str] = mapped_column(String(16))  # org | candidate | system
    actor_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    candidate_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True, nullable=True
    )
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
