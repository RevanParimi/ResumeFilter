"""Profile-source signal contracts (PI-6 / S6.1).

A profile source (GitHub today; LinkedIn export in S6.2) is ingested into a
structured, normalized, provenanced signal that is ADVISORY EVIDENCE — never a
score or a gate. Stored as a peer of resume extractions, revocable via DPDP
candidate erasure (CASCADE).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ProfileSourceType(StrEnum):
    GITHUB = "github"
    LINKEDIN_EXPORT = "linkedin_export"


class SourceSkillSignal(BaseModel):
    """One skill observed in a source, mapped to the S1.4 taxonomy when known."""

    name: str                                # raw source term, e.g. "Python"
    canonical: Optional[str] = None          # S1.4 taxonomy id, or None if unknown
    category: Optional[str] = None           # taxonomy category, or None
    weight: int = Field(default=0, ge=0)     # aggregated evidence volume (source-defined)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class GitHubActivity(BaseModel):
    """Aggregate activity for a GitHub account (evidence context, not a score)."""

    kind: Literal["github"] = "github"
    public_repos: int = 0
    followers: int = 0
    total_stars: int = 0
    top_languages: dict[str, int] = Field(default_factory=dict)  # name -> bytes
    most_recent_push: Optional[str] = None   # ISO-8601 UTC (sorts chronologically)
    account_created: Optional[str] = None    # ISO-8601 UTC
    sampled_repos: int = 0                    # repos that contributed after filtering


class LinkedInActivity(BaseModel):
    """Aggregate activity from a LinkedIn export (evidence context, not a score).

    De-identified in the sense of no contact PII and no free-text position
    descriptions: positions/education collapse to counts + canonical employer/
    institution names, never raw company or school text. The candidate's own
    ``headline``/``industry``/``languages`` are retained verbatim as low-
    sensitivity first-party context (same posture as storing a candidate's name
    from their resume) — not stripped, not a contact-PII field. No connections,
    no profile summary free-text, no vanity URL.
    """

    kind: Literal["linkedin_export"] = "linkedin_export"
    positions_count: int = 0
    current_positions: int = 0                       # positions with no end date
    employers: list[str] = Field(default_factory=list)      # canonical, deduped
    education_count: int = 0
    institutions: list[str] = Field(default_factory=list)   # canonical, deduped
    certifications_count: int = 0
    languages: list[str] = Field(default_factory=list)
    headline: Optional[str] = None
    industry: Optional[str] = None
    skills_listed: int = 0                            # raw count from Skills.csv


class ProfileSourceSignal(BaseModel):
    """The stored, advisory output of ingesting one profile source once."""

    id: str = Field(default_factory=lambda: f"psrc_{uuid.uuid4().hex[:10]}")
    source_type: ProfileSourceType
    identifier: str                          # the handle / source label
    skills: list[SourceSkillSignal] = Field(default_factory=list)
    activity: GitHubActivity | LinkedInActivity = Field(
        default_factory=GitHubActivity, discriminator="kind"
    )
    method: Literal["api", "export", "unavailable"] = "api"
    fetched_at: datetime
    warnings: list[str] = Field(default_factory=list)
    advisory: bool = True

    @model_validator(mode="before")
    @classmethod
    def _backfill_activity_kind(cls, data):
        """Rows stored before S6.2 have no ``activity.kind``; derive it from the
        already-present ``source_type`` so the discriminated union resolves. Only
        touches a dict activity that lacks the discriminator (a model instance
        already carries its default kind)."""
        if isinstance(data, dict):
            act = data.get("activity")
            if isinstance(act, dict) and "kind" not in act:
                st = data.get("source_type")
                st_val = getattr(st, "value", st)
                act["kind"] = "linkedin_export" if st_val == "linkedin_export" else "github"
        return data
