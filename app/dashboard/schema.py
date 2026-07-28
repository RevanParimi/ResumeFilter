"""Employer dashboard read-model contracts (S5.3). Pure, serializable. No I/O."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel

from app.comp.schema import CompBenchmark
from app.ledger.schema import CodingRoundResult, InterviewRecord, ReputationAssessment
from app.matching.schema import JobRequisition, MatchResult, RequisitionStatus


class SectionStatus(StrEnum):
    AVAILABLE = "available"            # consent granted; payload present
    CONSENT_REQUIRED = "consent_required"  # the reused store read raised ConsentError
    NO_DATA = "no_data"               # consent granted but the source yielded nothing


class RequisitionSummary(BaseModel):
    """One row on the pipeline overview — flags derivable from the req itself."""

    id: str
    title: str
    status: RequisitionStatus
    must_have_skill_count: int
    has_comp_band: bool
    has_skill_coverage_gate: bool
    created_at: datetime
    updated_at: datetime


class DashboardOverview(BaseModel):
    total_requisitions: int
    by_status: dict[str, int]                       # RequisitionStatus value -> count
    requisitions: tuple[RequisitionSummary, ...] = ()
    advisory: bool = True


class RequisitionBoard(BaseModel):
    requisition: JobRequisition
    comp: CompBenchmark
    match: MatchResult
    advisory: bool = True


class ReputationSection(BaseModel):
    status: SectionStatus
    data: Optional[ReputationAssessment] = None


class CodingRoundsSection(BaseModel):
    status: SectionStatus
    data: tuple[CodingRoundResult, ...] = ()


class RecordsSection(BaseModel):
    status: SectionStatus
    data: tuple[InterviewRecord, ...] = ()


class CandidateCard(BaseModel):
    """Per-candidate drill-in, keyed by candidate_id (no PII). Each section is
    independently consent-gated + audited via the reused store reads."""

    candidate_id: str
    reputation: ReputationSection
    coding_rounds: CodingRoundsSection
    records: RecordsSection
    advisory: bool = True
