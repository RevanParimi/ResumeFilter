"""Scoring node computes the unified fabrication risk in the calibration stage —
and provably never lets it touch verdicts or depth outputs."""

from app.graph.nodes.scoring import make_scoring_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import (
    AIGenerationAssessment,
    AILikelihoodBand,
    ConsistencyBand,
    CrossFieldAssessment,
    DuplicationBand,
    FabricationRiskBand,
    ResumeFarmAssessment,
)
from app.schemas.report import CoherenceVerdict
from tests.conftest import make_services


def _verdicts() -> list[CoherenceVerdict]:
    return [
        CoherenceVerdict(
            claim_id="c1", claim_text="t", claim_type="skill",
            coherence_score=0.8, confidence=0.8,
        )
    ]


def _assessments() -> dict:
    return dict(
        ai_generation=AIGenerationAssessment(
            likelihood=0.7, confidence=0.8, band=AILikelihoodBand.LIKELY
        ),
        cross_field=CrossFieldAssessment(
            score=0.6, confidence=0.8, band=ConsistencyBand.MAJOR_ISSUES
        ),
        resume_farm=ResumeFarmAssessment(
            score=0.85, confidence=0.8, band=DuplicationBand.NEAR_DUPLICATE, corpus_size=3
        ),
    )


async def test_scoring_emits_fabrication_risk(settings):
    node = make_scoring_node(make_services(settings))
    out = await node(EvaluationState(verdicts=_verdicts(), **_assessments()))
    risk = out["fabrication_risk"]
    assert risk is not None
    assert risk.band is FabricationRiskBand.ELEVATED
    assert [c.id for c in risk.components] == ["ai_generation", "cross_field", "resume_farm"]


async def test_all_inputs_absent_means_not_assessed(settings):
    node = make_scoring_node(make_services(settings))
    out = await node(EvaluationState(verdicts=_verdicts()))
    assert out["fabrication_risk"] is None


async def test_partial_inputs_still_assess(settings):
    node = make_scoring_node(make_services(settings))
    out = await node(
        EvaluationState(
            verdicts=_verdicts(),
            cross_field=CrossFieldAssessment(
                score=0.1, confidence=0.8, band=ConsistencyBand.CONSISTENT
            ),
        )
    )
    risk = out["fabrication_risk"]
    assert risk is not None
    assert risk.band is FabricationRiskBand.INSUFFICIENT_DATA  # 1 component never asserts


async def test_fabrication_risk_never_touches_depth_or_verdicts(settings):
    node = make_scoring_node(make_services(settings))
    with_risk = await node(EvaluationState(verdicts=_verdicts(), **_assessments()))
    without = await node(EvaluationState(verdicts=_verdicts()))
    assert with_risk["depth_score"] == without["depth_score"]
    assert with_risk["depth_band"] == without["depth_band"]
    assert with_risk["overall_confidence"] == without["overall_confidence"]
    assert [v.status for v in with_risk["verdicts"]] == [v.status for v in without["verdicts"]]
