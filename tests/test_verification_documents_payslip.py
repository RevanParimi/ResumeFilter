"""S7.2 payslip forensics. The arithmetic is the signal; the AMOUNTS are not
kept -- comp has its own consented path (S5.2) and this is not a back door."""

from datetime import datetime, timezone

from app.candidates.schema import CandidateProfile, DateRange, ExperienceEntry
from app.verification.documents import ParsedDocument, assess, assess_payslip
from app.verification.schema import (
    ClaimStrength, DocumentType, VerificationStatus,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)

CONSISTENT = """
ACME TECHNOLOGIES PRIVATE LIMITED
Payslip for March 2023
Employee: A Candidate     UAN: 100234567890
Gross Salary: 100000
Total Deductions: 22000
Net Pay: 78000
"""

INCONSISTENT = CONSISTENT.replace("Net Pay: 78000", "Net Pay: 95000")


def _profile(employer="Acme Technologies", start="2021-03", end="2024-01"):
    return CandidateProfile(experience=[ExperienceEntry(
        employer=employer, title="Engineer", dates=DateRange(start=start, end=end))])


def _parsed(text=CONSISTENT):
    return ParsedDocument(text=text, page_count=1, digest="d" * 64, metadata={})


def _ids(a):
    return {f.id for f in a.findings}


def test_a_consistent_payslip_is_documented():
    a = assess_payslip(_parsed(), _profile(), at=NOW, metadata_skew_days=1)
    assert a.status is VerificationStatus.VERIFIED
    assert a.strength is ClaimStrength.DOCUMENTED


def test_arithmetic_that_does_not_add_up_is_hard():
    a = assess_payslip(_parsed(INCONSISTENT), _profile(), at=NOW, metadata_skew_days=1)
    assert "payslip_arithmetic_mismatch" in _ids(a)
    assert a.status is VerificationStatus.FAILED
    assert a.strength is ClaimStrength.NONE


def test_an_employer_absent_from_the_resume_is_hard():
    a = assess_payslip(_parsed(), _profile(employer="Globex Corp"), at=NOW,
                       metadata_skew_days=1)
    assert "employer_not_claimed" in _ids(a)
    assert a.status is VerificationStatus.FAILED


def test_a_pay_period_outside_the_claimed_role_is_hard():
    a = assess_payslip(_parsed(), _profile(start="2015-01", end="2016-01"), at=NOW,
                       metadata_skew_days=1)
    assert "payslip_period_outside_role" in _ids(a)
    assert a.status is VerificationStatus.FAILED


def test_uan_presence_is_recorded_but_the_number_never_is():
    a = assess_payslip(_parsed(), _profile(), at=NOW, metadata_skew_days=1)
    assert "uan_present" in _ids(a)
    blob = " ".join(f.message + str(f.detail) for f in a.findings)
    assert "100234567890" not in blob


def test_no_finding_carries_a_salary_amount():
    """Comp intelligence is consented and k-anonymised (S5.2). A payslip must
    not become a back door into it."""
    for text in (CONSISTENT, INCONSISTENT):
        a = assess_payslip(_parsed(text), _profile(), at=NOW, metadata_skew_days=1)
        blob = " ".join(f.message + str(f.detail) for f in a.findings)
        for amount in ("100000", "78000", "95000", "22000"):
            assert amount not in blob


def test_a_payslip_with_no_recognisable_amounts_is_soft_not_hard():
    a = assess_payslip(_parsed("Payslip for March 2023\nAcme Technologies"),
                       _profile(), at=NOW, metadata_skew_days=1)
    assert "payslip_amounts_unreadable" in _ids(a)
    assert a.status is VerificationStatus.VERIFIED


def test_the_dispatcher_routes_by_document_type():
    letter = assess(_parsed("Employed with Acme Technologies from March 2021 to "
                            "January 2024. Head of Human Resources."),
                    _profile(), DocumentType.EXPERIENCE_LETTER, at=NOW,
                    metadata_skew_days=1)
    slip = assess(_parsed(), _profile(), DocumentType.PAYSLIP, at=NOW,
                  metadata_skew_days=1)
    assert letter.status is VerificationStatus.VERIFIED
    assert "uan_present" in _ids(slip)          # only the payslip path checks UAN


def test_amounts_with_separators_and_a_rupee_symbol_still_reconcile():
    """Indian payslips write 1,00,000 and prefix Rs./INR. A formatting quirk
    must not read as a discrepancy."""
    text = CONSISTENT.replace("Gross Salary: 100000", "Gross Salary: Rs. 1,00,000") \
                     .replace("Total Deductions: 22000", "Total Deductions: INR 22,000") \
                     .replace("Net Pay: 78000", "Net Pay: 78,000")
    a = assess_payslip(_parsed(text), _profile(), at=NOW, metadata_skew_days=1)
    assert "payslip_arithmetic_mismatch" not in _ids(a)
    assert a.status is VerificationStatus.VERIFIED
