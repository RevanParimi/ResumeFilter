# S2.3 — Resume-Farm Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect near-duplicate resumes ACROSS candidates (resume farms mass-produce applications from one template with the identity swapped) and surface an advisory `Report.resume_farm` assessment, without touching claim verdicts or depth scoring.

**Architecture:** A pure module `app/fabrication/similarity.py` computes deterministic MinHash signatures over word shingles of the resume with identity channels (email/phone/URLs) masked out — no LLM, no embeddings (ChromaDB is unreliable on this machine and real embeddings are PI-5 backlog by design). Signatures persist in a new `resume_fingerprints` table (Alembic `0002`, FK CASCADE so DPDP deletes erase them). Detection runs in the **API layer**, not the graph: self-exclusion requires the uploader's `candidate_id`, which the graph deliberately never sees (S1.3/S2.2 principle: the graph stays candidate-store-unaware). POST /candidates fingerprints the text, compares against all other candidates' stored signatures, builds a `ResumeFarmAssessment`, and passes it into `engine.evaluate(resume_farm=...)` exactly like `candidate_profile` in S2.2; the `report` node attaches it to `Report.resume_farm` and logs one flywheel record. POST /evaluate (no store, no identity) gets `resume_farm = None`.

**Tech Stack:** Python 3.13, Pydantic v2, SQLAlchemy + Alembic (SQLite, PG-shaped), LangGraph, pytest (offline), FastAPI/uvicorn for the smoke.

## Global Constraints

- Branch: `s23-resume-farm` (create from `main` at Task 1 Step 0).
- TDD, fully offline tests; `pytest -q` green before merge. Baseline: **270 tests**; this plan adds ~44 (→ ~314).
- **Advisory only — the conservative gate stays**: matches never change any `VerdictStatus`, `depth_score`, or `depth_band`. `ResumeFarmAssessment.advisory` is always `True`. Fusion into calibration is S2.4, not here.
- False positives are the existential risk. Shared resume templates are common and **legitimate** (coaching institutes, resume builders, college placement cells) — all reviewer-facing copy must say so and include the advisory framing ("reviewer context, never a rejection signal").
- **No LLM anywhere in S2.3** — MinHash needs no model; the convention requires deterministic fallbacks for LLM steps, not LLMs everywhere.
- A candidate's OWN resumes (re-uploads, new versions) are never matched against themselves — exclusion is by `candidate_id`.
- Config: new tunables go in `config.yaml` AND as `Settings` fields (env override `DEE_*`); no secrets. Exact new tunables (copy verbatim): `rf_shingle_words: 3`, `rf_num_permutations: 128`, `rf_min_shingles: 40`, `rf_similar_threshold: 0.60`, `rf_near_dup_threshold: 0.80`, `rf_cluster_candidates_min: 3`, `rf_max_matches: 10`.
- DB: new table `resume_fingerprints` via Alembic migration `0002_resume_fingerprints`; FKs `ondelete="CASCADE"` so the existing DPDP delete paths erase fingerprints with the resume/candidate — no new delete endpoints needed. The drift-guard test (`tests/test_migrations.py`) must stay green.
- No new graph node, no changes to `app/domains/`, calibration, `ai_signals`, or `cross_field`.
- Sprint ends with a local smoke (`scripts/smoke_s23.py`, uvicorn + HTTP, key-less AND live) and a ROADMAP.md update.
- Commit messages: NO Co-Authored-By trailer (user preference).

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `app/schemas/fabrication.py` | Modify | Append S2.3 contracts: `DuplicationBand`, `ResumeMatch`, `ResumeFarmAssessment` |
| `app/fabrication/similarity.py` | Create | Pure MinHash: masking, shingles, signatures, similarity estimate, `fingerprint_text`, `assess_resume_farm` |
| `app/fabrication/__init__.py` | Modify | Docstring line for S2.3 |
| `app/candidates/models.py` | Modify | `FingerprintRow` ORM model |
| `alembic/versions/0002_resume_fingerprints.py` | Create | Migration for the new table |
| `app/candidates/store.py` | Modify | `save_fingerprint` + `similar_resumes` |
| `app/graph/state.py` | Modify | `resume_farm` input field |
| `app/graph/build.py` | Modify | `evaluate(resume_farm=...)` kwarg |
| `app/schemas/report.py` | Modify | `Report.resume_farm` (Optional) |
| `app/graph/nodes/report.py` | Modify | Pass-through + summary sentence (near_duplicate only) + flywheel record |
| `app/api/routes.py` | Modify | POST /candidates: fingerprint → save → compare → assess → pass to engine + response field |
| `app/core/config.py` | Modify | Seven `rf_*` Settings fields |
| `config.yaml` | Modify | Same seven keys, commented |
| `tests/fixtures/farm_genai_resume_a.txt` | Create | Farm template, identity A |
| `tests/fixtures/farm_genai_resume_b.txt` | Create | Same template, identity B (name/city/contact swapped) |
| `tests/conftest.py` | Modify | `farm_resume_a` / `farm_resume_b` fixtures |
| `tests/test_resume_farm_schema.py` | Create | Task 1 tests |
| `tests/test_similarity.py` | Create | Task 2 tests |
| `tests/test_resume_farm_assess.py` | Create | Task 3 tests |
| `tests/test_fingerprint_store.py` | Create | Task 4 tests |
| `tests/test_migrations.py` | Modify | Expect `resume_fingerprints` after upgrade head |
| `tests/test_report_resume_farm.py` | Create | Task 5 tests |
| `tests/test_resume_farm_api.py` | Create | Task 6 tests |
| `scripts/smoke_s23.py` | Create | Task 7 smoke |
| `docs/ROADMAP.md` | Modify | Task 7 close-out |

---

### Task 1: Resume-farm schemas

**Files:**
- Modify: `app/schemas/fabrication.py` (append after `CrossFieldAssessment`)
- Test: `tests/test_resume_farm_schema.py`

**Interfaces:**
- Consumes: nothing new (pydantic only; `StrEnum`, `BaseModel`, `Field` already imported in the module).
- Produces (every later task imports these exact names from `app.schemas.fabrication`):
  - `DuplicationBand` (StrEnum: `INSUFFICIENT_DATA="insufficient_data"`, `UNIQUE="unique"`, `SIMILAR="similar"`, `NEAR_DUPLICATE="near_duplicate"`)
  - `ResumeMatch(candidate_id: str, resume_id: str, similarity: float 0..1)`
  - `ResumeFarmAssessment(score: float = 0.0, confidence: float = 0.0, band: DuplicationBand = INSUFFICIENT_DATA, matches: list[ResumeMatch] = [], corpus_size: int = 0, reasoning: str = "", advisory: bool = True)`

- [ ] **Step 0: Create the branch**

```bash
git checkout main
git checkout -b s23-resume-farm
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resume_farm_schema.py`:

```python
"""S2.3 contracts: conservative defaults, bounds, JSON round-trip."""

import pytest
from pydantic import ValidationError

from app.schemas.fabrication import (
    DuplicationBand,
    ResumeFarmAssessment,
    ResumeMatch,
)


def test_defaults_are_conservative():
    a = ResumeFarmAssessment()
    assert a.band is DuplicationBand.INSUFFICIENT_DATA
    assert a.score == 0.0
    assert a.confidence == 0.0
    assert a.matches == []
    assert a.corpus_size == 0
    assert a.advisory is True  # hard mandate, mirrors Report


def test_similarity_bounds_enforced():
    with pytest.raises(ValidationError):
        ResumeMatch(candidate_id="c", resume_id="r", similarity=1.5)
    with pytest.raises(ValidationError):
        ResumeFarmAssessment(confidence=-0.1)


def test_band_values_are_wire_stable():
    assert DuplicationBand.NEAR_DUPLICATE.value == "near_duplicate"
    assert DuplicationBand.UNIQUE.value == "unique"


def test_round_trips_through_json():
    a = ResumeFarmAssessment(
        score=0.91,
        confidence=0.9,
        band=DuplicationBand.NEAR_DUPLICATE,
        matches=[ResumeMatch(candidate_id="c1", resume_id="r1", similarity=0.91)],
        corpus_size=4,
        reasoning="r",
    )
    again = ResumeFarmAssessment.model_validate_json(a.model_dump_json())
    assert again == a
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_resume_farm_schema.py -q`
Expected: FAIL — `ImportError: cannot import name 'ResumeFarmAssessment'`

