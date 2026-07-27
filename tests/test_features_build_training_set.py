from datetime import datetime, timedelta, timezone

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
from app.features.training import build_training_set
from app.ledger.schema import ConsentPurpose, InterviewOutcome, InterviewStage
from app.ledger.store import LedgerStore
from app.services.report_store import InMemoryReportStore
from tests.conftest import make_candidate_store, set_extraction_created_at

T = datetime(2026, 6, 1, tzinfo=timezone.utc)
G = datetime(2026, 1, 1, tzinfo=timezone.utc)
PRE = T - timedelta(days=30)
POST = T + timedelta(days=30)


def _ingest(cs, name, email):
    resume = f"{name}\nML Engineer\nEmail: {email}\n"
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(resume), method="heuristic"),
                    resume_text=resume).candidate_id
    set_extraction_created_at(cs, cid, datetime(2026, 1, 1, tzinfo=timezone.utc))
    return cid


def _mv(cid, cs, ls, rs, reg, view):
    return materialize_candidate(cid, view=view, registry=reg, as_of=T,
                                 candidate_store=cs, report_store=rs, ledger_store=ls)


def _setup():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), InMemoryReportStore()
    reg = get_feature_registry()
    view = default_view(reg)
    org = ls.create_organization("Org A")
    a = _ingest(cs, "A Dev", "a@example.com")
    b = _ingest(cs, "B Dev", "b@example.com")
    c = _ingest(cs, "C Dev", "c@example.com")
    for cid in (a, b, c):
        ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org.id, now=G)
    # A and B are read-consented (materialization allowed); C is not.
    for cid in (a, b):
        ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ, org_id=org.id, now=G)
    # A: a post-cut HIRED record -> positive label.
    ls.submit_interview_record(org_id=org.id, candidate_id=a, stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=POST)
    # B: only a PRE-cut HIRED record -> censored (must NOT leak as a label).
    ls.submit_interview_record(org_id=org.id, candidate_id=b, stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=PRE)
    # C: a post-cut HIRED record exists, but C is not read-consented -> withheld.
    ls.submit_interview_record(org_id=org.id, candidate_id=c, stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=POST)
    mvs = [_mv(a, cs, ls, rs, reg, view), _mv(b, cs, ls, rs, reg, view), _mv(c, cs, ls, rs, reg, view)]
    return ls, mvs, (a, b, c)


def test_build_training_set_labels_the_mix_correctly():
    ls, mvs, (a, b, c) = _setup()
    examples = build_training_set(mvs, ledger_store=ls)
    by_id = {ex.vector.candidate_id: ex.label for ex in examples}
    # A: consented + post-cut hired.
    assert by_id[a].observed is True and by_id[a].hired is True and by_id[a].withheld is False
    # B: consented but only a pre-cut hired -> censored, not a false positive.
    assert by_id[b].observed is False and by_id[b].hired is None and by_id[b].withheld is False
    # C: withheld -> null label despite an existing post-cut hired record.
    assert by_id[c].withheld is True and by_id[c].hired is None and by_id[c].observed is False


def test_build_training_set_audits_every_join():
    ls, mvs, (a, b, c) = _setup()
    build_training_set(mvs, ledger_store=ls)
    for cid, expected in ((a, True), (b, True), (c, False)):
        joins = [x for x in ls.audit_for_candidate(cid) if x.action == "training.label"]
        assert joins and joins[-1].details.get("allowed") is expected


def test_audit_false_flag_skips_audit_rows():
    ls, mvs, _ = _setup()
    build_training_set(mvs, ledger_store=ls, audit=False)
    assert all(
        not [x for x in ls.audit_for_candidate(ex.vector.candidate_id) if x.action == "training.label"]
        for ex in build_training_set(mvs, ledger_store=ls, audit=False)
    )
