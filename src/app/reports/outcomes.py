"""The ONE constructor for a human outcome (S8.5, spec §3).

Recording an outcome has two doors as of this sprint -- the operator's
``POST /report/{id}/outcome`` and the customer's
``POST /screening/reports/{id}/outcome`` -- and it carries three rules:

1. a ``claim_id``, when given, must belong to the report;
2. ``notes`` must be bounded;
3. the record must state its own provenance.

This repo's signature defect, found by four consecutive branch reviews (S7.1
``start()``, S7.2 ``claim_ref``, S7.3 the audio path, S8.2 the two-challenge
lockout), is a rule enforced at one entry point and forgotten at the second.
So neither route owns a copy of any of the three. Both call this, and a test
asserts both REFUSE THE SAME INPUTS -- because "both call the helper" is a
claim about today's source, and "both refuse the same input" is a claim about
behaviour.

Pure: no session, no clock beyond ``OutcomeRecord``'s own default, no config
object. The cap arrives as a number, so this module never learns what
``Settings`` is.
"""

from __future__ import annotations

from typing import Optional

from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.schemas.report import Report


class OutcomeRefused(ValueError):
    """Refused before anything was written. ``code`` is a stable reason code --
    never model output, never prose the caller can influence."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def build_outcome(
    report: Report,
    *,
    outcome: OutcomeLabel,
    claim_id: Optional[str],
    notes: str,
    max_notes_chars: int,
    recorded_by: OutcomeSource,
    org_id: Optional[str] = None,
    recorded_by_org_user_id: Optional[str] = None,
) -> OutcomeRecord:
    """Validate and stamp one judgment. Raises ``OutcomeRefused`` (-> 422).

    ``recorded_by`` is deliberately keyword-required with NO default: see
    ``OutcomeRecord``.
    """
    if claim_id is not None:
        known = {v.claim_id for v in report.verdicts}
        if claim_id not in known:
            raise OutcomeRefused(
                "claim_not_in_report",
                f"claim '{claim_id}' is not part of report '{report.id}'",
            )

    # An unbounded free-text field a human types beside a candidate's name is
    # S7.2's `claim_ref` finding one table over -- that one stored 5031 chars
    # including a salary and a UAN.
    if len(notes) > max_notes_chars:
        raise OutcomeRefused(
            "notes_too_long",
            f"notes exceed max_outcome_notes_chars={max_notes_chars}",
        )

    return OutcomeRecord(
        report_id=report.id,
        claim_id=claim_id,
        outcome=outcome,
        notes=notes,
        recorded_by=recorded_by,
        org_id=org_id,
        recorded_by_org_user_id=recorded_by_org_user_id,
    )
