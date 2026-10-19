"""provenance — attach first-party GitHub metadata and fetch context.

For claims the candidate linked (or a candidate-level github_url they shared),
fetch repo signals via the GitHub API and attach them only to the linked claims.
Cache within this evaluation; never retrieve another candidate's evidence.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.graph.state import EvaluationState
from app.services import Services
from app.services.github import GitHubRepoEvidence, parse_github_url


def make_provenance_node(services: Services):
    log = get_logger("node.provenance")

    async def provenance(state: EvaluationState) -> dict:
        prov: dict[str, list[str]] = {}
        warnings: dict[str, list[str]] = {}
        cache: dict[tuple[str, str], GitHubRepoEvidence] = {}

        async def repo_evidence(owner: str, repo: str) -> GitHubRepoEvidence:
            key = (owner, repo)
            if key not in cache:
                cache[key] = await services.github.gather_repo_evidence(owner, repo)
            return cache[key]

        # Candidate-level shared repo supplies context to that candidate's claims.
        candidate_anchor = parse_github_url(state.github_url) if state.github_url else None

        for claim in state.claims:
            evidence = GitHubRepoEvidence()
            anchor = claim.external_anchor
            if anchor and anchor.repo:
                evidence = await repo_evidence(anchor.owner, anchor.repo)
            elif candidate_anchor and candidate_anchor.repo:
                evidence = await repo_evidence(candidate_anchor.owner, candidate_anchor.repo)

            if evidence.observations:
                prov[claim.id] = list(evidence.observations)
            if evidence.warnings:
                warnings[claim.id] = list(evidence.warnings)

        log.info("provenance_done", metadata_claims=len(prov), unavailable_claims=len(warnings))
        return {"provenance": prov, "provenance_warnings": warnings}

    return provenance