- [ ] **Step 3: Append the schemas**

Append to `app/schemas/fabrication.py` (after `CrossFieldAssessment`):

```python
class DuplicationBand(StrEnum):
    """Conservative advisory bands. INSUFFICIENT_DATA when we can't say."""

    INSUFFICIENT_DATA = "insufficient_data"
    UNIQUE = "unique"            # nothing similar among stored resumes
    SIMILAR = "similar"          # notable content overlap with another candidate
    NEAR_DUPLICATE = "near_duplicate"  # near-identical content, or a farm-like cluster


class ResumeMatch(BaseModel):
    """One stored resume (another candidate's) with estimated content overlap."""

    candidate_id: str
    resume_id: str
    similarity: float = Field(ge=0.0, le=1.0)  # estimated Jaccard over shingles


class ResumeFarmAssessment(BaseModel):
    """The farm-detection output: cross-candidate near-duplicate signals.

    Computed in the API layer (needs the candidate store + the uploader's
    identity for self-exclusion — the graph never sees either). Shared resume
    templates are common and legitimate; ADVISORY, never a rejection signal."""

    score: float = Field(default=0.0, ge=0.0, le=1.0)  # max match similarity
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    band: DuplicationBand = DuplicationBand.INSUFFICIENT_DATA
    matches: list[ResumeMatch] = Field(default_factory=list)
    corpus_size: int = 0  # fingerprinted resumes (other candidates) compared against
    reasoning: str = ""
    advisory: bool = True  # mirrors Report: never a rejection signal
```

Also append this line to the module docstring's list of sprints: `S2.3 — resume-farm detection: cross-candidate near-duplicate signals (MinHash).`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_resume_farm_schema.py tests/test_fabrication_schema.py tests/test_cross_field_schema.py -q`
Expected: `12 passed` (4 new + 8 existing untouched)

- [ ] **Step 5: Commit**

```bash
git add app/schemas/fabrication.py tests/test_resume_farm_schema.py
git commit -m "feat(schemas): resume-farm detection contracts (S2.3)"
```

---

### Task 2: MinHash similarity module + config knobs + farm fixture pair

**Files:**
- Create: `app/fabrication/similarity.py` (masking, shingles, MinHash; `assess_resume_farm` arrives in Task 3)
- Modify: `app/fabrication/__init__.py` (docstring), `app/core/config.py` (seven `rf_*` fields), `config.yaml` (same keys)
- Create: `tests/fixtures/farm_genai_resume_a.txt`, `tests/fixtures/farm_genai_resume_b.txt`
- Modify: `tests/conftest.py` (two fixtures)
- Test: `tests/test_similarity.py`

**Interfaces:**
- Consumes: `Settings` from `app.core.config`.
- Produces (exact names Tasks 3–6 build on):
  - `Fingerprint(algo: str, values: list[int], shingle_count: int)` — pydantic model
  - `algo_id(settings: Settings) -> str` — e.g. `"minhash-v1:128x3"`
  - `normalize_for_shingles(text: str) -> str`
  - `shingle_set(text: str, size: int) -> set[str]`
  - `minhash_signature(shingles: set[str], num_perm: int) -> list[int]`
  - `estimate_similarity(a: list[int], b: list[int]) -> float` (raises `ValueError` on length mismatch)
  - `fingerprint_text(text: str, settings: Settings) -> Fingerprint | None` (`None` when `< rf_min_shingles` shingles)
  - `Settings.rf_shingle_words/rf_num_permutations/rf_min_shingles/rf_similar_threshold/rf_near_dup_threshold/rf_cluster_candidates_min/rf_max_matches`
  - conftest fixtures `farm_resume_a: str`, `farm_resume_b: str`

- [ ] **Step 1: Create the farm fixture pair**

The pair simulates a real farm: identical template and bullets, identity swapped. Fixture B differs from A **only** in name, city, email, and phone — email/phone are masked by normalization, so only the name and city words separate the shingle sets, which lands the estimated similarity around 0.93 (comfortably above the 0.80 near-dup default with 128 permutations, stderr ≈ 0.02). Both carry extractor-friendly contact lines with DIFFERENT email+phone so identity resolution creates two distinct candidates (that is what makes the match cross-candidate).

Create `tests/fixtures/farm_genai_resume_a.txt` with EXACTLY:

```
Arjun Mehta — Senior GenAI Engineer
Pune | arjun.mehta@example.com | +91 98220 11223

SUMMARY

GenAI engineer with four years of experience building retrieval-augmented
generation systems and LLM evaluation tooling for enterprise clients.

EXPERIENCE

Senior GenAI Engineer at CloudMinds Software, Mar 2023 - Aug 2025
- Designed a retrieval-augmented assistant over 2M support documents using
  hybrid BM25 and dense retrieval with a cross-encoder reranker
- Reduced hallucination rate from 14% to 6% by adding grounded citation
  checks and a retrieval sufficiency gate before generation
- Built an offline evaluation harness with 1,200 curated question-answer
  pairs scored nightly in CI

ML Engineer at Brightpath Labs, Jun 2021 - Feb 2023
- Fine-tuned domain adapters for customer-intent classification across
  eleven regional languages
- Shipped a feature store consumed by three ranking models and cut training
  data preparation time from days to hours
- Automated drift monitoring with weekly evaluation reports to product teams

EDUCATION

B.E. in Computer Science — Pune Institute of Computer Technology, 2013 - 2017, CGPA 8.2/10

SKILLS

Python, PyTorch, LangChain, FAISS, Postgres, Docker
```

Create `tests/fixtures/farm_genai_resume_b.txt` as an exact copy of A with exactly four edits: line 1 name → `Kunal Deshpande`, line 2 → `Nagpur | kunal.deshpande@example.com | +91 99870 44556`. Everything else byte-identical:

```
Kunal Deshpande — Senior GenAI Engineer
Nagpur | kunal.deshpande@example.com | +91 99870 44556

SUMMARY

GenAI engineer with four years of experience building retrieval-augmented
generation systems and LLM evaluation tooling for enterprise clients.

EXPERIENCE

Senior GenAI Engineer at CloudMinds Software, Mar 2023 - Aug 2025
- Designed a retrieval-augmented assistant over 2M support documents using
  hybrid BM25 and dense retrieval with a cross-encoder reranker
- Reduced hallucination rate from 14% to 6% by adding grounded citation
  checks and a retrieval sufficiency gate before generation
- Built an offline evaluation harness with 1,200 curated question-answer
  pairs scored nightly in CI

ML Engineer at Brightpath Labs, Jun 2021 - Feb 2023
- Fine-tuned domain adapters for customer-intent classification across
  eleven regional languages
- Shipped a feature store consumed by three ranking models and cut training
  data preparation time from days to hours
- Automated drift monitoring with weekly evaluation reports to product teams

EDUCATION

B.E. in Computer Science — Pune Institute of Computer Technology, 2013 - 2017, CGPA 8.2/10

SKILLS

Python, PyTorch, LangChain, FAISS, Postgres, Docker
```

(Dates are all in the past — nothing depends on the test run date. The education years 2013–2017 keep the profile timeline coherent so `cross_field` stays quiet on these fixtures.)

Add to `tests/conftest.py` (next to the `inconsistent_resume` fixture):

```python
@pytest.fixture
def farm_resume_a() -> str:
    return (FIXTURES / "farm_genai_resume_a.txt").read_text(encoding="utf-8")


@pytest.fixture
def farm_resume_b() -> str:
    return (FIXTURES / "farm_genai_resume_b.txt").read_text(encoding="utf-8")
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_similarity.py`:

