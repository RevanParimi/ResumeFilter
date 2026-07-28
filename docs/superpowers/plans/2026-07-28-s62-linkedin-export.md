# S6.2 — LinkedIn export parsing (2nd profile-source adapter) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LinkedIn "Get a copy of your data" export parsing as the second
adapter on the S6.1 `app/profile_sources/` spine — a pure, offline, advisory
skill+activity signal ingested from a candidate-uploaded ZIP.

**Architecture:** GitHub's "live fetch" seam is replaced by a **pure parse-bytes**
seam; everything downstream is identical to S6.1. `parse_linkedin_export(bytes)`
(pure `zipfile`/`csv`, graceful degradation) → `to_signal` (pure; S1.4 taxonomy
mapping + conservative/corroboration confidence) → the **same** append-only
`ProfileSourceStore` (no migration, `signal` is JSON) → CASCADE erasure. A new
base64-in-JSON endpoint mirrors the existing `resume_pdf_b64` transport.

**Tech Stack:** Python 3.12, pydantic v2, FastAPI, SQLAlchemy, pytest. Stdlib
`zipfile`/`csv`/`io`/`base64`/`re` only — **no new dependency, no network, no LLM.**

## Global Constraints

- **Advisory only.** The signal is evidence, never a score/gate. Depth-eval
  scoring and verdicts are untouched.
- **Deterministic, no LLM, no network** anywhere in this adapter. No API key ever
  required.
- **DPDP: first-party only.** Candidate uploads their own export. Store the
  **derived signal only** — S1.4-mapped skills + de-identified activity aggregates
  (counts + *canonical* employers/institutions + headline/industry + languages).
  **No** raw contact PII (email/phone/address), **no** summary free-text, **no**
  connections, **no** vanity URL. **No new `ConsentPurpose`.**
- **Reuse the S6.1 `0010_profile_sources` table — no migration.** New rows carry
  `source_type="linkedin_export"`.
- **TDD, fully offline** (NullLLM/fakes); `pytest -q` green before merge.
- **Config:** tunables in `config.yaml` + `Settings` (defaults); secrets never.
- Files created live under `app/profile_sources/`; tests under `tests/`; match the
  existing S6.1 file/test style exactly.
- **No `Co-Authored-By` trailer** in commits (user preference).

---

## File map

- **Modify** `app/core/config.py` — 4 new `Settings` knobs (Task 1).
- **Modify** `config.yaml` — the same 4 knobs with defaults (Task 1).
- **Modify** `app/profile_sources/schema.py` — `LINKEDIN_EXPORT`, `LinkedInActivity`,
  extend `method` literal, `activity` discriminated union + back-compat validator,
  generalize `SourceSkillSignal.weight` docstring (Task 2).
- **Create** `app/profile_sources/linkedin.py` — raw DTOs + `parse_linkedin_export`
  (Task 3) + `to_signal` (Task 4).
- **Modify** `app/profile_sources/service.py` — `ingest_linkedin` method (Task 5).
- **Modify** `app/api/routes.py` — `POST /candidates/{id}/sources/linkedin`
  request model + route (Task 6).
- **Modify** `PROFILE_SOURCES.md`, `docs/ROADMAP.md`; **create**
  `scripts/smoke_s62.py` (Task 7).
- **Create** tests: `tests/test_linkedin_parse.py`,
  `tests/test_linkedin_transform.py`, and additions to
  `tests/test_profile_sources_schema.py`, `tests/test_profile_sources_service.py`,
  `tests/test_profile_sources_api.py`.

---

### Task 1: Config knobs

**Files:**
- Modify: `app/core/config.py` (after the `ps_github_*` block, ~line 124)
- Modify: `config.yaml` (near the profile-sources section)
- Test: `tests/test_config.py` (add one test; file already exists)

**Interfaces:**
- Produces: `Settings.max_linkedin_b64_chars: int`,
  `Settings.ps_linkedin_skill_base_confidence: float`,
  `Settings.ps_linkedin_skill_corroborated_confidence: float`,
  `Settings.ps_linkedin_max_rows: int`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_linkedin_source_defaults():
    from app.core.config import Settings
    s = Settings(_env_file=None, openrouter_api_key="")
    assert s.max_linkedin_b64_chars == 8_000_000
    assert s.ps_linkedin_skill_base_confidence == 0.4
    assert s.ps_linkedin_skill_corroborated_confidence == 0.6
    assert s.ps_linkedin_max_rows == 5_000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_linkedin_source_defaults -v`
Expected: FAIL (`AttributeError`/validation — knobs don't exist).

- [ ] **Step 3: Add the knobs**

In `app/core/config.py`, immediately after the `ps_github_include_forks` line
(the end of the S6.1 profile-sources block):

```python
    # --- Profile sources (PI-6, S6.2): LinkedIn export parsing ------------------
    # The candidate uploads their own LinkedIn "Get a copy of your data" ZIP.
    # Pure parse (no network, no LLM). Self-reported Skills.csv entries are
    # low-confidence CLAIMS, bumped only when a position/headline corroborates.
    max_linkedin_b64_chars: int = 8_000_000  # reject oversize uploads (≈6 MB zip)
    ps_linkedin_skill_base_confidence: float = Field(default=0.4, ge=0.0, le=1.0)
    ps_linkedin_skill_corroborated_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    ps_linkedin_max_rows: int = Field(default=5_000, ge=1)  # per-CSV row cap
