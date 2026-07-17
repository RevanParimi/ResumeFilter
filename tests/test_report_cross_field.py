"""Report node: cross_field pass-through, summary copy, flywheel record."""

from app.graph.nodes.report import make_report_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import (
    ConsistencyBand,
    CrossFieldAssessment,
    CrossFieldFinding,
    FindingSeverity,
)


def _assessment(band: ConsistencyBand, severity=FindingSeverity.MAJOR) -> CrossFieldAssessment:
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
        resume_text="x", cross_field=_assessment(ConsistencyBand.MAJOR_ISSUES)
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
        cross_field=_assessment(ConsistencyBand.MINOR_ISSUES, FindingSeverity.MINOR),
    )
    rep = (await node(state))["report"]
    assert rep.cross_field is not None               # data still on the report...
    assert "Cross-field consistency" not in rep.summary  # ...but no reviewer noise


async def test_no_assessment_means_none_and_no_record(services, flywheel):
    node = make_report_node(services)
    rep = (await node(EvaluationState(resume_text="x")))["report"]
    assert rep.cross_field is None
    assert not [r for r in flywheel.records if r.get("record_type") == "cross_field"]


async def test_flywheel_gets_one_cross_field_record(services, flywheel):
    node = make_report_node(services)
    state = EvaluationState(
        resume_text="x", cross_field=_assessment(ConsistencyBand.MAJOR_ISSUES)
    )
    rep = (await node(state))["report"]
    rows = [r for r in flywheel.records if r.get("record_type") == "cross_field"]
    assert len(rows) == 1
    assert rows[0]["report_id"] == rep.id
    assert rows[0]["band"] == "major_issues"
    assert rows[0]["finding_ids"] == ["timeline_overlap"]
    assert rows[0]["outcome"] is None  # closed later by human feedback
