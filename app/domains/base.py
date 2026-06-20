"""The domain boundary. Everything domain-specific lives behind this.

The LangGraph core knows only:
  * how to ask the active :class:`DomainModel` for its rules,
  * how to ask it for prompt fragments (extraction / plausibility / probes).

It never imports ``genai`` or branches on domain. Adding ``data_eng`` later is:
one module, one ``@register_domain``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from pydantic import BaseModel, Field

from app.schemas.claims import CandidateContext, Claim
from app.schemas.report import Evidence, EvidenceSource, Polarity


# ─────────────────────────────────────────────────────────────────────────────
# Rule layer — deterministic, domain-encoded coherence checks.
# ─────────────────────────────────────────────────────────────────────────────
class RuleFinding(BaseModel):
    """The verdict a single rule renders on a single claim."""

    rule_id: str
    fired: bool = True
    polarity: Polarity = Polarity.NEUTRAL
    # The rule's own coherence assessment for this claim, 0 (incoherent)..1.
    coherence: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning: str = ""
    expected_signals: list[str] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
    suggested_probes: list[str] = Field(default_factory=list)

    def to_evidence(self) -> Evidence:
        return Evidence(
            source=EvidenceSource.RULE,
            polarity=self.polarity,
            detail=self.reasoning,
            weight=self.confidence,
            ref=self.rule_id,
        )


class Rule(ABC):
    """A single coherence check, scoped to one or more claim types."""

    id: str
    claim_types: tuple[str, ...]
    description: str

    def handles(self, claim: Claim) -> bool:
        return claim.claim_type in self.claim_types

    @abstractmethod
    def evaluate(
        self,
        claim: Claim,
        context: CandidateContext,
        provenance: Optional[list[str]] = None,
    ) -> Optional[RuleFinding]:
        """Return a finding, or ``None`` if the rule doesn't apply to this claim."""
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# Domain model — the full plug-in surface.
# ─────────────────────────────────────────────────────────────────────────────
class DomainModel(ABC):
    """Everything the core needs to evaluate one domain."""

    #: stable registry key, e.g. "genai"
    key: str
    #: human label, e.g. "Generative AI Engineering"
    display_name: str

    # --- rule registry --------------------------------------------------------
    @property
    @abstractmethod
    def rules(self) -> list[Rule]:
        ...

    def rules_for(self, claim: Claim) -> list[Rule]:
        return [r for r in self.rules if r.handles(claim)]

    # --- claim taxonomy (vocabulary for claim_type) ---------------------------
    @property
    @abstractmethod
    def claim_types(self) -> list[str]:
        ...

    # --- prompt fragments (injected into services/llm by the nodes) -----------
    @abstractmethod
    def extraction_guidance(self) -> str:
        """Domain hints for claim_extraction (taxonomy, what counts as a claim)."""

    @abstractmethod
    def plausibility_system_prompt(self, context: CandidateContext) -> str:
        """Persona + reasoning instructions for the plausibility LLM pass."""

    @abstractmethod
    def probe_guidance(self) -> str:
        """How to write follow-up questions a fake can't survive in this domain."""


# ─────────────────────────────────────────────────────────────────────────────
# Registry.
# ─────────────────────────────────────────────────────────────────────────────
_REGISTRY: dict[str, DomainModel] = {}


def register_domain(cls: type[DomainModel]) -> type[DomainModel]:
    """Class decorator: instantiate and register a domain by its ``key``."""
    instance = cls()
    if not getattr(instance, "key", None):
        raise ValueError(f"{cls.__name__} must define a non-empty `key`")
    _REGISTRY[instance.key] = instance
    return cls


def get_domain(key: str) -> DomainModel:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise KeyError(
            f"Unknown domain '{key}'. Registered: {sorted(_REGISTRY)}"
        ) from None


def list_domains() -> list[str]:
    return sorted(_REGISTRY)


def _register_instance(instance: DomainModel) -> None:
    """Escape hatch for tests / programmatic registration."""
    _REGISTRY[instance.key] = instance
