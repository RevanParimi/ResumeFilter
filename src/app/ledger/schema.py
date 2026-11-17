"""S3.1 ledger contracts — cross-company evaluation ledger data shapes.

Taxonomies (consent purposes) are code constants, not config: changing
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


class ConsentPurpose(StrEnum):
    """What a grant authorizes. ledger_write = an org may submit ledger
    evidence about the candidate; ledger_read = an org may read the
    candidate's consent-gated ledger data (enforced at query time);
    identity_verify = the platform may verify the candidate's identity via an
    EXTERNAL source (S7.1 -- first-party self-service methods need no grant);
    verification_read = an org may see the candidate's identity assurance;
    interview_read = an org may see the candidate's AI-interview assessments
    (S7.3 -- a NEW purpose rather than another widening of verification_read,
    whose dated redefinition window is closed; see LEDGER.md)."""

    LEDGER_WRITE = "ledger_write"
    LEDGER_READ = "ledger_read"
    IDENTITY_VERIFY = "identity_verify"
    VERIFICATION_READ = "verification_read"
    INTERVIEW_READ = "interview_read"


class Organization(BaseModel):
    id: str
    name: str
    status: str = "active"  # active | suspended
    reliability_weight: float = 1.0  # per-org multiplier for S3.4 reputation (neutral=1.0)
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


class AuditEntry(BaseModel):
    id: str
    actor_type: str  # "org" | "candidate" | "system"
    actor_id: Optional[str] = None
    action: str  # e.g. "consent.grant", "consent.revoke"
    entity_type: str
    entity_id: str
    candidate_id: Optional[str] = None
    details: dict = Field(default_factory=dict)
    created_at: datetime
