from datetime import datetime, timezone
from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.features.context import build_context
from app.schemas.report import DepthBand, Report
from app.services.report_store import InMemoryReportStore
from tests.conftest import make_candidate_store, set_extraction_created_at
from app.ledger.store import LedgerStore
from app.ledger.schema import ConsentPurpose, InterviewStage, InterviewOutcome

RESUME = "Jane Rao\nSenior ML Engineer\nSkills: Python, Spark\nEmail: jane@example.com\n"


def _stores():
    cs = make_candidate_store()
    ls = LedgerStore(cs._session_factory)
    rs = InMemoryReportStore()
    return cs, ls, rs


def test_build_context_unknown_candidate_returns_none():
    cs, ls, rs = _stores()
    assert build_context("nope", candidate_store=cs, report_store=rs, ledger_store=ls) is None


def test_build_context_assembles_profile_report_and_ledger():
    cs, ls, rs = _stores()
    result = ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic")
    cid = cs.ingest(result, resume_text=RESUME).candidate_id
    # Pin created_at so the build_context `created_at <= as_of` cutoff includes it
    # (a default real-time created_at would sort after a fixed 2026-06-01 as_of).
    # The extraction is stamped wall-clock-now by ingest; pin it before the cutoff
    # too, else profile_as_of (S4.2) excludes it and ctx.profile is None.
    set_extraction_created_at(cs, cid, datetime(2026, 1, 1, tzinfo=timezone.utc))
    rs.save(Report(candidate_id=cid, depth_score=0.6, depth_band=DepthBand.SOLID,
                   created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    org = ls.create_organization("Org A")
    ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org.id, now=now)
    ls.submit_interview_record(
        org_id=org.id, candidate_id=cid, stage=InterviewStage.HM,
        outcome=InterviewOutcome.HIRED, interviewed_at=now, now=now,
    )

    ctx = build_context(cid, candidate_store=cs, report_store=rs, ledger_store=ls,
                        as_of=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert ctx is not None
    assert ctx.profile is not None and ctx.report is not None
    assert ctx.report.depth_score == 0.6
    assert len(ctx.interview_records) == 1


def test_build_context_respects_as_of_cutoff():
    cs, ls, rs = _stores()
    result = ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic")
    cid = cs.ingest(result, resume_text=RESUME).candidate_id
    org = ls.create_organization("Org A")
    later = datetime(2026, 5, 1, tzinfo=timezone.utc)
    ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org.id, now=later)
    ls.submit_interview_record(
        org_id=org.id, candidate_id=cid, stage=InterviewStage.HM,
        outcome=InterviewOutcome.HIRED, interviewed_at=later, now=later,
    )
    ctx = build_context(cid, candidate_store=cs, report_store=rs, ledger_store=ls,
                        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert ctx is not None and len(ctx.interview_records) == 0   # record is after as_of


def test_build_context_profile_is_point_in_time():
    cs, ls, rs = _stores()
    result = ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic")
    cid = cs.ingest(result, resume_text=RESUME).candidate_id
    set_extraction_created_at(cs, cid, datetime(2026, 5, 1, tzinfo=timezone.utc))

    early = build_context(cid, candidate_store=cs, report_store=rs, ledger_store=ls,
                          as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert early is not None and early.profile is None      # before the extraction existed

    late = build_context(cid, candidate_store=cs, report_store=rs, ledger_store=ls,
                         as_of=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert late.profile is not None
