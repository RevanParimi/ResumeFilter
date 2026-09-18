from app.graph.nodes.provenance import make_provenance_node
from app.graph.state import EvaluationState
from app.schemas.claims import Claim
from app.services.github import parse_github_url


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


async def test_provenance_does_not_reuse_another_evaluations_evidence(services, fake_github):
    fake_github._evidence = {("alice", "project"): ["Alice evidence"],
                             ("bob", "project"): ["Bob evidence"]}
    node = make_provenance_node(services)
    for owner in ("alice", "bob"):
        claim = Claim(text="Built production RAG", claim_type="rag")
        result = await node(EvaluationState(domain="genai", claims=[claim],
                            github_url=f"https://github.com/{owner}/project"))
        assert result["provenance"] == {claim.id: [f"{owner.title()} evidence"]}


async def test_provenance_keeps_claim_anchors_separate(services, fake_github):
    fake_github._evidence = {("alice", "one"): ["First repo evidence"],
                             ("alice", "two"): ["Second repo evidence"]}
    claims = [Claim(text="Built production RAG", external_anchor=parse_github_url(
        f"https://github.com/alice/{repo}")) for repo in ("one", "two", "one")]
    unlinked = Claim(text="Built production RAG")
    result = await make_provenance_node(services)(EvaluationState(
        domain="genai", claims=[*claims, unlinked]))
    assert result["provenance"] == {
        claims[0].id: ["First repo evidence"],
        claims[1].id: ["Second repo evidence"],
        claims[2].id: ["First repo evidence"],
    }
    assert fake_github.calls == [("alice", "one"), ("alice", "two")]
