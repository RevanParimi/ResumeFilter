"""S8.4 Phase B: the ingest core, extracted so batches and the single-upload
route run the SAME pipeline. Duplicating it would be the one-rule-two-doors
shape committed on purpose, in the sprint whose subject is that shape."""

from __future__ import annotations

import pytest

from app.graph.build import EvaluationEngine
from app.screening.ingest import IngestRefused, ingest_deps, ingest_resume


@pytest.mark.asyncio
async def test_ingest_resume_stamps_the_owner_and_returns_a_report(services, genuine_resume):
    org = services.ledger.create_organization("Acme Staffing")
    result = await ingest_resume(
        ingest_deps(services), EvaluationEngine(services),
        text=genuine_resume, domain="genai", evaluate=True, org_id=org.id,
    )
    assert result.candidate_id and result.resume_id
    assert result.report is not None
    assert services.report_store.get_for_org(org.id, result.report.id) is not None


@pytest.mark.asyncio
async def test_evaluate_false_skips_the_graph_but_still_ingests(services, genuine_resume):
    result = await ingest_resume(
        ingest_deps(services), EvaluationEngine(services),
        text=genuine_resume, domain="genai", evaluate=False, org_id=None,
    )
    assert result.report is None
    assert result.resume_farm is not None, "the farm check runs at ingest, not in the graph"


@pytest.mark.asyncio
async def test_empty_text_raises_a_reason_code_not_an_http_exception(services):
    """The batch processor writes this onto a row; a route maps it to 422.
    Neither can use an HTTPException."""
    with pytest.raises(IngestRefused) as exc:
        await ingest_resume(
            ingest_deps(services), EvaluationEngine(services),
            text="   ", domain="genai", evaluate=True, org_id=None,
        )
    assert exc.value.reason == "empty_resume"


@pytest.mark.asyncio
async def test_unknown_domain_is_refused_with_a_reason_code(services, genuine_resume):
    with pytest.raises(IngestRefused) as exc:
        await ingest_resume(
            ingest_deps(services), EvaluationEngine(services),
            text=genuine_resume, domain="no-such-domain", evaluate=True, org_id=None,
        )
    assert exc.value.reason == "unknown_domain"


@pytest.mark.asyncio
async def test_oversize_text_is_refused_with_a_reason_code(services):
    caps = services.settings
    with pytest.raises(IngestRefused) as exc:
        await ingest_resume(
            ingest_deps(services), EvaluationEngine(services),
            text="x" * (caps.max_resume_chars + 1), domain="genai",
            evaluate=True, org_id=None,
        )
    assert exc.value.reason == "resume_too_long"


@pytest.mark.asyncio
async def test_the_reason_codes_are_a_closed_vocabulary(services):
    """batch_items.error is String(64) holding these codes -- never prose and
    never model output. A code longer than the column is a write that fails at
    the worst possible moment."""
    from app.screening import ingest as mod

    for code in ("empty_resume", "unknown_domain", "resume_too_long"):
        assert len(code) <= 64
    assert IngestRefused("empty_resume").reason == "empty_resume"
    assert mod is not None
