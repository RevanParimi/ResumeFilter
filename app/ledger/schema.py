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


class CodingPlatform(StrEnum):
    """Where an automated coding assessment ran. A code-constant taxonomy like
    InterviewStage/Outcome; OTHER + platform_name absorbs the long tail without
    losing a controlled vocabulary for S3.4 grouping."""

    HACKERRANK = "hackerrank"
    CODILITY = "codility"
    LEETCODE = "leetcode"
    CODESIGNAL = "codesignal"
    HACKEREARTH = "hackerearth"
    INTERNAL = "internal"
    OTHER = "other"


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


class CodingRoundResult(BaseModel):
    """One structured coding-assessment result an org submitted about a candidate
    (S3.3). A peer of InterviewRecord. Field bounds are data hygiene, NOT scoring:
    relating score to max_score is normalization and belongs to S3.4."""

    id: str
    org_id: str
    candidate_id: str
    consent_id: str  # the ledger_write grant this was submitted under
    platform: CodingPlatform
    platform_name: Optional[str] = None  # free name when platform == OTHER
    assessment_name: Optional[str] = None
    score: float = Field(ge=0)
    max_score: Optional[float] = Field(default=None, ge=0)
    percentile: Optional[float] = Field(default=None, ge=0, le=100)
    problem_tags: list[str] = Field(default_factory=list)
    taken_at: datetime
    raw: dict = Field(default_factory=dict)
    created_at: datetime


class ObservedOffer(BaseModel):
    """One compensation offer an org extended to a candidate (S5.2). A peer of
    CodingRoundResult: consent-gated, candidate-linked, DPDP-swept. Carries its
    own role signal (role_family/seniority/city_tier as strings -- the comp
    vocabulary is validated at the API boundary, keeping this module comp-free).
    Field bounds are data hygiene, NOT scoring."""

    id: str
    org_id: str
    candidate_id: str
    consent_id: str  # the ledger_write grant this was submitted under
    role_family: str
    seniority: str
    city_tier: str
    ctc_fixed: float = Field(ge=0)
    ctc_variable: Optional[float] = Field(default=None, ge=0)
    currency: str = "INR"
    offered_at: datetime
    created_at: datetime


class ObservedOfferPoint(BaseModel):
    """De-identified projection for cross-candidate comp aggregation. Carries NO
    candidate/org identity -- only the total CTC and when it was offered, so the
    comp engine can never re-leak who was offered what."""

    total_ctc: float
    offered_at: datetime


class ReputationBand(StrEnum):
    """S3.4 — conservative advisory bands over a candidate's cross-company
    track record. INSUFFICIENT_DATA when we can't say. GUARDED is the only
    negative-leaning band and is corroboration-gated (>= rep_corroboration_orgs
    distinct orgs); a single org can never brand a candidate."""

    INSUFFICIENT_DATA = "insufficient_data"
    GUARDED = "guarded"
    MIXED = "mixed"
    FAVORABLE = "favorable"
    STRONG = "strong"


class ReputationComponent(BaseModel):
    """One evidence type's contribution to the reputation aggregate."""

    id: str  # "interview_records" | "coding_rounds"
    observations: int = 0
    effective_weight: float = Field(default=0.0, ge=0.0)   # sum of recency*reliability*type weights
    mean_value: float = Field(default=0.0, ge=0.0, le=1.0)  # weight-weighted mean outcome value


class ReputationAssessment(BaseModel):
    """S3.4 — advisory cross-company reputation. Beta-Binomial posterior mean
    shrunk toward a neutral prior, recency-decayed, per-org-reliability weighted.

    ADVISORY ONLY: never changes verdicts/depth, never a rejection signal.
    Carries no per-org identities (the raw-records endpoint exposes those under
    the same grant; the aggregate deliberately does not re-leak them)."""

    score: float = Field(default=0.5, ge=0.0, le=1.0)       # posterior mean
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)  # evidence-mass coverage
    band: ReputationBand = ReputationBand.INSUFFICIENT_DATA
    components: list[ReputationComponent] = Field(default_factory=list)
    total_observations: int = 0     # included observations
    distinct_orgs: int = 0          # distinct contributing orgs
    evidence_mass: float = Field(default=0.0, ge=0.0)  # sum of observation weights
    excluded_observations: int = 0  # withdrawn / un-normalizable coding rounds
    reasoning: str = ""
    advisory: bool = True  # mirrors Report: never a rejection signal


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