```

In `config.yaml`, near the existing `ps_github_*` entries, add:

```yaml
# Profile sources (S6.2): LinkedIn export parsing
max_linkedin_b64_chars: 8000000
ps_linkedin_skill_base_confidence: 0.4
ps_linkedin_skill_corroborated_confidence: 0.6
ps_linkedin_max_rows: 5000
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_linkedin_source_defaults -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py config.yaml tests/test_config.py
git commit -m "feat(s62): LinkedIn-source config knobs"
```

---

### Task 2: Schema — `LinkedInActivity` + discriminated-union `activity` + back-compat

**Files:**
- Modify: `app/profile_sources/schema.py`
- Test: `tests/test_profile_sources_schema.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `ProfileSourceType.LINKEDIN_EXPORT = "linkedin_export"`.
  - `LinkedInActivity(BaseModel)` with fields: `kind: Literal["linkedin_export"]`,
    `positions_count: int`, `current_positions: int`, `employers: list[str]`,
    `education_count: int`, `institutions: list[str]`, `certifications_count: int`,
    `languages: list[str]`, `headline: Optional[str]`, `industry: Optional[str]`,
    `skills_listed: int`.
  - `GitHubActivity.kind: Literal["github"] = "github"`.
  - `ProfileSourceSignal.activity: GitHubActivity | LinkedInActivity` (discriminated
    on `kind`, default_factory `GitHubActivity`), `method: Literal["api",
    "export", "unavailable"]`, and a `mode="before"` validator
    `_backfill_activity_kind`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_profile_sources_schema.py`:

```python
from datetime import datetime, timezone
from app.profile_sources.schema import (
    GitHubActivity, LinkedInActivity, ProfileSourceSignal, ProfileSourceType,
    SourceSkillSignal,
)

FETCHED = datetime(2026, 7, 28, tzinfo=timezone.utc)


def test_linkedin_signal_roundtrips_through_json():
    sig = ProfileSourceSignal(
        source_type=ProfileSourceType.LINKEDIN_EXPORT,
        identifier="linkedin_export",
        skills=[SourceSkillSignal(name="Python", canonical="python", weight=2, confidence=0.6)],
        activity=LinkedInActivity(positions_count=2, employers=["Infosys"], headline="Engineer"),
        method="export",
        fetched_at=FETCHED,
    )
    back = ProfileSourceSignal.model_validate(sig.model_dump(mode="json"))
    assert isinstance(back.activity, LinkedInActivity)
    assert back.activity.employers == ["Infosys"]
    assert back.method == "export"


def test_pre_s62_github_row_without_kind_still_validates():
    # A row stored before S6.2 has no activity.kind; the discriminator is
    # backfilled from the top-level source_type.
    legacy = {
        "id": "psrc_legacy01",
        "source_type": "github",
        "identifier": "octocat",
        "skills": [],
        "activity": {"public_repos": 3, "followers": 5, "total_stars": 4,
                     "top_languages": {"Python": 10}, "sampled_repos": 2},
        "method": "api",
        "fetched_at": "2026-07-28T00:00:00Z",
        "warnings": [],
        "advisory": True,
    }
    back = ProfileSourceSignal.model_validate(legacy)
    assert isinstance(back.activity, GitHubActivity)
    assert back.activity.public_repos == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_profile_sources_schema.py -v -k "linkedin or pre_s62"`
Expected: FAIL (`LinkedInActivity`/import errors; union not defined).

- [ ] **Step 3: Implement the schema changes**

In `app/profile_sources/schema.py`:

Update the imports line to include `model_validator`:

```python
from pydantic import BaseModel, Field, model_validator
```

Add `LINKEDIN_EXPORT` to the enum:

```python
class ProfileSourceType(StrEnum):
    GITHUB = "github"
    LINKEDIN_EXPORT = "linkedin_export"
```

Generalize the `SourceSkillSignal.weight` comment (semantics only):

```python
    weight: int = Field(default=0, ge=0)     # aggregated evidence volume (source-defined)
```

Add `kind` to `GitHubActivity` as its FIRST field:

```python
class GitHubActivity(BaseModel):
    """Aggregate activity for a GitHub account (evidence context, not a score)."""

    kind: Literal["github"] = "github"
    public_repos: int = 0
    followers: int = 0
    total_stars: int = 0
    top_languages: dict[str, int] = Field(default_factory=dict)  # name -> bytes
    most_recent_push: Optional[str] = None
    account_created: Optional[str] = None
    sampled_repos: int = 0
```

Add the new activity model directly after `GitHubActivity`:

```python
class LinkedInActivity(BaseModel):
    """Aggregate activity from a LinkedIn export (evidence context, not a score).

    De-identified: canonical employers/institutions + counts only. No raw contact
    PII, no summary text, no connections.
    """

    kind: Literal["linkedin_export"] = "linkedin_export"
    positions_count: int = 0
    current_positions: int = 0                       # positions with no end date
    employers: list[str] = Field(default_factory=list)      # canonical, deduped
    education_count: int = 0
    institutions: list[str] = Field(default_factory=list)   # canonical, deduped
    certifications_count: int = 0
    languages: list[str] = Field(default_factory=list)
    headline: Optional[str] = None
    industry: Optional[str] = None
    skills_listed: int = 0                            # raw count from Skills.csv
