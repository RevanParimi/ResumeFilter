"""Candidate DPDP portal contracts (S6.4). Read/consent shapes only — no scoring.

These are the render-ready projections the PortalService assembles from the
candidate + ledger + report + profile-source stores. A data principal accessing
their own data needs no consent object; auth == identity of the subject.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field

from app.candidates.schema import CandidateProfile
from app.candidates.store import ResumeSummary
from app.interview.schema import InterviewSummary
from app.ledger.schema import CodingRoundResult, ConsentGrant, InterviewRecord
from app.profile_sources.schema import ProfileSourceSignal
from app.verification.schema import ClaimEvidence, IdentityAssurance


class ConsentState(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class RetentionWindow(BaseModel):
    """One data class's retention posture. `ttl_days` is always the policy;
    `retained_until` is populated only for classes the portal materializes."""

    data_class: str
    ttl_days: int
    oldest_item_at: Optional[datetime] = None
    retained_until: Optional[datetime] = None


class RetentionPolicy(BaseModel):
    windows: list[RetentionWindow] = Field(default_factory=list)
    sweep_active: bool = False  # posture surfaced; mechanical purge is PI-8


class ReportRef(BaseModel):
    """A depth report's existence + when — NOT its advisory internals (v0)."""

    report_id: str
    domain: str
    created_at: datetime


class AccessLogEntry(BaseModel):
    """Candidate-friendly projection of one AuditEntry (who/what/when/allowed)."""

    at: datetime
    actor_type: str                       # "org" | "candidate" | "system"
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None      # org name resolved from actor_id, else None
    action: str
    allowed: Optional[bool] = None        # from details["allowed"] when present
    entity_type: str


class ConsentView(BaseModel):
    grant: ConsentGrant
    state: ConsentState


class MyData(BaseModel):
    """DPDP access view — everything the platform holds about the candidate that
    the portal surfaces. Reports appear as refs only."""

    candidate_id: str
    profile: Optional[CandidateProfile] = None
    resumes: list[ResumeSummary] = Field(default_factory=list)
    sources: list[ProfileSourceSignal] = Field(default_factory=list)
    interview_records: list[InterviewRecord] = Field(default_factory=list)
    coding_rounds: list[CodingRoundResult] = Field(default_factory=list)
    reports: list[ReportRef] = Field(default_factory=list)
    consents: list[ConsentGrant] = Field(default_factory=list)
    identity: Optional[IdentityAssurance] = None  # S7.1 advisory assurance
    # S7.2 advisory employment-claim evidence. A SEPARATE field, never folded
    # into `identity`: a payslip says a job was real, not who the person is.
    claims: Optional[ClaimEvidence] = None
    # S7.3 AI interviews, as HEADERS. Transcripts are the candidate's to read at
    # GET /portal/interviews/{id}; bundling every word into the access view
    # would make the one view they check hardest to actually read.
    interviews: list[InterviewSummary] = Field(default_factory=list)
    retention: RetentionPolicy
