"""New evaluations omit style; stored reports retain their optional field."""

from app.graph.build import EvaluationEngine
from app.schemas.fabrication import AIGenerationAssessment, AILikelihoodBand


async def test_new_report_has_no_writing_style_assessment(services, ai_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=ai_resume, domain="genai")

    assert report.ai_generation is None
    assert "Writing-style observations" not in report.summary
    # Mandates survive: advisory, human decides.
    assert report.advisory is True
    assert report.human_review_required is True


async def test_genuine_resume_keeps_depth_without_style_step(services, genuine_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=genuine_resume, domain="genai")

    assert report.ai_generation is None
    # S2.1 must not perturb depth-eval: same expectations as test_integration.
    assert report.depth_band.value in {"solid", "deep"}
    incoherent = [v for v in report.verdicts if v.status.value == "incoherent"]
    assert not incoherent


async def test_report_json_round_trip_includes_ai_generation(services, ai_resume):
    from app.schemas.report import Report

    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=ai_resume, domain="genai")
    report.ai_generation = AIGenerationAssessment(band=AILikelihoodBand.POSSIBLE)
    again = Report.model_validate_json(report.model_dump_json())
    assert again.ai_generation == report.ai_generation
