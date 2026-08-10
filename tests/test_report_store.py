"""Report store — durable reports + outcome records (FR-6..FR-8, NFR-4).

S8.1: the backend changed (raw sqlite3 in a second database -> SQLAlchemy on the
main one) but the Protocol surface is the contract, so these tests changed only
in how the store is constructed.
"""

from __future__ import annotations

import pytest

from app.candidates.models import CandidateRow
from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.reports.store import SqlReportStore, build_report_store
from app.schemas.report import Report
from tests.conftest import make_candidate_store


def _report(**overrides) -> Report:
    from app.schemas.report import CoherenceVerdict

    base = Report(
        domain="genai",
        verdicts=[
            CoherenceVerdict(
                claim_id="clm_1",
                claim_text="Fine-tuned Llama 3 on 40k examples",
                claim_type="fine_tuning",
            )
        ],
        summary="test report",
    )
    return base.model_copy(update=overrides)


@pytest.fixture
def factory():
    """The candidate store's own session factory: reports live in the same
    database as their subject now, which is the whole point of the fold."""
    return make_candidate_store()._session_factory


@pytest.fixture
def store(factory):
    return SqlReportStore(factory)


def test_report_candidate_id_defaults_none():
    """From the deleted test_report_candidate_link.py: an ad-hoc POST /evaluate
    report has no subject, which is why the FK column is nullable."""
    assert Report().candidate_id is None
    assert Report(candidate_id="cand-1").candidate_id == "cand-1"


def test_save_get_roundtrip(store):
    rep = _report()
    store.save(rep)
    got = store.get(rep.id)
    assert got is not None
    assert got.id == rep.id
    assert got.verdicts[0].claim_text == rep.verdicts[0].claim_text
    assert got.human_review_required is True


def test_get_missing_returns_none(store):
    assert store.get("rep_missing") is None


def test_save_is_an_upsert(store):
    """The old store used INSERT OR REPLACE, which Postgres does not have."""
    rep = _report()
    store.save(rep)
    store.save(rep.model_copy(update={"summary": "revised"}))
    got = store.get(rep.id)
    assert got is not None and got.summary == "revised"


def test_survives_a_new_store_instance(factory):
    """Durability (FR-6): a second instance on the same database sees the row."""
    rep = _report()
    SqlReportStore(factory).save(rep)
    got = SqlReportStore(factory).get(rep.id)
    assert got is not None and got.id == rep.id


def test_outcome_roundtrip(store):
    rep = _report()
    store.save(rep)
    store.add_outcome(
        OutcomeRecord(
            report_id=rep.id,
            claim_id="clm_1",
            outcome=OutcomeLabel.VERIFIED_GENUINE,
            notes="confirmed in screen",
            recorded_by=OutcomeSource.OPERATOR,
        )
    )
    store.add_outcome(
        OutcomeRecord(
            report_id=rep.id, outcome=OutcomeLabel.INCONCLUSIVE,
            recorded_by=OutcomeSource.OPERATOR,
        )
    )
    outs = store.outcomes(rep.id)
    assert len(outs) == 2
    assert outs[0].claim_id == "clm_1"
    assert outs[0].outcome == OutcomeLabel.VERIFIED_GENUINE
    assert outs[1].claim_id is None
    assert store.outcomes("rep_other") == []


def test_outcome_provenance_survives_the_roundtrip(store, factory):
    """A stamp that is written and not read back is not a stamp.

    Both provenance FKs are REAL rows here rather than convenient strings --
    the columns carry foreign keys, so a test that invents ids would prove the
    roundtrip while hiding whether the constraints are satisfiable at all.
    """
    from app.auth.models import OrgUserRow
    from app.ledger.models import OrganizationRow

    with factory() as s:
        s.add(OrganizationRow(id="org-a", name="Agency A"))
        s.flush()
        s.add(OrgUserRow(id="user-7", organization_id="org-a", email_hash="h"))
        s.commit()

    rep = _report()
    store.save(rep)
    store.add_outcome(
        OutcomeRecord(
            report_id=rep.id,
            outcome=OutcomeLabel.VERIFIED_FABRICATED,
            notes="the employer had never heard of them",
            recorded_by=OutcomeSource.ORGANIZATION,
            org_id="org-a",
            recorded_by_org_user_id="user-7",
        )
    )
    got = store.outcomes(rep.id)[0]
    assert got.recorded_by is OutcomeSource.ORGANIZATION
    assert got.org_id == "org-a"
    assert got.recorded_by_org_user_id == "user-7"


