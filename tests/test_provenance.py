from app.graph.nodes.provenance import make_provenance_node
from app.graph.state import EvaluationState
from app.schemas.claims import Claim


async def test_provenance_uses_first_party_github(services, fake_github):
    claim = Claim(text="Built production RAG", claim_type="rag")
    state = EvaluationState(
        domain="genai",
        github_url="https://github.com/priya-nair/rag-support-bot",
        claims=[claim],
    )
    out = await make_provenance_node(services)(state)
    assert claim.id in out["provenance"]
    assert fake_github.calls == [("priya-nair", "rag-support-bot")]


async def test_provenance_noop_without_links(services):
    claim = Claim(text="Built production RAG", claim_type="rag")
    out = await make_provenance_node(services)(EvaluationState(domain="genai", claims=[claim]))
    assert out["provenance"] == {}
