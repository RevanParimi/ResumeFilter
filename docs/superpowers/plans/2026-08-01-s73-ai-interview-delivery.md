# S7.3 — AI Interview Delivery v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver advisory, audio-first AI interviews that ask the depth report's own
probes, score the answers deterministically (with a capped LLM adjustment), and surface a
proxy-risk signal read from `IdentityAssurance` — candidate-initiated, consent-gated for
orgs, with audio structurally unstorable.

**Architecture:** A new pure-ish package `app/interview/` (peer of `app/verification/`)
plus one new service seam `app/services/speech.py`. Pure modules (`questions`, `scoring`,
`proxy`, `session`) hold all the logic and take no I/O; `store.py` persists two tables and
audits through `LedgerStore._audit`; `service.py` is the state machine and the gate layer.
Two HTTP planes: candidate (`X-Candidate-Key`) and org (`X-Org-Key`, gated by a new
`ConsentPurpose.INTERVIEW_READ`).

**Tech Stack:** Python 3.11+ · FastAPI · SQLAlchemy 2.0 + Alembic (SQLite, Postgres-shaped)
· pydantic v2 · pytest · OpenRouter (LLM + ASR, both optional at runtime).

**Spec:** `docs/superpowers/specs/2026-07-31-s73-ai-interview-delivery-design.md` — read it
before Task 1. Sections referenced below as "spec §N".

## Global Constraints

- **TDD, fully offline.** Every test runs with no API key and no network. `pytest -q` must
  be green before each commit. Never add a test that reaches a vendor.
- **Advisory only.** No auto-reject anywhere. `advisory=True` and
  `human_review_required=True` ship on the assessment and are asserted by tests.
- **Deterministic fallback for every LLM/ASR step.** No key ⇒ the interview still runs
  (text channel, deterministic scoring). `NullSpeech` refuses audio with a distinct error;
  `NullLLM` returns `{}` and deterministic scores stand.
- **Audio is structurally unstorable.** No column on either new table may hold audio bytes.
  The only audio field is `audio_digest` (sha256, `String(64)`). Asserted by a test.
- **The transcript IS stored** (spec §0.1) and is candidate-visible; it is **never** in an
  org-facing payload. Asserted by a test and by the smoke.
- **DPDP:** both tables CASCADE (sessions ← candidates, turns ← sessions). No new erasure
  path. Exactly one new `ConsentPurpose`: `INTERVIEW_READ`.
- **Config:** tunables in `config.yaml` + `Settings`; secrets only in `.env` (`DEE_*`).
  Band cut-points are knobs; scorer internals are module constants versioned by
  `SCORER_VERSION`.
- **Domain knowledge lives in `app/domains/`** via the `DomainModel` seam — the interview
  package never imports a concrete domain.
- **Layering:** `app/interview/` may import `app/verification/`; never the reverse.
- **Commits:** one per task, conventional-commit style, scope `s73`. **No `Co-Authored-By`
  trailer.**
- **Branch:** `s73-ai-interview-delivery`, created off `main` before Task 1.

---

## File Structure

**Created**

| File | Responsibility |
|---|---|
| `app/interview/__init__.py` | package marker |
| `app/interview/schema.py` | contracts + taxonomies (code constants) |
| `app/interview/questions.py` | `build_question_plan` — probes ▸ profile templates ▸ domain seeds |
| `app/interview/scoring.py` | per-turn rubric, capped LLM adjustment, aggregation, banding |
| `app/interview/proxy.py` | `assess_proxy_risk` over assurance + behaviour |
| `app/interview/session.py` | `effective_status` — read-time expiry, nothing else |
| `app/interview/models.py` | `InterviewSessionRow`, `InterviewTurnRow` |
| `app/interview/store.py` | `InterviewStore` — persistence, audit, org-gated read |
| `app/interview/service.py` | `InterviewService` — state machine + gates + wiring factory |
| `app/services/speech.py` | `SpeechClient` · `OpenRouterSpeech` · `NullSpeech` · `build_speech` |
| `alembic/versions/0015_ai_interviews.py` | two tables, both CASCADE |
| `scripts/smoke_s73.py` | uvicorn + scripted HTTP, key-less |
| `INTERVIEWS.md` | subsystem doc (peer of `VERIFICATION.md`) |
| `tests/test_interview_*.py`, `tests/test_speech_seam.py`, `tests/test_config_interview.py` | tests |

**Modified**

| File | Change |
|---|---|
| `app/ledger/schema.py` | `ConsentPurpose.INTERVIEW_READ` |
| `app/core/config.py` | `interview_*` knobs, `ret_interview_session_days`, `speech_*`, `"scoring"` tier |
| `config.yaml` | the same knobs, documented |
| `app/services/llm.py` | `Tier` gains `"scoring"` |
| `app/services/__init__.py` | `Services.speech`, `Services.interview`, wiring |
| `app/domains/base.py`, `app/domains/genai.py` | `interview_seed_questions()` |
| `app/portal/schema.py`, `app/portal/service.py`, `app/portal/retention.py` | `MyData.interviews`, retention window |
| `app/api/routes.py` | five candidate-plane routes, one org-plane route |
| `tests/conftest.py` | `FakeSpeech`, `make_services(speech=…, interview=…)` |
| `tests/test_migrations.py` | guards extended to the two new tables |
| `docs/ROADMAP.md`, `MODELS.md` | closeout |

---

### Task 0: Branch

- [ ] **Step 1: Create the branch**

```bash
git checkout main && git pull --ff-only 2>/dev/null; git checkout -b s73-ai-interview-delivery
pytest -q   # baseline: expect 1011 passed
```

Expected: 1011 passed. If not, stop and report — the baseline must be green.

---

### Task 1: Contracts (`app/interview/schema.py`)

**Files:**
- Create: `app/interview/__init__.py`, `app/interview/schema.py`
- Test: `tests/test_interview_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `InterviewStatus`, `QuestionSource`, `AnswerChannel`, `InterviewBand`,
  `ProxyBand`, `DIMENSIONS`, `InterviewQuestion`, `TurnScore`, `InterviewTurn`,
  `ProxyFinding`, `ProxyRisk`, `InterviewAssessment`, `InterviewSession`,
  `InterviewSummary`. Every later task imports from here.

- [ ] **Step 1: Write the failing test**

Create `tests/test_interview_schema.py`:

```python
"""S7.3 contracts. Taxonomies are code constants; the ladder-separation and
advisory guarantees are asserted here so no later layer can quietly drop them."""

from datetime import datetime, timezone

import pytest

