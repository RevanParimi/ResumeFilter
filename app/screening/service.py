"""Screening batches: the service (S8.4 Phase B).

Composition over the store and the ingest core. Owns no tables directly -- the
store does -- and holds no state, in the ``app/dashboard/`` style.

EVERY method takes ``org_id`` first, and the store it calls does too, so
tenancy is a property of the type signatures rather than of anybody's memory.
The store is deliberately NOT an attribute of ``Services``: if no handler can
reach an unscoped batch read, no handler can forget to scope one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.screening.ingest import IngestDeps, IngestRefused, ingest_resume
from app.screening.pagination import clamp_limit
from app.screening.schema import (
    BatchDetail, BatchPage, BatchSummary, BatchView, ItemSignals, ProcessResult,
    QueuePage, QueueRow, SignalCount, compose_reason, derive_status,
    signals_from_report,
)
from app.screening.store import (
    BatchRecord, ItemRecord, ScreeningStore, build_screening_store,
)

if TYPE_CHECKING:
    from app.graph.build import EvaluationEngine

log = get_logger("screening.service")


class ScreeningService:
    def __init__(
        self, store: ScreeningStore, deps: IngestDeps, *, settings: Settings
    ) -> None:
        self._store = store
        self._deps = deps
        self._settings = settings

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    # ── registration ────────────────────────────────────────────────────────

    def register(
        self,
        org_id: str,
        *,
        name: str,
        domain: str,
        texts: list[str],
        created_by_org_user_id: Optional[str],
    ) -> BatchDetail:
        """Register items. NO evaluation -- see spec §0.3: there is no worker
        anywhere in app/, and 500 nine-node graph runs cannot happen inside one
        request."""
        if not texts:
            raise ValueError("a batch needs at least one item")
        cap = self._settings.screening_max_batch_items
        if len(texts) > cap:
            raise ValueError(f"a batch holds at most {cap} items")

        batch_id = self._store.create_batch(
            org_id, name=name, domain=domain,
            created_by_org_user_id=created_by_org_user_id, texts=texts,
        )
        detail = self.get(org_id, batch_id)
        assert detail is not None  # just created, by this org
        return detail

    # ── reads ───────────────────────────────────────────────────────────────

    def get(self, org_id: str, batch_id: str) -> Optional[BatchDetail]:
        now = self._now()
        record = self._store.batch_row(org_id, batch_id)
        if record is None:
            return None
        counts = self._store.counts(org_id, batch_id, now=now)
        if counts is None:
            # Deleted between the two reads (a second tab). Absent, not a 500.
            return None
        return BatchDetail(
            **self._batch_fields(record),
            counts=counts,
            status=derive_status(counts),
        )

    def list(
        self, org_id: str, *, cursor: Optional[str], limit: Optional[int]
    ) -> BatchPage:
        now = self._now()
        records, next_cursor = self._store.list_batches(
            org_id, cursor=cursor, limit=clamp_limit(limit, self._settings)
        )
        views = []
        for record in records:
            counts = self._store.counts(org_id, record.id, now=now)
            if counts is None:
                # Deleted since the page SELECT; serve the rest of the page.
                continue
            views.append(BatchView(
                **self._batch_fields(record),
                counts=counts, status=derive_status(counts),
            ))
        return BatchPage(batches=views, next_cursor=next_cursor)

    def queue(
        self, org_id: str, batch_id: str, *, cursor: Optional[str], limit: Optional[int]
    ) -> Optional[QueuePage]:
        page = self._store.queue_page(
            org_id, batch_id, cursor=cursor,
            limit=clamp_limit(limit, self._settings), now=self._now(),
        )
        if page is None:
            return None
        rows, next_cursor = page
        return QueuePage(rows=[self._row(i) for i in rows], next_cursor=next_cursor)

    def summary(self, org_id: str, batch_id: str) -> Optional[BatchSummary]:
        now = self._now()
        record = self._store.batch_row(org_id, batch_id)
        if record is None:
            return None
        items = self._store.all_items(org_id, batch_id, now=now) or []

        counts = self._store.counts(org_id, batch_id, now=now)
        if counts is None:
            return None
        by_band: dict[str, int] = {}
        signals: dict[str, int] = {}
        for item in items:
            if item.signals is None:
                continue
            band = item.signals.risk_band.value
            by_band[band] = by_band.get(band, 0) + 1
            if item.signals.loudest_signal:
                key = item.signals.loudest_signal
                signals[key] = signals.get(key, 0) + 1

        return BatchSummary(
            batch_id=record.id, name=record.name, domain=record.domain,
            status=derive_status(counts), counts=counts,
            n_screened=sum(by_band.values()),
            by_risk_band=by_band,
            top_signals=[
                SignalCount(signal=k, count=v)
                for k, v in sorted(signals.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
        )

    def delete(self, org_id: str, batch_id: str) -> bool:
        return self._store.delete_batch(org_id, batch_id)

    # ── processing ──────────────────────────────────────────────────────────

    async def process(
        self, org_id: str, batch_id: str, *, engine: "EvaluationEngine"
    ) -> Optional[ProcessResult]:
        """Claim and run up to ``screening_max_items_per_call`` items.

        Each item is handled independently: one corrupt file must not abandon
        the other 499. An unexpected exception fails ITS item with a generic
        code rather than propagating, because the alternative is a row stuck in
        `processing` until the claim times out for a reason nobody recorded.
        """
        if self._store.batch_row(org_id, batch_id) is None:
            return None

        now = self._now()
        claimed = self._store.claim(
            org_id, batch_id,
            limit=self._settings.screening_max_items_per_call,
            now=now,
            timeout_seconds=self._settings.screening_claim_timeout_seconds,
        )

        processed = failed = 0
        for item in claimed:
            try:
                result = await ingest_resume(
                    self._deps, engine,
                    text=item.raw_text, domain=item.domain,
                    evaluate=True, org_id=org_id,
                )
            except IngestRefused as exc:
                self._store.fail(item.id, lease=item.claimed_at,
                                 error=exc.reason, at=self._now())
                failed += 1
                continue
            except Exception as exc:  # noqa: BLE001 - deliberately broad, see below
                # The exception's TEXT never goes on the row: batch_items.error
                # is a closed vocabulary, and an exception message can quote the
                # input that caused it.
                log.error("batch_item_failed", item_id=item.id, error=repr(exc))
                self._store.fail(item.id, lease=item.claimed_at,
                                 error="internal_error", at=self._now())
                failed += 1
                continue

            report = result.report
            self._store.complete(
                item.id,
                lease=item.claimed_at,
                candidate_id=result.candidate_id,
                resume_id=result.resume_id,
                report_id=report.id if report is not None else None,
                risk_score=(
                    report.fabrication_risk.score
                    if report is not None and report.fabrication_risk is not None
                    else None
                ),
                signals=signals_from_report(
                    report,
                    matched_existing=result.matched_existing,
                    matched_on=result.matched_on,
                    duplicate_resume=result.duplicate_resume,
                ) if report is not None else _no_report_signals(result),
                at=self._now(),
            )
            processed += 1

        counts = self._store.counts(org_id, batch_id, now=self._now())
        if counts is None:
            # The org deleted the batch while this call was evaluating. The
            # candidates and reports this call ingested are real and stay; the
            # batch itself is now absent, and absent answers 404 everywhere.
            log.warning("batch_deleted_mid_process", batch_id=batch_id,
                        processed=processed, failed=failed)
            return None
        return ProcessResult(
            batch_id=batch_id, processed=processed, failed=failed,
            remaining=counts.pending + counts.processing,
            status=derive_status(counts),
        )

    # ── mapping ─────────────────────────────────────────────────────────────

    @staticmethod
    def _batch_fields(record: BatchRecord) -> dict:
        return {
            "id": record.id, "name": record.name, "domain": record.domain,
            "created_at": record.created_at,
            "created_by_org_user_id": record.created_by_org_user_id,
        }

    @staticmethod
    def _row(item: ItemRecord) -> QueueRow:
        return QueueRow(
            item_id=item.item_id, status=item.status,
            created_at=item.created_at, processed_at=item.processed_at,
            candidate_id=item.candidate_id, resume_id=item.resume_id,
            report_id=item.report_id, risk_score=item.risk_score,
            signals=item.signals, error=item.error,
            reason=compose_reason(item.signals, item.status, item.error),
        )


def _no_report_signals(result) -> ItemSignals:
    """The subject was erased mid-evaluation, so there is nothing to score.

    The ingest itself succeeded, so the item is DONE with the ingest facts and
    no risk assessment -- which reads as "insufficient signal", the honest
    answer, rather than a zero.
    """
    return ItemSignals(
        matched_existing=result.matched_existing,
        matched_on=result.matched_on,
        duplicate_resume=result.duplicate_resume,
    )


def build_screening_service(
    settings: Optional[Settings] = None, *, deps: IngestDeps
) -> ScreeningService:
    settings = settings or get_settings()
    return ScreeningService(build_screening_store(settings), deps, settings=settings)
