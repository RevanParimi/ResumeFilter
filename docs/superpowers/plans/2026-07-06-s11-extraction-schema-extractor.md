# S1.1 — Prod-Grade Extraction Schema + Extractor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `CandidateProfile` schema (identity, hashed contact, education[], experience[], skills[], projects[], certifications[], links[] — each with per-field confidence + source-span provenance) and an `extract_profile()` extractor with an LLM primary path and a fully deterministic fallback.

**Architecture:** New `app/candidates/` package beside the existing vetting graph (modular monolith, per spec). `schema.py` holds the Pydantic contracts, `hashing.py` the contact-dedup hashing, `dates.py` deterministic date-range parsing, `extractor.py` the LLM+heuristic extractor. Nothing in `app/graph/` changes this sprint — API/engine wiring is S1.3, the DB store is S1.2.

**Tech Stack:** Python 3.11+, Pydantic v2, existing `LLMClient` abstraction (`app/services/llm.py`, `parsing` tier), pytest with `asyncio_mode=auto` (plain `async def test_` works, no decorator).

## Global Constraints

- Tests are **fully offline**: `NullLLM`/`FakeLLM` only, no network, no API key. `pytest -q` green before merge.
- The LLM path must degrade: no key / bad JSON / exception ⇒ deterministic heuristic path produces a usable profile.
- DPDP: only first-party resume content is parsed. Contact hashes are salted SHA-256 of normalized values; the salt is a **stable config.yaml tunable named exactly `contact_hash_salt`, default `"veritas-dedup-v1"`** (not a secret — changing it orphans stored hashes).
- Config: tunables go in `config.yaml` + `app/core/config.py` (`DEE_*` env override comes free); secrets only in `.env`.
- Advisory only — this sprint extracts data; it renders no judgments.
- Follow existing code style: module docstring stating design intent, `from __future__ import annotations`, `structlog` via `app.core.logging.get_logger`, node/services patterns as in `app/graph/nodes/claim_extraction.py`.
- Run commands from the repo root: `c:\Users\RevanParimi\OneDrive - IBM\Documents\Gen AI Projects\depth-eval-resume-engine`.

---

### Task 1: Schema primitives — `SourceSpan`, `ExtractedStr`, `DateRange`

**Files:**
- Create: `app/candidates/__init__.py`
- Create: `app/candidates/schema.py`
- Test: `tests/test_candidate_schema.py`

**Interfaces:**
- Consumes: nothing (leaf module; imports only pydantic/stdlib).
- Produces: `SourceSpan(start: int, end: int, text: str)` (validates `end >= start`), `ExtractedStr(value: str, confidence: float = 0.5, span: SourceSpan | None)`, `DateRange(start: str | None, end: str | None, is_current: bool = False)` — date points are `"YYYY-MM"` or `"YYYY"` strings. Every later task builds on these exact names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_candidate_schema.py`:

```python
"""Schema contracts for the candidate extraction models (S1.1)."""

import pytest
from pydantic import ValidationError

from app.candidates.schema import DateRange, ExtractedStr, SourceSpan


def test_source_span_rejects_reversed_range():
    with pytest.raises(ValidationError):
        SourceSpan(start=10, end=5, text="x")


def test_source_span_accepts_ordered_range():
    span = SourceSpan(start=3, end=8, text="hello")
    assert (span.start, span.end, span.text) == (3, 8, "hello")


def test_extracted_str_confidence_bounds():
    with pytest.raises(ValidationError):
        ExtractedStr(value="x", confidence=1.5)
    with pytest.raises(ValidationError):
        ExtractedStr(value="x", confidence=-0.1)


def test_extracted_str_defaults():
    f = ExtractedStr(value="Arjun")
    assert f.confidence == 0.5 and f.span is None


def test_date_range_defaults_to_open():
    d = DateRange()
    assert d.start is None and d.end is None and d.is_current is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_candidate_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.candidates'`

- [ ] **Step 3: Write the minimal implementation**

Create `app/candidates/__init__.py`:

```python
"""Candidate data backbone (PI-1): extraction schema, extractor, normalizers.

Peer subsystem to the vetting graph (see docs spec 2026-07-06). The graph
never imports this package; wiring into the API/engine happens in S1.3.
"""
```

Create `app/candidates/schema.py`:

```python
"""Candidate extraction contracts (PI-1 / S1.1).

Every extracted value carries PER-FIELD CONFIDENCE and SOURCE-SPAN PROVENANCE
back to the exact resume text it came from, so downstream consumers (store,
fabrication forensics, ML features) can audit any field to its origin.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class SourceSpan(BaseModel):
    """Character range in the normalized resume text a value was lifted from."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str = ""

    @model_validator(mode="after")
    def _ordered(self) -> "SourceSpan":
        if self.end < self.start:
            raise ValueError("span end must be >= start")
        return self


class ExtractedStr(BaseModel):
    """A scalar string field with extraction confidence + provenance."""

    value: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class DateRange(BaseModel):
    """A career period. Points are "YYYY-MM" or "YYYY" strings — resumes
    rarely carry day precision, and strings stay SQLite/JSON-friendly."""

    start: Optional[str] = None
    end: Optional[str] = None
    is_current: bool = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_candidate_schema.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add app/candidates/__init__.py app/candidates/schema.py tests/test_candidate_schema.py
git commit -m "feat(candidates): S1.1 schema primitives — SourceSpan, ExtractedStr, DateRange"
```

---

### Task 2: Entity models + `CandidateProfile` + `ExtractionResult`

**Files:**
- Modify: `app/candidates/schema.py` (append)
- Test: `tests/test_candidate_schema.py` (append)

**Interfaces:**
- Consumes: Task 1 primitives.
- Produces (exact names later tasks use):
  - `EmploymentType` StrEnum: `FULL_TIME/PART_TIME/INTERNSHIP/CONTRACT/FREELANCE/UNKNOWN` (values `"full_time"` etc.)
  - `LinkType` StrEnum: `GITHUB/LINKEDIN/PORTFOLIO/OTHER`
  - `ContactInfo(email/phone/location: ExtractedStr|None, email_hash/phone_hash: str|None)`
  - `EducationEntry(id, degree, field_of_study, institution, grade_value: float|None, grade_scale: str|None, dates: DateRange, confidence, span)`
  - `ExperienceEntry(id, employer, title, seniority: str|None, employment_type: EmploymentType, dates, confidence, span)`
  - `SkillItem(name, confidence, span)` · `ProjectEntry(id, name, description, technologies: list[str], url, confidence, span)` · `CertificationEntry(id, name, issuer, year: int|None, confidence, span)` · `LinkItem(type: LinkType, url, confidence=1.0, span)`
  - `CandidateProfile(id, full_name/headline: ExtractedStr|None, contact: ContactInfo, education/experience/skills/projects/certifications/links: lists)`
  - `ExtractionResult(profile: CandidateProfile, method: Literal["llm","heuristic"], warnings: list[str])`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_candidate_schema.py`:

```python
from app.candidates.schema import (
    CandidateProfile,
    EducationEntry,
    EmploymentType,
    ExperienceEntry,
    ExtractionResult,
)