from app.interview.schema import (
    DIMENSIONS, AnswerChannel, InterviewAssessment, InterviewBand, InterviewQuestion,
    InterviewStatus, InterviewSummary, ProxyBand, ProxyFinding, ProxyRisk, TurnScore,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def test_status_and_channel_vocabularies():
    assert {s.value for s in InterviewStatus} == {"in_progress", "completed", "abandoned"}
    assert {c.value for c in AnswerChannel} == {"audio", "text"}


def test_bands_are_ordered_vocabularies_not_numbers():
    # A band is a label over a score; unlike AssuranceLevel it is never max()'d.
    assert [b.value for b in InterviewBand] == [
        "insufficient_signal", "superficial", "emerging", "solid", "deep"
    ]
    assert [b.value for b in ProxyBand] == ["low", "moderate", "elevated"]


def test_interview_band_is_not_the_depth_band_type():
    """A resume-depth band and a live-interview band must never be silently
    interchangeable (spec section 5)."""
    from app.schemas.report import DepthBand
    assert InterviewBand is not DepthBand
    assert {b.value for b in InterviewBand} == {b.value for b in DepthBand}


def test_dimensions_are_the_four_rubric_axes():
    assert DIMENSIONS == ("specificity", "ownership", "depth", "consistency")


def test_proxy_finding_rejects_an_unknown_severity():
    ProxyFinding(id="x", severity="soft", message="m")
    ProxyFinding(id="x", severity="info", message="m")
    with pytest.raises(ValueError):
        ProxyFinding(id="x", severity="hard", message="m")


def test_proxy_risk_defaults_to_low_and_advisory():
    risk = ProxyRisk()
    assert risk.band is ProxyBand.LOW
    assert risk.findings == []
    assert risk.advisory is True


def test_assessment_is_advisory_and_review_required_by_default():
    a = InterviewAssessment(
        session_id="s1", candidate_id="c1", questions_planned=3, questions_answered=0,
        proxy=ProxyRisk(), scorer_version="s73.1",
    )
    assert a.advisory is True and a.human_review_required is True
    assert a.band is InterviewBand.INSUFFICIENT_SIGNAL
    assert a.overall == 0.0 and a.confidence == 0.0


def test_turn_score_can_be_empty_for_an_insufficient_answer():
    score = TurnScore(insufficient=True, codes=["insufficient_answer"])
    assert score.dimensions == {}


def test_summary_carries_no_transcript_field():
    """The org-facing projection must be structurally incapable of leaking words."""
    assert "transcript" not in InterviewSummary.model_fields
    assert "turns" not in InterviewSummary.model_fields


def test_question_carries_expected_signals_for_the_scorer():
    q = InterviewQuestion(id="q1", sequence=1, text="why?", source="probe",
                          expected_signals=["eval harness"], claim_id="cl1")
    assert q.expected_signals == ["eval harness"]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_interview_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.interview'`

- [ ] **Step 3: Implement**

Create `app/interview/__init__.py`:

```python
"""S7.3 AI interview delivery. Pure logic (questions/scoring/proxy/session) with
persistence and orchestration layered on top."""
```

Create `app/interview/schema.py`:

```python
"""S7.3 interview contracts.

Taxonomies here are code constants, not config -- the same stance as
AssuranceLevel/ConsentPurpose. Two deliberate shapes:

* `InterviewBand` duplicates `DepthBand`'s members and is NOT the same type. A
  resume-depth band answers "how deep does the written claim look"; an
  interview band answers "how deep did the live answers go". Making them one
  type invites a fusion nobody reviewed -- the S7.2 "two ladders" lesson.
* `InterviewSummary` has no transcript or turn field at all. It is the
  org-facing projection, and structural absence beats a filter someone forgets.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class InterviewStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"   # never stored; derived read-time past expires_at


class QuestionSource(StrEnum):
    PROBE = "probe"       # from the depth report -- the questions that matter most
    PROFILE = "profile"   # deterministic template over the candidate's own profile
    DOMAIN = "domain"     # a registered DomainModel's seed opener


class AnswerChannel(StrEnum):
    AUDIO = "audio"
    TEXT = "text"


class InterviewBand(StrEnum):
    INSUFFICIENT_SIGNAL = "insufficient_signal"
    SUPERFICIAL = "superficial"
    EMERGING = "emerging"
    SOLID = "solid"
    DEEP = "deep"


class ProxyBand(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"   # the ceiling: nothing here can CONFIRM a proxy


#: The rubric axes, in report order. A dict keyed by these is the score.
DIMENSIONS: tuple[str, ...] = ("specificity", "ownership", "depth", "consistency")

_PROXY_SEVERITIES = ("info", "soft")   # deliberately no "hard": see ProxyBand


class InterviewQuestion(BaseModel):
    id: str
    sequence: int
    text: str
    source: QuestionSource
    #: What a genuine answer would have to mention. For PROBE questions these
    #: are the verdict's missing_signals -- the scorer's yardstick without an LLM.
    expected_signals: list[str] = Field(default_factory=list)
    claim_id: Optional[str] = None


class TurnScore(BaseModel):
    """Per-answer rubric result. `dimensions` is a subset of DIMENSIONS: an
    insufficient answer scores nothing rather than scoring zero."""

    dimensions: dict[str, float] = Field(default_factory=dict)
    insufficient: bool = False
    codes: list[str] = Field(default_factory=list)


class InterviewTurn(BaseModel):
    id: str
    sequence: int
    question_id: str
    question_text: str
    question_source: QuestionSource
    expected_signals: list[str] = Field(default_factory=list)
    channel: AnswerChannel
    transcript: str = ""
    word_count: int = 0
    #: sha256 of the submitted audio. The bytes themselves are never stored and
    #: no field here could hold them.
    audio_digest: Optional[str] = None
    audio_duration_seconds: Optional[float] = None
    asked_at: datetime
    answered_at: datetime
    score: TurnScore = Field(default_factory=TurnScore)


class ProxyFinding(BaseModel):
    """One advisory proxy observation. Never an accusation, never `hard`."""

    id: str
    severity: str = "info"
    message: str
    detail: dict = Field(default_factory=dict)

    @field_validator("severity")
    @classmethod
    def _known_severity(cls, v: str) -> str:
        if v not in _PROXY_SEVERITIES:
            raise ValueError(f"severity must be one of {_PROXY_SEVERITIES}")
        return v


class ProxyRisk(BaseModel):
    band: ProxyBand = ProxyBand.LOW
    findings: list[ProxyFinding] = Field(default_factory=list)
    #: The S7.1 hook, as stamped when the session STARTED.
    assurance_level_at_start: int = 0
    advisory: bool = True


class InterviewAssessment(BaseModel):
    session_id: str
    candidate_id: str
    band: InterviewBand = InterviewBand.INSUFFICIENT_SIGNAL
    overall: float = Field(default=0.0, ge=0.0, le=1.0)
    dimensions: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    questions_planned: int = 0
    questions_answered: int = 0
    proxy: ProxyRisk = Field(default_factory=ProxyRisk)
    scorer_version: str = ""
    advisory: bool = True
    human_review_required: bool = True


class InterviewSession(BaseModel):
    """The candidate's own view: questions, turns (with transcripts), outcome."""

    id: str
    candidate_id: str
    domain: str = "genai"
    report_id: Optional[str] = None
    status: InterviewStatus = InterviewStatus.IN_PROGRESS
    assurance_level_at_start: int = 0
    questions: list[InterviewQuestion] = Field(default_factory=list)
    turns: list[InterviewTurn] = Field(default_factory=list)
    assessment: Optional[InterviewAssessment] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class InterviewSummary(BaseModel):
    """Header projection. Used by the candidate's list view AND the org read --
    which is why it has no transcript and no turns: an org must not be one
    forgotten filter away from the candidate's words."""

    id: str
    status: InterviewStatus
    domain: str = "genai"
    band: InterviewBand = InterviewBand.INSUFFICIENT_SIGNAL
    overall: float = 0.0
    dimensions: dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0
    proxy_band: ProxyBand = ProxyBand.LOW
    questions_planned: int = 0
    questions_answered: int = 0
    started_at: datetime
    completed_at: Optional[datetime] = None
    advisory: bool = True
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_interview_schema.py -q`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add app/interview tests/test_interview_schema.py
git commit -m "feat(s73): interview contracts -- own band type, transcript-free summary"
```

---

### Task 2: Config, consent purpose, scoring tier

**Files:**
- Modify: `app/core/config.py`, `config.yaml`, `app/ledger/schema.py`, `app/services/llm.py`
- Test: `tests/test_config_interview.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `Settings.interview_*` (see the knob table), `Settings.ret_interview_session_days`,
  `Settings.speech_timeout_seconds`, `Settings.speech_max_retries`,
  `Settings.model_for_tier("scoring")`, `ConsentPurpose.INTERVIEW_READ`, and
  `Tier = Literal[..., "scoring"]`. Tasks 4–13 read these.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_interview.py`:

```python
"""S7.3 knobs + the one new consent purpose. Band cut-points are knobs (the
ai_*/fr_*/rep_* precedent); scorer internals are NOT (they define what the
number means and are versioned by SCORER_VERSION instead)."""

import pytest

from app.core.config import Settings
from app.ledger.schema import ConsentPurpose


@pytest.fixture
def s(monkeypatch) -> Settings:
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


def test_question_plan_knobs(s):
    assert s.interview_max_questions == 8
    assert s.interview_min_questions == 3
    assert s.interview_session_ttl_minutes == 120


def test_input_caps(s):
    assert s.interview_max_audio_b64_chars == 8_000_000
    assert s.interview_max_answer_chars == 20_000
    assert s.interview_min_answer_words == 12


def test_proxy_rate_knobs_are_generous(s):
    # Human speech is ~2.5 words/sec; 4.0 leaves room for fast speakers.
    assert s.interview_max_words_per_second == 4.0
    assert s.interview_max_typed_words_per_second == 8.0


def test_llm_pass_is_capped(s):
    assert s.interview_llm_max_delta == 0.2
    assert s.interview_llm_excerpt_chars == 4000


def test_band_thresholds_and_weights(s):
    assert s.interview_min_confidence == 0.5
    assert s.interview_deep_threshold == 0.75
    assert s.interview_solid_threshold == 0.55
    assert s.interview_emerging_threshold == 0.35
    assert s.interview_weight_depth == 1.5      # dominant axis
    assert s.interview_weight_specificity == 1.0
    assert s.interview_weight_ownership == 1.0
    assert s.interview_weight_consistency == 1.0


def test_retention_and_speech_knobs(s):
    assert s.ret_interview_session_days == 1095
    assert s.speech_timeout_seconds == 60
    assert s.speech_max_retries == 2


def test_scoring_tier_resolves_to_model_scoring(s):
    assert s.model_for_tier("scoring") == s.model_scoring


def test_interview_read_is_a_new_consent_purpose(s):
    assert ConsentPurpose.INTERVIEW_READ.value == "interview_read"
    # VERIFICATION_READ's redefinition window is closed (ROADMAP watch item):
    # interview disclosure gets its own purpose, not another widening.
    assert ConsentPurpose.INTERVIEW_READ is not ConsentPurpose.VERIFICATION_READ


def test_knob_floors_reject_nonsense(s):
    with pytest.raises(ValueError):
        Settings(_env_file=None, openrouter_api_key="", interview_min_questions=0)
    with pytest.raises(ValueError):
        Settings(_env_file=None, openrouter_api_key="", interview_llm_max_delta=1.5)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_config_interview.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'interview_max_questions'`

- [ ] **Step 3: Implement**

In `app/core/config.py`, after the S7.2 document-forensics block, add:

```python
    # --- AI interviews (PI-7) - S7.3 delivery + advisory scoring --------------
    # Band cut-points are knobs; the scorer's own internals are module constants
    # in scoring.py, versioned by SCORER_VERSION -- a deploy that silently
    # redefined "specific" would make two stored assessments incomparable.
    interview_max_questions: int = Field(default=8, ge=1)
    interview_min_questions: int = Field(default=3, ge=1)
    interview_session_ttl_minutes: int = Field(default=120, ge=1)
    interview_max_audio_b64_chars: int = Field(default=8_000_000, ge=1024)
    interview_max_answer_chars: int = Field(default=20_000, ge=64)
    interview_min_answer_words: int = Field(default=12, ge=1)
    interview_max_words_per_second: float = Field(default=4.0, gt=0.0)
    interview_max_typed_words_per_second: float = Field(default=8.0, gt=0.0)
    interview_llm_max_delta: float = Field(default=0.2, ge=0.0, le=0.5)
    interview_llm_excerpt_chars: int = Field(default=4000, ge=100)
    interview_min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    interview_deep_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    interview_solid_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    interview_emerging_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    interview_weight_specificity: float = Field(default=1.0, ge=0.0)
    interview_weight_ownership: float = Field(default=1.0, ge=0.0)
    interview_weight_depth: float = Field(default=1.5, ge=0.0)
    interview_weight_consistency: float = Field(default=1.0, ge=0.0)
    ret_interview_session_days: int = Field(default=1095, ge=1)   # 3y, posture only
    speech_timeout_seconds: int = Field(default=60, ge=1)
    speech_max_retries: int = Field(default=2, ge=0)
```

Extend `model_for_tier` (both the `Literal` in its signature and the dict):

```python
    def model_for_tier(
        self,
        tier: Literal["reasoning", "reasoning_hard", "parsing", "bulk", "scoring"],
    ) -> str:
        """Resolve a logical tier to a concrete, config-driven model id."""
        return {
            "reasoning": self.model_reasoning,
            "reasoning_hard": self.model_reasoning_hard,
            "parsing": self.model_fast,
            "bulk": self.model_bulk,
            # S7.3: interview scoring. Advisory + human-reviewed + capped, so
            # the value tier is right.
            "scoring": self.model_scoring,
        }[tier]
```

In `app/services/llm.py`, widen the tier alias:

```python
Tier = Literal["reasoning", "reasoning_hard", "parsing", "bulk", "scoring"]
```

In `app/ledger/schema.py`, add the member and extend the docstring:

```python
class ConsentPurpose(StrEnum):
    """What a grant authorizes. ledger_write = an org may submit interview
    records about the candidate; ledger_read = an org may query the
    candidate's ledger history (enforced at query time in S3.2);
    identity_verify = the platform may verify the candidate's identity via an
    EXTERNAL source (S7.1 -- first-party self-service methods need no grant);
    verification_read = an org may see the candidate's identity assurance;
    interview_read = an org may see the candidate's AI-interview assessments
    (S7.3 -- a NEW purpose rather than another widening of verification_read,
    whose dated redefinition window is closed)."""

    LEDGER_WRITE = "ledger_write"
    LEDGER_READ = "ledger_read"
    IDENTITY_VERIFY = "identity_verify"
    VERIFICATION_READ = "verification_read"
    INTERVIEW_READ = "interview_read"
```

In `config.yaml`, after the S7.2 block:

```yaml
# --- AI interviews (PI-7) - S7.3 delivery + advisory scoring -------------------
# The interview asks the depth report's OWN probes. Scoring is deterministic;
# the LLM may only ADJUST a dimension by interview_llm_max_delta and can never
# alone produce a band. No key => audio is refused and it runs as a text
# interview. Advisory: an interview never gates matching, ranking, or scoring.
interview_max_questions: 8
interview_min_questions: 3          # below this there is nothing worth asking -> 422
interview_session_ttl_minutes: 120  # read-time expiry; no sweeper exists (PI-8)
interview_max_audio_b64_chars: 8000000   # ~6MB decoded; refused before any decode
interview_max_answer_chars: 20000
interview_min_answer_words: 12      # shorter -> scores nothing (not zero)
interview_max_words_per_second: 4.0      # audio; human speech is ~2.5
interview_max_typed_words_per_second: 8.0
interview_llm_max_delta: 0.2        # hard cap on the LLM's influence per dimension
interview_llm_excerpt_chars: 4000
interview_min_confidence: 0.5       # below this -> insufficient_signal, never assert
interview_deep_threshold: 0.75
interview_solid_threshold: 0.55
interview_emerging_threshold: 0.35
interview_weight_specificity: 1.0
interview_weight_ownership: 1.0
interview_weight_depth: 1.5         # dominant: did they cover what a real answer must
interview_weight_consistency: 1.0
ret_interview_session_days: 1095    # 3y, posture only (sweep is PI-8)
speech_timeout_seconds: 60
speech_max_retries: 2
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_config_interview.py tests/test_config.py tests/test_ledger_consent.py -q`
Expected: PASS. If a ledger test asserts the exact `ConsentPurpose` membership set, update
it to include `interview_read` — that is a deliberate taxonomy addition, not a break.

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py config.yaml app/ledger/schema.py app/services/llm.py tests/test_config_interview.py
git commit -m "feat(s73): interview knobs, INTERVIEW_READ purpose, scoring tier"
```

---

### Task 3: Question planning (`app/interview/questions.py`) + the domain seam

**Files:**
- Create: `app/interview/questions.py`
- Modify: `app/domains/base.py`, `app/domains/genai.py`
- Test: `tests/test_interview_questions.py`

**Interfaces:**
- Consumes: `InterviewQuestion`, `QuestionSource` (Task 1).
- Produces: `build_question_plan(*, profile, report, domain, limit, minimum) -> list[InterviewQuestion]`,
  `NothingToAskError`, `DEPTH_MARKERS`, `MAX_PROBES_PER_VERDICT`,
  `DomainModel.interview_seed_questions() -> list[str]`. Task 10 calls
  `build_question_plan`; Task 12 maps `NothingToAskError` to 422.

- [ ] **Step 1: Write the failing test**

Create `tests/test_interview_questions.py`:

```python
"""Question planning: probes first, then profile templates, then domain seeds.
Pure and deterministic -- ordering is asserted because a reviewer reading a
session must be able to tell WHY each question was asked."""

import pytest

from app.candidates.schema import CandidateProfile, ExperienceEntry, SkillItem
from app.domains.base import get_domain
from app.interview.questions import NothingToAskError, build_question_plan
from app.interview.schema import QuestionSource
from app.schemas.report import CoherenceVerdict, Report, VerdictStatus


def _profile() -> CandidateProfile:
    return CandidateProfile(
        experience=[ExperienceEntry(employer="Acme Technologies Pvt Ltd",
                                    employer_canonical="Acme Technologies",
                                    title="ML Engineer")],
        skills=[SkillItem(name="PyTorch", canonical="pytorch")],
    )


def _report(**kw) -> Report:
    verdicts = [
        CoherenceVerdict(claim_id="cl_flagged", claim_text="fine-tuned a 70B",
                         claim_type="fine_tuning", status=VerdictStatus.INCOHERENT,
                         missing_signals=["gpu hours", "dataset size"],
                         probes=["Which GPUs, and for how many hours?",
                                 "How large was the dataset?"]),
        CoherenceVerdict(claim_id="cl_plain", claim_text="built a RAG app",
                         claim_type="rag", status=VerdictStatus.COHERENT,
                         probes=["Which vector store?"]),
        CoherenceVerdict(claim_id="cl_deferred", claim_text="ran evals",
                         claim_type="evaluation", status=VerdictStatus.DEFER,
                         missing_signals=["metric"], probes=["Which metric moved?"]),
    ]
    return Report(verdicts=verdicts, flagged_claim_ids=["cl_flagged"],
                  deferred_claim_ids=["cl_deferred"], **kw)


def test_probes_come_first_and_flagged_before_deferred_before_the_rest():
    plan = build_question_plan(profile=_profile(), report=_report(),
                               domain=None, limit=8, minimum=1)
    probe_texts = [q.text for q in plan if q.source is QuestionSource.PROBE]
    assert probe_texts[0].startswith("Which GPUs")
    assert probe_texts.index("Which metric moved?") < probe_texts.index("Which vector store?")
    assert plan[0].source is QuestionSource.PROBE


def test_a_probe_carries_its_verdicts_missing_signals_as_expected_signals():
    plan = build_question_plan(profile=_profile(), report=_report(),
                               domain=None, limit=8, minimum=1)
    first = plan[0]
    assert first.claim_id == "cl_flagged"
    assert first.expected_signals == ["gpu hours", "dataset size"]


def test_at_most_two_probes_per_verdict():
    verdict = CoherenceVerdict(claim_id="c", claim_text="t", claim_type="rag",
                               probes=["p1", "p2", "p3", "p4"])
    report = Report(verdicts=[verdict])
    plan = build_question_plan(profile=None, report=report, domain=None,
                               limit=8, minimum=1)
    assert [q.text for q in plan] == ["p1", "p2"]


def test_profile_templates_fill_in_and_name_the_employer_and_skill():
    plan = build_question_plan(profile=_profile(), report=None,
                               domain=None, limit=8, minimum=1)
    assert all(q.source is QuestionSource.PROFILE for q in plan)
    assert "Acme Technologies" in plan[0].text
    assert "ML Engineer" in plan[0].text
    assert "Acme Technologies" in plan[0].expected_signals
    assert any("pytorch" in q.text for q in plan)


def test_domain_seeds_come_last_and_come_from_the_registry():
    plan = build_question_plan(profile=_profile(), report=None,
                               domain=get_domain("genai"), limit=8, minimum=1)
    assert plan[-1].source is QuestionSource.DOMAIN


def test_duplicate_question_text_is_deduped_case_and_space_insensitively():
    verdicts = [CoherenceVerdict(claim_id="a", claim_text="t", claim_type="rag",
                                 probes=["Which vector store?"]),
                CoherenceVerdict(claim_id="b", claim_text="t", claim_type="rag",
                                 probes=["which   VECTOR store?"])]
    plan = build_question_plan(profile=None, report=Report(verdicts=verdicts),
                               domain=None, limit=8, minimum=1)
    assert len(plan) == 1


def test_plan_is_capped_and_sequences_are_1_based_and_contiguous():
    plan = build_question_plan(profile=_profile(), report=_report(),
                               domain=get_domain("genai"), limit=3, minimum=1)
    assert len(plan) == 3
    assert [q.sequence for q in plan] == [1, 2, 3]


def test_too_little_on_file_refuses_rather_than_building_an_empty_interview():
    with pytest.raises(NothingToAskError):
        build_question_plan(profile=CandidateProfile(), report=None,
                            domain=None, limit=8, minimum=3)


def test_every_registered_domain_answers_the_seed_question_seam():
    from app.domains.base import list_domains
    for key in list_domains():
        seeds = get_domain(key).interview_seed_questions()
        assert isinstance(seeds, list)
        assert all(isinstance(s, str) and s.strip() for s in seeds)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_interview_questions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.interview.questions'`

- [ ] **Step 3: Implement**

Create `app/interview/questions.py`:

```python
"""Deterministic interview question planning (S7.3). Pure: no I/O, no clock.

The primary source is the depth report's OWN probes -- the questions
`probe_generation` already wrote for claims the pipeline could not settle. That
is what makes this an interview about THIS candidate rather than a generic
question bank. A profile-templated bank fills the rest so a candidate with no
report is still interviewable, and a domain may contribute seed openers through
the DomainModel seam (the core never imports a concrete domain).

Ordering is deliberate and asserted by tests: a reviewer reading a session must
be able to see why each question was asked.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

from app.candidates.schema import CandidateProfile
from app.interview.schema import InterviewQuestion, QuestionSource
from app.schemas.report import Report

_WS = re.compile(r"\s+")

#: Markers a substantive engineering answer tends to contain. Used as the
#: expected_signals of template questions, which have no verdict behind them.
DEPTH_MARKERS: tuple[str, ...] = (
    "fail", "debug", "trade-off", "latency", "cost", "rollback",
)

#: More than two probes from one claim turns the interview into an
#: interrogation about a single line of the resume.
MAX_PROBES_PER_VERDICT = 2

EXPERIENCE_TEMPLATE = (
    "At {employer} you worked as {title}. Describe one specific problem you "
    "solved there: what broke, how you found the cause, and what you changed."
)
SKILL_TEMPLATE = (
    "You list {skill}. Walk through the hardest thing you have done with it: "
    "what you tried first, why it failed, and what you did instead."
)


class NothingToAskError(Exception):
    """Too little is on file to build a meaningful interview. Refusing beats
    conducting an empty one and scoring the silence."""


def _norm(text: str) -> str:
    return _WS.sub(" ", text or "").strip().casefold()


def _probe_items(report: Optional[Report]) -> list[tuple[str, list[str], Optional[str]]]:
    if report is None:
        return []
    flagged = set(report.flagged_claim_ids)
    deferred = set(report.deferred_claim_ids)

    def rank(verdict) -> int:
        if verdict.claim_id in flagged:
            return 0
        if verdict.claim_id in deferred:
            return 1
        return 2

    items: list[tuple[str, list[str], Optional[str]]] = []
    # sorted() is stable, so within a rank group the report's own order holds.
    for verdict in sorted(report.verdicts, key=rank):
        for probe in verdict.probes[:MAX_PROBES_PER_VERDICT]:
            if probe and probe.strip():
                items.append(
                    (probe.strip(), list(verdict.missing_signals), verdict.claim_id)
                )
    return items


def _profile_items(
    profile: Optional[CandidateProfile],
) -> list[tuple[str, list[str], Optional[str]]]:
    if profile is None:
        return []
    items: list[tuple[str, list[str], Optional[str]]] = []
    for exp in profile.experience:
        employer = exp.employer_canonical or exp.employer
        if not employer:
            continue
        title = exp.title or "an engineer"
        items.append((
            EXPERIENCE_TEMPLATE.format(employer=employer, title=title),
            [employer, *DEPTH_MARKERS],
            None,
        ))
    for skill in profile.skills:
        name = skill.canonical or skill.name
        if not name:
            continue
        items.append((
            SKILL_TEMPLATE.format(skill=name), [name, *DEPTH_MARKERS], None,
        ))
    return items


def build_question_plan(
    *,
    profile: Optional[CandidateProfile],
    report: Optional[Report],
    domain,
    limit: int,
    minimum: int,
) -> list[InterviewQuestion]:
    """Ordered, deduped, capped plan. Raises NothingToAskError below `minimum`.

    `domain` is a DomainModel or None -- typed loosely on purpose so this module
    never imports the domain package's concrete classes.
    """
    seeds = list(domain.interview_seed_questions()) if domain is not None else []
    sourced: list[tuple[str, list[str], Optional[str], QuestionSource]] = [
        *[(t, s, c, QuestionSource.PROBE) for t, s, c in _probe_items(report)],
        *[(t, s, c, QuestionSource.PROFILE) for t, s, c in _profile_items(profile)],
        *[(t, [], None, QuestionSource.DOMAIN) for t in seeds],
    ]

    seen: set[str] = set()
    plan: list[InterviewQuestion] = []
    for text, signals, claim_id, source in sourced:
        key = _norm(text)
        if not key or key in seen:
            continue
        seen.add(key)
        plan.append(
            InterviewQuestion(
                id=f"q_{uuid.uuid4().hex[:10]}",
                sequence=len(plan) + 1,
                text=text,
                source=source,
                expected_signals=[s for s in dict.fromkeys(signals) if s],
                claim_id=claim_id,
            )
        )
        if len(plan) >= limit:
            break

    if len(plan) < minimum:
        raise NothingToAskError(
            f"only {len(plan)} question(s) available; {minimum} required. "
            "Add a resume or run a depth evaluation first."
        )
    return plan
```

In `app/domains/base.py`, add to `DomainModel` (after `probe_guidance`), as a
**non-abstract** method so existing domains keep working:

```python
    # --- interview seeds (S7.3) ----------------------------------------------
    def interview_seed_questions(self) -> list[str]:
        """Opening questions for an AI interview in this domain. Optional: the
        planner prefers the depth report's own probes and the candidate's
        profile, so a domain that returns nothing costs nothing."""
        return []
```

In `app/domains/genai.py`, override it on the domain class:

```python
    def interview_seed_questions(self) -> list[str]:
        return [
            "Describe the GenAI system you are proudest of: what it does, who "
            "uses it, and what you personally built.",
            "Tell me about a time a model behaved worse in production than in "
            "evaluation. How did you find out, and what did you change?",
        ]
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_interview_questions.py tests/test_data_eng.py -q`
Expected: PASS (9 new). `data_eng` is included because it must inherit the default seam.

- [ ] **Step 5: Commit**

```bash
git add app/interview/questions.py app/domains tests/test_interview_questions.py
git commit -m "feat(s73): question plan -- the depth report's own probes, asked first"
```

---

### Task 4: Deterministic scoring (`app/interview/scoring.py`)

**Files:**
- Create: `app/interview/scoring.py`
- Test: `tests/test_interview_scoring.py`

**Interfaces:**
- Consumes: `DIMENSIONS`, `TurnScore`, `InterviewTurn`, `InterviewAssessment`,
  `InterviewBand`, `ProxyRisk`, `InterviewQuestion` (Task 1); `Settings` (Task 2).
- Produces: `SCORER_VERSION`, `SPECIFICITY_TARGET`, `SUBSTANCE_TARGET_WORDS`,
  `word_count(text) -> int`, `score_turn(*, transcript, expected_signals, profile, settings) -> TurnScore`,
  `band_for(overall, confidence, settings) -> InterviewBand`,
  `aggregate(*, session_id, candidate_id, questions, turns, proxy, settings) -> InterviewAssessment`.
  Task 5 adds `adjust_with_llm` to this module; Task 10 calls `score_turn` + `aggregate`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_interview_scoring.py`:

```python
"""Deterministic rubric. Every dimension is neutral-when-unknown: a scorer that
confuses "no yardstick" with "shallow answer" punishes candidates for the
question bank's gaps."""

from datetime import datetime, timezone

import pytest

from app.candidates.schema import CandidateProfile, ExperienceEntry, SkillItem
from app.core.config import Settings
from app.interview.schema import (
    AnswerChannel, InterviewBand, InterviewQuestion, InterviewTurn, ProxyRisk, TurnScore,
)
from app.interview.scoring import (
    SCORER_VERSION, aggregate, band_for, score_turn, word_count,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def s(monkeypatch) -> Settings:
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        experience=[ExperienceEntry(employer="Acme", employer_canonical="Acme")],
        skills=[SkillItem(name="PyTorch", canonical="pytorch")],
    )


def _turn(seq: int, score: TurnScore, words: int = 60) -> InterviewTurn:
    return InterviewTurn(
        id=f"t{seq}", sequence=seq, question_id=f"q{seq}", question_text="q",
        question_source="probe", channel=AnswerChannel.TEXT, transcript="x " * words,
        word_count=words, asked_at=NOW, answered_at=NOW, score=score,
    )


def test_word_count_ignores_pure_punctuation_and_counts_hyphenates_once():
    assert word_count("we shipped a low-latency service -- twice") == 6


def test_an_answer_below_the_floor_scores_nothing_rather_than_zero(s, profile):
    score = score_turn(transcript="we did it", expected_signals=["gpu"],
                       profile=profile, settings=s)
    assert score.insufficient is True
    assert score.dimensions == {}
    assert score.codes == ["insufficient_answer"]


def test_specificity_rewards_numbers_and_named_tools(s, profile):
    vague = ("I worked on the model and made it better for the users over "
             "several months with the team and it went well overall")
    concrete = ("I fine-tuned PyTorch on 8 A100 GPUs for 14 hours, cut p99 "
                "latency from 900 ms to 220 ms and dropped cost by 40 percent")
    assert (score_turn(transcript=concrete, expected_signals=[], profile=profile,
                       settings=s).dimensions["specificity"]
            > score_turn(transcript=vague, expected_signals=[], profile=profile,
                         settings=s).dimensions["specificity"])


def test_ownership_prefers_i_over_we_and_is_neutral_when_neither_appears(s, profile):
    mine = ("I traced the regression to a tokenizer change, I rewrote the "
            "batching path and I shipped the fix behind a flag that week")
    ours = ("we traced the regression to a tokenizer change, we rewrote the "
            "batching path and our team shipped the fix behind a flag")
    neither = ("the regression came from a tokenizer change; the batching path "
               "was rewritten and the fix shipped behind a flag that week")
    assert score_turn(transcript=mine, expected_signals=[], profile=profile,
                      settings=s).dimensions["ownership"] == 1.0
    assert score_turn(transcript=ours, expected_signals=[], profile=profile,
                      settings=s).dimensions["ownership"] == 0.0
    assert score_turn(transcript=neither, expected_signals=[], profile=profile,
                      settings=s).dimensions["ownership"] == 0.5


def test_depth_is_the_share_of_expected_signals_actually_covered(s, profile):
    answer = ("I ran it on 8 GPUs for 14 hours over a dataset of 120k rows and "
              "logged every checkpoint so we could compare them properly")
    score = score_turn(transcript=answer, expected_signals=["gpu", "dataset", "eval harness"],
                       profile=profile, settings=s)
    assert score.dimensions["depth"] == pytest.approx(2 / 3)


def test_depth_is_neutral_when_the_question_has_no_yardstick(s, profile):
    answer = "I built the thing and then I rebuilt it after it fell over twice in production"
    score = score_turn(transcript=answer, expected_signals=[], profile=profile, settings=s)
    assert score.dimensions["depth"] == 0.5


def test_consistency_corroborates_but_never_punishes(s, profile):
    known = ("At Acme I moved the PyTorch training job onto spot instances and "
             "handled the preemption restarts myself over that quarter")
    unknown = ("At a client I cannot name I moved the training job onto spot "
               "instances and handled the preemption restarts myself")
    assert score_turn(transcript=known, expected_signals=[], profile=profile,
                      settings=s).dimensions["consistency"] == 1.0
    # v0 can corroborate, not contradict: an unrecognised employer stays neutral.
    assert score_turn(transcript=unknown, expected_signals=[], profile=profile,
                      settings=s).dimensions["consistency"] == 0.5


def test_band_needs_confidence_before_it_will_assert_anything(s):
    assert band_for(0.95, 0.10, s) is InterviewBand.INSUFFICIENT_SIGNAL
    assert band_for(0.80, 0.90, s) is InterviewBand.DEEP
    assert band_for(0.60, 0.90, s) is InterviewBand.SOLID
    assert band_for(0.40, 0.90, s) is InterviewBand.EMERGING
    assert band_for(0.10, 0.90, s) is InterviewBand.SUPERFICIAL


def test_aggregate_means_each_dimension_and_weights_depth_hardest(s):
    turns = [
        _turn(1, TurnScore(dimensions={"specificity": 1.0, "ownership": 1.0,
                                       "depth": 0.0, "consistency": 1.0})),
        _turn(2, TurnScore(dimensions={"specificity": 1.0, "ownership": 1.0,
                                       "depth": 0.0, "consistency": 1.0})),
    ]
    questions = [InterviewQuestion(id=f"q{i}", sequence=i, text="q", source="probe")
                 for i in (1, 2)]
    a = aggregate(session_id="s1", candidate_id="c1", questions=questions, turns=turns,
                  proxy=ProxyRisk(), settings=s)
    assert a.dimensions["depth"] == 0.0
    # depth weighs 1.5 of 4.5 total, so a zero there pulls overall to 3/4.5.
    assert a.overall == pytest.approx(2 / 3, abs=1e-3)
    assert a.scorer_version == SCORER_VERSION


def test_insufficient_turns_count_against_coverage_but_not_the_means(s):
    turns = [
        _turn(1, TurnScore(dimensions={"depth": 1.0})),
        _turn(2, TurnScore(insufficient=True, codes=["insufficient_answer"]), words=3),
    ]
    questions = [InterviewQuestion(id=f"q{i}", sequence=i, text="q", source="probe")
                 for i in (1, 2, 3, 4)]
    a = aggregate(session_id="s1", candidate_id="c1", questions=questions, turns=turns,
                  proxy=ProxyRisk(), settings=s)
    assert a.dimensions["depth"] == 1.0        # the empty turn did not drag it to 0.5
    assert a.coverage == 0.5                    # 2 answered of 4 planned
    assert a.questions_answered == 2 and a.questions_planned == 4
    assert a.confidence < 0.5                   # low coverage + one thin answer
    assert a.band is InterviewBand.INSUFFICIENT_SIGNAL


def test_an_unanswered_session_asserts_nothing(s):
    questions = [InterviewQuestion(id="q1", sequence=1, text="q", source="probe")]
    a = aggregate(session_id="s1", candidate_id="c1", questions=questions, turns=[],
                  proxy=ProxyRisk(), settings=s)
    assert a.confidence == 0.0 and a.overall == 0.0
    assert a.band is InterviewBand.INSUFFICIENT_SIGNAL
    assert a.advisory is True and a.human_review_required is True
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_interview_scoring.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.interview.scoring'`

- [ ] **Step 3: Implement**

Create `app/interview/scoring.py`:

```python
"""Deterministic interview scoring (S7.3). Pure: no I/O, no clock.

Four axes, each NEUTRAL WHEN UNKNOWN (0.5) rather than zero. That rule is the
whole ethic of this module: a scorer that treats "we have no yardstick" as
"the answer was shallow" punishes candidates for gaps in the question bank.

The targets below are module constants, not config knobs. They define what the
number MEANS; a deploy-time switch would make two stored assessments
incomparable. When they change, SCORER_VERSION changes with them, and every
stored assessment records which version produced it.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

from app.candidates.normalize.skills import normalize_skill
from app.candidates.schema import CandidateProfile
from app.core.config import Settings
from app.interview.schema import (
    DIMENSIONS, InterviewAssessment, InterviewBand, InterviewQuestion, InterviewTurn,
    ProxyRisk, TurnScore,
)

#: Bump on ANY change to the maths below. Stamped on every stored assessment.
SCORER_VERSION = "s73.1"

#: Concrete tokens (numerals + recognised tools) for a full specificity score.
SPECIFICITY_TARGET = 6
#: Words at which an answer counts as fully substantive for confidence.
SUBSTANCE_TARGET_WORDS = 60

_TOKEN = re.compile(r"[A-Za-z0-9+#./\-]+")
_FIRST_SINGULAR = frozenset({"i", "my", "me", "mine", "i'd", "i'll", "i've", "i'm"})
_FIRST_PLURAL = frozenset({"we", "our", "us", "ours", "we'd", "we'll", "we've", "we're"})


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text or "")


def _words(text: str) -> list[str]:
    return [t for t in _tokens(text) if any(c.isalpha() for c in t)]


def word_count(text: str) -> int:
    return len(_words(text))


def _specificity(tokens: Sequence[str]) -> float:
    concrete = 0
    for token in tokens:
        if any(c.isdigit() for c in token):
            concrete += 1
        elif normalize_skill(token) is not None:
            concrete += 1
    return round(min(1.0, concrete / SPECIFICITY_TARGET), 4)


def _ownership(words: Sequence[str]) -> float:
    lowered = [w.casefold() for w in words]
    mine = sum(1 for w in lowered if w in _FIRST_SINGULAR)
    ours = sum(1 for w in lowered if w in _FIRST_PLURAL)
    if mine + ours == 0:
        return 0.5   # neither claimed nor disclaimed: unknown, not bad
    return round(mine / (mine + ours), 4)


def _depth(text_cf: str, expected_signals: Sequence[str]) -> float:
    signals = [s for s in expected_signals if s and s.strip()]
    if not signals:
        return 0.5   # no yardstick for this question
    matched = sum(1 for s in signals if s.strip().casefold() in text_cf)
    return round(matched / len(signals), 4)


def _profile_terms(profile: Optional[CandidateProfile]) -> list[str]:
    if profile is None:
        return []
    terms: list[str] = []
    for exp in profile.experience:
        for value in (exp.employer_canonical, exp.employer):
            if value:
                terms.append(value.casefold())
    for skill in profile.skills:
        for value in (skill.canonical, skill.name):
            if value:
                terms.append(value.casefold())
    return list(dict.fromkeys(terms))


def _consistency(text_cf: str, profile: Optional[CandidateProfile]) -> float:
    """v0 CORROBORATES, it does not contradict. Naming something on the profile
    lifts this to 1.0; naming something we never taxonomised leaves it neutral.
    A candidate must never lose points for a client they cannot name."""
    for term in _profile_terms(profile):
        if term and term in text_cf:
            return 1.0
    return 0.5


def score_turn(
    *,
    transcript: str,
    expected_signals: Sequence[str],
    profile: Optional[CandidateProfile],
    settings: Settings,
) -> TurnScore:
    """Score ONE answer. An answer below the word floor scores NOTHING (an empty
    `dimensions`), which is different from scoring zero: silence is missing
    evidence, not evidence of shallowness."""
    words = _words(transcript)
    if len(words) < settings.interview_min_answer_words:
        return TurnScore(dimensions={}, insufficient=True, codes=["insufficient_answer"])

    text_cf = (transcript or "").casefold()
    return TurnScore(
        dimensions={
            "specificity": _specificity(_tokens(transcript)),
            "ownership": _ownership(words),
            "depth": _depth(text_cf, expected_signals),
            "consistency": _consistency(text_cf, profile),
        },
        insufficient=False,
        codes=[],
    )


def band_for(overall: float, confidence: float, settings: Settings) -> InterviewBand:
    """Conservative banding: confidence gates everything, exactly like the
    ai_*/fr_*/rep_* families. Below the floor we say nothing."""
    if confidence < settings.interview_min_confidence:
        return InterviewBand.INSUFFICIENT_SIGNAL
    if overall >= settings.interview_deep_threshold:
        return InterviewBand.DEEP
    if overall >= settings.interview_solid_threshold:
        return InterviewBand.SOLID
    if overall >= settings.interview_emerging_threshold:
        return InterviewBand.EMERGING
    return InterviewBand.SUPERFICIAL


def aggregate(
    *,
    session_id: str,
    candidate_id: str,
    questions: Sequence[InterviewQuestion],
    turns: Sequence[InterviewTurn],
    proxy: ProxyRisk,
    settings: Settings,
) -> InterviewAssessment:
    """Fold scored turns into one advisory assessment.

    Confidence = coverage x substance. Both matter: three thorough answers out
    of eight planned questions is not the same evidence as eight thorough ones,
    and eight one-liners are not either.
    """
    planned = len(questions)
    answered = len(turns)
    coverage = round(answered / planned, 4) if planned else 0.0

    dimensions: dict[str, float] = {}
    for dim in DIMENSIONS:
        values = [t.score.dimensions[dim] for t in turns if dim in t.score.dimensions]
        if values:
            dimensions[dim] = round(sum(values) / len(values), 4)

    weights = {
        dim: getattr(settings, f"interview_weight_{dim}") for dim in dimensions
    }
    total_weight = sum(weights.values())
    overall = (
        round(sum(dimensions[d] * weights[d] for d in dimensions) / total_weight, 4)
        if total_weight
        else 0.0
    )

    substance = (
        sum(min(1.0, t.word_count / SUBSTANCE_TARGET_WORDS) for t in turns) / answered
        if answered
        else 0.0
    )
    confidence = round(min(0.95, coverage * substance), 4)

    return InterviewAssessment(
        session_id=session_id,
        candidate_id=candidate_id,
        band=band_for(overall, confidence, settings),
        overall=overall,
        dimensions=dimensions,
        confidence=confidence,
        coverage=coverage,
        questions_planned=planned,
        questions_answered=answered,
        proxy=proxy,
        scorer_version=SCORER_VERSION,
    )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_interview_scoring.py -q`
Expected: PASS (12 passed). If `test_specificity_rewards_numbers_and_named_tools` fails,
check `normalize_skill` is being called per token (it takes a single term, not a sentence).

- [ ] **Step 5: Commit**

```bash
git add app/interview/scoring.py tests/test_interview_scoring.py
git commit -m "feat(s73): deterministic rubric -- neutral when unknown, never zero"
```

---

### Task 5: The capped LLM adjustment

**Files:**
- Modify: `app/interview/scoring.py`
- Test: `tests/test_interview_scoring_llm.py`

**Interfaces:**
- Consumes: `TurnScore` (Task 1), `Settings.interview_llm_*` (Task 2), `LLMClient`.
- Produces: `async adjust_with_llm(llm, *, question_text, transcript, expected_signals, base, settings) -> TurnScore`.
  Task 10 awaits it after `score_turn`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_interview_scoring_llm.py`:

```python
"""The LLM may ADJUST a dimension, never decide one. Same stance as S2.1: the
deterministic pass is the score, the model is a nudge with a hard cap."""

import pytest

from app.core.config import Settings
from app.interview.schema import TurnScore
from app.interview.scoring import adjust_with_llm
from app.services.llm import LLMClient, NullLLM
from tests.conftest import FakeLLM


@pytest.fixture
def s(monkeypatch) -> Settings:
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


BASE = TurnScore(dimensions={"specificity": 0.5, "ownership": 0.5,
                             "depth": 0.5, "consistency": 0.5})


async def _adjust(llm: LLMClient, s: Settings, base: TurnScore = BASE) -> TurnScore:
    return await adjust_with_llm(
        llm, question_text="Which GPUs?", transcript="I used 8 A100s for 14 hours",
        expected_signals=["gpu"], base=base, settings=s,
    )


@pytest.mark.asyncio
async def test_no_key_leaves_the_deterministic_score_untouched(s):
    out = await _adjust(NullLLM(s), s)
    assert out.dimensions == BASE.dimensions
    assert "llm_adjusted" not in out.codes


@pytest.mark.asyncio
async def test_an_adjustment_is_clamped_to_the_max_delta(s):
    llm = FakeLLM({"Which GPUs?": '{"dimensions": {"depth": 1.0}}'}, settings=s)
    out = await _adjust(llm, s)
    assert out.dimensions["depth"] == pytest.approx(0.7)   # 0.5 + 0.2 cap
    assert "llm_adjusted" in out.codes


@pytest.mark.asyncio
async def test_a_downward_adjustment_is_clamped_the_same_way(s):
    llm = FakeLLM({"Which GPUs?": '{"dimensions": {"depth": 0.0}}'}, settings=s)
    out = await _adjust(llm, s)
    assert out.dimensions["depth"] == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_scores_stay_inside_0_1_after_adjustment(s):
    base = TurnScore(dimensions={"depth": 0.95})
    llm = FakeLLM({"Which GPUs?": '{"dimensions": {"depth": 5.0}}'}, settings=s)
    out = await _adjust(llm, s, base)
    assert out.dimensions["depth"] == 1.0


@pytest.mark.asyncio
async def test_unknown_dimensions_and_junk_values_are_ignored(s):
    llm = FakeLLM(
        {"Which GPUs?": '{"dimensions": {"charisma": 1.0, "depth": "very good"}}'},
        settings=s,
    )
    out = await _adjust(llm, s)
    assert out.dimensions == BASE.dimensions
    assert "charisma" not in out.dimensions


@pytest.mark.asyncio
async def test_an_insufficient_answer_is_never_rescued_by_the_model(s):
    base = TurnScore(insufficient=True, codes=["insufficient_answer"])
    llm = FakeLLM({"Which GPUs?": '{"dimensions": {"depth": 1.0}}'}, settings=s)
    out = await _adjust(llm, s, base)
    assert out.dimensions == {} and out.insufficient is True


@pytest.mark.asyncio
async def test_a_raising_llm_is_not_an_error(s):
    class Boom(LLMClient):
        async def _araw(self, **kw):
            raise RuntimeError("upstream down")

    out = await _adjust(Boom(s), s)
    assert out.dimensions == BASE.dimensions
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_interview_scoring_llm.py -q`
Expected: FAIL — `ImportError: cannot import name 'adjust_with_llm'`

- [ ] **Step 3: Implement**

Append to `app/interview/scoring.py` (and add `from app.services.llm import LLMClient`
plus `from app.core.logging import get_logger` at the top; `log = get_logger(__name__)`):

```python
_SCORING_SYSTEM = (
    "You are grading ONE answer from a technical interview, on four axes: "
    "specificity (concrete detail), ownership (what the speaker personally did), "
    "depth (coverage of what a genuine answer must contain), and consistency. "
    "Return only dimensions you are confident differ from the given baseline. "
    "You are an adjustment, not the grader: your suggestions are clamped."
)


async def adjust_with_llm(
    llm: LLMClient,
    *,
    question_text: str,
    transcript: str,
    expected_signals: Sequence[str],
    base: TurnScore,
    settings: Settings,
) -> TurnScore:
    """Optionally nudge a deterministic score. The model can move a dimension by
    at most `interview_llm_max_delta` and can never introduce one, rescue an
    insufficient answer, or produce a band by itself. Any failure -- no key, bad
    JSON, an exception -- silently leaves the deterministic score standing,
    because degrading to rules is the designed behaviour, not an error."""
    if base.insufficient or not base.dimensions:
        return base

    excerpt = (transcript or "")[: settings.interview_llm_excerpt_chars]
    try:
        data = await llm.acomplete_json(
            tier="scoring",
            system=_SCORING_SYSTEM,
            prompt=(
                f"QUESTION: {question_text}\n"
                f"EXPECTED SIGNALS: {list(expected_signals)}\n"
                f"BASELINE: {base.dimensions}\n"
                f"ANSWER: {excerpt}\n"
                'Return JSON: {"dimensions": {"<axis>": 0.0-1.0, ...}}'
            ),
        )
    except Exception as exc:  # noqa: BLE001 -- an LLM outage is not a failure here
        log.warning("interview_scoring_llm_failed", error=str(exc))
        return base

    proposed = (data or {}).get("dimensions")
    if not isinstance(proposed, dict):
        return base

    cap = settings.interview_llm_max_delta
    adjusted = dict(base.dimensions)
    changed = False
    for dim, raw in proposed.items():
        if dim not in adjusted:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        delta = max(-cap, min(cap, value - adjusted[dim]))
        if delta:
            adjusted[dim] = round(min(1.0, max(0.0, adjusted[dim] + delta)), 4)
            changed = True

    if not changed:
        return base
    return TurnScore(
        dimensions=adjusted, insufficient=False, codes=[*base.codes, "llm_adjusted"]
    )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_interview_scoring_llm.py tests/test_interview_scoring.py -q`
Expected: PASS (7 + 12). If the async tests error with "async def functions are not
natively supported", check `pyproject.toml` has `asyncio_mode = "auto"` or keep the
explicit `@pytest.mark.asyncio` markers used above (other repo tests show the convention —
match them).

- [ ] **Step 5: Commit**

```bash
git add app/interview/scoring.py tests/test_interview_scoring_llm.py
git commit -m "feat(s73): capped LLM scoring adjustment -- a nudge, never the grader"
```

---

### Task 6: Proxy risk (`app/interview/proxy.py`)

**Files:**
- Create: `app/interview/proxy.py`
- Test: `tests/test_interview_proxy.py`

**Interfaces:**
- Consumes: `InterviewTurn`, `ProxyBand`, `ProxyFinding`, `ProxyRisk`, `AnswerChannel`
  (Task 1); `IdentityAssurance` (S7.1); `Settings` (Task 2).
- Produces: `assess_proxy_risk(*, assurance, turns, settings) -> ProxyRisk`, and the
  finding-id constants. Task 10 calls it before `aggregate`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_interview_proxy.py`:

```python
"""Proxy hooks: the S7.1 assurance number plus behaviour. No voice biometrics --
that would need a stored voiceprint, which the spine makes impossible on
purpose. Nothing here can CONFIRM a proxy; the band stops at elevated."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.interview.proxy import assess_proxy_risk
from app.interview.schema import AnswerChannel, InterviewTurn, ProxyBand, TurnScore
from app.verification.schema import AssuranceLevel, IdentityAssurance

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def s(monkeypatch) -> Settings:
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


def _assurance(level: AssuranceLevel) -> IdentityAssurance:
    return IdentityAssurance(candidate_id="c1", level=level)


def _turn(seq: int, *, channel=AnswerChannel.AUDIO, words=40, seconds=30.0) -> InterviewTurn:
    return InterviewTurn(
        id=f"t{seq}", sequence=seq, question_id=f"q{seq}", question_text="q",
        question_source="probe", channel=channel, transcript="word " * words,
        word_count=words, asked_at=NOW, answered_at=NOW + timedelta(seconds=seconds),
        score=TurnScore(dimensions={"depth": 0.5}),
    )


def _ids(risk) -> set[str]:
    return {f.id for f in risk.findings}


def test_no_assurance_is_a_soft_finding(s):
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.NONE),
                             turns=[_turn(1)], settings=s)
    assert "identity_assurance_none" in _ids(risk)
    assert [f.severity for f in risk.findings if f.id == "identity_assurance_none"] == ["soft"]


def test_self_attested_only_is_info_not_soft(s):
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.SELF_ATTESTED),
                             turns=[_turn(1)], settings=s)
    assert "identity_assurance_low" in _ids(risk)
    assert "identity_assurance_none" not in _ids(risk)


def test_contact_control_or_better_raises_no_assurance_finding(s):
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
                             turns=[_turn(1)], settings=s)
    assert not {"identity_assurance_none", "identity_assurance_low"} & _ids(risk)
    assert risk.assurance_level_at_start == int(AssuranceLevel.CONTACT_CONTROL)


def test_impossibly_fast_speech_is_flagged(s):
    # 200 words in 10 seconds = 20 w/s, far past the 4.0 knob.
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
                             turns=[_turn(1, words=200, seconds=10.0)], settings=s)
    assert "answer_rate_implausible" in _ids(risk)


def test_a_normal_speaking_rate_is_not_flagged(s):
    # 40 words in 30 seconds = 1.3 w/s.
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
                             turns=[_turn(1)], settings=s)
    assert "answer_rate_implausible" not in _ids(risk)
    assert risk.band is ProxyBand.LOW


def test_pasted_text_is_flagged_on_its_own_threshold(s):
    risk = assess_proxy_risk(
        assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
        turns=[_turn(1, channel=AnswerChannel.TEXT, words=300, seconds=5.0)],
        settings=s,
    )
    assert "typed_answer_rate_implausible" in _ids(risk)


def test_a_text_only_session_says_so_rather_than_hiding_it(s):
    risk = assess_proxy_risk(
        assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
        turns=[_turn(1, channel=AnswerChannel.TEXT, words=40, seconds=120.0)],
        settings=s,
    )
    assert "text_channel_only" in _ids(risk)
    assert [f.severity for f in risk.findings if f.id == "text_channel_only"] == ["info"]


def test_band_needs_two_soft_findings_before_it_escalates(s):
    one_soft = assess_proxy_risk(assurance=_assurance(AssuranceLevel.NONE),
                                 turns=[_turn(1)], settings=s)
    assert one_soft.band is ProxyBand.MODERATE

    two_soft = assess_proxy_risk(assurance=_assurance(AssuranceLevel.NONE),
                                 turns=[_turn(1, words=200, seconds=10.0)], settings=s)
    assert two_soft.band is ProxyBand.ELEVATED


def test_the_band_stops_at_elevated_and_stays_advisory(s):
    risk = assess_proxy_risk(
        assurance=_assurance(AssuranceLevel.NONE),
        turns=[_turn(i, words=300, seconds=1.0) for i in range(1, 6)],
        settings=s,
    )
    assert risk.band is ProxyBand.ELEVATED
    assert risk.advisory is True


def test_no_turns_yields_the_assurance_finding_only(s):
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.NONE),
                             turns=[], settings=s)
    assert _ids(risk) == {"identity_assurance_none"}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_interview_proxy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.interview.proxy'`

- [ ] **Step 3: Implement**

Create `app/interview/proxy.py`:

```python
"""Advisory proxy-risk signals for an interview (S7.3). Pure: no I/O, no clock
(every rate is computed from the turns' own asked_at/answered_at).

What this is NOT: voice biometrics. Comparing voiceprints across sessions would
require storing a voice embedding -- exactly the artifact class S7.1 made
structurally impossible -- and would need its own consent purpose and legal
review. The roadmap asked for "proxy-detection hooks reading IdentityAssurance",
and that is precisely what this is: the assurance level held when the session
STARTED, plus behaviour visible in the timing and wording of the answers.

Nothing here can confirm a proxy, so ProxyBand stops at `elevated` and no
finding may be `hard`. Escalation needs TWO soft findings -- the S2.4 AND-gate,
so one noisy signal cannot brand anyone.
"""

from __future__ import annotations

from typing import Sequence

from app.core.config import Settings
from app.fabrication import ai_text
from app.interview.schema import (
    AnswerChannel, InterviewTurn, ProxyBand, ProxyFinding, ProxyRisk,
)
from app.verification.schema import AssuranceLevel, IdentityAssurance

ASSURANCE_NONE = "identity_assurance_none"
ASSURANCE_LOW = "identity_assurance_low"
RATE_IMPLAUSIBLE = "answer_rate_implausible"
TYPED_RATE_IMPLAUSIBLE = "typed_answer_rate_implausible"
AI_STYLE = "answer_style_ai_generated"
TEXT_ONLY = "text_channel_only"


def _elapsed_seconds(turn: InterviewTurn) -> float:
    delta = (turn.answered_at - turn.asked_at).total_seconds()
    return max(delta, 1.0)   # never divide by zero; sub-second is already extreme


def assess_proxy_risk(
    *,
    assurance: IdentityAssurance,
    turns: Sequence[InterviewTurn],
    settings: Settings,
) -> ProxyRisk:
    findings: list[ProxyFinding] = []

    level = int(assurance.level) if assurance is not None else 0
    if level <= int(AssuranceLevel.NONE):
        findings.append(ProxyFinding(
            id=ASSURANCE_NONE, severity="soft",
            message="nothing verifies who is taking this interview",
            detail={"assurance_level": level},
        ))
    elif level == int(AssuranceLevel.SELF_ATTESTED):
        findings.append(ProxyFinding(
            id=ASSURANCE_LOW, severity="info",
            message="identity is self-attested only",
            detail={"assurance_level": level},
        ))

    audio = [t for t in turns if t.channel is AnswerChannel.AUDIO]
    text = [t for t in turns if t.channel is AnswerChannel.TEXT]

    fast_audio = [
        t for t in audio
        if t.word_count / _elapsed_seconds(t) > settings.interview_max_words_per_second
    ]
    if fast_audio:
        findings.append(ProxyFinding(
            id=RATE_IMPLAUSIBLE, severity="soft",
            message="one or more answers arrived faster than they could be spoken",
            detail={"turns": len(fast_audio)},
        ))

    fast_text = [
        t for t in text
        if t.word_count / _elapsed_seconds(t) > settings.interview_max_typed_words_per_second
    ]
    if fast_text:
        findings.append(ProxyFinding(
            id=TYPED_RATE_IMPLAUSIBLE, severity="soft",
            message="one or more typed answers arrived faster than they could be typed",
            detail={"turns": len(fast_text)},
        ))

    if turns:
        joined = "\n".join(t.transcript for t in turns if t.transcript)
        style = ai_text.assess_deterministic(joined)
        # The same conservatism band_for() applies to resumes: >= 2 independent
        # tells before the word "generated" is used at all.
        if len(style.signals) >= 2 and style.likelihood >= settings.ai_likely_threshold:
            findings.append(ProxyFinding(
                id=AI_STYLE, severity="soft",
                message="answer wording carries several machine-generated tells",
                detail={"tells": len(style.signals)},
            ))

    if turns and not audio:
        findings.append(ProxyFinding(
            id=TEXT_ONLY, severity="info",
            message="every answer was typed; voice-based proxy signals are unavailable",
            detail={"turns": len(text)},
        ))

    soft = sum(1 for f in findings if f.severity == "soft")
    band = ProxyBand.ELEVATED if soft >= 2 else (
        ProxyBand.MODERATE if soft == 1 else ProxyBand.LOW
    )
    return ProxyRisk(band=band, findings=findings, assurance_level_at_start=level)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_interview_proxy.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add app/interview/proxy.py tests/test_interview_proxy.py
git commit -m "feat(s73): proxy risk from assurance + behaviour, never biometrics"
```

---

### Task 7: The speech seam (`app/services/speech.py`) + `FakeSpeech`

**Files:**
- Create: `app/services/speech.py`
- Modify: `tests/conftest.py` (add `FakeSpeech`)
- Test: `tests/test_speech_seam.py`

**Interfaces:**
- Consumes: `Settings` (Task 2).
- Produces: `Transcript`, `SpeechClient`, `OpenRouterSpeech`, `NullSpeech`,
  `SpeechUnavailable`, `SpeechFailed`, `build_speech(settings) -> SpeechClient`,
  `AUDIO_FORMATS`; and `tests.conftest.FakeSpeech`. Task 10 awaits
  `speech.atranscribe(audio_b64=…, mime=…)`; Task 12 maps both exceptions to 422.

- [ ] **Step 1: Write the failing test**

Create `tests/test_speech_seam.py`:

```python
"""The ASR seam mirrors the LLM seam: an ABC, a live client, and a Null that
refuses. No key => audio is refused with a distinct error and the interview
runs as a TEXT interview. That is the deterministic fallback, stated honestly
rather than degraded silently."""

import pytest

from app.core.config import Settings
from app.services.speech import (
    NullSpeech, OpenRouterSpeech, SpeechClient, SpeechFailed, SpeechUnavailable,
    Transcript, build_speech, format_for_mime,
)


@pytest.fixture
def s(monkeypatch) -> Settings:
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


def test_no_key_builds_the_refusing_client(s):
    assert isinstance(build_speech(s), NullSpeech)


def test_a_key_plus_the_openrouter_provider_builds_the_live_client(monkeypatch):
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    keyed = Settings(_env_file=None, openrouter_api_key="sk-test",
                     speech_provider="openrouter")
    assert isinstance(build_speech(keyed), OpenRouterSpeech)


@pytest.mark.parametrize("provider", ["sarvam", "local"])
def test_declared_but_unimplemented_providers_are_inert_even_with_a_key(
    monkeypatch, provider
):
    """Inertness must read the same at every door -- the S7.2 review lesson."""
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    keyed = Settings(_env_file=None, openrouter_api_key="sk-test",
                     speech_provider=provider)
    assert isinstance(build_speech(keyed), NullSpeech)


@pytest.mark.asyncio
async def test_null_speech_refuses_with_speech_unavailable(s):
    with pytest.raises(SpeechUnavailable):
        await NullSpeech(s).atranscribe(audio_b64="AAAA", mime="audio/wav")


def test_known_mimes_map_to_provider_formats():
    assert format_for_mime("audio/wav") == "wav"
    assert format_for_mime("audio/mpeg") == "mp3"
    assert format_for_mime("audio/webm") == "webm"


def test_an_unknown_mime_is_refused_before_any_call():
    with pytest.raises(SpeechFailed):
        format_for_mime("application/pdf")


def test_transcript_carries_text_and_optional_duration():
    t = Transcript(text="hello", duration_seconds=1.5, model="voxtral")
    assert t.text == "hello" and t.duration_seconds == 1.5


def test_speech_client_is_abstract(s):
    with pytest.raises(TypeError):
        SpeechClient(s)   # type: ignore[abstract]


@pytest.mark.asyncio
async def test_fake_speech_records_calls_and_returns_its_script(s):
    from tests.conftest import FakeSpeech

    fake = FakeSpeech(text="I used 8 A100s for 14 hours")
    out = await fake.atranscribe(audio_b64="AAAA", mime="audio/wav")
    assert out.text == "I used 8 A100s for 14 hours"
    assert fake.calls == [("AAAA", "audio/wav")]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_speech_seam.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.speech'`

- [ ] **Step 3: Implement**

Create `app/services/speech.py`:

```python
"""ASR seam -- tiered, config-driven, key never hardcoded (S7.3).

Deliberately shaped like app/services/llm.py, which has survived six PIs: an
abstract client, a live OpenRouter implementation, and a Null that refuses so
tests need no network and a keyless deployment still works.

The refusal matters and is not an error path to paper over. With no key an
AUDIO answer is refused with SpeechUnavailable, the route turns that into a 422
naming the text channel, and the interview proceeds as a text interview. Nothing
silently degrades to a worse number.

TTS is deliberately absent (spec section 0.3): OpenRouter serves no TTS and the
local option is a GPU dependency neither the offline suite nor the key-less
smoke could exercise. Questions are delivered as text.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class SpeechUnavailable(Exception):
    """No speech provider is configured. The caller should offer the text
    channel -- this is the designed no-key path, not a malfunction."""


class SpeechFailed(Exception):
    """A configured provider could not transcribe this audio (bad format,
    timeout, upstream error). The caller must NOT record a turn: a retry has to
    be free, so a vendor outage never costs a candidate their answer."""


#: mime -> the `format` string the OpenAI-wire audio part expects.
AUDIO_FORMATS: dict[str, str] = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
}


def format_for_mime(mime: str) -> str:
    """Resolve a mime type, or refuse before any vendor call is made."""
    fmt = AUDIO_FORMATS.get((mime or "").split(";")[0].strip().casefold())
    if not fmt:
        raise SpeechFailed(f"unsupported audio type: {mime!r}")
    return fmt


class Transcript(BaseModel):
    text: str = ""
    duration_seconds: Optional[float] = None
    model: Optional[str] = None


class SpeechClient(ABC):
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    @abstractmethod
    async def atranscribe(self, *, audio_b64: str, mime: str) -> Transcript:
        ...


class OpenRouterSpeech(SpeechClient):
    """Live ASR through an audio-capable OpenRouter model (`asr_model`), on the
    OpenAI-compatible wire. Same account and SDK as the text tiers -- no second
    vendor relationship for v0 (MODELS.md, 2026-07-26)."""

    _SYSTEM = (
        "Transcribe the spoken answer verbatim in English. Return only the "
        "transcript text, with no commentary, labels, or timestamps."
    )

    def __init__(self, settings: Optional[Settings] = None) -> None:
        super().__init__(settings)
        from openai import AsyncOpenAI  # local import; optional at test time

        headers: dict[str, str] = {}
        if self.settings.openrouter_app_url:
            headers["HTTP-Referer"] = self.settings.openrouter_app_url
        if self.settings.openrouter_app_title:
            headers["X-Title"] = self.settings.openrouter_app_title

        self._client = AsyncOpenAI(
            api_key=self.settings.openrouter_api_key.get_secret_value(),
            base_url=self.settings.openrouter_base_url,
            timeout=self.settings.speech_timeout_seconds,
            max_retries=self.settings.speech_max_retries,
            default_headers=headers or None,
        )

    async def atranscribe(self, *, audio_b64: str, mime: str) -> Transcript:
        fmt = format_for_mime(mime)   # refuse before spending a call
        model = self.settings.asr_model
        try:
            resp = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": self._SYSTEM},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Transcribe this answer."},
                            {
                                "type": "input_audio",
                                "input_audio": {"data": audio_b64, "format": fmt},
                            },
                        ],
                    },
                ],
            )
        except Exception as exc:  # noqa: BLE001 -- one failure surface for the caller
            log.warning("asr_failed", model=model, error=str(exc))
            raise SpeechFailed(f"transcription failed: {exc}") from exc

        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise SpeechFailed("transcription returned no text")
        return Transcript(text=text, model=model)


class NullSpeech(SpeechClient):
    """No-provider fallback: refuses, so the caller offers the text channel."""

    async def atranscribe(self, *, audio_b64: str, mime: str) -> Transcript:
        raise SpeechUnavailable(
            "no speech provider is configured; answer this question in text"
        )


def build_speech(settings: Optional[Settings] = None) -> SpeechClient:
    settings = settings or get_settings()
    if settings.speech_provider == "openrouter" and settings.has_openrouter_key:
        return OpenRouterSpeech(settings)
    # `sarvam` and `local` are DECLARED but unimplemented in v0. They build the
    # refusing client even with a key -- a declared-but-inert provider must
    # answer the same way at every door (the S7.2 review lesson).
    log.warning(
        "speech_unavailable",
        provider=settings.speech_provider,
        detail="Audio answers will be refused; the text channel still works.",
    )
    return NullSpeech(settings)
```

In `tests/conftest.py`, add `FakeSpeech` after `FakeLLM`:

```python
class FakeSpeech(SpeechClient):
    """Scripted ASR: returns canned text and records what it was handed."""

    def __init__(self, text: str = "I built the ingestion path myself and it held",
                 settings: Settings | None = None,
                 fail: Exception | None = None) -> None:
        super().__init__(settings or Settings(_env_file=None, openrouter_api_key=""))
        self.text = text
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def atranscribe(self, *, audio_b64: str, mime: str):
        self.calls.append((audio_b64, mime))
        if self.fail is not None:
            raise self.fail
        return Transcript(text=self.text, duration_seconds=30.0, model="fake-asr")
```

with the import `from app.services.speech import SpeechClient, Transcript` at the top of
`conftest.py`.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_speech_seam.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/speech.py tests/test_speech_seam.py tests/conftest.py
git commit -m "feat(s73): ASR seam -- OpenRouter live, Null refuses, text channel stands"
```

---

### Task 8: ORM rows + migration `0015_ai_interviews`

**Files:**
- Create: `app/interview/models.py`, `alembic/versions/0015_ai_interviews.py`
- Modify: `tests/conftest.py` (register the models in `Base.metadata`), `tests/test_migrations.py`
- Test: `tests/test_interview_models.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (ORM only).
- Produces: `InterviewSessionRow`, `InterviewTurnRow`, tables `interview_sessions` /
  `interview_turns`, migration revision `0015_ai_interviews` (down: `0014_verification_subject`).
  Task 9 reads/writes these.

- [ ] **Step 1: Write the failing test**

Create `tests/test_interview_models.py`:

```python
"""Structural DPDP: no column here can hold audio. The single audio field is a
sha256 digest, so a future adapter cannot persist a voice sample without a
migration a reviewer would see -- the S7.1/S7.2 posture, unchanged."""

from sqlalchemy import String, Text

from app.interview.models import InterviewSessionRow, InterviewTurnRow


def _cols(model):
    return {c.name: c for c in model.__table__.columns}


def test_table_names():
    assert InterviewSessionRow.__tablename__ == "interview_sessions"
    assert InterviewTurnRow.__tablename__ == "interview_turns"


def test_sessions_cascade_from_candidates():
    fk = next(iter(_cols(InterviewSessionRow)["candidate_id"].foreign_keys))
    assert fk.column.table.name == "candidates"
    assert fk.ondelete == "CASCADE"


def test_turns_cascade_from_sessions():
    fk = next(iter(_cols(InterviewTurnRow)["session_id"].foreign_keys))
    assert fk.column.table.name == "interview_sessions"
    assert fk.ondelete == "CASCADE"


def test_the_audio_field_is_a_digest_not_a_blob():
    audio = _cols(InterviewTurnRow)["audio_digest"]
    assert isinstance(audio.type, String)
    assert audio.type.length == 64          # sha256 hex, and nothing larger fits


def test_no_column_on_either_table_can_hold_audio():
    """The transcript is TEXT by design (spec section 0.1). Nothing else is:
    a reviewer scanning for "where could bytes live" must find one answer."""
    for model in (InterviewSessionRow, InterviewTurnRow):
        for name, col in _cols(model).items():
            if isinstance(col.type, Text):
                assert name == "transcript", (
                    f"{model.__tablename__}.{name} is unbounded TEXT; only the "
                    "transcript may be, and audio never may"
                )
            assert "blob" not in type(col.type).__name__.casefold()
            assert "binary" not in type(col.type).__name__.casefold()


def test_report_id_is_a_loose_reference_not_a_foreign_key():
    """Reports live in a separate SQLite database (report_db_path), so an FK is
    not expressible -- the VerificationRow.consent_id precedent."""
    assert not _cols(InterviewSessionRow)["report_id"].foreign_keys


def test_status_and_candidate_are_indexed_for_the_reads_we_actually_do():
    cols = _cols(InterviewSessionRow)
    assert cols["candidate_id"].index is True
    assert cols["status"].index is True
    assert _cols(InterviewTurnRow)["session_id"].index is True


def test_assessment_and_scorer_version_are_stored_on_the_session():
    cols = _cols(InterviewSessionRow)
    assert "assessment" in cols and cols["assessment"].nullable is True
    assert cols["scorer_version"].type.length == 16
    assert cols["assurance_level_at_start"].nullable is False
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_interview_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.interview.models'`

- [ ] **Step 3: Implement**

Create `app/interview/models.py`:

```python
"""ORM rows for AI interviews (S7.3). Postgres-shaped on SQLite.

Two tables: a session (durable outcome + plan) and its turns. Note the absent
columns -- nothing here can hold audio. The one audio field is a sha256 digest,
so the "we never store the recording" claim is structural rather than
procedural, exactly as in S7.1/S7.2.

`transcript` IS stored, deliberately (spec section 0.1): it is first-party
content the candidate produced to be evaluated, and an advisory score whose
basis nobody can read is worse for the candidate than the PII cost. It is
candidate-visible and never disclosed to an org in v0.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewSessionRow(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    domain: Mapped[str] = mapped_column(String(32))
    # Which depth report supplied the probes. NOT a FK: reports live in a
    # separate SQLite database (report_db_path), so the constraint is not
    # expressible -- the VerificationRow.consent_id precedent.
    report_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    # The S7.1 hook, stamped when the session STARTED and never recomputed: a
    # candidate must not be able to verify themselves afterwards and rewrite
    # what the session was worth.
    assurance_level_at_start: Mapped[int] = mapped_column(Integer, default=0)
    planned_questions: Mapped[list] = mapped_column(JSON, default=list)
    # Computed ONCE at completion and stored. Unlike IdentityAssurance and
    # ClaimEvidence -- which depend on the clock and on rows that arrive later,
    # so storing them would store a lie -- an assessment is a closed fact about
    # a finished session, and recomputing it would re-hit a paid model.
    assessment: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    scorer_version: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InterviewTurnRow(Base):
    __tablename__ = "interview_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    question_id: Mapped[str] = mapped_column(String(36))
    question_text: Mapped[str] = mapped_column(Text)
    question_source: Mapped[str] = mapped_column(String(24))
    expected_signals: Mapped[list] = mapped_column(JSON, default=list)
    channel: Mapped[str] = mapped_column(String(8))
    #: The candidate's own words. The ONLY unbounded column on either table.
    transcript: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    #: sha256 of the submitted audio. The bytes are discarded with the request.
    audio_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    audio_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

Wait — `question_text` is `Text` and would trip `test_no_column_on_either_table_can_hold_audio`.
**Make `question_text` `String(512)`** instead: a question is platform-authored and bounded,
so the exception list stays exactly one column. Use:

```python
    question_text: Mapped[str] = mapped_column(String(512))
```

Create `alembic/versions/0015_ai_interviews.py`:

```python
"""ai interview sessions + turns (S7.3)

Revision ID: 0015_ai_interviews
Revises: 0014_verification_subject
Create Date: 2026-08-01

Two tables, both CASCADE: sessions from candidates, turns from sessions. The
existing DPDP hard-delete therefore sweeps an interview whole -- no new erasure
path exists or is needed.

Nothing here can hold audio. `transcript` is deliberately Text (the candidate's
own words, spec section 0.1); the only audio field is a sha256 digest.
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_ai_interviews"
down_revision = "0014_verification_subject"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("assurance_level_at_start", sa.Integer(), nullable=False),
        sa.Column("planned_questions", sa.JSON(), nullable=False),
        sa.Column("assessment", sa.JSON(), nullable=True),
        sa.Column("scorer_version", sa.String(length=16), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_interview_sessions_candidate_id", "interview_sessions",
                    ["candidate_id"])
    op.create_index("ix_interview_sessions_status", "interview_sessions", ["status"])

    op.create_table(
        "interview_turns",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("question_text", sa.String(length=512), nullable=False),
        sa.Column("question_source", sa.String(length=24), nullable=False),
        sa.Column("expected_signals", sa.JSON(), nullable=False),
        sa.Column("channel", sa.String(length=8), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("audio_digest", sa.String(length=64), nullable=True),
        sa.Column("audio_duration_seconds", sa.Float(), nullable=True),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_interview_turns_session_id", "interview_turns", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_interview_turns_session_id", table_name="interview_turns")
    op.drop_table("interview_turns")
    op.drop_index("ix_interview_sessions_status", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_candidate_id", table_name="interview_sessions")
    op.drop_table("interview_sessions")
```

In `tests/conftest.py`, add the metadata registration beside the others:

```python
import app.interview.models  # noqa: F401 — populate Base.metadata with interview tables
```

Also add the same import to `alembic/env.py` if that file imports the other model modules
(check it; if it imports `app.verification.models`, add `app.interview.models` next to it).

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_interview_models.py tests/test_migrations.py -q`
Expected: PASS. The four existing guards in `test_migrations.py`
(`test_migrated_schema_matches_orm_models`, `test_migrated_indexes_match_orm`,
`test_migrated_fks_and_nullability_match_orm`, `test_upgrade_head_creates_candidate_tables`)
are metadata-wide and will now cover the new tables automatically. If any fails, the
migration and the ORM disagree — **fix the migration**, and read the failure carefully: this
guard caught a real `nullable` drift in S7.1.

- [ ] **Step 5: Commit**

```bash
git add app/interview/models.py alembic tests/test_interview_models.py tests/conftest.py
git commit -m "feat(s73): interview tables + 0015 migration, both CASCADE, no audio column"
```

---

### Task 9: Read-time status + persistence (`session.py`, `store.py`)

**Files:**
- Create: `app/interview/session.py`, `app/interview/store.py`
- Test: `tests/test_interview_store.py`

**Interfaces:**
- Consumes: contracts (Task 1), rows (Task 8), `LedgerStore._audit`.
- Produces:
  - `session.effective_status(status, expires_at, *, at) -> InterviewStatus`
  - `InterviewStore(session_factory, *, ledger, settings)` with
    `create_session(*, candidate_id, domain, report_id, questions, assurance_level, at) -> InterviewSession`,
    `get_session(session_id) -> Optional[InterviewSession]`,
    `sessions_for_candidate(candidate_id) -> list[InterviewSession]`,
    `live_session_for_candidate(candidate_id, *, at) -> Optional[InterviewSession]`,
    `add_turn(session_id, *, question, channel, transcript, word_count, audio_digest, audio_duration_seconds, score, asked_at, answered_at) -> InterviewTurn`,
    `complete_session(session_id, *, assessment, at) -> InterviewSession`.
  Task 10 calls all of these; Task 11 adds `assessments_for_org` to this class.

- [ ] **Step 1: Write the failing test**

Create `tests/test_interview_store.py`:

```python
"""Persistence + audit. Expiry is READ-TIME: the stored status stays
in_progress and `effective_status` derives `abandoned`, because no sweeper
exists and a stored `abandoned` would be a lie nobody corrects (the S7.1 rule)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.interview.schema import (
    AnswerChannel, InterviewAssessment, InterviewQuestion, InterviewStatus, ProxyRisk,
    TurnScore,
)
from app.interview.session import effective_status
from app.interview.store import InterviewStore
from app.ledger.store import LedgerStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def wiring(settings):
    candidates = make_candidate_store()
    ledger = LedgerStore(candidates._session_factory, settings=settings)
    store = InterviewStore(candidates._session_factory, ledger=ledger, settings=settings)
    candidate = candidates.ingest(resume_text="Ravi. ML Engineer at Acme.",
                                  profile=None) if False else None
    return candidates, ledger, store


@pytest.fixture
def candidate_id(wiring):
    candidates, _, _ = wiring
    from app.candidates.models import CandidateRow
    with candidates._session_factory() as s:
        row = CandidateRow(id="cand_1")
        s.add(row)
        s.commit()
    return "cand_1"


def _questions(n: int = 2) -> list[InterviewQuestion]:
    return [
        InterviewQuestion(id=f"q{i}", sequence=i, text=f"question {i}", source="probe",
                          expected_signals=["gpu"])
        for i in range(1, n + 1)
    ]


def test_effective_status_derives_abandoned_without_writing_it():
    expires = NOW + timedelta(hours=1)
    assert effective_status(InterviewStatus.IN_PROGRESS, expires, at=NOW) is (
        InterviewStatus.IN_PROGRESS)
    assert effective_status(InterviewStatus.IN_PROGRESS, expires,
                            at=NOW + timedelta(hours=2)) is InterviewStatus.ABANDONED
    # A completed session never expires into abandoned.
    assert effective_status(InterviewStatus.COMPLETED, expires,
                            at=NOW + timedelta(days=9)) is InterviewStatus.COMPLETED


def test_create_session_stores_the_plan_and_stamps_assurance(wiring, candidate_id, settings):
    _, _, store = wiring
    session = store.create_session(
        candidate_id=candidate_id, domain="genai", report_id="rep_1",
        questions=_questions(), assurance_level=2, at=NOW,
    )
    assert session.status is InterviewStatus.IN_PROGRESS
    assert session.assurance_level_at_start == 2
    assert [q.text for q in session.questions] == ["question 1", "question 2"]
    assert session.expires_at == NOW + timedelta(
        minutes=settings.interview_session_ttl_minutes)


def test_create_session_refuses_an_unknown_candidate(wiring):
    _, _, store = wiring
    with pytest.raises(LookupError):
        store.create_session(candidate_id="nope", domain="genai", report_id=None,
                             questions=_questions(), assurance_level=0, at=NOW)


def test_starting_a_session_is_audited_into_the_candidates_access_log(
    wiring, candidate_id
):
    _, ledger, store = wiring
    store.create_session(candidate_id=candidate_id, domain="genai", report_id=None,
                         questions=_questions(), assurance_level=0, at=NOW)
    actions = [e.action for e in ledger.audit_for_candidate(candidate_id)]
    assert "interview.start" in actions


def test_add_turn_persists_the_transcript_and_the_digest_only(wiring, candidate_id):
    _, _, store = wiring
    session = store.create_session(candidate_id=candidate_id, domain="genai",
                                   report_id=None, questions=_questions(),
                                   assurance_level=0, at=NOW)
    turn = store.add_turn(
        session.id, question=session.questions[0], channel=AnswerChannel.AUDIO,
        transcript="I ran it on 8 A100s", word_count=6, audio_digest="a" * 64,
        audio_duration_seconds=12.0, score=TurnScore(dimensions={"depth": 1.0}),
        asked_at=NOW, answered_at=NOW + timedelta(seconds=30),
    )
    assert turn.transcript == "I ran it on 8 A100s"
    assert turn.audio_digest == "a" * 64
    assert turn.sequence == 1

    reread = store.get_session(session.id)
    assert len(reread.turns) == 1
    assert reread.turns[0].score.dimensions == {"depth": 1.0}


def test_turns_come_back_in_sequence_order(wiring, candidate_id):
    _, _, store = wiring
    session = store.create_session(candidate_id=candidate_id, domain="genai",
                                   report_id=None, questions=_questions(3),
                                   assurance_level=0, at=NOW)
    for q in reversed(session.questions):
        store.add_turn(session.id, question=q, channel=AnswerChannel.TEXT,
                       transcript="answer", word_count=1, audio_digest=None,
                       audio_duration_seconds=None, score=TurnScore(),
                       asked_at=NOW, answered_at=NOW)
    assert [t.sequence for t in store.get_session(session.id).turns] == [1, 2, 3]


def test_complete_session_stores_the_assessment_and_audits(wiring, candidate_id):
    _, ledger, store = wiring
    session = store.create_session(candidate_id=candidate_id, domain="genai",
                                   report_id=None, questions=_questions(),
                                   assurance_level=0, at=NOW)
    assessment = InterviewAssessment(
        session_id=session.id, candidate_id=candidate_id, questions_planned=2,
        questions_answered=2, proxy=ProxyRisk(), scorer_version="s73.1", overall=0.6,
    )
    done = store.complete_session(session.id, assessment=assessment,
                                  at=NOW + timedelta(minutes=5))
    assert done.status is InterviewStatus.COMPLETED
    assert done.assessment.overall == 0.6
    assert done.completed_at == NOW + timedelta(minutes=5)
    assert store.get_session(session.id).scorer_version == "s73.1"
    assert "interview.complete" in [e.action for e in ledger.audit_for_candidate(candidate_id)]


def test_live_session_ignores_completed_and_expired_ones(wiring, candidate_id):
    _, _, store = wiring
    session = store.create_session(candidate_id=candidate_id, domain="genai",
                                   report_id=None, questions=_questions(),
                                   assurance_level=0, at=NOW)
    assert store.live_session_for_candidate(candidate_id, at=NOW).id == session.id
    # Past its TTL it is no longer live, without anything being written.
    assert store.live_session_for_candidate(
        candidate_id, at=NOW + timedelta(days=1)) is None


def test_sessions_for_candidate_is_scoped_and_ordered(wiring, candidate_id):
    candidates, _, store = wiring
    from app.candidates.models import CandidateRow
    with candidates._session_factory() as s:
        s.add(CandidateRow(id="cand_2"))
        s.commit()
    store.create_session(candidate_id=candidate_id, domain="genai", report_id=None,
                         questions=_questions(), assurance_level=0, at=NOW)
    store.create_session(candidate_id="cand_2", domain="genai", report_id=None,
                         questions=_questions(), assurance_level=0, at=NOW)
    mine = store.sessions_for_candidate(candidate_id)
    assert len(mine) == 1 and mine[0].candidate_id == candidate_id
```

Note for the implementer: the `wiring` fixture above creates the candidate row directly
(`CandidateRow(id="cand_1")`) because these tests exercise the store, not ingestion. Drop
the unused `candidate = ...` line in `wiring` — it is a leftover; the fixture should just
return `(candidates, ledger, store)`.

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_interview_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.interview.session'`

- [ ] **Step 3: Implement**

Create `app/interview/session.py`:

```python
"""The session-status rule (S7.3). Pure, clock-injected, four lines on purpose.

Expiry is computed at READ time and never written. There is no scheduler in
this system, so a stored `abandoned` would be a lie nobody corrects -- the same
reasoning that keeps S7.1's `expired` derived rather than stamped.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.ledger.consent import as_utc
from app.interview.schema import InterviewStatus


def effective_status(
    status: InterviewStatus, expires_at: Optional[datetime], *, at: datetime
) -> InterviewStatus:
    """`abandoned` once an unfinished session passes its TTL. A finished
    session is finished forever."""
    if status is not InterviewStatus.IN_PROGRESS:
        return status
    if expires_at is not None and as_utc(expires_at) <= as_utc(at):
        return InterviewStatus.ABANDONED
    return status
```

Create `app/interview/store.py` following `app/verification/store.py`'s discipline exactly:

```python
"""Interview persistence + audit (S7.3).

Mirrors VerificationStore: every mutation is audited in the SAME transaction as
the write, through LedgerStore._audit, so an interview shows up in the
candidate's own DPDP access log for free.

Start and completion are audited; individual turns are not. A turn is the
candidate acting on their own session, inside a session whose start they can
already see -- a row per answer would flood the very log that exists to make
disclosure legible.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.candidates.models import CandidateRow
from app.core.config import Settings, get_settings
from app.interview.models import InterviewSessionRow, InterviewTurnRow
from app.interview.schema import (
    AnswerChannel, InterviewAssessment, InterviewQuestion, InterviewSession,
    InterviewStatus, InterviewTurn, QuestionSource, TurnScore,
)
from app.ledger.consent import as_utc
from app.ledger.store import LedgerStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _turn(row: InterviewTurnRow) -> InterviewTurn:
    return InterviewTurn(
        id=row.id,
        sequence=row.sequence,
        question_id=row.question_id,
        question_text=row.question_text,
        question_source=QuestionSource(row.question_source),
        expected_signals=list(row.expected_signals or []),
        channel=AnswerChannel(row.channel),
        transcript=row.transcript or "",
        word_count=row.word_count or 0,
        audio_digest=row.audio_digest,
        audio_duration_seconds=row.audio_duration_seconds,
        asked_at=as_utc(row.asked_at),
        answered_at=as_utc(row.answered_at),
        score=TurnScore(**(row.scores or {})),
    )


def _session(row: InterviewSessionRow, turns: Sequence[InterviewTurnRow]) -> InterviewSession:
    return InterviewSession(
        id=row.id,
        candidate_id=row.candidate_id,
        domain=row.domain,
        report_id=row.report_id,
        status=InterviewStatus(row.status),
        assurance_level_at_start=row.assurance_level_at_start or 0,
        questions=[InterviewQuestion(**q) for q in (row.planned_questions or [])],
        turns=[_turn(t) for t in turns],
        assessment=(InterviewAssessment(**row.assessment) if row.assessment else None),
        started_at=as_utc(row.started_at),
        completed_at=as_utc(row.completed_at) if row.completed_at else None,
        expires_at=as_utc(row.expires_at) if row.expires_at else None,
    )
```

The class itself — implement these methods with the shapes named in **Interfaces**:

- `create_session`: verify the candidate exists (`LookupError` otherwise); insert the row
  with `planned_questions=[q.model_dump(mode="json") for q in questions]`,
  `status=IN_PROGRESS`, `expires_at = moment + timedelta(minutes=settings.interview_session_ttl_minutes)`;
  audit `action="interview.start"`, `actor_type="candidate"`, `actor_id=candidate_id`,
  `entity_type="interview_session"`, `details={"domain": domain, "questions": len(questions),
  "assurance_level": assurance_level}`; commit; return `_session(row, [])`.
- `_turns_for(session, session_id)`: `select(InterviewTurnRow).where(...).order_by(InterviewTurnRow.sequence, InterviewTurnRow.id)`.
- `get_session` / `sessions_for_candidate`: read + convert; the latter ordered by
  `started_at, id`.
- `live_session_for_candidate(candidate_id, *, at)`: the newest `IN_PROGRESS` row whose
  `effective_status(..., at=at)` is still `IN_PROGRESS`; else `None`.
- `add_turn`: `sequence = 1 + count(existing turns)`; insert; **no audit**; commit; return
  `_turn(row)`. Store `score.model_dump()` into `scores`.
- `complete_session(session_id, *, assessment, at)`: set `status=COMPLETED`,
  `completed_at=at`, `assessment=assessment.model_dump(mode="json")`,
  `scorer_version=assessment.scorer_version`; audit `action="interview.complete"`,
  `actor_type="system"`, `details={"band": assessment.band.value, "answered":
  assessment.questions_answered, "planned": assessment.questions_planned}`; commit.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_interview_store.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add app/interview/session.py app/interview/store.py tests/test_interview_store.py
git commit -m "feat(s73): interview store -- audited start/complete, read-time expiry"
```

---

### Task 10: The service state machine + `Services` wiring

**Files:**
- Create: `app/interview/service.py`
- Modify: `app/services/__init__.py`, `tests/conftest.py`
- Test: `tests/test_interview_service.py`

**Interfaces:**
- Consumes: everything from Tasks 1–9.
- Produces: `InterviewService` with
  `start(candidate_id, *, domain_key="genai", at=None) -> InterviewSession`,
  `async answer(candidate_id, session_id, *, question_id, text=None, audio_b64=None, mime=None, at=None) -> tuple[InterviewSession, Optional[InterviewQuestion]]`,
  `get(candidate_id, session_id, *, at=None) -> InterviewSession`,
  `list_for_candidate(candidate_id, *, at=None) -> list[InterviewSummary]`,
  `async finish(candidate_id, session_id, *, at=None) -> InterviewSession`;
  exceptions `SessionConflictError`, `AnswerTooLargeError`;
  `build_interview_service(settings, *, candidates, ledger, report_store, verification, llm, speech) -> InterviewService`;
  `Services.speech`, `Services.interview`. Tasks 11–13 build on this.

- [ ] **Step 1: Write the failing test**

Create `tests/test_interview_service.py` covering, at minimum, these behaviours (write each
as its own test function, in this order):

```python
"""The state machine. Every gate here exists because a candidate-facing entry
point without one is how S7.1 and S7.2 both got escalations."""
```

1. `test_start_builds_a_plan_and_stamps_the_current_assurance_level` — ingest a resume,
   start, assert `session.questions` is non-empty, `status is IN_PROGRESS`,
   `assurance_level_at_start == 0`.
2. `test_start_stamps_a_higher_level_after_the_candidate_self_attests` — call
   `services.verification.start(candidate_id, VerificationMethod.SELF_ATTESTED)` first,
   then start an interview; assert `assurance_level_at_start == 1`. **This is the
   proxy hook, end to end.**
3. `test_start_refuses_when_there_is_nothing_to_ask` — bare `CandidateRow`, no profile →
   `NothingToAskError`.
4. `test_a_second_start_while_one_is_live_is_a_conflict` — `SessionConflictError`; assert
   the raised error names the live session id.
5. `test_a_second_start_is_allowed_once_the_first_expired` — pass `at=NOW + ttl + 1min`.
6. `test_answering_the_current_question_scores_it_and_advances` — assert the returned
   next question is sequence 2 and `session.turns[0].score.dimensions` is populated.
7. `test_answering_a_question_out_of_turn_is_refused` — wrong `question_id` →
   `SessionConflictError`; assert **no turn was recorded**.
8. `test_answering_an_expired_session_is_refused` — `SessionConflictError`.
9. `test_answering_a_completed_session_is_refused` — `SessionConflictError`.
10. `test_another_candidates_session_is_indistinguishable_from_a_missing_one` — a second
    candidate calling `get`/`answer` gets `LookupError`, and the first candidate's session
    is untouched.
11. `test_an_audio_answer_with_no_provider_is_refused_and_records_nothing` — default
    `NullSpeech` → `SpeechUnavailable`; assert `len(session.turns) == 0` afterwards.
12. `test_an_audio_answer_transcribes_stores_the_digest_and_discards_the_bytes` — inject
    `FakeSpeech`; assert `turn.transcript == fake.text`, `turn.audio_digest ==
    hashlib.sha256(base64.b64decode(audio_b64)).hexdigest()`, and that
    `turn.transcript != audio_b64` (the payload is nowhere in the row).
13. `test_a_failing_asr_records_no_turn_so_a_retry_is_free` — `FakeSpeech(fail=SpeechFailed(...))`.
14. `test_an_oversize_audio_body_is_refused_before_any_decode` — `AnswerTooLargeError`,
    and `fake.calls == []`.
15. `test_an_oversize_text_answer_is_refused` — `AnswerTooLargeError`.
16. `test_answering_the_last_question_completes_the_session_and_stores_an_assessment` —
    assert `status is COMPLETED`, `assessment is not None`, `assessment.advisory is True`,
    `assessment.proxy.assurance_level_at_start == session.assurance_level_at_start`,
    and the returned next question is `None`.
17. `test_finish_completes_early_with_lower_confidence` — answer 1 of 3, finish, assert
    `coverage < 1.0` and `band is INSUFFICIENT_SIGNAL`.
18. `test_finishing_an_already_completed_session_is_a_conflict`.
19. `test_list_for_candidate_returns_summaries_without_transcripts` — assert every returned
    object is an `InterviewSummary` and `"transcript" not in dumped` for each.

Use the repo's existing fixtures: `services` (offline), and ingest a real profile with
`services.candidates.ingest(...)` the way `tests/test_verification_claim_service.py` does —
**read that file first and copy its fixture shape**, because S7.2's plan got burned by
fixtures that created a bare `CandidateRow` with no profile behind it.

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_interview_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.interview.service'`

- [ ] **Step 3: Implement**

Create `app/interview/service.py`. Key structure (the gates are the point):

```python
"""Interview orchestration (S7.3).

This is a CANDIDATE-INITIATED entry point, so it carries the gates in the
service rather than trusting the route -- the S7.1/S7.2 lesson is that a gate
applied at one entry point and not the other is this codebase's recurring bug
shape. The gates, in order:

1. ONE LIVE SESSION. Concurrent sessions make attempt counting and the
   timing-based proxy signals meaningless.
2. OWNERSHIP. Every method resolves the session from (candidate_id, session_id)
   and raises LookupError for anything else -- another candidate's session is
   indistinguishable from a missing one.
3. CURRENT QUESTION. An answer must name the question it answers; a mismatch is
   refused rather than silently re-answering, so two racing clients cannot
   collapse into one turn.
4. LIVE SESSION ONLY. Expired (read-time) and completed sessions refuse answers.
5. SIZE, BEFORE DECODE. An oversize body is refused before base64 is expanded.

Nothing here can auto-reject: the output is an advisory assessment.
"""
```

```python
class SessionConflictError(Exception):
    """The session is not in a state that accepts this action (already live,
    already finished, expired, or the wrong question). Maps to 409."""


class AnswerTooLargeError(Exception):
    """The submitted answer body exceeds its cap. Checked BEFORE decoding."""
```

`InterviewService.__init__(self, store, candidates, ledger, report_store, *, verification,
llm, speech, settings=None)`.

`start`:
```python
    def start(self, candidate_id, *, domain_key="genai", at=None) -> InterviewSession:
        moment = as_utc(at) if at else _utcnow()
        if self._candidates.get_candidate(candidate_id) is None:
            raise LookupError(f"unknown candidate: {candidate_id}")
        live = self._store.live_session_for_candidate(candidate_id, at=moment)
        if live is not None:
            raise SessionConflictError(
                f"an interview is already in progress: {live.id}"
            )
        profile = self._candidates.latest_profile(candidate_id)
        report = self._latest_report(candidate_id)
        questions = build_question_plan(
            profile=profile,
            report=report,
            domain=get_domain(domain_key),
            limit=self._settings.interview_max_questions,
            minimum=self._settings.interview_min_questions,
        )
        assurance = self._verification.assurance_for_candidate(candidate_id, at=moment)
        return self._store.create_session(
            candidate_id=candidate_id, domain=domain_key,
            report_id=report.id if report else None, questions=questions,
            assurance_level=int(assurance.level), at=moment,
        )
```
`_latest_report`: `reports = self._report_store.for_candidate(candidate_id)` → the one with
the newest `created_at`, or `None`. Wrap in `try/except Exception` returning `None`: a
report-store hiccup must never block a candidate starting their own interview (the
`_corroborating_employers` precedent).

`answer` (async):
```python
    async def answer(self, candidate_id, session_id, *, question_id,
                     text=None, audio_b64=None, mime=None, at=None):
        moment = as_utc(at) if at else _utcnow()
        session = self._owned(candidate_id, session_id)
        status = effective_status(session.status, session.expires_at, at=moment)
        if status is not InterviewStatus.IN_PROGRESS:
            raise SessionConflictError(f"this interview is {status.value}")

        current = self._next_question(session)
        if current is None:
            raise SessionConflictError("every question has been answered")
        if question_id != current.id:
            raise SessionConflictError(
                f"answer question {current.id}; {question_id} is not the current one"
            )

        channel, transcript, digest, duration = await self._resolve_answer(
            text=text, audio_b64=audio_b64, mime=mime
        )
        asked_at = session.turns[-1].answered_at if session.turns else session.started_at
        score = score_turn(
            transcript=transcript,
            expected_signals=current.expected_signals,
            profile=self._candidates.latest_profile(candidate_id),
            settings=self._settings,
        )
        score = await adjust_with_llm(
            self._llm, question_text=current.text, transcript=transcript,
            expected_signals=current.expected_signals, base=score,
            settings=self._settings,
        )
        self._store.add_turn(
            session.id, question=current, channel=channel, transcript=transcript,
            word_count=word_count(transcript), audio_digest=digest,
            audio_duration_seconds=duration, score=score,
            asked_at=asked_at, answered_at=moment,
        )
        session = self._store.get_session(session.id)
        following = self._next_question(session)
        if following is None:
            session = await self._complete(session, at=moment)
        return session, following
```

`_resolve_answer`:
- text branch: refuse empty; `len(text) > settings.interview_max_answer_chars` →
  `AnswerTooLargeError`; return `(AnswerChannel.TEXT, text.strip(), None, None)`.
- audio branch: `len(audio_b64) > settings.interview_max_audio_b64_chars` →
  `AnswerTooLargeError` **before decoding**; `transcript = await self._speech.atranscribe(
  audio_b64=audio_b64, mime=mime or "audio/wav")` (let `SpeechUnavailable`/`SpeechFailed`
  propagate — the route maps them, and no turn is written because we have not called
  `add_turn` yet); `digest = hashlib.sha256(base64.b64decode(audio_b64, validate=True)).hexdigest()`
  — wrap the decode in `try/except binascii.Error` → `AnswerTooLargeError`? No: raise
  `ValueError("audio is not valid base64")`, which the route maps to 400.
- neither supplied → `ValueError("provide text or audio_b64")`.

`_complete(session, *, at)`: build `proxy = assess_proxy_risk(assurance=IdentityAssurance(
candidate_id=..., level=AssuranceLevel(session.assurance_level_at_start)), turns=session.turns,
settings=...)` — **use the stamped level, not a fresh read**, then
`assessment = aggregate(...)`, then `self._store.complete_session(session.id,
assessment=assessment, at=at)`.

`finish(candidate_id, session_id, *, at=None)`: same ownership + status gates, then
`_complete`. Refuse a completed/expired session with `SessionConflictError`.

`list_for_candidate`: map each session through a `_summary(session, *, at)` helper that
uses `effective_status` and pulls band/dimensions/proxy from `session.assessment` when
present.

`build_interview_service(...)` mirrors `build_verification_service`, taking
`candidates._session_factory`.

Then wire it. In `app/services/__init__.py`:
- `TYPE_CHECKING` import `from app.interview.service import InterviewService`
- dataclass fields: `speech: SpeechClient` and `interview: InterviewService`
- top-level `from app.services.speech import SpeechClient, build_speech`
- in `build_default_services`, after `verification = build_verification_service(...)`:
```python
    speech = build_speech(settings)
    interview = build_interview_service(
        settings, candidates=candidates, ledger=ledger, report_store=report_store,
        verification=verification, llm=llm, speech=speech,
    )
```
  (hoist `llm = build_llm(settings)` if it is currently constructed inline in the
  `Services(...)` call, so the interview service shares the one client.)

In `tests/conftest.py`, `make_services(...)` gains `speech=None, interview=None`
parameters; default `speech = speech or NullSpeech(settings)` and build a real
`InterviewService` over the in-memory report store.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_interview_service.py -q && pytest -q`
Expected: PASS, and the whole suite still green.

- [ ] **Step 5: Commit**

```bash
git add app/interview/service.py app/services/__init__.py tests/conftest.py tests/test_interview_service.py
git commit -m "feat(s73): interview state machine -- one live session, gates in the service"
```

---

### Task 11: Consent-gated org read

**Files:**
- Modify: `app/interview/store.py`, `app/interview/service.py`
- Test: `tests/test_interview_org.py`

**Interfaces:**
- Consumes: `ConsentPurpose.INTERVIEW_READ` (Task 2), `InterviewSummary` (Task 1).
- Produces: `InterviewStore.assessments_for_org(*, org_id, candidate_id, at) -> list[InterviewSummary]`
  and `InterviewService.assessments_for_org(...)` (same signature). Task 13 calls the
  service method from the org route.

- [ ] **Step 1: Write the failing test**

Create `tests/test_interview_org.py` asserting:

1. `test_no_grant_is_refused` — `ConsentError`.
2. `test_a_denied_read_is_still_audited` — after the refusal, the candidate's access log
   contains `interview.query` with `details["allowed"] is False`. **Surveillance must
   itself be observable** — this mirrors `claims_for_org`.
3. `test_an_interview_read_grant_allows_it_and_is_audited_allowed`.
4. `test_a_verification_read_grant_does_not_unlock_interviews` — grant
   `VERIFICATION_READ` only → still `ConsentError`. This is the whole reason the new
   purpose exists.
5. `test_revocation_closes_it_again`.
6. `test_only_completed_sessions_are_disclosed` — an in-progress session is absent from the
   org's list but present in the candidate's own.
7. `test_the_org_payload_carries_no_transcript` — dump every returned summary and assert
   no value anywhere in the JSON equals the transcript text.
8. `test_unknown_org_or_candidate_is_a_lookup_error`.

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_interview_org.py -q`
Expected: FAIL — `AttributeError: 'InterviewStore' object has no attribute 'assessments_for_org'`

- [ ] **Step 3: Implement**

Add to `InterviewStore`, copying `claims_for_org`'s shape exactly (read that method again
before writing this one):

