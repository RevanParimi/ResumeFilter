# S6.1 — GitHub-as-signal (profile-source ingestion) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a candidate-supplied GitHub handle into a structured, normalized,
provenanced skill + activity signal stored as a peer of resume extractions —
advisory, deterministic, DPDP-clean — on a reusable `profile_sources` spine.

**Architecture:** A new pure package `app/profile_sources/` (contracts → pure
`to_signal` transform → store → service) plus a live-fetch extension to the
existing `app/services/github.py`. Persistence is a new `profile_sources` table
on the candidates DB (CASCADE on candidate). Two endpoints on the existing admin
router. The only network is the GitHub fetch, which degrades gracefully; the
transform is pure and offline-tested.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy + Alembic (SQLite,
Postgres-shaped), FastAPI, httpx, pytest.

## Global Constraints

- **Advisory only.** The signal is evidence, never a score/gate. Depth-eval
  scoring and verdicts are untouched. `ProfileSourceSignal.advisory` is always `True`.
- **Deterministic, no LLM.** The raw→signal transform is pure Python. No API key
  required for the transform; the GitHub fetch degrades to `method="unavailable"`.
- **DPDP: first-party only.** Public data from a candidate-supplied handle.
  `profile_sources` FK → `candidates.id` **ON DELETE CASCADE**. No new
  `ConsentPurpose`. Store only the derived signal + public handle — never raw dumps.
- **TDD offline.** Tests use `FakeGitHub` / `httpx.MockTransport` — never the
  network. `pytest -q` green before every commit and before merge.
- **DB:** SQLAlchemy + Alembic on SQLite, Postgres-shaped. Every new migration
  extends the drift/index/FK-ondelete/nullability guards in `tests/test_migrations.py`.
- **Naming:** package `app/profile_sources/`; table `profile_sources`; migration
  `0010_profile_sources` (down_revision `0009_observed_offers`); config knobs
  `ps_github_*`; id prefix `psrc_`; commit prefix `feat(s61):` / `docs(s61):` —
  **no `Co-Authored-By` trailer** (user preference).

Spec: `docs/superpowers/specs/2026-07-28-s61-github-profile-source-design.md`.

---

### Task 1: Contracts (`app/profile_sources/schema.py`)

Pure Pydantic contracts for the profile-source signal. No I/O, no deps beyond pydantic.

**Files:**
- Create: `app/profile_sources/__init__.py` (empty)
- Create: `app/profile_sources/schema.py`
- Test: `tests/test_profile_sources_schema.py`

**Interfaces:**
- Produces:
  - `ProfileSourceType(StrEnum)`: `GITHUB = "github"`
  - `SourceSkillSignal(name: str, canonical: Optional[str], category: Optional[str], weight: int, confidence: float)`
  - `GitHubActivity(public_repos: int, followers: int, total_stars: int, top_languages: dict[str,int], most_recent_push: Optional[str], account_created: Optional[str], sampled_repos: int)`
  - `ProfileSourceSignal(id: str, source_type: ProfileSourceType, identifier: str, skills: list[SourceSkillSignal], activity: GitHubActivity, method: Literal["api","unavailable"], fetched_at: datetime, warnings: list[str], advisory: bool=True)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profile_sources_schema.py
from datetime import datetime, timezone

from app.profile_sources.schema import (
    GitHubActivity, ProfileSourceSignal, ProfileSourceType, SourceSkillSignal,
)


def test_source_skill_signal_defaults_and_bounds():
    s = SourceSkillSignal(name="Python", canonical="python", category="language", weight=10000)
    assert s.confidence == 0.5  # default until the transform sets it
    assert s.weight == 10000
    assert s.canonical == "python"


def test_profile_source_signal_available_shape():
    sig = ProfileSourceSignal(
        source_type=ProfileSourceType.GITHUB,
        identifier="octocat",
        skills=[SourceSkillSignal(name="Python", canonical="python", category="language", weight=10000, confidence=0.9)],
        activity=GitHubActivity(public_repos=8, total_stars=42, sampled_repos=8),
        method="api",
        fetched_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
    )
    assert sig.id.startswith("psrc_")
    assert sig.advisory is True
    assert sig.method == "api"
    assert sig.activity.total_stars == 42


def test_profile_source_signal_unavailable_shape():
    sig = ProfileSourceSignal(
        source_type=ProfileSourceType.GITHUB,
        identifier="ghost",
        method="unavailable",
        fetched_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
        warnings=["GitHub user ghost not found."],
    )
    assert sig.skills == []
    assert sig.activity.top_languages == {}
    assert sig.warnings == ["GitHub user ghost not found."]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profile_sources_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.profile_sources'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/profile_sources/__init__.py
```
(empty file)

```python
# app/profile_sources/schema.py
"""Profile-source signal contracts (PI-6 / S6.1).

A profile source (GitHub today; LinkedIn export in S6.2) is ingested into a
structured, normalized, provenanced signal that is ADVISORY EVIDENCE — never a
score or a gate. Stored as a peer of resume extractions, revocable via DPDP
candidate erasure (CASCADE).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProfileSourceType(StrEnum):
    GITHUB = "github"
    # LINKEDIN_EXPORT is reserved for S6.2 — added when that adapter lands.


class SourceSkillSignal(BaseModel):
    """One skill observed in a source, mapped to the S1.4 taxonomy when known."""

    name: str                                # raw source term, e.g. "Python"
    canonical: Optional[str] = None          # S1.4 taxonomy id, or None if unknown
    category: Optional[str] = None           # taxonomy category, or None
    weight: int = Field(default=0, ge=0)     # aggregated evidence volume (bytes)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class GitHubActivity(BaseModel):
    """Aggregate activity for a GitHub account (evidence context, not a score)."""

    public_repos: int = 0
    followers: int = 0
    total_stars: int = 0
    top_languages: dict[str, int] = Field(default_factory=dict)  # name -> bytes
    most_recent_push: Optional[str] = None   # ISO-8601 UTC (sorts chronologically)
    account_created: Optional[str] = None    # ISO-8601 UTC
    sampled_repos: int = 0                    # repos that contributed after filtering


class ProfileSourceSignal(BaseModel):
    """The stored, advisory output of ingesting one profile source once."""

    id: str = Field(default_factory=lambda: f"psrc_{uuid.uuid4().hex[:10]}")
    source_type: ProfileSourceType
    identifier: str                          # the handle
    skills: list[SourceSkillSignal] = Field(default_factory=list)
    activity: GitHubActivity = Field(default_factory=GitHubActivity)
    method: Literal["api", "unavailable"] = "api"
    fetched_at: datetime
    warnings: list[str] = Field(default_factory=list)
    advisory: bool = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_profile_sources_schema.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/profile_sources/__init__.py app/profile_sources/schema.py tests/test_profile_sources_schema.py
git commit -m "feat(s61): profile-source signal contracts"
```

