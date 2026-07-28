# S5.3 — Thin Employer Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three org-plane, read-only JSON endpoints that compose the existing S5.1/S5.2/PI-3 org-plane data into employer-ready views (pipeline overview, per-requisition board, per-candidate consent-gated card).

**Architecture:** A new pure composition package `app/dashboard/` (contracts + a `DashboardService` that calls the already-built `JobStore`, `CompService`, and `LedgerStore`). It owns no tables, holds no state, adds no new audit path — the card reuses the ledger's already-audited reads and catches `ConsentError` per section. Wired into `Services` with the S5.1/S5.2 cycle-safe pattern; three routes on `org_router`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy (unchanged), pytest. No new dependency, no migration, no LLM.

## Global Constraints

- TDD, fully offline tests (NullLLM/fakes via `tests/conftest.py`); `pytest -q` green before merge.
- Advisory only — every response carries `advisory=True`; nothing auto-rejects.
- DPDP: reuse the `ledger_read` consent purpose (no new taxonomy); audit by reuse only.
- No candidate PII on any read-model — `candidate_id` + advisory signals only.
- No platform-internal depth `Report` exposed on the org plane.
- Config knobs live in `config.yaml` + `app/core/config.py`, `DEE_*`-overridable.
- Commit messages use the `…(s53): …` convention; **no `Co-Authored-By` trailer**.
- Branch: `s53-employer-dashboard` (already created; the design spec is committed on it).
- Spec of record: `docs/superpowers/specs/2026-07-28-s53-employer-dashboard-design.md`.

---

### Task 1: Config knob `dash_board_top_n`

**Files:**
- Modify: `app/core/config.py` (after the comp block ending at the `comp_bands_path` line, ~259)
- Modify: `config.yaml` (after the comp section ending ~178)
- Test: `tests/test_config_dashboard.py`

**Interfaces:**
- Consumes: `app.core.config.Settings`
- Produces: `Settings.dash_board_top_n: int` (default `20`, `ge=1`) — consumed by `DashboardService.board` in Task 4.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_dashboard.py`:

```python
import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def test_dash_board_top_n_default():
    assert _settings().dash_board_top_n == 20


def test_dash_board_top_n_env_override(monkeypatch):
    monkeypatch.setenv("DEE_DASH_BOARD_TOP_N", "5")
    assert Settings(_env_file=None, openrouter_api_key="").dash_board_top_n == 5


def test_dash_board_top_n_rejects_zero():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, openrouter_api_key="", dash_board_top_n=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_dashboard.py -v`
Expected: FAIL — `AttributeError`/`ValidationError` (no `dash_board_top_n` field yet).

- [ ] **Step 3: Add the field to `app/core/config.py`**

Immediately after the `comp_bands_path` line (~259), add:

```python

    # --- Employer dashboard (PI-5, S5.3): read-only composition over jobs/comp/ledger.
    # Max ranked candidates returned per GET /jobs/{id}/board (passed as run_match limit).
    dash_board_top_n: int = Field(default=20, ge=1)
```

- [ ] **Step 4: Mirror the knob in `config.yaml`**

After the comp section (after the `# comp_bands_path:` comment line ~178), add:

```yaml

# --- Employer dashboard (PI-5) - S5.3 read-only composition over jobs/comp/ledger --
dash_board_top_n: 20             # max ranked candidates returned per GET /jobs/{id}/board
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_config_dashboard.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py config.yaml tests/test_config_dashboard.py
git commit -m "feat(s53): dash_board_top_n config knob"
```

---

### Task 2: Dashboard contracts (`app/dashboard/schema.py`)

**Files:**
- Create: `app/dashboard/__init__.py`
- Create: `app/dashboard/schema.py`
- Test: `tests/test_dashboard_schema.py`

**Interfaces:**
- Consumes: `app.comp.schema.CompBenchmark`; `app.ledger.schema.{CodingRoundResult, InterviewRecord, ReputationAssessment}`; `app.matching.schema.{JobRequisition, MatchResult, RequisitionStatus}`.
- Produces (used by Tasks 3–6):
  - `SectionStatus` StrEnum: `AVAILABLE="available"`, `CONSENT_REQUIRED="consent_required"`, `NO_DATA="no_data"`.
  - `RequisitionSummary(id:str, title:str, status:RequisitionStatus, must_have_skill_count:int, has_comp_band:bool, has_skill_coverage_gate:bool, created_at:datetime, updated_at:datetime)`
  - `DashboardOverview(total_requisitions:int, by_status:dict[str,int], requisitions:tuple[RequisitionSummary,...]=(), advisory:bool=True)`
  - `RequisitionBoard(requisition:JobRequisition, comp:CompBenchmark, match:MatchResult, advisory:bool=True)`
  - `ReputationSection(status:SectionStatus, data:Optional[ReputationAssessment]=None)`
  - `CodingRoundsSection(status:SectionStatus, data:tuple[CodingRoundResult,...]=())`
  - `RecordsSection(status:SectionStatus, data:tuple[InterviewRecord,...]=())`
  - `CandidateCard(candidate_id:str, reputation:ReputationSection, coding_rounds:CodingRoundsSection, records:RecordsSection, advisory:bool=True)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_schema.py`:

