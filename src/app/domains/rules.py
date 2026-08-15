"""Shared rule machinery every domain builds on (FR-16).

A :class:`SignalRule` expresses a coherence rule as "which expected signal
categories are present?": coherence rises with the fraction of categories
evidenced in the claim text/excerpt/provenance, falls for vague phrasing, and
can be overridden by a domain-specific contradiction (a 'tell').

Scoring constants (see FLOW.md §D — change deliberately, they are calibrated
together with the thresholds in config.yaml):

    coherence  = 0.30 + 0.55 · fraction      (0.30 nothing … 0.85 everything)
    vague penalty = −0.12
    confidence = 0.45 + 0.40 · decisiveness  (decisiveness = |fraction−0.5|·2)
    a fired contradiction pins confidence ≥ 0.85
"""

from __future__ import annotations

from typing import Callable, Optional

from app.domains.base import Rule, RuleFinding
from app.schemas.claims import CandidateContext, Claim, Specificity
from app.schemas.report import Polarity

# A contradiction detector: (haystack, context) → (coherence_delta, reasoning,
# extra_probes) when the tell fires, else None.
ContradictionFn = Callable[
    [str, CandidateContext], Optional[tuple[float, str, list[str]]]
]


def present(haystack: str, keywords: tuple[str, ...]) -> bool:
    """Case-insensitive 'any keyword appears' check."""
    h = haystack.lower()
    return any(k in h for k in keywords)


class SignalRule(Rule):
    """A coherence rule expressed as 'which expected signals are present?'."""

    def __init__(
        self,
        *,
        id: str,
        claim_types: tuple[str, ...],
        description: str,
        categories: dict[str, tuple[str, ...]],
        probes: dict[str, str],
        contradiction: Optional[ContradictionFn] = None,
    ) -> None:
        self.id = id
        self.claim_types = claim_types
        self.description = description
        self._categories = categories  # display_name -> keywords
        self._probes = probes          # display_name -> probe question
        self._contradiction = contradiction

    def evaluate(
        self,
        claim: Claim,
        context: CandidateContext,
        provenance: Optional[list[str]] = None,
    ) -> Optional[RuleFinding]:
        if not self.handles(claim):
            return None

        hay = " ".join(
            filter(None, [claim.text, claim.source_excerpt, context.notes, *(provenance or [])])
        )

        present_: list[str] = []
        missing: list[str] = []
        for name, kws in self._categories.items():
            (present_ if present(hay, kws) else missing).append(name)

        n = len(self._categories)
        fraction = len(present_) / n if n else 0.0
        coherence = 0.30 + 0.55 * fraction
        if claim.specificity == Specificity.VAGUE:
            coherence -= 0.12

        reasoning_bits = [
            f"Expected signals present: {present_ or 'none'}.",
            f"Missing: {missing or 'none'}.",
        ]
        probes = [self._probes[m] for m in missing if m in self._probes]

        # Domain-specific 'tell' override (e.g. fine-tuning a closed model).
        if self._contradiction is not None:
            hit = self._contradiction(hay, context)
            if hit is not None:
                delta, why, extra_probes = hit
                coherence += delta
                reasoning_bits.append(why)
                missing = [*missing, "coherence_contradiction"]
                probes = [*extra_probes, *probes]

        coherence = max(0.0, min(1.0, coherence))

        decisiveness = abs(fraction - 0.5) * 2  # extreme present/absent => decisive
        confidence = 0.45 + 0.40 * decisiveness
        if "coherence_contradiction" in missing:
            confidence = max(confidence, 0.85)
        confidence = max(0.0, min(1.0, confidence))

        if coherence < 0.40:
            polarity = Polarity.CONTRADICTS
        elif coherence > 0.65:
            polarity = Polarity.SUPPORTS
        else:
            polarity = Polarity.NEUTRAL

        return RuleFinding(
            rule_id=self.id,
            polarity=polarity,
            coherence=coherence,
            confidence=confidence,
            reasoning=" ".join(reasoning_bits),
            expected_signals=list(self._categories.keys()),
            missing_signals=missing,
            suggested_probes=probes[:4],
        )