def test_empty_profile_constructs_with_defaults():
    p = CandidateProfile()
    assert p.id.startswith("cand_")
    assert p.education == [] and p.skills == [] and p.links == []
    assert p.contact.email is None and p.contact.email_hash is None


def test_profile_json_round_trip():
    p = CandidateProfile(
        full_name=ExtractedStr(
            value="Arjun Mehta",
            confidence=0.9,
            span=SourceSpan(start=0, end=11, text="Arjun Mehta"),
        ),
        education=[
            EducationEntry(
                degree="B.Tech",
                field_of_study="Computer Science",
                institution="NIT Trichy",
                grade_value=8.6,
                grade_scale="cgpa_10",
                dates=DateRange(start="2014", end="2018"),
                confidence=0.8,
            )
        ],
        experience=[
            ExperienceEntry(
                employer="Flipkart",
                title="Senior Data Engineer",
                seniority="senior",
                employment_type=EmploymentType.FULL_TIME,
                dates=DateRange(start="2021-06", is_current=True),
                confidence=0.7,
            )
        ],
    )
    restored = CandidateProfile.model_validate_json(p.model_dump_json())
    assert restored == p
    assert restored.education[0].id.startswith("edu_")
    assert restored.experience[0].id.startswith("exp_")


def test_extraction_result_methods_are_constrained():
    with pytest.raises(ValidationError):
        ExtractionResult(profile=CandidateProfile(), method="magic")
    ok = ExtractionResult(profile=CandidateProfile(), method="heuristic")
    assert ok.warnings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_candidate_schema.py -q`
Expected: FAIL — `ImportError: cannot import name 'CandidateProfile'`

- [ ] **Step 3: Write the implementation**

Append to `app/candidates/schema.py` (add `import uuid`, `from enum import StrEnum`, `from typing import Literal` to the imports):

```python
class ContactInfo(BaseModel):
    """First-party contact data. Raw values stay (the candidate submitted
    them); *_hash fields let S1.2 identity resolution dedup across resumes
    without comparing raw values. Delete paths arrive with the store (S1.2)."""

    email: Optional[ExtractedStr] = None
    phone: Optional[ExtractedStr] = None
    location: Optional[ExtractedStr] = None
    email_hash: Optional[str] = None
    phone_hash: Optional[str] = None


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    INTERNSHIP = "internship"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    UNKNOWN = "unknown"


class LinkType(StrEnum):
    GITHUB = "github"
    LINKEDIN = "linkedin"
    PORTFOLIO = "portfolio"
    OTHER = "other"


class EducationEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"edu_{uuid.uuid4().hex[:10]}")
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    institution: Optional[str] = None
    # Grade exactly as claimed; canonical CGPA normalization is S1.4's job.
    grade_value: Optional[float] = None
    grade_scale: Optional[str] = None  # "cgpa_10" | "cgpa_4" | "percentage"
    dates: DateRange = Field(default_factory=DateRange)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class ExperienceEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"exp_{uuid.uuid4().hex[:10]}")
    employer: Optional[str] = None
    title: Optional[str] = None
    seniority: Optional[str] = None  # junior | mid | senior | staff
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    dates: DateRange = Field(default_factory=DateRange)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class SkillItem(BaseModel):
    name: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class ProjectEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"prj_{uuid.uuid4().hex[:10]}")
    name: str
    description: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class CertificationEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"crt_{uuid.uuid4().hex[:10]}")
    name: str
    issuer: Optional[str] = None
    year: Optional[int] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class LinkItem(BaseModel):
    """A URL the candidate shared. Verbatim from the resume ⇒ confidence 1.0."""

    type: LinkType = LinkType.OTHER
    url: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    span: Optional[SourceSpan] = None


class CandidateProfile(BaseModel):
    """The S1.1 contract: everything the extractor lifted from ONE resume."""

    id: str = Field(default_factory=lambda: f"cand_{uuid.uuid4().hex[:10]}")
    full_name: Optional[ExtractedStr] = None
    headline: Optional[ExtractedStr] = None
    contact: ContactInfo = Field(default_factory=ContactInfo)
    education: list[EducationEntry] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    skills: list[SkillItem] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    links: list[LinkItem] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Output of extract_profile(): the profile + how it was produced."""

    profile: CandidateProfile
    method: Literal["llm", "heuristic"]
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_candidate_schema.py -q`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add app/candidates/schema.py tests/test_candidate_schema.py
git commit -m "feat(candidates): CandidateProfile entity models + ExtractionResult"
```

---

### Task 3: Contact normalization + salted dedup hashing

**Files:**
- Create: `app/candidates/hashing.py`
- Modify: `app/core/config.py` (add `contact_hash_salt` after the report-store section)
- Modify: `config.yaml` (add a Candidates section after `report_db_path`)
- Test: `tests/test_contact_hashing.py`

**Interfaces:**
- Consumes: `CandidateProfile`, `ContactInfo` from Task 2; `Settings` gains field `contact_hash_salt: str = "veritas-dedup-v1"`.
- Produces: `normalize_email(email: str) -> str`, `normalize_phone(phone: str, default_country: str = "91") -> str` (returns `""` when not phone-shaped), `contact_hash(normalized: str, salt: str) -> str` (hex sha256), `apply_contact_hashes(profile: CandidateProfile, salt: str) -> None` (in-place). Task 6's `extract_profile` calls `apply_contact_hashes`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_contact_hashing.py`:

```python
"""Contact dedup hashing (S1.1): same person ⇒ same hash, salt-scoped."""

from app.candidates.hashing import (
    apply_contact_hashes,
    contact_hash,
    normalize_email,
    normalize_phone,
)
from app.candidates.schema import CandidateProfile, ContactInfo, ExtractedStr


def test_email_normalization_is_case_and_space_insensitive():
    a = normalize_email("  Arjun.Mehta@Example.COM ")
    b = normalize_email("arjun.mehta@example.com")
    assert a == b == "arjun.mehta@example.com"


def test_indian_phone_formats_normalize_identically():
    forms = ["+91 98765 43210", "098765 43210", "9876543210", "+91-98765-43210"]
    assert {normalize_phone(f) for f in forms} == {"+919876543210"}


def test_non_phone_input_normalizes_to_empty():
    assert normalize_phone("123") == ""
    assert normalize_phone("call me") == ""


def test_contact_hash_is_salt_scoped_and_deterministic():
    h1 = contact_hash("arjun@example.com", salt="veritas-dedup-v1")
    h2 = contact_hash("arjun@example.com", salt="veritas-dedup-v1")
    h3 = contact_hash("arjun@example.com", salt="other-salt")
    assert h1 == h2 and h1 != h3 and len(h1) == 64


def test_apply_contact_hashes_fills_profile_in_place():
    profile = CandidateProfile(
        contact=ContactInfo(
            email=ExtractedStr(value="Arjun.Mehta@Example.com"),
            phone=ExtractedStr(value="+91 98765 43210"),
        )
    )
    apply_contact_hashes(profile, salt="veritas-dedup-v1")
    assert profile.contact.email_hash == contact_hash(
        "arjun.mehta@example.com", "veritas-dedup-v1"
    )
    assert profile.contact.phone_hash == contact_hash(
        "+919876543210", "veritas-dedup-v1"
    )


def test_apply_contact_hashes_skips_missing_or_invalid():
    profile = CandidateProfile(
        contact=ContactInfo(phone=ExtractedStr(value="not a phone"))
    )
    apply_contact_hashes(profile, salt="veritas-dedup-v1")
    assert profile.contact.email_hash is None
    assert profile.contact.phone_hash is None


def test_settings_expose_contact_hash_salt(settings):
    assert settings.contact_hash_salt == "veritas-dedup-v1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_contact_hashing.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.candidates.hashing'`

- [ ] **Step 3: Write the implementation**

Create `app/candidates/hashing.py`:

```python
"""Contact normalization + salted hashing for identity dedup (DPDP-lean).

