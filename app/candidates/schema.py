"""Candidate extraction contracts (PI-1 / S1.1).

Every extracted value carries PER-FIELD CONFIDENCE and SOURCE-SPAN PROVENANCE
back to the exact resume text it came from, so downstream consumers (store,
fabrication forensics, ML features) can audit any field to its origin.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class SourceSpan(BaseModel):
    """Character range in the normalized resume text a value was lifted from."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str = ""

    @model_validator(mode="after")
    def _ordered(self) -> "SourceSpan":
        if self.end < self.start:
            raise ValueError("span end must be >= start")
        return self


class ExtractedStr(BaseModel):
    """A scalar string field with extraction confidence + provenance."""

    value: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class DateRange(BaseModel):
    """A career period. Points are "YYYY-MM" or "YYYY" strings — resumes
    rarely carry day precision, and strings stay SQLite/JSON-friendly."""

    start: Optional[str] = None
    end: Optional[str] = None
    is_current: bool = False


class ContactInfo(BaseModel):
    """First-party contact data. Raw values stay (the candidate submitted
    them); *_hash fields let S1.2 identity resolution dedup across resumes
    without comparing raw values. Delete paths arrive with the store (S1.2)."""

    email: Optional[ExtractedStr] = None
    phone: Optional[ExtractedStr] = None
    location: Optional[ExtractedStr] = None
    email_hash: Optional[str] = None
    phone_hash: Optional[str] = None


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    INTERNSHIP = "internship"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    UNKNOWN = "unknown"


class LinkType(StrEnum):
    GITHUB = "github"
    LINKEDIN = "linkedin"
    PORTFOLIO = "portfolio"
    OTHER = "other"


class EducationEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"edu_{uuid.uuid4().hex[:10]}")
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    institution: Optional[str] = None
    # Grade exactly as claimed; canonical CGPA normalization is S1.4's job.
    grade_value: Optional[float] = None
    grade_scale: Optional[str] = None  # "cgpa_10" | "cgpa_4" | "percentage"
    dates: DateRange = Field(default_factory=DateRange)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class ExperienceEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"exp_{uuid.uuid4().hex[:10]}")
    employer: Optional[str] = None
    title: Optional[str] = None
    seniority: Optional[str] = None  # junior | mid | senior | staff
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    dates: DateRange = Field(default_factory=DateRange)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class SkillItem(BaseModel):
    name: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class ProjectEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"prj_{uuid.uuid4().hex[:10]}")
    name: str
    description: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class CertificationEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"crt_{uuid.uuid4().hex[:10]}")
    name: str
    issuer: Optional[str] = None
    year: Optional[int] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class LinkItem(BaseModel):
    """A URL the candidate shared. Verbatim from the resume ⇒ confidence 1.0."""

    type: LinkType = LinkType.OTHER
    url: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class CandidateProfile(BaseModel):
    """The S1.1 contract: everything the extractor lifted from ONE resume."""

    id: str = Field(default_factory=lambda: f"cand_{uuid.uuid4().hex[:10]}")
    full_name: Optional[ExtractedStr] = None
    headline: Optional[ExtractedStr] = None
    contact: ContactInfo = Field(default_factory=ContactInfo)
    education: list[EducationEntry] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    skills: list[SkillItem] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    links: list[LinkItem] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Output of extract_profile(): the profile + how it was produced."""

    profile: CandidateProfile
    method: Literal["llm", "heuristic"]
    warnings: list[str] = Field(default_factory=list)
