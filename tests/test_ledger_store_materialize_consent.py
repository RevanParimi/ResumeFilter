from datetime import datetime, timezone

import pytest

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.ledger.schema import ConsentPurpose
from app.ledger.store import LedgerStore
from tests.conftest import make_candidate_store

RESUME = "Jane Rao\nML Engineer\nSkills: Python\nEmail: jane@example.com\n"
AT = datetime(2026, 6, 1, tzinfo=timezone.utc)
G = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _setup():
    cs = make_candidate_store()
    ls = LedgerStore(cs._session_factory)
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
                    resume_text=RESUME).candidate_id
    return cs, ls, cid


def test_allowed_with_active_read_grant():
    cs, ls, cid = _setup()
    org = ls.create_organization("Org A")
    ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ, org_id=org.id, now=G)
    d = ls.materialization_consent(cid, at=AT)
    assert d.allowed and d.grant_id
    audits = [a for a in ls.audit_for_candidate(cid) if a.action == "feature.materialize"]
    assert audits and audits[-1].details.get("allowed") is True


def test_withheld_without_grant_does_not_raise():
    cs, ls, cid = _setup()
    d = ls.materialization_consent(cid, at=AT)
    assert not d.allowed
    audits = [a for a in ls.audit_for_candidate(cid) if a.action == "feature.materialize"]
    assert audits and audits[-1].details.get("allowed") is False


def test_unknown_candidate_raises():
    cs, ls, cid = _setup()
    with pytest.raises(LookupError):
        ls.materialization_consent("nope", at=AT)
