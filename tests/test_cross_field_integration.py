"""End-to-end (offline): the inconsistent fixture earns MAJOR_ISSUES with
explained findings via the heuristic-profile fallback; an explicitly passed
profile takes precedence; the genuine resume stays clean; and S2.2 stays
advisory — depth scoring and claim verdicts are untouched by the band."""

from app.candidates.schema import CandidateProfile, DateRange, EmploymentType, ExperienceEntry
from app.graph.build import EvaluationEngine
from app.schemas.fabrication import ConsistencyBand


async def test_inconsistent_resume_gets_major_issues(services, inconsistent_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=inconsistent_resume, domain="genai")

    assert report.cross_field is not None
    assert report.cross_field.band is ConsistencyBand.MAJOR_ISSUES
    assert len(report.cross_field.findings) >= 2
    assert all(f.detail for f in report.cross_field.findings)
    assert "Cross-field consistency: major_issues" in report.summary
    assert "never a rejection signal" in report.summary
    # Mandates survive: advisory, human decides.
    assert report.advisory is True
    assert report.human_review_required is True


async def test_explicit_profile_takes_precedence(services, genuine_resume):
    # The genuine TEXT is clean, but the caller-supplied profile overlaps:
    # findings prove POST /candidates' extraction wins over re-derivation.
    profile = CandidateProfile(
        experience=[
            ExperienceEntry(title="Lead Engineer", employer="A",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2021-01", end="2022-08")),
            ExperienceEntry(title="Senior Engineer", employer="B",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2020-06", end="2022-08")),
        ],
    )
    engine = EvaluationEngine(services)
    report = await engine.evaluate(
        resume_text=genuine_resume, domain="genai", candidate_profile=profile
    )
    assert report.cross_field is not None
    assert any(f.id == "timeline_overlap" for f in report.cross_field.findings)


async def test_genuine_resume_is_clean_and_depth_unchanged(services, genuine_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=genuine_resume, domain="genai")

    assert report.cross_field is not None
    assert report.cross_field.band is not ConsistencyBand.MAJOR_ISSUES
    # S2.2 must not perturb depth-eval: same expectations as test_integration.
    assert report.depth_band.value in {"solid", "deep"}
    incoherent = [v for v in report.verdicts if v.status.value == "incoherent"]
    assert not incoherent


async def test_report_json_round_trip_includes_cross_field(services, inconsistent_resume):
    from app.schemas.report import Report

    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=inconsistent_resume, domain="genai")
    again = Report.model_validate_json(report.model_dump_json())
    assert again.cross_field == report.cross_field