```python
from app.dashboard.schema import (
    CandidateCard, CodingRoundsSection, DashboardOverview, RecordsSection,
    ReputationSection, RequisitionSummary, SectionStatus,
)
from app.matching.schema import RequisitionStatus


def test_section_status_values():
    assert SectionStatus.AVAILABLE == "available"
    assert SectionStatus.CONSENT_REQUIRED == "consent_required"
    assert SectionStatus.NO_DATA == "no_data"


def test_overview_defaults_and_shape():
    ov = DashboardOverview(total_requisitions=0, by_status={})
    assert ov.advisory is True
    assert ov.requisitions == ()


def test_requisition_summary_flags():
    from datetime import datetime, timezone
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    rs = RequisitionSummary(
        id="r1", title="BE", status=RequisitionStatus.OPEN, must_have_skill_count=2,
        has_comp_band=True, has_skill_coverage_gate=False, created_at=now, updated_at=now,
    )
    assert rs.has_comp_band is True and rs.has_skill_coverage_gate is False


def test_card_sections_default_empty():
    card = CandidateCard(
        candidate_id="c1",
        reputation=ReputationSection(status=SectionStatus.CONSENT_REQUIRED),
        coding_rounds=CodingRoundsSection(status=SectionStatus.NO_DATA),
        records=RecordsSection(status=SectionStatus.NO_DATA),
    )
    assert card.advisory is True
    assert card.reputation.data is None
    assert card.coding_rounds.data == ()
    assert card.records.data == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.dashboard'`.

- [ ] **Step 3: Create `app/dashboard/__init__.py`**

```python
"""Employer dashboard read-models (PI-5 / S5.3).

Pure composition over JobStore + CompService + LedgerStore. Owns no tables,
holds no state, adds no new audit path. Advisory only.
"""
```

- [ ] **Step 4: Create `app/dashboard/schema.py`**

```python
"""Employer dashboard read-model contracts (S5.3). Pure, serializable. No I/O."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel

from app.comp.schema import CompBenchmark
from app.ledger.schema import CodingRoundResult, InterviewRecord, ReputationAssessment
from app.matching.schema import JobRequisition, MatchResult, RequisitionStatus


class SectionStatus(StrEnum):
    AVAILABLE = "available"            # consent granted; payload present
    CONSENT_REQUIRED = "consent_required"  # the reused store read raised ConsentError
    NO_DATA = "no_data"               # consent granted but the source yielded nothing


class RequisitionSummary(BaseModel):
    """One row on the pipeline overview — flags derivable from the req itself."""

    id: str
    title: str
    status: RequisitionStatus
    must_have_skill_count: int
    has_comp_band: bool
    has_skill_coverage_gate: bool
    created_at: datetime
    updated_at: datetime


class DashboardOverview(BaseModel):
    total_requisitions: int
    by_status: dict[str, int]                       # RequisitionStatus value -> count
    requisitions: tuple[RequisitionSummary, ...] = ()
    advisory: bool = True


class RequisitionBoard(BaseModel):
    requisition: JobRequisition
    comp: CompBenchmark
    match: MatchResult
    advisory: bool = True


class ReputationSection(BaseModel):
    status: SectionStatus
    data: Optional[ReputationAssessment] = None


class CodingRoundsSection(BaseModel):
    status: SectionStatus
    data: tuple[CodingRoundResult, ...] = ()


class RecordsSection(BaseModel):
    status: SectionStatus
    data: tuple[InterviewRecord, ...] = ()


class CandidateCard(BaseModel):
    """Per-candidate drill-in, keyed by candidate_id (no PII). Each section is
    independently consent-gated + audited via the reused store reads."""

    candidate_id: str
    reputation: ReputationSection
    coding_rounds: CodingRoundsSection
    records: RecordsSection
    advisory: bool = True
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_dashboard_schema.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add app/dashboard/__init__.py app/dashboard/schema.py tests/test_dashboard_schema.py
git commit -m "feat(s53): dashboard read-model contracts"
```

---

### Task 3: `DashboardService.overview` + Services wiring

This task adds the service class (with `overview`), wires `Services.dashboard` in
both the production builder and the test builder, so later tasks can call
`services.dashboard.*`.

