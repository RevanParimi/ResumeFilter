"""End-to-end (offline): the AI-drafted fixture earns a LIKELY band with
explained deterministic signals; the genuine resume never does; and S2.1
stays advisory — depth scoring and claim verdicts are untouched by the band."""

from app.graph.build import EvaluationEngine
from app.schemas.fabrication import AILikelihoodBand, SignalSource


async def test_ai_generated_resume_gets_likely_band(services, ai_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=ai_resume, domain="genai")

    assert report.ai_generation is not None
    assert report.ai_generation.band is AILikelihoodBand.LIKELY
    det = [
        s for s in report.ai_generation.signals
        if s.source is SignalSource.DETERMINISTIC
    ]
    assert len(det) >= 2                       # multiple independent tells...
    assert all(s.detail for s in det)          # ...each one explained
    assert "AI-generation signals: likely" in report.summary
    # Mandates survive: advisory, human decides.
    assert report.advisory is True
    assert report.human_review_required is True


async def test_genuine_resume_is_not_likely_and_depth_unchanged(services, genuine_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=genuine_resume, domain="genai")

    assert report.ai_generation is not None
    assert report.ai_generation.band is not AILikelihoodBand.LIKELY
    # S2.1 must not perturb depth-eval: same expectations as test_integration.
    assert report.depth_band.value in {"solid", "deep"}
    incoherent = [v for v in report.verdicts if v.status.value == "incoherent"]
    assert not incoherent


async def test_report_json_round_trip_includes_ai_generation(services, ai_resume):
    from app.schemas.report import Report

    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=ai_resume, domain="genai")
    again = Report.model_validate_json(report.model_dump_json())
    assert again.ai_generation == report.ai_generation
