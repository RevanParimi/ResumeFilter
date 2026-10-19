"""Full-pipeline (offline) checks: fabrication_risk lands on real reports."""

import json
from pathlib import Path

import pytest

from app.candidates.extractor import heuristic_profile
from app.graph.build import EvaluationEngine
from app.schemas.fabrication import (
    DuplicationBand,
    FabricationRiskAssessment,
    FabricationRiskBand,
    ResumeFarmAssessment,
    ResumeMatch,
)
from tests.conftest import FakeLLM, make_services


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
    assert set(ids) <= {"cross_field", "resume_farm"}
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


@pytest.mark.parametrize("domain", ["genai", "data_eng"])
@pytest.mark.parametrize("farm", [None, ResumeFarmAssessment(
    confidence=0.7, band=DuplicationBand.UNIQUE, corpus_size=4), _near_dup()])
async def test_same_truthful_resume_plain_and_polished_has_identical_factual_risk(settings, domain, farm):
    texts = [Path("tests/fixtures/style_" + name + "_resume.txt").read_text(encoding="utf-8")
             for name in ("plain", "polished")]
    # Hold atomic claims/profile/corpus fixed; only descriptive style varies.
    script = {"extracting atomic": json.dumps({"claims": [
        {"text": "Built a daily ingestion pipeline for finance reporting.", "claim_type": "unknown"}
    ]})}
    profile = heuristic_profile(texts[0])
    reports = [await EvaluationEngine(make_services(settings, llm=FakeLLM(script, settings))).evaluate(
        resume_text=text, domain=domain, candidate_profile=profile, resume_farm=farm) for text in texts]
    plain, polished = reports
    assert polished.ai_generation.band.value == "likely"
    assert plain.ai_generation.likelihood < polished.ai_generation.likelihood
    assert plain.fabrication_risk == polished.fabrication_risk
    assert plain.cross_field == polished.cross_field
    assert plain.resume_farm == polished.resume_farm == farm
    assert plain.fabrication_risk.scorer_version == 2
    assert plain.depth_score == polished.depth_score
    assert plain.depth_band == polished.depth_band
    assert [(v.status, v.coherence_score, v.confidence) for v in plain.verdicts] == [
        (v.status, v.coherence_score, v.confidence) for v in polished.verdicts]
    assert all(r.advisory and r.human_review_required for r in reports)
    if farm is None:
        assert plain.fabrication_risk.band is FabricationRiskBand.INSUFFICIENT_DATA
    elif farm.band is DuplicationBand.UNIQUE:
        assert plain.fabrication_risk.band is FabricationRiskBand.LOW
    else:
        assert plain.fabrication_risk.band is FabricationRiskBand.MODERATE