S1.2 resolves "same candidate, new resume" by comparing these hashes instead
of raw contact values. The salt is a config.yaml tunable, NOT a secret — it
must stay stable across deploys or dedup breaks; changing it orphans every
stored hash.
"""

from __future__ import annotations

import hashlib
import re

from app.candidates.schema import CandidateProfile

_NON_DIGITS = re.compile(r"\D+")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(phone: str, default_country: str = "91") -> str:
    """Reduce a phone to '+<country><number>'; '' when not phone-shaped.

    Indian resumes write the same number as '+91 98765 43210',
    '098765 43210' or '9876543210' — all must hash identically.
    """
    digits = _NON_DIGITS.sub("", phone).lstrip("0")
    if len(digits) == 10:
        digits = default_country + digits
    if not 11 <= len(digits) <= 15:
        return ""
    return "+" + digits


def contact_hash(normalized: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{normalized}".encode("utf-8")).hexdigest()


def apply_contact_hashes(profile: CandidateProfile, salt: str) -> None:
    """Fill contact.*_hash in place from the raw extracted values."""
    contact = profile.contact
    if contact.email and contact.email.value:
        contact.email_hash = contact_hash(normalize_email(contact.email.value), salt)
    if contact.phone and contact.phone.value:
        normalized = normalize_phone(contact.phone.value)
        if normalized:
            contact.phone_hash = contact_hash(normalized, salt)
```

In `app/core/config.py`, after the report-store block (`report_db_path: str = "./data/reports.db"`), add:

```python
    # --- Candidates (PI-1) ------------------------------------------------------
    # Salt for contact dedup hashes (email/phone). NOT a secret — it must stay
    # stable across deploys or identity resolution breaks; changing it orphans
    # every stored hash.
    contact_hash_salt: str = "veritas-dedup-v1"
```

In `config.yaml`, after the `report_db_path` line, add:

```yaml
# --- Candidates (PI-1) ---------------------------------------------------------
# Salt for contact dedup hashes (email/phone). Stable across deploys; NOT a secret.
contact_hash_salt: "veritas-dedup-v1"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_contact_hashing.py -q`
Expected: `7 passed`

- [ ] **Step 5: Run the full suite (config change touches everything)**

Run: `pytest -q`
Expected: all tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add app/candidates/hashing.py app/core/config.py config.yaml tests/test_contact_hashing.py
git commit -m "feat(candidates): contact normalization + salted dedup hashing (contact_hash_salt config)"
```

---

### Task 4: Deterministic date-range parser

**Files:**
- Create: `app/candidates/dates.py`
- Test: `tests/test_candidate_dates.py`

**Interfaces:**
- Consumes: `DateRange` from Task 1.
- Produces: `date_points(text: str) -> list[tuple[int, str]]` (ordered `(char_pos, "YYYY-MM"|"YYYY")` tokens), `parse_date_range(text: str) -> DateRange`, `has_date_range(text: str) -> bool`. Task 5's heuristic extractor uses all three (`date_points` to slice the title/employer head off an experience line).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_candidate_dates.py`:

```python
"""Deterministic career date-range parsing (S1.1)."""

from app.candidates.dates import date_points, has_date_range, parse_date_range


def test_month_year_range_with_present():
    d = parse_date_range("Jun 2021 - Present")
    assert d.start == "2021-06" and d.end is None and d.is_current is True


def test_full_month_names_and_to_separator():
    d = parse_date_range("January 2020 to March 2022")
    assert d.start == "2020-01" and d.end == "2022-03" and d.is_current is False


def test_year_only_range():
    d = parse_date_range("2014 - 2018")
    assert d.start == "2014" and d.end == "2018" and d.is_current is False


def test_numeric_month_slash_year():
    d = parse_date_range("03/2021 - 06/2023")
    assert d.start == "2021-03" and d.end == "2023-06"


def test_no_dates_returns_open_range():
    d = parse_date_range("Built streaming pipelines processing 2TB/day")
    assert d.start is None and d.end is None


def test_date_points_positions_are_ordered():
    pts = date_points("Data Engineer, Infosys — Jul 2018 - May 2021")
    assert [v for _, v in pts] == ["2018-07", "2021-05"]
    assert pts[0][0] < pts[1][0]


def test_has_date_range_detects_career_lines():
    assert has_date_range("Jun 2021 - Present") is True
    assert has_date_range("2014 - 2018, CGPA: 8.6/10") is True
    assert has_date_range("Built pipelines processing 2TB/day") is False
    assert has_date_range("CGPA: 8.6/10") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_candidate_dates.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.candidates.dates'`

- [ ] **Step 3: Write the implementation**

Create `app/candidates/dates.py`:

```python
"""Deterministic date parsing for resume career lines.

