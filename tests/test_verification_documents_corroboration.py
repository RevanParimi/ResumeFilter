"""S7.2 follow-up: cross-source corroboration as an ADVISORY FINDING.

The strength ladder is deliberately untouched. A LinkedIn export is the
candidate's own artifact, so agreement between it and their letter is the same
principal asserting the same thing twice -- worth surfacing to a reviewer,
never worth calling `CORROBORATED`, which means an INDEPENDENT source agrees.
"""

from datetime import datetime, timezone

from app.candidates.schema import CandidateProfile, DateRange, ExperienceEntry
from app.verification.documents import ParsedDocument, assess, assess_experience_letter
from app.verification.schema import ClaimStrength, DocumentType, VerificationStatus

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)

LETTER = """
ACME TECHNOLOGIES PRIVATE LIMITED
hr@acme.com
This is to certify that A Candidate (Employee ID ACM-1) was employed with Acme
Technologies as a Senior Software Engineer from March 2021 to January 2024.
Head of Human Resources
"""


def _profile(employer="Acme Technologies"):
    return CandidateProfile(experience=[ExperienceEntry(
        employer=employer, title="Senior Software Engineer",
        dates=DateRange(start="2021-03", end="2024-01"))])


def _parsed(text=LETTER):
    return ParsedDocument(text=text, page_count=1, digest="d" * 64, metadata={})


def _ids(a):
    return {f.id for f in a.findings}


def _assess(corroborating=frozenset(), profile=None):
    return assess_experience_letter(
        _parsed(), profile or _profile(), at=NOW, metadata_skew_days=1,
        corroborating_employers=corroborating,
    )


def test_an_employer_present_in_a_profile_source_is_corroborated():
    a = _assess({"Acme Technologies"})
    assert "employer_corroborated_by_profile_source" in _ids(a)
    assert a.status is VerificationStatus.VERIFIED


def test_corroboration_does_not_lift_the_strength():
    """THE point of this increment. CORROBORATED means an INDEPENDENT source
    agrees; a LinkedIn export the candidate uploaded is not independent of the
    candidate, so it informs a reviewer and moves no number."""
    plain = _assess()
    corroborated = _assess({"Acme Technologies"})
    assert plain.strength is ClaimStrength.DOCUMENTED
    assert corroborated.strength is ClaimStrength.DOCUMENTED
    assert corroborated.strength is not ClaimStrength.CORROBORATED


def test_an_employer_absent_from_a_populated_profile_source_is_only_info():
    """People leave short stints, contract roles and stealth startups off
    LinkedIn constantly. Anything above `info` here is a false-positive factory."""
    a = _assess({"Globex Corp"})
    assert "employer_absent_from_profile_source" in _ids(a)
    absent = next(f for f in a.findings
                  if f.id == "employer_absent_from_profile_source")
    assert absent.severity == "info"
    assert a.status is VerificationStatus.VERIFIED


def test_no_profile_source_on_file_produces_no_corroboration_finding_either_way():
    a = _assess(frozenset())
    assert "employer_corroborated_by_profile_source" not in _ids(a)
    assert "employer_absent_from_profile_source" not in _ids(a)


def test_corroboration_tolerates_a_differently_written_legal_suffix():
    """The letterhead says PRIVATE LIMITED, LinkedIn says Pvt Ltd, the resume
    says neither. One notion of "same employer" across all three."""
    a = _assess({"Acme Technologies Pvt Ltd"})
    assert "employer_corroborated_by_profile_source" in _ids(a)


def test_corroboration_is_skipped_when_the_letter_matches_no_resume_employer():
    """A hard failure returns before corroboration is even considered -- there
    is no matched employer to corroborate."""
    a = _assess({"Acme Technologies"}, profile=_profile(employer="Globex Corp"))
    assert "employer_not_claimed" in _ids(a)
    assert "employer_corroborated_by_profile_source" not in _ids(a)


def test_no_corroboration_finding_names_the_employer():
    """Findings stay non-PII: they record that a check ran, not what it saw."""
    for corroborating in ({"Acme Technologies"}, {"Globex Corp"}):
        a = _assess(corroborating)
        blob = " ".join(f.message + str(f.detail) for f in a.findings)
        assert "Acme" not in blob and "Globex" not in blob


