"""S8.4 Phase A: ownership is a property of the UPLOAD, not the person.

The SET NULL test is the point of this file. An org offboarding must leave the
candidate and their resume intact and merely UNOWNED -- a CASCADE typo would be
silent until the first organization is ever deleted.
"""

from __future__ import annotations

from sqlalchemy import select

from app.candidates import hashing
from app.candidates.models import ResumeRow
from app.candidates.schema import (
    CandidateProfile,
    ContactInfo,
    ExtractedStr,
    ExtractionResult,
)
from app.reports.models import ReportRow

SALT = "upload-ownership-salt"


def _extraction(*, email: str, name: str = "Priya") -> ExtractionResult:
    """A hashed extraction, so identity resolution can actually dedup.

    The hashes are what ``_resolve_candidate`` matches on -- an extraction
    without them forks a new candidate every time and any dedup assertion
    built on it is inert.
    """
    profile = CandidateProfile(
        full_name=ExtractedStr(value=name),
        contact=ContactInfo(email=ExtractedStr(value=email)),
    )
    hashing.apply_contact_hashes(profile, salt=SALT)
    return ExtractionResult(profile=profile, method="heuristic")


def _resume_rows(services, candidate_id: str) -> list[ResumeRow]:
    with services.candidates._session_factory() as s:
        return list(
            s.execute(
                select(ResumeRow)
                .where(ResumeRow.candidate_id == candidate_id)
                .order_by(ResumeRow.version)
            ).scalars().all()
        )


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


# ── Each agency owns its OWN upload, even of identical text ─────────────────
# Spec §0.1: "a candidate uploaded by both agencies appears in BOTH queues from
# ONE candidate row, because EACH AGENCY OWNS ITS OWN UPLOAD of her." Two
# agencies handed the same PDF for the same person is the most likely real
# input this product sees. A single-valued resumes.org_id cannot represent two
# owners of one row, so identical text from a DIFFERENT org gets its own row.


def test_two_orgs_uploading_identical_text_each_own_their_upload(services):
    """One candidate, two resume rows, two owners -- neither invisible."""
    a = services.ledger.create_organization("Agency A")
    b = services.ledger.create_organization("Agency B")
    text = "priya nair -- genai engineer -- identical bytes"

    first = services.candidates.ingest(
        _extraction(email="priya@x.io"), text, org_id=a.id
    )
    second = services.candidates.ingest(
        _extraction(email="priya@x.io"), text, org_id=b.id
    )

    assert second.candidate_id == first.candidate_id, "one person, one candidate row"
    assert second.duplicate_resume is True, (
        "the sha matched -- duplicate_resume is a fact about the TEXT, and stays "
        "true whichever row the upload lands on"
    )
    assert second.resume_id != first.resume_id, (
        "org B's upload must be its OWN row: one org_id column cannot hold two owners"
    )
    assert services.candidates.org_owns_candidate(a.id, first.candidate_id) is True
    assert services.candidates.org_owns_candidate(b.id, first.candidate_id) is True, (
        "org B just uploaded this person and must see her in its own queue"
    )

    rows = _resume_rows(services, first.candidate_id)
    assert [r.org_id for r in rows] == [a.id, b.id]
    assert {r.text_sha256 for r in rows} == {rows[0].text_sha256}, (
        "both rows carry the same text -- the dedup signal is preserved"
    )


def test_an_org_uploading_after_an_admin_does_not_steal_the_admin_row(services):
    """An unowned admin upload stays unowned; the org gets its own owned row."""
    org = services.ledger.create_organization("Agency A")
    text = "deepak kulkarni -- backend -- identical bytes"

    admin_out = services.candidates.ingest(_extraction(email="deepak@x.io"), text)
    org_out = services.candidates.ingest(
        _extraction(email="deepak@x.io"), text, org_id=org.id
    )

    assert org_out.candidate_id == admin_out.candidate_id
    assert org_out.duplicate_resume is True
    assert org_out.resume_id != admin_out.resume_id

    rows = {r.id: r.org_id for r in _resume_rows(services, admin_out.candidate_id)}
    assert rows[admin_out.resume_id] is None, "the admin's upload stays unowned"
    assert rows[org_out.resume_id] == org.id
    assert services.candidates.org_owns_candidate(org.id, org_out.candidate_id) is True


def test_the_same_org_re_uploading_its_own_text_reuses_its_row(services):
    """Idempotency pin: same owner, same text -> the SAME row, no version bump."""
    org = services.ledger.create_organization("Agency A")
    text = "asha rao -- identical bytes"

    first = services.candidates.ingest(
        _extraction(email="asha@x.io"), text, org_id=org.id
    )
    again = services.candidates.ingest(
        _extraction(email="asha@x.io"), text, org_id=org.id
    )

    assert again.resume_id == first.resume_id
    assert again.resume_version == first.resume_version == 1
    assert again.duplicate_resume is True
    assert len(_resume_rows(services, first.candidate_id)) == 1


def test_an_admin_re_uploading_identical_text_still_reuses_the_row(services):
    """The admin path (org_id=None) is byte-identical to pre-S8.4 behaviour:
    a None owner never diverges, it reuses whatever row is already there."""
    text = "unowned -- identical bytes"
    first = services.candidates.ingest(_extraction(email="nobody@x.io"), text)
    again = services.candidates.ingest(_extraction(email="nobody@x.io"), text)

    assert again.resume_id == first.resume_id
    assert again.resume_version == 1
    assert again.duplicate_resume is True
    assert len(_resume_rows(services, first.candidate_id)) == 1
