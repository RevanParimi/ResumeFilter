from datetime import datetime, timedelta, timezone

from app.ledger.schema import (
    CodingPlatform, CodingRoundResult, InterviewOutcome, InterviewRecord, InterviewStage,
)
from app.features.training import build_label

T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _ir(outcome, when, rid="r"):
    return InterviewRecord(id=rid, org_id="o1", candidate_id="c1", consent_id="g1",
                           stage=InterviewStage.HM, outcome=outcome, interviewed_at=when,
                           created_at=when)


def _cr(pct, when, rid="cr"):
    return CodingRoundResult(id=rid, org_id="o1", candidate_id="c1", consent_id="g1",
                             platform=CodingPlatform.HACKERRANK, score=80.0, percentile=pct,
                             taken_at=when, created_at=when)


def test_record_at_exactly_as_of_does_not_leak_into_label():
    # A record AT the cut fed features; strictly-after is required to label.
    lab = build_label(as_of=T, interview_records=[_ir(InterviewOutcome.HIRED, T)],
                      coding_rounds=[], consent_allowed=True)
    assert lab.observed is False and lab.hired is None and lab.outcome is None


def test_post_cut_hired_labels_positive_with_lag():
    when = T + timedelta(days=30)
    lab = build_label(as_of=T, interview_records=[_ir(InterviewOutcome.HIRED, when)],
                      coding_rounds=[], consent_allowed=True)
    assert lab.observed is True and lab.hired is True and lab.outcome == "hired"
    assert lab.event_at == when and abs(lab.lag_days - 30.0) < 1e-6


def test_terminal_best_wins_and_withdrawn_excluded():
    recs = [
        _ir(InterviewOutcome.REJECTED, T + timedelta(days=5), "a"),
        _ir(InterviewOutcome.OFFER, T + timedelta(days=10), "b"),
        _ir(InterviewOutcome.WITHDRAWN, T + timedelta(days=20), "c"),
    ]
    lab = build_label(as_of=T, interview_records=recs, coding_rounds=[], consent_allowed=True)
    assert lab.outcome == "offer" and lab.hired is True
    assert lab.event_at == T + timedelta(days=10)  # earliest carrier of the winner


def test_event_at_is_earliest_carrier_of_winning_outcome():
    recs = [
        _ir(InterviewOutcome.HIRED, T + timedelta(days=40), "late"),
        _ir(InterviewOutcome.HIRED, T + timedelta(days=15), "early"),
    ]
    lab = build_label(as_of=T, interview_records=recs, coding_rounds=[], consent_allowed=True)
    assert lab.event_at == T + timedelta(days=15)


def test_advanced_and_rejected_are_not_hire_positive():
    for oc in (InterviewOutcome.ADVANCED, InterviewOutcome.REJECTED, InterviewOutcome.NO_SHOW):
        lab = build_label(as_of=T, interview_records=[_ir(oc, T + timedelta(days=3))],
                          coding_rounds=[], consent_allowed=True)
        assert lab.observed is True and lab.hired is False and lab.outcome == oc.value


def test_all_withdrawn_is_unobserved():
    lab = build_label(as_of=T, interview_records=[_ir(InterviewOutcome.WITHDRAWN, T + timedelta(days=3))],
                      coding_rounds=[], consent_allowed=True)
    assert lab.observed is False and lab.hired is None


def test_censored_when_no_post_cut_record_but_coding_still_set():
    # pre-cut hired must NOT label; post-cut coding percentile is independent.
    lab = build_label(as_of=T,
                      interview_records=[_ir(InterviewOutcome.HIRED, T - timedelta(days=10))],
                      coding_rounds=[_cr(88.0, T + timedelta(days=5))], consent_allowed=True)
    assert lab.observed is False and lab.hired is None and lab.outcome is None
    assert lab.coding_best_percentile == 88.0


def test_coding_best_is_max_post_cut_percentile_ignoring_pre_and_nulls():
    rounds = [
        _cr(99.0, T - timedelta(days=1), "pre"),        # pre-cut -> ignored
        _cr(70.0, T + timedelta(days=1), "p70"),
        _cr(None, T + timedelta(days=2), "pnull"),      # no percentile -> ignored
        _cr(85.0, T + timedelta(days=3), "p85"),
    ]
    lab = build_label(as_of=T, interview_records=[], coding_rounds=rounds, consent_allowed=True)
    assert lab.coding_best_percentile == 85.0 and lab.observed is False


def test_consent_withheld_yields_fully_null_label_even_with_records():
    lab = build_label(as_of=T, interview_records=[_ir(InterviewOutcome.HIRED, T + timedelta(days=3))],
                      coding_rounds=[_cr(90.0, T + timedelta(days=3))], consent_allowed=False)
    assert lab.withheld is True and lab.observed is False
    assert lab.hired is None and lab.outcome is None and lab.coding_best_percentile is None
