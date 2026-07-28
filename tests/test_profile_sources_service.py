import pytest

from app.candidates.models import CandidateRow
from app.candidates.schema import (
    CandidateProfile, ExtractionResult, LinkItem, LinkType,
)
from app.core.config import Settings
from app.profile_sources.service import ProfileSourceService
from app.profile_sources.store import ProfileSourceStore
from app.services.github import GitHubUserRaw
from tests.conftest import FakeGitHub, make_candidate_store


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def _service(cs, github=None):
    return ProfileSourceService(
        github=github or FakeGitHub(),
        store=ProfileSourceStore(cs._session_factory),
        candidates=cs,
        settings=_settings(),
    )


def _bare_candidate(cs) -> str:
    with cs._session_factory() as s:
        row = CandidateRow(full_name="Test")
        s.add(row)
        s.commit()
        return row.id


@pytest.mark.asyncio
async def test_ingest_with_explicit_handle_persists_signal():
    cs = make_candidate_store()
    gh = FakeGitHub()
    svc = _service(cs, gh)
    cid = _bare_candidate(cs)
    sig = await svc.ingest_github(cid, handle="octocat")
    assert sig.method == "api"
    assert sig.identifier == "octocat"
    assert gh.user_calls == ["octocat"]
    assert svc.list_sources(cid)[0].identifier == "octocat"


@pytest.mark.asyncio
async def test_handle_derived_from_profile_github_link():
    cs = make_candidate_store()
    profile = CandidateProfile(links=[LinkItem(type=LinkType.GITHUB, url="https://github.com/torvalds")])
    outcome = cs.ingest(ExtractionResult(profile=profile, method="heuristic"), "resume text about linux")
    cid = outcome.candidate_id
    gh = FakeGitHub()
    sig = await _service(cs, gh).ingest_github(cid)  # no explicit handle
    assert gh.user_calls == ["torvalds"]
    assert sig.identifier == "torvalds"


@pytest.mark.asyncio
async def test_no_handle_and_no_link_raises_value_error():
    cs = make_candidate_store()
    cid = _bare_candidate(cs)
    with pytest.raises(ValueError):
        await _service(cs).ingest_github(cid)


@pytest.mark.asyncio
async def test_unknown_candidate_raises_lookup_error():
    cs = make_candidate_store()
    with pytest.raises(LookupError):
        await _service(cs).ingest_github("does-not-exist", handle="octocat")


@pytest.mark.asyncio
async def test_unavailable_fetch_still_persists_unavailable_signal():
    cs = make_candidate_store()
    gh = FakeGitHub(user_signals={"ghost": GitHubUserRaw(login="ghost", available=False, warnings=["not found"])})
    svc = _service(cs, gh)
    cid = _bare_candidate(cs)
    sig = await svc.ingest_github(cid, handle="ghost")
    assert sig.method == "unavailable"
    assert svc.list_sources(cid)[0].method == "unavailable"