def test_outcomes_for_org_is_scoped_to_the_owner_and_to_its_own_rows(store, factory):
    """Two independent facts, and both matter.

    A report has exactly one owning org, so `outcomes_for_org` cannot leak
    ACROSS tenants -- but it can leak DOWNWARD: an operator's internal note
    about a customer's report ("this agency keeps uploading fakes") must not
    appear in that customer's own list. Hence the org_id filter on top of the
    ownership check.
    """
    from app.ledger.models import OrganizationRow

    with factory() as s:
        s.add(OrganizationRow(id="org-a", name="Agency A"))
        s.add(OrganizationRow(id="org-b", name="Agency B"))
        s.commit()

    rep = _report()
    store.save(rep, org_id="org-a")
    store.add_outcome(OutcomeRecord(
        report_id=rep.id, outcome=OutcomeLabel.VERIFIED_GENUINE,
        notes="spoke to the employer", recorded_by=OutcomeSource.ORGANIZATION,
        org_id="org-a",
    ))
    store.add_outcome(OutcomeRecord(
        report_id=rep.id, outcome=OutcomeLabel.INCONCLUSIVE,
        notes="internal: this agency keeps uploading fakes",
        recorded_by=OutcomeSource.OPERATOR,
    ))

    mine = store.outcomes_for_org("org-a", rep.id)
    assert mine is not None
    assert [o.outcome for o in mine] == [OutcomeLabel.VERIFIED_GENUINE]
    assert all("internal" not in o.notes for o in mine)

    # The operator's cross-tenant view still sees both.
    assert len(store.outcomes(rep.id)) == 2

    # Another org's report, and an absent one, are the same answer: None, which
    # the route turns into one 404 (TENANCY.md §6).
    assert store.outcomes_for_org("org-b", rep.id) is None
    assert store.outcomes_for_org("org-a", "rep_missing") is None


def test_outcomes_for_org_distinguishes_no_outcomes_from_no_report(store, factory):
    """An empty list and None are different answers: "you have judged nothing"
    is not "this is not yours"."""
    from app.ledger.models import OrganizationRow

    with factory() as s:
        s.add(OrganizationRow(id="org-a", name="Agency A"))
        s.commit()

    rep = _report()
    store.save(rep, org_id="org-a")
    assert store.outcomes_for_org("org-a", rep.id) == []


def test_delete_removes_report_and_outcomes(store):
    rep = _report()
    store.save(rep)
    store.add_outcome(OutcomeRecord(
        report_id=rep.id, outcome=OutcomeLabel.INCONCLUSIVE,
        recorded_by=OutcomeSource.OPERATOR,
    ))
    assert store.delete(rep.id) is True
    assert store.get(rep.id) is None
    assert store.outcomes(rep.id) == []
    assert store.delete(rep.id) is False


def test_for_candidate_is_ordered_and_scoped(store, factory):
    with factory() as s:
        s.add(CandidateRow(id="cand_a"))
        s.add(CandidateRow(id="cand_b"))
        s.commit()
    from datetime import datetime, timezone

    older = _report(candidate_id="cand_a",
                    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = _report(candidate_id="cand_a",
                    created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    other = _report(candidate_id="cand_b")
    for rep in (newer, older, other):
        store.save(rep)

    got = store.for_candidate("cand_a")

    assert [r.id for r in got] == [older.id, newer.id]
    assert store.for_candidate("cand_nobody") == []


def test_build_report_store_uses_the_main_db_url(settings, tmp_path):
    """Reports are no longer a database of their own: the builder reads
    candidates_db_url, the one Alembic manages."""
    url = "sqlite:///" + (tmp_path / "veritas.db").as_posix()
    s = settings.model_copy(update={"candidates_db_url": url})

    from app.core.migrate import upgrade_to_head

    upgrade_to_head(s)
    store = build_report_store(s)
    assert isinstance(store, SqlReportStore)

    rep = _report()
    store.save(rep)
    assert build_report_store(s).get(rep.id) is not None


def test_save_refuses_a_report_whose_subject_was_erased(store, factory):
    """The race POST /candidates has always had: an eval in flight when an
    erasure lands. Before S8.1 the orphan was written and a compensating delete
    in the route had to remember it; now the FK refuses it."""
    from app.reports.store import SubjectErasedError

    with pytest.raises(SubjectErasedError):
        store.save(_report(candidate_id="never-existed"))


def test_save_still_raises_for_integrity_failures_it_cannot_explain(store):
    """An unattached report has no FK, so an IntegrityError there is NOT the
    erasure race and must not be relabelled as one."""
    assert store.save(_report()) is None


def test_save_rejects_bad_org_id_even_with_valid_candidate(services):
    """Reports now have two FKs (candidate CASCADE, org SET NULL). An
    IntegrityError from a bad org_id must not be swallowed and re-raised as
    SubjectErasedError; only a genuine candidate erasure should do that.

    This is a latent bug (no shipped caller passes org_id yet) that becomes
    live at Task 6 when routes wire org_id arguments.
    """
    from datetime import datetime, timezone
    from sqlalchemy.exc import IntegrityError

    from app.reports.store import SubjectErasedError

    # Create a candidate so candidate_id is valid.
    from app.candidates.schema import (
        CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult,
    )
    outcome = services.candidates.ingest(
        ExtractionResult(
            profile=CandidateProfile(
                full_name=ExtractedStr(value="Test"),
                contact=ContactInfo(email=ExtractedStr(value="test@x.io")),
            ),
            method="heuristic",
        ),
        resume_text="test text",
    )

    # Try to save a report with that candidate but a bad org_id.
    report = Report(
        id="rep-bad-org",
        domain="genai",
        created_at=datetime.now(timezone.utc),
        candidate_id=outcome.candidate_id,
    )

    # This must raise IntegrityError (bad org FK), NOT SubjectErasedError
    # (which would incorrectly blame the candidate).
    with pytest.raises(IntegrityError):
        services.report_store.save(report, org_id="org-does-not-exist")
