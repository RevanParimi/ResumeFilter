"""The ONE constructor both outcome doors go through (S8.5, spec §3/§4).

Recording an outcome is about to gain a second entry point, and it carries
three rules: the claim must belong to the report, the notes must be bounded,
and the record must state its own provenance. This repo's signature defect --
found by four consecutive branch reviews -- is a rule enforced at one entry
point and forgotten at the second, so the rules live here, in a pure function,
and neither route is allowed to own a copy.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.reports.outcomes import OutcomeRefused, build_outcome
from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.schemas.report import CoherenceVerdict, Report, VerdictStatus


def _report(*claim_ids: str) -> Report:
    return Report(
        id="rep-1",
        domain="genai",
        candidate_id="cand-1",
        created_at=datetime.now(timezone.utc),
        verdicts=[
            CoherenceVerdict(
                claim_id=c,
                claim_text="built a thing",
                claim_type="project",
                status=VerdictStatus.COHERENT,
            )
            for c in claim_ids
        ],
    )


def test_a_report_level_outcome_needs_no_claim():
    rec = build_outcome(
        _report("clm-1"),
        outcome=OutcomeLabel.INCONCLUSIVE,
        claim_id=None,
        notes="screen pending",
        max_notes_chars=2000,
        recorded_by=OutcomeSource.OPERATOR,
    )
    assert isinstance(rec, OutcomeRecord)
    assert rec.report_id == "rep-1"
    assert rec.claim_id is None
    assert rec.recorded_by is OutcomeSource.OPERATOR
    assert rec.org_id is None


def test_a_known_claim_is_accepted_and_an_unknown_one_is_refused():
    report = _report("clm-1", "clm-2")
    ok = build_outcome(
        report, outcome=OutcomeLabel.VERIFIED_FABRICATED, claim_id="clm-2",
        notes="", max_notes_chars=2000, recorded_by=OutcomeSource.OPERATOR,
    )
    assert ok.claim_id == "clm-2"

    with pytest.raises(OutcomeRefused) as exc:
        build_outcome(
            report, outcome=OutcomeLabel.VERIFIED_GENUINE, claim_id="clm-nope",
            notes="", max_notes_chars=2000, recorded_by=OutcomeSource.OPERATOR,
        )
    assert exc.value.code == "claim_not_in_report"
    assert "clm-nope" in str(exc.value)


def test_notes_are_bounded():
    """S7.2's `claim_ref` finding, one table over: an unbounded free-text field
    that a human types beside a candidate's name. 5031 characters including a
    salary and a UAN is what that cost last time."""
    report = _report("clm-1")
    at_cap = build_outcome(
        report, outcome=OutcomeLabel.INCONCLUSIVE, claim_id=None,
        notes="x" * 50, max_notes_chars=50, recorded_by=OutcomeSource.OPERATOR,
    )
    assert len(at_cap.notes) == 50

    with pytest.raises(OutcomeRefused) as exc:
        build_outcome(
            report, outcome=OutcomeLabel.INCONCLUSIVE, claim_id=None,
            notes="x" * 51, max_notes_chars=50,
            recorded_by=OutcomeSource.OPERATOR,
        )
    assert exc.value.code == "notes_too_long"
    assert "50" in str(exc.value), "the refusal must name the cap it enforced"


def test_provenance_is_carried_through():
    rec = build_outcome(
        _report("clm-1"),
        outcome=OutcomeLabel.VERIFIED_GENUINE,
        claim_id="clm-1",
        notes="spoke to the employer",
        max_notes_chars=2000,
        recorded_by=OutcomeSource.ORGANIZATION,
        org_id="org-a",
        recorded_by_org_user_id="user-7",
    )
    assert rec.recorded_by is OutcomeSource.ORGANIZATION
    assert rec.org_id == "org-a"
    assert rec.recorded_by_org_user_id == "user-7"


def test_recorded_by_has_no_default_anywhere():
    """A default would be the forget-me hazard the shared constructor exists to
    remove -- and a wrong provenance stamp is invisible until PI-9 draws a
    conclusion from it (spec §2/§3)."""
    import inspect

    params = inspect.signature(build_outcome).parameters
    assert params["recorded_by"].default is inspect.Parameter.empty, (
        "build_outcome must not default recorded_by"
    )
    assert OutcomeRecord.model_fields["recorded_by"].is_required(), (
        "OutcomeRecord.recorded_by must be a required field"
    )


def test_the_source_enum_has_exactly_two_members():
    """The distinction PI-9 depends on is 'did a customer say this, or did we'.
    A third member would need a calibration argument, in writing."""
    assert {s.value for s in OutcomeSource} == {"operator", "organization"}
