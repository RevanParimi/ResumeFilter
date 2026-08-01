"""S7.3 contracts. Taxonomies are code constants; the ladder-separation and
advisory guarantees are asserted here so no later layer can quietly drop them."""

from datetime import datetime, timezone

import pytest

from app.interview.schema import (
    DIMENSIONS, AnswerChannel, InterviewAssessment, InterviewBand, InterviewQuestion,
    InterviewStatus, InterviewSummary, ProxyBand, ProxyFinding, ProxyRisk, TurnScore,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def test_status_and_channel_vocabularies():
    assert {s.value for s in InterviewStatus} == {"in_progress", "completed", "abandoned"}
    assert {c.value for c in AnswerChannel} == {"audio", "text"}


def test_bands_are_ordered_vocabularies_not_numbers():
    # A band is a label over a score; unlike AssuranceLevel it is never max()'d.
    assert [b.value for b in InterviewBand] == [
        "insufficient_signal", "superficial", "emerging", "solid", "deep"
    ]
    assert [b.value for b in ProxyBand] == ["low", "moderate", "elevated"]


def test_interview_band_is_not_the_depth_band_type():
    """A resume-depth band and a live-interview band must never be silently
    interchangeable (spec section 5)."""
    from app.schemas.report import DepthBand

    assert InterviewBand is not DepthBand
    assert {b.value for b in InterviewBand} == {b.value for b in DepthBand}


def test_dimensions_are_the_four_rubric_axes():
    assert DIMENSIONS == ("specificity", "ownership", "depth", "consistency")


def test_proxy_finding_rejects_an_unknown_severity():
    ProxyFinding(id="x", severity="soft", message="m")
    ProxyFinding(id="x", severity="info", message="m")
    with pytest.raises(ValueError):
        ProxyFinding(id="x", severity="hard", message="m")


def test_proxy_risk_defaults_to_low_and_advisory():
    risk = ProxyRisk()
    assert risk.band is ProxyBand.LOW
    assert risk.findings == []
    assert risk.advisory is True


def test_assessment_is_advisory_and_review_required_by_default():
    a = InterviewAssessment(
        session_id="s1", candidate_id="c1", questions_planned=3, questions_answered=0,
        proxy=ProxyRisk(), scorer_version="s73.1",
    )
    assert a.advisory is True and a.human_review_required is True
    assert a.band is InterviewBand.INSUFFICIENT_SIGNAL
    assert a.overall == 0.0 and a.confidence == 0.0


def test_turn_score_can_be_empty_for_an_insufficient_answer():
    score = TurnScore(insufficient=True, codes=["insufficient_answer"])
    assert score.dimensions == {}


def test_summary_carries_no_transcript_field():
    """The org-facing projection must be structurally incapable of leaking words."""
    assert "transcript" not in InterviewSummary.model_fields
    assert "turns" not in InterviewSummary.model_fields


def test_question_carries_expected_signals_for_the_scorer():
    q = InterviewQuestion(id="q1", sequence=1, text="why?", source="probe",
                          expected_signals=["eval harness"], claim_id="cl1")
    assert q.expected_signals == ["eval harness"]


def test_summary_round_trips_through_json():
    s = InterviewSummary(id="s1", status=InterviewStatus.COMPLETED, started_at=NOW)
    dumped = s.model_dump(mode="json")
    assert dumped["status"] == "completed"
    assert dumped["advisory"] is True


def test_verification_never_imports_interview():
    """Layering, pinned: app/interview/ reads the S7.1 assurance number, so the
    dependency runs one way only. The same rule S5.2 set for ledger<-comp."""
    import pathlib

    verification = pathlib.Path("app/verification")
    offenders = [
        f.name for f in verification.glob("*.py")
        if "app.interview" in f.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"verification must not import interview: {offenders}"
