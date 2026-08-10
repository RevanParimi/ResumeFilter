"""The ONE door org-plane handlers reach people through (S8.4 Phase A, §3.3).

Four consecutive branch reviews -- S7.1 ``start()``, S7.2 ``claim_ref``, S7.3
the audio path, S8.2 the two-challenge lockout -- each found the same shape: a
rule enforced by REMEMBERING to enforce it, forgotten at the second door. A
tenancy rule spread across the org plane is that shape by construction.

So org handlers get no option. Every method here takes ``org_id`` first, there
is no unscoped read on this object, and both report-returning methods redact
before returning so a handler cannot forget. ``tests/test_org_scope_guard.py``
is the backstop that covers routes nobody has written yet.

**S8.5 renamed this from ``OrgScopedReads``, because it now holds a WRITE.** A
class named for reading while it records outcomes would be a lie in the one
file whose entire job is being trustworthy about scope, and the next person
adding a write would either believe the name or put their write somewhere
worse. The ATTRIBUTE the guard watches -- ``services.screening_scope`` -- is
deliberately unchanged, so the guard needed no edit and keeps covering routes
that do not exist yet.

Owns no tables and holds no state -- pure composition over the two stores, in
the ``app/dashboard/`` style.
"""

from __future__ import annotations

from typing import Optional

from app.candidates.store import CandidateStore
from app.reports.outcomes import build_outcome
from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.reports.store import ReportStore
from app.schemas.report import Report
from app.screening.projection import redact_for_org


class OrgScopedAccess:
    def __init__(self, reports: ReportStore, candidates: CandidateStore) -> None:
        self._reports = reports
        self._candidates = candidates

    def report(self, org_id: str, report_id: str) -> Optional[Report]:
        """One report this org commissioned, redacted. None if it is not theirs.

        None rather than an exception, so the route answers 404: another org's
        report must be indistinguishable from one that does not exist.
        """
        found = self._reports.get_for_org(org_id, report_id)
        return None if found is None else redact_for_org(found)

    def reports_for_candidate(self, org_id: str, candidate_id: str) -> list[Report]:
        """This org's own reports about one person, oldest first, all redacted.

        A person this org has never uploaded yields an EMPTY LIST, not a 404 --
        "you have no reports about them" and "they do not exist" are different
        facts, and only the first is this org's business.
        """
        return [
            redact_for_org(r)
            for r in self._reports.for_candidate_and_org(org_id, candidate_id)
        ]

    def owns_candidate(self, org_id: str, candidate_id: str) -> bool:
        return self._candidates.org_owns_candidate(org_id, candidate_id)

    def record_outcome(
        self,
        org_id: str,
        report_id: str,
        *,
        outcome: OutcomeLabel,
        claim_id: Optional[str],
        notes: str,
        max_notes_chars: int,
        org_user_id: Optional[str],
    ) -> Optional[OutcomeRecord]:
        """The customer closing the loop on a report they commissioned (S8.5).

        ``None`` for "not yours, or absent" -- the same answer as ``.report``,
        so the two reads and the one write cannot disagree about what a missing
        report looks like, and the route emits one 404 for all of it.

        Raises ``OutcomeRefused`` (-> 422) for an unknown claim or an over-long
        note. Both rules live in ``build_outcome``, shared with the operator's
        route: this is the second door, and a rule that only one door enforces
        is this repo's signature defect.

        ``recorded_by`` is NOT a parameter. This facade *is* the org plane, so
        it cannot stamp anything else -- which is a stronger guarantee than a
        caller passing the right value, and the reason the argument exists at
        all is that ``org_id`` is SET NULL and a null org must stay
        distinguishable from an operator's judgment.

        The redaction is irrelevant here and that is deliberate: the read used
        for validation is the UNredacted row (only ``resume_farm.matches[]``
        differs, and a claim id is not in it), while nothing about the report
        is returned to the caller at all.
        """
        report = self._reports.get_for_org(org_id, report_id)
        if report is None:
            return None
        record = build_outcome(
            report,
            outcome=outcome,
            claim_id=claim_id,
            notes=notes,
            max_notes_chars=max_notes_chars,
            recorded_by=OutcomeSource.ORGANIZATION,
            org_id=org_id,
            recorded_by_org_user_id=org_user_id,
        )
        self._reports.add_outcome(record)
        return record

    def outcomes(
        self, org_id: str, report_id: str
    ) -> Optional[list[OutcomeRecord]]:
        """This org's OWN judgments on a report it commissioned (S8.5).

        Not every judgment on that report: an operator's internal note lives on
        the same row set, and the customer is not its audience. ``None`` for
        "not yours, or absent"; an empty list means "yours, nothing recorded".
        """
        return self._reports.outcomes_for_org(org_id, report_id)


def build_org_scoped_access(
    reports: ReportStore, candidates: CandidateStore
) -> OrgScopedAccess:
    return OrgScopedAccess(reports, candidates)
