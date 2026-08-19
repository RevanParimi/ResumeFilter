"""The cross-report outcome scan (S9.1 Task 5).

Both existing readers are report-scoped -- `outcomes(report_id)` for the
operator, `outcomes_for_org(org_id, report_id)` for the customer. A calibration
harness asks a different question ("across everything we ever judged, how well
did the signal track the verdict?"), so it needs a scan, and the scan is
ADMIN-PLANE ONLY: cross-tenant by construction, with deliberately no org-scoped
variant.

Built on the real SqlReportStore against real SQLite, like tests/
test_report_store.py -- there is one implementation and no in-memory fake, so
there is nothing here that can drift away from what production runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.reports.store import SqlReportStore
from app.schemas.report import CoherenceVerdict, Report
from tests.conftest import make_candidate_store


@pytest.fixture
def factory():
    return make_candidate_store()._session_factory


@pytest.fixture
def store(factory):
    return SqlReportStore(factory)


def _report(store, *claim_ids: str, created_at=None) -> Report:
    rep = Report(
        domain="genai",
        created_at=created_at or datetime.now(timezone.utc),
        verdicts=[
            CoherenceVerdict(
                claim_id=c, claim_text="built a thing", claim_type="project"
            )
            for c in claim_ids
        ],
    )
    store.save(rep)
    return rep


def _outcome(rep, **over) -> OutcomeRecord:
    base = dict(
        report_id=rep.id,
        outcome=OutcomeLabel.VERIFIED_FABRICATED,
        recorded_by=OutcomeSource.ORGANIZATION,
        recorded_at=datetime.now(timezone.utc),
    )
    base.update(over)
    return OutcomeRecord(**base)


def test_scan_returns_every_report_level_outcome_joined_to_its_report(store):
    rep = _report(store)
    store.add_outcome(_outcome(rep))

    rows = store.report_level_outcomes()
    assert len(rows) == 1
    got_report, got_outcome = rows[0]
    assert got_report.id == rep.id
    assert got_outcome.outcome is OutcomeLabel.VERIFIED_FABRICATED
    assert got_outcome.recorded_by is OutcomeSource.ORGANIZATION


def test_scan_excludes_per_claim_outcomes(store):
    """A per-claim outcome judges ONE CLAIM. Every signal this harness measures
    is report-level, so scoring a whole-report number against a single claim's
    verdict is a category error one column over."""
    rep = _report(store, "clm-1")
    store.add_outcome(_outcome(rep, claim_id="clm-1"))

    assert store.report_level_outcomes() == []


def test_scan_keeps_the_report_level_row_when_a_report_has_both(store):
    """The filter must be per ROW, not per report: a report judged as a whole
    AND claim-by-claim is the normal case once a reviewer works through it."""
    rep = _report(store, "clm-1")
    store.add_outcome(_outcome(rep, claim_id="clm-1"))
    store.add_outcome(_outcome(rep, outcome=OutcomeLabel.VERIFIED_GENUINE))

    rows = store.report_level_outcomes()
    assert [o.outcome for _, o in rows] == [OutcomeLabel.VERIFIED_GENUINE]
    assert all(o.claim_id is None for _, o in rows)


def test_scan_is_cross_report_and_cross_org(store):
    now = datetime.now(timezone.utc)
    for i in range(3):
        rep = _report(store, created_at=now + timedelta(hours=i))
        store.add_outcome(
            _outcome(rep, outcome=OutcomeLabel.VERIFIED_GENUINE,
                     recorded_by=OutcomeSource.OPERATOR)
        )
    assert len(store.report_level_outcomes()) == 3


def test_scan_is_empty_when_nothing_was_judged(store):
    _report(store)
    assert store.report_level_outcomes() == []


def test_the_order_is_deterministic_when_two_outcomes_share_a_timestamp(store):
    """The `id` tiebreak is the whole reason the ORDER BY has three columns.

    A label source reducing many outcomes to one ('earliest wins') is only
    deterministic if the scan is, and a same-second double submit -- two
    reviewers, one report, one click each -- produces exactly this. Without the
    tiebreak SQLite may return either row first and the harness's label would
    depend on page cache state.
    """
    rep = _report(store)
    same = datetime.now(timezone.utc)
    store.add_outcome(_outcome(rep, outcome=OutcomeLabel.VERIFIED_GENUINE,
                               recorded_at=same))
    store.add_outcome(_outcome(rep, outcome=OutcomeLabel.VERIFIED_FABRICATED,
                               recorded_at=same))

    first = [store.report_level_outcomes() for _ in range(5)]
    assert all(r == first[0] for r in first)
    assert [o.outcome for _, o in first[0]] == [
        OutcomeLabel.VERIFIED_GENUINE, OutcomeLabel.VERIFIED_FABRICATED,
    ]


def test_all_reports_with_candidates_skips_ad_hoc_reports():
    """POST /evaluate reports carry candidate_id=None: there is no subject to
    join a ledger row to, so the ledger label source must never see them."""
    from app.candidates.extractor import heuristic_profile
    from app.candidates.schema import ExtractionResult

    cs = make_candidate_store()
    store = SqlReportStore(cs._session_factory)
    resume = "Jane Rao\nML Engineer\nSkills: Python\nEmail: jane@example.com\n"
    cid = cs.ingest(
        ExtractionResult(profile=heuristic_profile(resume), method="heuristic"),
        resume_text=resume,
    ).candidate_id

    now = datetime.now(timezone.utc)
    store.save(Report(domain="genai", candidate_id=cid, created_at=now))
    store.save(Report(domain="genai", candidate_id=None, created_at=now))

    got = store.all_reports_with_candidates()
    assert len(got) == 1 and got[0].candidate_id == cid
