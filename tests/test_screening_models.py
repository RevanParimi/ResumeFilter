"""S8.4 Phase B: the batch tables, and the three ondelete decisions.

The SET NULL assertions are the point. A candidate erasing themselves must not
delete an organisation's record of what it screened -- and a CASCADE typo on
any of the three subject pointers would do exactly that, silently, until the
first erasure.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.screening.models import BatchItemRow, ScreeningBatchRow


def test_batch_org_id_cascades():
    """A batch is the ORG's work product -- unlike a resume, it has no meaning
    once the org is gone."""
    fk = next(iter(ScreeningBatchRow.__table__.c.org_id.foreign_keys))
    assert fk.column.table.name == "organizations"
    assert fk.ondelete == "CASCADE"
    assert ScreeningBatchRow.__table__.c.org_id.nullable is False


def test_batch_creator_is_set_null():
    """An org user leaving must not delete the batch they registered."""
    fk = next(iter(ScreeningBatchRow.__table__.c.created_by_org_user_id.foreign_keys))
    assert fk.column.table.name == "org_users"
    assert fk.ondelete == "SET NULL"
    assert ScreeningBatchRow.__table__.c.created_by_org_user_id.nullable is True


def test_the_three_subject_pointers_are_set_null_not_cascade():
    for col in ("candidate_id", "resume_id", "report_id"):
        c = BatchItemRow.__table__.c[col]
        fk = next(iter(c.foreign_keys))
        assert c.nullable is True, f"{col} must be nullable"
        assert fk.ondelete == "SET NULL", (
            f"batch_items.{col} must be SET NULL -- a candidate's erasure must "
            f"not rewrite the org's record of how many resumes it screened"
        )


def test_items_cascade_from_their_batch():
    fk = next(iter(BatchItemRow.__table__.c.batch_id.foreign_keys))
    assert fk.ondelete == "CASCADE"


def test_text_sha256_is_indexed_but_not_unique():
    """Phase A made a per-org resume row, so one sha can legitimately appear on
    several items -- and an org may hold two copies of one CV."""
    col = BatchItemRow.__table__.c.text_sha256
    assert col.index is True
    assert col.unique in (False, None)


def test_erasing_a_candidate_leaves_the_item_with_a_null_pointer(services):
    """The behaviour the ondelete assertions stand in for, end to end."""
    from app.candidates.schema import (
        CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult,
    )

    org = services.ledger.create_organization("Acme Staffing")
    outcome = services.candidates.ingest(
        ExtractionResult(
            profile=CandidateProfile(
                full_name=ExtractedStr(value="Priya"),
                contact=ContactInfo(email=ExtractedStr(value="priya@example.in")),
            ),
            method="heuristic",
        ),
        "Priya Nair\nEmail: priya@example.in\nEXPERIENCE\n- Engineer, Acme\n",
        org_id=org.id,
    )

    sf = services.candidates._session_factory
    with sf() as s:
        batch = ScreeningBatchRow(org_id=org.id, name="Q3 intake", domain="genai")
        s.add(batch)
        s.flush()
        s.add(BatchItemRow(
            batch_id=batch.id, status="done", raw_text="", text_sha256="a" * 64,
            candidate_id=outcome.candidate_id, resume_id=outcome.resume_id,
            created_at=datetime.now(timezone.utc),
        ))
        s.commit()
        batch_id = batch.id

    assert services.candidates.delete_candidate(outcome.candidate_id) is True

    with sf() as s:
        item = s.execute(
            select(BatchItemRow).where(BatchItemRow.batch_id == batch_id)
        ).scalars().one()
        assert item.candidate_id is None and item.resume_id is None
        assert item.status == "done", "the org's record of the screening survives"


def test_deleting_an_org_takes_its_batches_with_it(services):
    org = services.ledger.create_organization("Acme Staffing")
    sf = services.candidates._session_factory
    with sf() as s:
        batch = ScreeningBatchRow(org_id=org.id, name="x", domain="genai")
        s.add(batch)
        s.commit()

    assert services.ledger.delete_organization(org.id) is True

    with sf() as s:
        assert s.execute(select(ScreeningBatchRow)).scalars().all() == []
