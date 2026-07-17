"""Report surfaces the farm assessment: field, summary note, flywheel record."""

from app.graph.build import EvaluationEngine
from app.graph.nodes.report import make_report_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import DuplicationBand, ResumeFarmAssessment, ResumeMatch


def _near_dup() -> ResumeFarmAssessment:
    return ResumeFarmAssessment(
        score=0.91,
        confidence=0.9,
        band=DuplicationBand.NEAR_DUPLICATE,
        matches=[ResumeMatch(candidate_id="c1", resume_id="r1", similarity=0.91)],
        corpus_size=4,
        reasoning="r",
    )


async def test_report_carries_assessment_and_flywheel_record(services, flywheel):
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
    assert "Resume-farm signals" in loud["report"].summary
    assert "never a rejection signal" in loud["report"].summary

    quiet = await node(
        EvaluationState(
            resume_text="t",
            resume_farm=ResumeFarmAssessment(
                band=DuplicationBand.UNIQUE, confidence=0.9, corpus_size=3
            ),
        )
    )
    assert "Resume-farm signals" not in quiet["report"].summary
    assert quiet["report"].resume_farm.band is DuplicationBand.UNIQUE


async def test_absent_assessment_stays_absent(services, flywheel):
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
