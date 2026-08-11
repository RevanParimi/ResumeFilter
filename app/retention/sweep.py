"""The retention sweep (S8.3 Phase B).

Pure orchestration over ``app/retention/plan.py``: no HTTP vocabulary, no route,
no scheduler. There is still no worker anywhere in ``app/`` (re-measured this
sprint), so this is an INVOCABLE thing -- an admin route and a ``python -m``
entry point -- and never a daemon. If nobody calls it, nothing is deleted, and
OPERATING.md says so rather than leaving an operator to infer it.

DRY-RUN PARITY IS THE DESIGN. ``affected`` is computed by the same COUNT in both
modes and only the write is skipped, so a preview cannot disagree with the
action it previews. A sweeper whose preview and whose action differ is worse
than one with no preview at all: the preview is the entire reason an operator
trusts the destructive call.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.logging import get_logger
from app.retention.plan import TARGETS, SweepMode, SweepTarget, ttl_days
from app.retention.schema import ClassSweepResult, SweepReport

log = get_logger(__name__)


def _predicate(target: SweepTarget, cutoff: datetime):
    """Rows eligible for this target.

    ``<`` and not ``<=``: a row exactly on its boundary survives one more pass.
    The difference is one row on one day, and the direction that errs is the one
    that keeps a person's data a moment longer.

    The CLEAR arm carries a NON-EMPTY test as well as the age test, and that is
    not an optimisation. ``batch_items.raw_text`` is already ``""`` on every
    successful item, so age alone would report those same rows as "cleared"
    every day forever -- a preview that lies in the direction of looking busy,
    and a number an operator would soon stop reading.
    """
    column = getattr(target.model, target.timestamp_column)
    condition = column.is_not(None) & (column < cutoff)
    if target.mode is SweepMode.CLEAR:
        cleared = getattr(target.model, target.clear_column)
        condition = condition & (cleared != "")
    return condition


def run_sweep(
    session_factory: sessionmaker,
    settings: Settings,
    *,
    now: datetime,
    dry_run: bool,
    metrics=None,
) -> SweepReport:
    cap = settings.sweep_max_rows_per_class
    totals: dict[str, int] = {}
    truncated_classes: set[str] = set()

    for target in TARGETS:
        cutoff = now - timedelta(days=ttl_days(target, settings))
        condition = _predicate(target, cutoff)
        with session_factory() as session:
            matched = session.scalar(
                select(func.count()).select_from(target.model).where(condition)
            ) or 0
            affected = min(matched, cap)
            if matched > cap:
                truncated_classes.add(target.data_class)
            if not dry_run and affected:
                # A subquery on the primary key, never an IN of ten thousand
                # bound parameters: dialect variable limits are not a thing to
                # be one deploy away from discovering.
                chosen = (
                    select(target.model.id)
                    .where(condition)
                    .order_by(getattr(target.model, target.timestamp_column))
                    .limit(cap)
                    .scalar_subquery()
                )
                if target.mode is SweepMode.DELETE:
                    statement = delete(target.model).where(
                        target.model.id.in_(chosen)
                    )
                else:
                    statement = (
                        update(target.model)
                        .where(target.model.id.in_(chosen))
                        .values(**{target.clear_column: ""})
                    )
                session.execute(
                    statement.execution_options(synchronize_session=False)
                )
                session.commit()
                if metrics is not None:
                    # AFTER the commit, and only on a real run: a preview that
                    # moved this counter would be counting intentions.
                    metrics.add(
                        "retention_deleted", affected, data_class=target.data_class
                    )
            totals[target.data_class] = totals.get(target.data_class, 0) + affected

    by_class = [
        ClassSweepResult(
            data_class=name,
            affected=count,
            truncated=name in truncated_classes,
        )
        for name, count in sorted(totals.items())
    ]
    report = SweepReport(
        by_class=by_class,
        dry_run=dry_run,
        truncated=bool(truncated_classes),
        at=now,
    )
    log.info(
        "retention_sweep",
        dry_run=dry_run,
        truncated=report.truncated,
        affected=sum(totals.values()),
    )
    return report
