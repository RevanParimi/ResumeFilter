# S1.4 India Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich every extracted `CandidateProfile` with India-normalized canonical values — skill taxonomy ids, degree family + canonical 10-point CGPA, canonical institution + tier, canonical employer, canonical city + market tier, and a parsed notice period — without ever touching the claimed values.

**Architecture:** A new `app/candidates/normalize/` package of **pure, deterministic** lookup-table normalizers (no LLM anywhere — there is nothing to degrade, which trivially satisfies the fallback convention). Each entity type gets one module (`skills`, `degrees`, `orgs`, `location`) plus a shared key normalizer (`text.py`). A single orchestrator `normalize_profile(profile)` enriches a profile in place; `extract_profile` calls it after either extraction path (LLM or heuristic), so normalization is identical regardless of how the profile was produced. Normalized values land in **new Optional sibling fields** on the S1.1 schema (claimed values stay verbatim — advisory system, never guess; unknown ⇒ `None`). The enriched profile is stored via the existing `extractions.profile` JSON column — **no new tables, no Alembic migration, no API changes**; `GET /candidates/{id}` exposes the new fields automatically through `latest_profile`.

**Canonical vocabularies (locked here):** skills and degrees use snake_case taxonomy ids (`"apache_spark"`, `"btech"`); institutions, employers, and cities use canonical display names (`"NIT Trichy"`, `"Flipkart"`, `"Bengaluru"`). Institution tiers: `"tier_1" | "tier_2" | None`; city tiers: `"metro" | "tier_2"`; degree levels: `"diploma" | "bachelor" | "master" | "doctorate"`. Grade canonical scale is CGPA/10 (cgpa_4 × 2.5; percentage ÷ 9.5 per the CBSE convention, clamped to 10).

**Tech Stack:** Pure Python (regex + dict lookup tables), Pydantic v2 schema growth (all-Optional, backward compatible with stored S1.1–S1.3 extraction JSON), pytest offline, httpx + uvicorn smoke.

## Global Constraints

- TDD, fully offline tests; `pytest -q` green before merge (**138 tests green today — never fewer; 190 expected after this plan**).
- Every LLM step degrades deterministically. S1.4 adds **no** LLM step: all normalizers are deterministic; the LLM path benefits only because `normalize_profile` runs on whatever the extractor produced. No test may require an API key.
- Advisory only: canonical values and tiers are metadata for search/ML — nothing gates, rejects, or scores on them in this sprint.
- DPDP: no new tables. Normalized values live inside the profile JSON in `extractions.profile` and are erased by the existing S1.2/S1.3 delete paths. Claimed values are never overwritten (forensics needs them in PI-2).
- DB: **no Alembic migration** (JSON payload growth only). Old stored profiles must still validate — every new schema field is `Optional` with default `None`.
- Config: **no new settings**; taxonomy tables are domain knowledge in code (extensible dicts), not config tunables. Secrets stay in `.env` (`DEE_*`).
- The LangGraph pipeline, domains, `/evaluate`, and all S1.3 endpoints are untouched. The only existing files modified are `app/candidates/schema.py` (Task 5) and `app/candidates/extractor.py` (Task 6).
- Windows venv: run Python as `.resume\Scripts\python.exe`; tests as `.resume\Scripts\python.exe -m pytest -q` from repo root.
- Work on branch `s14-india-normalization` (create from `main` in Task 1).

**Existing interfaces this plan consumes (already on `main`):**

- `app.candidates.schema` — `CandidateProfile`, `ContactInfo`, `EducationEntry` (`degree`, `institution`, `grade_value: Optional[float]`, `grade_scale: Optional[str]` ∈ `"cgpa_10"|"cgpa_4"|"percentage"`), `ExperienceEntry` (`employer`), `SkillItem` (`name`), `ExtractedStr` (`value`, `confidence`, `span`), `SourceSpan(start, end, text)`.
- `app.candidates.extractor` — `extract_profile(resume_text, *, llm, settings) -> ExtractionResult`, `heuristic_profile(text) -> CandidateProfile`, `_split_sections` (returns `{"header": [(abs_offset, stripped_line), ...], "education": [...], ...}`), `PROFILE_EXTRACTION_SYSTEM` prompt, `_parse_llm_profile`, `_scalar`.
- `tests/conftest.py` — `settings` fixture (hermetic, key-less), `flywheel` fixture, `FakeLLM` (scripted by prompt substring), `make_services(...)`; NullLLM ⇒ heuristic extraction.
- Fixture `tests/fixtures/full_profile_resume.txt` — Arjun Mehta: header city "Bengaluru, Karnataka"; B.Tech / CGPA 8.6/10 / NIT Trichy; Flipkart + Infosys; skills Python, SQL, Apache Spark, Kafka, Airflow, AWS.
- `POST /candidates` (supports `evaluate: false`), `GET /candidates/{id}` → `latest_profile` (S1.3).

---

### Task 1: Key normalizer + skill taxonomy (`normalize/text.py`, `normalize/skills.py`)

**Files:**
- Create: `app/candidates/normalize/__init__.py` (empty for now; orchestrator arrives in Task 5)
- Create: `app/candidates/normalize/text.py`
- Create: `app/candidates/normalize/skills.py`
- Test: `tests/test_normalize_skills.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces: `norm_key(value: str) -> str` (lowercase; punctuation/whitespace runs → single space; keeps `+` and `#`) — every later lookup table indexes and probes with it. `SkillMatch(canonical: str, category: str)` NamedTuple; `normalize_skill(name: str) -> Optional[SkillMatch]`; `SKILL_CATEGORIES: frozenset[str]`. Task 5's orchestrator imports `normalize_skill`.

- [ ] **Step 1: Create the branch**

```powershell
git checkout main; git checkout -b s14-india-normalization
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_normalize_skills.py`:

```python
"""S1.4 skill taxonomy — norm_key + normalize_skill lookup tables."""

from app.candidates.normalize.skills import (
    SKILL_CATEGORIES,
    _TAXONOMY,
    normalize_skill,
)
from app.candidates.normalize.text import norm_key


def test_norm_key_lowers_and_collapses_punctuation():
    assert norm_key("  Node.JS ") == "node js"
    assert norm_key("CI/CD") == "ci cd"
    assert norm_key("scikit-learn") == "scikit learn"


def test_norm_key_keeps_plus_and_hash():
    assert norm_key("C++") == "c++"
    assert norm_key("C#") == "c#"


def test_exact_canonical_match():
    m = normalize_skill("Python")
    assert m is not None
    assert (m.canonical, m.category) == ("python", "language")


def test_alias_variants():
    assert normalize_skill("JS").canonical == "javascript"
    assert normalize_skill("ReactJS").canonical == "react"
    assert normalize_skill("K8s").canonical == "kubernetes"
    assert normalize_skill("PySpark").canonical == "apache_spark"


def test_punctuation_variants():
    assert normalize_skill("Node.js").canonical == "nodejs"
    assert normalize_skill("scikit-learn").canonical == "scikit_learn"
    assert normalize_skill("CI/CD").canonical == "ci_cd"


def test_symbol_languages():
    assert normalize_skill("C++").canonical == "cpp"
    assert normalize_skill("c#").canonical == "csharp"


def test_all_categories_from_fixed_vocabulary():
    used = {category for category, _aliases in _TAXONOMY.values()}
    assert used <= SKILL_CATEGORIES


def test_unknown_and_empty_return_none():
    assert normalize_skill("Underwater Basket Weaving") is None
    assert normalize_skill("") is None
    assert normalize_skill("   ") is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_skills.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.candidates.normalize'`.

- [ ] **Step 4: Implement**

Create `app/candidates/normalize/__init__.py`:

```python
"""India normalization (S1.4) — deterministic enrichment of CandidateProfile.

Pure functions over curated lookup tables; no LLM anywhere (nothing to
degrade). Claimed values are NEVER overwritten: canonical values land in
sibling fields and stay None when a value isn't in the tables — advisory
system, never guess. The orchestrator normalize_profile arrives in Task 5.
"""
```

Create `app/candidates/normalize/text.py`:

```python
"""Shared key normalization for the S1.4 lookup tables.

Alias tables are indexed by norm_key(alias) and probed with norm_key(input),
so "Node.js", "node js" and "NODE-JS" hit the same row. '+' and '#' survive
because C++/C# would die under plain word-splitting.
"""

from __future__ import annotations

import re

_NON_KEY = re.compile(r"[^\w+#]+")


def norm_key(value: str) -> str:
    """Lowercase; collapse punctuation/whitespace runs to single spaces."""
    return _NON_KEY.sub(" ", value.lower()).strip()
```

Create `app/candidates/normalize/skills.py`:

