"""claim_extraction — atomic, checkable claims + candidate context.

Primary path: LLM (parsing tier) returns structured claims using the active
domain's extraction guidance. Fallback path: a deterministic heuristic so the
pipeline (and tests) run fully offline with no API key. Either way, output is a
validated :class:`ClaimSet`.
"""

from __future__ import annotations

import re

from app.core.logging import get_logger
from app.domains.base import get_domain
from app.graph.state import EvaluationState
from app.schemas.claims import (
    CandidateContext,
    Claim,
    ClaimSet,
    Specificity,
)
from app.services import Services
from app.services.github import parse_github_url

_NUM = re.compile(r"\d")
_NAMED = re.compile(
    r"(llama|mistral|gpt-|claude|gemini|bert|t5|qwen|gemma|ada-002|bge|e5|"
    r"recall@|mrr|ndcg|f1|p95|p99|a100|h100|lora|qlora)",
    re.IGNORECASE,
)


def _classify_type(line: str, hints: list[tuple[str, tuple[str, ...]]]) -> str | None:
    """First matching (claim_type, keywords) pair wins — hints come from the
    active DomainModel, so the fallback works for every registered domain."""
    low = line.lower()
    for ctype, kws in hints:
        if any(k in low for k in kws):
            return ctype
    return None


def _specificity(line: str) -> Specificity:
    named = bool(_NAMED.search(line))
    numeric = bool(_NUM.search(line))
    if named and numeric:
        return Specificity.SPECIFIC
    if named or numeric:
        return Specificity.MODERATE
    return Specificity.VAGUE


def _heuristic_extract(
    text: str, domain: str, hints: list[tuple[str, tuple[str, ...]]]
) -> ClaimSet:
    claims: list[Claim] = []
    for raw in re.split(r"[\n\r]+", text):
        line = raw.strip().lstrip("-•*• ").strip()
        if len(line) < 12:
            continue
        # Classify on the prose only — a URL's path (e.g. ".../rag-support-bot")
        # must not be mistaken for a claim about RAG.
        m = re.search(r"https?://\S+", line)
        prose = re.sub(r"https?://\S+", "", line).strip()
        ctype = _classify_type(prose, hints)
        if ctype is None:
            continue
        anchor = None
        if m and "github.com" in m.group(0):
            anchor = parse_github_url(m.group(0).rstrip(").,"))
        claims.append(
            Claim(
                text=line,
                domain=domain,
                claim_type=ctype,
                specificity=_specificity(line),
                external_anchor=anchor,
                source_excerpt=line,
            )
        )
    return ClaimSet(candidate_context=CandidateContext(), claims=claims)


def _parse_llm_claimset(payload: dict, domain: str) -> ClaimSet:
    ctx_raw = payload.get("candidate_context", {}) or {}
    ctx = CandidateContext(**{k: v for k, v in ctx_raw.items() if k in CandidateContext.model_fields})
    claims: list[Claim] = []
    for c in payload.get("claims", []) or []:
        anchor = None
        a = c.get("external_anchor")
        if isinstance(a, dict) and a.get("url"):
            anchor = parse_github_url(a["url"]) if "github.com" in a["url"] else None
        try:
            claims.append(
                Claim(
                    text=c["text"],
                    domain=domain,
                    claim_type=c.get("claim_type", "generic"),
                    specificity=Specificity(c.get("specificity", "moderate")),
                    external_anchor=anchor,
                    source_excerpt=c.get("source_excerpt") or c.get("text"),
                )
            )
        except (KeyError, ValueError):
            continue
    return ClaimSet(candidate_context=ctx, claims=claims)


def make_claim_extraction_node(services: Services):
    log = get_logger("node.claim_extraction")

    async def claim_extraction(state: EvaluationState) -> dict:
        domain = get_domain(state.domain)
        text = state.resume_text or ""

        claimset = ClaimSet()
        try:
            payload = await services.llm.acomplete_json(
                tier="parsing",
                system=domain.extraction_guidance(),
                prompt=f"RESUME:\n{text}",
            )
            if payload.get("claims"):
                claimset = _parse_llm_claimset(payload, state.domain)
        except Exception as exc:  # any LLM error → heuristic fallback
            log.warning("extraction_llm_failed", error=str(exc))

        if not claimset.claims:
            # Hints come from the active domain, never hardcoded here (FR-17).
            claimset = _heuristic_extract(
                text, state.domain, domain.heuristic_type_hints()
            )

        # Fold first-party links into candidate context (consent-clean).
        ctx = claimset.candidate_context
        ctx.github_url = ctx.github_url or state.github_url
        ctx.portfolio_url = ctx.portfolio_url or state.portfolio_url

        log.info("claims_extracted", n=len(claimset.claims))
        return {"claims": claimset.claims, "candidate_context": ctx}

    return claim_extraction
