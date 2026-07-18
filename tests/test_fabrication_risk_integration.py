"""Full-pipeline (offline) checks: fabrication_risk lands on real reports."""

from app.graph.build import EvaluationEngine
from app.schemas.fabrication import (
    DuplicationBand,
    FabricationRiskAssessment,
    FabricationRiskBand,
    ResumeFarmAssessment,
    ResumeMatch,
)
from tests.conftest import make_services


def _near_dup() -> ResumeFarmAssessment:
    return ResumeFarmAssessment(
        score=0.91,
        confidence=0.9,
        band=DuplicationBand.NEAR_DUPLICATE,
        matches=[ResumeMatch(candidate_id="c1", resume_id="r1", similarity=0.91)],
        corpus_size=4,
        reasoning="r",
    )


async def test_candidates_path_includes_farm_component(settings, genuine_resume):
    engine = EvaluationEngine(make_services(settings))
    report = await engine.evaluate(resume_text=genuine_resume, resume_farm=_near_dup())
    risk = report.fabrication_risk
    assert isinstance(risk, FabricationRiskAssessment)
    ids = [c.id for c in risk.components]
    assert "resume_farm" in ids
    assert set(ids) <= {"ai_generation", "cross_field", "resume_farm"}
    assert risk.advisory is True


async def test_evaluate_path_has_no_farm_component(settings, genuine_resume):
    engine = EvaluationEngine(make_services(settings))
    report = await engine.evaluate(resume_text=genuine_resume)
    risk = report.fabrication_risk
    assert isinstance(risk, FabricationRiskAssessment)
    assert "resume_farm" not in [c.id for c in risk.components]
    assert isinstance(risk.band, FabricationRiskBand)


async def test_fabrication_risk_never_moves_depth(settings, genuine_resume):
    plain = await EvaluationEngine(make_services(settings)).evaluate(resume_text=genuine_resume)
    farmed = await EvaluationEngine(make_services(settings)).evaluate(
        resume_text=genuine_resume, resume_farm=_near_dup()
    )
    assert plain.depth_score == farmed.depth_score
    assert plain.depth_band == farmed.depth_band
    assert [v.status for v in plain.verdicts] == [v.status for v in farmed.verdicts]


async def test_stored_pre_s24_reports_still_validate(settings, genuine_resume):
    engine = EvaluationEngine(make_services(settings))
    report = await engine.evaluate(resume_text=genuine_resume)
    dumped = report.model_dump(mode="json")
    dumped.pop("fabrication_risk")  # simulate a pre-S2.4 stored report
    from app.schemas.report import Report
    assert Report.model_validate(dumped).fabrication_risk is None