```python
"""MinHash similarity — pure, offline, deterministic by construction."""

import pytest

from app.fabrication.similarity import (
    Fingerprint,
    algo_id,
    estimate_similarity,
    fingerprint_text,
    minhash_signature,
    normalize_for_shingles,
    shingle_set,
)


def test_normalization_masks_identity_channels():
    text = "Arjun Mehta | arjun.mehta@example.com | +91 98220 11223 | www.arjun.dev"
    out = normalize_for_shingles(text)
    assert "example" not in out          # email masked
    assert "98220" not in out            # phone masked
    assert "arjun dev" not in out        # url masked
    assert "arjun mehta" in out          # names are NOT masked (only ~2 words of noise)


def test_year_ranges_are_masked_like_phones():
    # The phone mask deliberately swallows bare digit runs such as "2013 - 2017";
    # farms stagger dates, so removing them from shingles helps detection.
    assert "2013" not in normalize_for_shingles("B.E. — PICT, 2013 - 2017")


def test_shingles_are_word_trigrams():
    s = shingle_set("alpha beta gamma delta", 3)
    assert s == {"alpha beta gamma", "beta gamma delta"}
    assert shingle_set("too short", 3) == set()


def test_signature_is_deterministic_and_sized():
    sh = shingle_set("one two three four five six seven eight nine ten", 3)
    a = minhash_signature(sh, 64)
    b = minhash_signature(sh, 64)
    assert a == b
    assert len(a) == 64


def test_identical_sets_estimate_one_disjoint_near_zero():
    x = shingle_set("the quick brown fox jumps over the lazy dog again and again", 3)
    y = shingle_set("completely different resume content about databases and networking systems here", 3)
    sx, sy = minhash_signature(x, 128), minhash_signature(y, 128)
    assert estimate_similarity(sx, sx) == 1.0
    assert estimate_similarity(sx, sy) < 0.15


def test_estimate_rejects_incomparable_signatures():
    with pytest.raises(ValueError):
        estimate_similarity([1, 2, 3], [1, 2])


def test_fingerprint_text_rejects_short_text(settings):
    assert fingerprint_text("too little text to fingerprint honestly", settings) is None


def test_fingerprint_text_shape(settings, farm_resume_a):
    fp = fingerprint_text(farm_resume_a, settings)
    assert isinstance(fp, Fingerprint)
    assert fp.algo == algo_id(settings) == "minhash-v1:128x3"
    assert len(fp.values) == settings.rf_num_permutations
    assert fp.shingle_count >= settings.rf_min_shingles


def test_contact_swap_alone_changes_nothing(settings, farm_resume_a):
    # Masking makes an email/phone-only swap invisible: same signature.
    swapped = farm_resume_a.replace("arjun.mehta@example.com", "someone.else@other.org")
    swapped = swapped.replace("+91 98220 11223", "+91 90000 00001")
    assert fingerprint_text(swapped, settings).values == fingerprint_text(farm_resume_a, settings).values


def test_farm_pair_estimates_near_duplicate(settings, farm_resume_a, farm_resume_b):
    fa = fingerprint_text(farm_resume_a, settings)
    fb = fingerprint_text(farm_resume_b, settings)
    assert estimate_similarity(fa.values, fb.values) >= 0.85


def test_farm_vs_genuine_estimates_low(settings, farm_resume_a, genuine_resume):
    fa = fingerprint_text(farm_resume_a, settings)
    fg = fingerprint_text(genuine_resume, settings)
    assert estimate_similarity(fa.values, fg.values) < 0.4


def test_settings_expose_rf_knobs(settings):
    assert settings.rf_shingle_words == 3
    assert settings.rf_num_permutations == 128
    assert settings.rf_min_shingles == 40
    assert settings.rf_similar_threshold == 0.60
    assert settings.rf_near_dup_threshold == 0.80
    assert settings.rf_cluster_candidates_min == 3
    assert settings.rf_max_matches == 10
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_similarity.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fabrication.similarity'`

- [ ] **Step 4: Write the module + config knobs**

Create `app/fabrication/similarity.py`:

```python
"""Resume-farm similarity (S2.3) — deterministic MinHash, no LLM, no I/O.

Resume farms mass-produce applications from one template: same bullets,
different name/contact. Detection therefore compares CONTENT — word shingles
with identity channels (emails, phones, URLs) masked out — across candidates,
via MinHash signatures so the store never diffs raw text pairs.

Conservative by construction: shared resume templates are common and
legitimate (coaching institutes, resume builders, college placement cells),
so results are ADVISORY context for a reviewer, never a rejection signal.
S2.4 owns fusion into a unified fabrication_risk.

Determinism contract: signatures are comparable ONLY within one algo id
(hash family + permutation count + shingle size). Changing any of those
bumps `algo_id`, and stored rows only ever join on an exact algo id.
"""

from __future__ import annotations

import hashlib
import random
import re
from functools import lru_cache

from pydantic import BaseModel

from app.core.config import Settings
from app.schemas.fabrication import (
    DuplicationBand,
    ResumeFarmAssessment,
    ResumeMatch,
)

_ALGO_FAMILY = "minhash-v1"
_MERSENNE = (1 << 61) - 1  # modulus for the affine permutations
_SEED = 0x5EED_FA12  # fixed forever for minhash-v1; changing it means a new family

_EMAIL_RE = re.compile(r"\S+@\S+")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
# Also swallows bare digit runs like "2013 - 2017": farms stagger dates, so
# removing them from shingles helps detection and never hurts genuine pairs.
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{7,}\d")
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


class Fingerprint(BaseModel):
    """One resume's MinHash signature + how much text stood behind it."""

    algo: str
    values: list[int]
    shingle_count: int


def algo_id(settings: Settings) -> str:
    return f"{_ALGO_FAMILY}:{settings.rf_num_permutations}x{settings.rf_shingle_words}"


def normalize_for_shingles(text: str) -> str:
    """Lowercased content with identity channels masked. Farms swap the name,
    email and phone but keep the bullets — contact strings must never
    contribute shingles (the name itself is ~2 words of noise; acceptable)."""
    t = text.lower()
    t = _URL_RE.sub(" ", t)
    t = _EMAIL_RE.sub(" ", t)
    t = _PHONE_RE.sub(" ", t)
    return _NON_WORD_RE.sub(" ", t).strip()


def shingle_set(text: str, size: int) -> set[str]:
    words = normalize_for_shingles(text).split()
    if len(words) < size:
        return set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


@lru_cache(maxsize=4)
def _permutations(num_perm: int) -> tuple[tuple[int, int], ...]:
    rng = random.Random(_SEED)  # Random's algorithm is stable across CPython versions
    return tuple(
        (rng.randrange(1, _MERSENNE), rng.randrange(0, _MERSENNE))
        for _ in range(num_perm)
    )


def _stable_hash(shingle: str) -> int:
    digest = hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def minhash_signature(shingles: set[str], num_perm: int) -> list[int]:
    """Classic MinHash: min over affine permutations of stable 64-bit hashes."""
    if not shingles:
        raise ValueError("cannot sign an empty shingle set")
    hashes = [_stable_hash(s) for s in shingles]
    return [
        min((a * h + b) % _MERSENNE for h in hashes) for a, b in _permutations(num_perm)
    ]


def estimate_similarity(a: list[int], b: list[int]) -> float:
    """Fraction of agreeing components ≈ Jaccard similarity of the shingle
    sets. Only signatures from the same algo id are comparable."""
    if not a or len(a) != len(b):
        raise ValueError("signatures are not comparable (length mismatch)")
    return sum(x == y for x, y in zip(a, b)) / len(a)


def fingerprint_text(text: str, settings: Settings) -> Fingerprint | None:
    """None when the text is too short to fingerprint honestly (a similarity
    estimate over a handful of shingles would be noise, not signal)."""
    shingles = shingle_set(text, settings.rf_shingle_words)
    if len(shingles) < settings.rf_min_shingles:
        return None
    return Fingerprint(
        algo=algo_id(settings),
        values=minhash_signature(shingles, settings.rf_num_permutations),
        shingle_count=len(shingles),
    )
```

