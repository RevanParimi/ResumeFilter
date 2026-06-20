from app.graph.nodes.ingest import make_ingest_node
from app.graph.state import EvaluationState


async def test_ingest_passes_text(services, genuine_resume):
    node = make_ingest_node(services)
    out = await node(EvaluationState(raw_resume_text=genuine_resume))
    assert out["resume_text"].startswith("Priya")


async def test_ingest_empty_is_flagged(services):
    node = make_ingest_node(services)
    out = await node(EvaluationState(raw_resume_text="   "))
    assert out["resume_text"] == ""
    assert "empty_resume" in out["errors"]