```

Update `ProfileSourceSignal` — the `activity` field, the `method` literal, and add
the back-compat validator:

```python
class ProfileSourceSignal(BaseModel):
    """The stored, advisory output of ingesting one profile source once."""

    id: str = Field(default_factory=lambda: f"psrc_{uuid.uuid4().hex[:10]}")
    source_type: ProfileSourceType
    identifier: str                          # the handle / source label
    skills: list[SourceSkillSignal] = Field(default_factory=list)
    activity: GitHubActivity | LinkedInActivity = Field(
        default_factory=GitHubActivity, discriminator="kind"
    )
    method: Literal["api", "export", "unavailable"] = "api"
    fetched_at: datetime
    warnings: list[str] = Field(default_factory=list)
    advisory: bool = True

    @model_validator(mode="before")
    @classmethod
    def _backfill_activity_kind(cls, data):
        """Rows stored before S6.2 have no ``activity.kind``; derive it from the
        already-present ``source_type`` so the discriminated union resolves. Only
        touches a dict activity that lacks the discriminator (a model instance
        already carries its default kind)."""
        if isinstance(data, dict):
            act = data.get("activity")
            if isinstance(act, dict) and "kind" not in act:
                st = data.get("source_type")
                st_val = getattr(st, "value", st)
                act["kind"] = "linkedin_export" if st_val == "linkedin_export" else "github"
        return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_profile_sources_schema.py -v`
Then the full profile-sources + transform suites (guard the GitHub path):
Run: `pytest tests/test_profile_sources_transform.py tests/test_profile_sources_store.py -q`
Expected: PASS (GitHub `to_signal` still constructs `GitHubActivity(...)`, now with
a defaulted `kind` — unchanged behavior).

- [ ] **Step 5: Commit**

```bash
git add app/profile_sources/schema.py tests/test_profile_sources_schema.py
git commit -m "feat(s62): LinkedInActivity + discriminated activity union (back-compat)"
```

---

### Task 3: Pure parse — `parse_linkedin_export`

**Files:**
- Create: `app/profile_sources/linkedin.py`
- Test: `tests/test_linkedin_parse.py`

**Interfaces:**
- Consumes: `Settings.ps_linkedin_max_rows`.
- Produces:
  - `LinkedInPositionRaw(company, title, description, started_on, finished_on)` (all `str`, default `""`).
  - `LinkedInEducationRaw(school, degree)` (both `str`, default `""`).
  - `LinkedInExportRaw(available: bool, skills: list[str], positions:
    list[LinkedInPositionRaw], education: list[LinkedInEducationRaw],
    certifications: list[str], languages: list[str], headline: Optional[str],
    industry: Optional[str], warnings: list[str])`.
  - `parse_linkedin_export(data: bytes, settings: Settings) -> LinkedInExportRaw`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_linkedin_parse.py`:

```python
import csv
import io
import zipfile

from app.core.config import Settings
from app.profile_sources.linkedin import parse_linkedin_export


def _settings(**kw):
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def _zip(files: dict[str, str]) -> bytes:
    """Build an in-memory zip from {archive_name: csv_text}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


SKILLS = "Name\nPython\nDjango\nLeadership\n"
POSITIONS = (
    "Company Name,Title,Description,Started On,Finished On\n"
    "Infosys,Python Developer,Built Django APIs,Jan 2020,Dec 2021\n"
    "TCS,Engineer,Kubernetes work,Jan 2022,\n"
)
EDUCATION = "School Name,Degree Name,Start Date,End Date\nIIT Madras,B.Tech,2016,2020\n"
PROFILE = "First Name,Last Name,Headline,Industry\nAsha,K,Senior Python Engineer,Information Technology\n"


def test_parses_all_sections():
    raw = parse_linkedin_export(
        _zip({"Skills.csv": SKILLS, "Positions.csv": POSITIONS,
              "Education.csv": EDUCATION, "Profile.csv": PROFILE}),
        _settings(),
    )
    assert raw.available is True
    assert raw.skills == ["Python", "Django", "Leadership"]
    assert [p.company for p in raw.positions] == ["Infosys", "TCS"]
    assert raw.positions[1].finished_on == ""   # current role
    assert raw.education[0].school == "IIT Madras"
    assert raw.headline == "Senior Python Engineer"
    assert raw.industry == "Information Technology"


def test_tolerates_column_name_variants():
    positions = "Company,Title\nWipro,SDE\n"
    education = "School,Degree\nBITS Pilani,M.Tech\n"
    raw = parse_linkedin_export(_zip({"Positions.csv": positions, "Education.csv": education}), _settings())
    assert raw.positions[0].company == "Wipro"
    assert raw.education[0].school == "BITS Pilani"


def test_nested_directory_members_resolved():
    raw = parse_linkedin_export(_zip({"Basic_LinkedInDataExport/Skills.csv": SKILLS}), _settings())
    assert raw.available is True
    assert raw.skills == ["Python", "Django", "Leadership"]


def test_missing_optional_files_are_fine():
    raw = parse_linkedin_export(_zip({"Skills.csv": SKILLS}), _settings())
    assert raw.available is True
    assert raw.positions == [] and raw.education == []


def test_non_zip_is_unavailable():
    raw = parse_linkedin_export(b"this is not a zip", _settings())
    assert raw.available is False
    assert raw.warnings


def test_zip_without_linkedin_csvs_is_unavailable():
    raw = parse_linkedin_export(_zip({"Ad_Targeting.csv": "Member Age\n25\n"}), _settings())
    assert raw.available is False
    assert any("no linkedin" in w.lower() for w in raw.warnings)


def test_row_cap_enforced():
    many = "Name\n" + "".join(f"skill{i}\n" for i in range(50))
    raw = parse_linkedin_export(_zip({"Skills.csv": many}), _settings(ps_linkedin_max_rows=10))
    assert len(raw.skills) == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_linkedin_parse.py -v`
