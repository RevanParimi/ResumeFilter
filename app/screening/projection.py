"""The ONE org-facing redaction (S8.4 Phase A, spec §3.4).

``resume_farm.matches[]`` names other candidates' resumes, which may belong to
another customer. An organization learns THAT a near-duplicate exists and how
similar it is -- never whose it is.

This function is the only place that happens. Every org-facing reader calls it:
the single-report route and Phase B's batch queue read-model. Two copies would
be a bound that holds on one path and lapses on the other, which is the S7.2
``claim_ref`` finding and the S7.3 transcript finding a third time.

Pure: no I/O, no session, no clock. The input report is never mutated -- it is
usually the admin plane's own object.
"""

from __future__ import annotations

from app.schemas.fabrication import ResumeFarmAssessment
from app.schemas.report import Report


def redact_for_org(report: Report) -> Report:
    """Return a copy safe to hand an organization.

    Everything else survives, deliberately: the org sees the FULL report,
    including ``verdicts[]``, ``missing_signals`` and ``probes[]``. Those are
    what convert a score into an action (UI.md §4.B), and withholding them
    would make the numbers less useful without making them more honest.

    ``resume_farm`` is ``None`` for pre-S2.3 reports and ad-hoc ``POST
    /evaluate`` runs that never touched the farm detector. The org-facing copy
    normalizes that into an empty, ``INSUFFICIENT_DATA`` assessment rather
    than leaving ``None`` -- "no farm signal was computed" is representable
    honestly, and org-facing callers never have to null-check ``resume_farm``.
    """
    farm = report.resume_farm or ResumeFarmAssessment()
    if not farm.matches:
        return report.model_copy(deep=True, update={"resume_farm": farm.model_copy(deep=True)})

    redacted = [
        m.model_copy(update={"candidate_id": None, "resume_id": None})
        for m in farm.matches
    ]
    return report.model_copy(
        deep=True,
        update={"resume_farm": farm.model_copy(update={"matches": redacted})},
    )
