"""The org-facing redactions (S8.4 Phase A, spec §3.4).

``resume_farm.matches[]`` names other candidates' resumes, which may belong to
another customer. An organization learns THAT a near-duplicate exists and how
similar it is -- never whose it is.

``_stripped_matches`` is the one place that stripping happens. Every org-facing
reader of a ``ResumeFarmAssessment`` calls it, directly or via one of the two
functions below: the single-report route, Phase B's batch queue read-model,
and -- since the leak this module was found carrying (see
``redact_ingest_response_for_org``) -- the upload response itself. Two copies
of the strip would be a bound that holds on one path and lapses on another,
which is the S7.2 ``claim_ref`` finding and the S7.3 transcript finding a
third time; this module exists so there is exactly one.

Pure: no I/O, no session, no clock. Input objects are never mutated -- they
are usually the admin plane's own objects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas.fabrication import ResumeFarmAssessment
from app.schemas.report import Report

if TYPE_CHECKING:
    # Deferred: app.api.routes reaches this module at runtime via
    # app.services -> app.screening.scope -> app.screening.projection, so a
    # top-level import here would cycle. `from __future__ import annotations`
    # (above) makes every annotation in this file a lazy string, so this
    # import is never executed at runtime -- it exists purely for type
    # checkers/IDEs to resolve the hint on redact_ingest_response_for_org.
    from app.api.routes import CandidateCreateResponse


def _stripped_matches(farm: ResumeFarmAssessment) -> ResumeFarmAssessment:
    """Return a copy of ``farm`` with candidate_id/resume_id stripped from
    every match. The one primitive both redactions below call -- see the
    module docstring for why there is only one.

    A present-but-empty ``matches`` list round-trips unchanged (nothing to
    strip); callers still decide what an absent assessment means.
    """
    if not farm.matches:
        return farm
    redacted = [
        m.model_copy(update={"candidate_id": None, "resume_id": None})
        for m in farm.matches
    ]
    return farm.model_copy(update={"matches": redacted})


def redact_for_org(report: Report) -> Report:
    """Return a copy safe to hand an organization.

    Everything else survives, deliberately: the org sees the FULL report,
    including ``verdicts[]``, ``missing_signals`` and ``probes[]``. Those are
    what convert a score into an action (UI.md §4.B), and withholding them
    would make the numbers less useful without making them more honest.

    ``resume_farm`` stays exactly what it was -- ``None`` round-trips as
    ``None``, and a present-but-empty assessment round-trips as present and
    empty -- because a null and an ``insufficient_data`` conclusion are
    different facts (no assessment ever ran, vs. one ran and could not say),
    and this function's one job is stripping counterparty identity, not
    inventing signal.
    """
    farm = report.resume_farm
    if farm is None or not farm.matches:
        return report.model_copy(deep=True)

    return report.model_copy(
        deep=True,
        update={"resume_farm": _stripped_matches(farm)},
    )


def redact_ingest_response_for_org(
    resp: "CandidateCreateResponse",
) -> "CandidateCreateResponse":
    """Redact an org-plane upload response before it leaves the process.

    ``_ingest_one`` (app/api/routes.py) computes ``resume_farm`` from
    ``services.candidates.similar_resumes(...)``, which scans the ENTIRE
    platform's resume fingerprints -- every customer's -- excluding only the
    uploader's own candidate. The resulting assessment carries real
    ``candidate_id``/``resume_id`` values that may belong to another
    organization's candidates, and it appears TWICE in the response: as the
    top-level ``resume_farm`` and again inside the embedded ``report``'s own
    ``resume_farm``. Both must be stripped, or the second copy re-leaks what
    the first one just redacted.

    Same ``None``/empty preservation rule as ``redact_for_org``: an absent or
    empty assessment is left exactly as it was, on both the top-level field
    and (via delegating to ``redact_for_org``) the embedded report.
    """
    update: dict[str, object] = {}

    farm = resp.resume_farm
    if farm is not None and farm.matches:
        update["resume_farm"] = _stripped_matches(farm)

    if resp.report is not None:
        update["report"] = redact_for_org(resp.report)

    if not update:
        return resp.model_copy(deep=True)
    return resp.model_copy(deep=True, update=update)
