"""Demand-side matching contracts (PI-5 / S5.1).

Pure, serializable request/result models + enums. No I/O, no callables. The
engine lives in match.py. A JobRequisition is org-owned; matching is advisory —
it narrows and orders, never auto-rejects.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.features.ranking_schema import Contribution

_LOC_TIERS = ("metro", "tier_2")
_DEGREE_LEVELS = ("none", "diploma", "bachelor", "master", "doctorate")


class RequisitionStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"


class CompBand(BaseModel):
    """Advisory compensation band. Stored on the requisition; NOT a matching
    term in S5.1 (comp intelligence is S5.2)."""

    currency: str = "INR"
    ctc_min: Optional[float] = Field(default=None, ge=0.0)
    ctc_max: Optional[float] = Field(default=None, ge=0.0)
    variable_max: Optional[float] = Field(default=None, ge=0.0)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _bounds(self) -> "CompBand":
        if (
            self.ctc_min is not None
            and self.ctc_max is not None
            and self.ctc_max < self.ctc_min
        ):
            raise ValueError("ctc_max must be >= ctc_min")
        return self


class MatchWeights(BaseModel):
    """Optional per-term weight overrides; each falls back to its match_* default."""

    skill_coverage: Optional[float] = Field(default=None, gt=0.0)
    years: Optional[float] = Field(default=None, gt=0.0)
    degree: Optional[float] = Field(default=None, gt=0.0)
    notice: Optional[float] = Field(default=None, gt=0.0)
    location: Optional[float] = Field(default=None, gt=0.0)


class JobRequisitionInput(BaseModel):
    """Writable requisition fields (API create/replace payload). Skills are
    free-text here; the store normalizes them to canonical taxonomy keys."""

    title: str
    status: RequisitionStatus = RequisitionStatus.OPEN
    must_have_skills: tuple[str, ...] = ()
    nice_to_have_skills: tuple[str, ...] = ()
    min_years_experience: Optional[float] = Field(default=None, ge=0.0)
    min_degree_level: Optional[str] = None
    max_notice_days: Optional[int] = Field(default=None, ge=0)
    location_tiers: Optional[tuple[str, ...]] = None
    remote: bool = False
    min_skill_coverage: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    comp_band: Optional[CompBand] = None
    weights: Optional[MatchWeights] = None

    @model_validator(mode="after")
    def _validate(self) -> "JobRequisitionInput":
        if not self.must_have_skills and not self.nice_to_have_skills:
            raise ValueError("requisition needs at least one must-have or nice-to-have skill")
        if self.min_degree_level is not None and self.min_degree_level not in _DEGREE_LEVELS:
            raise ValueError(f"min_degree_level must be one of {_DEGREE_LEVELS}")
        if self.location_tiers is not None:
            for t in self.location_tiers:
                if t not in _LOC_TIERS:
                    raise ValueError(f"location tier must be in {_LOC_TIERS}: {t!r}")
        return self


class JobRequisition(JobRequisitionInput):
    """A stored requisition (skills are canonical). Server-owned id/org/timestamps."""

    id: str
    org_id: str
    created_at: datetime
    updated_at: datetime


class SkillMatchDetail(BaseModel):
    """Per-candidate skill explanation for one requisition."""

    matched: tuple[str, ...] = ()
    missing_must_have: tuple[str, ...] = ()
    matched_nice_to_have: tuple[str, ...] = ()
    coverage: float  # [0,1], the value fed to the match.skill_coverage term


class MatchedCandidate(BaseModel):
    candidate_id: str
    score: float          # composite [0,1]
    coverage: float       # share of ranking weight that had data (S4.3 semantics)
    skill: SkillMatchDetail
    contributions: tuple[Contribution, ...] = ()
    missing: tuple[str, ...] = ()  # ranking terms with no value for this candidate


class MatchResult(BaseModel):
    advisory: bool = True
    requisition_id: str
    as_of: Optional[datetime] = None
    view_name: str
    view_version: int
    pool_size: int
    filtered_size: int
    ranked: tuple[MatchedCandidate, ...] = ()
    #: Why the ranking is empty, when it is. `no_materialized_candidates` means
    #: the feature store has not been materialized -- a SERVER-side state, which
    #: is why this is a 200 with a reason rather than a 422 blaming the caller
    #: (S8.4 Phase B §1.11). None on every successful match.
    reason: Optional[str] = None
