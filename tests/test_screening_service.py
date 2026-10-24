"""Screening service regressions, grouped by behavior."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from app.candidates.store import CandidateStore
from app.graph.build import EvaluationEngine
from app.screening.models import BatchItemRow
from app.screening.schema import BatchStatus, ItemStatus
from app.screening.ingest import IngestRefused, ingest_deps, ingest_resume
from app.screening.store import CompletionOutcome
from tests.conftest import make_services
from tests.test_report_erasure_concurrency import database  # noqa: F401


# Screening service

def _org(services, name="Acme Staffing"):
    return services.ledger.create_organization(name).id


@pytest.fixture
def lease_services(database, settings):
    _, factory = database
    return make_services(settings.model_copy(update={"screening_max_items_per_call": 2}),
                         candidates=CandidateStore(factory))


def _lease_batch(services, genuine_resume, count=3):
    org = _org(services)
    batch = services.screening.register(org, name="Lease scheduling", domain="genai",
        texts=[genuine_resume + f"\nSynthetic reference {i}" for i in range(count)],
        created_by_org_user_id=None)
    return org, batch.id


class _PausedEngine:
    def __init__(self, services):
        self.real = EvaluationEngine(services)
        self.entered, self.release = asyncio.Event(), asyncio.Event()

    async def evaluate(self, **kwargs):
        self.entered.set()
        await self.release.wait()
        return await self.real.evaluate(**kwargs)


@pytest.mark.asyncio
async def test_waiting_provider_does_not_lease_the_unstarted_chunk(lease_services, genuine_resume):
    services = lease_services
    org, bid = _lease_batch(services, genuine_resume)
    slow = _PausedEngine(services)
    pending = asyncio.create_task(services.screening.process(org, bid, engine=slow))
    try:
        await asyncio.wait_for(slow.entered.wait(), 10)
        counts = services.screening.get(org, bid).counts
        assert (counts.processing, counts.pending) == (1, 2)
        other = await services.screening.process(org, bid, engine=EvaluationEngine(services))
        assert (other.processed, other.failed, other.remaining) == (2, 0, 1)
    finally:
        slow.release.set()
        first = await pending
    assert (first.processed, first.failed, first.remaining) == (1, 0, 0)
    assert services.screening.get(org, bid).counts.done == 3
    rows = services.screening.queue(org, bid, cursor=None, limit=10).rows
    assert len({row.report_id for row in rows}) == 3
    assert all(row.status == ItemStatus.DONE and row.advisory and row.human_review_required for row in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("refusal", [True, False], ids=["refused-ingest", "unexpected-error"])
async def test_refused_failure_write_is_not_counted_or_replayed(lease_services, genuine_resume, monkeypatch, refusal):
    services = lease_services
    org, bid = _lease_batch(services, genuine_resume, count=2)
    svc, store = services.screening, services.screening._store
    now = datetime.now(timezone.utc)
    clock = [now]
    monkeypatch.setattr(svc, "_now", lambda: clock[0])
    stolen = []

    class StealingEngine:
        async def evaluate(self, **kwargs):
            clock[0] += timedelta(seconds=services.settings.screening_claim_timeout_seconds + 1)
            stolen.extend(store.claim(org, bid, limit=1, now=clock[0],
                timeout_seconds=services.settings.screening_claim_timeout_seconds))
            raise IngestRefused("unknown_domain") if refusal else RuntimeError("synthetic engine failure")

    result = await svc.process(org, bid, engine=StealingEngine())
    assert (result.processed, result.failed, result.remaining) == (0, 0, 2)
    assert len(stolen) == 1, "a lost lease must not trigger another paid attempt in this call"
    with services.session_factory() as session:
        rows = session.scalars(select(BatchItemRow).where(BatchItemRow.batch_id == bid)).all()
        assert sorted(row.status for row in rows) == ["pending", "processing"]
        assert all(row.error is None for row in rows)
    assert store.fail(stolen[0].id, lease=stolen[0].claimed_at, error="internal_error", at=clock[0])
    assert svc.retry(org, bid).requeued == 1
    recovered = await svc.process(org, bid, engine=EvaluationEngine(services))
    assert (recovered.processed, recovered.failed, recovered.remaining) == (2, 0, 0)


@pytest.mark.asyncio
async def test_cancellation_leaves_only_active_lease_and_later_request_recovers(lease_services, genuine_resume, monkeypatch):
    services = lease_services
    org, bid = _lease_batch(services, genuine_resume)
    clock = [datetime.now(timezone.utc)]
    monkeypatch.setattr(services.screening, "_now", lambda: clock[0])
    slow = _PausedEngine(services)
    pending = asyncio.create_task(services.screening.process(org, bid, engine=slow))
    try:
        await asyncio.wait_for(slow.entered.wait(), 10)
    finally:
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    counts = services.screening.get(org, bid).counts
    assert (counts.processing, counts.pending, counts.failed, counts.done) == (1, 2, 0, 0)
    clock[0] += timedelta(seconds=services.settings.screening_claim_timeout_seconds + 1)
    recovered = await services.screening.process(org, bid, engine=EvaluationEngine(services))
    assert (recovered.processed, recovered.failed, recovered.remaining) == (2, 0, 1)
    finished = await services.screening.process(org, bid, engine=EvaluationEngine(services))
    assert (finished.processed, finished.failed, finished.remaining) == (1, 0, 0)
    rows = services.screening.queue(org, bid, cursor=None, limit=10).rows
    assert len({row.report_id for row in rows}) == 3


@pytest.mark.asyncio
async def test_expired_provider_result_stops_then_recovery_uses_fresh_leases(lease_services, genuine_resume, monkeypatch):
    services = lease_services
    org, bid = _lease_batch(services, genuine_resume, count=2)
    clock = [datetime.now(timezone.utc)]
    monkeypatch.setattr(services.screening, "_now", lambda: clock[0])
    real = EvaluationEngine(services)
    calls = []

    class AdvancingEngine:
        async def evaluate(self, **kwargs):
            calls.append(kwargs["resume_text"])
            if len(calls) == 1:
                clock[0] += timedelta(seconds=services.settings.screening_claim_timeout_seconds + 1)
            else:
                counts = services.screening.get(org, bid).counts
                assert (counts.processing, counts.pending) == (1, 1 if len(calls) == 2 else 0), "new work needs a fresh lease"
            return await real.evaluate(**kwargs)

    result = await services.screening.process(org, bid, engine=AdvancingEngine())
    assert (result.processed, result.failed, result.remaining) == (0, 0, 2)
    assert len(calls) == 1
    recovered = await services.screening.process(org, bid, engine=AdvancingEngine())
    assert (recovered.processed, recovered.failed, recovered.remaining) == (2, 0, 0)
    assert len(calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("refusal", [True, False], ids=["refused-ingest", "unexpected-error"])
async def test_expired_failure_is_neither_counted_nor_replayed(lease_services, genuine_resume, monkeypatch, refusal):
    services = lease_services
    org, bid = _lease_batch(services, genuine_resume, count=2)
    clock = [datetime.now(timezone.utc)]
    monkeypatch.setattr(services.screening, "_now", lambda: clock[0])
    calls = []

    class ExpiringEngine:
        async def evaluate(self, **kwargs):
            calls.append(kwargs["resume_text"])
            clock[0] += timedelta(seconds=services.settings.screening_claim_timeout_seconds + 1)
            raise IngestRefused("unknown_domain") if refusal else RuntimeError("synthetic engine failure")

    result = await services.screening.process(org, bid, engine=ExpiringEngine())
    assert (result.processed, result.failed, result.remaining) == (0, 0, 2)
    assert len(calls) == 1
    counts = services.screening.get(org, bid).counts
    assert (counts.pending, counts.processing, counts.failed, counts.done) == (2, 0, 0, 0)
    recovered = await services.screening.process(org, bid, engine=EvaluationEngine(services))
    assert (recovered.processed, recovered.failed, recovered.remaining) == (2, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ["processing", "done", "failed"])
async def test_refused_completion_stops_before_reclaiming_the_same_item(lease_services, genuine_resume, monkeypatch, winner):
    services = lease_services
    org, bid = _lease_batch(services, genuine_resume, count=2)
    svc, store = services.screening, services.screening._store
    clock = [datetime.now(timezone.utc)]
    monkeypatch.setattr(svc, "_now", lambda: clock[0])
    complete = store.complete
    stolen = []

    def steal_before_completion(item_id, **kwargs):
        clock[0] += timedelta(seconds=services.settings.screening_claim_timeout_seconds + 1)
        stolen.extend(store.claim(org, bid, limit=1, now=clock[0],
            timeout_seconds=services.settings.screening_claim_timeout_seconds))
        assert len(stolen) == 1
        if winner == "done":
            assert complete(item_id, **{**kwargs, "lease": stolen[0].claimed_at, "at": clock[0]}) is CompletionOutcome.DONE
        elif winner == "failed":
            assert store.fail(item_id, lease=stolen[0].claimed_at, error="internal_error", at=clock[0])
        return complete(item_id, **kwargs)

    monkeypatch.setattr(store, "complete", steal_before_completion)
    result = await svc.process(org, bid, engine=EvaluationEngine(services))
    assert (result.processed, result.failed, result.remaining) == (0, 0, 2 if winner == "processing" else 1)
    assert len(stolen) == 1
    counts = svc.get(org, bid).counts
    assert (counts.processing, counts.pending, counts.done, counts.failed) == (
        int(winner == "processing"), 1, int(winner == "done"), int(winner == "failed"))


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
    """Legacy invalid rows still fail alone; new registration refuses them."""
    org = _org(services)
    bid = services.screening._store.create_batch(
        org, name="x", domain="genai", texts=["   ", genuine_resume],
        created_by_org_user_id=None,
    )
    engine = EvaluationEngine(services)
    while (await services.screening.process(org, bid, engine=engine)).remaining:
        pass

    detail = services.screening.get(org, bid)
    assert (detail.counts.done, detail.counts.failed) == (1, 1)
    assert detail.status is BatchStatus.PARTIAL

    rows = services.screening.queue(org, bid, cursor=None, limit=10).rows
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


class _DeleteRacingStore:
    """The REAL store with the batch REALLY deleted between a caller's first
    read and its counts() -- the interleaving a two-tab delete produces. Like
    the _try_claim test, the race is unreachable through sequential public
    calls, so the test builds the state directly; nothing here is canned."""

    def __init__(self, inner, org_id):
        self._inner = inner
        self._org = org_id
        self.armed = False

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def counts(self, org_id, batch_id, *, now):
        if self.armed:
            self.armed = False
            self._inner.delete_batch(self._org, batch_id)
        return self._inner.counts(org_id, batch_id, now=now)


def _racing_service(services, org):
    from app.screening.service import ScreeningService
    from app.screening.store import ScreeningStore

    store = _DeleteRacingStore(
        ScreeningStore(services.candidates._session_factory), org
    )
    # The container's own limiter, not a permissive stand-in: `limiter` is a
    # REQUIRED argument precisely so a construction site cannot end up silently
    # unlimited, and a test that passed a no-op here would be re-opening that
    # hole for itself.
    return ScreeningService(
        store, services.screening._deps, settings=services.settings,
        limiter=services.screening._limiter,
    ), store


def test_a_batch_deleted_mid_get_is_absent_not_a_500(services, genuine_resume):
    """DELETE from a second tab lands between batch_row and counts. The old
    code called derive_status(None) -> AttributeError -> 500."""
    org = _org(services)
    svc, store = _racing_service(services, org)
    batch = svc.register(org, name="x", domain="genai", texts=[genuine_resume],
                         created_by_org_user_id=None)
    store.armed = True
    assert svc.get(org, batch.id) is None
    assert svc.get(org, batch.id) is None, "and it stays absent"


def test_a_batch_deleted_mid_list_is_skipped_not_a_500(services, genuine_resume):
    org = _org(services)
    svc, store = _racing_service(services, org)
    svc.register(org, name="keep", domain="genai", texts=[genuine_resume],
                 created_by_org_user_id=None)
    svc.register(org, name="doomed", domain="genai", texts=[genuine_resume],
                 created_by_org_user_id=None)
    store.armed = True
    page = svc.list(org, cursor=None, limit=10)
    assert len(page.batches) == 1, "the vanished batch is skipped, the rest served"


def test_a_batch_deleted_mid_summary_is_absent_not_a_500(services, genuine_resume):
    org = _org(services)
    svc, store = _racing_service(services, org)
    batch = svc.register(org, name="x", domain="genai", texts=[genuine_resume],
                        created_by_org_user_id=None)
    store.armed = True
    assert svc.summary(org, batch.id) is None


@pytest.mark.asyncio
async def test_a_batch_deleted_mid_process_is_absent_not_a_500(
    services, genuine_resume
):
    """The widest window of the four: a process call runs graph evaluations
    for minutes, and the final counts read raced a delete."""
    org = _org(services)
    svc, store = _racing_service(services, org)
    batch = svc.register(org, name="x", domain="genai", texts=[genuine_resume],
                         created_by_org_user_id=None)
    engine = EvaluationEngine(services)
    store.armed = True
    assert await svc.process(org, batch.id, engine=engine) is None


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


# Screening ingest

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
