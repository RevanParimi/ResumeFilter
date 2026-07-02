"""data_eng domain — proves the plug-in architecture end to end (FR-16..FR-18).

Everything here runs offline: heuristic extraction (domain-provided type hints)
plus the deterministic SignalRule registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domains.base import get_domain, list_domains
from app.graph.build import EvaluationEngine
from app.schemas.claims import CandidateContext, Claim, Specificity

FIXTURES = Path(__file__).parent / "fixtures"

FABRICATED_LINE = (
    "Built ETL pipelines processing petabytes of data daily to improve insights."
)


@pytest.fixture
def data_eng_resume() -> str:
    return (FIXTURES / "data_eng_resume.txt").read_text(encoding="utf-8")


def test_data_eng_registered_with_hints():
    assert "data_eng" in list_domains()
    d = get_domain("data_eng")
    assert "etl_pipeline" in d.claim_types
    assert d.heuristic_type_hints(), "offline fallback needs domain-provided hints"
    # genai keeps working through the same interface (no more graph-layer leak)
    assert get_domain("genai").heuristic_type_hints()


def test_scale_without_tooling_contradiction_fires():
    d = get_domain("data_eng")
    claim = Claim(
        text=FABRICATED_LINE,
        domain="data_eng",
        claim_type="etl_pipeline",
        specificity=Specificity.VAGUE,
        source_excerpt=FABRICATED_LINE,
    )
    findings = [f for f in (r.evaluate(claim, CandidateContext()) for r in d.rules_for(claim)) if f]
    assert findings, "etl_pipeline rule must handle the claim"
    f = findings[0]
    assert f.coherence < 0.35, "petabyte scale with no distributed tooling is a tell"
    assert f.confidence >= 0.85
    assert f.suggested_probes


def test_genuine_streaming_claim_scores_coherent():
    d = get_domain("data_eng")
    text = (
        "Designed streaming ingestion on Kafka with Flink delivering exactly-once "
        "semantics; sustained 50k events/sec with consumer lag alerting."
    )
    claim = Claim(
        text=text,
        domain="data_eng",
        claim_type="streaming",
        specificity=Specificity.SPECIFIC,
        source_excerpt=text,
    )
    findings = [f for f in (r.evaluate(claim, CandidateContext()) for r in d.rules_for(claim)) if f]
    assert findings and findings[0].coherence >= 0.6


async def test_end_to_end_data_eng_offline(services, data_eng_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=data_eng_resume, domain="data_eng")

    assert report.domain == "data_eng"
    assert report.human_review_required is True
    types = {v.claim_type for v in report.verdicts}
    assert {"etl_pipeline", "streaming", "warehouse_modeling"} <= types
    # A genuine, detailed data-eng resume must not be flagged.
    assert not report.flagged_claim_ids
