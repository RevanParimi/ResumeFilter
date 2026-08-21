"""Coverage reaches the Report by the path resume_farm already uses (S9.2)."""

from app.schemas.extraction import CoverageBand, ExtractionCoverage
from app.schemas.report import Report


def test_report_defaults_to_no_coverage():
    """None, not a refusal object: every pre-S9.2 stored report has no coverage
    at all, exactly as it has no ai_generation or cross_field."""
    assert Report().extraction_coverage is None


async def test_coverage_lands_on_the_report(services):
    from app.graph.build import EvaluationEngine

    engine = EvaluationEngine(services)
    cov = ExtractionCoverage(band=CoverageBand.MAJOR_GAPS, checks_run=5)
    report = await engine.evaluate(
        resume_text="Priya Sharma\npriya@example.com\nSenior Data Engineer",
        domain="genai",
        extraction_coverage=cov,
    )
    assert report.extraction_coverage is not None
    assert report.extraction_coverage.band is CoverageBand.MAJOR_GAPS


async def test_major_gaps_says_so_in_the_summary(services):
    from app.graph.build import EvaluationEngine

    engine = EvaluationEngine(services)
    report = await engine.evaluate(
        resume_text="Priya Sharma\npriya@example.com\nSenior Data Engineer",
        domain="genai",
        extraction_coverage=ExtractionCoverage(band=CoverageBand.MAJOR_GAPS, checks_run=5),
    )
    assert "could not be read" in report.summary.lower() or "not extracted" in report.summary.lower()
