"""cross_field node: explicit profile, heuristic fallback, wiring."""

from app.candidates.schema import CandidateProfile, DateRange, EmploymentType, ExperienceEntry
from app.graph.build import _PIPELINE
from app.graph.nodes.cross_field import make_cross_field_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import ConsistencyBand


def _overlapping_profile() -> CandidateProfile:
    return CandidateProfile(
        experience=[
            ExperienceEntry(title="Lead Engineer", employer="A",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2021-01", end="2022-08")),
            ExperienceEntry(title="Senior Engineer", employer="B",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2020-06", end="2022-08")),
        ],
    )


async def test_explicit_profile_is_used_not_the_text(services):
    # The text alone carries no dates; findings prove the profile was used.
    node = make_cross_field_node(services)
    state = EvaluationState(
        resume_text="plain text with no dates at all",
        candidate_profile=_overlapping_profile(),
    )
    out = await node(state)
    a = out["cross_field"]
    assert any(f.id == "timeline_overlap" for f in a.findings)
    assert a.advisory is True


async def test_heuristic_fallback_flags_the_inconsistent_fixture(services, inconsistent_resume):
    node = make_cross_field_node(services)
    out = await node(EvaluationState(resume_text=inconsistent_resume))
    assert out["cross_field"].band is ConsistencyBand.MAJOR_ISSUES


async def test_no_text_produces_no_assessment(services):
    node = make_cross_field_node(services)
    assert await node(EvaluationState()) == {}
    assert await node(EvaluationState(resume_text="   ")) == {}


async def test_genuine_resume_is_not_major(services, genuine_resume):
    node = make_cross_field_node(services)
    out = await node(EvaluationState(resume_text=genuine_resume))
    assert out["cross_field"].band is not ConsistencyBand.MAJOR_ISSUES


def test_pipeline_wires_cross_field_after_ai_signals():
    names = [name for name, _ in _PIPELINE]
    assert names.index("cross_field") == names.index("ai_signals") + 1