```python
"""Skill taxonomy for the Indian tech market (S1.4).

Curated, extensible table: canonical snake_case id -> (category, aliases).
Matching is exact on norm_key — a skill line is already a single claimed
token by the time it gets here (the extractor splits on separators), so no
fuzzy matching: unknown skills stay None rather than being guessed.
"""

from __future__ import annotations

from typing import NamedTuple, Optional

from app.candidates.normalize.text import norm_key


class SkillMatch(NamedTuple):
    canonical: str
    category: str


SKILL_CATEGORIES = frozenset(
    {
        "language", "web", "mobile", "data", "ml", "cloud",
        "devops", "database", "testing", "analytics",
    }
)

# canonical_id: (category, aliases). Aliases are raw human forms; the index
# is built with norm_key so punctuation/case variants collapse.
_TAXONOMY: dict[str, tuple[str, tuple[str, ...]]] = {
    # languages
    "python": ("language", ("python", "python3")),
    "java": ("language", ("java", "core java")),
    "javascript": ("language", ("javascript", "js", "ecmascript", "es6")),
    "typescript": ("language", ("typescript", "ts")),
    "c": ("language", ("c", "c language", "c programming")),
    "cpp": ("language", ("c++", "cpp")),
    "csharp": ("language", ("c#", "csharp", "c sharp")),
    "go": ("language", ("go", "golang")),
    "rust": ("language", ("rust",)),
    "kotlin": ("language", ("kotlin",)),
    "swift": ("language", ("swift",)),
    "php": ("language", ("php",)),
    "ruby": ("language", ("ruby",)),
    "scala": ("language", ("scala",)),
    "r": ("language", ("r", "r programming")),
    "sql": ("language", ("sql",)),
    # web / backend
    "react": ("web", ("react", "reactjs", "react.js")),
    "angular": ("web", ("angular", "angularjs", "angular.js")),
    "vuejs": ("web", ("vue", "vuejs", "vue.js")),
    "nextjs": ("web", ("next.js", "nextjs")),
    "nodejs": ("web", ("node", "nodejs", "node.js")),
    "express": ("web", ("express", "express.js", "expressjs")),
    "django": ("web", ("django", "django rest framework", "drf")),
    "flask": ("web", ("flask",)),
    "fastapi": ("web", ("fastapi", "fast api")),
    "spring": ("web", ("spring", "spring boot", "springboot")),
    "dotnet": ("web", (".net", "dotnet", ".net core", "asp.net")),
    "html": ("web", ("html", "html5")),
    "css": ("web", ("css", "css3")),
    "graphql": ("web", ("graphql",)),
    "rest_api": ("web", ("rest", "rest api", "restful api", "rest apis", "restful apis")),
    # mobile
    "android": ("mobile", ("android", "android development")),
    "ios": ("mobile", ("ios", "ios development")),
    "flutter": ("mobile", ("flutter",)),
    "react_native": ("mobile", ("react native",)),
    # data engineering
    "apache_spark": ("data", ("spark", "apache spark", "pyspark")),
    "kafka": ("data", ("kafka", "apache kafka")),
    "airflow": ("data", ("airflow", "apache airflow")),
    "hadoop": ("data", ("hadoop", "apache hadoop")),
    "hive": ("data", ("hive", "apache hive")),
    "dbt": ("data", ("dbt",)),
    "snowflake": ("data", ("snowflake",)),
    "databricks": ("data", ("databricks",)),
    "etl": ("data", ("etl", "elt", "etl pipelines")),
    "pandas": ("data", ("pandas",)),
    "numpy": ("data", ("numpy",)),
    # ML / AI
    "machine_learning": ("ml", ("machine learning", "ml")),
    "deep_learning": ("ml", ("deep learning", "neural networks")),
    "pytorch": ("ml", ("pytorch", "torch")),
    "tensorflow": ("ml", ("tensorflow", "tf")),
    "scikit_learn": ("ml", ("scikit-learn", "sklearn", "scikit learn")),
    "nlp": ("ml", ("nlp", "natural language processing")),
    "computer_vision": ("ml", ("computer vision", "opencv")),
    "generative_ai": ("ml", ("generative ai", "genai", "gen ai", "llm", "llms", "large language models")),
    "langchain": ("ml", ("langchain", "langgraph")),
    "hugging_face": ("ml", ("hugging face", "huggingface", "transformers")),
    "rag": ("ml", ("rag", "retrieval augmented generation")),
    "mlops": ("ml", ("mlops", "ml ops")),
    # cloud
    "aws": ("cloud", ("aws", "amazon web services")),
    "azure": ("cloud", ("azure", "microsoft azure")),
    "gcp": ("cloud", ("gcp", "google cloud", "google cloud platform")),
    # devops
    "docker": ("devops", ("docker", "containers")),
    "kubernetes": ("devops", ("kubernetes", "k8s")),
    "jenkins": ("devops", ("jenkins",)),
    "terraform": ("devops", ("terraform",)),
    "git": ("devops", ("git", "github", "gitlab", "bitbucket")),
    "ci_cd": ("devops", ("ci/cd", "cicd", "ci cd", "continuous integration")),
    "linux": ("devops", ("linux", "unix", "shell scripting", "bash")),
    # databases
    "mysql": ("database", ("mysql",)),
    "postgresql": ("database", ("postgres", "postgresql")),
    "mongodb": ("database", ("mongo", "mongodb")),
    "redis": ("database", ("redis",)),
    "oracle_db": ("database", ("oracle", "oracle db", "pl/sql", "plsql")),
    "sql_server": ("database", ("sql server", "mssql", "microsoft sql server", "t-sql")),
    "elasticsearch": ("database", ("elasticsearch", "elastic search", "opensearch")),
    "cassandra": ("database", ("cassandra",)),
    "dynamodb": ("database", ("dynamodb", "dynamo db")),
    # testing
    "selenium": ("testing", ("selenium", "selenium webdriver")),
    "cypress": ("testing", ("cypress",)),
    "junit": ("testing", ("junit", "testng")),
    "pytest": ("testing", ("pytest",)),
    "manual_testing": ("testing", ("manual testing", "qa", "quality assurance")),
    # analytics / BI
    "power_bi": ("analytics", ("power bi", "powerbi")),
    "tableau": ("analytics", ("tableau",)),
    "excel": ("analytics", ("excel", "ms excel", "microsoft excel", "advanced excel")),
}


def _build_index() -> dict[str, SkillMatch]:
    index: dict[str, SkillMatch] = {}
    for canonical, (category, aliases) in _TAXONOMY.items():
        match = SkillMatch(canonical=canonical, category=category)
        for alias in aliases:
            key = norm_key(alias)
            existing = index.get(key)
            if existing is not None and existing != match:  # taxonomy bug
                raise ValueError(
                    f"skill alias {alias!r} claimed by {existing.canonical} and {canonical}"
                )
            index[key] = match
    return index


_INDEX = _build_index()


def normalize_skill(name: str) -> Optional[SkillMatch]:
    key = norm_key(name or "")
    return _INDEX.get(key) if key else None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_skills.py -v`
Expected: 8 passed.

Then: `.resume\Scripts\python.exe -m pytest -q`
Expected: 146 passed (138 + 8).

- [ ] **Step 6: Commit**

```powershell
git add app/candidates/normalize tests/test_normalize_skills.py
git commit -m "feat(normalize): norm_key helper + Indian-market skill taxonomy"
```

---

### Task 2: Degree canonicalization + CGPA normalizer (`normalize/degrees.py`)

**Files:**
- Create: `app/candidates/normalize/degrees.py`
- Test: `tests/test_normalize_degrees.py`

**Interfaces:**
- Consumes: `norm_key` (Task 1).
- Produces: `DegreeMatch(canonical: str, level: str)` NamedTuple (level ∈ `"diploma"|"bachelor"|"master"|"doctorate"`); `normalize_degree(degree: str) -> Optional[DegreeMatch]` (exact alias hit, else longest-alias whole-word scan for strings like "B.Tech in CS"); `normalize_grade(value: Optional[float], scale: Optional[str]) -> Optional[float]` (canonical CGPA/10). Task 5 imports both.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_normalize_degrees.py`:

```python
"""S1.4 degree canonicalization + CGPA normalization (10-point canonical)."""

import pytest

from app.candidates.normalize.degrees import normalize_degree, normalize_grade


def test_btech_aliases():
    for raw in ("B.Tech", "BTech", "b tech", "Bachelor of Technology"):
        m = normalize_degree(raw)
        assert m is not None and m.canonical == "btech", raw
        assert m.level == "bachelor"


def test_levels_across_families():
    assert normalize_degree("B.E.").level == "bachelor"
    assert normalize_degree("M.Tech").level == "master"
    assert normalize_degree("MBA").level == "master"
    assert normalize_degree("Ph.D").level == "doctorate"
    assert normalize_degree("Diploma").level == "diploma"


