"""The ONE ingest core (S8.4 Phase B, design §1.3).

``POST /screening/candidates`` and ``POST /screening/batches/{id}/process`` run
the same pipeline: extract, resolve identity, store, fingerprint, farm-check,
evaluate. It lives here rather than in the route because the batch processor
cannot use a FastAPI ``Request`` and must turn a refusal into a row status
rather than a status code.

So refusals are ``IngestRefused(reason)`` carrying a reason CODE, and the two
callers map it their own way: the route to 422, the processor to
``status='failed', error=<reason>``.

Extracting this also emptied ``ALLOWLISTED_LINES`` in
``tests/test_org_scope_guard.py`` -- all five exemptions were lines of this
function. The one genuinely cross-tenant read among them, ``similar_resumes``
(which must scan every customer's fingerprints or the resume-farm check is
worthless), is still bounded exactly where it was: at the org-plane boundary by
``redact_ingest_response_for_org``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from app.candidates.store import CandidateStore, MatchedOn
from app.core.config import Settings
from app.reports.store import ReportStore, SubjectErasedError
from app.schemas.fabrication import ResumeFarmAssessment
from app.schemas.report import Report
from app.services.llm import LLMClient

if TYPE_CHECKING:
    from app.graph.build import EvaluationEngine
    from app.services import Services


class IngestRefused(Exception):
    """A refusal carrying a reason CODE, never prose.

    The code is written onto ``batch_items.error`` -- a ``String(64)`` holding
    closed vocabulary, never model output and never another row's content.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class IngestDeps:
    """Exactly what ingestion needs, so nothing here reaches a whole container."""

    candidates: CandidateStore
    reports: ReportStore
    llm: LLMClient
    settings: Settings


def ingest_deps(services: "Services") -> IngestDeps:
    return IngestDeps(
        candidates=services.candidates,
        reports=services.report_store,
        llm=services.llm,
        settings=services.settings,
    )


@dataclass(frozen=True)
class IngestResult:
    candidate_id: str
    resume_id: str
    resume_version: int
    matched_existing: bool
    matched_on: Optional[MatchedOn]
    duplicate_resume: bool
    extraction_method: str
    report: Optional[Report]
    resume_farm: ResumeFarmAssessment


async def ingest_resume(
    deps: IngestDeps,
    engine: "EvaluationEngine",
    *,
    text: str,
    domain: str,
    evaluate: bool,
    org_id: Optional[str],
) -> IngestResult:
    """Upload -> extract -> store -> (auto) depth-eval, for ONE resume.

    ``org_id`` is the owner stamped on the resume and on the report; ``None`` is
    the admin plane, which owns nothing by design.
    """
    # Function-local: these pull in the domain registry and the graph, and a
    # top-level import would cycle back through app.services.
    # Paths VERIFIED against app/api/routes.py:27-32 -- note `domains.base`
    # (not `app.domains`) and `fabrication.similarity` (not `resume_farm`).
    from app.candidates.extractor import extract_profile
    from app.domains.base import get_domain
    from app.fabrication.similarity import assess_resume_farm, fingerprint_text

    if len(text) > deps.settings.max_resume_chars:
        raise IngestRefused("resume_too_long")
    text = (text or "").strip()
    if not text:
        raise IngestRefused("empty_resume")
    try:
        get_domain(domain)
    except KeyError as exc:
        raise IngestRefused("unknown_domain") from exc

    result = await extract_profile(text, llm=deps.llm, settings=deps.settings)
    outcome = deps.candidates.ingest(result, text, org_id=org_id)

    # S2.3: fingerprint + farm check. Lives HERE, not in a graph node: the
    # comparison must exclude the uploader's own candidate (re-uploads and new
    # versions are legitimate), and the graph deliberately never learns the
    # candidate identity.
    farm = ResumeFarmAssessment()  # insufficient_data when the text is too short
    fp = fingerprint_text(text, deps.settings)
    if fp is not None:
        deps.candidates.save_fingerprint(
            fp, resume_id=outcome.resume_id, candidate_id=outcome.candidate_id
        )
        matches, corpus = deps.candidates.similar_resumes(
            fp,
            exclude_candidate_id=outcome.candidate_id,
            threshold=deps.settings.rf_similar_threshold,
            limit=deps.settings.rf_max_matches,
        )
        farm = assess_resume_farm(
            matches, shingle_count=fp.shingle_count, corpus_size=corpus,
            settings=deps.settings,
        )

    report: Optional[Report] = None
    if evaluate:
        report = await engine.evaluate(
            resume_text=text, domain=domain,
            candidate_profile=result.profile, resume_farm=farm,
        )
        report.candidate_id = outcome.candidate_id
        # DPDP: a derived report must not outlive the erasure of its subject.
        # Since S8.1 the foreign key REFUSES the orphan outright, and an erasure
        # landing after the save cascades the row away -- so both halves of this
        # race are the database's job, not a compensating delete we remember.
        try:
            deps.reports.save(report, org_id=org_id)
        except SubjectErasedError:
            report = None
        else:
            if deps.candidates.get_candidate(outcome.candidate_id) is None:
                report = None

    return IngestResult(
        candidate_id=outcome.candidate_id,
        resume_id=outcome.resume_id,
        resume_version=outcome.resume_version,
        matched_existing=outcome.matched_existing,
        matched_on=outcome.matched_on,
        duplicate_resume=outcome.duplicate_resume,
        extraction_method=result.method,
        report=report,
        resume_farm=farm,
    )