---

### Task 2: Live GitHub user fetch + config knobs (`app/services/github.py`, `app/core/config.py`, `config.yaml`)

Add raw DTOs, extend the `GitHubService` Protocol, implement `gather_user_signal`
on `GitHubClient` with the existing graceful-degradation posture, and add the
three `ps_github_*` config knobs (consumed here and in Task 3).

**Files:**
- Modify: `app/services/github.py` (add DTOs + Protocol method + client method)
- Modify: `app/core/config.py` (add `ps_github_*` to `Settings`)
- Modify: `config.yaml` (add a `# profile sources` section)
- Test: `tests/test_github_user_signal.py`

**Interfaces:**
- Consumes: `Settings.ps_github_repo_limit`, `Settings.ps_github_language_repos`.
- Produces:
  - `GitHubRepoRaw(name: str, language: Optional[str], languages: dict[str,int], stargazers_count: int, pushed_at: Optional[str], fork: bool)`
  - `GitHubUserRaw(login: str, available: bool, public_repos: int, followers: int, account_created: Optional[str], repos: list[GitHubRepoRaw], warnings: list[str])`
  - `GitHubService.gather_user_signal(login: str) -> GitHubUserRaw` (async, on the Protocol)
  - `GitHubClient.gather_user_signal(login)` implementation
  - `Settings.ps_github_repo_limit: int = 100`, `ps_github_language_repos: int = 30`, `ps_github_include_forks: bool = False`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_github_user_signal.py
import httpx
import pytest

from app.core.config import Settings
from app.services.github import GitHubClient, GitHubUserRaw


def _client(handler, settings=None):
    transport = httpx.MockTransport(handler)
    ac = httpx.AsyncClient(base_url="https://api.github.com", transport=transport)
    return GitHubClient(settings=settings or Settings(_env_file=None, openrouter_api_key=""), client=ac)


@pytest.mark.asyncio
async def test_gather_user_signal_happy_path():
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/users/octocat":
            return httpx.Response(200, json={"public_repos": 2, "followers": 5, "created_at": "2011-01-25T18:44:36Z"})
        if p == "/users/octocat/repos":
            return httpx.Response(200, json=[
                {"name": "hello", "language": "Python", "stargazers_count": 3, "pushed_at": "2025-01-05T00:00:00Z", "fork": False},
                {"name": "world", "language": "Go", "stargazers_count": 1, "pushed_at": "2024-06-01T00:00:00Z", "fork": False},
            ])
        if p == "/repos/octocat/hello/languages":
            return httpx.Response(200, json={"Python": 10000, "HTML": 500})
        if p == "/repos/octocat/world/languages":
            return httpx.Response(200, json={"Go": 8000})
        return httpx.Response(404, json={})

    raw = await _client(handler).gather_user_signal("octocat")
    assert isinstance(raw, GitHubUserRaw)
    assert raw.available is True
    assert raw.public_repos == 2
    assert {r.name for r in raw.repos} == {"hello", "world"}
    hello = next(r for r in raw.repos if r.name == "hello")
    assert hello.languages == {"Python": 10000, "HTML": 500}


@pytest.mark.asyncio
async def test_gather_user_signal_unknown_user_is_unavailable():
    def handler(request):
        return httpx.Response(404, json={})
    raw = await _client(handler).gather_user_signal("ghost")
    assert raw.available is False
    assert raw.repos == []
    assert any("ghost" in w for w in raw.warnings)