def test_degree_with_inline_field_of_study():
    assert normalize_degree("B.Tech (Computer Science)").canonical == "btech"
    assert normalize_degree("Bachelor of Engineering - ECE").canonical == "be"


def test_longest_alias_wins():
    # Long forms must resolve via their full alias, not a stray short token.
    assert normalize_degree("Master of Engineering").canonical == "me"
    assert normalize_degree("Post Graduate Diploma in Management").canonical == "pgdm"


def test_unknown_or_empty_degree_none():
    assert normalize_degree("Certificate in Yoga") is None
    assert normalize_degree("") is None


def test_grade_cgpa10_passthrough():
    assert normalize_grade(8.6, "cgpa_10") == 8.6


def test_grade_cgpa4_scaled():
    assert normalize_grade(3.6, "cgpa_4") == 9.0
    assert normalize_grade(4.0, "cgpa_4") == 10.0


def test_grade_percentage_cbse_conversion():
    assert normalize_grade(86.0, "percentage") == pytest.approx(9.05)
    assert normalize_grade(97.0, "percentage") == 10.0  # clamped


def test_grade_out_of_range_none():
    assert normalize_grade(11.2, "cgpa_10") is None
    assert normalize_grade(4.5, "cgpa_4") is None
    assert normalize_grade(101.0, "percentage") is None


def test_grade_missing_or_unknown_scale_none():
    assert normalize_grade(None, "cgpa_10") is None
    assert normalize_grade(8.6, None) is None
    assert normalize_grade(8.6, "letter") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_degrees.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.candidates.normalize.degrees'`.

- [ ] **Step 3: Implement**

Create `app/candidates/normalize/degrees.py`:

```python
"""Indian degree canonicalization + grade normalization (S1.4).

Canonical grade scale is CGPA on the 10-point scale: cgpa_10 passes through,
cgpa_4 scales by 2.5, percentage divides by 9.5 (the CBSE convention) and
clamps to 10. Out-of-range or unknown-scale claims return None — the raw
claim stays untouched on the profile for PI-2 forensics.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

from app.candidates.normalize.text import norm_key


class DegreeMatch(NamedTuple):
    canonical: str
    level: str  # "diploma" | "bachelor" | "master" | "doctorate"


# canonical_id: (level, aliases). Indexed via norm_key ("B.E." -> "b e").
_DEGREES: dict[str, tuple[str, tuple[str, ...]]] = {
    "btech": ("bachelor", ("b.tech", "btech", "b tech", "bachelor of technology")),
    "be": ("bachelor", ("b.e", "b.e.", "be", "bachelor of engineering")),
    "bsc": ("bachelor", ("b.sc", "bsc", "bachelor of science")),
    "bca": ("bachelor", ("bca", "bachelor of computer applications")),
    "bcom": ("bachelor", ("b.com", "bcom", "bachelor of commerce")),
    "ba": ("bachelor", ("b.a", "ba", "bachelor of arts")),
    "bba": ("bachelor", ("bba", "bachelor of business administration")),
    "mtech": ("master", ("m.tech", "mtech", "m tech", "master of technology")),
    "me": ("master", ("m.e", "m.e.", "me", "master of engineering")),
    "msc": ("master", ("m.sc", "msc", "master of science")),
    "ms": ("master", ("m.s", "ms")),
    "mca": ("master", ("mca", "master of computer applications")),
    "mba": ("master", ("mba", "master of business administration")),
    "pgdm": ("master", ("pgdm", "post graduate diploma in management")),
    "mcom": ("master", ("m.com", "mcom", "master of commerce")),
    "ma": ("master", ("m.a", "ma", "master of arts")),
    "phd": ("doctorate", ("ph.d", "phd", "ph d", "doctor of philosophy")),
    "diploma": ("diploma", ("diploma", "polytechnic", "polytechnic diploma")),
}


def _build_index() -> dict[str, DegreeMatch]:
    index: dict[str, DegreeMatch] = {}
    for canonical, (level, aliases) in _DEGREES.items():
        match = DegreeMatch(canonical=canonical, level=level)
        for alias in aliases:
            key = norm_key(alias)
            existing = index.get(key)
            if existing is not None and existing != match:  # taxonomy bug
                raise ValueError(
                    f"degree alias {alias!r} claimed by {existing.canonical} and {canonical}"
                )
            index[key] = match
    return index


_INDEX = _build_index()
_KEYS_BY_LENGTH = sorted(_INDEX, key=len, reverse=True)


def normalize_degree(degree: str) -> Optional[DegreeMatch]:
    key = norm_key(degree or "")
    if not key:
        return None
    hit = _INDEX.get(key)
    if hit:
        return hit
    # Degree strings often carry the field inline ("B.Tech in CS"): fall back
    # to the LONGEST known alias found as a whole word inside the key.
    for alias_key in _KEYS_BY_LENGTH:
        if re.search(rf"(?<![\w+#]){re.escape(alias_key)}(?![\w+#])", key):
            return _INDEX[alias_key]
    return None


def normalize_grade(value: Optional[float], scale: Optional[str]) -> Optional[float]:
    """Claimed grade -> canonical CGPA/10, or None when it can't be trusted."""
    if value is None or scale is None:
        return None
    if scale == "cgpa_10":
        return round(value, 2) if 0 <= value <= 10 else None
    if scale == "cgpa_4":
        return round(value * 2.5, 2) if 0 <= value <= 4 else None
    if scale == "percentage":
        return round(min(value / 9.5, 10.0), 2) if 0 <= value <= 100 else None
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_degrees.py -v`
Expected: 10 passed.

Then: `.resume\Scripts\python.exe -m pytest -q`
Expected: 156 passed (146 + 10).

- [ ] **Step 5: Commit**

```powershell
git add app/candidates/normalize/degrees.py tests/test_normalize_degrees.py
git commit -m "feat(normalize): degree canonicalization + 10-point CGPA normalizer"
```

---

### Task 3: Institution + employer canonicalization (`normalize/orgs.py`)

**Files:**
- Create: `app/candidates/normalize/orgs.py`
- Test: `tests/test_normalize_orgs.py`

**Interfaces:**
- Consumes: `norm_key` (Task 1).
- Produces: `InstitutionMatch(canonical: str, tier: Optional[str])` NamedTuple (tier ∈ `"tier_1"|"tier_2"|None`); `canonicalize_institution(name: str) -> Optional[InstitutionMatch]` (alias table first, then IIT/IIM/NIT/IIIT campus patterns); `canonicalize_employer(name: str) -> Optional[str]` (legal-suffix stripping + alias table; returns canonical display name). Task 5 imports both.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_normalize_orgs.py`:

```python
"""S1.4 institution + employer canonicalization."""

from app.candidates.normalize.orgs import (
    canonicalize_employer,
    canonicalize_institution,
)


def test_iit_pattern_variants():
    for raw in ("IIT Bombay", "Indian Institute of Technology, Bombay"):
        m = canonicalize_institution(raw)
        assert m is not None and m.canonical == "IIT Bombay", raw
        assert m.tier == "tier_1"


def test_nit_trichy_spelling_variants_collide():
    a = canonicalize_institution("NIT Trichy")
    b = canonicalize_institution("National Institute of Technology, Tiruchirappalli")
    assert a is not None and b is not None
    assert a.canonical == b.canonical == "NIT Trichy"
    assert a.tier == "tier_2"


def test_alias_institutions():
    assert canonicalize_institution("Indian Institute of Science").canonical == "IISc Bangalore"
    assert canonicalize_institution("BITS Pilani").tier == "tier_1"
    assert canonicalize_institution("Visvesvaraya Technological University").canonical == "VTU"


def test_iiit_hyderabad_alias_beats_generic_pattern():
    assert canonicalize_institution("IIIT Hyderabad").tier == "tier_1"
    assert canonicalize_institution("IIIT Delhi").tier == "tier_2"  # generic pattern


def test_recognized_but_untiered():
    m = canonicalize_institution("IGNOU")
    assert m is not None and m.canonical == "IGNOU" and m.tier is None


def test_unknown_institution_none():
    assert canonicalize_institution("Springfield Institute of Magic") is None
    assert canonicalize_institution("") is None


def test_employer_aliases():
    assert canonicalize_employer("Tata Consultancy Services") == "TCS"
    assert canonicalize_employer("Cognizant Technology Solutions") == "Cognizant"
    assert canonicalize_employer("Facebook") == "Meta"


def test_employer_legal_suffixes_stripped():
    assert canonicalize_employer("Infosys Ltd") == "Infosys"
    assert canonicalize_employer("Wipro Pvt. Ltd.") == "Wipro"
    assert canonicalize_employer("Zoho Corporation") == "Zoho"
    assert canonicalize_employer("Amazon India") == "Amazon"


