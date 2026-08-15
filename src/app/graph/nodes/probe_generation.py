"""probe_generation — questions a fake can't survive, for suspicious claims.

Only claims whose coherence falls below the flag threshold get LLM-crafted
probes (scoped to their missing signals). Rule-suggested probes seeded in
plausibility are preserved as the offline/no-key baseline.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.domains.base import get_domain
from app.graph.state import EvaluationState
from app.services import Services


def make_probe_generation_node(services: Services):
    log = get_logger("node.probe_generation")

    async def probe_generation(state: EvaluationState) -> dict:
        domain = get_domain(state.domain)
        threshold = services.settings.flag_coherence_threshold
        verdicts = state.verdicts
        generated = 0

        for v in verdicts:
            if v.coherence_score >= threshold:
                continue  # only probe the suspicious ones
            try:
                data = await services.llm.acomplete_json(
                    tier="reasoning",
                    system=domain.probe_guidance(),
                    prompt=(
                        f"CLAIM: {v.claim_text}\n"
                        f"MISSING SIGNALS: {v.missing_signals}\n"
                        'Return JSON: {"probes": [str, ...]} with 1-3 questions.'
                    ),
                )
            except Exception as exc:
                log.warning("probe_llm_failed", claim_id=v.claim_id, error=str(exc))
                data = {}

            new = [str(p) for p in data.get("probes", []) if p]
            if new:
                v.probes = list(dict.fromkeys([*v.probes, *new]))[:5]
                generated += 1

        log.info("probes_done", probed_claims=generated)
        return {"verdicts": verdicts}

    return probe_generation
