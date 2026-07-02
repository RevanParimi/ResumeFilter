# M1 Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist reports, close the flywheel outcome loop, harden the API, add LLM retries, extract shared rule machinery, ship a second domain (`data_eng`), and add Docker + CI.

**Architecture:** Follow the existing Protocol + real + in-memory-fake service pattern for the report store; keep all routes thin (validation + store + engine); domain knowledge stays behind `DomainModel` (new `heuristic_type_hints()` hook removes the genai leak from the graph layer).

**Tech Stack:** FastAPI, Pydantic v2, stdlib sqlite3, structlog, pytest (+ fastapi TestClient), LangGraph. No new runtime dependencies.

## Global Constraints

- Python 3.11+; venv at `.resume` (`.resume\Scripts\python.exe -m pytest -q`).
- All tests fully offline & hermetic (`DEE_CONFIG_FILE` → nonexistent file; fakes for LLM/GitHub).
- Secrets only via env/.env; tunables get a Settings field + config.yaml entry.
- Never store resume text in the report store (NFR-4).
- `advisory=True` / `human_review_required=True` invariants untouched.
- Spec: `docs/superpowers/specs/2026-07-03-m1-production-hardening-design.md`.

---

### Task 1: Report store service (SQLite + in-memory)

**Files:**
- Create: `app/services/report_store.py`
- Modify: `app/core/config.py` (add `report_db_path`), `config.yaml`, `app/services/__init__.py` (add to `Services` + builder)
- Test: `tests/test_report_store.py`

**Interfaces (Produces):**
```python
class OutcomeLabel(StrEnum):
    VERIFIED_GENUINE = "verified_genuine"
    VERIFIED_FABRICATED = "verified_fabricated"
    CANDIDATE_CLARIFIED = "candidate_clarified"
    INCONCLUSIVE = "inconclusive"

class OutcomeRecord(BaseModel):
    report_id: str
    claim_id: str | None = None
    outcome: OutcomeLabel
    notes: str = ""
    recorded_at: datetime  # default utcnow

class ReportStore(Protocol):
    def save(self, report: Report) -> None: ...
    def get(self, report_id: str) -> Report | None: ...
    def add_outcome(self, rec: OutcomeRecord) -> None: ...
    def outcomes(self, report_id: str) -> list[OutcomeRecord]: ...
    def delete(self, report_id: str) -> bool: ...

class SqliteReportStore: ...   # (path | settings) → WAL sqlite, threading.Lock
class InMemoryReportStore: ...
def build_report_store(settings) -> ReportStore: ...
```
`Services` gains `report_store: ReportStore`; `build_default_services` wires
`build_report_store(settings)`; `tests/conftest.py: make_services` wires
`InMemoryReportStore()`.

- [ ] Write failing tests: sqlite save/get round-trip (tmp_path), get-missing → None, restart survival (2nd store instance same path), add_outcome/outcomes round-trip, delete removes report+outcomes, in-memory parity.
- [ ] Run: `pytest tests/test_report_store.py -q` → FAIL (module missing)
- [ ] Implement `report_store.py`; add `report_db_path: str = "./data/reports.db"` to Settings + config.yaml; extend `Services` and conftest.
- [ ] Run full suite → PASS. Commit `feat: persistent SQLite report store`.

### Task 2: Persisted reports + outcome endpoints

**Files:**
- Modify: `app/api/routes.py`, `app/main.py`
- Test: `tests/test_api.py` (new)

**Interfaces (Produces):**
- `app.state.services` (full bundle) replaces ad-hoc `report_store` dict; routes read `request.app.state.services.report_store` / `.flywheel`.
- `POST /report/{report_id}/outcome` body `{outcome, claim_id?, notes?}` → 200 `{report_id, claim_id, outcome, recorded_at}`; 404 unknown report; 422 claim_id not in report.
- `GET /report/{report_id}/outcomes` → `{report_id, outcomes: [...]}`.
- Flywheel record on outcome: `{record_type: "outcome", report_id, claim_id, outcome, notes}`.
- Test helper: build app with `make_services(...)` engine via dependency-free `create_app(services)`-style wiring (lifespan builds default services only when none injected — expose `app.state.services` set in lifespan; tests override before TestClient enters or via `app.state`).

- [ ] Write failing TestClient tests: evaluate→get round-trip via sqlite tmp store; outcome POST report-level + claim-level; 404/422 paths; outcomes GET; flywheel outcome record asserted (InMemoryFlywheel).
- [ ] Run → FAIL. Implement routes + lifespan wiring.
- [ ] Full suite PASS. Commit `feat: persist reports; outcome endpoints close flywheel loop`.

