"""Report regressions, grouped by behavior."""

import pytest
from app.graph.nodes.report import make_report_node
from app.graph.state import EvaluationState
from app.schemas.report import (
    CoherenceVerdict,
    DepthBand,
    Evidence,
    EvidenceSource,
    Polarity,
    VerdictStatus,
)
from app.schemas.fabrication import (
    AIGenerationAssessment,
    AILikelihoodBand,
    AISignal,
    ConsistencyBand,
    CrossFieldAssessment,
    CrossFieldFinding,
    FindingSeverity,
    FabricationRiskAssessment,
    FabricationRiskBand,
    RiskComponent,
    DuplicationBand,
    ResumeFarmAssessment,
    ResumeMatch,
)
from app.graph.build import EvaluationEngine


# Report

async def test_report_is_advisory_and_logs_flywheel(services, flywheel):
    verdicts = [
        CoherenceVerdict(
            claim_id="c1", claim_text="Fine-tuned GPT-4", claim_type="fine_tuning",
            coherence_score=0.05, confidence=0.85, status=VerdictStatus.INCOHERENT,
            evidence=[Evidence(source=EvidenceSource.RULE, polarity=Polarity.CONTRADICTS, detail="d")],
            probes=["Which base model and method?"],
        ),
    ]
    state = EvaluationState(
        verdicts=verdicts, depth_score=0.05, overall_confidence=0.85, depth_band=DepthBand.SUPERFICIAL
    )
    out = await make_report_node(services)(state)
    rep = out["report"]

    assert rep.human_review_required is True
    assert rep.advisory is True
    assert "c1" in rep.flagged_claim_ids
    assert len(flywheel.records) == len(verdicts)  # flywheel logged every claim
    assert flywheel.records[0]["outcome"] is None   # open for later feedback


# Report ai

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
    assert "Writing-style observations" in rep.summary
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


async def test_style_only_remains_descriptive_and_cannot_supply_factual_coverage(services):
    from app.graph.nodes.scoring import make_scoring_node

    state = EvaluationState(resume_text="x", ai_generation=_assessment(AILikelihoodBand.LIKELY))
    scored = await make_scoring_node(services)(state)
    rep = (await make_report_node(services)(state.model_copy(update=scored)))["report"]
    assert rep.ai_generation == state.ai_generation
    assert rep.fabrication_risk.band.value == "insufficient_data"
    assert rep.fabrication_risk.score == rep.fabrication_risk.confidence == 0.0
    assert rep.fabrication_risk.components == []
    assert rep.fabrication_risk.scorer_version == 2
    assert rep.advisory and rep.human_review_required


# Report cross field

def _cross_field_assessment(band: ConsistencyBand, severity=FindingSeverity.MAJOR) -> CrossFieldAssessment:
    return CrossFieldAssessment(
        score=0.6,
        confidence=0.9,
        band=band,
        findings=[CrossFieldFinding(id="timeline_overlap", detail="d",
                                    severity=severity, score=0.8)],
        reasoning="[deterministic] 1 finding(s) across 4 evaluated checks",
    )


async def test_report_carries_cross_field_and_major_summary_note(services):
    node = make_report_node(services)
    state = EvaluationState(
        resume_text="x", cross_field=_cross_field_assessment(ConsistencyBand.MAJOR_ISSUES)
    )
    rep = (await node(state))["report"]
    assert rep.cross_field is not None
    assert rep.cross_field.band is ConsistencyBand.MAJOR_ISSUES
    assert "Cross-field consistency: major_issues" in rep.summary
    assert "never a rejection signal" in rep.summary
    assert rep.advisory is True and rep.human_review_required is True


async def test_minor_band_stays_out_of_summary(services):
    node = make_report_node(services)
    state = EvaluationState(
        resume_text="x",
        cross_field=_cross_field_assessment(ConsistencyBand.MINOR_ISSUES, FindingSeverity.MINOR),
    )
    rep = (await node(state))["report"]
    assert rep.cross_field is not None               # data still on the report...
    assert "Cross-field consistency" not in rep.summary  # ...but no reviewer noise