def test_employer_indian_startups():
    assert canonicalize_employer("Flipkart") == "Flipkart"
    assert canonicalize_employer("PhonePe") == "PhonePe"
    assert canonicalize_employer("Razorpay") == "Razorpay"


def test_employer_unknown_none():
    assert canonicalize_employer("Sharma & Sons Traders") is None
    assert canonicalize_employer("") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_orgs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.candidates.normalize.orgs'`.

- [ ] **Step 3: Implement**

Create `app/candidates/normalize/orgs.py`:

```python
"""Institution + employer canonicalization for the Indian market (S1.4).

Institutions: explicit alias table first (covers tier overrides like IIIT
Hyderabad), then campus patterns for the IIT/IIM/NIT/IIIT systems so the
long tail ("Indian Institute of Technology, Madras") needs no table row.
Tiers are ADVISORY search metadata, not a gate: tier_1/tier_2/None.

Employers: trailing legal tokens (Pvt/Ltd/Inc/...) are stripped, then an
alias table maps to a canonical display name. Unknown orgs return None —
inventing canonicals for unknowns would cause false merges downstream.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

from app.candidates.normalize.text import norm_key


class InstitutionMatch(NamedTuple):
    canonical: str
    tier: Optional[str]  # "tier_1" | "tier_2" | None (recognized, untiered)


# canonical display name: (tier, aliases). Indexed via norm_key.
_INSTITUTIONS: dict[str, tuple[Optional[str], tuple[str, ...]]] = {
    "IISc Bangalore": ("tier_1", ("iisc", "indian institute of science", "iisc bangalore", "iisc bengaluru")),
    "BITS Pilani": ("tier_1", ("bits pilani", "bits", "birla institute of technology and science")),
    "IIIT Hyderabad": ("tier_1", ("iiit hyderabad", "iiit-h", "international institute of information technology hyderabad")),
    "ISB Hyderabad": ("tier_1", ("isb", "indian school of business")),
    "Anna University": ("tier_2", ("anna university",)),
    "VTU": ("tier_2", ("vtu", "visvesvaraya technological university")),
    "Jadavpur University": ("tier_2", ("jadavpur university", "jadavpur")),
    "Delhi University": ("tier_2", ("delhi university", "university of delhi")),
    "DTU": ("tier_2", ("dtu", "delhi technological university", "delhi college of engineering", "dce")),
    "Jamia Millia Islamia": ("tier_2", ("jamia millia islamia", "jamia")),
    "VIT Vellore": ("tier_2", ("vit", "vit vellore", "vellore institute of technology")),
    "SRM University": ("tier_2", ("srm", "srm university", "srm institute of science and technology")),
    "MIT Manipal": ("tier_2", ("mit manipal", "manipal institute of technology")),
    "COEP Pune": ("tier_2", ("coep", "college of engineering pune")),
    "PSG College of Technology": ("tier_2", ("psg college of technology", "psg tech")),
    "Amrita Vishwa Vidyapeetham": ("tier_2", ("amrita", "amrita vishwa vidyapeetham", "amrita university")),
    "Osmania University": ("tier_2", ("osmania university", "osmania")),
    "Pune University": ("tier_2", ("pune university", "university of pune", "savitribai phule pune university", "sppu")),
    "IGNOU": (None, ("ignou", "indira gandhi national open university")),
    "LPU": (None, ("lpu", "lovely professional university")),
    "Chandigarh University": (None, ("chandigarh university",)),
}

# Campus patterns run AFTER the alias table (so IIIT Hyderabad keeps tier_1).
_INST_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"^(?:iit|indian institute of technology)\s+(?P<campus>[a-z][a-z ]*)$"), "IIT {campus}", "tier_1"),
    (re.compile(r"^(?:iim|indian institute of management)\s+(?P<campus>[a-z][a-z ]*)$"), "IIM {campus}", "tier_1"),
    (re.compile(r"^(?:nit|national institute of technology)\s+(?P<campus>[a-z][a-z ]*)$"), "NIT {campus}", "tier_2"),
    (re.compile(r"^(?:iiit|indian institute of information technology)\s+(?P<campus>[a-z][a-z ]*)$"), "IIIT {campus}", "tier_2"),
)

# Campus spellings folded so "NIT Tiruchirappalli" == "NIT Trichy".
_CAMPUS_FIX = {
    "tiruchirappalli": "Trichy",
    "tiruchirapalli": "Trichy",
    "trichy": "Trichy",
}


def _build_inst_index() -> dict[str, InstitutionMatch]:
    index: dict[str, InstitutionMatch] = {}
    for canonical, (tier, aliases) in _INSTITUTIONS.items():
        match = InstitutionMatch(canonical=canonical, tier=tier)
        for alias in aliases:
            key = norm_key(alias)
            existing = index.get(key)
            if existing is not None and existing != match:  # table bug
                raise ValueError(
                    f"institution alias {alias!r} claimed by {existing.canonical} and {canonical}"
                )
            index[key] = match
    return index


_INST_INDEX = _build_inst_index()


def canonicalize_institution(name: str) -> Optional[InstitutionMatch]:
    key = norm_key(name or "")
    if not key:
        return None
    hit = _INST_INDEX.get(key)
    if hit:
        return hit
    for pattern, template, tier in _INST_PATTERNS:
        m = pattern.match(key)
        if m:
            campus = m.group("campus").strip()
            campus = _CAMPUS_FIX.get(campus, campus.title())
            return InstitutionMatch(canonical=template.format(campus=campus), tier=tier)
    return None


# canonical display name: aliases. Indexed via norm_key.
_EMPLOYERS: dict[str, tuple[str, ...]] = {
    "TCS": ("tcs", "tata consultancy services"),
    "Infosys": ("infosys", "infosys technologies"),
    "Infosys BPM": ("infosys bpm",),
    "Wipro": ("wipro", "wipro technologies"),
    "HCL": ("hcl", "hcl technologies", "hcltech"),
    "Tech Mahindra": ("tech mahindra", "techm"),
    "Cognizant": ("cognizant", "cts", "cognizant technology solutions"),
    "Accenture": ("accenture",),
    "Capgemini": ("capgemini",),
    "LTIMindtree": ("ltimindtree", "lti", "mindtree", "l&t infotech", "larsen & toubro infotech"),
    "IBM": ("ibm", "international business machines", "ibm india"),
    "Amazon": ("amazon", "amazon india", "amazon development centre india"),
    "Google": ("google", "google india"),
    "Microsoft": ("microsoft", "microsoft india"),
    "Meta": ("meta", "facebook"),
    "Apple": ("apple",),
    "Netflix": ("netflix",),
    "Adobe": ("adobe", "adobe systems"),
    "Oracle": ("oracle", "oracle india"),
    "SAP": ("sap", "sap labs", "sap labs india"),
    "Salesforce": ("salesforce",),
    "Intuit": ("intuit",),
    "NVIDIA": ("nvidia",),
    "Uber": ("uber",),
    "Walmart Global Tech": ("walmart", "walmart global tech", "walmart labs"),
    "Flipkart": ("flipkart",),
    "Myntra": ("myntra",),
    "Paytm": ("paytm", "one97", "one97 communications"),
    "PhonePe": ("phonepe",),
    "Razorpay": ("razorpay",),
    "Zomato": ("zomato",),
    "Swiggy": ("swiggy",),
    "Ola": ("ola", "ola cabs", "ani technologies"),
    "Zoho": ("zoho",),
    "Freshworks": ("freshworks", "freshdesk"),
    "Zerodha": ("zerodha",),
    "CRED": ("cred", "dreamplug technologies"),
    "Meesho": ("meesho",),
    "Reliance Jio": ("jio", "reliance jio", "jio platforms"),
    "Deloitte": ("deloitte", "deloitte india", "deloitte usi"),
    "EY": ("ey", "ernst & young", "ernst and young"),
    "KPMG": ("kpmg",),
    "PwC": ("pwc", "pricewaterhousecoopers"),
    "JPMorgan Chase": ("jpmorgan", "jp morgan", "jpmorgan chase", "jpmc"),
    "Goldman Sachs": ("goldman sachs",),
    "Morgan Stanley": ("morgan stanley",),
    "Barclays": ("barclays",),
    "Samsung R&D": ("samsung", "samsung r&d", "samsung electronics"),
    "Qualcomm": ("qualcomm",),
    "Intel": ("intel",),
    "Cisco": ("cisco", "cisco systems"),
    "Dell": ("dell", "dell technologies", "emc", "dell emc"),
    "VMware": ("vmware",),
    "Atlassian": ("atlassian",),
    "ServiceNow": ("servicenow",),
    "Nagarro": ("nagarro",),
    "Persistent Systems": ("persistent", "persistent systems"),
    "Mphasis": ("mphasis",),
    "Hexaware": ("hexaware", "hexaware technologies"),
    "Coforge": ("coforge", "niit technologies"),
    "Genpact": ("genpact",),
}

_LEGAL_TOKENS = {
    "pvt", "private", "ltd", "limited", "llp", "inc",
    "co", "corp", "corporation", "company", "india",
}


def _build_emp_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, aliases in _EMPLOYERS.items():
        for alias in aliases:
            key = norm_key(alias)
            existing = index.get(key)
            if existing is not None and existing != canonical:  # table bug
                raise ValueError(
                    f"employer alias {alias!r} claimed by {existing} and {canonical}"
                )
            index[key] = canonical
    return index


_EMP_INDEX = _build_emp_index()


def canonicalize_employer(name: str) -> Optional[str]:
    words = norm_key(name or "").split()
    while words:
        hit = _EMP_INDEX.get(" ".join(words))
        if hit:
            return hit
        if words[-1] in _LEGAL_TOKENS:
            words.pop()  # "wipro pvt ltd" -> "wipro pvt" -> "wipro"
        else:
            return None
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_orgs.py -v`
Expected: 10 passed.

