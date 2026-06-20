from app.graph.nodes.plausibility import make_plausibility_node
from app.graph.nodes.probe_generation import make_probe_generation_node
from app.graph.state import EvaluationState
from app.schemas.claims import CandidateContext, Claim


async def test_suspicious_claim_carries_probes(services):
    claim = Claim(
        text="Built production RAG at scale serving millions of users.",
        claim_type="rag",
    )
    state = EvaluationState(
        domain="genai", claims=[claim], candidate_context=CandidateContext()
    )
    verdicts = (await make_plausibility_node(services)(state))["verdicts"]
    state = state.model_copy(update={"verdicts": verdicts})

    out = await make_probe_generation_node(services)(state)
    # Even with NullLLM, rule-seeded probes survive for the suspicious claim.
    assert out["verdicts"][0].probes