Expected: FAIL (`ModuleNotFoundError: app.profile_sources.linkedin`).

- [ ] **Step 3: Implement `linkedin.py` (parse half)**

Create `app/profile_sources/linkedin.py`:

```python
"""Pure LinkedIn-export parse + raw → ProfileSourceSignal transform (S6.2).

No I/O beyond reading the in-memory ZIP bytes handed in; no network, no LLM. The
candidate uploads their own "Get a copy of your data" export. Advisory evidence
only. Self-reported skills are treated as CLAIMS (conservative confidence),
bumped only when a position/headline corroborates.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.candidates.normalize.orgs import (
    canonicalize_employer, canonicalize_institution,
)
from app.candidates.normalize.skills import normalize_skill
from app.core.config import Settings
from app.profile_sources.schema import (
    LinkedInActivity, ProfileSourceSignal, ProfileSourceType, SourceSkillSignal,
)


class LinkedInPositionRaw(BaseModel):
    company: str = ""
    title: str = ""
    description: str = ""
    started_on: str = ""
    finished_on: str = ""


class LinkedInEducationRaw(BaseModel):
    school: str = ""
    degree: str = ""


class LinkedInExportRaw(BaseModel):
    available: bool = False
    skills: list[str] = Field(default_factory=list)
    positions: list[LinkedInPositionRaw] = Field(default_factory=list)
    education: list[LinkedInEducationRaw] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    headline: Optional[str] = None
    industry: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


# Filename stems (lower-cased, no extension) we recognise inside the archive.
_KNOWN_STEMS = {"skills", "positions", "education", "profile", "certifications", "languages"}


def _find_member(names: list[str], stem: str) -> Optional[str]:
    """Return the archive member whose basename is ``<stem>.csv`` (case-insensitive),
    tolerating a nested export directory."""
    want = f"{stem}.csv"
    for n in names:
        if n.rsplit("/", 1)[-1].lower() == want:
            return n
    return None


def _read_rows(zf: zipfile.ZipFile, member: str, settings: Settings, warnings: list[str]) -> list[dict[str, str]]:
    try:
        with zf.open(member) as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace")
            reader = csv.DictReader(text)
            rows: list[dict[str, str]] = []
            for i, row in enumerate(reader):
                if i >= settings.ps_linkedin_max_rows:
                    break
                rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
            return rows
    except Exception as exc:  # a corrupt member is a warning, never a crash
        warnings.append(f"could not read {member}: {exc}")
        return []


def _col(row: dict[str, str], *names: str) -> str:
    for n in names:
        v = row.get(n, "")
        if v:
            return v
    return ""


def parse_linkedin_export(data: bytes, settings: Settings) -> LinkedInExportRaw:
    warnings: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError):
        return LinkedInExportRaw(available=False, warnings=["not a valid zip archive"])

    names = zf.namelist()
    members = {stem: _find_member(names, stem) for stem in _KNOWN_STEMS}
    if not any(members.values()):
        return LinkedInExportRaw(
            available=False, warnings=["no LinkedIn export CSVs found in archive"]
        )

    raw = LinkedInExportRaw(available=True)

    if members["skills"]:
        raw.skills = [
            _col(r, "Name") for r in _read_rows(zf, members["skills"], settings, warnings)
            if _col(r, "Name")
        ]
    if members["certifications"]:
        raw.certifications = [
            _col(r, "Name") for r in _read_rows(zf, members["certifications"], settings, warnings)
            if _col(r, "Name")
        ]
    if members["languages"]:
        raw.languages = [
            _col(r, "Name") for r in _read_rows(zf, members["languages"], settings, warnings)
            if _col(r, "Name")
        ]
    if members["positions"]:
        for r in _read_rows(zf, members["positions"], settings, warnings):
            raw.positions.append(LinkedInPositionRaw(
                company=_col(r, "Company Name", "Company"),
                title=_col(r, "Title"),
                description=_col(r, "Description"),
                started_on=_col(r, "Started On"),
                finished_on=_col(r, "Finished On"),
            ))
    if members["education"]:
        for r in _read_rows(zf, members["education"], settings, warnings):
            raw.education.append(LinkedInEducationRaw(
                school=_col(r, "School Name", "School"),
                degree=_col(r, "Degree Name", "Degree"),
            ))
    if members["profile"]:
        prows = _read_rows(zf, members["profile"], settings, warnings)
        if prows:
            raw.headline = _col(prows[0], "Headline") or None
            raw.industry = _col(prows[0], "Industry") or None

    raw.warnings = warnings
    return raw
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_linkedin_parse.py -v`
Expected: PASS (all 7).

- [ ] **Step 5: Commit**

```bash
git add app/profile_sources/linkedin.py tests/test_linkedin_parse.py
git commit -m "feat(s62): pure parse_linkedin_export (zip/csv, graceful degradation)"
```

---

### Task 4: Pure transform — `to_signal`

**Files:**
- Modify: `app/profile_sources/linkedin.py` (append the transform)
- Test: `tests/test_linkedin_transform.py`

**Interfaces:**
- Consumes: `LinkedInExportRaw` (Task 3), `Settings.ps_linkedin_skill_base_confidence`,
  `Settings.ps_linkedin_skill_corroborated_confidence`, `normalize_skill`,
  `canonicalize_employer`, `canonicalize_institution`, `LinkedInActivity`,
  `ProfileSourceSignal` (Task 2).
