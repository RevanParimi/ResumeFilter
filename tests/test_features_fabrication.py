from datetime import datetime, timezone
import csv

import pytest
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


@pytest.mark.parametrize("scorer_version", [1, 2, 99])
def test_risk_feature_versions_never_relabel_stored_scores(scorer_version):
    from app.features import default_view, get_feature_registry
    from app.core.config import Settings

    reg = get_feature_registry()
    ctx = _ctx(Report(fabrication_risk=FabricationRiskAssessment(
        scorer_version=scorer_version, score=0.42, band=FabricationRiskBand.MODERATE)))
    for version in (1, 2):
        assert reg.compute_one("fabrication.risk_score", ctx, version=version) == (
            0.42 if scorer_version == version else None)
        assert reg.compute_one("fabrication.risk_band", ctx, version=version) == (
            "moderate" if scorer_version == version else None)
    view = default_view(reg, settings=Settings(_env_file=None, openrouter_api_key=""))
    assert view.version == 2
    assert dict(view.members)["fabrication.risk_score"] == dict(view.members)["fabrication.risk_band"] == 2
    vector = reg.compute_view(view, ctx)
    assert vector.values["fabrication.risk_score"] == (0.42 if scorer_version == 2 else None)


def test_materialized_csv_keeps_historical_and_current_semantics_separate(services, tmp_path):
    from dataclasses import replace
    from app.candidates.extractor import heuristic_profile
    from app.candidates.schema import ExtractionResult
    from app.features import default_view, get_feature_registry
    from app.features.export import export_view_csv
    from app.features.materialize import materialize_candidate
    from tests.conftest import set_extraction_created_at

    reg = get_feature_registry()
    current = default_view(reg, settings=services.settings)
    legacy = replace(current, version=1, members=tuple(
        (n, 1 if n in ("fabrication.risk_score", "fabrication.risk_band") else v)
        for n, v in current.members))
    ids = []
    for version in (1, 2):
        text = "Synthetic Version " + str(version) + "\nSkills: Python"
        cid = services.candidates.ingest(ExtractionResult(profile=heuristic_profile(text),
            method="heuristic"), resume_text=text).candidate_id
        set_extraction_created_at(services.candidates, cid, datetime(2025, 1, 1, tzinfo=timezone.utc))
        services.report_store.save(Report(candidate_id=cid, created_at=AS_OF,
            fabrication_risk=FabricationRiskAssessment(scorer_version=version, score=0.42,
                confidence=0.6, band=FabricationRiskBand.MODERATE)))
        ids.append(cid)
    for view in (legacy, current):
        rows = [materialize_candidate(cid, view=view, registry=reg, as_of=AS_OF,
            candidate_store=services.candidates, report_store=services.report_store,
            ledger_store=services.ledger) for cid in ids]
        path = tmp_path / (str(view.version) + ".csv")
        export_view_csv(rows, view=view, registry=reg, ledger_store=services.ledger, path=str(path))
        with path.open(newline="", encoding="utf-8") as handle:
            exported = list(csv.DictReader(handle))
        for index, row in enumerate(exported, start=1):
            assert row["view_version"] == str(view.version)
            assert row["fabrication.risk_score"] == ("0.42" if index == view.version else "")
            assert row["fabrication.risk_band"] == ("moderate" if index == view.version else "")