Then: `.resume\Scripts\python.exe -m pytest -q`
Expected: 166 passed (156 + 10).

- [ ] **Step 5: Commit**

```powershell
git add app/candidates/normalize/orgs.py tests/test_normalize_orgs.py
git commit -m "feat(normalize): institution canonicalization with tiers + employer aliases"
```

---

### Task 4: City gazetteer + notice-period parser (`normalize/location.py`)

**Files:**
- Create: `app/candidates/normalize/location.py`
- Test: `tests/test_normalize_location.py`

**Interfaces:**
- Consumes: stdlib `re` only (works on RAW text — offsets must survive for provenance spans, so no norm_key here).
- Produces: `CityFind(city: str, tier: str, start: int, end: int, text: str)` and `find_city(text: str) -> Optional[CityFind]` (word-boundary regex over raw text, longest alias first); `NoticeFind(days: Optional[int], start: int, end: int, text: str)` and `parse_notice_period(text: str) -> Optional[NoticeFind]` (`days=0` ⇒ immediate; `days=None` ⇒ stated but unquantified, e.g. "serving notice"). Tasks 5 and 6 import both.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_normalize_location.py`:

```python
"""S1.4 city gazetteer + notice-period parsing (raw-text scanners with offsets)."""

from app.candidates.normalize.location import find_city, parse_notice_period


def test_bangalore_becomes_bengaluru():
    for raw in ("Bangalore", "Bengaluru, Karnataka"):
        m = find_city(raw)
        assert m is not None and m.city == "Bengaluru", raw
        assert m.tier == "metro"


def test_gurgaon_becomes_gurugram():
    assert find_city("Gurgaon, Haryana").city == "Gurugram"


def test_new_delhi_prefers_longest_alias():
    m = find_city("New Delhi, India")
    assert m.city == "Delhi" and m.text == "New Delhi"


def test_tier2_aliases():
    assert find_city("Mysore").city == "Mysuru"
    assert find_city("Trivandrum").city == "Thiruvananthapuram"
    m = find_city("Vizag")
    assert m.city == "Visakhapatnam" and m.tier == "tier_2"


def test_find_city_span_offsets():
    text = "Based in Pune since 2020"
    m = find_city(text)
    assert text[m.start : m.end] == m.text == "Pune"


def test_no_known_city_none():
    assert find_city("Remote, Mars Colony One") is None
    assert find_city("") is None


def test_notice_labelled_forms():
    assert parse_notice_period("Notice Period: 30 days").days == 30
    assert parse_notice_period("Notice period - 2 months").days == 60


def test_notice_inline_forms():
    assert parse_notice_period("45 days notice").days == 45
    assert parse_notice_period("2 weeks' notice").days == 14


def test_notice_immediate_forms():
    assert parse_notice_period("Immediate joiner").days == 0
    assert parse_notice_period("Notice Period: Immediate").days == 0
    assert parse_notice_period("Available immediately").days == 0


def test_notice_bare_value_forms():
    # LLM extraction returns just the value ("30 days"): accept whole-string.
    assert parse_notice_period("30 days").days == 30
    assert parse_notice_period("Immediate").days == 0


def test_notice_serving_is_unquantified():
    m = parse_notice_period("Currently serving notice period")
    assert m is not None and m.days is None
    assert "serving notice" in m.text.lower()


def test_notice_absent_none():
    assert parse_notice_period("Python developer, 5 years experience") is None


def test_notice_span_offsets():
    text = "Skills: Python\nNotice Period: 45 days\n"
    m = parse_notice_period(text)
    assert text[m.start : m.end] == m.text
    assert m.days == 45
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_location.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.candidates.normalize.location'`.

- [ ] **Step 3: Implement**

Create `app/candidates/normalize/location.py`:

```python
"""Indian city gazetteer + notice-period parsing (S1.4).

Both scanners work on RAW text and return character offsets, so the
extractor can attach SourceSpan provenance. City tiers ("metro"/"tier_2")
are talent-market metadata, not judgments. Notice period: days=0 means
immediate joiner; days=None means stated but unquantified ("serving
notice"); a missing statement returns None outright.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional


class CityFind(NamedTuple):
    city: str   # canonical display name
    tier: str   # "metro" | "tier_2"
    start: int
    end: int
    text: str   # matched substring, verbatim


class NoticeFind(NamedTuple):
    days: Optional[int]
    start: int
    end: int
    text: str


# canonical display name: (tier, aliases). Aliases are matched as whole
# words, case-insensitively, against raw text.
_CITIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "Bengaluru": ("metro", ("bengaluru", "bangalore")),
    "Mumbai": ("metro", ("mumbai", "bombay", "navi mumbai")),
    "Delhi": ("metro", ("new delhi", "delhi")),
    "Gurugram": ("metro", ("gurugram", "gurgaon")),
    "Noida": ("metro", ("noida",)),
    "Hyderabad": ("metro", ("hyderabad", "secunderabad")),
    "Chennai": ("metro", ("chennai", "madras")),
    "Kolkata": ("metro", ("kolkata", "calcutta")),
    "Pune": ("metro", ("pune",)),
    "Ahmedabad": ("metro", ("ahmedabad",)),
    "Jaipur": ("tier_2", ("jaipur",)),
    "Lucknow": ("tier_2", ("lucknow",)),
    "Indore": ("tier_2", ("indore",)),
    "Bhopal": ("tier_2", ("bhopal",)),
    "Nagpur": ("tier_2", ("nagpur",)),
    "Chandigarh": ("tier_2", ("chandigarh", "mohali", "panchkula")),
    "Kochi": ("tier_2", ("kochi", "cochin", "ernakulam")),
    "Thiruvananthapuram": ("tier_2", ("thiruvananthapuram", "trivandrum")),
    "Coimbatore": ("tier_2", ("coimbatore",)),
    "Mysuru": ("tier_2", ("mysuru", "mysore")),
    "Visakhapatnam": ("tier_2", ("visakhapatnam", "vizag")),
    "Bhubaneswar": ("tier_2", ("bhubaneswar",)),
    "Surat": ("tier_2", ("surat",)),
    "Vadodara": ("tier_2", ("vadodara", "baroda")),
    "Trichy": ("tier_2", ("trichy", "tiruchirappalli")),
    "Madurai": ("tier_2", ("madurai",)),
    "Kanpur": ("tier_2", ("kanpur",)),
    "Patna": ("tier_2", ("patna",)),
    "Guwahati": ("tier_2", ("guwahati",)),
    "Dehradun": ("tier_2", ("dehradun",)),
    "Nashik": ("tier_2", ("nashik",)),
    "Mangaluru": ("tier_2", ("mangaluru", "mangalore")),
}

_ALIAS_TO_CITY: dict[str, tuple[str, str]] = {
    alias: (city, tier)
    for city, (tier, aliases) in _CITIES.items()
    for alias in aliases
}

# Longest alias first so "new delhi" wins over "delhi" at the same position.
# Aliases are strictly [a-z ] (asserted below), so no re.escape is needed —
# re.escape would backslash the spaces and break the \s+ substitution.
assert all(a.replace(" ", "").isalpha() for a in _ALIAS_TO_CITY)
_CITY_RE = re.compile(
    r"\b(?:"
    + "|".join(
        a.replace(" ", r"\s+")
        for a in sorted(_ALIAS_TO_CITY, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)


def find_city(text: str) -> Optional[CityFind]:
    m = _CITY_RE.search(text or "")
    if not m:
        return None
    alias = re.sub(r"\s+", " ", m.group(0).lower())
    city, tier = _ALIAS_TO_CITY[alias]
    return CityFind(city=city, tier=tier, start=m.start(), end=m.end(), text=m.group(0))


_UNIT_DAYS = {"day": 1, "week": 7, "month": 30}

_NP_LABELLED = re.compile(
    r"notice\s*period\s*[:\-–]?\s*"
    r"(?:(?P<imm>immediate(?:ly)?)|(?P<num>\d{1,3})\s*(?P<unit>day|week|month)s?)",
    re.IGNORECASE,
)
_NP_INLINE = re.compile(
    r"\b(?P<num>\d{1,3})\s*(?P<unit>day|week|month)s?['’]?\s*(?:of\s+)?notice\b",
    re.IGNORECASE,
)
_NP_IMMEDIATE = re.compile(
    r"\b(?:immediate\s+joiner|available\s+immediately|immediately\s+available)\b",
    re.IGNORECASE,
)
_NP_SERVING = re.compile(
    r"\bserving\s+(?:my\s+)?notice(?:\s+period)?\b", re.IGNORECASE
)
# Whole-string bare value ("30 days", "Immediate") — how an LLM-extracted
# notice_period.value arrives. Anchored, so resume-body scans never hit it.
_NP_BARE = re.compile(
    r"^\s*(?:(?P<imm>immediate(?:ly)?(?:\s+joiner)?)"
    r"|(?P<num>\d{1,3})\s*(?P<unit>day|week|month)s?)\s*$",
    re.IGNORECASE,
)


def _days(m: re.Match) -> Optional[int]:
    if m.groupdict().get("imm"):
        return 0
    return int(m.group("num")) * _UNIT_DAYS[m.group("unit").lower()]


def parse_notice_period(text: str) -> Optional[NoticeFind]:
    text = text or ""
    for pattern in (_NP_LABELLED, _NP_INLINE):
        m = pattern.search(text)
        if m:
            return NoticeFind(days=_days(m), start=m.start(), end=m.end(), text=m.group(0))
    m = _NP_IMMEDIATE.search(text)
    if m:
        return NoticeFind(days=0, start=m.start(), end=m.end(), text=m.group(0))
    m = _NP_SERVING.search(text)
    if m:
        return NoticeFind(days=None, start=m.start(), end=m.end(), text=m.group(0))
    m = _NP_BARE.match(text)
    if m:
        return NoticeFind(days=_days(m), start=m.start(), end=m.end(), text=m.group(0))
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_location.py -v`
Expected: 13 passed.

