"""Screening batches: persistence, org-scoped by construction (S8.4 Phase B).

EVERY method takes ``org_id`` first and turns it into a WHERE clause. There is
no unscoped read on this object -- the same rule as ``OrgScopedReads``, one
table further along, and for the same reason: a rule enforced by remembering to
enforce it gets forgotten at the second door.

A batch that belongs to another organisation returns ``None``/``False``/``[]``
so the route can answer 404. Never an exception, never a 403: a 403 confirms
the batch exists, which is the fact being protected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import get_logger
from app.ledger.consent import as_utc
from app.screening.models import BatchItemRow, ScreeningBatchRow
from app.screening.pagination import decode_cursor, encode_cursor, iso_datetime
from app.screening.schema import BatchCounts, ItemSignals, ItemStatus

log = get_logger("screening.store")

#: The queue's sort key for an item that has not been scored yet. Below every
#: real score (which is >= 0.0), so unscreened rows sort last under DESC.
_UNSCORED = -1.0


@dataclass(frozen=True)
class BatchRecord:
    id: str
    org_id: str
    name: str
    domain: str
    created_by_org_user_id: Optional[str]
    created_at: datetime


@dataclass(frozen=True)
class ItemRecord:
    item_id: str
    status: ItemStatus
    raw_text: str
    candidate_id: Optional[str]
    resume_id: Optional[str]
    report_id: Optional[str]
    risk_score: Optional[float]
    signals: Optional[ItemSignals]
    error: Optional[str]
    created_at: datetime
    processed_at: Optional[datetime]


@dataclass(frozen=True)
class ClaimedItem:
    id: str
    raw_text: str
    domain: str
    #: The lease. `complete`/`fail` only land while the row still carries this
    #: exact claim -- a claimant that outlived the timeout writes back nothing.
    claimed_at: datetime


def _signals_of(row: BatchItemRow) -> Optional[ItemSignals]:
    """Parse the stored blob, or degrade to None.

    S7.3's finding, applied here before it can happen: one unparseable write
    must not raise on EVERY later read of the batch it belongs to. The sort key
    lives in its own column, so a queue whose signals cannot be read still
    ranks correctly.
    """
    if row.signals is None:
        return None
    try:
        return ItemSignals.model_validate(row.signals)
    except ValidationError:
        log.warning("unreadable_item_signals", item_id=row.id)
        return None


class ScreeningStore:
    def __init__(
        self, session_factory: sessionmaker, claim_timeout_seconds: int = 900
    ) -> None:
        self._session_factory = session_factory
        #: Read-time only. Nothing here ever REWRITES a stale claim -- see
        #: `_item_record`.
        self._claim_timeout = claim_timeout_seconds

    # ── writes ──────────────────────────────────────────────────────────────

    def create_batch(
        self,
        org_id: str,
        *,
        name: str,
        domain: str,
        created_by_org_user_id: Optional[str],
        texts: list[str],
    ) -> str:
        """Register a batch and its items. NO evaluation -- a row insert."""
        with self._session_factory() as s:
            batch = ScreeningBatchRow(
                org_id=org_id, name=name, domain=domain,
                created_by_org_user_id=created_by_org_user_id,
            )
            s.add(batch)
            s.flush()
            for text in texts:
                s.add(self._new_item(batch.id, text))
            s.commit()
            return batch.id

    def add_items(self, org_id: str, batch_id: str, *, texts: list[str]) -> bool:
        """Append items to an existing batch (used by tests and by a resumed
        upload). Scoped like every other method."""
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return False
            for text in texts:
                s.add(self._new_item(batch_id, text))
            s.commit()
            return True

    @staticmethod
    def _new_item(batch_id: str, text: str) -> BatchItemRow:
        return BatchItemRow(
            batch_id=batch_id,
            status=ItemStatus.PENDING.value,
            raw_text=text,
            text_sha256=sha256(text.encode("utf-8")).hexdigest(),
            created_at=datetime.now(timezone.utc),
        )

    def claim(
        self,
        org_id: str,
        batch_id: str,
        *,
        limit: int,
        now: datetime,
        timeout_seconds: int,
    ) -> list[ClaimedItem]:
        """Claim up to ``limit`` claimable items, one conditional UPDATE each.

        The read that CHOOSES an item can be stale -- two browser tabs both hit
        ``POST .../process``. The write that CLAIMS it cannot: it re-asserts
        claimability in its own WHERE clause and counts only if it changed a
        row. Each item is a full nine-node graph run, so a double claim is a
        double bill.
        """
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return []
            domain = batch.domain

            claimable = self._claimable(now, timeout_seconds)
            ids = s.execute(
                select(BatchItemRow.id)
                .where(BatchItemRow.batch_id == batch_id, claimable)
                .order_by(BatchItemRow.created_at, BatchItemRow.id)
                .limit(limit)
            ).scalars().all()

            claimed = [
                item_id for item_id in ids
                if self._try_claim(s, item_id, claimable=claimable, now=now)
            ]
            s.commit()

            if not claimed:
                return []
            rows = s.execute(
                select(BatchItemRow).where(BatchItemRow.id.in_(claimed))
            ).scalars().all()
            order = {item_id: i for i, item_id in enumerate(claimed)}
            rows = sorted(rows, key=lambda r: order[r.id])
            return [
                ClaimedItem(
                    id=r.id, raw_text=r.raw_text, domain=domain, claimed_at=now
                )
                for r in rows
            ]

    @staticmethod
    def _try_claim(session, item_id: str, *, claimable, now: datetime) -> bool:
        """Claim ONE item, or refuse. The conditional UPDATE, on its own.

        A separate method because the race it defends against is unreachable
        through a single sequential ``claim`` call -- the second call's own
        SELECT filters the row out long before this UPDATE would -- so a mutant
        that deletes the ``claimable`` clause below survives every end-to-end
        test. ``tests/test_screening_store.py`` drives this directly to build
        the interleaved state, the same way S8.2's two-challenge test had to.
        """
        res = session.execute(
            update(BatchItemRow)
            .where(BatchItemRow.id == item_id, claimable)
            .values(status=ItemStatus.PROCESSING.value, claimed_at=now)
        )
        return res.rowcount == 1

    @staticmethod
    def _claimable(now: datetime, timeout_seconds: int):
        """pending, or a `processing` claim old enough to be presumed dead.

        A NULL ``claimed_at`` on a processing row is a bug state; treating it as
        stale is the self-healing reading (spec §4.4).
        """
        stale_before = now - timedelta(seconds=timeout_seconds)
        return or_(
            BatchItemRow.status == ItemStatus.PENDING.value,
            and_(
                BatchItemRow.status == ItemStatus.PROCESSING.value,
                or_(
                    BatchItemRow.claimed_at.is_(None),
                    BatchItemRow.claimed_at < stale_before,
                ),
            ),
        )

    def _holds_lease(self, item_id: str, lease: datetime):
        """WHERE clause: the row still carries THIS claim.

        `claim` re-asserts claimability before taking an item; this is the
        matching guard on the way back out. A claimant that outlived
        ``claim_timeout_seconds`` loses the row to the next claim, and its
        late write-back must be discarded rather than landing on top of the
        live claimant's result -- the same race, one step later.
        """
        return and_(
            BatchItemRow.id == item_id,
            BatchItemRow.status == ItemStatus.PROCESSING.value,
            BatchItemRow.claimed_at == lease,
        )

    def complete(
        self,
        item_id: str,
        *,
        lease: datetime,
        candidate_id: Optional[str],
        resume_id: Optional[str],
        report_id: Optional[str],
        risk_score: Optional[float],
        signals: ItemSignals,
        at: datetime,
    ) -> bool:
        """Success. CLEARS ``raw_text``: the text now lives in ``resumes``,
        where candidate erasure already cascades (spec §4.2).

        False when the lease was lost (or the batch deleted) -- the caller's
        work is discarded, because somebody else now owns the row's truth.
        """
        with self._session_factory() as s:
            res = s.execute(
                update(BatchItemRow)
                .where(self._holds_lease(item_id, lease))
                .values(
                    status=ItemStatus.DONE.value,
                    raw_text="",
                    candidate_id=candidate_id,
                    resume_id=resume_id,
                    report_id=report_id,
                    risk_score=risk_score,
                    signals=signals.model_dump(mode="json"),
                    error=None,
                    processed_at=at,
                )
            )
            s.commit()
            if res.rowcount != 1:
                log.warning("lost_claim_lease", item_id=item_id, outcome="complete")
                return False
            return True

    def fail(self, item_id: str, *, lease: datetime, error: str, at: datetime) -> bool:
        """Failure KEEPS ``raw_text`` -- see SCREENING.md §7 on what that does
        and does not buy today. Lease-checked exactly like `complete`."""
        with self._session_factory() as s:
            res = s.execute(
                update(BatchItemRow)
                .where(self._holds_lease(item_id, lease))
                .values(
                    status=ItemStatus.FAILED.value,
                    error=error[:64],
                    processed_at=at,
                )
            )
            s.commit()
            if res.rowcount != 1:
                log.warning("lost_claim_lease", item_id=item_id, outcome="fail")
                return False
            return True

    def delete_batch(self, org_id: str, batch_id: str) -> bool:
        """Delete the batch, its items and their text. Items CASCADE."""
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return False
            s.delete(batch)
            s.commit()
            return True

    # ── reads ───────────────────────────────────────────────────────────────

    def batch_row(self, org_id: str, batch_id: str) -> Optional[BatchRecord]:
        with self._session_factory() as s:
            row = s.get(ScreeningBatchRow, batch_id)
            if row is None or row.org_id != org_id:
                return None
            return self._batch_record(row)

    def list_batches(
        self, org_id: str, *, cursor: Optional[str], limit: int
    ) -> tuple[list[BatchRecord], Optional[str]]:
        """Newest first, keyed on ``(created_at, id)``."""
        with self._session_factory() as s:
            q = select(ScreeningBatchRow).where(ScreeningBatchRow.org_id == org_id)
            if cursor is not None:
                last_created, last_id = decode_cursor(
                    cursor, arity=2, types=(str, str)
                )
                cut = iso_datetime(last_created)
                q = q.where(
                    or_(
                        ScreeningBatchRow.created_at < cut,
                        and_(
                            ScreeningBatchRow.created_at == cut,
                            ScreeningBatchRow.id > last_id,
                        ),
                    )
                )
            rows = s.execute(
                q.order_by(ScreeningBatchRow.created_at.desc(), ScreeningBatchRow.id)
                .limit(limit + 1)
            ).scalars().all()

            more = len(rows) > limit
            rows = rows[:limit]
            next_cursor = (
                encode_cursor((as_utc(rows[-1].created_at), rows[-1].id))
                if more and rows else None
            )
            return [self._batch_record(r) for r in rows], next_cursor

    def counts(
        self, org_id: str, batch_id: str, *, now: datetime
    ) -> Optional[BatchCounts]:
        """Item counts, with a stale claim READ as pending.

        The read reinterprets; it never rewrites. A stored status corrected by
        a read would be a fact that depends on who looked at it last.
        """
        items = self.all_items(org_id, batch_id, now=now)
        if items is None:
            return None
        counts = BatchCounts()
        for item in items:
            setattr(counts, item.status.value, getattr(counts, item.status.value) + 1)
        return counts

    def all_items(
        self, org_id: str, batch_id: str, *, now: datetime
    ) -> Optional[list[ItemRecord]]:
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return None
            rows = s.execute(
                select(BatchItemRow)
                .where(BatchItemRow.batch_id == batch_id)
                .order_by(BatchItemRow.created_at, BatchItemRow.id)
            ).scalars().all()
            return [self._item_record(r, now=now) for r in rows]

    def queue_page(
        self,
        org_id: str,
        batch_id: str,
        *,
        cursor: Optional[str],
        limit: int,
        now: datetime,
    ) -> Optional[tuple[list[ItemRecord], Optional[str]]]:
        """Riskiest first; unscreened and failed rows last.

        ``COALESCE(risk_score, -1)`` rather than ``NULLS LAST``: SQLite sorts
        NULLs first under DESC and has no NULLS LAST, so the expression is the
        portable spelling of the same intent.
        """
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return None

            sort_key = func.coalesce(BatchItemRow.risk_score, _UNSCORED)
            q = select(BatchItemRow).where(BatchItemRow.batch_id == batch_id)
            if cursor is not None:
                last_score, last_id = decode_cursor(
                    cursor, arity=2, types=((int, float), str)
                )
                q = q.where(
                    or_(
                        sort_key < last_score,
                        and_(sort_key == last_score, BatchItemRow.id > last_id),
                    )
                )
            rows = s.execute(
                q.order_by(sort_key.desc(), BatchItemRow.id).limit(limit + 1)
            ).scalars().all()

            more = len(rows) > limit
            rows = rows[:limit]
            next_cursor = (
                encode_cursor(
                    (rows[-1].risk_score if rows[-1].risk_score is not None else _UNSCORED,
                     rows[-1].id)
                )
                if more and rows else None
            )
            return [self._item_record(r, now=now) for r in rows], next_cursor

    # ── mapping ─────────────────────────────────────────────────────────────

    @staticmethod
    def _batch_record(row: ScreeningBatchRow) -> BatchRecord:
        return BatchRecord(
            id=row.id, org_id=row.org_id, name=row.name or "", domain=row.domain,
            created_by_org_user_id=row.created_by_org_user_id,
            created_at=as_utc(row.created_at),
        )

    def _item_record(self, row: BatchItemRow, *, now: datetime) -> ItemRecord:
        status = ItemStatus(row.status)
        if (
            status is ItemStatus.PROCESSING
            and (row.claimed_at is None
                 or as_utc(row.claimed_at) < now - timedelta(seconds=self._claim_timeout))
        ):
            # Spec §4.4: a claim nobody is honouring reads as pending again, so
            # a batch interrupted by a redeploy heals on the next process call.
            status = ItemStatus.PENDING
        return ItemRecord(
            item_id=row.id,
            status=status,
            raw_text=row.raw_text or "",
            candidate_id=row.candidate_id,
            resume_id=row.resume_id,
            report_id=row.report_id,
            risk_score=row.risk_score,
            signals=_signals_of(row),
            error=row.error,
            created_at=as_utc(row.created_at),
            processed_at=as_utc(row.processed_at) if row.processed_at else None,
        )


def build_screening_store(settings: Optional[Settings] = None) -> ScreeningStore:
    """On the shared candidates DB URL -- one metadata root, one Alembic env.
    Schema is Alembic's job, NOT the builder's."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return ScreeningStore(
        make_session_factory(engine),
        claim_timeout_seconds=settings.screening_claim_timeout_seconds,
    )
