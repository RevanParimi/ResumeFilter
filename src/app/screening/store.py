"""Screening batches: persistence, org-scoped by construction (S8.4 Phase B).

EVERY method takes ``org_id`` first and turns it into a WHERE clause. There is
no unscoped read on this object -- the same rule as ``OrgScopedAccess``, one
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
from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.candidates.models import CandidateRow, ResumeRow
from app.candidates.store import IngestOutcome, ResumeErasedError
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import get_logger
from app.ledger.consent import as_utc
from app.reports.models import ReportRow
from app.schemas.report import Report
from app.screening.models import BatchItemRow, ScreeningBatchRow, ScreeningInputRow, ScreeningErasureStateRow
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
    expected_resume_id: Optional[str] = None
    input_generation: Optional[int] = None


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

    @staticmethod
    def _generation(session, *, lock=False) -> int:
        if lock and session.bind.dialect.name == "sqlite":
            # A SELECT does not start a SQLite write transaction. Acquire it
            # before subject writes, never upgrade a stale read snapshot.
            session.execute(update(ScreeningErasureStateRow).where(
                ScreeningErasureStateRow.id == 1).values(
                    generation=ScreeningErasureStateRow.generation))
        query = select(ScreeningErasureStateRow.generation).where(ScreeningErasureStateRow.id == 1)
        if lock:
            query = query.with_for_update(read=True)
        return session.execute(query).scalar_one()

    @staticmethod
    def _blocked_input():
        current = select(ScreeningErasureStateRow.generation).where(
            ScreeningErasureStateRow.id == 1).scalar_subquery()
        return and_(BatchItemRow.status != ItemStatus.DONE.value, or_(
            func.coalesce(BatchItemRow.error, "") == "fresh_upload_required",
            and_(BatchItemRow.raw_text != "", or_(BatchItemRow.input_generation.is_(None),
                                                   BatchItemRow.input_generation != current)),
        ))

    def check_input_generation(self, session, item: ClaimedItem) -> bool:
        # Resume-bound retry already has a precise CASCADE lifetime.
        if item.expected_resume_id is not None:
            return True
        generation = self._generation(session, lock=True)
        return item.input_generation is not None and item.input_generation == generation

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
            generation = self._generation(s, lock=True)
            batch = ScreeningBatchRow(
                org_id=org_id, name=name, domain=domain,
                created_by_org_user_id=created_by_org_user_id,
            )
            s.add(batch)
            s.flush()
            for text in texts:
                s.add(self._new_item(batch.id, text, generation))
            s.commit()
            return batch.id

    def add_items(self, org_id: str, batch_id: str, *, texts: list[str]) -> bool:
        """Append items to an existing batch (used by tests and by a resumed
        upload). Scoped like every other method."""
        with self._session_factory() as s:
            generation = self._generation(s, lock=True)
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return False
            for text in texts:
                s.add(self._new_item(batch_id, text, generation))
            s.commit()
            return True

    @staticmethod
    def _new_item(batch_id: str, text: str, generation: int) -> BatchItemRow:
        return BatchItemRow(
            batch_id=batch_id,
            status=ItemStatus.PENDING.value,
            raw_text=text,
            text_sha256=sha256(text.encode("utf-8")).hexdigest(),
            created_at=datetime.now(timezone.utc),
            input_generation=generation,
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

            # Persist the same refusal queue/count reads project immediately.
            # Clear the lease, not the retained text or its original TTL.
            s.execute(update(BatchItemRow).where(
                BatchItemRow.batch_id == batch_id, self._blocked_input(),
            ).values(status=ItemStatus.FAILED.value, error="fresh_upload_required", claimed_at=None))

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
                select(BatchItemRow, ScreeningInputRow.resume_id, ResumeRow.raw_text)
                .outerjoin(ScreeningInputRow, ScreeningInputRow.id == BatchItemRow.id)
                .outerjoin(ResumeRow, and_(ResumeRow.id == ScreeningInputRow.resume_id,
                                          ResumeRow.org_id == org_id))
                .where(BatchItemRow.id.in_(claimed))
            ).all()
            order = {item_id: i for i, item_id in enumerate(claimed)}
            rows = sorted(rows, key=lambda r: order[r[0].id])
            return [
                ClaimedItem(
                    id=r.id, raw_text=retry_text if rid is not None and retry_text is not None else r.raw_text,
                    domain=domain, claimed_at=now, expected_resume_id=rid,
                    input_generation=r.input_generation,
                )
                for r, rid, retry_text in rows
            ]

    def retain_ingested_input(self, session, org_id: str, item: ClaimedItem,
                              outcome: IngestOutcome) -> bool:
        """Bind retry input inside ingest's transaction, before it commits.

        Resume text already exists. Keep only a private CASCADE reference and
        clear the unlinked copy. Public subject links still wait for completion.
        The caller must abort ingest when this returns False.
        """
        if item.expected_resume_id is None and item.input_generation != self._generation(session):
            return False
        resume = session.scalar(select(ResumeRow).where(
            ResumeRow.id == outcome.resume_id, ResumeRow.candidate_id == outcome.candidate_id,
            ResumeRow.org_id == org_id,
        ).with_for_update())
        if resume is None:
            raise ResumeErasedError()
        res = session.execute(update(BatchItemRow).where(
            self._holds_lease(item.id, item.claimed_at),
            ~self._blocked_input(),
            # A sweep can clear an initial claimant's copy before ingest.
            BatchItemRow.raw_text != "" if item.expected_resume_id is None else True,
            BatchItemRow.batch_id.in_(select(ScreeningBatchRow.id).where(
                ScreeningBatchRow.org_id == org_id)),
        ).values(raw_text="", text_sha256="").returning(BatchItemRow.created_at))
        created_at = res.scalar_one_or_none()
        if created_at is None:
            return False
        retained = session.scalar(select(ScreeningInputRow).where(
            ScreeningInputRow.id == item.id).with_for_update())
        if item.expected_resume_id is not None:
            # A sweep may have removed the reference since claim loaded text.
            # Do not restore a swept capability from a worker's stale copy.
            return (retained is not None and retained.resume_id == item.expected_resume_id
                    and outcome.resume_id == item.expected_resume_id)
        if retained is not None:
            return False
        session.add(ScreeningInputRow(id=item.id, resume_id=outcome.resume_id,
                                     created_at=created_at))
        session.flush()
        return True

    def bind_input_report(self, session, org_id: str, item: ClaimedItem,
                          report: Report) -> bool:
        """Tie retry to report erasure in the report's own save transaction.

        Lock the lease before the private input, matching completion. Never
        recreate a reference removed by erasure or retention while evaluating.
        The caller must roll back the report when this returns False.
        """
        held = session.execute(update(BatchItemRow).where(
            self._holds_lease(item.id, item.claimed_at),
            BatchItemRow.batch_id.in_(select(ScreeningBatchRow.id).where(
                ScreeningBatchRow.org_id == org_id)),
        ).values(raw_text=""))
        if held.rowcount != 1:
            return False
        bound = session.execute(update(ScreeningInputRow).where(
            ScreeningInputRow.id == item.id,
            ScreeningInputRow.resume_id.in_(select(ResumeRow.id).join(
                ReportRow, ReportRow.candidate_id == ResumeRow.candidate_id).where(
                    ResumeRow.org_id == org_id, ReportRow.org_id == org_id,
                    ReportRow.id == report.id, ResumeRow.candidate_id == report.candidate_id)),
        ).values(report_id=report.id))
        return bound.rowcount == 1

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
    def _stale_processing(now: datetime, timeout_seconds: int):
        """A `processing` claim old enough to be presumed dead.

        A NULL ``claimed_at`` on a processing row is a bug state; treating it as
        stale is the self-healing reading (spec §4.4). The SQL spelling of the
        rule ``_item_record`` applies in Python -- both are pinned by the
        stale-claim tests, which assert the reinterpretation through `counts`
        AND through an item read.
        """
        stale_before = now - timedelta(seconds=timeout_seconds)
        return and_(
            BatchItemRow.status == ItemStatus.PROCESSING.value,
            or_(
                BatchItemRow.claimed_at.is_(None),
                BatchItemRow.claimed_at < stale_before,
            ),
        )

    @classmethod
    def _claimable(cls, now: datetime, timeout_seconds: int):
        """pending, or a `processing` claim old enough to be presumed dead."""
        return or_(
            BatchItemRow.status == ItemStatus.PENDING.value,
            cls._stale_processing(now, timeout_seconds),
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

        False when the lease was lost, the batch deleted, or a linked parent
        erased. Foreign keys order this write with deletion. Erasure-first
        scrubs retained input under the same lease and refuses stale results;
        completion-first keeps the existing SET NULL/count retention behavior.
        """
        with self._session_factory() as s:
            try:
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
                if res.rowcount == 1:
                    s.execute(delete(ScreeningInputRow).where(ScreeningInputRow.id == item_id))
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                foreign_key = (
                    getattr(exc.orig, "sqlstate", None) == "23503"
                    or getattr(exc.orig, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_FOREIGNKEY"
                )
                if not foreign_key:
                    raise
                reason = next((
                    code for model, identity, code in (
                        (CandidateRow, candidate_id, "candidate_erased"),
                        (ResumeRow, resume_id, "resume_erased"),
                        (ReportRow, report_id, "report_erased"),
                    ) if identity is not None and s.get(model, identity) is None
                ), None)
                if reason is None:
                    raise
                # Rollback released the item lock. A new claimant or batch
                # deletion can win before cleanup, so reassert the lease.
                cleanup = s.execute(
                    update(BatchItemRow)
                    .where(self._holds_lease(item_id, lease))
                    .values(status=ItemStatus.FAILED.value, raw_text="", text_sha256="",
                            candidate_id=None, resume_id=None, report_id=None,
                            signals=None, risk_score=None, error=reason, processed_at=at)
                )
                if cleanup.rowcount == 1:
                    s.execute(delete(ScreeningInputRow).where(ScreeningInputRow.id == item_id))
                s.commit()
                return False
            if res.rowcount != 1:
                log.warning("lost_claim_lease", item_id=item_id, outcome="complete")
                return False
            return True

    def fail(self, item_id: str, *, lease: datetime, error: str, at: datetime) -> bool:
        """Keep ordinary failure input for retry; scrub explicit erasure refusals.

        The failed status and scrub share one lease-checked write/commit, so a
        recorded erasure refusal cannot leave input available to batch retry.
        """
        values = dict(status=ItemStatus.FAILED.value, error=error[:64], processed_at=at)
        if error in {"candidate_erased", "resume_erased", "report_erased"}:
            values.update(raw_text="", text_sha256="", candidate_id=None,
                          resume_id=None, report_id=None, signals=None, risk_score=None)
        with self._session_factory() as s:
            res = s.execute(
                update(BatchItemRow)
                .where(self._holds_lease(item_id, lease))
                .values(**values)
            )
            if res.rowcount == 1 and error in {"candidate_erased", "resume_erased", "report_erased"}:
                s.execute(delete(ScreeningInputRow).where(ScreeningInputRow.id == item_id))
            s.commit()
            if res.rowcount != 1:
                log.warning("lost_claim_lease", item_id=item_id, outcome="fail")
                return False
            return True

    def requeue_failed(
        self, org_id: str, batch_id: str
    ) -> Optional[tuple[int, int]]:
        """Flip this batch's FAILED items back to pending. (requeued, skipped).

        ``None`` when the batch is not this organisation's OR does not exist,
        so the route answers one 404 for both -- another org's batch must be
        indistinguishable from one that was never created.

        An item without raw input or a surviving private resume reference is
        SKIPPED. The status change is ALL this does; the existing
        ``process`` call remains the only door that evaluates anything.
        """
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return None

            generation = self._generation(s, lock=True)
            failed = s.execute(
                select(BatchItemRow).where(
                    BatchItemRow.batch_id == batch_id,
                    or_(BatchItemRow.status == ItemStatus.FAILED.value, self._blocked_input()),
                )
            ).scalars().all()

            requeued = skipped = 0
            for row in failed:
                if row.error == "fresh_upload_required" or (
                    row.raw_text and row.input_generation != generation
                ):
                    skipped += 1
                    continue
                retained = s.scalar(select(ResumeRow.id).join(ScreeningInputRow,
                    ScreeningInputRow.resume_id == ResumeRow.id).where(
                        ScreeningInputRow.id == row.id, ResumeRow.org_id == org_id,
                        ResumeRow.raw_text != ""))
                if not row.raw_text and retained is None:
                    skipped += 1
                    continue
                row.status = ItemStatus.PENDING.value
                row.error = None
                row.claimed_at = None
                row.processed_at = None
                requeued += 1
            s.commit()
            return requeued, skipped

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

        A GROUP BY, not a row load: this runs on every poll of `get`, on every
        batch of a `list` page and at the end of every `process` call, and the
        item rows carry `raw_text` -- counting 500 pending resumes must not
        drag 500 resumes' text out of the database each time.
        """
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return None
            effective = case(
                (self._blocked_input(), ItemStatus.FAILED.value),
                (
                    self._stale_processing(now, self._claim_timeout),
                    ItemStatus.PENDING.value,
                ),
                else_=BatchItemRow.status,
            ).label("effective")
            rows = s.execute(
                select(effective, func.count())
                .where(BatchItemRow.batch_id == batch_id)
                .group_by(effective)
            ).all()
            counts = BatchCounts()
            for status_value, n in rows:
                setattr(counts, status_value, n)
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
            generation = self._generation(s)
            return [self._item_record(r, now=now, generation=generation) for r in rows]

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
            generation = self._generation(s)
            return [self._item_record(r, now=now, generation=generation) for r in rows], next_cursor

    # ── mapping ─────────────────────────────────────────────────────────────

    @staticmethod
    def _batch_record(row: ScreeningBatchRow) -> BatchRecord:
        return BatchRecord(
            id=row.id, org_id=row.org_id, name=row.name or "", domain=row.domain,
            created_by_org_user_id=row.created_by_org_user_id,
            created_at=as_utc(row.created_at),
        )

    def _item_record(self, row: BatchItemRow, *, now: datetime, generation: int) -> ItemRecord:
        status = ItemStatus(row.status)
        blocked = status is not ItemStatus.DONE and (row.error == "fresh_upload_required" or (
            bool(row.raw_text) and row.input_generation != generation))
        if blocked:
            status = ItemStatus.FAILED
        elif (
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
            error="fresh_upload_required" if blocked else row.error,
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