```python
    def assessments_for_org(
        self, *, org_id: str, candidate_id: str, at: Optional[datetime] = None
    ) -> list[InterviewSummary]:
        """Query-time DPDP gate, mirroring VerificationStore.claims_for_org: an
        org sees interview assessments only under an active INTERVIEW_READ
        grant, and EVERY attempt -- allowed or denied -- is audited in the same
        transaction.

        Returns HEADERS only. `InterviewSummary` has no transcript field, so the
        candidate's own words cannot reach an org through this path even if a
        future caller forgets to filter.

        Only COMPLETED sessions are disclosed: an interrupted session is not an
        attempt at anything, and `attempts` is exactly the count returned here.
        """
```

Implementation notes: `LookupError` for unknown org/candidate; `self._ledger._grants_for(
session, candidate_id, ConsentPurpose.INTERVIEW_READ)` + `consent_logic.check_consent(...)`;
audit `action="interview.query"`, `entity_type="candidate"`,
`details={"allowed": False, "purpose": "interview_read"}` on the denied path (**commit
before raising `ConsentError`**); on the allowed path select the candidate's sessions with
`status == InterviewStatus.COMPLETED.value`, build summaries, audit
`details={"allowed": True, "consent_id": decision.grant_id, "sessions": len(summaries)}`,
commit, return.