**Files:**
- Create: `app/dashboard/service.py`
- Modify: `app/services/__init__.py` (dataclass field ~27-40, `TYPE_CHECKING` block ~21-24, `build_default_services` ~42-62)
- Modify: `tests/conftest.py` (`make_services` signature ~102-113 and body ~121-142)
- Test: `tests/test_dashboard_service.py`

**Interfaces:**
- Consumes: `app.matching.store.{JobStore, build_job_store}`; `app.comp.service.{CompService, build_comp_service}`; `app.ledger.store.{LedgerStore, ConsentError, build_ledger_store}`; `Settings.dash_board_top_n`; Task 2 contracts.
- Produces:
  - `DashboardService(jobs:JobStore, comp:CompService, ledger:LedgerStore, *, settings=None)` with `.overview(org_id:str) -> DashboardOverview`, `.board(org_id, req_id) -> Optional[RequisitionBoard]` (Task 4), `.card(org_id, candidate_id) -> CandidateCard` (Task 5).
  - `build_dashboard_service(settings=None) -> DashboardService`
  - `Services.dashboard: DashboardService`
  - `make_services(..., dashboard=None)` test builder wires it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_service.py`:

```python
from datetime import datetime, timezone

from app.candidates.schema import (
    CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult, SkillItem,
)
from app.matching.schema import JobRequisitionInput, RequisitionStatus
from app.dashboard.schema import SectionStatus

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _org(services, name="Acme"):
    return services.ledger.create_organization(name).id


def test_overview_counts_and_flags(services):
    org_id = _org(services)
    services.jobs.create_requisition(org_id, JobRequisitionInput(
        title="Open BE", must_have_skills=("python", "django"),
        min_skill_coverage=0.5, comp_band={"ctc_min": 800000, "ctc_max": 900000},
    ))
    services.jobs.create_requisition(org_id, JobRequisitionInput(
        title="Closed FE", status=RequisitionStatus.CLOSED, must_have_skills=("react",),
    ))

    ov = services.dashboard.overview(org_id)
    assert ov.total_requisitions == 2
    assert ov.by_status == {"open": 1, "closed": 1}
    assert ov.advisory is True
    open_row = next(r for r in ov.requisitions if r.title == "Open BE")
    assert open_row.must_have_skill_count == 2
    assert open_row.has_comp_band is True
    assert open_row.has_skill_coverage_gate is True
    closed_row = next(r for r in ov.requisitions if r.title == "Closed FE")
    assert closed_row.has_comp_band is False
    assert closed_row.has_skill_coverage_gate is False


def test_overview_scoped_to_org(services):
    a = _org(services, "A")
    b = _org(services, "B")
    services.jobs.create_requisition(a, JobRequisitionInput(
        title="A-req", must_have_skills=("python",)))
    assert services.dashboard.overview(b).total_requisitions == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_service.py -v`
Expected: FAIL — `AttributeError: 'Services' object has no attribute 'dashboard'`.

- [ ] **Step 3: Create `app/dashboard/service.py`**

```python
"""Employer dashboard service (S5.3). Pure composition over JobStore +
CompService + LedgerStore. Owns no tables and holds no state; each method
assembles an existing, already-audited read into a render-ready contract.
The card catches ConsentError per section (LookupError propagates). Advisory."""

from __future__ import annotations

from typing import Optional

from app.comp.service import CompService, build_comp_service
from app.core.config import Settings, get_settings
from app.dashboard.schema import (
    CandidateCard, CodingRoundsSection, DashboardOverview, RecordsSection,
    ReputationSection, RequisitionBoard, RequisitionSummary, SectionStatus,
)
from app.ledger.store import ConsentError, LedgerStore, build_ledger_store
from app.matching.store import JobStore, build_job_store