Handles the formats Indian resumes actually use: 'Jun 2021 - Present',
'January 2020 to March 2022', '2014 - 2018', '03/2021 - 06/2023'. Points are
kept as "YYYY-MM"/"YYYY" strings (see DateRange). No LLM anywhere.
"""

from __future__ import annotations

import re

from app.candidates.schema import DateRange

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_YEAR = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_NUMERIC_MY = re.compile(r"\b(0?[1-9]|1[0-2])[/-]((?:19|20)\d{2})\b")
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_PRESENT = re.compile(r"\b(present|current|till date|ongoing|now)\b", re.IGNORECASE)


def date_points(text: str) -> list[tuple[int, str]]:
    """All (position, 'YYYY-MM'|'YYYY') date tokens, in order of appearance."""
    found: list[tuple[int, int, str]] = []  # (start, end, value)
    for m in _MONTH_YEAR.finditer(text):
        month = _MONTHS[m.group(1).lower()[:3]]
        found.append((m.start(), m.end(), f"{m.group(2)}-{month:02d}"))
    for m in _NUMERIC_MY.finditer(text):
        found.append((m.start(), m.end(), f"{m.group(2)}-{int(m.group(1)):02d}"))
    covered = [(s, e) for s, e, _ in found]
    for m in _YEAR.finditer(text):
        if not any(s <= m.start() < e for s, e in covered):
            found.append((m.start(), m.end(), m.group(1)))
    found.sort()
    return [(s, v) for s, _, v in found]


def parse_date_range(text: str) -> DateRange:
    points = date_points(text)
    current = bool(_PRESENT.search(text))
    if not points:
        return DateRange(is_current=current)
    start = points[0][1]
    end = points[1][1] if len(points) > 1 else None
    return DateRange(start=start, end=end, is_current=current and end is None)


def has_date_range(text: str) -> bool:
    """True when a line reads like a dated career entry: two date points, or
    one point plus a 'Present'-style marker."""
    points = date_points(text)
    return len(points) >= 2 or (len(points) == 1 and bool(_PRESENT.search(text)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_candidate_dates.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add app/candidates/dates.py tests/test_candidate_dates.py
git commit -m "feat(candidates): deterministic date-range parser for career lines"
```

---

### Task 5: Deterministic (heuristic) profile extractor + fixture

**Files:**
- Create: `app/candidates/extractor.py` (heuristic half; LLM half arrives in Task 6)
- Create: `tests/fixtures/full_profile_resume.txt`
- Test: `tests/test_candidate_extractor_heuristic.py`

**Interfaces:**
- Consumes: schema models (Task 2), `date_points`/`parse_date_range`/`has_date_range` (Task 4).
- Produces: `heuristic_profile(text: str) -> CandidateProfile` (public — Task 6's `extract_profile` and tests call it). Section-based parsing; every entry carries a `SourceSpan` whose `text` slice matches the resume exactly.

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/full_profile_resume.txt` (exact content, keep formatting):

```text
Arjun Mehta
Senior Data Engineer | Bengaluru, Karnataka
Email: arjun.mehta@example.com | Phone: +91 98765 43210
GitHub: https://github.com/arjun-mehta | LinkedIn: https://www.linkedin.com/in/arjun-mehta

EXPERIENCE
Senior Data Engineer, Flipkart — Jun 2021 - Present
- Built streaming pipelines on Kafka and Spark processing 2TB/day.
Data Engineer, Infosys — Jul 2018 - May 2021
- Developed ETL workflows in Airflow for retail clients.

EDUCATION
B.Tech in Computer Science, NIT Trichy — 2014 - 2018, CGPA: 8.6/10

SKILLS
Python, SQL, Apache Spark, Kafka, Airflow, AWS

PROJECTS
open-lineage-tracker — https://github.com/arjun-mehta/open-lineage-tracker
- Metadata lineage tracking tool for Spark jobs.

CERTIFICATIONS
AWS Certified Data Analytics - Specialty, Amazon Web Services, 2022
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_candidate_extractor_heuristic.py`:

```python
"""Deterministic extractor path (S1.1) — must work with zero LLM."""

from pathlib import Path

import pytest

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import EmploymentType, LinkType

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def full_resume() -> str:
    return (FIXTURES / "full_profile_resume.txt").read_text(encoding="utf-8")


def test_identity_and_contact(full_resume):
    p = heuristic_profile(full_resume)
    assert p.full_name is not None and p.full_name.value == "Arjun Mehta"
    assert p.headline is not None and "Data Engineer" in p.headline.value
    assert p.contact.email is not None
    assert p.contact.email.value == "arjun.mehta@example.com"
    assert p.contact.email.confidence >= 0.9
    assert p.contact.phone is not None and "98765" in p.contact.phone.value


def test_education_entry(full_resume):
    p = heuristic_profile(full_resume)
    assert len(p.education) == 1
    edu = p.education[0]
    assert edu.degree == "B.Tech"
    assert edu.field_of_study == "Computer Science"
    assert edu.institution == "NIT Trichy"
    assert edu.grade_value == 8.6 and edu.grade_scale == "cgpa_10"
    assert edu.dates.start == "2014" and edu.dates.end == "2018"


def test_experience_entries(full_resume):
    p = heuristic_profile(full_resume)
    assert len(p.experience) == 2
    first, second = p.experience
    assert first.title == "Senior Data Engineer" and first.employer == "Flipkart"
    assert first.seniority == "senior"
    assert first.dates.start == "2021-06" and first.dates.is_current is True
    assert second.employer == "Infosys"
    assert second.dates.start == "2018-07" and second.dates.end == "2021-05"
    # Bullet lines under an entry are NOT separate entries.
    assert all(e.employment_type == EmploymentType.UNKNOWN for e in p.experience)


def test_skills_projects_certifications_links(full_resume):
    p = heuristic_profile(full_resume)
    skills = {s.name for s in p.skills}
    assert {"Python", "SQL", "Kafka", "AWS"} <= skills
    assert len(p.projects) == 1
    prj = p.projects[0]
    assert prj.name == "open-lineage-tracker"
    assert prj.url == "https://github.com/arjun-mehta/open-lineage-tracker"
    assert prj.description is not None and "lineage" in prj.description.lower()
    assert len(p.certifications) == 1
    crt = p.certifications[0]
    assert crt.year == 2022 and crt.issuer == "Amazon Web Services"
    link_types = {l.type for l in p.links}
    assert LinkType.GITHUB in link_types and LinkType.LINKEDIN in link_types


def test_every_span_slices_back_into_the_resume(full_resume):
    p = heuristic_profile(full_resume)
    entries = (
        list(p.education) + list(p.experience) + list(p.projects)
        + list(p.certifications) + list(p.links)
    )
    assert entries, "extractor produced nothing"
    for e in entries:
        assert e.span is not None
        assert full_resume[e.span.start : e.span.end] == e.span.text
    assert p.contact.email is not None and p.contact.email.span is not None
    s = p.contact.email.span
    assert full_resume[s.start : s.end] == s.text


def test_unstructured_resume_degrades_gracefully(full_resume):
    # No section headers at all → still finds contact + links, crashes never.
    p = heuristic_profile("Reach me at someone@example.com or +91 98765 43210")
    assert p.contact.email is not None
    assert p.education == [] and p.experience == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_candidate_extractor_heuristic.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.candidates.extractor'`

- [ ] **Step 4: Write the implementation**

Create `app/candidates/extractor.py`:

```python
"""Resume → CandidateProfile extraction (S1.1).

