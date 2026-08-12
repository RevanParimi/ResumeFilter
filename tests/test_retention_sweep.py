"""The retention sweep (S8.3 Phase B).

Every window is driven by an injected `now`, never by waiting: a test that
sleeps is a test nobody runs.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.candidates.models import CandidateRow, ExtractionRow, ResumeRow
from app.core.config import Settings
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.models import OrganizationRow
from app.metrics.registry import build_metrics
from app.retention.sweep import run_sweep
from app.screening.models import BatchItemRow, ScreeningBatchRow

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

ALL_CLASSES = {
    "resumes", "profile_sources", "verifications", "interviews",
    "interview_records", "coding_rounds", "observed_offers", "audit_log",
    "batch_item_text", "rate_limit_counters", "login_state",
}


@pytest.fixture
def session_factory():
    # make_engine, NOT create_engine: it is what installs
    # PRAGMA foreign_keys=ON, without which the cascade test below would be
    # measuring SQLite's default rather than our schema.
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _settings(**over):
    return Settings(_env_file=None, openrouter_api_key="", **over)


def _seed_resume(session_factory, *, age_days: int) -> tuple[str, str]:
    """One candidate + one resume + one extraction, aged by `age_days`."""
    when = NOW - timedelta(days=age_days)
    with session_factory() as s:
        cand = CandidateRow(full_name="Asha R")
        s.add(cand)
        s.flush()
        resume = ResumeRow(
            candidate_id=cand.id, version=1, raw_text="x", text_sha256="a" * 64,
            created_at=when,
        )
        s.add(resume)
        s.flush()
        s.add(ExtractionRow(
            resume_id=resume.id, candidate_id=cand.id, method="heuristic",
            profile={}, warnings=[], created_at=when,
        ))
        s.commit()
        return resume.id, cand.id


def test_dry_run_counts_and_deletes_nothing(session_factory):
    _seed_resume(session_factory, age_days=2000)   # older than ret_resume_days (1095)
    report = run_sweep(session_factory, _settings(), now=NOW, dry_run=True)
    resumes = next(c for c in report.by_class if c.data_class == "resumes")
    assert resumes.affected == 1
    assert report.dry_run is True
    with session_factory() as s:
        assert len(s.execute(select(ResumeRow)).scalars().all()) == 1


def test_a_real_run_deletes_exactly_what_the_dry_run_counted(session_factory):
    """DRY-RUN PARITY. A preview that disagrees with the action is worse than
    no preview: it is the entire reason an operator trusts the destructive
    call after reading the safe one."""
    _seed_resume(session_factory, age_days=2000)
    preview = run_sweep(session_factory, _settings(), now=NOW, dry_run=True)
    real = run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    assert [(c.data_class, c.affected) for c in preview.by_class] == \
           [(c.data_class, c.affected) for c in real.by_class]
    with session_factory() as s:
        assert s.execute(select(ResumeRow)).scalars().all() == []


def test_rows_inside_the_window_survive(session_factory):
    _seed_resume(session_factory, age_days=10)
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    with session_factory() as s:
        assert len(s.execute(select(ResumeRow)).scalars().all()) == 1


def test_a_row_exactly_ON_the_boundary_survives(session_factory):
    """`<` and not `<=`, pinned. The difference is one row on one day, and the
    direction that errs is the one that keeps data a moment longer."""
    _seed_resume(session_factory, age_days=1095)   # exactly ret_resume_days
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    with session_factory() as s:
        assert len(s.execute(select(ResumeRow)).scalars().all()) == 1


def test_the_delete_cascades_at_the_DATABASE(session_factory):
    """MEASURED, not assumed. A bulk DELETE bypasses SQLAlchemy's ORM-level
    cascade -- what carries it here is the FK's ON DELETE CASCADE plus
    PRAGMA foreign_keys=ON from app/core/db.py. If either were absent this
    sweep would leave an orphaned extraction holding the very text the resume
    row was deleted to remove, and the sweep would report success."""
    _seed_resume(session_factory, age_days=2000)
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    with session_factory() as s:
        assert s.execute(select(ExtractionRow)).scalars().all() == []


def test_the_cap_bounds_one_invocation_and_the_report_says_so(session_factory):
    for _ in range(4):
        _seed_resume(session_factory, age_days=2000)
    settings = _settings(sweep_max_rows_per_class=2)
    report = run_sweep(session_factory, settings, now=NOW, dry_run=False)
    resumes = next(c for c in report.by_class if c.data_class == "resumes")
    assert resumes.affected == 2
    assert resumes.truncated is True
    assert report.truncated is True          # any class truncated
    with session_factory() as s:
        assert len(s.execute(select(ResumeRow)).scalars().all()) == 2


def test_a_truncated_sweep_finishes_the_job_on_the_next_run(session_factory):
    """`truncated: true` is an instruction, not an apology -- so running again
    must actually make progress rather than re-reporting the same rows."""
    for _ in range(4):
        _seed_resume(session_factory, age_days=2000)
    settings = _settings(sweep_max_rows_per_class=2)
    run_sweep(session_factory, settings, now=NOW, dry_run=False)
    second = run_sweep(session_factory, settings, now=NOW, dry_run=False)
    assert next(
        c for c in second.by_class if c.data_class == "resumes"
    ).truncated is False
    with session_factory() as s:
        assert s.execute(select(ResumeRow)).scalars().all() == []


def test_a_clean_database_reports_zero_everywhere_and_is_not_truncated(session_factory):
    report = run_sweep(session_factory, _settings(), now=NOW, dry_run=True)
    assert all(c.affected == 0 for c in report.by_class)
    assert report.truncated is False
    assert {c.data_class for c in report.by_class} == ALL_CLASSES


# ── CLEAR mode: the row survives, and the predicate has two halves ───────────

_seeded = 0


def _seed_batch_item(session_factory, *, age_days: int, text: str) -> str:
    """One org + batch + item, aged by `age_days`.

    Org names are made unique per call: `uq_organizations_name_ci` is a
    case-insensitive UNIQUE index, so a fixed name would collide on the second
    seed and the failure would look nothing like its cause.
    """
    global _seeded
    _seeded += 1
    when = NOW - timedelta(days=age_days)
    with session_factory() as s:
        org = OrganizationRow(name=f"Agency {_seeded}")
        s.add(org)
        s.flush()
        batch = ScreeningBatchRow(org_id=org.id, domain="genai", created_at=when)
        s.add(batch)
        s.flush()
        item = BatchItemRow(
            batch_id=batch.id, status="failed", raw_text=text,
            text_sha256="b" * 64, created_at=when,
        )
        s.add(item)
        s.commit()
        return item.id


def test_clear_mode_blanks_the_text_and_KEEPS_the_row(session_factory):
    item_id = _seed_batch_item(session_factory, age_days=200, text="a resume")
    report = run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    cleared = next(c for c in report.by_class if c.data_class == "batch_item_text")
    assert cleared.affected == 1
    with session_factory() as s:
        row = s.get(BatchItemRow, item_id)
        assert row is not None, "the org's record of what it screened must survive"
        assert row.raw_text == ""
        assert row.status == "failed"       # the outcome is not rewritten


def test_a_second_sweep_reports_zero_rather_than_the_same_rows_again(session_factory):
    """The non-empty half of the predicate, stated as behaviour. Without it a
    preview reports 'about to clear 1' every day forever on a row that is
    already blank -- and an operator who sees a number that never falls stops
    reading the number."""
    _seed_batch_item(session_factory, age_days=200, text="a resume")
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    second = run_sweep(session_factory, _settings(), now=NOW, dry_run=True)
    cleared = next(c for c in second.by_class if c.data_class == "batch_item_text")
    assert cleared.affected == 0


def test_an_already_blank_row_is_never_counted_even_on_the_FIRST_pass(session_factory):
    """The same predicate from the other side: an item cleared on SUCCESS is
    the common case, and counting those would make the number meaningless from
    the first run rather than from the second."""
    _seed_batch_item(session_factory, age_days=200, text="")
    report = run_sweep(session_factory, _settings(), now=NOW, dry_run=True)
    cleared = next(c for c in report.by_class if c.data_class == "batch_item_text")
    assert cleared.affected == 0


def test_a_recent_failed_item_keeps_its_text_so_retry_still_works(session_factory):
    """Phase A and Phase B meet here: retention BOUNDS the retry window, and
    inside the window the retry's input must still be there."""
    item_id = _seed_batch_item(session_factory, age_days=5, text="a resume")
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    with session_factory() as s:
        assert s.get(BatchItemRow, item_id).raw_text == "a resume"


