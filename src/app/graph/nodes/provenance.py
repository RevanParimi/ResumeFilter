"""provenance — ground anchored claims against first-party GitHub evidence.

For claims the candidate linked (or a candidate-level github_url they shared),
fetch repo signals via the GitHub API and attach them only to the linked claims.
Cache within this evaluation; never retrieve another candidate's evidence.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.graph.state import EvaluationState
from app.services import Services
from app.services.github import parse_github_url


def make_provenance_node(services: Services):
    log = get_logger("node.provenance")

    async def provenance(state: EvaluationState) -> dict:
        prov: dict[str, list[str]] = {}
        cache: dict[tuple[str, str], list[str]] = {}

        async def repo_evidence(owner: str, repo: str) -> list[str]:
            key = (owner, repo)
            if key not in cache:
                cache[key] = await services.github.gather_repo_evidence(owner, repo)
            return cache[key]

        # Candidate-level shared repo (applies as soft grounding to all claims).
        candidate_anchor = parse_github_url(state.github_url) if state.github_url else None

        for claim in state.claims:
            evidence: list[str] = []
            anchor = claim.external_anchor
            if anchor and anchor.repo:
                evidence = await repo_evidence(anchor.owner, anchor.repo)
            elif candidate_anchor and candidate_anchor.repo:
                evidence = await repo_evidence(candidate_anchor.owner, candidate_anchor.repo)

            if evidence:
                prov[claim.id] = list(evidence)

        log.info("provenance_done", grounded_claims=len(prov))
        return {"provenance": prov}

    return provenance
