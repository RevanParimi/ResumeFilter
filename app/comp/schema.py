"""Comp intelligence contracts (PI-5 / S5.2). Pure, serializable. Advisory —
every output narrows to a band + confidence, never a decision. The static-band
vocabulary (role families, seniority, city tiers) is owned here so both the
comp engine and the ledger's observed-offer capture agree on it; the ledger
stores these as plain strings and never imports this module (layering)."""

from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.matching.schema import CompBand


class SeniorityBand(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


# Curated role families for the IT launch vertical. A small controlled
# vocabulary keyed by the static band table; unknown roles resolve to the default.
ROLE_FAMILIES: tuple[str, ...] = (
    "backend_engineer",
    "frontend_engineer",
    "fullstack_engineer",
    "data_engineer",
    "data_scientist",
    "ml_engineer",
    "devops_sre",
    "qa_engineer",
    "mobile_engineer",
    "engineering_manager",
)
CITY_TIERS: tuple[str, ...] = ("metro", "tier_2")
DEFAULT_ROLE_FAMILY = "backend_engineer"


class RoleSignal(BaseModel):
    """The resolved (role_family x seniority x city_tier) key comp is computed for."""

    role_family: str
    seniority: SeniorityBand
    city_tier: str

    @model_validator(mode="after")
    def _validate(self) -> "RoleSignal":
        if self.role_family not in ROLE_FAMILIES:
            raise ValueError(f"role_family must be one of {ROLE_FAMILIES}")
        if self.city_tier not in CITY_TIERS:
            raise ValueError(f"city_tier must be one of {CITY_TIERS}")
        return self


class CompBandEstimate(BaseModel):
    """Advisory comp band (annual TOTAL CTC) for a role signal."""

    currency: str = "INR"
    p25: float
    p50: float
    p75: float
    confidence: float = Field(ge=0.0, le=1.0)
    role_family: str
    seniority: SeniorityBand
    city_tier: str
    n_observed: int = 0                      # included observed offers (>= k, else 0)
    sources: tuple[str, ...] = ("static",)   # ("static",) or ("static","observed")
    reasoning: str = ""
    advisory: bool = True


class CompBenchmark(BaseModel):
    """A requisition's stored comp_band positioned against the market estimate."""

    estimate: CompBandEstimate
    requisition_band: Optional[CompBand] = None
    position: Optional[str] = None    # "below" | "at" | "above" | None (no band)
    delta_pct: Optional[float] = None  # (req_mid - p50) / p50
    reasoning: str = ""
    advisory: bool = True