- Produces: `to_signal(raw: LinkedInExportRaw, settings: Settings, *,
  fetched_at: datetime) -> ProfileSourceSignal`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_linkedin_transform.py`:

```python
from datetime import datetime, timezone

from app.core.config import Settings
from app.profile_sources.linkedin import (
    LinkedInEducationRaw, LinkedInExportRaw, LinkedInPositionRaw, to_signal,
)
from app.profile_sources.schema import LinkedInActivity, ProfileSourceType

FETCHED = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _settings(**kw):
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def _raw(**kw):
    base = dict(available=True, skills=[], positions=[], education=[])
    base.update(kw)
    return LinkedInExportRaw(**base)


def test_maps_canonical_and_keeps_unknown():
    raw = _raw(skills=["Python", "Wingdings"])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.source_type == ProfileSourceType.LINKEDIN_EXPORT
    assert sig.method == "export"
    by = {s.name: s for s in sig.skills}
    assert by["Python"].canonical == "python"
    assert by["Wingdings"].canonical is None


def test_corroboration_bumps_confidence_and_weight():
    raw = _raw(
        skills=["Python", "Leadership"],
        positions=[LinkedInPositionRaw(title="Python Developer", description="Built services")],
        headline="Senior Python Engineer",
    )
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    by = {s.name: s for s in sig.skills}
    # Python appears in a position title AND the headline -> corroborated.
    assert by["Python"].confidence == 0.6
    assert by["Python"].weight >= 1
    # Leadership appears nowhere in positions/headline -> base.
    assert by["Leadership"].confidence == 0.4
    assert by["Leadership"].weight == 0
    # sorted corroborated-first.
    assert sig.skills[0].name == "Python"


def test_short_skill_names_do_not_substring_false_match():
    # "Go" must not match "Good"; token-based corroboration.
    raw = _raw(skills=["Go"], positions=[LinkedInPositionRaw(title="Good manager", description="")])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.skills[0].weight == 0
    assert sig.skills[0].confidence == 0.4


def test_duplicate_skill_collapses_keeping_max_corroboration():
    raw = _raw(skills=["Python", "python"],
               positions=[LinkedInPositionRaw(title="Python dev", description="")])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    pys = [s for s in sig.skills if s.name.lower() == "python"]
    assert len(pys) == 1
    assert pys[0].confidence == 0.6


def test_activity_aggregates_and_canonicalizes():
    raw = _raw(
        skills=["Python"],
        positions=[
            LinkedInPositionRaw(company="Infosys Technologies", finished_on="Dec 2021"),
            LinkedInPositionRaw(company="TCS", finished_on=""),
        ],
        education=[LinkedInEducationRaw(school="IIT Madras", degree="B.Tech")],
        certifications=["AWS SAA"],
        languages=["English", "Hindi"],
        headline="Engineer",
        industry="IT",
    )
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    act = sig.activity
    assert isinstance(act, LinkedInActivity)
    assert act.positions_count == 2
    assert act.current_positions == 1
    assert act.employers == ["Infosys", "TCS"]        # canonical, deduped, ordered
    assert act.institutions == ["IIT Madras"]
    assert act.education_count == 1
    assert act.certifications_count == 1
    assert act.languages == ["English", "Hindi"]
    assert act.skills_listed == 1


