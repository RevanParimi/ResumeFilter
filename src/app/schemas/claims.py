"""Claim-side contracts: what the engine extracts and reasons over.

These models are DOMAIN-AGNOSTIC. ``claim_type`` is a free string whose
vocabulary is owned by the active :class:`~app.domains.base.DomainModel`
(e.g. the GenAI domain defines ``fine_tuning``, ``rag``, ``multi_agent``).
The core never enumerates domain claim types here.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class Specificity(StrEnum):
    """How concrete a claim is — a primary fakery signal.

    Vague claims ("improved accuracy") are cheap to fabricate; specific claims
    ("raised eval F1 from 0.71→0.83 on a 12k-row held-out set") are not.
    """

    VAGUE = "vague"
    MODERATE = "moderate"
    SPECIFIC = "specific"


class AnchorType(StrEnum):
    """Kinds of FIRST-PARTY external evidence the candidate themselves shared."""

    GITHUB_REPO = "github_repo"
    GITHUB_USER = "github_user"
    PORTFOLIO_URL = "portfolio_url"


class ExternalAnchor(BaseModel):
    """A candidate-provided link a claim can be grounded against (consent-clean)."""

    type: AnchorType
    url: str
    # For github_repo: owner/name parsed out for the GitHub service.
    owner: Optional[str] = None
    repo: Optional[str] = None


class Claim(BaseModel):
    """An atomic, checkable assertion lifted from the resume."""

    id: str = Field(default_factory=lambda: f"clm_{uuid.uuid4().hex[:10]}")
    text: str
    domain: str = "genai"
    claim_type: str = "generic"
    specificity: Specificity = Specificity.MODERATE
    external_anchor: Optional[ExternalAnchor] = None
    # Verbatim resume snippet the claim was derived from (auditability).
    source_excerpt: Optional[str] = None


class CandidateContext(BaseModel):
    """Context used to judge whether a claim COHERES with reality.

    A claim is plausible or not *relative to the candidate's situation*: a
    Tier-3 services-firm junior rarely had sustained GPU access, so "fine-tuned
    an LLM" demands far more corroboration there than at a frontier lab.
    """

    full_name: Optional[str] = None
    role_title: Optional[str] = None
    seniority: Optional[str] = None  # e.g. junior | mid | senior | staff
    years_experience: Optional[float] = None
    # Coarse employer signal: "tier1_ai_lab" | "product_company" |
    # "services_firm" | "startup" | "academia" | "unknown".
    employer_type: Optional[str] = None
    employer_name: Optional[str] = None
    # Whatever else the extractor surfaced that bears on infra/data access.
    notes: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None


class ClaimSet(BaseModel):
    """Output of claim_extraction: the claims plus the context to judge them in."""

    candidate_context: CandidateContext = Field(default_factory=CandidateContext)
    claims: list[Claim] = Field(default_factory=list)
