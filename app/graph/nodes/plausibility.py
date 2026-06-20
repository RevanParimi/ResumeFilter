"""plausibility — THE CORE. Hybrid coherence reasoning.

For each claim we combine:
  (a) the active DomainModel's RULE REGISTRY — deterministic, encoded expertise;
  (b) an LLM DOMAIN-EXPERT pass — prompted as a senior engineer with candidate
      context + provenance, reasoning about whether the claim COHERES.

Both produce (coherence, confidence) plus evidence. We fuse them by
confidence-weighting and emit a fully-explained :class:`CoherenceVerdict`
(status is left for the scoring/calibration node). Conservative throughout:
absent signals lower confidence rather than manufacturing certainty.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.domains.base import get_domain
from app.graph.state import EvaluationState
from app.schemas.claims import CandidateContext, Claim
from app.schemas.report import CoherenceVerdict, Evidence, EvidenceSource, Polarity
from app.services import Services

# Bounds keep a single noisy source from dominating the fused score.
_LLM_MAX_CONFIDENCE = 0.85


def _fuse(pairs: list[tuple[float, float]]) -> tuple[float, float]:
    """Confidence-weighted fusion of (coherence, confidence) signals."""
    if not pairs:
        return 0.5, 0.0
    weight = sum(c for _, c in pairs)
    if weight == 0:
        coherence = sum(co for co, _ in pairs) / len(pairs)
        return coherence, 0.0
    coherence = sum(co * cf for co, cf in pairs) / weight
    confidence = weight / len(pairs)
    return coherence, min(1.0, confidence)


async def _llm_assessment(
    services: Services, domain_key: str, claim: Claim,
    ctx: CandidateContext, grounding: list[str],
) -> tuple[tuple[float, float] | None, Evidence | None, list[str], list[str], str]:
    """Returns ((coherence,confidence)|None, evidence|None, expected, missing, reasoning)."""
    domain = get_domain(domain_key)
    system = domain.plausibility_system_prompt(ctx)
    prompt = (
        f"CLAIM: {claim.text}\n"
        f"claim_type: {claim.claim_type}; specificity: {claim.specificity}\n"
        f"PROVENANCE: {grounding or 'none'}\n\n"
        "Return JSON: {coherence: 0..1, confidence: 0..1, reasoning: str, "
        "expected_signals: [str], missing_signals: [str]}."
    )
    try:
        data = await services.llm.acomplete_json(tier="reasoning", system=system, prompt=prompt)
    except Exception:
        return None, None, [], [], ""
    if not data or "coherence" not in data:
        return None, None, [], [], ""

    coh = max(0.0, min(1.0, float(data.get("coherence", 0.5))))
    conf = max(0.0, min(_LLM_MAX_CONFIDENCE, float(data.get("confidence", 0.0))))
    reasoning = str(data.get("reasoning", "")).strip()
    polarity = (
        Polarity.CONTRADICTS if coh < 0.4 else Polarity.SUPPORTS if coh > 0.65 else Polarity.NEUTRAL
    )
    evidence = Evidence(
        source=EvidenceSource.LLM, polarity=polarity, detail=reasoning or "LLM coherence pass",
        weight=conf, ref="plausibility.llm",
    )
    expected = [str(s) for s in data.get("expected_signals", []) if s]
    missing = [str(s) for s in data.get("missing_signals", []) if s]
    return (coh, conf), evidence, expected, missing, reasoning


def make_plausibility_node(services: Services):
    log = get_logger("node.plausibility")

    async def plausibility(state: EvaluationState) -> dict:
        domain = get_domain(state.domain)
        ctx = state.candidate_context
        verdicts: list[CoherenceVerdict] = []

        for claim in state.claims:
            grounding = state.provenance.get(claim.id, [])
            pairs: list[tuple[float, float]] = []
            evidence: list[Evidence] = []
            expected: set[str] = set()
            missing: set[str] = set()
            reasons: list[str] = []
            probes: list[str] = []

            # (a) rule registry --------------------------------------------------
            for rule in domain.rules_for(claim):
                finding = rule.evaluate(claim, ctx, grounding)
                if finding is None:
                    continue
                pairs.append((finding.coherence, finding.confidence))
                evidence.append(finding.to_evidence())
                expected.update(finding.expected_signals)
                missing.update(finding.missing_signals)
                reasons.append(f"[rule:{finding.rule_id}] {finding.reasoning}")
                probes.extend(finding.suggested_probes)

            # (b) LLM domain-expert pass ----------------------------------------
            llm_pair, llm_ev, llm_exp, llm_miss, llm_reason = await _llm_assessment(
                services, state.domain, claim, ctx, grounding
            )
            if llm_pair is not None:
                pairs.append(llm_pair)
                if llm_ev:
                    evidence.append(llm_ev)
                expected.update(llm_exp)
                missing.update(llm_miss)
                if llm_reason:
                    reasons.append(f"[llm] {llm_reason}")

            # provenance as supporting evidence (neutral-to-supporting) ---------
            for line in grounding:
                pol = Polarity.CONTRADICTS if "does not exist" in line.lower() else Polarity.SUPPORTS
                evidence.append(
                    Evidence(source=EvidenceSource.GITHUB, polarity=pol, detail=line, weight=0.4)
                )

            coherence, confidence = _fuse(pairs)
            verdicts.append(
                CoherenceVerdict(
                    claim_id=claim.id,
                    claim_text=claim.text,
                    claim_type=claim.claim_type,
                    coherence_score=coherence,
                    confidence=confidence,
                    reasoning=" ".join(reasons),
                    expected_signals=sorted(expected),
                    missing_signals=sorted(missing),
                    evidence=evidence,
                    probes=list(dict.fromkeys(probes))[:4],  # de-dup, seed for probe node
                )
            )

        log.info("plausibility_done", verdicts=len(verdicts))
        return {"verdicts": verdicts}

    return plausibility
