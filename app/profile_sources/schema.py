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

from pydantic import BaseModel, Field


class ProfileSourceType(StrEnum):
    GITHUB = "github"
    # LINKEDIN_EXPORT is reserved for S6.2 — added when that adapter lands.


class SourceSkillSignal(BaseModel):
    """One skill observed in a source, mapped to the S1.4 taxonomy when known."""

    name: str                                # raw source term, e.g. "Python"
    canonical: Optional[str] = None          # S1.4 taxonomy id, or None if unknown
    category: Optional[str] = None           # taxonomy category, or None
    weight: int = Field(default=0, ge=0)     # aggregated evidence volume (bytes)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class GitHubActivity(BaseModel):
    """Aggregate activity for a GitHub account (evidence context, not a score)."""

    public_repos: int = 0
    followers: int = 0
    total_stars: int = 0
    top_languages: dict[str, int] = Field(default_factory=dict)  # name -> bytes
    most_recent_push: Optional[str] = None   # ISO-8601 UTC (sorts chronologically)
    account_created: Optional[str] = None    # ISO-8601 UTC
    sampled_repos: int = 0                    # repos that contributed after filtering


class ProfileSourceSignal(BaseModel):
    """The stored, advisory output of ingesting one profile source once."""

    id: str = Field(default_factory=lambda: f"psrc_{uuid.uuid4().hex[:10]}")
    source_type: ProfileSourceType
    identifier: str                          # the handle
    skills: list[SourceSkillSignal] = Field(default_factory=list)
    activity: GitHubActivity = Field(default_factory=GitHubActivity)
    method: Literal["api", "unavailable"] = "api"
    fetched_at: datetime
    warnings: list[str] = Field(default_factory=list)
    advisory: bool = True