async def test_cross_field_no_assessment_means_none_and_no_record(services, flywheel):
    node = make_report_node(services)
    rep = (await node(EvaluationState(resume_text="x")))["report"]
    assert rep.cross_field is None
    assert not [r for r in flywheel.records if r.get("record_type") == "cross_field"]


async def test_flywheel_gets_one_cross_field_record(services, flywheel):
    node = make_report_node(services)
    state = EvaluationState(
        resume_text="x", cross_field=_cross_field_assessment(ConsistencyBand.MAJOR_ISSUES)
    )
    rep = (await node(state))["report"]
    rows = [r for r in flywheel.records if r.get("record_type") == "cross_field"]
    assert len(rows) == 1
    assert rows[0]["report_id"] == rep.id
    assert rows[0]["band"] == "major_issues"
    assert rows[0]["finding_ids"] == ["timeline_overlap"]
    assert rows[0]["outcome"] is None  # closed later by human feedback


# Report fabrication risk

def _risk(band: FabricationRiskBand, score: float = 0.55) -> FabricationRiskAssessment:
    return FabricationRiskAssessment(
        scorer_version=2,
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
    assert rep.fabrication_risk.scorer_version == records[0]["scorer_version"] == 2
    assert records[0]["components"] == {"cross_field": "major_issues", "resume_farm": "near_duplicate"}
    assert records[0]["outcome"] is None


async def test_summary_context_on_all_bands_with_explicit_refusal(services):
    node = make_report_node(services)
    for band in (FabricationRiskBand.MODERATE, FabricationRiskBand.ELEVATED):
        out = await node(EvaluationState(resume_text="t", fabrication_risk=_risk(band)))
        assert "Factual review context v2" in out["report"].summary
        assert "never a rejection signal" in out["report"].summary

    for band in (FabricationRiskBand.LOW, FabricationRiskBand.INSUFFICIENT_DATA):
        out = await node(
            EvaluationState(resume_text="t", fabrication_risk=_risk(band, score=0.1))
        )
        assert "Factual review context v2" in out["report"].summary
        assert out["report"].fabrication_risk is not None  # field still present


async def test_absent_assessment_stays_absent(services, flywheel):
    node = make_report_node(services)
    out = await node(EvaluationState(resume_text="t"))
    assert out["report"].fabrication_risk is None
    assert not [r for r in flywheel.records if r.get("record_type") == "fabrication_risk"]


# Report resume farm

def _near_dup() -> ResumeFarmAssessment:
    return ResumeFarmAssessment(
        score=0.91,
        confidence=0.9,
        band=DuplicationBand.NEAR_DUPLICATE,
        matches=[ResumeMatch(candidate_id="c1", resume_id="r1", similarity=0.91)],
        corpus_size=4,
        reasoning="r",
    )


async def test_resume_farm_report_carries_assessment_and_flywheel_record(services, flywheel):
    node = make_report_node(services)
    out = await node(EvaluationState(resume_text="text", resume_farm=_near_dup()))
    rep = out["report"]
    assert rep.resume_farm is not None
    assert rep.resume_farm.band is DuplicationBand.NEAR_DUPLICATE
    assert rep.advisory is True and rep.human_review_required is True
    records = [r for r in flywheel.records if r.get("record_type") == "resume_farm"]
    assert len(records) == 1
    assert records[0]["band"] == "near_duplicate"
    assert records[0]["match_count"] == 1
    assert records[0]["corpus_size"] == 4
    assert records[0]["outcome"] is None


async def test_summary_note_only_for_near_duplicate(services):
    node = make_report_node(services)
    loud = await node(EvaluationState(resume_text="t", resume_farm=_near_dup()))
    assert "Content overlap" in loud["report"].summary
    assert "never a rejection signal" in loud["report"].summary

    quiet = await node(
        EvaluationState(
            resume_text="t",
            resume_farm=ResumeFarmAssessment(
                band=DuplicationBand.UNIQUE, confidence=0.9, corpus_size=3
            ),
        )
    )
    assert "Content overlap" not in quiet["report"].summary
    assert quiet["report"].resume_farm.band is DuplicationBand.UNIQUE


async def test_resume_farm_absent_assessment_stays_absent(services, flywheel):
    node = make_report_node(services)
    out = await node(EvaluationState(resume_text="t"))
    assert out["report"].resume_farm is None
    assert not [r for r in flywheel.records if r.get("record_type") == "resume_farm"]


async def test_engine_kwarg_lands_on_the_report(services, genuine_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=genuine_resume, resume_farm=_near_dup())
    assert report.resume_farm is not None
    assert report.resume_farm.score == 0.91


async def test_engine_default_is_none(services, genuine_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=genuine_resume)
    assert report.resume_farm is None


# Report review context

async def test_polished_writing_summary_does_not_claim_authorship(services):
    style = AIGenerationAssessment(
        band=AILikelihoodBand.LIKELY, likelihood=.9, confidence=.8,
        signals=[AISignal(id="uniform_bullets", detail="6 bullets with similar lengths", score=.9)],
    )
    rep = (await make_report_node(services)(EvaluationState(resume_text="text", ai_generation=style)))["report"]
    assert "Writing-style observations" in rep.summary
    assert "cannot establish authorship or dishonesty" in rep.summary
    assert "likelihood" not in rep.summary.lower()
    assert "AI-generation" not in rep.summary
    assert rep.ai_generation == style  # wire fields remain compatible
    assert rep.advisory and rep.human_review_required


async def test_timeline_summary_invites_date_and_role_clarification(services):
    finding = CrossFieldFinding(id="timeline_overlap", detail="Two roles overlap by 8 months", score=.8)
    xf = CrossFieldAssessment(band=ConsistencyBand.MAJOR_ISSUES, score=.75, confidence=.8, findings=[finding])
    rep = (await make_report_node(services)(EvaluationState(resume_text="text", cross_field=xf)))["report"]
    assert "dates and concurrent or part-time roles" in rep.summary
    assert "extraction may be incomplete" in rep.summary
    assert rep.cross_field.findings == [finding]


async def test_duplication_summary_describes_similarity_and_legitimate_templates(services):
    farm = ResumeFarmAssessment(band=DuplicationBand.NEAR_DUPLICATE, score=.91, confidence=.8,
        corpus_size=4, matches=[ResumeMatch(candidate_id="other", resume_id="r", similarity=.91)])
    rep = (await make_report_node(services)(EvaluationState(resume_text="text", resume_farm=farm)))["report"]
    assert "Content overlap" in rep.summary
    assert "shared templates" in rep.summary.lower()
    assert "candidate's own contributions" in rep.summary
    assert "91% estimated content overlap" in rep.summary
    assert rep.resume_farm == farm


@pytest.mark.parametrize("band", list(FabricationRiskBand))
async def test_current_summary_explains_heuristic_and_missing_coverage(services, band):
    risk = FabricationRiskAssessment(scorer_version=2, band=band, score=.1, confidence=.45)
    rep = (await make_report_node(services)(EvaluationState(resume_text="text", fabrication_risk=risk)))["report"]
    assert "v2" in rep.summary
    assert "fraud probability" in rep.summary
    assert "writing style is excluded" in rep.summary
    if band is FabricationRiskBand.INSUFFICIENT_DATA:
        assert "Insufficient data" in rep.summary
        assert "cannot assess" in rep.summary
    assert rep.fabrication_risk == risk


def test_openapi_explains_legacy_style_index_without_breaking_fields(settings, flywheel):
    from app.main import create_app
    from tests.conftest import make_services

    schema = create_app(make_services(settings, flywheel=flywheel)).openapi()["components"]["schemas"]["AIGenerationAssessment"]
    assert "cannot establish authorship or dishonesty" in schema["description"]
    assert "not an authorship probability" in schema["properties"]["likelihood"]["description"]
    assert {"likelihood", "confidence", "band", "signals", "reasoning", "advisory"} <= set(schema["properties"])
