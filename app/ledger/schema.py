"""S3.1 ledger contracts — cross-company evaluation ledger data shapes.

Taxonomies (stage/outcome/purpose) are code constants, not config: changing
them is a reviewed schema decision, never a deploy-time tunable. DPDP
framing: a consent grant is purpose-scoped (exactly one purpose per grant),
org-scoped (a specific member org, or None = any member org), always
expiring, and revocable at any time. Revocation keeps the row so the audit
trail survives; DPDP *erasure* deletes it (cascades from the candidate).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class InterviewStage(StrEnum):
    SCREEN = "screen"
    TECH = "tech"
    CODING = "coding"
    HM = "hm"


class InterviewOutcome(StrEnum):
    ADVANCED = "advanced"
    REJECTED = "rejected"
    OFFER = "offer"
    HIRED = "hired"
    WITHDRAWN = "withdrawn"
    NO_SHOW = "no_show"


class ConsentPurpose(StrEnum):
    """What a grant authorizes. ledger_write = an org may submit interview
    records about the candidate; ledger_read = an org may query the
    candidate's ledger history (enforced at query time in S3.2)."""

    LEDGER_WRITE = "ledger_write"
    LEDGER_READ = "ledger_read"


class Organization(BaseModel):
    id: str
    name: str
    status: str = "active"  # active | suspended
    created_at: datetime


class ConsentGrant(BaseModel):
    id: str
    candidate_id: str
    org_id: Optional[str] = None  # None = any member organization
    purpose: ConsentPurpose
    granted_at: datetime
    expires_at: datetime  # always expires; DPDP forbids perpetual consent
    revoked_at: Optional[datetime] = None


class ConsentDecision(BaseModel):
    allowed: bool
    reason: str
    grant_id: Optional[str] = None  # the grant that authorized, when allowed


class InterviewRecord(BaseModel):
    id: str
    org_id: str
    candidate_id: str
    consent_id: str  # the grant this record was submitted under
    stage: InterviewStage
    outcome: InterviewOutcome
    interviewed_at: datetime
    summary: Optional[str] = None
    created_at: datetime


class EvaluationEvent(BaseModel):
    id: str
    record_id: str
    candidate_id: str
    event_type: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class AuditEntry(BaseModel):
    id: str
    actor_type: str  # "org" | "candidate" | "system"
    actor_id: Optional[str] = None
    action: str  # e.g. "consent.grant", "consent.revoke", "record.submit"
    entity_type: str
    entity_id: str
    candidate_id: Optional[str] = None
    details: dict = Field(default_factory=dict)
    created_at: datetime