### Task 3: API hardening (caps, domain pre-check, request-id, errors, auth, discovery)

**Files:**
- Modify: `app/api/routes.py` (caps validators, domain pre-check, `/domains`, `/healthz`), `app/main.py` (middleware, exception handler, auth dependency), `app/core/config.py` + `config.yaml` (`max_resume_chars=200000`, `max_pdf_b64_chars=14000000`, `api_auth_key` SecretStr — env-only, NOT in yaml)
- Test: `tests/test_api.py` (extend)

**Behavior:**
- Oversize resume_text / pdf_b64 → 422 (Pydantic validator, message names the cap).
- Unknown domain → 422 with registered list, engine never invoked.
- Middleware: `X-Request-ID` in→bind contextvars→out header; access log line with `duration_ms`; clear contextvars after.
- `@app.exception_handler(Exception)` → 500 `{"detail": "internal_error", "request_id": ...}`; remove `detail=f"evaluation_failed: {exc}"` leak.
- Auth dependency: if `settings.api_auth_key` set and header `X-API-Key` mismatch → 401. Applied to evaluate/report routes only.
- `GET /domains` → `[{key, display_name, claim_types}]`; `GET /healthz` → `{status, version, env, llm_mode, domains}`.

- [ ] Failing tests: request-id echo + generated; oversize 422 (text + pdf); unknown domain 422 lists `genai`; 401 with key configured / 200 without; healthz payload keys; domains payload.
- [ ] Implement; full suite PASS. Commit `feat: harden API surface`.

### Task 4: LLM retries

**Files:** `app/services/llm.py`, `app/core/config.py`, `config.yaml`; test in `tests/test_api.py` or `tests/test_report_store.py` not needed — add `tests/test_llm_config.py` asserting `Settings().llm_max_retries == 2` and OpenRouterLLM passes it (constructor inspection via monkeypatched AsyncOpenAI).

- [ ] Failing test → implement `llm_max_retries: int = 2`, pass `max_retries=` to AsyncOpenAI. Suite PASS. Commit `feat: configured LLM client retries`.

### Task 5: Shared rule machinery + domain-owned heuristics + data_eng domain

**Files:**
- Create: `app/domains/rules.py` (move `SignalRule` + `present()` from genai), `app/domains/data_eng.py`, `tests/test_data_eng.py`, `tests/fixtures/data_eng_resume.txt`
- Modify: `app/domains/genai.py` (import shared; add `heuristic_type_hints()` returning current `_TYPE_HINTS` mapping), `app/domains/base.py` (`heuristic_type_hints()` default `{}`), `app/graph/nodes/claim_extraction.py` (use `domain.heuristic_type_hints()`), `app/domains/__init__.py` (import data_eng)

**data_eng:** claim types `etl_pipeline, streaming, warehouse_modeling, orchestration, data_quality, generic`; three `SignalRule`s per spec §5 (incl. scale-without-distributed-tooling contradiction, −0.30, conf ≥0.85); prompts mirroring genai's structure; heuristic hints for all non-generic types.

- [ ] Failing tests: registry has `data_eng`; heuristic extraction on data_eng fixture yields typed claims offline; fabricated-style claim ("processed petabytes daily" with no tooling) → coherence < 0.35 & confidence ≥ 0.85 via rule; genuine streaming claim with broker+engine+semantics+lag → coherence ≥ 0.6; end-to-end engine run with `domain="data_eng"` produces a report offline.
- [ ] Implement refactor (genai behavior unchanged — existing tests are the guard) + new domain. Suite PASS. Commit `feat: data_eng domain + shared SignalRule machinery`.

### Task 6: Docker + CI

**Files:** Create `Dockerfile`, `.dockerignore`, `.github/workflows/ci.yml`.

- [ ] Dockerfile: `python:3.12-slim`, non-root `appuser`, `pip install -r requirements.txt`, expose 8000, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`, HEALTHCHECK curl-less (python urllib) on `/healthz`.
- [ ] CI: push/PR, matrix 3.11/3.12, `pip install -r requirements.txt`, `pytest -q`.
- [ ] Validate locally what's validatable (docker build if daemon available; else YAML lint via python). Commit `chore: Dockerfile + CI`.

### Task 7: Docs + final verification

- [ ] Update README.md (new endpoints, auth, store, data_eng, Docker) and FLOW.md (project tree, config table additions, outcome loop section).
- [ ] `pytest -q` full suite green.
- [ ] Live smoke: start uvicorn (no key) → POST /evaluate → restart → GET /report/{id} OK → POST outcome → check data/flywheel.jsonl + reports.db → healthz/domains.
- [ ] Commit `docs: M1 updates`; final review pass (superpowers:requesting-code-review analog inline).