Then: `.resume\Scripts\python.exe -m pytest -q`
Expected: 179 passed (166 + 13).

- [ ] **Step 5: Commit**

```powershell
git add app/candidates/normalize/location.py tests/test_normalize_location.py
git commit -m "feat(normalize): Indian city gazetteer + notice-period parser"
```

---

### Task 5: Schema growth + `normalize_profile` orchestrator

**Files:**
- Modify: `app/candidates/schema.py` (new Optional fields on `SkillItem`, `EducationEntry`, `ExperienceEntry`, `ContactInfo`, `CandidateProfile`)
- Modify: `app/candidates/normalize/__init__.py` (add the orchestrator)
- Test: `tests/test_normalize_profile.py`

**Interfaces:**
- Consumes: `normalize_skill` (T1), `normalize_degree`/`normalize_grade` (T2), `canonicalize_institution`/`canonicalize_employer` (T3), `find_city`/`parse_notice_period` (T4).
- Produces: schema fields — `SkillItem.canonical/.category`, `EducationEntry.degree_canonical/.degree_level/.grade_cgpa_10/.institution_canonical/.institution_tier`, `ExperienceEntry.employer_canonical`, `ContactInfo.location_city/.location_tier`, `CandidateProfile.notice_period: Optional[ExtractedStr]` + `.notice_period_days: Optional[int]` (all default `None`); `normalize_profile(profile: CandidateProfile) -> CandidateProfile` (enriches in place, returns the same object). Task 6 calls `normalize_profile` and populates `notice_period`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_normalize_profile.py`:

```python
"""S1.4 schema growth + normalize_profile orchestration (pure, offline)."""

from app.candidates.normalize import normalize_profile
from app.candidates.schema import (
    CandidateProfile,
    ContactInfo,
    EducationEntry,
    ExperienceEntry,
    ExtractedStr,
    SkillItem,
)


def test_legacy_profile_payload_still_validates():
    """Pre-S1.4 extractions (stored JSON) must load with the new fields None."""
    legacy = {
        "id": "cand_legacy1",
        "skills": [{"name": "Python", "confidence": 0.7}],
        "education": [{"degree": "B.Tech", "grade_value": 8.0, "grade_scale": "cgpa_10"}],
        "experience": [{"employer": "Infosys"}],
    }
    p = CandidateProfile.model_validate(legacy)
    assert p.skills[0].canonical is None
    assert p.education[0].grade_cgpa_10 is None
    assert p.experience[0].employer_canonical is None
    assert p.notice_period is None and p.notice_period_days is None


def test_skills_enriched():
    p = CandidateProfile(skills=[SkillItem(name="PySpark"), SkillItem(name="K8s")])
    normalize_profile(p)
    assert [(s.canonical, s.category) for s in p.skills] == [
        ("apache_spark", "data"),
        ("kubernetes", "devops"),
    ]


def test_education_enriched():
    p = CandidateProfile(
        education=[
            EducationEntry(
                degree="B.Tech",
                institution="National Institute of Technology, Tiruchirappalli",
                grade_value=8.6,
                grade_scale="cgpa_10",
            )
        ]
    )
    normalize_profile(p)
    edu = p.education[0]
    assert edu.degree_canonical == "btech" and edu.degree_level == "bachelor"
    assert edu.grade_cgpa_10 == 8.6
    assert edu.institution_canonical == "NIT Trichy"
    assert edu.institution_tier == "tier_2"
    # Claims stay verbatim:
    assert edu.degree == "B.Tech"
    assert edu.institution == "National Institute of Technology, Tiruchirappalli"


def test_experience_employer_enriched():
    p = CandidateProfile(
        experience=[
            ExperienceEntry(employer="Infosys Ltd"),
            ExperienceEntry(employer="Chai Point"),
        ]
    )
    normalize_profile(p)
    assert p.experience[0].employer_canonical == "Infosys"
    assert p.experience[1].employer_canonical is None
    assert p.experience[1].employer == "Chai Point"


def test_location_and_notice_enriched():
    p = CandidateProfile(
        contact=ContactInfo(location=ExtractedStr(value="Bangalore, Karnataka")),
        notice_period=ExtractedStr(value="Notice Period: 30 days"),
    )
    normalize_profile(p)
    assert p.contact.location_city == "Bengaluru"
    assert p.contact.location_tier == "metro"
    assert p.notice_period_days == 30


def test_normalize_returns_the_same_object():
    p = CandidateProfile()
    assert normalize_profile(p) is p
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_profile.py -v`
Expected: FAIL — `ImportError: cannot import name 'normalize_profile'` from `app.candidates.normalize`.

- [ ] **Step 3: Grow the schema**

In `app/candidates/schema.py`, apply these additions (each new field defaults to `None` — stored S1.1–S1.3 profiles must keep validating):

**(a)** `ContactInfo` — append after `phone_hash`:

```python
    # S1.4: canonical Indian city lifted from `location` (None = no known city).
    location_city: Optional[str] = None   # e.g. "Bengaluru"
    location_tier: Optional[str] = None   # "metro" | "tier_2"
```

**(b)** `EducationEntry` — append after `span`:

```python
    # S1.4 normalization — the claimed values above stay verbatim.
    degree_canonical: Optional[str] = None       # taxonomy id, e.g. "btech"
    degree_level: Optional[str] = None           # diploma|bachelor|master|doctorate
    grade_cgpa_10: Optional[float] = None        # canonical CGPA on the 10-point scale
    institution_canonical: Optional[str] = None  # e.g. "NIT Trichy"
    institution_tier: Optional[str] = None       # "tier_1" | "tier_2" | None
```

**(c)** `ExperienceEntry` — append after `span`:

```python
    # S1.4: canonical employer (None = not in the alias table; claim untouched).
    employer_canonical: Optional[str] = None     # e.g. "Flipkart"
```

**(d)** `SkillItem` — append after `span`:

```python
    # S1.4 taxonomy mapping (None = unknown skill; the claimed name stays).
    canonical: Optional[str] = None  # taxonomy id, e.g. "apache_spark"
    category: Optional[str] = None   # taxonomy category, e.g. "data"