class DashboardService:
    def __init__(
        self,
        jobs: JobStore,
        comp: CompService,
        ledger: LedgerStore,
        *,
        settings: Optional[Settings] = None,
    ) -> None:
        self._jobs = jobs
        self._comp = comp
        self._ledger = ledger
        self._settings = settings or get_settings()

    def overview(self, org_id: str) -> DashboardOverview:
        reqs = self._jobs.list_requisitions(org_id)
        by_status: dict[str, int] = {}
        summaries: list[RequisitionSummary] = []
        for r in reqs:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
            summaries.append(
                RequisitionSummary(
                    id=r.id,
                    title=r.title,
                    status=r.status,
                    must_have_skill_count=len(r.must_have_skills),
                    has_comp_band=r.comp_band is not None,
                    has_skill_coverage_gate=r.min_skill_coverage is not None,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
            )
        return DashboardOverview(
            total_requisitions=len(reqs),
            by_status=by_status,
            requisitions=tuple(summaries),
        )


def build_dashboard_service(settings: Optional[Settings] = None) -> DashboardService:
    settings = settings or get_settings()
    return DashboardService(
        build_job_store(settings),
        build_comp_service(settings),
        build_ledger_store(settings),
        settings=settings,
    )
```

- [ ] **Step 4: Wire `Services.dashboard` in `app/services/__init__.py`**

In the `TYPE_CHECKING` block (~21-24) add:

```python
    from app.dashboard.service import DashboardService
```

Add a field to the `Services` dataclass (after `comp: CompService`):

```python
    dashboard: DashboardService
```

In `build_default_services`, add to the function-local import group:

```python
    from app.dashboard.service import build_dashboard_service
```

and add to the `Services(...)` constructor (after `comp=build_comp_service(settings),`):

```python
        dashboard=build_dashboard_service(settings),
```

- [ ] **Step 5: Wire the test builder in `tests/conftest.py`**

Add `dashboard=None` to the `make_services` keyword params (after `comp=None,`):

```python
    dashboard=None,
```

In the body, after the `comp` block (after the `comp = CompService(ledger, settings=settings)` lines) and before `return Services(`:

```python
    if dashboard is None:
        from app.dashboard.service import DashboardService
        dashboard = DashboardService(jobs, comp, ledger, settings=settings)
```

Add `dashboard=dashboard,` to the returned `Services(...)` (after `comp=comp,`).

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_dashboard_service.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Run the full suite to confirm nothing else broke from the dataclass change**

Run: `pytest -q`
Expected: PASS (all prior tests + the new ones; the new required `dashboard` field is supplied by both `Services` constructors).

- [ ] **Step 8: Commit**

```bash
git add app/dashboard/service.py app/services/__init__.py tests/conftest.py tests/test_dashboard_service.py
git commit -m "feat(s53): DashboardService.overview + Services wiring"
```

---

### Task 4: `DashboardService.board`

**Files:**
- Modify: `app/dashboard/service.py` (add the `board` method to the class)
- Test: `tests/test_dashboard_service.py` (add board cases)

**Interfaces:**
- Consumes: `JobStore.get_requisition`, `JobStore.run_match`, `CompService.benchmark`, `Settings.dash_board_top_n`, `RequisitionBoard`.
- Produces: `DashboardService.board(org_id:str, req_id:str) -> Optional[RequisitionBoard]` — `None` iff the requisition is not owned by `org_id`. When owned, returns a fully-composed board whose `match.pool_size` may be `0` (the endpoint, Task 6, turns that into 422).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dashboard_service.py`:

```python
def test_board_cross_org_is_none(services):
    a = _org(services, "A")
    b = _org(services, "B")
    req = services.jobs.create_requisition(a, JobRequisitionInput(
        title="A-req", must_have_skills=("python",)))
    assert services.dashboard.board(b, req.id) is None


def test_board_composes_req_comp_and_empty_match(services):
    org_id = _org(services)
    req = services.jobs.create_requisition(org_id, JobRequisitionInput(
        title="Senior Backend Engineer", must_have_skills=("python",),
        min_years_experience=7, location_tiers=("metro",),
        comp_band={"ctc_min": 800000, "ctc_max": 900000},
    ))
    board = services.dashboard.board(org_id, req.id)
    assert board is not None
    assert board.requisition.id == req.id
    assert board.comp.advisory is True                 # comp benchmark composed
    assert board.match.pool_size == 0                  # nothing materialized -> empty
    assert board.match.ranked == ()
    assert board.advisory is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_service.py -k board -v`
Expected: FAIL — `AttributeError: 'DashboardService' object has no attribute 'board'`.

- [ ] **Step 3: Add the `board` method**

In `app/dashboard/service.py`, add to `DashboardService` (after `overview`):

```python
    def board(self, org_id: str, req_id: str) -> Optional[RequisitionBoard]:
        req = self._jobs.get_requisition(org_id, req_id)
        if req is None:
            return None
        comp = self._comp.benchmark(req, org_id=org_id)
        match = self._jobs.run_match(
            org_id, req_id, as_of=None, limit=self._settings.dash_board_top_n
        )
        if match is None:  # req is owned, so run_match found it — defensive only
            return None
        return RequisitionBoard(requisition=req, comp=comp, match=match)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_service.py -k board -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/dashboard/service.py tests/test_dashboard_service.py
git commit -m "feat(s53): DashboardService.board (req + comp + match)"
```

---

### Task 5: `DashboardService.card` (per-section consent + status)

**Files:**
- Modify: `app/dashboard/service.py` (add `card` + three private section helpers)
- Test: `tests/test_dashboard_service.py` (add card cases)

**Interfaces:**
- Consumes: `LedgerStore.reputation_for_org`, `LedgerStore.query_coding_rounds_for_org`, `LedgerStore.query_records_for_org` (each raises `ConsentError` without an active `ledger_read` grant, and `LookupError` for unknown org/candidate); the Task 2 card contracts.
- Produces: `DashboardService.card(org_id:str, candidate_id:str) -> CandidateCard`. Catches `ConsentError` → that section is `CONSENT_REQUIRED`. **Does not** catch `LookupError` — it propagates (the endpoint maps it to 404 for an unknown candidate). Section status when consent is granted: `NO_DATA` when the source is empty (`reputation.total_observations == 0`, or empty coding-round/record lists), else `AVAILABLE`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dashboard_service.py`:

```python
from datetime import timedelta

from app.ledger.schema import ConsentPurpose, InterviewOutcome, InterviewStage


def _candidate(services, name="Ann", email="ann@x.io"):
    saved = services.candidates.ingest(
        ExtractionResult(
            profile=CandidateProfile(
                full_name=ExtractedStr(value=name),
                contact=ContactInfo(email=ExtractedStr(value=email)),
                skills=[SkillItem(name="python", canonical="python")],
            ),
            method="heuristic",
        ),
        resume_text=email,
    )
    return saved.candidate_id


def test_card_all_sections_consent_required_without_grant(services):
    org_id = _org(services)
    cand_id = _candidate(services)
    card = services.dashboard.card(org_id, cand_id)
    assert card.candidate_id == cand_id
    assert card.reputation.status == SectionStatus.CONSENT_REQUIRED
    assert card.coding_rounds.status == SectionStatus.CONSENT_REQUIRED
    assert card.records.status == SectionStatus.CONSENT_REQUIRED
    assert card.reputation.data is None


def test_card_sections_available_after_read_grant(services):
    org_id = _org(services)
    cand_id = _candidate(services)
    # A submitted interview record needs a write grant; reading needs a read grant.
    services.ledger.grant_consent(
        candidate_id=cand_id, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org_id,
        expires_at=NOW + timedelta(days=90))
    services.ledger.submit_interview_record(
        org_id=org_id, candidate_id=cand_id, stage=InterviewStage.TECH,
        outcome=InterviewOutcome.ADVANCED, interviewed_at=NOW)
    services.ledger.grant_consent(
        candidate_id=cand_id, purpose=ConsentPurpose.LEDGER_READ, org_id=org_id,
        expires_at=NOW + timedelta(days=90))

    card = services.dashboard.card(org_id, cand_id)
    assert card.records.status == SectionStatus.AVAILABLE
    assert len(card.records.data) == 1
    # No coding rounds submitted -> granted but empty -> no_data.
    assert card.coding_rounds.status == SectionStatus.NO_DATA
    # Reputation reads the one record; with consent it is AVAILABLE (has observations).
    assert card.reputation.status == SectionStatus.AVAILABLE


def test_card_unknown_candidate_raises_lookuperror(services):
    import pytest
    org_id = _org(services)
    with pytest.raises(LookupError):
        services.dashboard.card(org_id, "no-such-candidate")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_service.py -k card -v`
Expected: FAIL — `AttributeError: 'DashboardService' object has no attribute 'card'`.

- [ ] **Step 3: Add `card` + section helpers**

In `app/dashboard/service.py`, add to `DashboardService` (after `board`):

```python
    def card(self, org_id: str, candidate_id: str) -> CandidateCard:
        # Section order matters only for the unknown-candidate case: the first
        # reused read raises LookupError, which we let propagate (-> 404). For a
        # known candidate each section is independently consent-gated + audited.
        return CandidateCard(
            candidate_id=candidate_id,
            reputation=self._reputation_section(org_id, candidate_id),
            coding_rounds=self._coding_rounds_section(org_id, candidate_id),
            records=self._records_section(org_id, candidate_id),
        )

    def _reputation_section(self, org_id: str, candidate_id: str) -> ReputationSection:
        try:
            rep = self._ledger.reputation_for_org(org_id=org_id, candidate_id=candidate_id)
        except ConsentError:
            return ReputationSection(status=SectionStatus.CONSENT_REQUIRED, data=None)
        status = (
            SectionStatus.NO_DATA if rep.total_observations == 0 else SectionStatus.AVAILABLE
        )
        return ReputationSection(status=status, data=rep)

    def _coding_rounds_section(self, org_id: str, candidate_id: str) -> CodingRoundsSection:
        try:
            rounds = self._ledger.query_coding_rounds_for_org(
                org_id=org_id, candidate_id=candidate_id
            )
        except ConsentError:
            return CodingRoundsSection(status=SectionStatus.CONSENT_REQUIRED, data=())
        status = SectionStatus.AVAILABLE if rounds else SectionStatus.NO_DATA
        return CodingRoundsSection(status=status, data=tuple(rounds))

    def _records_section(self, org_id: str, candidate_id: str) -> RecordsSection:
        try:
            records = self._ledger.query_records_for_org(
                org_id=org_id, candidate_id=candidate_id
            )
        except ConsentError:
            return RecordsSection(status=SectionStatus.CONSENT_REQUIRED, data=())
        status = SectionStatus.AVAILABLE if records else SectionStatus.NO_DATA
        return RecordsSection(status=status, data=tuple(records))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_service.py -k card -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the whole service test file**

Run: `pytest tests/test_dashboard_service.py -v`
Expected: PASS (all overview + board + card cases).

- [ ] **Step 6: Commit**

```bash
git add app/dashboard/service.py tests/test_dashboard_service.py
git commit -m "feat(s53): DashboardService.card (per-section consent + status)"
```

---

### Task 6: Org-plane endpoints + root catalog

**Files:**
- Modify: `app/api/routes.py` (import + three handlers on `org_router`)
- Modify: `app/main.py` (root endpoint catalog list ~100-128)
- Test: `tests/test_dashboard_api.py`

**Interfaces:**
- Consumes: `Services.dashboard`; `require_org`; Task 2 contracts.
- Produces HTTP routes on `org_router` (all `X-Org-Key`):
  - `GET /dashboard/overview` -> `DashboardOverview`
  - `GET /jobs/{req_id}/board` -> `RequisitionBoard` (404 cross-org / 422 empty pool)
  - `GET /candidates/{candidate_id}/card` -> `CandidateCard` (404 unknown candidate)

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_api.py`:

```python
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.candidates.schema import (
    CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult, SkillItem,
)
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
from app.ledger.schema import ConsentPurpose
from app.main import create_app
from tests.conftest import set_extraction_created_at

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)
AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c


def _org_key(services, name="Acme"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _candidate(services, name="Ann", email="ann@x.io", skills=("python",)):
    saved = services.candidates.ingest(
        ExtractionResult(
            profile=CandidateProfile(
                full_name=ExtractedStr(value=name),
                contact=ContactInfo(email=ExtractedStr(value=email)),
                skills=[SkillItem(name=s, canonical=s) for s in skills],
            ),
            method="heuristic",
        ),
        resume_text=email,
    )
    return saved.candidate_id


def _materialize(services, candidate_id):
    registry = get_feature_registry()
    set_extraction_created_at(services.candidates, candidate_id, AS_OF.replace(tzinfo=None))
    mv = materialize_candidate(
        candidate_id, view=default_view(registry), registry=registry, as_of=AS_OF,
        candidate_store=services.candidates, report_store=services.report_store,
        ledger_store=services.ledger,
    )
    services.features.upsert_vector(mv)


def test_all_dashboard_routes_require_org_key(services):
    with _client(services) as c:
        assert c.get("/dashboard/overview").status_code == 401
        assert c.get("/jobs/x/board").status_code == 401
        assert c.get("/candidates/x/card").status_code == 401


def test_overview_endpoint(services):
    _, key = _org_key(services)
    hdr = {"X-Org-Key": key}
    with _client(services) as c:
        c.post("/jobs", headers=hdr, json={"title": "BE", "must_have_skills": ["python"]})
        r = c.get("/dashboard/overview", headers=hdr)
        assert r.status_code == 200
        body = r.json()
        assert body["total_requisitions"] == 1
        assert body["by_status"] == {"open": 1}
        assert body["advisory"] is True


def test_board_404_cross_org_and_422_empty_pool(services):
    _, key_a = _org_key(services, "A")
    org_b = services.ledger.create_organization("B")
    key_b = services.ledger.issue_api_key(org_b.id)
    with _client(services) as c:
        req = c.post("/jobs", headers={"X-Org-Key": key_a},
                     json={"title": "BE", "must_have_skills": ["python"]}).json()
        # cross-org -> 404
        assert c.get(f"/jobs/{req['id']}/board", headers={"X-Org-Key": key_b}).status_code == 404
        # owned but nothing materialized -> 422
        assert c.get(f"/jobs/{req['id']}/board", headers={"X-Org-Key": key_a}).status_code == 422


def test_board_200_with_materialized_pool(services):
    org_id, key = _org_key(services)
    hdr = {"X-Org-Key": key}
    _materialize(services, _candidate(services, "Strong", "s@x.io", ("python", "django")))
    with _client(services) as c:
        req = c.post("/jobs", headers=hdr,
                     json={"title": "BE", "must_have_skills": ["python", "django"],
                           "comp_band": {"ctc_min": 800000, "ctc_max": 900000}}).json()
        r = c.get(f"/jobs/{req['id']}/board", headers=hdr)
        assert r.status_code == 200
        body = r.json()
        assert body["requisition"]["id"] == req["id"]
        assert body["comp"]["advisory"] is True
        assert body["match"]["pool_size"] == 1
        assert body["match"]["ranked"][0]["candidate_id"]


def test_card_consent_flow(services):
    org_id, key = _org_key(services)
    hdr = {"X-Org-Key": key}
    cand_id = _candidate(services)
    with _client(services) as c:
        # unknown candidate -> 404
        assert c.get("/candidates/nope/card", headers=hdr).status_code == 404
        # known candidate, no grant -> 200, all sections consent_required
        r0 = c.get(f"/candidates/{cand_id}/card", headers=hdr)
        assert r0.status_code == 200
        b0 = r0.json()
        assert b0["reputation"]["status"] == "consent_required"
        assert b0["records"]["status"] == "consent_required"
        # grant read -> sections resolve (no data submitted -> no_data)
        services.ledger.grant_consent(
            candidate_id=cand_id, purpose=ConsentPurpose.LEDGER_READ, org_id=org_id,
            expires_at=NOW + timedelta(days=90))
        b1 = c.get(f"/candidates/{cand_id}/card", headers=hdr).json()
        assert b1["records"]["status"] == "no_data"
        assert b1["coding_rounds"]["status"] == "no_data"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_api.py -v`
Expected: FAIL — 404s become 401/404 mismatches / routes missing (the dashboard routes don't exist yet).

- [ ] **Step 3: Add the import in `app/api/routes.py`**

Near the other schema imports (after the `from app.comp.schema import (...)` block ~27-29), add:

```python
from app.dashboard.schema import CandidateCard, DashboardOverview, RequisitionBoard
```

- [ ] **Step 4: Add the three handlers to `app/api/routes.py`**

After the comp block (after the `job_comp` handler ending ~731), add:

```python
# ── Employer dashboard (S5.3) ────────────────────────────────────────────────
# Org plane (X-Org-Key). Read-only composition over jobs/comp/ledger. Advisory;
# no new state, no new consent purpose, no new audit path (the card reuses the
# ledger's already-audited reads and degrades per section on missing consent).


@org_router.get("/dashboard/overview", response_model=DashboardOverview)
async def dashboard_overview(
    request: Request, org_id: str = Depends(require_org)
) -> DashboardOverview:
    return _services(request).dashboard.overview(org_id)


@org_router.get("/jobs/{req_id}/board", response_model=RequisitionBoard)
async def job_board(
    req_id: str, request: Request, org_id: str = Depends(require_org)
) -> RequisitionBoard:
    board = _services(request).dashboard.board(org_id, req_id)
    if board is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    if board.match.pool_size == 0:
        raise HTTPException(status_code=422, detail="no materialized candidates to match")
    return board


@org_router.get("/candidates/{candidate_id}/card", response_model=CandidateCard)
async def candidate_card(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> CandidateCard:
    try:
        return _services(request).dashboard.card(org_id, candidate_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 5: Add the routes to the root catalog in `app/main.py`**

In the `endpoints` list (~100-128), after `"POST /talent/search",` add:

```python
                "GET /dashboard/overview",
                "GET /jobs/{id}/board",
                "GET /candidates/{id}/card",
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_dashboard_api.py -v`
Expected: PASS (5 tests).

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS (all green).

- [ ] **Step 8: Commit**

```bash
git add app/api/routes.py app/main.py tests/test_dashboard_api.py
git commit -m "feat(s53): org-plane dashboard endpoints (overview/board/card)"
```

---

### Task 7: `DASHBOARD.md` + smoke script + sprint close

**Files:**
- Create: `DASHBOARD.md` (repo root, peer of `MATCHING.md` / `COMP.md`)
- Create: `scripts/smoke_s53.py`
- Modify: `docs/ROADMAP.md` (status board `S5.3` → `[x]`, Current state, session log)

**Interfaces:**
- Consumes: the running app (uvicorn) + the three endpoints. The smoke reuses the
  server-boot / teardown / `_get` / `_post` harness from `scripts/smoke_s52.py`
  (copy it, adapt the checks). Key-less capable (heuristic extraction).

- [ ] **Step 1: Write `DASHBOARD.md`**

Cover, in prose matching `COMP.md`/`MATCHING.md`:
- Purpose: employer-ready read-models over the org plane; API-first; JSON only.
- The three endpoints, their shapes, and the lean-board / drill-in-card split.
- Consent-by-reuse: card sections reuse `reputation_for_org` /
  `query_coding_rounds_for_org` / `query_records_for_org`; `ledger_read`; per-section
  `SectionStatus` degradation; card is 200 even with no grants; 404 only for an
  unknown candidate.
- Plane boundary: no candidate PII, no depth `Report`; `match.surface` audit rows are
  written by `run_match` when a board loads (disclosure log), the card writes the
  ledger reads' own audit rows; overview writes none.
- `dash_board_top_n` knob.

- [ ] **Step 2: Write `scripts/smoke_s53.py`**

Copy the harness from `scripts/smoke_s52.py` (server boot on a temp DB, `_get`/`_post`
helpers, teardown, `SMOKE OK` / exit code). Replace the check body with this sequence
(each an assertion that prints a line; exit non-zero on first failure):

1. `POST /ledger/orgs` (admin) → capture `org_id` + `X-Org-Key` (or build via the
   admin plane exactly as `smoke_s52.py` does).
2. `POST /jobs` (org key) with must-have `["python","django"]`, a `comp_band`, and
   `min_skill_coverage` → capture `req_id`.
3. `GET /dashboard/overview` → `total_requisitions == 1`, `by_status == {"open": 1}`.
4. `GET /jobs/{req_id}/board` **before materialization** → **422**.
5. Create a candidate via `POST /candidates` (heuristic), then materialize it the way
   `smoke_s51.py` does (or, if the smoke can't reach the materialize helper over HTTP,
   reuse `smoke_s51.py`'s materialization approach). `GET /jobs/{req_id}/board` → **200**,
   `match.pool_size >= 1`, `comp.advisory is True`.
6. `GET /candidates/{cand_id}/card` **without consent** → 200, all three section
   statuses `consent_required`.
7. `POST /ledger/candidates/{cand_id}/consent` (admin) granting `ledger_read` for the
   org → `GET .../card` → `records`/`coding_rounds` status `no_data` (nothing submitted).
8. `POST /ledger/consent/{consent_id}/revoke` → `GET .../card` → back to
   `consent_required`.
9. `GET /jobs/{req_id}/board` with a **second org's** key → **404**.
10. `GET /candidates/does-not-exist/card` → **404**.

Print `SMOKE OK` and exit 0 when all pass.

> Note (from S5.1/S5.2 smokes): construct the `TestClient`/server so the lifespan
> runs (the app sets `app.state.services` on startup). Follow `smoke_s52.py` exactly.

- [ ] **Step 3: Run the smoke (key-less)**

Run: `python scripts/smoke_s53.py`
Expected: all checks print OK; final `SMOKE OK`; exit code 0.

- [ ] **Step 4: Run the full offline suite once more**

Run: `pytest -q`
Expected: PASS (green; ~25–30 new tests over the 653 baseline).

- [ ] **Step 5: Update `docs/ROADMAP.md`**

- Status board: `S5.3` `[ ]` → `[x]`; note PI-5 complete if S5.1–S5.3 all done.
- "Current state" + "Next action": S5.3 built (pending final whole-branch review +
  merge); next is PI-6 shaping (candidate side & intake) per gap-analysis §6.
- Add a `2026-07-28` session-log entry summarizing S5.3.

- [ ] **Step 6: Commit**

```bash
git add DASHBOARD.md scripts/smoke_s53.py docs/ROADMAP.md
git commit -m "docs(s53): DASHBOARD.md + smoke_s53 + ROADMAP (S5.3 built)"
```

---

## After all tasks

- Whole-branch self-review (superpowers:requesting-code-review) before merge — no
  Critical/Important expected; the layer adds no new state, audit, or consent path.
- Merge `s53-employer-dashboard` → `main` (fast-forward), confirm `pytest -q` green on
  main, delete the branch, and finalize the ROADMAP session log (per CLAUDE.md
  end-of-session step).

## Self-Review (author checklist — completed)

**Spec coverage:**
- §3.1 overview → Task 3. §3.2 board (404/422 parity) → Task 4 (service) + Task 6 (endpoint). §3.3 card (per-section status, 200-not-403, 404 unknown) → Task 5 + Task 6.
- §4 consent/audit by reuse → Tasks 5–6 (reuse of the three audited store methods; no new audit code). Depth-report exclusion → nothing in the plan surfaces `Report` (enforced by omission; noted in DASHBOARD.md, Task 7).
- §5 architecture/wiring (cycle-safe) → Task 3. §6 `dash_board_top_n` → Task 1. §7 tests → Tasks 1–6. §8 DASHBOARD.md + smoke → Task 7.

**Placeholder scan:** none — every code step carries full content; the smoke script (Task 7) reuses the existing `smoke_s52.py` harness with an explicit 10-step check sequence.

**Type consistency:** `DashboardService(jobs, comp, ledger, *, settings)` and `build_dashboard_service` match between Task 3 and the conftest/Services wiring; `SectionStatus` values (`available`/`consent_required`/`no_data`) are identical across schema, service, and API tests; `board() -> Optional[RequisitionBoard]` (None ⇒ 404) and the endpoint's `pool_size == 0 ⇒ 422` are consistent between Task 4 and Task 6.