@pytest.mark.asyncio
async def test_gather_user_signal_network_error_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("boom")
    raw = await _client(handler).gather_user_signal("octocat")
    assert raw.available is False
    assert any("failed" in w.lower() for w in raw.warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_github_user_signal.py -v`
Expected: FAIL — `ImportError: cannot import name 'GitHubUserRaw'`.

- [ ] **Step 3: Write minimal implementation**

In `app/core/config.py`, add after the GitHub block (`github_api_base = ...`):

```python
    # --- Profile sources (PI-6, S6.1): GitHub-as-signal ------------------------
    # A candidate-supplied GitHub handle is fetched (public data only) and turned
    # into an ADVISORY structured skill/activity signal. Limits bound rate-limit
    # exposure; forks are not authored signal.
    ps_github_repo_limit: int = Field(default=100, ge=1)
    ps_github_language_repos: int = Field(default=30, ge=0)
    ps_github_include_forks: bool = False
```
(`Field` is already imported in config.py.)

In `config.yaml`, add a section (near the other tunables):

```yaml
# --- Profile sources (PI-6, S6.1): GitHub-as-signal ---
ps_github_repo_limit: 100
ps_github_language_repos: 30
ps_github_include_forks: false
```

In `app/services/github.py`, add `BaseModel`/`Field` to the imports
(`from pydantic import BaseModel, Field`) and the DTOs above `class GitHubService`:

```python
class GitHubRepoRaw(BaseModel):
    name: str
    language: Optional[str] = None
    languages: dict[str, int] = Field(default_factory=dict)
    stargazers_count: int = 0
    pushed_at: Optional[str] = None
    fork: bool = False


class GitHubUserRaw(BaseModel):
    """Raw, source-shaped GitHub account data. `available=False` ⇒ the fetch
    could not complete (404 / rate-limit / network) — never an exception."""

    login: str
    available: bool = True
    public_repos: int = 0
    followers: int = 0
    account_created: Optional[str] = None
    repos: list[GitHubRepoRaw] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
```

Extend the Protocol:

```python
class GitHubService(Protocol):
    async def gather_repo_evidence(self, owner: str, repo: str) -> list[str]: ...
    async def gather_user_signal(self, login: str) -> "GitHubUserRaw": ...
```

Add the client method (after `gather_repo_evidence`, before `_safe_get_json`):

```python
    async def gather_user_signal(self, login: str) -> GitHubUserRaw:
        """A user's public repos aggregated into a raw signal DTO. Any fetch
        failure yields available=False + a warning — never raises."""
        try:
            r = await self._client.get(f"/users/{login}")
        except httpx.HTTPError as exc:
            log.warning("github_user_fetch_error", login=login, error=str(exc))
            return GitHubUserRaw(login=login, available=False,
                                 warnings=[f"GitHub user fetch failed for {login}: {exc}"])
        if r.status_code == 404:
            return GitHubUserRaw(login=login, available=False,
                                 warnings=[f"GitHub user {login} not found."])
        if r.status_code >= 400:
            return GitHubUserRaw(login=login, available=False,
                                 warnings=[f"GitHub returned {r.status_code} for user {login}."])
        u = r.json()
        repos_json = await self._safe_get_json(f"/users/{login}/repos?per_page=100&sort=pushed")
        repos_json = repos_json if isinstance(repos_json, list) else []
        repos_json = repos_json[: self.settings.ps_github_repo_limit]

        repos: list[GitHubRepoRaw] = []
        for i, rp in enumerate(repos_json):
            is_fork = bool(rp.get("fork", False))
            languages: dict[str, int] = {}
            if i < self.settings.ps_github_language_repos and not is_fork:
                langs = await self._safe_get_json(f"/repos/{login}/{rp.get('name')}/languages")
                if isinstance(langs, dict):
                    languages = {k: int(v) for k, v in langs.items()}
            repos.append(GitHubRepoRaw(
                name=rp.get("name", ""),
                language=rp.get("language"),
                languages=languages,
                stargazers_count=int(rp.get("stargazers_count", 0) or 0),
                pushed_at=rp.get("pushed_at"),
                fork=is_fork,
            ))
        return GitHubUserRaw(
            login=login, available=True,
            public_repos=int(u.get("public_repos", 0) or 0),
            followers=int(u.get("followers", 0) or 0),
            account_created=u.get("created_at"),
            repos=repos,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_github_user_signal.py -v`
Expected: PASS (3 tests). Then `pytest -q` — full suite still green.

- [ ] **Step 5: Commit**

```bash
git add app/services/github.py app/core/config.py config.yaml tests/test_github_user_signal.py
git commit -m "feat(s61): GitHub user-signal fetch + ps_github_* config knobs"
```

---

### Task 3: Pure transform (`app/profile_sources/github.py`)

Raw DTO → typed `ProfileSourceSignal`. Pure: no network, `fetched_at` injected.
Aggregates languages, maps to the S1.4 taxonomy, computes bounded confidence.

**Files:**
- Create: `app/profile_sources/github.py`
- Test: `tests/test_profile_sources_transform.py`

**Interfaces:**
- Consumes: `GitHubUserRaw`/`GitHubRepoRaw` (Task 2), `ProfileSourceSignal` &c. (Task 1),
  `Settings.ps_github_include_forks`, `app.candidates.normalize.skills.normalize_skill`.
- Produces: `to_signal(raw: GitHubUserRaw, settings: Settings, *, fetched_at: datetime) -> ProfileSourceSignal`;
  module constant `PRIMARY_LANGUAGE_NOMINAL_BYTES: int = 2048`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profile_sources_transform.py
from datetime import datetime, timezone

from app.core.config import Settings
from app.profile_sources.github import PRIMARY_LANGUAGE_NOMINAL_BYTES, to_signal
from app.services.github import GitHubRepoRaw, GitHubUserRaw

FETCHED = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _settings(**kw):
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def _raw(**kw):
    return GitHubUserRaw(login="octocat", available=True, public_repos=3, followers=5,
                         account_created="2011-01-25T18:44:36Z", **kw)


def test_aggregates_languages_and_maps_canonical():
    raw = _raw(repos=[
        GitHubRepoRaw(name="a", languages={"Python": 8000, "HTML": 500}, stargazers_count=3, pushed_at="2025-01-05T00:00:00Z"),
        GitHubRepoRaw(name="b", languages={"Python": 2000, "Go": 4000}, stargazers_count=1, pushed_at="2024-06-01T00:00:00Z"),
    ])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.method == "api"
    by_name = {s.name: s for s in sig.skills}
    assert by_name["Python"].weight == 10000
    assert by_name["Python"].canonical == "python"
    assert by_name["Go"].canonical == "go"
    # skills sorted by weight desc: Python (10000) first.
    assert sig.skills[0].name == "Python"
    assert sig.activity.total_stars == 4
    assert sig.activity.most_recent_push == "2025-01-05T00:00:00Z"
    assert sig.activity.sampled_repos == 2


def test_unknown_language_kept_with_none_canonical():
    raw = _raw(repos=[GitHubRepoRaw(name="a", languages={"Brainfuck": 500})])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    bf = next(s for s in sig.skills if s.name == "Brainfuck")
    assert bf.canonical is None and bf.category is None


def test_confidence_is_bounded_and_monotone():
    raw = _raw(repos=[GitHubRepoRaw(name="a", languages={"Python": 10000, "Ruby": 1000})])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    conf = {s.name: s.confidence for s in sig.skills}
    assert conf["Python"] == 0.9            # dominant hits the cap
    assert 0.3 <= conf["Ruby"] < conf["Python"]  # smaller share, lower, floored at 0.3


def test_forks_excluded_by_default_included_when_configured():
    raw = _raw(repos=[
        GitHubRepoRaw(name="mine", languages={"Python": 5000}, fork=False),
        GitHubRepoRaw(name="forked", languages={"Java": 9000}, fork=True),
    ])
    default = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert {s.name for s in default.skills} == {"Python"}
    assert default.activity.sampled_repos == 1
    withforks = to_signal(raw, _settings(ps_github_include_forks=True), fetched_at=FETCHED)
    assert {s.name for s in withforks.skills} == {"Python", "Java"}


def test_primary_language_only_repo_uses_nominal_weight():
    raw = _raw(repos=[GitHubRepoRaw(name="a", language="Python", languages={})])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.skills[0].weight == PRIMARY_LANGUAGE_NOMINAL_BYTES


def test_unavailable_raw_produces_unavailable_signal():
    raw = GitHubUserRaw(login="ghost", available=False, warnings=["GitHub user ghost not found."])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.method == "unavailable"
    assert sig.skills == []
    assert sig.identifier == "ghost"
    assert sig.warnings == ["GitHub user ghost not found."]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profile_sources_transform.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.profile_sources.github'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/profile_sources/github.py
"""Pure GitHub raw → ProfileSourceSignal transform (S6.1). No I/O, no LLM.

Aggregates per-language bytes across a user's non-fork repos, maps each language
to the S1.4 skill taxonomy (unknown languages kept with canonical=None), and
derives a bounded, evidence-monotone confidence. ADVISORY evidence only.
"""

from __future__ import annotations

from datetime import datetime

from app.candidates.normalize.skills import normalize_skill
from app.core.config import Settings
from app.profile_sources.schema import (
    GitHubActivity, ProfileSourceSignal, ProfileSourceType, SourceSkillSignal,
)
from app.services.github import GitHubUserRaw

# Repos beyond ps_github_language_repos have no per-language byte breakdown; their
# primary `language` still counts, at this fixed nominal weight, so a large
# account's tail languages are not silently dropped.
PRIMARY_LANGUAGE_NOMINAL_BYTES = 2048


def to_signal(
    raw: GitHubUserRaw, settings: Settings, *, fetched_at: datetime
) -> ProfileSourceSignal:
    if not raw.available:
        return ProfileSourceSignal(
            source_type=ProfileSourceType.GITHUB,
            identifier=raw.login,
            skills=[],
            activity=GitHubActivity(),
            method="unavailable",
            fetched_at=fetched_at,
            warnings=list(raw.warnings),
        )

    repos = [r for r in raw.repos if settings.ps_github_include_forks or not r.fork]
    lang_bytes: dict[str, int] = {}
    total_stars = 0
    pushes: list[str] = []
    for r in repos:
        total_stars += r.stargazers_count
        if r.pushed_at:
            pushes.append(r.pushed_at)
        if r.languages:
            for lang, b in r.languages.items():
                lang_bytes[lang] = lang_bytes.get(lang, 0) + int(b)
        elif r.language:
            lang_bytes[r.language] = lang_bytes.get(r.language, 0) + PRIMARY_LANGUAGE_NOMINAL_BYTES

    max_w = max(lang_bytes.values(), default=0)
    skills: list[SourceSkillSignal] = []
    for lang, w in sorted(lang_bytes.items(), key=lambda kv: (-kv[1], kv[0])):
        match = normalize_skill(lang)
        conf = 0.3 + 0.6 * (w / max_w) if max_w else 0.3
        skills.append(SourceSkillSignal(
            name=lang,
            canonical=match.canonical if match else None,
            category=match.category if match else None,
            weight=w,
            confidence=round(min(0.9, conf), 4),
        ))

    activity = GitHubActivity(
        public_repos=raw.public_repos,
        followers=raw.followers,
        total_stars=total_stars,
        top_languages=dict(lang_bytes),
        most_recent_push=max(pushes) if pushes else None,  # ISO-8601 UTC sorts chronologically
        account_created=raw.account_created,
        sampled_repos=len(repos),
    )
    return ProfileSourceSignal(
        source_type=ProfileSourceType.GITHUB,
        identifier=raw.login,
        skills=skills,
        activity=activity,
        method="api",
        fetched_at=fetched_at,
        warnings=list(raw.warnings),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_profile_sources_transform.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/profile_sources/github.py tests/test_profile_sources_transform.py
git commit -m "feat(s61): pure GitHub raw -> ProfileSourceSignal transform"
```

---

### Task 4: ORM model + migration `0010` + drift guards

New `profile_sources` table on the shared `Base` (candidates DB), migration, and
the every-migration guard extensions. Also register the model in `conftest.py` so
`create_all` builds the table for later tasks.

**Files:**
- Create: `app/profile_sources/models.py`
- Create: `alembic/versions/0010_profile_sources.py`
- Modify: `tests/test_migrations.py` (import model; extend table/index/FK loops)
- Modify: `tests/conftest.py` (import model so `Base.metadata` includes it)

**Interfaces:**
- Produces: `ProfileSourceRow` (`__tablename__ = "profile_sources"`), migration
  `0010_profile_sources` (revises `0009_observed_offers`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_migrations.py` — extend the table assertion in
`test_upgrade_head_creates_candidate_tables`:

```python
    assert "profile_sources" in names  # S6.1 migration 0010
```

Add near the other `*_TABLES` tuples:

```python
PROFILE_SOURCE_TABLES = ("profile_sources",)  # S6.1
```

And append `+ PROFILE_SOURCE_TABLES` to the loop targets in BOTH
`test_migrated_indexes_match_orm` and `test_migrated_fks_and_nullability_match_orm`:

```python
    for table in LEDGER_TABLES + FEATURE_TABLES + MATCHING_TABLES + PROFILE_SOURCE_TABLES:
```

Add the model import near the other model imports at the top of the file:

```python
import app.profile_sources.models  # noqa: F401 — populate Base.metadata
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migrations.py -v`
Expected: FAIL — `ModuleNotFoundError: app.profile_sources.models` (import), or after
the model exists, `add_table` drift / missing `profile_sources` table.

- [ ] **Step 3: Write minimal implementation**

```python
# app/profile_sources/models.py
"""ORM row for stored profile-source signals (S6.1). Postgres-shaped on SQLite.

One row per fetch (append-only history). CASCADEs with the candidate so DPDP
erasure sweeps it — the same contract as resume_fingerprints/extractions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProfileSourceRow(Base):
    __tablename__ = "profile_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    identifier: Mapped[str] = mapped_column(Text)
    signal: Mapped[dict] = mapped_column(JSON)
    method: Mapped[str] = mapped_column(String(16))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

```python
# alembic/versions/0010_profile_sources.py
"""profile sources: GitHub-as-signal ingestion (S6.1)

Revision ID: 0010_profile_sources
Revises: 0009_observed_offers
Create Date: 2026-07-28

"""
from alembic import op
import sqlalchemy as sa

revision = "0010_profile_sources"
down_revision = "0009_observed_offers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id", sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("signal", sa.JSON(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_profile_sources_candidate_id", "profile_sources", ["candidate_id"])
    op.create_index("ix_profile_sources_source_type", "profile_sources", ["source_type"])


def downgrade() -> None:
    op.drop_index("ix_profile_sources_source_type", table_name="profile_sources")
    op.drop_index("ix_profile_sources_candidate_id", table_name="profile_sources")
    op.drop_table("profile_sources")
```

Add to `tests/conftest.py` near the other model imports (lines ~15-17):

```python
import app.profile_sources.models  # noqa: F401 — populate Base.metadata
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_migrations.py -v`
Expected: PASS (all four migration tests, including drift/index/FK/nullability
now covering `profile_sources`).

- [ ] **Step 5: Commit**

```bash
git add app/profile_sources/models.py alembic/versions/0010_profile_sources.py tests/test_migrations.py tests/conftest.py
git commit -m "feat(s61): profile_sources table + migration 0010 + drift guards"
```

---

### Task 5: Store (`app/profile_sources/store.py`)

Append-only persistence on the candidates DB, plus a CASCADE-erasure test.

**Files:**
- Create: `app/profile_sources/store.py`
- Test: `tests/test_profile_sources_store.py`

**Interfaces:**
- Consumes: `ProfileSourceRow` (Task 4), `ProfileSourceSignal`/`ProfileSourceType` (Task 1),
  `app.core.db.make_engine`/`make_session_factory`, `Settings.candidates_db_url`.
- Produces:
  - `ProfileSourceStore(session_factory)` with `save_signal(candidate_id, signal) -> str`,
    `signals_for_candidate(candidate_id, source_type=None) -> list[ProfileSourceSignal]`,
    `latest_for_source(candidate_id, source_type) -> Optional[ProfileSourceSignal]`
  - `build_profile_source_store(settings=None) -> ProfileSourceStore`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profile_sources_store.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profile_sources_store.py -v`
Expected: FAIL — `ModuleNotFoundError: app.profile_sources.store`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/profile_sources/store.py
"""Append-only store for profile-source signals (S6.1), on the candidates DB.

One row per fetch — history is retained (point-in-time materialization later).
DPDP erasure needs no delete path here: rows CASCADE with the candidate.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.profile_sources.models import ProfileSourceRow
from app.profile_sources.schema import ProfileSourceSignal, ProfileSourceType


class ProfileSourceStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def save_signal(self, candidate_id: str, signal: ProfileSourceSignal) -> str:
        with self._session_factory() as session:
            row = ProfileSourceRow(
                candidate_id=candidate_id,
                source_type=signal.source_type.value,
                identifier=signal.identifier,
                signal=signal.model_dump(mode="json"),
                method=signal.method,
                fetched_at=signal.fetched_at,
            )
            session.add(row)
            session.commit()
            return row.id

    def signals_for_candidate(
        self, candidate_id: str, source_type: Optional[ProfileSourceType] = None
    ) -> list[ProfileSourceSignal]:
        with self._session_factory() as session:
            q = select(ProfileSourceRow).where(ProfileSourceRow.candidate_id == candidate_id)
            if source_type is not None:
                q = q.where(ProfileSourceRow.source_type == source_type.value)
            rows = (
                session.execute(
                    q.order_by(ProfileSourceRow.created_at.desc(), ProfileSourceRow.id.desc())
                )
                .scalars()
                .all()
            )
            return [ProfileSourceSignal.model_validate(r.signal) for r in rows]

    def latest_for_source(
        self, candidate_id: str, source_type: ProfileSourceType
    ) -> Optional[ProfileSourceSignal]:
        sigs = self.signals_for_candidate(candidate_id, source_type)
        return sigs[0] if sigs else None


def build_profile_source_store(settings: Optional[Settings] = None) -> ProfileSourceStore:
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return ProfileSourceStore(make_session_factory(engine))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_profile_sources_store.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/profile_sources/store.py tests/test_profile_sources_store.py
git commit -m "feat(s61): ProfileSourceStore (append-only, CASCADE erasure)"
```

---

### Task 6: Service (`app/profile_sources/service.py`) + conftest FakeGitHub

Orchestrate: candidate existence check, handle resolution (explicit → profile
link → error), fetch → transform → persist. Extend the conftest `FakeGitHub` with
`gather_user_signal` so service (and later API) tests stay offline.

**Files:**
- Create: `app/profile_sources/service.py`
- Modify: `tests/conftest.py` (`FakeGitHub.gather_user_signal` + `user_signals` arg)
- Test: `tests/test_profile_sources_service.py`

**Interfaces:**
- Consumes: `ProfileSourceStore` (Task 5), `to_signal` (Task 3), `GitHubService`/`GitHubUserRaw` (Task 2),
  `CandidateStore`, `app.services.github.parse_github_url`, `app.candidates.schema.LinkType`.
- Produces:
  - `ProfileSourceService(*, github, store, candidates, settings)` with
    `async ingest_github(candidate_id, handle=None) -> ProfileSourceSignal` and
    `list_sources(candidate_id, source_type=None) -> list[ProfileSourceSignal]`
    (both raise `LookupError` for an unknown candidate; `ingest_github` raises
    `ValueError` when no handle can be resolved / is malformed)
  - `build_profile_source_service(settings=None, *, github=None, candidates=None) -> ProfileSourceService`

- [ ] **Step 1: Write the failing test**

First extend `tests/conftest.py`. Add imports at top (with the other service imports):

```python
from app.services.github import GitHubRepoRaw, GitHubUserRaw
```

Replace the `FakeGitHub` class with the extended version:

```python
class FakeGitHub:
    """Canned GitHub provenance + user signals; no network."""

    def __init__(
        self,
        evidence: dict[tuple[str, str], list[str]] | None = None,
        user_signals: dict[str, "GitHubUserRaw"] | None = None,
    ) -> None:
        self._evidence = evidence or {}
        self._user_signals = user_signals or {}
        self.calls: list[tuple[str, str]] = []
        self.user_calls: list[str] = []

    async def gather_repo_evidence(self, owner: str, repo: str) -> list[str]:
        self.calls.append((owner, repo))
        return self._evidence.get(
            (owner, repo),
            [f"Repo {owner}/{repo} exists: primary_language=Python, recent commits found."],
        )

    async def gather_user_signal(self, login: str) -> "GitHubUserRaw":
        self.user_calls.append(login)
        return self._user_signals.get(
            login,
            GitHubUserRaw(
                login=login, available=True, public_repos=1, followers=0,
                repos=[GitHubRepoRaw(name="demo", language="Python",
                                     languages={"Python": 10000}, stargazers_count=3,
                                     pushed_at="2025-01-01T00:00:00Z")],
            ),
        )
```

Now the service test:

```python
# tests/test_profile_sources_service.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profile_sources_service.py -v`
Expected: FAIL — `ModuleNotFoundError: app.profile_sources.service`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/profile_sources/service.py
"""Profile-source ingestion orchestration (S6.1).

Resolves a GitHub handle (explicit arg, else the candidate's profile GitHub
link), fetches the public signal, transforms it, and persists it. Advisory:
a missing/unreachable GitHub yields a stored `method="unavailable"` signal, not
an error. No LLM.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from app.candidates.schema import LinkType
from app.candidates.store import CandidateStore, build_candidate_store
from app.core.config import Settings, get_settings
from app.profile_sources.github import to_signal
from app.profile_sources.schema import ProfileSourceSignal, ProfileSourceType
from app.profile_sources.store import ProfileSourceStore, build_profile_source_store
from app.services.github import GitHubClient, GitHubService, parse_github_url

_LOGIN_RE = re.compile(r"[A-Za-z0-9-]{1,39}")


class ProfileSourceService:
    def __init__(
        self,
        *,
        github: GitHubService,
        store: ProfileSourceStore,
        candidates: CandidateStore,
        settings: Settings,
    ) -> None:
        self._github = github
        self._store = store
        self._candidates = candidates
        self._settings = settings

    async def ingest_github(
        self, candidate_id: str, handle: Optional[str] = None
    ) -> ProfileSourceSignal:
        if self._candidates.get_candidate(candidate_id) is None:
            raise LookupError(f"candidate {candidate_id} not found")
        login = self._resolve_handle(candidate_id, handle)
        raw = await self._github.gather_user_signal(login)
        signal = to_signal(raw, self._settings, fetched_at=datetime.now(timezone.utc))
        self._store.save_signal(candidate_id, signal)
        return signal

    def list_sources(
        self, candidate_id: str, source_type: Optional[ProfileSourceType] = None
    ) -> list[ProfileSourceSignal]:
        if self._candidates.get_candidate(candidate_id) is None:
            raise LookupError(f"candidate {candidate_id} not found")
        return self._store.signals_for_candidate(candidate_id, source_type)

    def _resolve_handle(self, candidate_id: str, handle: Optional[str]) -> str:
        if handle and handle.strip():
            return self._parse_login(handle.strip())
        profile = self._candidates.latest_profile(candidate_id)
        if profile is not None:
            for link in profile.links:
                if link.type == LinkType.GITHUB:
                    anchor = parse_github_url(link.url)
                    if anchor is not None and anchor.owner:
                        return anchor.owner
        raise ValueError("no GitHub handle supplied or found on the candidate profile")

    @staticmethod
    def _parse_login(raw: str) -> str:
        if "github.com" in raw:
            anchor = parse_github_url(raw)
            if anchor is not None and anchor.owner:
                return anchor.owner
            raise ValueError(f"unparseable GitHub URL: {raw}")
        if _LOGIN_RE.fullmatch(raw):
            return raw
        raise ValueError(f"invalid GitHub handle: {raw}")


def build_profile_source_service(
    settings: Optional[Settings] = None,
    *,
    github: Optional[GitHubService] = None,
    candidates: Optional[CandidateStore] = None,
) -> ProfileSourceService:
    settings = settings or get_settings()
    candidates = candidates or build_candidate_store(settings)
    github = github or GitHubClient(settings)
    store = build_profile_source_store(settings)
    return ProfileSourceService(
        github=github, store=store, candidates=candidates, settings=settings
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_profile_sources_service.py -v`
Expected: PASS (5 tests). Then `pytest -q` — full suite green (conftest change is
additive; existing `FakeGitHub()` callers still work).

- [ ] **Step 5: Commit**

```bash
git add app/profile_sources/service.py tests/conftest.py tests/test_profile_sources_service.py
git commit -m "feat(s61): ProfileSourceService (handle resolution, fetch->transform->persist)"
```

---

### Task 7: Services wiring + API endpoints

Add `profile_sources` to the `Services` container (cycle-safe), wire it in
`build_default_services` and the conftest `make_services`, and add the two
endpoints on the admin `router`.

**Files:**
- Modify: `app/services/__init__.py` (`Services.profile_sources` + build wiring)
- Modify: `app/api/routes.py` (request/response models + two handlers)
- Modify: `app/main.py` (root endpoint list)
- Modify: `tests/conftest.py` (`make_services` param + default build)
- Test: `tests/test_profile_sources_api.py`

**Interfaces:**
- Consumes: `ProfileSourceService`/`build_profile_source_service` (Task 6),
  `ProfileSourceSignal`/`ProfileSourceType` (Task 1).
- Produces: `Services.profile_sources: ProfileSourceService`; endpoints
  `POST /candidates/{id}/sources/github` (→ `ProfileSourceSignal`),
  `GET /candidates/{id}/sources` (→ `ProfileSourcesResponse{candidate_id, sources}`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profile_sources_api.py
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.github import GitHubUserRaw
from tests.conftest import FakeGitHub, make_services


def _client(services):
    return TestClient(create_app(services), raise_server_exceptions=False)


def _candidate(client) -> str:
    r = client.post("/candidates", json={"resume_text":
        "Dev\nEmail: dev@example.com\nSKILLS\nPython\n", "evaluate": False})
    assert r.status_code == 200
    return r.json()["candidate_id"]


def test_post_github_source_available(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/github", json={"handle": "octocat"})
        assert r.status_code == 200
        body = r.json()
        assert body["method"] == "api"
        assert body["identifier"] == "octocat"
        assert any(s["canonical"] == "python" for s in body["skills"])

        lst = client.get(f"/candidates/{cid}/sources")
        assert lst.status_code == 200
        assert len(lst.json()["sources"]) == 1


def test_post_github_source_unavailable_is_200(settings):
    gh = FakeGitHub(user_signals={"ghost": GitHubUserRaw(login="ghost", available=False, warnings=["not found"])})
    services = make_services(settings, github=gh)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/github", json={"handle": "ghost"})
        assert r.status_code == 200
        assert r.json()["method"] == "unavailable"


def test_post_github_source_no_handle_is_400(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)  # resume has no github link
        r = client.post(f"/candidates/{cid}/sources/github", json={})
        assert r.status_code == 400


def test_post_github_source_unknown_candidate_is_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.post("/candidates/nope/sources/github", json={"handle": "octocat"})
        assert r.status_code == 404


def test_get_sources_unknown_candidate_is_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.get("/candidates/nope/sources")
        assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profile_sources_api.py -v`
Expected: FAIL — `TypeError: make_services() ... profile_sources` / `AttributeError:
Services has no field 'profile_sources'` / 404 route not found.

- [ ] **Step 3: Write minimal implementation**

In `app/services/__init__.py`:

Add under the existing `TYPE_CHECKING` block:
```python
    from app.profile_sources.service import ProfileSourceService
```
Add the field to the `Services` dataclass (after `dashboard`):
```python
    profile_sources: ProfileSourceService
```
Rewrite the body of `build_default_services` to hoist shared deps and wire the service:
```python
def build_default_services(settings: Optional[Settings] = None) -> Services:
    from app.comp.service import build_comp_service
    from app.dashboard.service import build_dashboard_service
    from app.features.store import build_feature_store
    from app.matching.store import build_job_store
    from app.profile_sources.service import build_profile_source_service

    settings = settings or get_settings()
    github = GitHubClient(settings)
    candidates = build_candidate_store(settings)
    return Services(
        settings=settings,
        llm=build_llm(settings),
        vectorstore=build_vectorstore(settings),
        github=github,
        flywheel=build_flywheel(settings),
        report_store=build_report_store(settings),
        candidates=candidates,
        ledger=build_ledger_store(settings),
        features=build_feature_store(settings),
        jobs=build_job_store(settings),
        comp=build_comp_service(settings),
        dashboard=build_dashboard_service(settings),
        profile_sources=build_profile_source_service(
            settings, github=github, candidates=candidates
        ),
    )
```

In `tests/conftest.py` `make_services`, add a `profile_sources=None` kwarg, and
compute a single shared `github` so `Services.github` and the profile-source
service share one fake. Replace the top of `make_services` and the constructor:

```python
def make_services(
    settings: Settings,
    *,
    llm: LLMClient | None = None,
    github: FakeGitHub | None = None,
    flywheel: InMemoryFlywheel | None = None,
    candidates: CandidateStore | None = None,
    ledger: LedgerStore | None = None,
    features: FeatureStore | None = None,
    jobs=None,
    comp=None,
    dashboard=None,
    profile_sources=None,
) -> Services:
    candidates = candidates or make_candidate_store()
    github = github or FakeGitHub()
    ledger = ledger or LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        settings=settings,
    )
    features = features or FeatureStore(candidates._session_factory)
    if jobs is None:
        from app.matching.store import JobStore
        jobs = JobStore(
            candidates._session_factory,
            candidate_store=candidates, feature_store=features, settings=settings,
        )
    if comp is None:
        from app.comp.service import CompService
        comp = CompService(ledger, settings=settings)
    if dashboard is None:
        from app.dashboard.service import DashboardService
        dashboard = DashboardService(jobs, comp, ledger, settings=settings)
    if profile_sources is None:
        from app.profile_sources.service import ProfileSourceService
        from app.profile_sources.store import ProfileSourceStore
        profile_sources = ProfileSourceService(
            github=github,
            store=ProfileSourceStore(candidates._session_factory),
            candidates=candidates, settings=settings,
        )
    return Services(
        settings=settings,
        llm=llm or NullLLM(settings),
        vectorstore=InMemoryVectorStore(),
        github=github,
        flywheel=flywheel or InMemoryFlywheel(),
        report_store=InMemoryReportStore(),
        candidates=candidates,
        ledger=ledger,
        features=features,
        jobs=jobs,
        comp=comp,
        dashboard=dashboard,
        profile_sources=profile_sources,
    )
```

In `app/api/routes.py`:

Add the import (with the other `app.*` imports):
```python
from app.profile_sources.schema import ProfileSourceSignal, ProfileSourceType
```
Add request/response models and handlers (near the candidate routes, before the
ledger routes at line ~365):
```python
class GitHubSourceRequest(BaseModel):
    handle: Optional[str] = None


class ProfileSourcesResponse(BaseModel):
    candidate_id: str
    sources: list[ProfileSourceSignal]


@router.post(
    "/candidates/{candidate_id}/sources/github", response_model=ProfileSourceSignal
)
async def ingest_github_source(
    candidate_id: str, req: GitHubSourceRequest, request: Request
) -> ProfileSourceSignal:
    """Ingest a candidate's public GitHub handle as an advisory skill signal.
    A missing/unreachable handle returns 200 with method='unavailable'."""
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    try:
        return await services.profile_sources.ingest_github(candidate_id, handle=req.handle)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/candidates/{candidate_id}/sources", response_model=ProfileSourcesResponse
)
async def list_candidate_sources(
    candidate_id: str, request: Request, source_type: Optional[ProfileSourceType] = None
) -> ProfileSourcesResponse:
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return ProfileSourcesResponse(
        candidate_id=candidate_id,
        sources=services.profile_sources.list_sources(candidate_id, source_type),
    )
```

In `app/main.py`, add to the root `endpoints` list (after the candidates entries):
```python
                "POST /candidates/{id}/sources/github",
                "GET /candidates/{id}/sources",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_profile_sources_api.py -v`
Expected: PASS (5 tests). Then `pytest -q` — full suite green.

- [ ] **Step 5: Commit**

```bash
git add app/services/__init__.py app/api/routes.py app/main.py tests/conftest.py tests/test_profile_sources_api.py
git commit -m "feat(s61): wire ProfileSourceService + GitHub source endpoints"
```

---

### Task 8: Smoke (`scripts/smoke_s61.py`)

End-to-end over real HTTP: create candidate → ingest a GitHub source (stable
public handle) → list → DPDP erase → 404. Robust to rate-limit/offline (the live
fetch may return `unavailable`; the endpoint contract must still hold).

**Files:**
- Create: `scripts/smoke_s61.py`

- [ ] **Step 1: Write the smoke script**

```python
# scripts/smoke_s61.py
"""S6.1 smoke: boot uvicorn on a migrated scratch DB, create a candidate, ingest
a GitHub profile source (handle=octocat), list it, then DPDP-erase the candidate
and confirm the sources 404. Hits the LIVE public GitHub API; robust to
rate-limit/offline (asserts the endpoint returns 200 with method in {api,
unavailable} and that erasure sweeps the source). Run from repo root:
python scripts/smoke_s61.py
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

PORT = 8061
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
RESUME = "Dev\nEmail: dev@example.com\nSKILLS\nPython\n"


def _wait_healthy(c) -> bool:
    for _ in range(60):
        try:
            if c.get("/healthz").status_code == 200:
                return True
        except httpx.TransportError:
            time.sleep(0.5)
    return False


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s61.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_API_AUTH_KEY": ADMIN,
    })
    admin_h = {"X-API-Key": ADMIN}
    checks: dict[str, bool] = {}

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(60, connect=5)) as c:
            if not _wait_healthy(c):
                print("FAIL server never became healthy")
                return 1

            cid = c.post("/candidates", json={"resume_text": RESUME, "evaluate": False},
                         headers=admin_h).json()["candidate_id"]

            r = c.post(f"/candidates/{cid}/sources/github",
                       json={"handle": "octocat"}, headers=admin_h)
            checks["POST github source -> 200"] = r.status_code == 200
            body = r.json() if r.status_code == 200 else {}
            method = body.get("method")
            checks["method in {api, unavailable}"] = method in {"api", "unavailable"}
            if method == "api":
                checks["api signal has activity.public_repos >= 0"] = (
                    body.get("activity", {}).get("public_repos", -1) >= 0
                )
            else:
                print("  NOTE  live GitHub fetch unavailable (rate-limit/offline) — "
                      "endpoint contract still verified")

            lst = c.get(f"/candidates/{cid}/sources", headers=admin_h)
            checks["GET sources -> 200, one row"] = (
                lst.status_code == 200 and len(lst.json()["sources"]) == 1
            )

            no_handle = c.post(f"/candidates/{cid}/sources/github", json={}, headers=admin_h)
            checks["no-handle (no github link) -> 400"] = no_handle.status_code == 400

            deleted = c.delete(f"/candidates/{cid}", headers=admin_h)
            checks["DPDP delete candidate -> 200"] = deleted.status_code == 200

            after = c.get(f"/candidates/{cid}/sources", headers=admin_h)
            checks["sources 404 after erasure"] = after.status_code == 404
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if any(not ok for ok in checks.values()):
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the smoke**

