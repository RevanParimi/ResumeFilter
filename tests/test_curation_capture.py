from app.candidates.normalize.skills import clear_curated_overlay
from app.curation.schema import CurationStatus
from tests.conftest import make_services


def teardown_function():
    clear_curated_overlay()


def _candidate(services) -> str:
    from app.candidates.models import CandidateRow
    with services.candidates._session_factory() as s:
        row = CandidateRow(full_name="Cap")
        s.add(row)
        s.commit()
        return row.id


async def test_github_ingest_captures_unmapped_skill(settings, fake_github):
    # FakeGitHub default user signal reports language "Python" (maps) — inject an
    # unknown language so an unmapped skill flows to the queue.
    from app.services.github import GitHubRepoRaw, GitHubUserRaw
    from tests.conftest import FakeGitHub
    gh = FakeGitHub(user_signals={"dev": GitHubUserRaw(
        login="dev", available=True, public_repos=1, followers=0,
        repos=[GitHubRepoRaw(name="r", language="Cobol", languages={"Cobol": 5000},
                             stargazers_count=1, pushed_at="2025-01-01T00:00:00Z")],
    )})
    services = make_services(settings, github=gh)
    cid = _candidate(services)
    await services.profile_sources.ingest_github(cid, handle="dev")
    pending = services.curation.list_unmapped(CurationStatus.PENDING)
    assert any(t.norm_key == "cobol" and "github" in t.source_types for t in pending)


async def test_fully_mapped_signal_queues_nothing(settings):
    from app.services.github import GitHubRepoRaw, GitHubUserRaw
    from tests.conftest import FakeGitHub
    gh = FakeGitHub(user_signals={"dev": GitHubUserRaw(
        login="dev", available=True, public_repos=1, followers=0,
        repos=[GitHubRepoRaw(name="r", language="Python", languages={"Python": 5000},
                             stargazers_count=1, pushed_at="2025-01-01T00:00:00Z")],
    )})
    services = make_services(settings, github=gh)
    cid = _candidate(services)
    await services.profile_sources.ingest_github(cid, handle="dev")
    assert services.curation.list_unmapped(CurationStatus.PENDING) == []


async def test_capture_failure_does_not_break_ingest(settings):
    # Inject an UNMAPPED language so _capture_unmapped actually calls record_unmapped
    # (the default FakeGitHub reports "Python", which maps and would never capture).
    from app.services.github import GitHubRepoRaw, GitHubUserRaw
    from tests.conftest import FakeGitHub
    gh = FakeGitHub(user_signals={"dev": GitHubUserRaw(
        login="dev", available=True, public_repos=1, followers=0,
        repos=[GitHubRepoRaw(name="r", language="Cobol", languages={"Cobol": 5000},
                             stargazers_count=1, pushed_at="2025-01-01T00:00:00Z")],
    )})
    services = make_services(settings, github=gh)

    class Boom:
        def record_unmapped(self, *a, **k):
            raise RuntimeError("boom")

    services.profile_sources._curation = Boom()
    cid = _candidate(services)
    sig = await services.profile_sources.ingest_github(cid, handle="dev")
    assert sig is not None  # ingestion still succeeds despite capture blowing up
    assert any(s.canonical is None for s in sig.skills)  # capture path was exercised
