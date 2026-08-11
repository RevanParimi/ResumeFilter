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

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
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
    """Sweep every target once.

    ``sweep_max_rows_per_class`` bounds each TARGET, not each data class, and
    the only class with two targets is ``login_state`` -- so one invocation can
    move up to 2x the cap for it. Stated rather than hidden: the cap exists to
    bound how long a single statement holds locks, which is a per-table
    property, and a class-wide budget would make the second table's progress
    depend on the first table's size. The report still marks the CLASS
    truncated, which is what an operator acts on.
    """
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


def main(argv: Optional[list[str]] = None) -> int:
    """``python -m app.retention.sweep [--apply]``.

    A CLI *and* a route, because there is no scheduler: this is the entry point
    a Railway cron or an operator shell uses. Both go through ``run_sweep`` and
    both refuse a real run on a disabled config, so the rule cannot be enforced
    at one door and forgotten at the other -- and a cron is precisely the caller
    nobody is watching when it goes wrong.

    Deleting takes an explicit ``--apply``, mirroring the route's
    ``dry_run: true`` default: the safe thing is what you get for free.

    OUTPUT CONTRACT: the report is the LAST line of stdout, and it is JSON.
    This process shares stdout with the structured log (``configure_logging``
    points structlog's PrintLoggerFactory there, because the server's access
    log is read that way), so ``run_sweep``'s own ``retention_sweep`` line
    lands on stdout first. That makes the stream a sequence of JSON documents
    rather than one -- fine for ``jq``, and a ``json.loads`` of the whole
    buffer fails. Nothing logs after the print, so "last line" holds; a test
    pins it, because an output contract nobody asserts is a comment.
    """
    from app.core.config import get_settings
    from app.core.db import make_engine, make_session_factory

    parser = argparse.ArgumentParser(prog="app.retention.sweep")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete. Without it this is a dry run, deliberately.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.apply and not settings.retention_sweep_enabled:
        print("retention_sweep_disabled", file=sys.stderr)
        return 2

    factory = make_session_factory(make_engine(settings.candidates_db_url))
    report = run_sweep(
        factory,
        settings,
        now=datetime.now(timezone.utc),
        dry_run=not args.apply,
    )
    print(json.dumps(report.model_dump(mode="json")))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
