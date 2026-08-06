"""S8.4 Phase A: org-scoped reads. Another org's report is INDISTINGUISHABLE
from one that does not exist -- a 403 would confirm it exists."""

from __future__ import annotations

from datetime import datetime, timezone

from app.candidates.hashing import apply_contact_hashes
from app.candidates.schema import (
    CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult,
)
from app.schemas.report import Report


def _org(services, name):
    return services.ledger.create_organization(name).id


def _upload(services, org_id, *, name="Priya", email="priya@x.io", text="resume text"):
    profile = CandidateProfile(
        full_name=ExtractedStr(value=name),
        contact=ContactInfo(email=ExtractedStr(value=email)),
    )
    apply_contact_hashes(profile, salt=services.settings.contact_hash_salt)
    return services.candidates.ingest(
        ExtractionResult(
            profile=profile,
            method="heuristic",
        ),
        resume_text=text,
        org_id=org_id,
    )


def _report(services, org_id, candidate_id, report_id):
    r = Report(id=report_id, domain="genai", candidate_id=candidate_id,
               created_at=datetime.now(timezone.utc))
    services.report_store.save(r, org_id=org_id)
    return r


def test_get_for_org_returns_only_own_reports(services):
    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    cand = _upload(services, a).candidate_id
    _report(services, a, cand, "rep-a")

    assert services.report_store.get_for_org(a, "rep-a") is not None
    assert services.report_store.get_for_org(b, "rep-a") is None


def test_unowned_reports_belong_to_nobody(services):
    """A pre-S8.4 or admin-uploaded report is unowned, not everyone's."""
    a = _org(services, "Agency A")
    cand = _upload(services, a).candidate_id
    services.report_store.save(
        Report(id="rep-orphan", domain="genai", candidate_id=cand,
               created_at=datetime.now(timezone.utc))
    )
    assert services.report_store.get_for_org(a, "rep-orphan") is None
    assert services.report_store.get("rep-orphan") is not None  # admin still sees it


def test_for_candidate_and_org_filters_by_owner(services):
    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    cand = _upload(services, a).candidate_id
    _report(services, a, cand, "rep-a")
    _report(services, b, cand, "rep-b")

    assert [r.id for r in services.report_store.for_candidate_and_org(a, cand)] == ["rep-a"]
    assert [r.id for r in services.report_store.for_candidate_and_org(b, cand)] == ["rep-b"]


def test_two_orgs_uploading_one_person_share_the_candidate_row(services):
    """The whole point of ownership-on-the-upload: candidates stay global."""
    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    first = _upload(services, a, text="priya v1")
    second = _upload(services, b, text="priya v2")

    assert first.candidate_id == second.candidate_id, "dedup by email hash still holds"
    assert services.candidates.org_owns_candidate(a, first.candidate_id) is True
    assert services.candidates.org_owns_candidate(b, first.candidate_id) is True


def test_org_owns_candidate_is_false_for_a_stranger(services):
    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    cand = _upload(services, a).candidate_id
    assert services.candidates.org_owns_candidate(b, cand) is False


def test_candidate_erasure_still_takes_owned_reports_with_it(services):
    """Ownership must not weaken the DPDP cascade (spec §7).

    reports.candidate_id CASCADEs and reports.org_id SET NULLs -- adding the
    second FK must not have given the row a reason to survive its subject.
    """
    from app.reports.models import ReportRow

    a = _org(services, "Agency A")
    cand = _upload(services, a).candidate_id
    _report(services, a, cand, "rep-erase")

    assert services.candidates.delete_candidate(cand) is True

    with services.candidates._session_factory() as s:
        assert s.get(ReportRow, "rep-erase") is None, (
            "an owned report must still die with its subject"
        )


def test_facade_report_redacts_and_scopes(services):
    from app.schemas.fabrication import ResumeFarmAssessment, ResumeMatch

    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    cand = _upload(services, a).candidate_id
    r = Report(
        id="rep-f", domain="genai", candidate_id=cand,
        created_at=datetime.now(timezone.utc),
        resume_farm=ResumeFarmAssessment(
            matches=[ResumeMatch(candidate_id="other", resume_id="res", similarity=0.9)],
        ),
    )
    services.report_store.save(r, org_id=a)

    got = services.screening_scope.report(a, "rep-f")
    assert got is not None
    assert got.resume_farm.matches[0].candidate_id is None, "facade must redact"
    assert got.resume_farm.matches[0].similarity == 0.9

    assert services.screening_scope.report(b, "rep-f") is None


def test_facade_reports_for_candidate_redacts_every_element(services):
    from app.schemas.fabrication import ResumeFarmAssessment, ResumeMatch

    a = _org(services, "Agency A")
    cand = _upload(services, a).candidate_id
    for rid in ("rep-1", "rep-2"):
        services.report_store.save(
            Report(id=rid, domain="genai", candidate_id=cand,
                   created_at=datetime.now(timezone.utc),
                   resume_farm=ResumeFarmAssessment(
                       matches=[ResumeMatch(candidate_id="o", resume_id="r",
                                            similarity=0.5)])),
            org_id=a,
        )
    out = services.screening_scope.reports_for_candidate(a, cand)
    assert len(out) == 2
    assert all(m.candidate_id is None for r in out for m in r.resume_farm.matches)


def test_facade_owns_candidate(services):
    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    cand = _upload(services, a).candidate_id
    assert services.screening_scope.owns_candidate(a, cand) is True
    assert services.screening_scope.owns_candidate(b, cand) is False


def test_every_facade_read_takes_org_id_first():
    """The signature IS the enforcement; Task 7's guard is the backstop."""
    import inspect
    from app.screening.scope import OrgScopedReads

    for name in ("report", "reports_for_candidate", "owns_candidate"):
        params = list(inspect.signature(getattr(OrgScopedReads, name)).parameters)
        assert params[:2] == ["self", "org_id"], f"{name} must scope by org first"
