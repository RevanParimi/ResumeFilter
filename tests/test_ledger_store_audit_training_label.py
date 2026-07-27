from datetime import datetime, timezone

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.ledger.store import LedgerStore
from tests.conftest import make_candidate_store

RESUME = "Jane Rao\nML Engineer\nEmail: jane@example.com\n"
T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _setup():
    cs = make_candidate_store()
    ls = LedgerStore(cs._session_factory)
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
                    resume_text=RESUME).candidate_id
    return ls, cid


def test_audit_training_label_allowed_writes_row():
    ls, cid = _setup()
    ls.audit_training_label(cid, allowed=True, as_of=T)
    audits = [a for a in ls.audit_for_candidate(cid) if a.action == "training.label"]
    assert len(audits) == 1
    assert audits[-1].details.get("allowed") is True
    assert audits[-1].details.get("as_of", "").startswith("2026-06-01")
    assert audits[-1].actor_type == "system" and audits[-1].candidate_id == cid


def test_audit_training_label_withheld_writes_row_and_does_not_raise():
    ls, cid = _setup()
    ls.audit_training_label(cid, allowed=False, as_of=T)
    audits = [a for a in ls.audit_for_candidate(cid) if a.action == "training.label"]
    assert len(audits) == 1 and audits[-1].details.get("allowed") is False
