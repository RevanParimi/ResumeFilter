"""S8.4 Phase B: the screening service -- registration, bounded processing,
and the read-models."""

from __future__ import annotations

import pytest

from app.graph.build import EvaluationEngine
from app.screening.schema import BatchStatus, ItemStatus


def _org(services, name="Acme Staffing"):
    return services.ledger.create_organization(name).id


def test_registration_is_evaluation_free(services, genuine_resume):
    """The whole point of registering: 500 resumes cannot be evaluated inside
    one request, so upload only inserts rows."""
    org = _org(services)
    batch = services.screening.register(
        org, name="Q3", domain="genai", texts=[genuine_resume, genuine_resume],
        created_by_org_user_id=None,
    )
    assert batch.counts.pending == 2
    assert batch.status is BatchStatus.PENDING
    assert services.candidates.get_candidate("anything") is None
    assert services.report_store.for_candidate("anything") == []


def test_an_empty_batch_is_refused(services):
    org = _org(services)
    with pytest.raises(ValueError):
        services.screening.register(org, name="x", domain="genai", texts=[],
                                    created_by_org_user_id=None)


def test_an_oversize_batch_is_refused(services, genuine_resume):
    org = _org(services)
    cap = services.settings.screening_max_batch_items
    with pytest.raises(ValueError):
        services.screening.register(org, name="x", domain="genai",
                                    texts=["t"] * (cap + 1),
                                    created_by_org_user_id=None)


@pytest.mark.asyncio
async def test_process_is_bounded_and_resumable(services, genuine_resume):
    org = _org(services)
    batch = services.screening.register(
        org, name="Q3", domain="genai",
        texts=[f"{genuine_resume}\nRef {i}" for i in range(3)],
        created_by_org_user_id=None,
    )
    engine = EvaluationEngine(services)

    first = await services.screening.process(org, batch.id, engine=engine)
    assert first.processed <= services.settings.screening_max_items_per_call
    assert first.remaining == 3 - first.processed

    while (await services.screening.process(org, batch.id, engine=engine)).remaining:
        pass

    done = services.screening.get(org, batch.id)
    assert done.counts.done == 3
    assert done.status is BatchStatus.COMPLETE


@pytest.mark.asyncio
async def test_processing_a_finished_batch_is_a_no_op(services, genuine_resume):
    org = _org(services)
    batch = services.screening.register(org, name="x", domain="genai",
                                        texts=[genuine_resume],
                                        created_by_org_user_id=None)
    engine = EvaluationEngine(services)
    await services.screening.process(org, batch.id, engine=engine)
    again = await services.screening.process(org, batch.id, engine=engine)
    assert (again.processed, again.failed, again.remaining) == (0, 0, 0)


@pytest.mark.asyncio
async def test_a_bad_item_fails_alone_and_the_batch_continues(services, genuine_resume):
    """A batch of 500 with one corrupt file has to finish."""
    org = _org(services)
    batch = services.screening.register(
        org, name="x", domain="genai", texts=["   ", genuine_resume],
        created_by_org_user_id=None,
    )
    engine = EvaluationEngine(services)
    while (await services.screening.process(org, batch.id, engine=engine)).remaining:
        pass

    detail = services.screening.get(org, batch.id)
    assert (detail.counts.done, detail.counts.failed) == (1, 1)
    assert detail.status is BatchStatus.PARTIAL

    rows = services.screening.queue(org, batch.id, cursor=None, limit=10).rows
    failed = [r for r in rows if r.status is ItemStatus.FAILED][0]
    assert failed.error == "empty_resume"
    assert "empty_resume" in failed.reason


@pytest.mark.asyncio
async def test_the_queue_row_carries_the_signals_and_a_composed_reason(
    services, genuine_resume
):
    org = _org(services)
    batch = services.screening.register(org, name="x", domain="genai",
                                        texts=[genuine_resume],
                                        created_by_org_user_id=None)
    engine = EvaluationEngine(services)
    await services.screening.process(org, batch.id, engine=engine)

    row = services.screening.queue(org, batch.id, cursor=None, limit=10).rows[0]
    assert row.status is ItemStatus.DONE
    assert row.candidate_id and row.report_id
    assert row.signals is not None
    assert row.reason, "the one-line reason is composed, never stored"
    assert row.advisory is True and row.human_review_required is True


@pytest.mark.asyncio
async def test_a_queue_row_can_never_carry_resume_farm_match_identities(
    services, farm_resume_a, farm_resume_b
):
    """Design §1.1: no Report is on this path, so there is nothing to redact --
    asserted on a batch whose report genuinely HAS farm matches."""
    other = _org(services, "Other Agency")
    mine = _org(services, "Acme Staffing")
    engine = EvaluationEngine(services)

    # Seed another customer's near-duplicate so the farm check has something to
    # find, then screen ours.
    seeded = services.screening.register(other, name="theirs", domain="genai",
                                         texts=[farm_resume_a],
                                         created_by_org_user_id=None)
    await services.screening.process(other, seeded.id, engine=engine)

    ours = services.screening.register(mine, name="mine", domain="genai",
                                       texts=[farm_resume_b],
                                       created_by_org_user_id=None)
    await services.screening.process(mine, ours.id, engine=engine)

    row = services.screening.queue(mine, ours.id, cursor=None, limit=10).rows[0]
    dumped = row.model_dump_json()
    assert "matches" not in dumped
    assert row.signals.farm_corpus_size >= 0, "a COUNT survives; identities never existed here"


@pytest.mark.asyncio
async def test_summary_is_counts_only(services, genuine_resume):
    org = _org(services)
    batch = services.screening.register(org, name="Q3", domain="genai",
                                        texts=[genuine_resume],
                                        created_by_org_user_id=None)
    engine = EvaluationEngine(services)
    await services.screening.process(org, batch.id, engine=engine)

    summary = services.screening.summary(org, batch.id)
    assert summary.n_screened == 1
    assert sum(summary.by_risk_band.values()) == 1
    dumped = summary.model_dump_json()
    for leaked in ("candidate_id", "resume_id", "report_id", "reasoning"):
        assert leaked not in dumped, f"a roll-up must not carry {leaked}"


def test_every_read_is_none_for_another_org(services, genuine_resume):
    a, b = _org(services, "A"), _org(services, "B")
    batch = services.screening.register(a, name="x", domain="genai",
                                        texts=[genuine_resume],
                                        created_by_org_user_id=None)
    assert services.screening.get(b, batch.id) is None
    assert services.screening.queue(b, batch.id, cursor=None, limit=10) is None
    assert services.screening.summary(b, batch.id) is None
    assert services.screening.delete(b, batch.id) is False
    assert services.screening.list(b, cursor=None, limit=10).batches == []
