"""``python -m app.signal_quality.report`` (S9.1).

A CLI as well as a route, for the same reason the retention sweep has both:
there is no scheduler anywhere in ``app/``, so this is an INVOCABLE thing and
never a daemon.

OUTPUT CONTRACT: the report is the LAST line of stdout, and it is JSON. This
process shares stdout with the structured log, so the stream is a sequence of
JSON documents rather than one. A test pins it, because an output contract
nobody asserts is a comment.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


def main(argv: Optional[list[str]] = None) -> int:
    from app.core.config import get_settings
    from app.core.migrate import revision_state
    from app.ledger.store import build_ledger_store
    from app.reports.store import build_report_store
    from app.signal_quality.labels import LedgerLabelSource, OutcomesLabelSource
    from app.signal_quality.service import measure

    parser = argparse.ArgumentParser(prog="app.signal_quality.report")
    parser.add_argument(
        "--source", choices=("outcomes", "ledger"), default="outcomes",
        help="which ground truth to measure against (default: outcomes)",
    )
    parser.add_argument(
        "--include-operator-labels", action="store_true",
        help="include our OWN operators' judgments. Off by default: training on "
             "them believing a customer produced them is circular.",
    )
    args = parser.parse_args(argv)
    settings = get_settings()

    # S8.6, FOUND BY RUNNING IT: the retention CLI met an unmigrated database
    # with a forty-line SQLAlchemy traceback and exit 1. This process reads
    # only, but it is reachable the same way -- an operator shell, or a cron
    # container that starts before the web service has migrated anything.
    #
    # The check runs BEFORE any store is built, so the refusal cannot itself
    # raise on the way to refusing, and it can honestly say nothing was read.
    current, head = revision_state(settings)
    if current != head:
        print(
            "signal_quality_refused: the database is not migrated (schema is at "
            f"{current or 'no revision at all'}, head is {head}). Nothing was "
            "read. The web service applies migrations on boot; run it, or "
            "`alembic upgrade head`, first.",
            file=sys.stderr,
        )
        return 3

    # The BUILDERS, not a hand-wired engine: build_ledger_store also carries
    # ledger_consent_default_ttl_days and ledger_api_key_bytes off settings,
    # and a second construction path here is how those would silently differ
    # from the ones the web service runs with.
    reports = build_report_store(settings)
    if args.source == "ledger":
        source = LedgerLabelSource(reports, build_ledger_store(settings))
    else:
        source = OutcomesLabelSource(
            reports, include_operator_labels=args.include_operator_labels
        )

    report = measure(
        source,
        min_samples=settings.min_signal_quality_samples,
        bins=settings.signal_quality_curve_bins,
    )
    print(json.dumps(report.model_dump(mode="json")))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