Run: `python scripts/smoke_s61.py`
Expected: `SMOKE OK`, exit 0. All checks `OK` (the `method == "api"` sub-check is
skipped with a NOTE if GitHub is rate-limited/offline; the contract checks still pass).

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_s61.py
git commit -m "test(s61): smoke_s61 (uvicorn + live GitHub, rate-limit-robust)"
```

---

### Task 9: Docs + ROADMAP

`PROFILE_SOURCES.md` (peer of `MATCHING.md`/`COMP.md`/`DASHBOARD.md`) and the
ROADMAP update (PI-6 reshape + S6.1 status/session log).

**Files:**
- Create: `PROFILE_SOURCES.md`
- Modify: `docs/ROADMAP.md` (status board `S6.1 [x]`, Current state, session log,
  PI-6 reshape note)

- [ ] **Step 1: Write `PROFILE_SOURCES.md`**

Document, matching the tone/structure of `COMP.md`/`DASHBOARD.md`:
- What a profile source is (advisory structured skill/activity signal, peer of
  resume extractions).
- The GitHub adapter: fetch (`gather_user_signal`) → pure transform (`to_signal`,
  language aggregation + S1.4 mapping + bounded confidence + fork exclusion) →
  `ProfileSourceStore` (append-only, CASCADE).
- Handle resolution (explicit → profile GitHub link → 400).
- DPDP posture: first-party public data, no new consent purpose, CASCADE erasure.
- Config knobs `ps_github_*`.
- Endpoints `POST /candidates/{id}/sources/github`, `GET /candidates/{id}/sources`.
- Non-goals / follow-ups: corroboration, feature-store consumption, LinkedIn
  export (S6.2), candidate auth (S6.3 moves these endpoints under candidate auth).

- [ ] **Step 2: Update `docs/ROADMAP.md`**

- Status board: change the `PI-6` block so `S6.1` is `[x]` with a one-line
  summary; note the reshape (S6.2 now = LinkedIn export + curation loop).
- "Current state": set Current sprint to S6.1 COMPLETE with the test count and
  smoke result; set Next action to shape/plan S6.2.
- Add a session-log entry dated 2026-07-28 summarizing S6.1 (package, migration
  0010, endpoints, test delta, smoke, merge status).

- [ ] **Step 3: Final verification**

Run: `pytest -q`
Expected: all green (baseline 672 + ~28 new ≈ 700).

Run: `python -m pyflakes app/profile_sources/ app/services/github.py app/api/routes.py app/services/__init__.py`
Expected: no output (clean).

- [ ] **Step 4: Commit**

```bash
git add PROFILE_SOURCES.md docs/ROADMAP.md
git commit -m "docs(s61): PROFILE_SOURCES.md + ROADMAP (PI-6 reshape, S6.1 done)"
```

---

## Self-Review

**1. Spec coverage:**
- §5.1 contracts → Task 1. §5.2 transform → Task 3. §5.3 service → Task 6.
  §5.4 store → Task 5. §6 live fetch → Task 2. §7 migration → Task 4. §8 API →
  Task 7. §9 DPDP (CASCADE, no new purpose) → Task 4 migration + Task 5 CASCADE
  test + documented in Task 9. §10 config → Task 2. §11 testing/smoke → every
  task + Task 8. §12 non-goals → documented in Task 9. §13 deliverables → all tasks.
  All spec sections have a home.
- Handle resolution (explicit → profile link → 400) — Task 6 (`_resolve_handle`).
- Degraded-200-vs-400-vs-404 contract — Task 7 API tests.

**2. Placeholder scan:** No TBD/TODO/"add error handling"/"similar to Task N".
Every code step has runnable code and concrete assertions. The only intentional
free-form deliverable is `PROFILE_SOURCES.md` prose (Task 9), scoped by a
content checklist.

**3. Type consistency:**
- `to_signal(raw, settings, *, fetched_at)` — defined Task 3, called identically
  in Task 6.
- `gather_user_signal(login) -> GitHubUserRaw` — defined Task 2 (Protocol +
  client), faked in Task 6 conftest, consumed in Task 6 service.
- `ProfileSourceStore(session_factory)` + `save_signal`/`signals_for_candidate`/
  `latest_for_source` — defined Task 5, consumed Task 6/7.
- `ProfileSourceService(*, github, store, candidates, settings)` with
  `ingest_github`/`list_sources` — defined Task 6, consumed Task 7 + conftest.
- `ProfileSourceType`/`ProfileSourceSignal` — defined Task 1, used Tasks 3/5/6/7.
- Migration `0010_profile_sources` revises `0009_observed_offers`; table
  `profile_sources`; indexes `ix_profile_sources_candidate_id` /
  `ix_profile_sources_source_type` match between ORM (`index=True`) and migration.

One test-only note for the executor: in Task 6
`test_handle_derived_from_profile_github_link`, the candidate id comes straight
from `cs.ingest(...).candidate_id` (the store's `ingest` returns an
`IngestOutcome` carrying it) — no extra query helper is needed.