```

**(e)** `CandidateProfile` — append after `links`:

```python
    # S1.4: claimed notice period / availability + normalized day count
    # (0 = immediate joiner; None = not stated or not quantifiable).
    notice_period: Optional[ExtractedStr] = None
    notice_period_days: Optional[int] = None
```

- [ ] **Step 4: Implement the orchestrator**

Replace `app/candidates/normalize/__init__.py` in full:

```python
"""India normalization (S1.4) — deterministic enrichment of CandidateProfile.

Pure functions over curated lookup tables; no LLM anywhere (nothing to
degrade). Claimed values are NEVER overwritten: canonical values land in
sibling fields and stay None when a value isn't in the tables — advisory
system, never guess.
"""

from __future__ import annotations

from app.candidates.normalize.degrees import normalize_degree, normalize_grade
from app.candidates.normalize.location import find_city, parse_notice_period
from app.candidates.normalize.orgs import (
    canonicalize_employer,
    canonicalize_institution,
)
from app.candidates.normalize.skills import normalize_skill
from app.candidates.schema import CandidateProfile


def normalize_profile(profile: CandidateProfile) -> CandidateProfile:
    """Enrich in place (and return) — one call after any extraction path."""
    for skill in profile.skills:
        match = normalize_skill(skill.name)
        if match:
            skill.canonical, skill.category = match.canonical, match.category
    for edu in profile.education:
        if edu.degree:
            deg = normalize_degree(edu.degree)
            if deg:
                edu.degree_canonical, edu.degree_level = deg.canonical, deg.level
        edu.grade_cgpa_10 = normalize_grade(edu.grade_value, edu.grade_scale)
        if edu.institution:
            inst = canonicalize_institution(edu.institution)
            if inst:
                edu.institution_canonical = inst.canonical
                edu.institution_tier = inst.tier
    for exp in profile.experience:
        if exp.employer:
            exp.employer_canonical = canonicalize_employer(exp.employer)
    location = profile.contact.location
    if location and location.value:
        city = find_city(location.value)
        if city:
            profile.contact.location_city = city.city
            profile.contact.location_tier = city.tier
    if profile.notice_period and profile.notice_period.value:
        found = parse_notice_period(profile.notice_period.value)
        if found:
            profile.notice_period_days = found.days
    return profile


