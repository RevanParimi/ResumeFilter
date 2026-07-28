from datetime import datetime, timezone

from app.candidates.models import CandidateRow
from app.profile_sources.schema import (
    GitHubActivity, ProfileSourceSignal, ProfileSourceType, SourceSkillSignal,
)
from app.profile_sources.store import ProfileSourceStore
from tests.conftest import make_candidate_store

FETCHED = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _candidate(cs) -> str:
    with cs._session_factory() as s:
        row = CandidateRow(full_name="Test")
        s.add(row)
        s.commit()
        return row.id


def _sig(identifier="octocat"):
    return ProfileSourceSignal(
        source_type=ProfileSourceType.GITHUB, identifier=identifier,
        skills=[SourceSkillSignal(name="Python", canonical="python", category="language", weight=10000, confidence=0.9)],
        activity=GitHubActivity(public_repos=2, total_stars=4, sampled_repos=2),
        method="api", fetched_at=FETCHED,
    )


def test_save_and_list_newest_first():
    cs = make_candidate_store()
    store = ProfileSourceStore(cs._session_factory)
    cid = _candidate(cs)
    store.save_signal(cid, _sig("first"))
    store.save_signal(cid, _sig("second"))
    sigs = store.signals_for_candidate(cid)
    assert len(sigs) == 2
    assert sigs[0].identifier == "second"  # newest first
    assert sigs[0].skills[0].canonical == "python"


def test_latest_for_source_and_type_filter():
    cs = make_candidate_store()
    store = ProfileSourceStore(cs._session_factory)
    cid = _candidate(cs)
    store.save_signal(cid, _sig("only"))
    latest = store.latest_for_source(cid, ProfileSourceType.GITHUB)
    assert latest is not None and latest.identifier == "only"
    assert store.signals_for_candidate(cid, ProfileSourceType.GITHUB)[0].identifier == "only"


def test_cascade_erasure_sweeps_profile_sources():
    cs = make_candidate_store()
    store = ProfileSourceStore(cs._session_factory)
    cid = _candidate(cs)
    store.save_signal(cid, _sig())
    assert store.signals_for_candidate(cid) != []
    assert cs.delete_candidate(cid) is True
    assert store.signals_for_candidate(cid) == []  # CASCADE swept it