Add the thin service passthrough:

```python
    def assessments_for_org(self, *, org_id, candidate_id, at=None) -> list[InterviewSummary]:
        return self._store.assessments_for_org(
            org_id=org_id, candidate_id=candidate_id, at=at
        )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_interview_org.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add app/interview/store.py app/interview/service.py tests/test_interview_org.py
git commit -m "feat(s73): consent-gated org read on INTERVIEW_READ, every attempt audited"
```

---

### Task 12: Candidate-plane routes

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_interview_api.py`

**Interfaces:**
- Consumes: `InterviewService` (Task 10).
- Produces: `POST /portal/interviews`, `GET /portal/interviews`,
  `GET /portal/interviews/{id}`, `POST /portal/interviews/{id}/answers`,
  `POST /portal/interviews/{id}/finish`, and the request models
  `StartInterviewRequest`, `SubmitAnswerRequest`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_interview_api.py` (use `fastapi.testclient.TestClient` over
`create_app(make_services(...))`, following `tests/test_verification_claim_api.py`) asserting:

1. `201/200` on start with a first question in the body; `422` when there is nothing to ask.
2. `409` on a second start while one is live.
3. `401` with no/bad `X-Candidate-Key` on every one of the five routes.
4. `404` for another candidate's session id (**not 403** — no probing).
5. `200` on a text answer; the response carries the scored turn count and the next question.
6. `409` on a wrong `question_id`.
7. `422` on an audio answer with no provider, with `speech_unavailable` in the detail.
8. `422` on an oversize text answer and on an oversize `audio_b64`.
9. `400` on an answer with neither `text` nor `audio_b64`.
10. Completing the last question returns the assessment with `advisory: true`.
11. `GET /portal/interviews/{id}` includes transcripts (**it is the candidate's own data**).
12. `GET /portal/interviews` returns summaries and **no transcript key anywhere** in the
    serialized body.

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_interview_api.py -q`
Expected: FAIL — 404s from FastAPI (routes do not exist yet).

- [ ] **Step 3: Implement**

In `app/api/routes.py`, add the imports and, after the S7.2 document block, the routes:

```python
class StartInterviewRequest(BaseModel):
    domain: str = "genai"


class SubmitAnswerRequest(BaseModel):
    """Exactly one of `text` / `audio_b64`. `question_id` is REQUIRED: an answer
    must name the question it answers, so two racing clients cannot collapse
    into one turn (409 on a mismatch)."""

    question_id: str
    text: str | None = None
    audio_b64: str | None = None
    mime: str | None = None
```

Handlers follow the S7.1/S7.2 pattern precisely — resolve `candidate_id` from
`Depends(require_candidate)`, never from the path — with this exception mapping:

| Exception | Status |
|---|---|
| `NothingToAskError` | 422 |
| `SessionConflictError` | 409 |
| `AnswerTooLargeError` | 422 |
| `SpeechUnavailable` | 422 (detail must contain `speech_unavailable`) |
| `SpeechFailed` | 422 (detail must contain `speech_failed`) |
| `ValueError` (no answer body / bad base64) | 400 |
| `LookupError` | 404 |

Register nothing new in `main.py` — `candidate_router` is already included.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_interview_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py tests/test_interview_api.py
git commit -m "feat(s73): candidate-plane interview routes"
```

---

### Task 13: Org-plane route + portal integration

**Files:**
- Modify: `app/api/routes.py`, `app/portal/schema.py`, `app/portal/service.py`,
  `app/portal/retention.py`, `tests/conftest.py`
- Test: `tests/test_interview_org_api.py`, `tests/test_portal_interviews.py`

**Interfaces:**
- Consumes: `InterviewService.assessments_for_org` (Task 11), `InterviewSummary` (Task 1).
- Produces: `GET /interview/candidates/{candidate_id}/assessments`,
  `MyData.interviews: list[InterviewSummary]`, retention window `interviews`.

- [ ] **Step 1: Write the failing test**

`tests/test_interview_org_api.py`: 403 without a grant → grant `interview_read` → 200 →
the payload contains `attempts` and a list of summaries → **no transcript text anywhere in
the body** → revoke → 403 → unknown candidate 404 → no `X-Org-Key` 401.

`tests/test_portal_interviews.py`: `GET /portal/me` carries `interviews` (summaries, no
transcripts) and a `retention` window with `data_class == "interviews"` and
`ttl_days == 1095`.

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_interview_org_api.py tests/test_portal_interviews.py -q`
Expected: FAIL — 404 from FastAPI, and `MyData` has no `interviews` field.

- [ ] **Step 3: Implement**

Org route:

```python
@org_router.get("/interview/candidates/{candidate_id}/assessments")
async def org_candidate_interviews(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> dict:
    """Consent-gated interview assessments (INTERVIEW_READ). Every attempt --
    allowed or denied -- is audited by the store. Headers only: bands,
    dimensions, proxy band, timestamps. NEVER the candidate's words."""
    try:
        summaries = _services(request).interview.assessments_for_org(
            org_id=org_id, candidate_id=candidate_id
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "attempts": len(summaries),
        "assessments": [s.model_dump(mode="json") for s in summaries],
    }
```

`app/portal/schema.py`: import `InterviewSummary` and add
`interviews: list[InterviewSummary] = Field(default_factory=list)` to `MyData`, with a
comment that it is summaries only — transcripts are reachable through
`GET /portal/interviews/{id}`, not bundled into the access view.

`app/portal/retention.py`: add `"interviews": "ret_interview_session_days"` to
`RETENTION_KNOBS`.

`app/portal/service.py`: accept an optional `interview=None` collaborator (mirroring
`verification=None`), populate `MyData.interviews` from
`self._interview.list_for_candidate(candidate_id)` when present, and add
`"interviews": min((s.started_at for s in interviews), default=None)` to the `oldest` map.
Update `build_portal_service` and both call sites (`app/services/__init__.py`,
`tests/conftest.py`) to pass it — **`PortalService` must be built after
`InterviewService`**.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_interview_org_api.py tests/test_portal_interviews.py tests/test_portal_service.py tests/test_portal_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py app/portal tests/test_interview_org_api.py tests/test_portal_interviews.py tests/conftest.py app/services/__init__.py
git commit -m "feat(s73): org-plane assessments read + portal my-data/retention"
```

---

### Task 14: Erasure, smoke, docs

**Files:**
- Create: `tests/test_interview_erasure.py`, `scripts/smoke_s73.py`, `INTERVIEWS.md`
- Modify: `README.md`, `MODELS.md`, `docs/ROADMAP.md`

**Interfaces:** none produced; this task closes the sprint.

- [ ] **Step 1: Write the failing erasure test**

`tests/test_interview_erasure.py`:
1. `test_deleting_a_candidate_removes_their_sessions_and_turns` — count rows in both
   tables directly via the session factory before and after
   `DELETE /portal/me`; assert both reach zero.
2. `test_the_org_read_404s_after_erasure` — with a live `interview_read` grant, the org
   read returns 404 once the candidate is gone (not an empty 200).
3. `test_no_new_erasure_path_was_added` — assert `CandidateStore.delete_candidate` (or
   whatever the existing hard-delete is named — check `app/candidates/store.py`) is
   unchanged in signature and that erasure works through it alone.

Run: `pytest tests/test_interview_erasure.py -q` → PASS is expected **without new code**,
because both tables CASCADE. If it fails, the migration's `ondelete` is wrong — fix the
migration, not the test.

- [ ] **Step 2: Write the smoke script**

`scripts/smoke_s73.py`, modelled directly on `scripts/smoke_s72.py` (uvicorn on a free
port, `requests`, exit non-zero on any failure, key-less). Checks, in order:

1. create candidate (POST /candidates with a fixture resume) → admin mints a candidate key
2. `GET /portal/interviews` → empty
3. `POST /portal/interviews` → 200, a first question is present
4. audio answer → **422 containing `speech_unavailable`**
5. text answer → 200, scored, next question returned
6. wrong `question_id` → 409
7. oversize text answer → 422
8. answer the remaining questions → session completes, assessment present with
   `advisory: true` and a band
9. proxy risk contains `identity_assurance_none`, band is not above `elevated`
10. `POST /portal/verifications {"method": "self_attested"}` → level 1; start a **new**
    interview → `assurance_level_at_start == 1`
11. org read → 403 → grant `interview_read` → 200 → **assert the transcript string appears
    nowhere in the org response body** → revoke → 403
12. `GET /portal/me` → `interviews` present, retention window `interviews` present
13. `GET /portal/access-log` → contains `interview.query` with the org name resolved
14. `DELETE /portal/me` → org read → 404

Run: `python scripts/smoke_s73.py`
Expected: `14/14 OK`, exit 0.

- [ ] **Step 3: Write `INTERVIEWS.md`**

Peer of `VERIFICATION.md`. Sections: why probes are the question source · the three
decisions from spec §0 · the speech seam and what "no key" means · the rubric and why every
axis is neutral-when-unknown · proxy signals and the explicit no-biometrics stance · the
data model and why the assessment is stored when the other roll-ups are not · consent and
the new purpose · API · config · non-goals · follow-ups. Add a line to `README.md`'s doc
index.

- [ ] **Step 4: Full verification**

```bash
pytest -q
python -m pyflakes app/interview app/services/speech.py scripts/smoke_s73.py
python scripts/smoke_s73.py
```
Expected: all green; record the exact test count for the ROADMAP.

- [ ] **Step 5: Update `MODELS.md` and `docs/ROADMAP.md`, then commit**

`MODELS.md`: move `model_scoring` / `speech_provider` / `asr_model` out of "Future slots"
into the active table; note `tts_model` stays inert and why; append a verification-log line
for the live ASR ping **if** one was run with a real key (and only then).

`docs/ROADMAP.md`: status board `S7.3 [x]`, PI-7 `[COMPLETE]`, a new "Current state" entry,
"Next action" → PI-8 shaping, and a session-log entry.

```bash
git add tests/test_interview_erasure.py scripts/smoke_s73.py INTERVIEWS.md README.md MODELS.md docs/ROADMAP.md
git commit -m "test(s73): erasure + uvicorn smoke; INTERVIEWS/MODELS/ROADMAP docs"
```

---

## Self-Review

**Spec coverage** — every section maps to a task: §0.1 transcript/audio → Tasks 8, 10, 12;
§0.2 planes/consent → Tasks 2, 11, 13; §0.3 ASR seam → Task 7; §3 question plan → Task 3;
§4 speech → Task 7; §5 scoring → Tasks 4, 5; §6 proxy → Task 6; §7 DPDP → Tasks 8, 11, 13,
14; §8 data model → Task 8; §9 state machine → Task 10; §10 API → Tasks 12, 13; §11 config
→ Task 2; §12 testing/smoke → every task + Task 14; §13 non-goals → nothing built for them,
recorded in `INTERVIEWS.md` (Task 14); §14 follow-ups → Task 14 docs.

**Known deviations from the spec, decided while planning:**
- `question_text` is `String(512)`, not `Text`, so the "only one unbounded column" test has
  exactly one exception (the transcript). The spec's §8 table said Text; the narrower type
  is strictly better and the test enforces it.
- `assess_proxy_risk` is clock-free (rates come from the turns' own timestamps); the spec
  was corrected to match before this plan was written.
- Three band-threshold knobs (`interview_deep/solid/emerging_threshold`) were added to spec
  §11 during planning, matching the `ai_*`/`fr_*`/`rep_*` precedent.

**Type consistency** — `build_question_plan`, `score_turn`, `adjust_with_llm`,
`assess_proxy_risk`, `aggregate`, `band_for`, `effective_status`, `atranscribe`,
`assessments_for_org` are each defined once and called with the same keyword names
everywhere. `InterviewSummary` is the single org-facing projection and appears in Tasks 1,
10, 11, 13.

**Risk to watch during execution** — Task 10 is the largest task and holds every gate. If
it grows past a comfortable review, split it: 10a (`start` + ownership + one-live-session),
10b (`answer` + `_resolve_answer` + completion). Do not merge Task 10 without tests 4, 7,
10, 11, 13 and 14 from its list passing, because those are the S7.1/S7.2 escalation shapes
in this sprint's clothing.
