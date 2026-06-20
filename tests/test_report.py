from app.graph.nodes.report import make_report_node
from app.graph.state import EvaluationState
from app.schemas.report import (
    CoherenceVerdict,
    DepthBand,
    Evidence,
    EvidenceSource,
    Polarity,
    VerdictStatus,
)


async def test_report_is_advisory_and_logs_flywheel(services, flywheel):
    verdicts = [
        CoherenceVerdict(
            claim_id="c1", claim_text="Fine-tuned GPT-4", claim_type="fine_tuning",
            coherence_score=0.05, confidence=0.85, status=VerdictStatus.INCOHERENT,
            evidence=[Evidence(source=EvidenceSource.RULE, polarity=Polarity.CONTRADICTS, detail="d")],
            probes=["Which base model and method?"],
        ),
    ]
    state = EvaluationState(
        verdicts=verdicts, depth_score=0.05, overall_confidence=0.85, depth_band=DepthBand.SUPERFICIAL
    )
    out = await make_report_node(services)(state)
    rep = out["report"]

    assert rep.human_review_required is True
    assert rep.advisory is True
    assert "c1" in rep.flagged_claim_ids
    assert len(flywheel.records) == len(verdicts)  # flywheel logged every claim
    assert flywheel.records[0]["outcome"] is None   # open for later feedback