def test_the_payslip_path_corroborates_too():
    slip = ("ACME TECHNOLOGIES PRIVATE LIMITED\nPayslip for March 2023\n"
            "Gross Salary: 100000\nTotal Deductions: 22000\nNet Pay: 78000\n")
    a = assess(ParsedDocument(text=slip, page_count=1, digest="d" * 64, metadata={}),
               _profile(), DocumentType.PAYSLIP, at=NOW, metadata_skew_days=1,
               corroborating_employers={"Acme Technologies"})
    assert "employer_corroborated_by_profile_source" in _ids(a)
    assert a.strength is ClaimStrength.DOCUMENTED


def test_corroboration_defaults_to_absent_so_existing_callers_are_unchanged():
    """The parameter is optional: every S7.2 caller keeps its exact behaviour."""
    a = assess_experience_letter(_parsed(), _profile(), at=NOW, metadata_skew_days=1)
    assert "employer_corroborated_by_profile_source" not in _ids(a)
    assert a.strength is ClaimStrength.DOCUMENTED


# ── End to end through the real service ─────────────────────────────────────


def _services_with_linkedin(settings, employers):
    """A candidate with a resume AND a stored LinkedIn profile-source signal."""
    import base64

    from app.candidates.schema import ExtractionResult
    from app.profile_sources.schema import (
        LinkedInActivity, ProfileSourceSignal, ProfileSourceType,
    )
    from tests.conftest import make_services

    services = make_services(settings)
    outcome = services.candidates.ingest(
        ExtractionResult(profile=_profile(), method="heuristic"), "resume text")
    cid = outcome.candidate_id
    if employers is not None:
        services.profile_sources._store.save_signal(
            cid,
            ProfileSourceSignal(
                source_type=ProfileSourceType.LINKEDIN_EXPORT,
                identifier="export.zip",
                activity=LinkedInActivity(employers=list(employers)),
                method="export",
                fetched_at=NOW,
            ),
        )
    return services, cid, base64.b64encode(LETTER.encode()).decode("ascii")


def test_the_service_corroborates_against_a_stored_linkedin_signal(settings):
    services, cid, b64 = _services_with_linkedin(settings, ["Acme Technologies"])
    _, findings, evidence = services.verification.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER, b64, at=NOW)
    ids = {f.id for f in findings}
    assert "employer_corroborated_by_profile_source" in ids
    assert evidence.strength is ClaimStrength.DOCUMENTED   # still not lifted


def test_the_service_reports_absence_when_linkedin_lists_other_employers(settings):
    services, cid, b64 = _services_with_linkedin(settings, ["Globex Corp"])
    _, findings, _ = services.verification.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER, b64, at=NOW)
    assert "employer_absent_from_profile_source" in {f.id for f in findings}


def test_the_service_says_nothing_when_no_profile_source_exists(settings):
    services, cid, b64 = _services_with_linkedin(settings, None)
    _, findings, _ = services.verification.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER, b64, at=NOW)
    ids = {f.id for f in findings}
    assert "employer_corroborated_by_profile_source" not in ids
    assert "employer_absent_from_profile_source" not in ids


def test_a_service_without_profile_sources_still_assesses_documents(settings):
    """The collaborator is optional; document submission must not depend on it."""
    from app.ledger.store import LedgerStore
    from app.verification.service import VerificationService
    from app.verification.store import VerificationStore
    from tests.conftest import make_candidate_store

    from app.candidates.schema import ExtractionResult

    candidates = make_candidate_store()
    ledger = LedgerStore(candidates._session_factory,
                         default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
                         settings=settings)
    service = VerificationService(
        VerificationStore(candidates._session_factory, ledger=ledger, settings=settings),
        candidates, ledger, settings=settings)      # no profile_sources
    cid = candidates.ingest(
        ExtractionResult(profile=_profile(), method="heuristic"), "resume").candidate_id

    import base64
    v, findings, evidence = service.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER,
        base64.b64encode(LETTER.encode()).decode("ascii"), at=NOW)
    assert v.status is VerificationStatus.VERIFIED
    assert evidence.strength is ClaimStrength.DOCUMENTED
    assert "employer_corroborated_by_profile_source" not in {f.id for f in findings}