# ── the counter ──────────────────────────────────────────────────────────────


def test_a_real_sweep_counts_what_it_removed_per_data_class(session_factory):
    _seed_resume(session_factory, age_days=2000)
    metrics = build_metrics()
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False, metrics=metrics)
    key = ("retention_deleted", (("data_class", "resumes"),))
    assert metrics.snapshot().get(key) == 1


def test_a_dry_run_counts_NOTHING(session_factory):
    """A preview that moved the counter would make the runbook's 'how much
    have we deleted' unanswerable -- it would be counting intentions."""
    _seed_resume(session_factory, age_days=2000)
    metrics = build_metrics()
    run_sweep(session_factory, _settings(), now=NOW, dry_run=True, metrics=metrics)
    assert metrics.snapshot() == {}


def test_the_counter_carries_the_ROW_COUNT_not_one_per_class(session_factory):
    for _ in range(3):
        _seed_resume(session_factory, age_days=2000)
    metrics = build_metrics()
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False, metrics=metrics)
    key = ("retention_deleted", (("data_class", "resumes"),))
    assert metrics.snapshot()[key] == 3


def test_a_counter_row_can_never_be_written_without_an_expiry(session_factory):
    """REVIEW FINDING. `rate_limit_counters` is the ONE swept class whose rows
    the sweep judges by `expires_at`, and the predicate skips NULLs -- so a row
    written without one is INVISIBLE TO THE SWEEP FOREVER.

    It is also unreachable by any other cleanup: `RateLimitStore.hit`'s own
    housekeeping only retires older windows *of a key that is hit again*, and
    its docstring says so ("the Phase B sweep owns keys that are never seen
    again"). A NULL row is a salted email hash beside a salted IP hash,
    retained permanently, in the sprint whose entire point is that retention is
    now enforced.

    No caller can write one today, which is exactly why this is a test and not
    a comment -- Phase A's `enforce` fail-open was the same shape. `hit` now
    REQUIRES the value, so the hole cannot be opened by a future caller.
    """
    import inspect

    from app.ratelimit.store import RateLimitStore

    signature = inspect.signature(RateLimitStore.hit)
    expires = signature.parameters["expires_at"]
    assert expires.default is inspect.Parameter.empty, (
        "expires_at must be REQUIRED: a row written without one is retained "
        "forever, because the sweep's predicate skips NULLs"
    )
    assert "Optional" not in str(expires.annotation)


def test_the_sweep_genuinely_cannot_see_a_null_expiry(session_factory):
    """The other half of the finding, as behaviour rather than as a signature:
    a NULL-expiry row planted directly IS immortal. This is what makes the
    required argument load-bearing rather than tidy."""
    from app.ratelimit.models import RateLimitCounterRow

    with session_factory() as s:
        s.add(RateLimitCounterRow(
            bucket_key="d" * 64, window_start=0, count=1, expires_at=None,
        ))
        s.commit()

    run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    with session_factory() as s:
        survivors = s.execute(select(RateLimitCounterRow)).scalars().all()
        assert len(survivors) == 1, (
            "if this ever starts passing with 0, the sweep learned to judge "
            "NULL expiries and this test should become the assertion of that"
        )


def test_cleared_rows_are_counted_under_the_SAME_name(session_factory):
    """One counter, labelled by class. A separate `retention_cleared` would
    make 'how much moved' a sum an operator has to remember to compute."""
    _seed_batch_item(session_factory, age_days=200, text="a resume")
    metrics = build_metrics()
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False, metrics=metrics)
    key = ("retention_deleted", (("data_class", "batch_item_text"),))
    assert metrics.snapshot()[key] == 1
