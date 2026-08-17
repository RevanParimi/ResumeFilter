"""One-shot: import the pre-S8.1 reports.db into the main database (S8.1).

    python scripts/migrate_reports_into_main_db.py [--old-db ./data/reports.db]

Run once per deployment that has a reports.db. An absent file is a clean no-op,
so it is safe on a fresh install. Idempotent: a report already present is
skipped.

Reports whose candidate no longer exists are REPORTED AND DROPPED. They are the
old convention's actual failures -- an erased person's depth evaluation, kept
alive because nothing enforced the two-step delete -- and the new foreign key
would reject them anyway.

Deliberately NOT an Alembic step: a migration must not read a filesystem path
out of Settings, must not need a second database engine to be reachable, and
must stay runnable on a deployment that never had a reports.db.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

from sqlalchemy import select

# S8.7: the package moved to src/app/, so the repository root is no longer an
# importable location -- this now points one level deeper. Under pytest the
# import resolves through pyproject's `pythonpath` regardless, which is exactly
# why a stale value here would have gone unnoticed.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
)

from app.candidates.models import CandidateRow  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.reports.models import OutcomeRow, ReportRow  # noqa: E402
from app.reports.schema import OutcomeSource  # noqa: E402


def _dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


def migrate(old_db_path: str, session_factory) -> dict:
    """Copy reports + outcomes across. Returns a count of what happened."""
    if not os.path.exists(old_db_path):
        return {"imported": 0, "orphaned": 0, "outcomes": 0}

    conn = sqlite3.connect(f"file:{old_db_path}?mode=ro", uri=True)
    try:
        reports = conn.execute(
            "SELECT id, domain, created_at, depth_band, candidate_id, body"
            " FROM reports"
        ).fetchall()
        outcomes = conn.execute(
            "SELECT report_id, claim_id, outcome, notes, recorded_at FROM outcomes"
        ).fetchall()
    finally:
        conn.close()

    imported = orphaned = kept_outcomes = 0
    with session_factory() as s:
        known = {c for (c,) in s.execute(select(CandidateRow.id))}
        existing = {r for (r,) in s.execute(select(ReportRow.id))}
        landed: set[str] = set()

        for rid, domain, created_at, depth_band, candidate_id, body in reports:
            if rid in existing:
                continue
            if candidate_id is not None and candidate_id not in known:
                orphaned += 1
                continue
            s.add(ReportRow(
                id=rid, domain=domain or "genai",
                depth_band=depth_band or "insufficient_signal",
                candidate_id=candidate_id, body=json.loads(body),
                created_at=_dt(created_at),
            ))
            landed.add(rid)
            imported += 1

        # Flushed before the outcomes so their foreign key has something to
        # point at: the two rows carry no ORM relationship to order them.
        s.flush()

        for report_id, claim_id, outcome, notes, recorded_at in outcomes:
            if report_id not in landed:
                continue
            s.add(OutcomeRow(
                report_id=report_id, claim_id=claim_id, outcome=outcome,
                notes=notes or "", recorded_at=_dt(recorded_at),
                # S8.5: `recorded_by` is NOT NULL with no server default, so
                # every writer must state provenance -- and this importer is a
                # THIRD writer to `outcomes`, easy to miss beside the two
                # routes. `operator` is a fact about these rows, not a guess:
                # they come from the pre-S8.1 reports database, which predates
                # the org plane entirely.
                recorded_by=OutcomeSource.OPERATOR.value,
            ))
            kept_outcomes += 1

        s.commit()

    return {"imported": imported, "orphaned": orphaned, "outcomes": kept_outcomes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-db", default="./data/reports.db")
    args = parser.parse_args()

    settings = get_settings()
    factory = make_session_factory(make_engine(settings.candidates_db_url))
    result = migrate(args.old_db, factory)

    print(f"imported: {result['imported']} reports, {result['outcomes']} outcomes")
    if result["orphaned"]:
        print(
            f"DROPPED {result['orphaned']} orphaned report(s): their candidate "
            "was already erased. These are what the pre-S8.1 convention actually "
            "leaked."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
