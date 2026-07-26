from datetime import datetime, timezone
from app.features.schema import FeatureContext
import app.features.definitions.fabrication as fab
from app.schemas.fabrication import (
    AIGenerationAssessment, AILikelihoodBand, ConsistencyBand, CrossFieldAssessment,
    CrossFieldFinding, DuplicationBand, FabricationRiskAssessment, FabricationRiskBand,
    FindingSeverity, ResumeFarmAssessment,
)
from app.schemas.report import Report

AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _ctx(report):
    return FeatureContext(candidate_id="c1", as_of=AS_OF, report=report)


def test_risk_score_and_band():
    r = Report(candidate_id="c1", fabrication_risk=FabricationRiskAssessment(
        score=0.42, band=FabricationRiskBand.MODERATE))
    assert fab.risk_score(_ctx(r)) == 0.42
    assert fab.risk_band(_ctx(r)) == "moderate"


def test_none_when_subsystem_absent():
    r = Report(candidate_id="c1")
    assert fab.risk_score(_ctx(r)) is None
    assert fab.ai_generation_band(_ctx(r)) is None
    assert fab.resume_farm_band(_ctx(r)) is None
    assert fab.cross_field_major_count(_ctx(r)) is None
    assert fab.risk_score(_ctx(None)) is None


def test_ai_farm_bands_and_major_count():
    r = Report(
        candidate_id="c1",
        ai_generation=AIGenerationAssessment(band=AILikelihoodBand.POSSIBLE),
        resume_farm=ResumeFarmAssessment(band=DuplicationBand.NEAR_DUPLICATE),
        cross_field=CrossFieldAssessment(band=ConsistencyBand.MAJOR_ISSUES, findings=[
            CrossFieldFinding(id="timeline_overlap", detail="x", severity=FindingSeverity.MAJOR, score=0.8),
            CrossFieldFinding(id="gap", detail="y", severity=FindingSeverity.MINOR, score=0.2),
        ]),
    )
    ctx = _ctx(r)
    assert fab.ai_generation_band(ctx) == "possible"
    assert fab.resume_farm_band(ctx) == "near_duplicate"
    assert fab.cross_field_major_count(ctx) == 1