__all__ = ["normalize_profile"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_profile.py -v`
Expected: 6 passed.

Then: `.resume\Scripts\python.exe -m pytest -q`
Expected: 185 passed (179 + 6) — the schema growth must not break any existing test.

- [ ] **Step 6: Commit**

```powershell
git add app/candidates/schema.py app/candidates/normalize/__init__.py tests/test_normalize_profile.py
git commit -m "feat(candidates): normalized profile fields + normalize_profile orchestrator"
```

---

### Task 6: Extractor integration — lift location/notice, normalize every path

**Files:**
- Modify: `app/candidates/extractor.py`
- Test: `tests/test_normalize_integration.py`

**Interfaces:**
- Consumes: `normalize_profile` (T5), `find_city`/`parse_notice_period` (T4), existing `_split_sections`/`_contact`/`ExtractedStr`/`SourceSpan`.
- Produces: `heuristic_profile` now fills `contact.location` (first known city in the header block, with span) and `profile.notice_period` (whole-text scan, with span); `PROFILE_EXTRACTION_SYSTEM` gains a `notice_period` key; `_parse_llm_profile` maps it; `extract_profile` calls `normalize_profile(profile)` on BOTH paths before hashing. The API surface is unchanged — normalized fields ride the profile JSON.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_normalize_integration.py`:

```python
"""S1.4 end-to-end: extractor lifts location/notice, extract_profile
normalizes both paths, API exposes normalized fields. Fully offline."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.candidates.extractor import extract_profile, heuristic_profile
from app.main import create_app
from app.services.llm import NullLLM
from tests.conftest import FakeLLM, make_services

FIXTURES = Path(__file__).parent / "fixtures"

_BASE = (FIXTURES / "full_profile_resume.txt").read_text(encoding="utf-8")
# Notice period sits in the resume header, where candidates actually put it —
# appending at the tail would land it inside the CERTIFICATIONS section.
RESUME = _BASE.replace("\n\nEXPERIENCE", "\nNotice Period: 30 days\n\nEXPERIENCE", 1)


def test_heuristic_lifts_location_with_span():
    profile = heuristic_profile(RESUME)
    loc = profile.contact.location
    assert loc is not None and loc.value == "Bengaluru"
    assert RESUME[loc.span.start : loc.span.end] == "Bengaluru"


def test_heuristic_lifts_notice_period_with_span():
    profile = heuristic_profile(RESUME)
    notice = profile.notice_period
    assert notice is not None and "30 days" in notice.value
    assert RESUME[notice.span.start : notice.span.end] == notice.value


async def test_extract_profile_normalizes_offline(settings):
    result = await extract_profile(RESUME, llm=NullLLM(settings), settings=settings)
    assert result.method == "heuristic"
    p = result.profile
    canon = {s.canonical for s in p.skills}
    assert {"python", "sql", "apache_spark", "kafka", "airflow", "aws"} <= canon
    edu = p.education[0]
    assert edu.degree_canonical == "btech" and edu.degree_level == "bachelor"
    assert edu.grade_cgpa_10 == 8.6
    assert edu.institution_canonical == "NIT Trichy"
    assert edu.institution_tier == "tier_2"
    assert {e.employer_canonical for e in p.experience} == {"Flipkart", "Infosys"}
    assert p.contact.location_city == "Bengaluru"
    assert p.contact.location_tier == "metro"
    assert p.notice_period_days == 30


async def test_llm_path_notice_period_normalized(settings):
    payload = json.dumps(
        {
            "full_name": {"value": "Arjun Mehta", "confidence": 0.9,
                          "source_excerpt": "Arjun Mehta"},
            "headline": None,
            "contact": {
                "email": {"value": "arjun.mehta@example.com", "confidence": 0.9,
                          "source_excerpt": "arjun.mehta@example.com"},
                "phone": None,
                "location": {"value": "Bengaluru, Karnataka", "confidence": 0.9,
                             "source_excerpt": "Bengaluru, Karnataka"},
            },
            "notice_period": {"value": "30 days", "confidence": 0.9,
                              "source_excerpt": "Notice Period: 30 days"},
            "education": [],
            "experience": [],
            "skills": [{"name": "PySpark", "confidence": 0.9, "source_excerpt": "Spark"}],
            "projects": [],
            "certifications": [],
            "links": [],
        }
    )
    llm = FakeLLM({"RESUME:": payload}, settings=settings)
    result = await extract_profile(RESUME, llm=llm, settings=settings)
    assert result.method == "llm"
    p = result.profile
    assert p.notice_period is not None and p.notice_period.value == "30 days"
    assert p.notice_period_days == 30  # bare-value form parsed
    assert p.contact.location_city == "Bengaluru"
    assert p.skills[0].canonical == "apache_spark"


def test_api_exposes_normalized_profile(settings, flywheel):
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        cid = client.post(
            "/candidates", json={"resume_text": RESUME, "evaluate": False}
        ).json()["candidate_id"]
        detail = client.get(f"/candidates/{cid}").json()
    lp = detail["latest_profile"]
    assert lp["contact"]["location_city"] == "Bengaluru"
    assert lp["notice_period_days"] == 30
    assert lp["education"][0]["institution_canonical"] == "NIT Trichy"
    canon = {s["canonical"] for s in lp["skills"]}
    assert {"python", "apache_spark"} <= canon
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_integration.py -v`
Expected: all 5 FAIL — the heuristic tests on `loc is not None` / `notice is not None` (extractor doesn't lift them yet); the normalization tests on `canonical is None` / `location_city is None` (nothing calls `normalize_profile`).

- [ ] **Step 3: Implement the extractor changes**

In `app/candidates/extractor.py`:

**(a)** Add imports (with the other `app.candidates` imports):

```python
from app.candidates.normalize import normalize_profile
from app.candidates.normalize.location import find_city, parse_notice_period
```

**(b)** Add two helpers directly after `_contact`:

```python
def _location(sections: dict[str, list[tuple[int, str]]]) -> Optional[ExtractedStr]:
    """First known Indian city in the pre-section header block."""
    for start, line in sections.get("header", []):
        hit = find_city(line)
        if hit:
            return ExtractedStr(
                value=hit.text,
                confidence=0.7,
                span=SourceSpan(
                    start=start + hit.start, end=start + hit.end, text=hit.text
                ),
            )
    return None


def _notice_period(text: str) -> Optional[ExtractedStr]:
    """Whole-text notice-period scan; normalization to days is S1.4's
    normalize_profile, this only captures the claim + provenance."""
    hit = parse_notice_period(text)
    if hit is None:
        return None
    return ExtractedStr(
        value=hit.text,
        confidence=0.85,
        span=SourceSpan(start=hit.start, end=hit.end, text=hit.text),
    )
```

**(c)** Replace `heuristic_profile` so both are wired in:

```python
def heuristic_profile(text: str) -> CandidateProfile:
    """Deterministic extraction — the no-LLM floor the pipeline can trust."""
    sections = _split_sections(text)
    full_name, headline = _header_identity(sections)
    contact = _contact(text)
    contact.location = _location(sections)
    return CandidateProfile(
        full_name=full_name,
        headline=headline,
        contact=contact,
        notice_period=_notice_period(text),
        education=_education(sections.get("education", [])),
        experience=_experience(sections.get("experience", [])),
        skills=_skills(sections.get("skills", [])),
        projects=_projects(sections.get("projects", [])),
        certifications=_certifications(sections.get("certifications", [])),
        links=_links(text),
    )
```

**(d)** In `PROFILE_EXTRACTION_SYSTEM`, add one line to the JSON shape, directly under the closing `},` of the `"contact"` block:

```
  "notice_period": {"value": str, "confidence": 0-1, "source_excerpt": str},
```

and one line to the `Rules:` list at the bottom:

```
- notice_period: the stated notice period / joining availability, verbatim (e.g. "30 days", "immediate joiner"); null when the resume does not state one.
```

**(e)** In `_parse_llm_profile`, add `notice_period` to the initial `CandidateProfile(...)` construction, after the `contact=ContactInfo(...)` argument:

```python
        notice_period=_scalar(payload.get("notice_period"), text),
```

**(f)** In `extract_profile`, add the normalization call directly after the heuristic-fallback block (before `hashing.apply_contact_hashes`):

```python
    if profile is None or _is_empty(profile):
        profile = heuristic_profile(resume_text)
        method = "heuristic"
    normalize_profile(profile)  # S1.4: same enrichment for both paths
    hashing.apply_contact_hashes(profile, settings.contact_hash_salt)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_normalize_integration.py -v`
Expected: 5 passed.

Then the full suite: `.resume\Scripts\python.exe -m pytest -q`
Expected: 190 passed (185 + 5) — existing extractor/API tests must stay green (the new fields are additive; no canned FakeLLM payload contains `notice_period`, which maps to `None`).

- [ ] **Step 5: Commit**

```powershell
git add app/candidates/extractor.py tests/test_normalize_integration.py
git commit -m "feat(extractor): lift location + notice period; normalize profiles on both paths"
```

---

### Task 7: Smoke script (uvicorn + HTTP) + roadmap close-out

**Files:**
- Create: `scripts/smoke_s14.py`
- Modify: `docs/ROADMAP.md` (status board, current state, session log)

**Interfaces:**
- Consumes: the S1.3 HTTP surface (`POST /candidates` with `evaluate: false`, `GET /candidates/{id}`, `DELETE /candidates/{id}`); Alembic env; fixture `tests/fixtures/full_profile_resume.txt`.
- Produces: `python scripts/smoke_s14.py` exiting 0 with `SMOKE OK` — with a live key (LLM extraction) AND key-less (heuristic floor). This is the per-sprint uvicorn smoke the conventions require.

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s14.py`:

```python
"""S1.4 smoke: India normalization visible over the real HTTP surface.

Migrates a scratch DB, boots uvicorn, uploads the fixture resume (with a
notice-period line injected into the header), then verifies the stored
latest_profile carries canonical skills / degree / CGPA / institution /
employer / city / notice-period. evaluate=false — S1.4 is extraction +
normalization, so no depth-eval tokens are spent. Works with a live key
(LLM extraction) and without one (heuristic floor). Run from the repo root:
    python scripts/smoke_s14.py
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

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")
PORT = 8014
BASE = f"http://127.0.0.1:{PORT}"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s14.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update(
        {
            "DEE_CANDIDATES_DB_URL": url,
            "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
            "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
            # Chroma init can hang on some machines; the smoke stays bounded.
            "DEE_VECTORSTORE_BACKEND": "memory",
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            base_text = FIXTURE.read_text(encoding="utf-8")
            text = base_text.replace(
                "\n\nEXPERIENCE", "\nNotice Period: 30 days\n\nEXPERIENCE", 1
            )
            created = c.post(
                "/candidates", json={"resume_text": text, "evaluate": False}
            ).json()
            cid = created["candidate_id"]
            print(
                f"POST /candidates [{created['extraction_method']}]: candidate={cid[:8]}"
            )

            detail = c.get(f"/candidates/{cid}").json()
            lp = detail["latest_profile"]
            edu = (lp.get("education") or [{}])[0]
            contact = lp.get("contact") or {}
            skills = {s.get("canonical") for s in lp.get("skills") or []}
            employers = {
                e.get("employer_canonical") for e in lp.get("experience") or []
            }

            deleted = c.delete(f"/candidates/{cid}")
            gone = c.get(f"/candidates/{cid}")

        checks = {
            "degree canonicalized (btech / bachelor)": edu.get("degree_canonical")
            == "btech"
            and edu.get("degree_level") == "bachelor",
            "CGPA normalized on 10-point scale": edu.get("grade_cgpa_10") == 8.6,
            "institution canonical + tier": edu.get("institution_canonical")
            == "NIT Trichy"
            and edu.get("institution_tier") == "tier_2",
            "employers canonicalized": {"Flipkart", "Infosys"} <= employers,
            "skills mapped to taxonomy": {
                "python", "sql", "apache_spark", "kafka", "airflow", "aws"
            } <= skills,
            "city normalized (Bengaluru metro)": contact.get("location_city")
            == "Bengaluru"
            and contact.get("location_tier") == "metro",
            "notice period parsed (30 days)": lp.get("notice_period_days") == 30,
            "DPDP delete still green": deleted.status_code == 200
            and gone.status_code == 404,
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"  {'OK  ' if ok else 'FAIL'} {name}")
        if failed:
            return 1
        print("\nSMOKE OK")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=15)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the smoke offline (deterministic floor)**

Run (PowerShell, repo root):

```powershell
$env:DEE_OPENROUTER_API_KEY = ""; .resume\Scripts\python.exe scripts/smoke_s14.py
```

Expected: `[heuristic]` on the POST line, all 8 checks `OK`, exit 0 with `SMOKE OK`.
Afterwards clear the override so later shells aren't key-less: `Remove-Item Env:DEE_OPENROUTER_API_KEY`.

- [ ] **Step 3: Run the smoke live (if a key is configured in .env)**

Run: `.resume\Scripts\python.exe scripts/smoke_s14.py`
Expected: `[llm]` extraction (or `[heuristic]` if no key), all checks `OK`, `SMOKE OK`. If the LLM omits or reshapes a value the checks depend on (e.g. grade), investigate the prompt mapping — don't loosen the check.

- [ ] **Step 4: Full suite one last time**

Run: `.resume\Scripts\python.exe -m pytest -q`
Expected: 190 passed, 0 failed.

- [ ] **Step 5: Update `docs/ROADMAP.md`**

- Status board: `[~] S1.4` → `[x] S1.4` (PI-1 complete), `[ ] S2.1` → `[~] S2.1`.
- "Current state": current sprint → S2.1 (AI-generated-resume signals); next action → write the S2.1 plan (new pipeline node; deterministic signals first, LLM-assisted second; conservative gate stays); last-session line summarizing S1.4 (branch, `app/candidates/normalize/` package, schema fields, extractor wiring, test count 190, smoke result).
- Session log: append a dated S1.4 entry.

- [ ] **Step 6: Commit**

```powershell
git add scripts/smoke_s14.py docs/ROADMAP.md
git commit -m "chore: S1.4 smoke script + roadmap close-out"
```

---

## Execution notes

- Run everything from the repo root; the venv is `.resume\Scripts\python.exe` (Windows).
- Only `app/candidates/schema.py` (Task 5) and `app/candidates/extractor.py` (Task 6) are modified among existing files — if a task seems to need changes to the graph, store, routes, or Alembic, stop and re-read the architecture note.
- The lookup tables are curated starting points, deliberately conservative: unknown values normalize to `None`, never to a guess. Extending a table is a data change + one test, not a design change.
- Known accepted limitation: `find_city` on header lines can false-positive when a header mentions an institution containing a city name (e.g. "Delhi Technological University" in a headline). Accepted for S1.4 — the value keeps its provenance span so PI-2 forensics can audit it.
- Tests always run offline (NullLLM/FakeLLM); only the optional live smoke spends tokens (extraction only — the smoke posts with `evaluate: false`).
- Merge flow (matches S1.1–S1.3): after all tasks green, merge `s14-india-normalization` into `main` per superpowers:finishing-a-development-branch.
