"""Candidate extraction contracts (PI-1 / S1.1).

Every extracted value carries PER-FIELD CONFIDENCE and SOURCE-SPAN PROVENANCE
back to the exact resume text it came from, so downstream consumers (store,
fabrication forensics, ML features) can audit any field to its origin.
"""

from __future__ import annotations

from typing import Optional

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
