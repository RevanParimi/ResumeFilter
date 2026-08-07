"""The ONE door org-plane handlers read people through (S8.4 Phase A, §3.3).

Four consecutive branch reviews -- S7.1 ``start()``, S7.2 ``claim_ref``, S7.3
the audio path, S8.2 the two-challenge lockout -- each found the same shape: a
rule enforced by REMEMBERING to enforce it, forgotten at the second door. A
tenancy rule spread across the org plane is that shape by construction.

So org handlers get no option. Every method here takes ``org_id`` first, there
is no unscoped read on this object, and both report-returning methods redact
before returning so a handler cannot forget. ``tests/test_org_scope_guard.py``
is the backstop that covers routes nobody has written yet.

Owns no tables and holds no state -- pure composition over the two stores, in
the ``app/dashboard/`` style.
"""

from __future__ import annotations

from typing import Optional

from app.candidates.store import CandidateStore
from app.reports.store import ReportStore
from app.schemas.report import Report
from app.screening.projection import redact_for_org


class OrgScopedReads:
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


def build_org_scoped_reads(
    reports: ReportStore, candidates: CandidateStore
) -> OrgScopedReads:
    return OrgScopedReads(reports, candidates)
