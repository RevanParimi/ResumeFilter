from datetime import datetime, timezone

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from tests.conftest import make_candidate_store, set_extraction_created_at

RESUME = "Jane Rao\nSenior ML Engineer\nSkills: Python, Spark\nEmail: jane@example.com\n"


def _ingest(cs):
    return cs.ingest(
        ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
        resume_text=RESUME,
    ).candidate_id


def test_profile_as_of_none_before_first_extraction():
    cs = make_candidate_store()
    cid = _ingest(cs)
    set_extraction_created_at(cs, cid, datetime(2026, 5, 1, tzinfo=timezone.utc))
    assert cs.profile_as_of(cid, datetime(2026, 1, 1, tzinfo=timezone.utc)) is None


def test_profile_as_of_returns_profile_after_extraction():
    cs = make_candidate_store()
    cid = _ingest(cs)
    set_extraction_created_at(cs, cid, datetime(2026, 5, 1, tzinfo=timezone.utc))
    prof = cs.profile_as_of(cid, datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert prof is not None
    assert prof.full_name  # heuristic pulled a name


def test_profile_as_of_unknown_candidate_is_none():
    cs = make_candidate_store()
    assert cs.profile_as_of("nope", datetime(2026, 6, 1, tzinfo=timezone.utc)) is None
