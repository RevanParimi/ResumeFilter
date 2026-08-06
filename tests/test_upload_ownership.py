"""S8.4 Phase A: ownership is a property of the UPLOAD, not the person.

The SET NULL test is the point of this file. An org offboarding must leave the
candidate and their resume intact and merely UNOWNED -- a CASCADE typo would be
silent until the first organization is ever deleted.
"""

from __future__ import annotations

from sqlalchemy import select

from app.candidates.models import ResumeRow
from app.reports.models import ReportRow


def test_resume_and_report_carry_a_nullable_org_id():
    assert ResumeRow.__table__.c.org_id.nullable is True
    assert ReportRow.__table__.c.org_id.nullable is True


def test_org_id_foreign_keys_are_set_null_not_cascade():
    """CASCADE here would delete a person's resume when an org offboards."""
    for table in (ResumeRow.__table__, ReportRow.__table__):
        fk = next(fk for fk in table.c.org_id.foreign_keys)
        assert fk.column.table.name == "organizations"
        assert fk.ondelete == "SET NULL", (
            f"{table.name}.org_id must be SET NULL -- a person's resume does not "
            f"die with the organization that happened to upload it"
        )


def test_deleting_an_org_leaves_the_resume_intact_and_unowned(services):
    """The behaviour the ondelete assertion above is standing in for."""
    from app.candidates.schema import (
        CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult,
    )

    org = services.ledger.create_organization("Acme Staffing")
    outcome = services.candidates.ingest(
        ExtractionResult(
            profile=CandidateProfile(
                full_name=ExtractedStr(value="Priya"),
                contact=ContactInfo(email=ExtractedStr(value="priya@x.io")),
            ),
            method="heuristic",
        ),
        resume_text="priya resume text",
        org_id=org.id,
    )

    with services.candidates._session_factory() as s:
        row = s.get(ResumeRow, outcome.resume_id)
        assert row.org_id == org.id

    # Offboard the organization.
    with services.candidates._session_factory() as s:
        from app.ledger.models import OrganizationRow
        s.delete(s.get(OrganizationRow, org.id))
        s.commit()

    with services.candidates._session_factory() as s:
        row = s.get(ResumeRow, outcome.resume_id)
        assert row is not None, "the person's resume must survive the org"
        assert row.org_id is None, "and must read as unowned"
        assert s.execute(
            select(ResumeRow).where(ResumeRow.candidate_id == outcome.candidate_id)
        ).scalars().first() is not None


def test_report_save_stamps_org_and_keeps_it_out_of_the_body(services):
    from datetime import datetime, timezone
    from app.schemas.report import Report

    org = services.ledger.create_organization("Beta Staffing")
    report = Report(id="rep-1", domain="genai", created_at=datetime.now(timezone.utc))
    services.report_store.save(report, org_id=org.id)

    with services.candidates._session_factory() as s:
        row = s.get(ReportRow, "rep-1")
        assert row.org_id == org.id
        assert "org_id" not in row.body, "ownership is storage, not the report contract"

    assert services.report_store.get("rep-1").model_dump().get("org_id") is None


def test_resaving_without_an_org_does_not_un_own_a_report(services):
    """save() is an upsert; a later save from another path must not orphan it."""
    from datetime import datetime, timezone
    from app.schemas.report import Report

    org = services.ledger.create_organization("Gamma Staffing")
    report = Report(id="rep-2", domain="genai", created_at=datetime.now(timezone.utc))
    services.report_store.save(report, org_id=org.id)
    services.report_store.save(report)  # no org_id supplied

    with services.candidates._session_factory() as s:
        assert s.get(ReportRow, "rep-2").org_id == org.id