Primary path (Task 6): LLM (parsing tier) returns the profile as JSON with
per-field confidence and verbatim source excerpts, which are re-located in the
resume to produce character spans. Fallback path (this file's heuristic half):
a deterministic section parser, so the pipeline works offline with no API key
— the same NullLLM degradation contract as the eval graph.

Heuristic confidences are fixed by evidence strength: regex-matched contact
0.85–0.95, section-structured entries 0.5–0.7. They are honest priors, not
measurements.
"""

from __future__ import annotations

import re
from typing import Optional

from app.candidates.dates import date_points, has_date_range, parse_date_range
from app.candidates.schema import (
    CandidateProfile,
    CertificationEntry,
    ContactInfo,
    EducationEntry,
    EmploymentType,
    ExperienceEntry,
    ExtractedStr,
    LinkItem,
    LinkType,
    ProjectEntry,
    SkillItem,
    SourceSpan,
)
from app.core.logging import get_logger

log = get_logger("candidates.extractor")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\+?91[-\s]?)?0?[6-9]\d{4}[-\s]?\d{5}\b")
_URL = re.compile(r"https?://[^\s)>\]]+")
_DEGREE = re.compile(
    r"\b(b\.?\s?tech|m\.?\s?tech|b\.?e\b|m\.?e\b|b\.?sc|m\.?sc|bca|mca|mba|"
    r"ph\.?d|b\.?com|m\.?com|diploma)\b",
    re.IGNORECASE,
)
_GRADE = re.compile(
    r"(?:cgpa|gpa)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+))?", re.IGNORECASE
)
_PERCENT = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*%")
_BULLET = re.compile(r"^[-•*·]\s*")

_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "education": ("education", "academics", "academic background", "qualifications"),
    "experience": (
        "experience", "work experience", "professional experience",
        "employment", "employment history", "work history",
    ),
    "skills": ("skills", "technical skills", "core skills", "skill set", "technologies"),
    "projects": ("projects", "personal projects", "key projects", "academic projects"),
    "certifications": (
        "certifications", "certificates", "licenses",
        "licenses & certifications", "courses & certifications",
    ),
}
_SENIORITY_HINTS: tuple[tuple[str, str], ...] = (
    ("principal", "staff"), ("staff", "staff"), ("lead", "senior"),
    ("senior", "senior"), ("sr.", "senior"), ("junior", "junior"),
    ("jr.", "junior"), ("intern", "junior"),
)


def _line_span(start: int, line: str) -> SourceSpan:
    return SourceSpan(start=start, end=start + len(line), text=line)


def _split_sections(text: str) -> dict[str, list[tuple[int, str]]]:
    """Map section → [(char_offset_of_stripped_line, stripped_line)].
    Content before any recognized header lands in pseudo-section 'header'."""
    alias_to_section = {
        alias: section
        for section, aliases in _SECTION_ALIASES.items()
        for alias in aliases
    }
    sections: dict[str, list[tuple[int, str]]] = {"header": []}
    current = "header"
    offset = 0
    for raw in text.splitlines(keepends=True):
        line = raw.strip()
        if line:
            key = line.rstrip(":").strip().lower()
            if key in alias_to_section:
                current = alias_to_section[key]
                sections.setdefault(current, [])
            else:
                start = offset + (len(raw) - len(raw.lstrip()))
                sections.setdefault(current, []).append((start, line))
        offset += len(raw)
    return sections


def _header_identity(
    sections: dict[str, list[tuple[int, str]]],
) -> tuple[Optional[ExtractedStr], Optional[ExtractedStr]]:
    """(full_name, headline) from the pre-section header block."""
    prose = [
        (s, l)
        for s, l in sections.get("header", [])
        if "@" not in l and not _URL.search(l)
    ]
    full_name = headline = None
    if prose:
        start, line = prose[0]
        name = re.split(r"[|—–]", line)[0].strip()
        words = name.split()
        if 1 < len(words) <= 5 and not any(ch.isdigit() for ch in name):
            full_name = ExtractedStr(
                value=name, confidence=0.6, span=_line_span(start, line)
            )
    if len(prose) > 1:
        start, line = prose[1]
        headline = ExtractedStr(value=line, confidence=0.5, span=_line_span(start, line))
    return full_name, headline


def _contact(text: str) -> ContactInfo:
    contact = ContactInfo()
    m = _EMAIL.search(text)
    if m:
        contact.email = ExtractedStr(
            value=m.group(0),
            confidence=0.95,
            span=SourceSpan(start=m.start(), end=m.end(), text=m.group(0)),
        )
    m = _PHONE.search(text)
    if m:
        contact.phone = ExtractedStr(
            value=m.group(0).strip(),
            confidence=0.85,
            span=SourceSpan(start=m.start(), end=m.end(), text=m.group(0)),
        )
    return contact


def _links(text: str) -> list[LinkItem]:
    links: list[LinkItem] = []
    seen: set[str] = set()
    for m in _URL.finditer(text):
        url = m.group(0).rstrip(").,;")
        if url in seen:
            continue
        seen.add(url)
        low = url.lower()
        if "github.com" in low:
            ltype = LinkType.GITHUB
        elif "linkedin.com" in low:
            ltype = LinkType.LINKEDIN
        else:
            ltype = LinkType.OTHER
        links.append(
            LinkItem(
                type=ltype,
                url=url,
                span=SourceSpan(start=m.start(), end=m.start() + len(url), text=url),
            )
        )
    return links


def _education(lines: list[tuple[int, str]]) -> list[EducationEntry]:
    entries: list[EducationEntry] = []
    for start, line in lines:
        content = _BULLET.sub("", line)
        if not (_DEGREE.search(content) or _GRADE.search(content)):
            continue
        degree = field_of_study = institution = None
        for seg in (s.strip() for s in re.split(r"[—–,]", content) if s.strip()):
            if degree is None and _DEGREE.search(seg):
                lower = seg.lower()
                if " in " in lower:
                    i = lower.index(" in ")
                    degree, field_of_study = seg[:i].strip(), seg[i + 4 :].strip()
                else:
                    degree = seg
            elif (
                degree is not None
                and institution is None
                and not any(ch.isdigit() for ch in seg)
            ):
                institution = seg
        grade_value = grade_scale = None
        gm = _GRADE.search(content)
        pm = _PERCENT.search(content)
        if gm:
            grade_value = float(gm.group(1))
            denom = gm.group(2)
            grade_scale = f"cgpa_{denom}" if denom else (
                "cgpa_10" if grade_value <= 10 else None
            )
        elif pm:
            grade_value, grade_scale = float(pm.group(1)), "percentage"
        entries.append(
            EducationEntry(
                degree=degree,
                field_of_study=field_of_study,
                institution=institution,
                grade_value=grade_value,
                grade_scale=grade_scale,
                dates=parse_date_range(content),
                confidence=0.6,
                span=_line_span(start, line),
            )
        )
    return entries


def _experience(lines: list[tuple[int, str]]) -> list[ExperienceEntry]:
    entries: list[ExperienceEntry] = []
    for start, line in lines:
        content = _BULLET.sub("", line)
        # Only dated, non-bullet lines open an entry; bullets are duties.
        if _BULLET.match(line) or not has_date_range(content):
            continue
        head = content[: date_points(content)[0][0]].strip().rstrip("—–-|,").strip()
        title = employer = None
        if " at " in head.lower():
            i = head.lower().rindex(" at ")
            title, employer = head[:i].strip(), head[i + 4 :].strip()
        elif "," in head:
            title, employer = (p.strip() for p in head.rsplit(",", 1))
        elif head:
            title = head
        low = content.lower()
        if "intern" in low:
            etype = EmploymentType.INTERNSHIP
        elif "freelance" in low:
            etype = EmploymentType.FREELANCE
        elif "contract" in low:
            etype = EmploymentType.CONTRACT
        else:
            etype = EmploymentType.UNKNOWN
        seniority = next(
            (v for k, v in _SENIORITY_HINTS if k in (title or "").lower()), None
        )
        entries.append(
            ExperienceEntry(
                employer=employer,
                title=title,
                seniority=seniority,
                employment_type=etype,
                dates=parse_date_range(content),
                confidence=0.6,
                span=_line_span(start, line),
            )
        )
    return entries


def _skills(lines: list[tuple[int, str]]) -> list[SkillItem]:
    items: list[SkillItem] = []
    seen: set[str] = set()
    for start, line in lines:
        content = _BULLET.sub("", line)
        for part in re.split(r"[,;·|]", content):
            name = part.strip().rstrip(".")
            if not 1 < len(name) <= 40 or name.lower() in seen:
                continue
            seen.add(name.lower())
            items.append(SkillItem(name=name, confidence=0.7, span=_line_span(start, line)))
    return items


def _projects(lines: list[tuple[int, str]]) -> list[ProjectEntry]:
    projects: list[ProjectEntry] = []
    for start, line in lines:
        if _BULLET.match(line):
            if projects:  # bullet = description of the last project
                desc = _BULLET.sub("", line)
                cur = projects[-1]
                cur.description = (
                    f"{cur.description} {desc}".strip() if cur.description else desc
                )
            continue
        m = _URL.search(line)
        url = m.group(0).rstrip(").,;") if m else None
        name = _URL.sub("", line).strip().strip("—–-|:").strip()
        if not name and not url:
            continue
        projects.append(
            ProjectEntry(
                name=name or url, url=url, confidence=0.5, span=_line_span(start, line)
            )
        )
    return projects


def _certifications(lines: list[tuple[int, str]]) -> list[CertificationEntry]:
    entries: list[CertificationEntry] = []
    for start, line in lines:
        content = _BULLET.sub("", line)
        if len(content) < 4:
            continue
        parts = [p.strip() for p in content.split(",")]
        year = None
        if parts and re.fullmatch(r"(?:19|20)\d{2}", parts[-1]):
            year = int(parts.pop())
        entries.append(
            CertificationEntry(
                name=parts[0] if parts else content,
                issuer=", ".join(parts[1:]) or None,
                year=year,
                confidence=0.5,
                span=_line_span(start, line),
            )
        )
    return entries


def heuristic_profile(text: str) -> CandidateProfile:
    """Deterministic extraction — the no-LLM floor the pipeline can trust."""
    sections = _split_sections(text)
    full_name, headline = _header_identity(sections)
    return CandidateProfile(
        full_name=full_name,
        headline=headline,
        contact=_contact(text),
        education=_education(sections.get("education", [])),
        experience=_experience(sections.get("experience", [])),
        skills=_skills(sections.get("skills", [])),
        projects=_projects(sections.get("projects", [])),
        certifications=_certifications(sections.get("certifications", [])),
        links=_links(text),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_candidate_extractor_heuristic.py -q`
Expected: `6 passed`

If a parsing assertion fails, print the actual parse with
`python -c "from pathlib import Path; from app.candidates.extractor import heuristic_profile; print(heuristic_profile(Path('tests/fixtures/full_profile_resume.txt').read_text(encoding='utf-8')).model_dump_json(indent=2))"`
and fix the regex/segmentation — do not weaken the test.

- [ ] **Step 6: Commit**

```bash
git add app/candidates/extractor.py tests/fixtures/full_profile_resume.txt tests/test_candidate_extractor_heuristic.py
git commit -m "feat(candidates): deterministic section-based profile extractor"
```

---

### Task 6: LLM extraction path + `extract_profile()` orchestrator

**Files:**
- Modify: `app/candidates/extractor.py` (append LLM half)
- Test: `tests/test_candidate_extractor_llm.py`

**Interfaces:**
- Consumes: `LLMClient.acomplete_json(tier="parsing", system, prompt)` from `app/services/llm.py`; `heuristic_profile` (Task 5); `apply_contact_hashes` (Task 3); `Settings.contact_hash_salt` (Task 3).
- Produces: `async extract_profile(resume_text: str, *, llm: LLMClient, settings: Settings | None = None) -> ExtractionResult` — the single public entry point S1.2/S1.3 will call. Also `PROFILE_EXTRACTION_SYSTEM` (prompt constant) and `_parse_llm_profile(payload: dict, text: str) -> CandidateProfile`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_candidate_extractor_llm.py`:

```python
"""LLM extraction path (S1.1): scripted FakeLLM, fallback on abstain/garbage."""

import json
from pathlib import Path

import pytest

from app.candidates.extractor import extract_profile
from app.services.llm import NullLLM
from tests.conftest import FakeLLM

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def full_resume() -> str:
    return (FIXTURES / "full_profile_resume.txt").read_text(encoding="utf-8")


def _llm_payload() -> str:
    return json.dumps(
        {
            "full_name": {
                "value": "Arjun Mehta",
                "confidence": 0.97,
                "source_excerpt": "Arjun Mehta",
            },
            "headline": None,
            "contact": {
                "email": {
                    "value": "arjun.mehta@example.com",
                    "confidence": 0.99,
                    "source_excerpt": "arjun.mehta@example.com",
                },
                "phone": {
                    "value": "+91 98765 43210",
                    "confidence": 0.95,
                    "source_excerpt": "+91 98765 43210",
                },
                "location": {
                    "value": "Bengaluru, Karnataka",
                    "confidence": 0.9,
                    "source_excerpt": "Bengaluru, Karnataka",
                },
            },
            "education": [
                {
                    "degree": "B.Tech",
                    "field_of_study": "Computer Science",
                    "institution": "NIT Trichy",
                    "grade_value": 8.6,
                    "grade_scale": "cgpa_10",
                    "start": "2014",
                    "end": "2018",
                    "is_current": False,
                    "confidence": 0.92,
                    "source_excerpt": "B.Tech in Computer Science, NIT Trichy",
                }
            ],
            "experience": [
                {
                    "employer": "Flipkart",
                    "title": "Senior Data Engineer",
                    "seniority": "senior",
                    "employment_type": "full_time",
                    "start": "2021-06",
                    "end": None,
                    "is_current": True,
                    "confidence": 1.7,
                    "source_excerpt": "Senior Data Engineer, Flipkart",
                }
            ],
            "skills": [{"name": "Kafka", "confidence": 0.9, "source_excerpt": "Kafka"}],
            "projects": [],
            "certifications": [],
            "links": [{"type": "github", "url": "https://github.com/arjun-mehta"}],
        }
    )


async def test_llm_path_parses_profile_and_locates_spans(settings, full_resume):
    llm = FakeLLM({"RESUME:": _llm_payload()}, settings=settings)
    result = await extract_profile(full_resume, llm=llm, settings=settings)
    assert result.method == "llm"
    p = result.profile
    assert p.full_name is not None and p.full_name.value == "Arjun Mehta"
    # source_excerpt was re-located to a real character span:
    assert p.full_name.span is not None
    s = p.full_name.span
    assert full_resume[s.start : s.end] == "Arjun Mehta"
    edu_span = p.education[0].span
    assert edu_span is not None
    assert full_resume[edu_span.start : edu_span.end] == edu_span.text
    assert p.contact.location is not None
    assert p.experience[0].dates.is_current is True
    assert p.links[0].type == "github"


async def test_llm_confidence_is_clamped_to_unit_interval(settings, full_resume):
    llm = FakeLLM({"RESUME:": _llm_payload()}, settings=settings)
    result = await extract_profile(full_resume, llm=llm, settings=settings)
    assert result.profile.experience[0].confidence == 1.0  # 1.7 clamped


async def test_llm_path_computes_contact_hashes(settings, full_resume):
    llm = FakeLLM({"RESUME:": _llm_payload()}, settings=settings)
    result = await extract_profile(full_resume, llm=llm, settings=settings)
    assert result.profile.contact.email_hash is not None
    assert result.profile.contact.phone_hash is not None


async def test_null_llm_falls_back_to_heuristic(settings, full_resume):
    result = await extract_profile(full_resume, llm=NullLLM(settings), settings=settings)
    assert result.method == "heuristic"
    assert result.profile.contact.email is not None
    assert result.profile.contact.email_hash is not None


async def test_garbage_llm_output_falls_back_to_heuristic(settings, full_resume):
    llm = FakeLLM({"RESUME:": "sorry, I cannot help with that"}, settings=settings)
    result = await extract_profile(full_resume, llm=llm, settings=settings)
    assert result.method == "heuristic"
    assert len(result.profile.experience) == 2


async def test_llm_exception_degrades_with_warning(settings, full_resume):
    class BoomLLM(NullLLM):
        async def _araw(self, *, model, system, prompt, max_tokens):
            raise RuntimeError("provider down")

    result = await extract_profile(full_resume, llm=BoomLLM(settings), settings=settings)
    assert result.method == "heuristic"
    assert any("provider down" in w for w in result.warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_candidate_extractor_llm.py -q`
Expected: FAIL — `ImportError: cannot import name 'extract_profile'`

- [ ] **Step 3: Write the implementation**

Append to `app/candidates/extractor.py`. Extend the schema import block with `DateRange` and `ExtractionResult`, and add `from app.core.config import Settings` + `from app.services.llm import LLMClient` to the imports. Then:

```python
PROFILE_EXTRACTION_SYSTEM = """You are a precise resume parser for the Indian job market.
Extract a structured candidate profile from the resume.

Return ONE JSON object with exactly these keys (use null / [] when absent):
{
  "full_name":  {"value": str, "confidence": 0-1, "source_excerpt": str},
  "headline":   {"value": str, "confidence": 0-1, "source_excerpt": str},
  "contact": {
    "email":    {"value": str, "confidence": 0-1, "source_excerpt": str},
    "phone":    {"value": str, "confidence": 0-1, "source_excerpt": str},
    "location": {"value": str, "confidence": 0-1, "source_excerpt": str}
  },
  "education":  [{"degree": str, "field_of_study": str, "institution": str,
                  "grade_value": number, "grade_scale": "cgpa_10"|"cgpa_4"|"percentage",
                  "start": "YYYY-MM"|"YYYY", "end": "YYYY-MM"|"YYYY"|null, "is_current": bool,
                  "confidence": 0-1, "source_excerpt": str}],
  "experience": [{"employer": str, "title": str,
                  "seniority": "junior"|"mid"|"senior"|"staff",
                  "employment_type": "full_time"|"part_time"|"internship"|"contract"|"freelance"|"unknown",
                  "start": "YYYY-MM"|"YYYY", "end": "YYYY-MM"|"YYYY"|null, "is_current": bool,
                  "confidence": 0-1, "source_excerpt": str}],
  "skills":         [{"name": str, "confidence": 0-1, "source_excerpt": str}],
  "projects":       [{"name": str, "description": str, "technologies": [str],
                      "url": str, "confidence": 0-1, "source_excerpt": str}],
  "certifications": [{"name": str, "issuer": str, "year": int,
                      "confidence": 0-1, "source_excerpt": str}],
  "links":          [{"type": "github"|"linkedin"|"portfolio"|"other", "url": str}]
}

Rules:
- Copy each source_excerpt VERBATIM from the resume; it is used to locate provenance spans.
- Report only what the resume states; never invent values. Lower confidence when inferring.
- Dates: "YYYY-MM" when the month is stated, else "YYYY".
"""


def _clamp(value: object, default: float = 0.5) -> float:
    try:
        return min(1.0, max(0.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _find_span(text: str, excerpt: str) -> Optional[SourceSpan]:
    """Re-locate an LLM-quoted excerpt in the resume (case-insensitive rescue)."""
    if not excerpt:
        return None
    idx = text.find(excerpt)
    if idx < 0:
        idx = text.lower().find(excerpt.lower())
    if idx < 0:
        return None
    return SourceSpan(start=idx, end=idx + len(excerpt), text=text[idx : idx + len(excerpt)])


def _scalar(node: object, text: str) -> Optional[ExtractedStr]:
    if not isinstance(node, dict) or not node.get("value"):
        return None
    return ExtractedStr(
        value=str(node["value"]),
        confidence=_clamp(node.get("confidence")),
        span=_find_span(text, str(node.get("source_excerpt") or "")),
    )


def _node_dates(node: dict) -> DateRange:
    return DateRange(
        start=node.get("start") or None,
        end=node.get("end") or None,
        is_current=bool(node.get("is_current")),
    )


def _parse_llm_profile(payload: dict, text: str) -> CandidateProfile:
    """Defensive payload→profile mapping: skip malformed entries, never raise."""
    contact_raw = payload.get("contact") or {}
    profile = CandidateProfile(
        full_name=_scalar(payload.get("full_name"), text),
        headline=_scalar(payload.get("headline"), text),
        contact=ContactInfo(
            email=_scalar(contact_raw.get("email"), text),
            phone=_scalar(contact_raw.get("phone"), text),
            location=_scalar(contact_raw.get("location"), text),
        ),
    )
    for e in payload.get("education") or []:
        if not isinstance(e, dict):
            continue
        try:
            profile.education.append(
                EducationEntry(
                    degree=e.get("degree"),
                    field_of_study=e.get("field_of_study"),
                    institution=e.get("institution"),
                    grade_value=e.get("grade_value"),
                    grade_scale=e.get("grade_scale"),
                    dates=_node_dates(e),
                    confidence=_clamp(e.get("confidence")),
                    span=_find_span(text, str(e.get("source_excerpt") or "")),
                )
            )
        except (TypeError, ValueError):
            continue
    for x in payload.get("experience") or []:
        if not isinstance(x, dict):
            continue
        try:
            raw_type = str(x.get("employment_type") or "unknown")
            etype = (
                EmploymentType(raw_type)
                if raw_type in EmploymentType._value2member_map_
                else EmploymentType.UNKNOWN
            )
            profile.experience.append(
                ExperienceEntry(
                    employer=x.get("employer"),
                    title=x.get("title"),
                    seniority=x.get("seniority"),
                    employment_type=etype,
                    dates=_node_dates(x),
                    confidence=_clamp(x.get("confidence")),
                    span=_find_span(text, str(x.get("source_excerpt") or "")),
                )
            )
        except (TypeError, ValueError):
            continue
    for s in payload.get("skills") or []:
        if isinstance(s, dict) and s.get("name"):
            profile.skills.append(
                SkillItem(
                    name=str(s["name"]),
                    confidence=_clamp(s.get("confidence")),
                    span=_find_span(text, str(s.get("source_excerpt") or "")),
                )
            )
    for pr in payload.get("projects") or []:
        if isinstance(pr, dict) and pr.get("name"):
            profile.projects.append(
                ProjectEntry(
                    name=str(pr["name"]),
                    description=pr.get("description"),
                    technologies=[str(t) for t in pr.get("technologies") or []],
                    url=pr.get("url"),
                    confidence=_clamp(pr.get("confidence")),
                    span=_find_span(text, str(pr.get("source_excerpt") or "")),
                )
            )
    for c in payload.get("certifications") or []:
        if isinstance(c, dict) and c.get("name"):
            try:
                year = int(c["year"]) if c.get("year") is not None else None
            except (TypeError, ValueError):
                year = None
            profile.certifications.append(
                CertificationEntry(
                    name=str(c["name"]),
                    issuer=c.get("issuer"),
                    year=year,
                    confidence=_clamp(c.get("confidence")),
                    span=_find_span(text, str(c.get("source_excerpt") or "")),
                )
            )
    for lk in payload.get("links") or []:
        if isinstance(lk, dict) and lk.get("url"):
            raw_type = str(lk.get("type") or "other")
            ltype = (
                LinkType(raw_type)
                if raw_type in LinkType._value2member_map_
                else LinkType.OTHER
            )
            profile.links.append(
                LinkItem(type=ltype, url=str(lk["url"]), span=_find_span(text, str(lk["url"])))
            )
    return profile


def _is_empty(profile: CandidateProfile) -> bool:
    return (
        profile.full_name is None
        and profile.contact.email is None
        and profile.contact.phone is None
        and not profile.education
        and not profile.experience
        and not profile.skills
    )


async def extract_profile(
    resume_text: str, *, llm: LLMClient, settings: Optional[Settings] = None
) -> ExtractionResult:
    """LLM extraction with a deterministic floor — never returns nothing."""
    settings = settings or llm.settings
    warnings: list[str] = []
    profile: Optional[CandidateProfile] = None
    method = "heuristic"
    try:
        payload = await llm.acomplete_json(
            tier="parsing",
            system=PROFILE_EXTRACTION_SYSTEM,
            prompt=f"RESUME:\n{resume_text}",
        )
        if payload:
            profile = _parse_llm_profile(payload, resume_text)
            method = "llm"
    except Exception as exc:  # any LLM failure → heuristic floor
        warnings.append(f"llm_extraction_failed: {exc}")
        log.warning("profile_llm_failed", error=str(exc))
    if profile is None or _is_empty(profile):
        profile = heuristic_profile(resume_text)
        method = "heuristic"
    hashing.apply_contact_hashes(profile, settings.contact_hash_salt)
    log.info(
        "profile_extracted",
        method=method,
        education=len(profile.education),
        experience=len(profile.experience),
        skills=len(profile.skills),
    )
    return ExtractionResult(profile=profile, method=method, warnings=warnings)
```

Also add `from app.candidates import hashing` to the import block (module import avoids a long from-list; `hashing` imports `schema`, no cycle).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_candidate_extractor_llm.py -q`
Expected: `6 passed`

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: all tests pass (existing 20+ plus the new candidate tests).

- [ ] **Step 6: Commit**

```bash
git add app/candidates/extractor.py tests/test_candidate_extractor_llm.py
git commit -m "feat(candidates): LLM extraction path + extract_profile orchestrator with deterministic fallback"
```

---

### Task 7: Sprint close — smoke script, ROADMAP update

S1.1 adds no API route (that's S1.3), so this sprint's smoke run drives the new public entry point directly on all three fixture resumes with whatever LLM the environment provides (NullLLM offline ⇒ still must pass).

**Files:**
- Create: `scripts/smoke_s11.py`
- Modify: `docs/ROADMAP.md` (status board + current state + session log)

**Interfaces:**
- Consumes: `extract_profile`, `build_llm`, `get_settings` — exactly as S1.3's API wiring will.

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s11.py`:

```python
"""S1.1 smoke: run the profile extractor end-to-end on the fixture resumes.

Uses build_llm() — with no API key this exercises the deterministic floor
(NullLLM), with a key it exercises the live LLM path. Both must produce a
non-empty profile. Run from the repo root:  python scripts/smoke_s11.py
"""

import asyncio
import sys
from pathlib import Path

from app.candidates.extractor import extract_profile
from app.core.config import get_settings
from app.services.llm import build_llm

FIXTURES = Path("tests/fixtures")
RESUMES = (
    "full_profile_resume.txt",
    "genuine_genai_resume.txt",
    "fabricated_genai_resume.txt",
)


def main() -> int:
    settings = get_settings()
    llm = build_llm(settings)
    for name in RESUMES:
        text = (FIXTURES / name).read_text(encoding="utf-8")
        result = asyncio.run(extract_profile(text, llm=llm, settings=settings))
        p = result.profile
        print(f"\n=== {name} [{result.method}] warnings={result.warnings}")
        print(
            f"  name={p.full_name.value if p.full_name else None!r}"
            f" email_hash={(p.contact.email_hash or 'none')[:12]}"
            f" edu={len(p.education)} exp={len(p.experience)}"
            f" skills={len(p.skills)} projects={len(p.projects)}"
            f" certs={len(p.certifications)} links={len(p.links)}"
        )
        if not (p.links or p.skills or p.experience or p.contact.email):
            print(f"  FAIL: extractor produced an empty profile for {name}")
            return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the smoke**

Run: `python scripts/smoke_s11.py`
Expected: three profile summary lines + `SMOKE OK`, exit code 0. Offline, `full_profile_resume.txt` must show `[heuristic]` with `edu=1 exp=2` and a non-`none` email hash.

- [ ] **Step 3: Run the full suite one last time**

Run: `pytest -q`
Expected: green.

- [ ] **Step 4: Update `docs/ROADMAP.md`**

- Status board: `[~] S1.1` → `[x] S1.1`, `[ ] S1.2` → `[~] S1.2`.
- "Current state": current sprint = S1.2 (candidate store); next action = write S1.2 plan (schema tables candidates/resumes/extractions, SQLAlchemy + Alembic, identity resolution via the S1.1 email/phone hashes).
- Session log: add a dated entry — S1.1 built TDD-offline (`app/candidates/`: schema, hashing, dates, extractor; ~26 new tests), smoke green via `scripts/smoke_s11.py`.

- [ ] **Step 5: Commit**

```bash
git add scripts/smoke_s11.py docs/ROADMAP.md
git commit -m "chore: S1.1 smoke script + roadmap close-out"
```

---

## Self-Review (done at plan-writing time)

- **Spec coverage:** CandidateProfile fields (identity ✓ Task 2, contact-hashed ✓ Task 3, education/experience/skills/projects/certifications/links ✓ Task 2/5), per-field confidence ✓ (every model), source-span provenance ✓ (`SourceSpan` + span-audit tests), LLM extraction ✓ Task 6, deterministic fallback ✓ Task 5, offline TDD ✓, config tunable ✓ Task 3, sprint smoke ✓ Task 7. India normalization (taxonomy, canonical CGPA, institutions) is **S1.4 by design** — S1.1 only preserves raw grade + scale.
- **Type consistency:** `heuristic_profile` (Task 5) is called by Task 6 and Task 7 under that exact name; `apply_contact_hashes(profile, salt)` matches Task 3; `date_points/parse_date_range/has_date_range` match Task 4; `ExtractionResult(profile, method, warnings)` consistent across Tasks 2/6/7.
- **Placeholder scan:** none — every step carries full code/content.
