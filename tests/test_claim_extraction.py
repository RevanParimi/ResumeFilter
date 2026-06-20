from app.graph.nodes.claim_extraction import make_claim_extraction_node
from app.graph.state import EvaluationState


async def test_heuristic_extracts_typed_claims(services, genuine_resume):
    # NullLLM returns nothing → deterministic heuristic fallback runs.
    node = make_claim_extraction_node(services)
    out = await node(EvaluationState(domain="genai", resume_text=genuine_resume))
    types = {c.claim_type for c in out["claims"]}
    assert {"fine_tuning", "rag", "multi_agent"} <= types


async def test_shared_links_folded_into_context(services, fabricated_resume):
    node = make_claim_extraction_node(services)
    out = await node(
        EvaluationState(
            domain="genai",
            resume_text=fabricated_resume,
            github_url="https://github.com/foo/bar",
        )
    )
    assert out["candidate_context"].github_url == "https://github.com/foo/bar"
    assert len(out["claims"]) >= 3
