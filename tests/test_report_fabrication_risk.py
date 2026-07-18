"""Report surfaces the unified fabrication risk: field, summary note, flywheel."""

from app.graph.nodes.report import make_report_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import (
    FabricationRiskAssessment,
    FabricationRiskBand,
    RiskComponent,
)


def _risk(band: FabricationRiskBand, score: float = 0.55) -> FabricationRiskAssessment:
    return FabricationRiskAssessment(
        score=score,
        confidence=0.75,
        band=band,
        components=[
            RiskComponent(id="cross_field", band="major_issues", risk=0.75,
                          confidence=0.8, weight=0.8, flagged=True),
            RiskComponent(id="resume_farm", band="near_duplicate", risk=0.80,
                          confidence=0.8, weight=0.8, flagged=True),
        ],
        reasoning="r",
    )


async def test_report_carries_assessment_and_flywheel_record(services, flywheel):
    node = make_report_node(services)
    out = await node(
        EvaluationState(resume_text="t", fabrication_risk=_risk(FabricationRiskBand.ELEVATED))
    )
    rep = out["report"]
    assert rep.fabrication_risk is not None
    assert rep.fabrication_risk.band is FabricationRiskBand.ELEVATED
    assert rep.advisory is True and rep.human_review_required is True
    records = [r for r in flywheel.records if r.get("record_type") == "fabrication_risk"]
    assert len(records) == 1
    assert records[0]["band"] == "elevated"
    assert records[0]["components"] == {"cross_field": "major_issues", "resume_farm": "near_duplicate"}
    assert records[0]["outcome"] is None


async def test_summary_note_on_moderate_and_elevated_only(services):
    node = make_report_node(services)
    for band in (FabricationRiskBand.MODERATE, FabricationRiskBand.ELEVATED):
        out = await node(EvaluationState(resume_text="t", fabrication_risk=_risk(band)))
        assert "Unified fabrication risk" in out["report"].summary
        assert "never a rejection signal" in out["report"].summary

    for band in (FabricationRiskBand.LOW, FabricationRiskBand.INSUFFICIENT_DATA):
        out = await node(
            EvaluationState(resume_text="t", fabrication_risk=_risk(band, score=0.1))
        )
        assert "Unified fabrication risk" not in out["report"].summary
        assert out["report"].fabrication_risk is not None  # field still present


async def test_absent_assessment_stays_absent(services, flywheel):
    node = make_report_node(services)
    out = await node(EvaluationState(resume_text="t"))
    assert out["report"].fabrication_risk is None
    assert not [r for r in flywheel.records if r.get("record_type") == "fabrication_risk"]
