"""Report node: ai_generation pass-through, summary copy, flywheel record."""

from app.graph.nodes.report import make_report_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import AIGenerationAssessment, AILikelihoodBand, AISignal


def _assessment(band: AILikelihoodBand) -> AIGenerationAssessment:
    return AIGenerationAssessment(
        likelihood=0.8,
        confidence=0.85,
        band=band,
        signals=[AISignal(id="template_phrases", detail="d", score=0.9)],
        reasoning="[deterministic] 1/4 tells fired",
    )


async def test_report_carries_ai_generation_and_summary_note(services, flywheel):
    node = make_report_node(services)
    state = EvaluationState(
        resume_text="x", ai_generation=_assessment(AILikelihoodBand.LIKELY)
    )
    rep = (await node(state))["report"]
    assert rep.ai_generation is not None
    assert rep.ai_generation.band is AILikelihoodBand.LIKELY
    assert "AI-generation signals: likely" in rep.summary
    assert "never a rejection signal" in rep.summary
    # advisory mandates untouched
    assert rep.advisory is True and rep.human_review_required is True


async def test_unlikely_band_stays_out_of_summary(services):
    node = make_report_node(services)
    state = EvaluationState(
        resume_text="x", ai_generation=_assessment(AILikelihoodBand.UNLIKELY)
    )
    rep = (await node(state))["report"]
    assert rep.ai_generation is not None          # data still on the report...
    assert "AI-generation signals" not in rep.summary  # ...but no reviewer noise


async def test_no_assessment_means_none_and_no_record(services, flywheel):
    node = make_report_node(services)
    rep = (await node(EvaluationState(resume_text="x")))["report"]
    assert rep.ai_generation is None
    assert not [r for r in flywheel.records if r.get("record_type") == "ai_signals"]


async def test_flywheel_gets_one_ai_signals_record(services, flywheel):
    node = make_report_node(services)
    state = EvaluationState(
        resume_text="x", ai_generation=_assessment(AILikelihoodBand.POSSIBLE)
    )
    rep = (await node(state))["report"]
    rows = [r for r in flywheel.records if r.get("record_type") == "ai_signals"]
    assert len(rows) == 1
    assert rows[0]["report_id"] == rep.id
    assert rows[0]["band"] == "possible"
    assert rows[0]["signal_ids"] == ["template_phrases"]
    assert rows[0]["outcome"] is None  # closed later by human feedback
