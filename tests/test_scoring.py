from app.graph.nodes.scoring import make_scoring_node
from app.graph.state import EvaluationState
from app.schemas.report import (
    CoherenceVerdict,
    DepthBand,
    Evidence,
    EvidenceSource,
    Polarity,
    VerdictStatus,
)


def _verdict(coh, conf):
    return CoherenceVerdict(
        claim_id="c1",
        claim_text="x",
        claim_type="fine_tuning",
        coherence_score=coh,
        confidence=conf,
        evidence=[Evidence(source=EvidenceSource.RULE, polarity=Polarity.CONTRADICTS, detail="d")],
    )


async def test_scoring_flags_low_coherence_high_confidence(services):
    out = await make_scoring_node(services)(EvaluationState(verdicts=[_verdict(0.05, 0.85)]))
    assert out["verdicts"][0].status == VerdictStatus.INCOHERENT
    assert out["depth_band"] != DepthBand.DEEP


async def test_scoring_defers_when_unsure(services):
    out = await make_scoring_node(services)(EvaluationState(verdicts=[_verdict(0.05, 0.30)]))
    assert out["verdicts"][0].status == VerdictStatus.DEFER
