"""S7.2 experience-letter forensics. Conservative by construction: a small
Indian employer with no mail domain is SOFT, never HARD."""

from datetime import datetime, timezone

from app.candidates.schema import CandidateProfile, DateRange, ExperienceEntry
from app.verification.documents import ParsedDocument, assess_experience_letter
from app.verification.schema import ClaimStrength, VerificationStatus

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)

CLEAN = """
ACME TECHNOLOGIES PRIVATE LIMITED
hr@acme.com

TO WHOM IT MAY CONCERN

This is to certify that Ms. A Candidate (Employee ID ACM-4471) was employed
with Acme Technologies as a Senior Software Engineer from March 2021 to
January 2024.

Sincerely,
R. Sharma
Head of Human Resources
"""


def _profile(employer="Acme Technologies", title="Senior Software Engineer",
             start="2021-03", end="2024-01"):
    return CandidateProfile(
        experience=[ExperienceEntry(
            employer=employer, title=title,
            dates=DateRange(start=start, end=end),
        )]
    )


def _parsed(text=CLEAN, metadata=None):
    return ParsedDocument(text=text, page_count=1, digest="d" * 64,
                          metadata=metadata or {})


def _ids(assessment):
    return {f.id for f in assessment.findings}


def test_a_clean_letter_is_documented_and_verified():
    a = assess_experience_letter(_parsed(), _profile(), at=NOW, metadata_skew_days=1)
    assert a.status is VerificationStatus.VERIFIED
    assert a.strength is ClaimStrength.DOCUMENTED
    assert not [f for f in a.findings if f.severity == "hard"]


def test_dates_that_contradict_the_resume_are_a_hard_finding():
    a = assess_experience_letter(
        _parsed(), _profile(start="2018-01", end="2019-01"), at=NOW,
        metadata_skew_days=1,
    )
    assert "letter_dates_mismatch" in _ids(a)
    assert a.status is VerificationStatus.FAILED
    assert a.strength is ClaimStrength.NONE


def test_an_employer_absent_from_the_resume_is_a_hard_finding():
    a = assess_experience_letter(
        _parsed(), _profile(employer="Globex Corp"), at=NOW, metadata_skew_days=1,
    )
    assert "employer_not_claimed" in _ids(a)
    assert a.status is VerificationStatus.FAILED


def test_a_missing_issuer_domain_is_soft_never_hard():
    """Small Indian employers legitimately have no mail domain."""
    text = CLEAN.replace("hr@acme.com", "")
    a = assess_experience_letter(_parsed(text), _profile(), at=NOW, metadata_skew_days=1)
    assert "issuer_domain_unknown" in _ids(a)
    assert all(f.severity != "hard" for f in a.findings)
    assert a.status is VerificationStatus.VERIFIED


def test_a_missing_signatory_and_employee_id_are_mill_markers():
    text = "This certifies employment with Acme Technologies from March 2021 to January 2024."
    a = assess_experience_letter(_parsed(text), _profile(), at=NOW, metadata_skew_days=1)
    assert {"no_signatory", "no_employee_id"} <= _ids(a)


def test_a_designation_that_disagrees_is_soft():
    a = assess_experience_letter(
        _parsed(), _profile(title="Principal Architect"), at=NOW, metadata_skew_days=1,
    )
    assert "designation_mismatch" in _ids(a)
    assert a.status is VerificationStatus.VERIFIED   # titles drift legitimately


def test_metadata_skew_between_creation_and_modification_is_flagged():
    a = assess_experience_letter(
        _parsed(metadata={"created": "D:20240101120000", "modified": "D:20260101120000"}),
        _profile(), at=NOW, metadata_skew_days=1,
    )
    assert "metadata_modified_after_creation" in _ids(a)


def test_identical_creation_and_modification_are_not_flagged():
    a = assess_experience_letter(
        _parsed(metadata={"created": "D:20240101120000", "modified": "D:20240101120000"}),
        _profile(), at=NOW, metadata_skew_days=1,
    )
    assert "metadata_modified_after_creation" not in _ids(a)


def test_no_profile_on_file_means_no_corroboration_not_a_failure():
    a = assess_experience_letter(_parsed(), None, at=NOW, metadata_skew_days=1)
    assert "no_profile_to_compare" in _ids(a)
    assert a.status is VerificationStatus.VERIFIED
    assert a.strength is ClaimStrength.DOCUMENTED


def test_no_finding_ever_carries_document_text():
    a = assess_experience_letter(_parsed(), _profile(employer="Globex Corp"), at=NOW,
                                 metadata_skew_days=1)
    blob = " ".join(f.message + str(f.detail) for f in a.findings)
    assert "R. Sharma" not in blob
    assert "ACM-4471" not in blob


def test_a_canonicalised_employer_still_matches_a_differently_written_letter():
    """S1.4 canonicalization is the point: 'Acme Technologies Private Limited'
    on the letter and 'Acme Technologies' on the resume are the same employer."""
    profile = _profile(employer="Acme Technologies Pvt Ltd")
    a = assess_experience_letter(_parsed(), profile, at=NOW, metadata_skew_days=1)
    assert "employer_not_claimed" not in _ids(a)