def test_unavailable_raw_yields_unavailable_signal():
    raw = LinkedInExportRaw(available=False, warnings=["not a valid zip archive"])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.method == "unavailable"
    assert sig.skills == []
    assert isinstance(sig.activity, LinkedInActivity)
    assert sig.warnings == ["not a valid zip archive"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_linkedin_transform.py -v`
Expected: FAIL (`ImportError: cannot import name 'to_signal'`).

- [ ] **Step 3: Append the transform to `linkedin.py`**

Add at the end of `app/profile_sources/linkedin.py`:

```python
# Tokens for whole-token corroboration: alnum plus the punctuation real skill
# names carry (c++, c#, .net). Short names ("go", "c", "r") match only as a
# standalone token, never as a substring.
_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _corroboration(skill: str, positions: list[LinkedInPositionRaw], headline: Optional[str]) -> int:
    """How many positions (title+description) + the headline mention the skill as
    a standalone token. A bounded evidence count, not a score."""
    tok = skill.lower().strip()
    if not tok:
        return 0
    count = 0
    for p in positions:
        if tok in _tokens(f"{p.title} {p.description}"):
            count += 1
    if headline and tok in _tokens(headline):
        count += 1
    return count


def _dedup(values: list[Optional[str]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _build_skills(raw: LinkedInExportRaw, settings: Settings) -> list[SourceSkillSignal]:
    best: dict[str, tuple[str, int]] = {}  # lower(name) -> (display, corroboration)
    for name in raw.skills:
        display = name.strip()
        if not display:
            continue
        corr = _corroboration(display, raw.positions, raw.headline)
        key = display.lower()
        if key not in best or corr > best[key][1]:
            best[key] = (display, corr)
    out: list[SourceSkillSignal] = []
    for display, corr in best.values():
        match = normalize_skill(display)
        conf = (
            settings.ps_linkedin_skill_corroborated_confidence if corr >= 1
            else settings.ps_linkedin_skill_base_confidence
        )
        out.append(SourceSkillSignal(
            name=display,
            canonical=match.canonical if match else None,
            category=match.category if match else None,
            weight=corr,
            confidence=round(conf, 4),
        ))
    out.sort(key=lambda s: (-s.weight, s.name.lower()))
    return out


def _build_activity(raw: LinkedInExportRaw) -> LinkedInActivity:
    employers = _dedup([canonicalize_employer(p.company) for p in raw.positions])
    institutions = _dedup([
        (m.canonical if (m := canonicalize_institution(e.school)) else None)
        for e in raw.education
    ])
    current = sum(1 for p in raw.positions if not p.finished_on.strip())
    return LinkedInActivity(
        positions_count=len(raw.positions),
        current_positions=current,
        employers=employers,
        education_count=len(raw.education),
        institutions=institutions,
        certifications_count=len(raw.certifications),
        languages=list(raw.languages),
        headline=raw.headline,
        industry=raw.industry,
        skills_listed=len(raw.skills),
    )


def to_signal(
    raw: LinkedInExportRaw, settings: Settings, *, fetched_at: datetime
) -> ProfileSourceSignal:
    if not raw.available:
        return ProfileSourceSignal(
            source_type=ProfileSourceType.LINKEDIN_EXPORT,
            identifier="linkedin_export",
            skills=[],
            activity=LinkedInActivity(),
            method="unavailable",
            fetched_at=fetched_at,
            warnings=list(raw.warnings),
        )
    return ProfileSourceSignal(
        source_type=ProfileSourceType.LINKEDIN_EXPORT,
        identifier="linkedin_export",
        skills=_build_skills(raw, settings),
        activity=_build_activity(raw),
        method="export",
        fetched_at=fetched_at,
        warnings=list(raw.warnings),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_linkedin_transform.py -v`
Expected: PASS (all 6).

- [ ] **Step 5: Commit**

```bash
git add app/profile_sources/linkedin.py tests/test_linkedin_transform.py
git commit -m "feat(s62): pure LinkedIn to_signal (taxonomy map + corroboration confidence)"
```

---

### Task 5: Service — `ingest_linkedin`

**Files:**
- Modify: `app/profile_sources/service.py`
- Test: `tests/test_profile_sources_service.py`

**Interfaces:**
- Consumes: `parse_linkedin_export` + `to_signal` (Tasks 3–4), the existing
  `ProfileSourceStore`, `CandidateStore`.
- Produces: `ProfileSourceService.ingest_linkedin(candidate_id: str, data: bytes)
  -> ProfileSourceSignal` (async).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_profile_sources_service.py` (helpers `make_candidate_store`,
`_bare_candidate`, `_service`, `_settings` already exist in that file). Add a zip
helper and tests:

```python
import io
import zipfile

from app.profile_sources.schema import ProfileSourceType


def _linkedin_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Skills.csv", "Name\nPython\n")
        zf.writestr("Positions.csv", "Company Name,Title,Finished On\nInfosys,Python Dev,\n")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_ingest_linkedin_persists_export_signal():
    cs = make_candidate_store()
    svc = _service(cs)
    cid = _bare_candidate(cs)
    sig = await svc.ingest_linkedin(cid, _linkedin_zip())
    assert sig.method == "export"
    assert sig.source_type == ProfileSourceType.LINKEDIN_EXPORT
    stored = svc.list_sources(cid, ProfileSourceType.LINKEDIN_EXPORT)
    assert len(stored) == 1
    assert stored[0].method == "export"


@pytest.mark.asyncio
async def test_ingest_linkedin_unknown_candidate_raises():
    cs = make_candidate_store()
    with pytest.raises(LookupError):
        await _service(cs).ingest_linkedin("nope", _linkedin_zip())


@pytest.mark.asyncio
async def test_ingest_linkedin_garbage_persists_unavailable():
    cs = make_candidate_store()
    svc = _service(cs)
    cid = _bare_candidate(cs)
    sig = await svc.ingest_linkedin(cid, b"not a zip")
    assert sig.method == "unavailable"
    assert svc.list_sources(cid)[0].method == "unavailable"


@pytest.mark.asyncio
async def test_erasure_sweeps_linkedin_rows():
    cs = make_candidate_store()
    svc = _service(cs)
    cid = _bare_candidate(cs)
    await svc.ingest_linkedin(cid, _linkedin_zip())
    cs.delete_candidate(cid)
    assert cs.get_candidate(cid) is None
    assert svc.list_sources(cid) == []   # CASCADE swept the row
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_profile_sources_service.py -v -k linkedin`
Expected: FAIL (`AttributeError: ... has no attribute 'ingest_linkedin'`).

- [ ] **Step 3: Implement `ingest_linkedin`**

In `app/profile_sources/service.py`, update the github import to an alias and add
the LinkedIn import (top of file, alongside the existing imports):

```python
from app.profile_sources.github import to_signal as github_to_signal
from app.profile_sources.linkedin import parse_linkedin_export
from app.profile_sources.linkedin import to_signal as linkedin_to_signal
```

Update the one call site inside `ingest_github` (`to_signal(...)` →
`github_to_signal(...)`). Then add the new method after `ingest_github`:

```python
    async def ingest_linkedin(
        self, candidate_id: str, data: bytes
    ) -> ProfileSourceSignal:
        if self._candidates.get_candidate(candidate_id) is None:
            raise LookupError(f"candidate {candidate_id} not found")
        raw = parse_linkedin_export(data, self._settings)
        signal = linkedin_to_signal(
            raw, self._settings, fetched_at=datetime.now(timezone.utc)
        )
        self._store.save_signal(candidate_id, signal)
        return signal
```

(`datetime`/`timezone` are already imported in `service.py`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_profile_sources_service.py -v`
Expected: PASS (existing GitHub service tests still green after the alias rename).

- [ ] **Step 5: Commit**

```bash
git add app/profile_sources/service.py tests/test_profile_sources_service.py
git commit -m "feat(s62): ProfileSourceService.ingest_linkedin"
```

---

### Task 6: API route — `POST /candidates/{id}/sources/linkedin`

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_profile_sources_api.py`

**Interfaces:**
- Consumes: `services.profile_sources.ingest_linkedin`,
  `services.settings.max_linkedin_b64_chars`.
- Produces: `POST /candidates/{candidate_id}/sources/linkedin` accepting
  `{"export_b64": str}` → 200 `ProfileSourceSignal`; 404 unknown candidate; 422
  bad base64 / oversize.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_profile_sources_api.py` (module already has `_client`,
`_candidate`, and imports `make_services`, `FakeGitHub`; add `base64/io/zipfile`):

```python
import base64
import io
import zipfile


def _linkedin_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Skills.csv", "Name\nPython\nLeadership\n")
        zf.writestr("Positions.csv", "Company Name,Title,Finished On\nInfosys,Python Dev,\n")
        zf.writestr("Profile.csv", "Headline,Industry\nPython Engineer,IT\n")
    return base64.b64encode(buf.getvalue()).decode()


def test_post_linkedin_source_available(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": _linkedin_b64()})
        assert r.status_code == 200
        body = r.json()
        assert body["method"] == "export"
        assert body["source_type"] == "linkedin_export"
        assert any(s["canonical"] == "python" for s in body["skills"])
        assert body["activity"]["employers"] == ["Infosys"]

        lst = client.get(f"/candidates/{cid}/sources?source_type=linkedin_export")
        assert lst.status_code == 200
        assert len(lst.json()["sources"]) == 1


def test_post_linkedin_wrong_zip_is_200_unavailable(settings, fake_github):
    services = make_services(settings, github=fake_github)
    b64 = base64.b64encode(_wrong_zip()).decode()
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": b64})
        assert r.status_code == 200
        assert r.json()["method"] == "unavailable"


def _wrong_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Ad_Targeting.csv", "Member Age\n25\n")
    return buf.getvalue()


def test_post_linkedin_bad_base64_is_422(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": "!!!not base64!!!"})
        assert r.status_code == 422


def test_post_linkedin_oversize_is_422(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        big = "A" * (services.settings.max_linkedin_b64_chars + 1)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": big})
        assert r.status_code == 422


def test_post_linkedin_unknown_candidate_is_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.post("/candidates/nope/sources/linkedin", json={"export_b64": _linkedin_b64()})
        assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_profile_sources_api.py -v -k linkedin`
Expected: FAIL (404 route not found → returns 404 for the wrong reason, and the
200/422 cases fail).

- [ ] **Step 3: Add the request model + route**

In `app/api/routes.py`, add `import base64` and `import binascii` to the imports
(top of file). Add the request model next to `GitHubSourceRequest`
(~line 351):

```python
class LinkedInSourceRequest(BaseModel):
    export_b64: str
```

Add the route immediately after `ingest_github_source` (~line 376):

```python
@router.post(
    "/candidates/{candidate_id}/sources/linkedin", response_model=ProfileSourceSignal
)
async def ingest_linkedin_source(
    candidate_id: str, req: LinkedInSourceRequest, request: Request
) -> ProfileSourceSignal:
    """Ingest a candidate's uploaded LinkedIn data export (base64 ZIP) as an
    advisory skill signal (S6.2). Malformed transport (bad base64 / oversize) is
    422; a valid file with no recognizable LinkedIn CSVs returns 200 with
    method='unavailable'."""
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    if len(req.export_b64) > services.settings.max_linkedin_b64_chars:
        raise HTTPException(
            status_code=422,
            detail=f"export_b64 exceeds max_linkedin_b64_chars={services.settings.max_linkedin_b64_chars}",
        )
    try:
        data = base64.b64decode(req.export_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="invalid_base64") from exc
    return await services.profile_sources.ingest_linkedin(candidate_id, data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_profile_sources_api.py -v`
Expected: PASS (GitHub API tests still green).

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py tests/test_profile_sources_api.py
git commit -m "feat(s62): POST /candidates/{id}/sources/linkedin endpoint"
```

---

### Task 7: Docs, smoke, ROADMAP

**Files:**
- Modify: `PROFILE_SOURCES.md`
- Create: `scripts/smoke_s62.py`
- Modify: `docs/ROADMAP.md`

**Interfaces:** none (documentation + a live smoke over the running app).

- [ ] **Step 1: Write `scripts/smoke_s62.py`**

Create `scripts/smoke_s62.py` (patterned on `smoke_s61.py`; key-less — this path
has no LLM and no network):

```python
"""S6.2 smoke: boot uvicorn on a migrated scratch DB, create a candidate, ingest
a LinkedIn export (base64 zip built in-script), list it, verify canonical skills +
corroboration + canonical employers, then bad-base64 -> 422 and DPDP-erase ->
sources 404. No network, no LLM. Run from repo root: python scripts/smoke_s62.py
"""

import base64
import io
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

PORT = 8062
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
RESUME = "Dev\nEmail: dev@example.com\nSKILLS\nPython\n"


def _export_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Skills.csv", "Name\nPython\nDjango\nLeadership\n")
        zf.writestr(
            "Positions.csv",
            "Company Name,Title,Description,Started On,Finished On\n"
            "Infosys,Python Developer,Built Django APIs,Jan 2020,Dec 2021\n"
            "TCS,Engineer,Kubernetes work,Jan 2022,\n",
        )
        zf.writestr("Education.csv", "School Name,Degree Name\nIIT Madras,B.Tech\n")
        zf.writestr("Profile.csv", "Headline,Industry\nSenior Python Engineer,Information Technology\n")
    return base64.b64encode(buf.getvalue()).decode()


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
    url = "sqlite:///" + (scratch / "smoke_s62.db").as_posix()
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

            r = c.post(f"/candidates/{cid}/sources/linkedin",
                       json={"export_b64": _export_b64()}, headers=admin_h)
            checks["POST linkedin -> 200"] = r.status_code == 200
            body = r.json() if r.status_code == 200 else {}
            checks["method == export"] = body.get("method") == "export"
            skills = {s["name"]: s for s in body.get("skills", [])}
            checks["python canonical"] = skills.get("Python", {}).get("canonical") == "python"
            checks["python corroborated (0.6)"] = skills.get("Python", {}).get("confidence") == 0.6
            checks["leadership base (0.4)"] = skills.get("Leadership", {}).get("confidence") == 0.4
            act = body.get("activity", {})
            checks["employers canonicalized"] = act.get("employers") == ["Infosys", "TCS"]
            checks["institutions canonicalized"] = act.get("institutions") == ["IIT Madras"]
            checks["current_positions == 1"] = act.get("current_positions") == 1

            lst = c.get(f"/candidates/{cid}/sources?source_type=linkedin_export", headers=admin_h)
            checks["GET linkedin sources -> 1 row"] = (
                lst.status_code == 200 and len(lst.json()["sources"]) == 1
            )

            bad = c.post(f"/candidates/{cid}/sources/linkedin",
                         json={"export_b64": "!!!not base64!!!"}, headers=admin_h)
            checks["bad base64 -> 422"] = bad.status_code == 422

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

Run: `python scripts/smoke_s62.py`
Expected: every check `OK`, final `SMOKE OK`, exit 0. (If a check fails, fix the
product code — the smoke is the acceptance gate.)

- [ ] **Step 3: Update `PROFILE_SOURCES.md`**

Change the title/intro to cover both adapters, and add a LinkedIn section after
the GitHub pipeline documenting: the base64-zip upload transport; the pure
`parse_linkedin_export` → `to_signal` seams; the conservative + corroboration
confidence model (0.4 / 0.6); the de-identified `LinkedInActivity` (no raw contact
PII / summary); the discriminated-union `activity` + `source_type`-derived
back-compat validator (no migration); `method="export"`; the endpoint contract
(200 / 200-unavailable / 404 / 422); the new config knobs. Note the curation loop
is now S6.3.

- [ ] **Step 4: Update `docs/ROADMAP.md`**

- Status board PI-6: mark S6.2 `[x]` and relabel it "LinkedIn export parsing
  (2nd profile_sources adapter)"; add `[ ] S6.3 Normalization curation loop` and
  `[ ] S6.4 Candidate auth + DPDP portal` (moving the portal from S6.3 to S6.4).
- "Current sprint" / "Next action": record S6.2 done, next = S6.3 (curation loop).
- Add a session-log entry summarizing the sprint (new test count, smoke result).

- [ ] **Step 5: Run the full suite + commit**

```bash
pytest -q
git add PROFILE_SOURCES.md scripts/smoke_s62.py docs/ROADMAP.md
git commit -m "docs(s62): PROFILE_SOURCES LinkedIn section + smoke_s62 + ROADMAP (PI-6 reshape)"
```

Expected: `pytest -q` green (697 → ~725).

---

## Self-Review

**1. Spec coverage:**
- §5.1 schema generalization (LINKEDIN_EXPORT, LinkedInActivity, union, back-compat
  validator, method="export") → Task 2. ✓
- §5.2 `parse_linkedin_export` (graceful degradation, column variants, nested dirs,
  row cap) → Task 3. ✓
- §5.2 `to_signal` (taxonomy mapping, corroboration confidence, dedup, activity,
  unavailable path, token-based matching) → Task 4. ✓
- §5.3 `ingest_linkedin` (existence check, parse→transform→persist, "linkedin_export"
  identifier) → Task 5. ✓
- §5.4 store reuse / CASCADE / filter → Task 5 tests. ✓
- §6 API (200 / 200-unavailable / 404 / 422 bad-b64 / 422 oversize) → Task 6. ✓
- §7 DPDP (no new consent purpose; CASCADE) → Task 5 erasure test; docs Task 7. ✓
- §8 config knobs → Task 1. ✓
- §9 tests + smoke → every task's tests + Task 7 smoke. ✓
- §11 deliverables (PROFILE_SOURCES.md, smoke_s62, ROADMAP reshape) → Task 7. ✓

**2. Placeholder scan:** No TBD/TODO; every code + test block is concrete. ✓

**3. Type consistency:** `parse_linkedin_export(data, settings) -> LinkedInExportRaw`
and `to_signal(raw, settings, *, fetched_at) -> ProfileSourceSignal` are used
identically in Tasks 3–5. `LinkedInActivity` field names
(`employers`/`institutions`/`current_positions`/`skills_listed`) match across schema
(Task 2), transform (Task 4), API test + smoke (Tasks 6–7). `ingest_linkedin(cid,
data: bytes)` consistent across service (Task 5) and route (Task 6). The github
import alias rename (`github_to_signal`) is applied at its one call site in the same
task (Task 5). ✓

## Execution Handoff

Plan complete. Two execution options — see below.