(The `DuplicationBand` / `ResumeFarmAssessment` / `ResumeMatch` imports are used by Task 3's `assess_resume_farm`; keeping them in place now avoids an import churn commit.)

Add to `app/core/config.py`, directly after the S2.2 `xf_*` block:

```python
    # --- Fabrication defense (PI-2, S2.3): resume-farm detection -----------------
    # Deterministic MinHash over contact-masked word shingles, compared across
    # candidates at ingest. ADVISORY: shared resume templates are common and
    # legitimate; matches are reviewer context, never a rejection signal.
    # Changing shingle_words/num_permutations changes the algo id — previously
    # stored fingerprints simply stop participating until re-fingerprinted.
    rf_shingle_words: int = 3
    rf_num_permutations: int = 128
    rf_min_shingles: int = 40
    rf_similar_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    rf_near_dup_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    rf_cluster_candidates_min: int = 3
    rf_max_matches: int = 10
```

Add to `config.yaml`, directly after the S2.2 `xf_*` block:

```yaml
# --- Fabrication defense (PI-2) — S2.3 resume-farm detection -------------------
# Deterministic MinHash over contact-masked word shingles, compared across
# candidates at ingest. ADVISORY: shared templates are common and legitimate.
rf_shingle_words: 3              # words per shingle
rf_num_permutations: 128         # signature size (stderr of estimate ~ 1/sqrt(n))
rf_min_shingles: 40              # below this -> band "insufficient_data"
rf_similar_threshold: 0.60       # estimated overlap to count as a match at all
rf_near_dup_threshold: 0.80      # any match >= this -> band "near_duplicate"
rf_cluster_candidates_min: 3     # matches from >= this many other candidates -> near_duplicate
rf_max_matches: 10               # matches carried on the assessment (best first)
```

Append this line to the `app/fabrication/__init__.py` docstring: `S2.3 similarity.py is orchestrated by the API layer (POST /candidates), not a node.`

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_similarity.py -q`
Expected: `12 passed`. If `test_farm_pair_estimates_near_duplicate` fails, verify the two fixture files differ ONLY on lines 1–2 (name/city/contact) — do not loosen the assertion.

- [ ] **Step 6: Run the full suite (config change must not break anything)**

Run: `pytest -q`
Expected: all green (~286 tests).

- [ ] **Step 7: Commit**

```bash
git add app/fabrication/similarity.py app/fabrication/__init__.py app/core/config.py config.yaml tests/fixtures/farm_genai_resume_a.txt tests/fixtures/farm_genai_resume_b.txt tests/conftest.py tests/test_similarity.py
git commit -m "feat(fabrication): deterministic MinHash resume similarity + rf_* knobs (S2.3)"
```

---

### Task 3: Farm assessment + banding

**Files:**
- Modify: `app/fabrication/similarity.py` (append `assess_resume_farm`)
- Test: `tests/test_resume_farm_assess.py`

**Interfaces:**
- Consumes: Task 1 schemas; Task 2 module (imports already in place).
- Produces (Tasks 5–6 rely on this exact signature):
  - `assess_resume_farm(matches: list[ResumeMatch], *, shingle_count: int, corpus_size: int, settings: Settings) -> ResumeFarmAssessment` — `matches` are already filtered at `rf_similar_threshold` by the store; `score` = max similarity; `confidence = 0.0` when `shingle_count < rf_min_shingles`, else `min(0.9, 0.6 + 0.05 * min(corpus_size, 6))` (a tiny corpus makes "unique" a weak claim).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resume_farm_assess.py`:

```python
"""Farm banding — pure, offline, conservative copy mandated."""

from app.fabrication.similarity import assess_resume_farm
from app.schemas.fabrication import DuplicationBand, ResumeMatch


def _m(cand: str, sim: float, resume: str = "r") -> ResumeMatch:
    return ResumeMatch(candidate_id=cand, resume_id=f"{resume}_{cand}", similarity=sim)


def test_short_text_is_insufficient_regardless_of_matches(settings):
    a = assess_resume_farm(
        [_m("c1", 0.95)], shingle_count=10, corpus_size=5, settings=settings
    )
    assert a.band is DuplicationBand.INSUFFICIENT_DATA
    assert a.confidence == 0.0


def test_no_matches_is_unique(settings):
    a = assess_resume_farm([], shingle_count=200, corpus_size=6, settings=settings)
    assert a.band is DuplicationBand.UNIQUE
    assert a.score == 0.0
    assert a.matches == []
    assert a.corpus_size == 6
    assert a.confidence == 0.9


def test_empty_corpus_unique_has_low_confidence(settings):
    a = assess_resume_farm([], shingle_count=200, corpus_size=0, settings=settings)
    assert a.band is DuplicationBand.UNIQUE
    assert a.confidence == 0.6  # "unique among nothing" is a weak claim


def test_single_high_match_is_near_duplicate(settings):
    a = assess_resume_farm(
        [_m("c1", 0.91)], shingle_count=200, corpus_size=4, settings=settings
    )
    assert a.band is DuplicationBand.NEAR_DUPLICATE
    assert a.score == 0.91


def test_mid_match_is_similar_only(settings):
    a = assess_resume_farm(
        [_m("c1", 0.65)], shingle_count=200, corpus_size=4, settings=settings
    )
    assert a.band is DuplicationBand.SIMILAR


def test_cluster_of_mid_matches_escalates_to_near_duplicate(settings):
    # A farm rarely produces one perfect copy; it produces MANY near copies.
    matches = [_m("c1", 0.65), _m("c2", 0.68), _m("c3", 0.62)]
    a = assess_resume_farm(matches, shingle_count=200, corpus_size=8, settings=settings)
    assert a.band is DuplicationBand.NEAR_DUPLICATE


def test_two_versions_of_one_other_candidate_stay_similar(settings):
    # Two resumes from ONE other candidate is not a cluster of candidates.
    matches = [_m("c1", 0.65), _m("c1", 0.68, resume="r2")]
    a = assess_resume_farm(matches, shingle_count=200, corpus_size=8, settings=settings)
    assert a.band is DuplicationBand.SIMILAR


def test_reasoning_carries_the_advisory_framing(settings):
    a = assess_resume_farm(
        [_m("c1", 0.91)], shingle_count=200, corpus_size=4, settings=settings
    )
    assert "never a rejection signal" in a.reasoning
    assert a.advisory is True
    clean = assess_resume_farm([], shingle_count=200, corpus_size=4, settings=settings)
    assert "no stored resume" in clean.reasoning
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_resume_farm_assess.py -q`
Expected: FAIL — `ImportError: cannot import name 'assess_resume_farm'`

- [ ] **Step 3: Append the assessment**

Append to `app/fabrication/similarity.py`:

```python
def assess_resume_farm(
    matches: list[ResumeMatch],
    *,
    shingle_count: int,
    corpus_size: int,
    settings: Settings,
) -> ResumeFarmAssessment:
    """Band the store's match list (already filtered at rf_similar_threshold).

    NEAR_DUPLICATE fires on one near-identical copy OR a farm-like cluster
    (matches from >= rf_cluster_candidates_min distinct other candidates).
    Pure so S2.4 can reuse it when fusing fabrication_risk."""
    if shingle_count < settings.rf_min_shingles:
        return ResumeFarmAssessment()  # INSUFFICIENT_DATA defaults

    confidence = min(0.9, 0.6 + 0.05 * min(corpus_size, 6))
    distinct = len({m.candidate_id for m in matches})
    if any(m.similarity >= settings.rf_near_dup_threshold for m in matches) or (
        distinct >= settings.rf_cluster_candidates_min
    ):
        band = DuplicationBand.NEAR_DUPLICATE
    elif matches:
        band = DuplicationBand.SIMILAR
    else:
        band = DuplicationBand.UNIQUE
    score = max((m.similarity for m in matches), default=0.0)

    if matches:
        reasoning = (
            f"[deterministic] {len(matches)} stored resume(s) from {distinct} other "
            f"candidate(s) share >= {settings.rf_similar_threshold:.0%} estimated "
            f"content overlap (max {score:.0%}) out of {corpus_size} compared; "
            f"shared templates are common and legitimate — reviewer context, "
            f"never a rejection signal"
        )
    else:
        reasoning = (
            f"[deterministic] no stored resume among {corpus_size} compared shares "
            f">= {settings.rf_similar_threshold:.0%} estimated content overlap"
        )
    return ResumeFarmAssessment(
        score=score,
        confidence=confidence,
        band=band,
        matches=matches,
        corpus_size=corpus_size,
        reasoning=reasoning,
        advisory=True,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_resume_farm_assess.py tests/test_similarity.py -q`
Expected: `20 passed`

- [ ] **Step 5: Commit**

```bash
git add app/fabrication/similarity.py tests/test_resume_farm_assess.py
git commit -m "feat(fabrication): resume-farm assessment + conservative banding (S2.3)"
```

---

### Task 4: Fingerprint persistence — model, migration 0002, store methods

**Files:**
- Modify: `app/candidates/models.py` (append `FingerprintRow`)
- Create: `alembic/versions/0002_resume_fingerprints.py`
- Modify: `app/candidates/store.py` (two methods), `tests/test_migrations.py` (expect the new table)
- Test: `tests/test_fingerprint_store.py`

**Interfaces:**
- Consumes: `Fingerprint`, `estimate_similarity` (Task 2); `ResumeMatch` (Task 1).
- Produces (Task 6 relies on these exact signatures):
  - `FingerprintRow` (table `resume_fingerprints`; unique `(resume_id, algo)`; FKs CASCADE)
  - `CandidateStore.save_fingerprint(fp: Fingerprint, *, resume_id: str, candidate_id: str) -> bool` — idempotent per `(resume_id, algo)`; `True` when a row was written
  - `CandidateStore.similar_resumes(fp: Fingerprint, *, exclude_candidate_id: str, threshold: float, limit: int) -> tuple[list[ResumeMatch], int]` — matches from OTHER candidates only, same algo only, best-first, capped at `limit`; second element = number of fingerprints compared (corpus size)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fingerprint_store.py`:

```python
"""Fingerprint persistence: idempotent save, cross-candidate query, DPDP cascade."""

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.fabrication.similarity import Fingerprint, fingerprint_text
from tests.conftest import make_candidate_store


def _ingest(store, text: str):
    profile = heuristic_profile(text)
    return store.ingest(ExtractionResult(profile=profile, method="heuristic"), text)


def _fp(values: list[int], algo: str = "minhash-v1:128x3") -> Fingerprint:
    return Fingerprint(algo=algo, values=values, shingle_count=100)


def test_save_is_idempotent_per_resume_and_algo(farm_resume_a, settings):
    store = make_candidate_store()
    out = _ingest(store, farm_resume_a)
    fp = fingerprint_text(farm_resume_a, settings)
    assert store.save_fingerprint(fp, resume_id=out.resume_id, candidate_id=out.candidate_id) is True
    assert store.save_fingerprint(fp, resume_id=out.resume_id, candidate_id=out.candidate_id) is False


def test_similar_resumes_finds_the_other_candidate(farm_resume_a, farm_resume_b, settings):
    store = make_candidate_store()
    out_a = _ingest(store, farm_resume_a)
    out_b = _ingest(store, farm_resume_b)
    assert out_a.candidate_id != out_b.candidate_id  # different contact hashes
    fa = fingerprint_text(farm_resume_a, settings)
    fb = fingerprint_text(farm_resume_b, settings)
    store.save_fingerprint(fa, resume_id=out_a.resume_id, candidate_id=out_a.candidate_id)
    store.save_fingerprint(fb, resume_id=out_b.resume_id, candidate_id=out_b.candidate_id)

    matches, corpus = store.similar_resumes(
        fb, exclude_candidate_id=out_b.candidate_id, threshold=0.60, limit=10
    )
    assert corpus == 1
    assert len(matches) == 1
    assert matches[0].candidate_id == out_a.candidate_id
    assert matches[0].resume_id == out_a.resume_id
    assert matches[0].similarity >= 0.85


def test_own_candidate_is_always_excluded(farm_resume_a, settings):
    store = make_candidate_store()
    out = _ingest(store, farm_resume_a)
    fp = fingerprint_text(farm_resume_a, settings)
    store.save_fingerprint(fp, resume_id=out.resume_id, candidate_id=out.candidate_id)
    matches, corpus = store.similar_resumes(
        fp, exclude_candidate_id=out.candidate_id, threshold=0.60, limit=10
    )
    assert matches == [] and corpus == 0  # a perfect self-match never surfaces


def test_threshold_and_algo_filter(farm_resume_a, genuine_resume, settings):
    store = make_candidate_store()
    out_a = _ingest(store, farm_resume_a)
    out_g = _ingest(store, genuine_resume)
    fa = fingerprint_text(farm_resume_a, settings)
    fg = fingerprint_text(genuine_resume, settings)
    store.save_fingerprint(fa, resume_id=out_a.resume_id, candidate_id=out_a.candidate_id)
    # Unrelated content below threshold -> compared but not matched.
    matches, corpus = store.similar_resumes(
        fg, exclude_candidate_id=out_g.candidate_id, threshold=0.60, limit=10
    )
    assert corpus == 1 and matches == []
    # Different algo id -> not even compared (signatures incomparable).
    alien = _fp([1] * 64, algo="minhash-v1:64x3")
    matches, corpus = store.similar_resumes(
        alien, exclude_candidate_id=out_g.candidate_id, threshold=0.0, limit=10
    )
    assert corpus == 0 and matches == []


def test_dpdp_deletes_cascade_to_fingerprints(farm_resume_a, farm_resume_b, settings):
    store = make_candidate_store()
    out_a = _ingest(store, farm_resume_a)
    out_b = _ingest(store, farm_resume_b)
    fa = fingerprint_text(farm_resume_a, settings)
    fb = fingerprint_text(farm_resume_b, settings)
    store.save_fingerprint(fa, resume_id=out_a.resume_id, candidate_id=out_a.candidate_id)
    store.save_fingerprint(fb, resume_id=out_b.resume_id, candidate_id=out_b.candidate_id)

    store.delete_resume(out_a.resume_id)          # resume-level erasure
    _, corpus = store.similar_resumes(
        fb, exclude_candidate_id=out_b.candidate_id, threshold=0.60, limit=10
    )
    assert corpus == 0

    store.delete_candidate(out_b.candidate_id)    # candidate-level erasure
    _, corpus = store.similar_resumes(
        fa, exclude_candidate_id="nobody", threshold=0.0, limit=10
    )
    assert corpus == 0
```

Also modify `tests/test_migrations.py::test_upgrade_head_creates_candidate_tables` — change the assertion line to:

```python
    assert {"candidates", "resumes", "extractions", "resume_fingerprints"} <= names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fingerprint_store.py tests/test_migrations.py -q`
Expected: FAIL — `ImportError`/`AttributeError` on `save_fingerprint`, and the migration test failing on the missing table.

- [ ] **Step 3: Implement model, migration, store methods**

Append to `app/candidates/models.py`:

```python
class FingerprintRow(Base):
    """MinHash signature of one resume's contact-masked content (S2.3).

    One row per resume per algo id — rows only ever join on an exact algo so
    incompatible signatures are never compared. DPDP: cascades away with the
    resume/candidate, like every other derived row."""

    __tablename__ = "resume_fingerprints"
    __table_args__ = (
        UniqueConstraint("resume_id", "algo", name="uq_fingerprints_resume_algo"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resume_id: Mapped[str] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    algo: Mapped[str] = mapped_column(String(32), index=True)
    signature: Mapped[list] = mapped_column(JSON)
    shingle_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

Create `alembic/versions/0002_resume_fingerprints.py`:

```python
"""resume fingerprints for farm detection (S2.3)

Revision ID: 0002_resume_fingerprints
Revises: 0001_candidate_store
Create Date: 2026-07-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0002_resume_fingerprints"
down_revision = "0001_candidate_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_fingerprints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resume_id",
            sa.String(36),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("algo", sa.String(32), nullable=False),
        sa.Column("signature", sa.JSON(), nullable=False),
        sa.Column("shingle_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("resume_id", "algo", name="uq_fingerprints_resume_algo"),
    )
    op.create_index("ix_resume_fingerprints_resume_id", "resume_fingerprints", ["resume_id"])
    op.create_index(
        "ix_resume_fingerprints_candidate_id", "resume_fingerprints", ["candidate_id"]
    )
    op.create_index("ix_resume_fingerprints_algo", "resume_fingerprints", ["algo"])


def downgrade() -> None:
    op.drop_table("resume_fingerprints")
```

Append to `app/candidates/store.py` (methods on `CandidateStore`, after `delete_resume`; also extend the imports: add `FingerprintRow` to the `app.candidates.models` import line, and add `from app.fabrication.similarity import Fingerprint, estimate_similarity` and `from app.schemas.fabrication import ResumeMatch` — `similarity` is a pure module, so the store stays I/O-clean):

```python
    def save_fingerprint(
        self, fp: Fingerprint, *, resume_id: str, candidate_id: str
    ) -> bool:
        """Idempotent per (resume, algo): re-uploads of an existing version
        write nothing. Returns True when a row was actually written."""
        with self._session_factory() as session:
            exists = session.execute(
                select(FingerprintRow.id).where(
                    FingerprintRow.resume_id == resume_id,
                    FingerprintRow.algo == fp.algo,
                )
            ).first()
            if exists:
                return False
            session.add(
                FingerprintRow(
                    resume_id=resume_id,
                    candidate_id=candidate_id,
                    algo=fp.algo,
                    signature=list(fp.values),
                    shingle_count=fp.shingle_count,
                )
            )
            session.commit()
            return True

    def similar_resumes(
        self,
        fp: Fingerprint,
        *,
        exclude_candidate_id: str,
        threshold: float,
        limit: int,
    ) -> tuple[list[ResumeMatch], int]:
        """Estimated-similarity matches from OTHER candidates, best first, plus
        how many stored fingerprints were compared (the corpus size). Linear
        scan in Python — signatures are small int lists and SQLite-scale
        corpora are thousands, not millions; LSH banding is the flagged
        optimization if this ever grows past that."""
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(FingerprintRow).where(
                        FingerprintRow.algo == fp.algo,
                        FingerprintRow.candidate_id != exclude_candidate_id,
                    )
                )
                .scalars()
                .all()
            )
            matches = [
                ResumeMatch(
                    candidate_id=r.candidate_id,
                    resume_id=r.resume_id,
                    similarity=sim,
                )
                for r in rows
                if (sim := estimate_similarity(fp.values, list(r.signature))) >= threshold
            ]
            matches.sort(key=lambda m: m.similarity, reverse=True)
            return matches[:limit], len(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fingerprint_store.py tests/test_migrations.py -q`
Expected: `7 passed` (5 new + 2 migration tests, drift guard included — it fails if model and migration disagree).

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: all green (~299 tests).

- [ ] **Step 6: Commit**

```bash
git add app/candidates/models.py app/candidates/store.py alembic/versions/0002_resume_fingerprints.py tests/test_fingerprint_store.py tests/test_migrations.py
git commit -m "feat(candidates): resume_fingerprints table + store methods, migration 0002 (S2.3)"
```

---

### Task 5: State + Report + report-node surfacing

**Files:**
- Modify: `app/graph/state.py` (one input field), `app/graph/build.py` (`evaluate` kwarg), `app/schemas/report.py` (`Report.resume_farm`), `app/graph/nodes/report.py` (pass-through + summary + flywheel)
- Test: `tests/test_report_resume_farm.py`

**Interfaces:**
- Consumes: `ResumeFarmAssessment`, `DuplicationBand` (Task 1).
- Produces: `EvaluationState.resume_farm: Optional[ResumeFarmAssessment]` (input field, like `candidate_profile`); `EvaluationEngine.evaluate(..., resume_farm: Optional[ResumeFarmAssessment] = None)`; `Report.resume_farm: Optional[ResumeFarmAssessment]`; flywheel `record_type: "resume_farm"`. Task 6 passes the assessment through this kwarg.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_report_resume_farm.py`:

```python
"""Report surfaces the farm assessment: field, summary note, flywheel record."""

from app.graph.build import EvaluationEngine
from app.graph.nodes.report import make_report_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import DuplicationBand, ResumeFarmAssessment, ResumeMatch


def _near_dup() -> ResumeFarmAssessment:
    return ResumeFarmAssessment(
        score=0.91,
        confidence=0.9,
        band=DuplicationBand.NEAR_DUPLICATE,
        matches=[ResumeMatch(candidate_id="c1", resume_id="r1", similarity=0.91)],
        corpus_size=4,
        reasoning="r",
    )


async def test_report_carries_assessment_and_flywheel_record(services, flywheel):
    node = make_report_node(services)
    out = await node(EvaluationState(resume_text="text", resume_farm=_near_dup()))
    rep = out["report"]
    assert rep.resume_farm is not None
    assert rep.resume_farm.band is DuplicationBand.NEAR_DUPLICATE
    assert rep.advisory is True and rep.human_review_required is True
    records = [r for r in flywheel.records if r.get("record_type") == "resume_farm"]
    assert len(records) == 1
    assert records[0]["band"] == "near_duplicate"
    assert records[0]["match_count"] == 1
    assert records[0]["corpus_size"] == 4
    assert records[0]["outcome"] is None


async def test_summary_note_only_for_near_duplicate(services):
    node = make_report_node(services)
    loud = await node(EvaluationState(resume_text="t", resume_farm=_near_dup()))
    assert "Resume-farm signals" in loud["report"].summary
    assert "never a rejection signal" in loud["report"].summary

    quiet = await node(
        EvaluationState(
            resume_text="t",
            resume_farm=ResumeFarmAssessment(
                band=DuplicationBand.UNIQUE, confidence=0.9, corpus_size=3
            ),
        )
    )
    assert "Resume-farm signals" not in quiet["report"].summary
    assert quiet["report"].resume_farm.band is DuplicationBand.UNIQUE


async def test_absent_assessment_stays_absent(services, flywheel):
    node = make_report_node(services)
    out = await node(EvaluationState(resume_text="t"))
    assert out["report"].resume_farm is None
    assert not [r for r in flywheel.records if r.get("record_type") == "resume_farm"]


async def test_engine_kwarg_lands_on_the_report(services, genuine_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=genuine_resume, resume_farm=_near_dup())
    assert report.resume_farm is not None
    assert report.resume_farm.score == 0.91


async def test_engine_default_is_none(services, genuine_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=genuine_resume)
    assert report.resume_farm is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report_resume_farm.py -q`
Expected: FAIL — `ValidationError`/`AttributeError`: `EvaluationState` has no field `resume_farm`.

- [ ] **Step 3: Implement the four wiring edits**

In `app/graph/state.py`, add after the `candidate_profile` field (and extend the existing `app.schemas.fabrication` import with `ResumeFarmAssessment`):

```python
    # S2.3: resume-farm assessment computed by the API layer. Detection needs
    # the candidate store AND the uploader's candidate_id for self-exclusion —
    # the graph deliberately sees neither, so this arrives as an input.
    # None => not assessed (ad-hoc POST /evaluate runs).
    resume_farm: Optional[ResumeFarmAssessment] = None
```

In `app/graph/build.py`, extend `EvaluationEngine.evaluate` (add the import of `ResumeFarmAssessment` from `app.schemas.fabrication`):

```python
    async def evaluate(
        self,
        *,
        resume_text: Optional[str] = None,
        resume_pdf_b64: Optional[str] = None,
        github_url: Optional[str] = None,
        portfolio_url: Optional[str] = None,
        domain: str = "genai",
        candidate_profile: Optional[CandidateProfile] = None,
        resume_farm: Optional[ResumeFarmAssessment] = None,
    ) -> Report:
        initial = EvaluationState(
            domain=domain,
            raw_resume_text=resume_text,
            resume_pdf_b64=resume_pdf_b64,
            github_url=github_url,
            portfolio_url=portfolio_url,
            candidate_profile=candidate_profile,
            resume_farm=resume_farm,
        )
```

(The rest of the method body is unchanged.)

In `app/schemas/report.py`, add after the `cross_field` field (extend the existing `app.schemas.fabrication` import with `ResumeFarmAssessment`):

```python
    # S2.3: advisory resume-farm signals (cross-candidate near-duplicate
    # context for the reviewer, never a verdict; fusion into calibration is
    # S2.4). None for pre-S2.3 reports and ad-hoc POST /evaluate runs.
    resume_farm: Optional[ResumeFarmAssessment] = None
```

In `app/graph/nodes/report.py`:

1. Extend the fabrication import: `from app.schemas.fabrication import AILikelihoodBand, ConsistencyBand, DuplicationBand, FindingSeverity`.
2. After the `xf` summary block, add:

```python
        rf = state.resume_farm
        if rf is not None and rf.band is DuplicationBand.NEAR_DUPLICATE:
            summary += (
                f" Resume-farm signals: {len(rf.matches)} stored resume(s) from "
                f"other candidates share up to {rf.score:.0%} estimated content "
                f"overlap — shared templates are common and legitimate; reviewer "
                f"context only, never a rejection signal."
            )
```

3. In the `Report(...)` constructor call, add `resume_farm=state.resume_farm,` after `cross_field=state.cross_field,`.
4. After the `cross_field` flywheel block, add:

```python
        if state.resume_farm is not None:
            services.flywheel.log(
                {
                    "record_type": "resume_farm",
                    "evaluation_id": state.evaluation_id,
                    "report_id": rep.id,
                    "domain": state.domain,
                    "band": state.resume_farm.band.value,
                    "score": state.resume_farm.score,
                    "confidence": state.resume_farm.confidence,
                    "match_count": len(state.resume_farm.matches),
                    "corpus_size": state.resume_farm.corpus_size,
                    "outcome": None,  # closed later by human/hiring signal
                }
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report_resume_farm.py -q`
Expected: `5 passed`

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: all green (~304 tests).

- [ ] **Step 6: Commit**

```bash
git add app/graph/state.py app/graph/build.py app/schemas/report.py app/graph/nodes/report.py tests/test_report_resume_farm.py
git commit -m "feat(report): surface advisory resume_farm assessment + flywheel record (S2.3)"
```

---

### Task 6: POST /candidates wiring

**Files:**
- Modify: `app/api/routes.py` (fingerprint → save → compare → assess → pass to engine; response field)
- Test: `tests/test_resume_farm_api.py`

**Interfaces:**
- Consumes: `fingerprint_text`, `assess_resume_farm` (Tasks 2–3); `save_fingerprint`, `similar_resumes` (Task 4); `evaluate(resume_farm=...)` (Task 5).
- Produces: `CandidateCreateResponse.resume_farm: Optional[ResumeFarmAssessment]` — ALWAYS set on POST /candidates (bulk imports with `evaluate=False` are exactly the farm scenario, so the signal must not depend on running a depth-eval). POST /evaluate is untouched: `Report.resume_farm` stays `None` there.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resume_farm_api.py`:

```python
"""Farm detection over the API: cross-candidate matches, self-exclusion,
evaluate=False visibility. Offline: NullLLM => heuristic extraction."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_services


@pytest.fixture
def api(settings, flywheel):
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, services


def _post(client, text, **extra):
    resp = client.post("/candidates", json={"resume_text": text, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_first_upload_is_unique(api, farm_resume_a):
    client, _ = api
    body = _post(client, farm_resume_a)
    farm = body["resume_farm"]
    assert farm is not None
    assert farm["band"] == "unique"
    assert farm["corpus_size"] == 0
    assert farm["advisory"] is True
    assert body["report"]["resume_farm"]["band"] == "unique"


def test_identity_swapped_copy_flags_near_duplicate(api, farm_resume_a, farm_resume_b):
    client, _ = api
    first = _post(client, farm_resume_a)
    second = _post(client, farm_resume_b)
    assert second["candidate_id"] != first["candidate_id"]
    farm = second["resume_farm"]
    assert farm["band"] == "near_duplicate"
    assert farm["matches"][0]["candidate_id"] == first["candidate_id"]
    assert farm["matches"][0]["similarity"] >= 0.85
    # The advisory note reached the report summary.
    assert "Resume-farm signals" in second["report"]["summary"]
    assert "never a rejection signal" in second["report"]["summary"]


def test_own_reupload_never_self_matches(api, farm_resume_a):
    client, _ = api
    first = _post(client, farm_resume_a)
    again = _post(client, farm_resume_a)  # same contact -> same candidate, dedup
    assert again["candidate_id"] == first["candidate_id"]
    assert again["duplicate_resume"] is True
    assert again["resume_farm"]["band"] == "unique"


def test_new_version_of_own_resume_never_self_matches(api, farm_resume_a):
    client, _ = api
    first = _post(client, farm_resume_a)
    v2 = _post(client, farm_resume_a + "\nCERTIFICATIONS\n\nAWS Solutions Architect Associate\n")
    assert v2["candidate_id"] == first["candidate_id"]
    assert v2["resume_version"] == 2
    assert v2["resume_farm"]["band"] == "unique"


def test_bulk_import_still_sees_the_signal(api, farm_resume_a, farm_resume_b):
    client, _ = api
    _post(client, farm_resume_a, evaluate=False)
    second = _post(client, farm_resume_b, evaluate=False)
    assert second["report"] is None
    assert second["resume_farm"]["band"] == "near_duplicate"


def test_genuine_resume_stays_unique_next_to_the_farm(api, farm_resume_a, genuine_resume):
    client, _ = api
    _post(client, farm_resume_a)
    body = _post(client, genuine_resume)
    assert body["resume_farm"]["band"] == "unique"


def test_short_resume_is_insufficient_data(api):
    client, _ = api
    body = _post(client, "Asha Rao\nEmail: asha@example.com\nSKILLS\nPython")
    assert body["resume_farm"]["band"] == "insufficient_data"


def test_post_evaluate_has_no_farm_assessment(api, farm_resume_a):
    client, _ = api
    _post(client, farm_resume_a)
    rep = client.post("/evaluate", json={"resume_text": farm_resume_a}).json()
    assert rep["resume_farm"] is None  # no identity to exclude -> not assessed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_resume_farm_api.py -q`
Expected: FAIL — `KeyError: 'resume_farm'` (field not on the response yet).

- [ ] **Step 3: Wire the route**

In `app/api/routes.py`:

1. Add imports: `from app.fabrication.similarity import assess_resume_farm, fingerprint_text` and `from app.schemas.fabrication import ResumeFarmAssessment`.
2. Add the response field to `CandidateCreateResponse` (after `report`):

```python
    # S2.3: cross-candidate near-duplicate signals, computed at ingest so bulk
    # imports (evaluate=False) still see them. Advisory, like everything else.
    resume_farm: Optional[ResumeFarmAssessment] = None
```

3. In `create_candidate`, directly after `outcome = services.candidates.ingest(result, text)`:

```python
    # S2.3: fingerprint + farm check. Lives HERE, not in a graph node: the
    # comparison must exclude the uploader's own candidate (re-uploads and new
    # versions are legitimate), and the graph deliberately never learns the
    # candidate identity.
    farm = ResumeFarmAssessment()  # insufficient_data when the text is too short
    fp = fingerprint_text(text, services.settings)
    if fp is not None:
        services.candidates.save_fingerprint(
            fp, resume_id=outcome.resume_id, candidate_id=outcome.candidate_id
        )
        matches, corpus = services.candidates.similar_resumes(
            fp,
            exclude_candidate_id=outcome.candidate_id,
            threshold=services.settings.rf_similar_threshold,
            limit=services.settings.rf_max_matches,
        )
        farm = assess_resume_farm(
            matches,
            shingle_count=fp.shingle_count,
            corpus_size=corpus,
            settings=services.settings,
        )
```

4. Pass it into the engine call — change the `engine.evaluate(...)` call to:

```python
        report = await request.app.state.engine.evaluate(
            resume_text=text,
            domain=req.domain,
            candidate_profile=result.profile,
            resume_farm=farm,
        )
```

5. Add `resume_farm=farm,` to the `CandidateCreateResponse(...)` constructor at the end of the handler.

(DPDP note, no code needed: if the candidate is erased while the eval runs, the existing post-eval re-check already drops the report, and the fingerprint row cascades away with the candidate.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_resume_farm_api.py -q`
Expected: `8 passed`

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: all green (~312 tests). `tests/test_candidates_api.py` must pass untouched — its short `RESUME` constant now also gets a `resume_farm` key (`insufficient_data`), which no existing assertion inspects.

- [ ] **Step 6: Commit**

```bash
git add app/api/routes.py tests/test_resume_farm_api.py
git commit -m "feat(api): farm detection at ingest — fingerprint, compare, surface (S2.3)"
```

---

### Task 7: Smoke run + ROADMAP close-out

**Files:**
- Create: `scripts/smoke_s23.py`
- Modify: `docs/ROADMAP.md`

**Interfaces:**
- Consumes: the full S2.3 surface over real HTTP (uvicorn + migrated scratch SQLite DB).
- Produces: sprint completion evidence (smoke green key-less AND live) + updated roadmap.

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s23.py` (same harness shape as `scripts/smoke_s22.py`):

```python
"""S2.3 smoke: resume-farm detection visible over the real HTTP surface.

Boots uvicorn on a scratch, Alembic-migrated SQLite DB and walks the farm
story end to end: first upload of a template is unique; an identity-swapped
copy from a "different" candidate lands near_duplicate with the match pointing
back at the first candidate; the uploader's own re-upload never self-matches;
a genuine resume stays unique; POST /evaluate carries no farm assessment.
Works with a live key (LLM extraction) and without one (heuristic floor).
Run from the repo root:
    python scripts/smoke_s23.py
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

FARM_A = Path("tests/fixtures/farm_genai_resume_a.txt")
FARM_B = Path("tests/fixtures/farm_genai_resume_b.txt")
GENUINE = Path("tests/fixtures/genuine_genai_resume.txt")
PORT = 8023
BASE = f"http://127.0.0.1:{PORT}"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s23.db").as_posix()
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
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(600, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            text_a = FARM_A.read_text(encoding="utf-8")
            text_b = FARM_B.read_text(encoding="utf-8")
            text_g = GENUINE.read_text(encoding="utf-8")

            first = c.post("/candidates", json={"resume_text": text_a, "domain": "genai"}).json()
            print(f"upload A: candidate={first.get('candidate_id', '?')} "
                  f"farm_band={(first.get('resume_farm') or {}).get('band', '?')}")
            second = c.post("/candidates", json={"resume_text": text_b, "domain": "genai"}).json()
            print(f"upload B (identity-swapped copy): candidate={second.get('candidate_id', '?')} "
                  f"farm_band={(second.get('resume_farm') or {}).get('band', '?')}")
            re_up = c.post("/candidates", json={"resume_text": text_a, "domain": "genai"}).json()
            print(f"re-upload A: duplicate={re_up.get('duplicate_resume')} "
                  f"farm_band={(re_up.get('resume_farm') or {}).get('band', '?')}")
            genuine = c.post("/candidates", json={"resume_text": text_g, "domain": "genai"}).json()
            print(f"upload genuine: farm_band={(genuine.get('resume_farm') or {}).get('band', '?')}")
            adhoc = c.post("/evaluate", json={"resume_text": text_a, "domain": "genai"}).json()
            print(f"POST /evaluate: resume_farm={adhoc.get('resume_farm')}")

        farm_b = second.get("resume_farm") or {}
        matches = farm_b.get("matches") or [{}]
        rep_b = second.get("report") or {}
        checks = {
            "first upload: band unique (empty corpus)": (first.get("resume_farm") or {}).get("band")
            == "unique",
            "copy: two distinct candidates": second.get("candidate_id") != first.get("candidate_id"),
            "copy: band near_duplicate": farm_b.get("band") == "near_duplicate",
            "copy: match points at the first candidate": matches[0].get("candidate_id")
            == first.get("candidate_id"),
            "copy: report carries the assessment": (rep_b.get("resume_farm") or {}).get("band")
            == "near_duplicate",
            "copy: summary carries the advisory note": "never a rejection signal"
            in rep_b.get("summary", ""),
            "re-upload: own resume never self-matches": (re_up.get("resume_farm") or {}).get("band")
            == "unique",
            "genuine: stays unique next to the farm": (genuine.get("resume_farm") or {}).get("band")
            == "unique",
            "/evaluate: no farm assessment (no identity)": adhoc.get("resume_farm") is None,
            "mandates hold (advisory + human review)": rep_b.get("advisory") is True
            and rep_b.get("human_review_required") is True,
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

- [ ] **Step 2: Run the smoke key-less**

Run (PowerShell, repo root): `$env:DEE_OPENROUTER_API_KEY = ""; python scripts/smoke_s23.py`
Expected: all 10 checks `OK`, exit 0, `SMOKE OK`. (Key-less ⇒ NullLLM ⇒ heuristic extraction; farm detection is deterministic either way.)

- [ ] **Step 3: Run the smoke live**

Run (PowerShell, repo root, with the real key present in `.env`): `python scripts/smoke_s23.py`
Expected: all 10 checks `OK`, `SMOKE OK`. If the OpenRouter key has expired (it has before), ask the user to refresh it rather than skipping the live run.

- [ ] **Step 4: Run the full suite one last time**

Run: `pytest -q`
Expected: all green (~312 tests). Record the exact count for the ROADMAP entry.

- [ ] **Step 5: Update `docs/ROADMAP.md`**

- Status board: `[~] S2.3` → `[x] S2.3  Resume-farm detection — MinHash near-duplicates across candidates (resume_fingerprints table, API-layer detection, advisory Report.resume_farm)`.
- "Current state": current sprint → `S2.4 — Unified fabrication_risk`; next action → `Write the S2.4 plan (fuse ai_generation + cross_field + resume_farm into a unified advisory fabrication_risk on calibration + Report)`; last-session line summarizing S2.3 (branch, files, exact green test count from Step 4, smoke 10/10 key-less AND live).
- Append a session-log entry dated 2026-07-17 in the established style: what was built (similarity module, migration 0002, store methods, API wiring, `Report.resume_farm`), the conservative-design points (contact masking, self-exclusion by candidate_id, cluster escalation, advisory copy), test delta, smoke result, `Next: S2.4 plan.`

- [ ] **Step 6: Commit**

```bash
git add scripts/smoke_s23.py docs/ROADMAP.md
git commit -m "chore: S2.3 smoke script + roadmap close-out"
```

- [ ] **Step 7: Merge readiness**

Announce completion and use the superpowers:finishing-a-development-branch skill to decide merge/PR/cleanup for `s23-resume-farm` (S2.2 merged to `main` directly; expect the same unless the user says otherwise).

---

## Self-Review Notes

- **Spec coverage:** ROADMAP S2.3 scope is "near-duplicates across candidates (minhash/embeddings)" — minhash chosen (embeddings are PI-5 backlog; ChromaDB unreliable on this machine). Design-spec testing strategy asks for adversarial near-duplicate pairs → Task 2 fixtures. DPDP (consent/delete paths on new tables) → CASCADE FKs + Task 4 cascade tests. Advisory-only, deterministic-fallback, config-split, smoke-per-sprint conventions → global constraints + Tasks 2/6/7.
- **Type consistency:** `Fingerprint`/`ResumeMatch`/`ResumeFarmAssessment` signatures match across Tasks 2–6; `similar_resumes` returns `tuple[list[ResumeMatch], int]` everywhere it is consumed (Tasks 4 and 6); `evaluate(resume_farm=...)` matches Tasks 5 and 6.
- **Known-accepted residuals:** (1) resumes ingested before S2.3 have no fingerprints and silently sit outside the corpus — `corpus_size` makes that visible; a backfill utility is deliberately out of scope. (2) The linear scan is O(corpus) per ingest — fine at SQLite scale, LSH banding is the flagged upgrade path. (3) A farm that heavily rewords every copy can sink below 0.60 estimated overlap — the conservative trade is intentional (false positives are the existential risk).
