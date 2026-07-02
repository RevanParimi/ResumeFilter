# M1 Production Hardening — Design

Implements FR-6..FR-18, FR-20..21 of [docs/REQUIREMENTS.md](../../REQUIREMENTS.md).
Design decisions below are final for M1.

## 1. Persistent report store — `app/services/report_store.py`

A `ReportStore` Protocol with two implementations, mirroring the existing
flywheel/vectorstore pattern (Protocol + real + in-memory fake):

```python
class ReportStore(Protocol):
    def save(self, report: Report) -> None: ...
    def get(self, report_id: str) -> Report | None: ...
    def add_outcome(self, rec: OutcomeRecord) -> None: ...
    def outcomes(self, report_id: str) -> list[OutcomeRecord]: ...
    def delete(self, report_id: str) -> bool: ...      # DPDP erasure (NFR-4)
```

- **`SqliteReportStore`** — stdlib `sqlite3`, no new dependency. Two tables:
  - `reports(id TEXT PK, domain TEXT, created_at TEXT, depth_band TEXT, body TEXT)`
    — `body` is the full `Report` JSON (schema evolution = Pydantic's problem,
    not SQL's). WAL mode; `check_same_thread=False` + a lock (FastAPI default
    threadpool for sync work is fine at this scale).
  - `outcomes(id INTEGER PK AUTOINCREMENT, report_id TEXT, claim_id TEXT NULL,
    outcome TEXT, notes TEXT, recorded_at TEXT)`.
- **`InMemoryReportStore`** — dicts/lists, for tests.
- Config: `report_db_path: ./data/reports.db` (YAML + `DEE_REPORT_DB_PATH`).
- The resume text itself is never stored (NFR-4) — the Report schema doesn't
  contain it today; keep it that way.

## 2. Outcome loop — routes

- `POST /report/{report_id}/outcome` body:
  `{outcome: OutcomeLabel, claim_id?: str, notes?: str}` with
  `OutcomeLabel = verified_genuine | verified_fabricated | candidate_clarified | inconclusive`.
  Validation: 404 unknown report; 422 claim_id not in that report.
  Side effects: store.add_outcome(...) AND flywheel.log(record_type="outcome",
  report_id, claim_id, outcome, notes) — same sink the evaluation rows go to,
  so the training joiner reads one file.
- `GET /report/{report_id}/outcomes` → `{report_id, outcomes: [...]}`.

## 3. API hardening — `app/main.py`, `app/api/routes.py`

- **Caps** (config): `max_resume_chars=200_000`, `max_pdf_b64_chars=14_000_000`.
  Enforced in `EvaluateRequest` validators → FastAPI 422.
- **Domain pre-check**: `get_domain(req.domain)` in the route before invoking
  the engine → 422 listing registered domains (moves the existing KeyError
  catch earlier; graph never runs on a bad domain).
- **Request-ID middleware**: pure-ASGI-level FastAPI `@app.middleware("http")`;
  reads `X-Request-ID` or generates `req_<hex12>`; binds it via
  `structlog.contextvars.bind_contextvars`; emits one `access` log line with
  method, path, status, duration_ms; sets response header. `configure_logging`
  gains the `merge_contextvars` processor.
- **Global exception handler**: `@app.exception_handler(Exception)` → JSON 500
  `{detail: "internal_error", request_id}`; full traceback logged. The blanket
  `except Exception → 500 detail=str(exc)` in the evaluate route (leaks
  internals) is removed in favor of this.
- **Auth**: `api_auth_key: SecretStr` setting (default empty = disabled). A
  FastAPI dependency on the evaluate/report routes: if configured and header
  `X-API-Key` doesn't match → 401. `/healthz` and `/` stay open.
- **`GET /domains`** → `[{key, display_name, claim_types}]`.
- **`GET /healthz`** → `{status, version, env, llm_mode, domains}`; version
  read from package metadata (fallback to app version constant).

## 4. LLM resilience — `app/services/llm.py`

`AsyncOpenAI(..., max_retries=settings.llm_max_retries)` with
`llm_max_retries: int = 2` in Settings + config.yaml. Node-level try/except
fallbacks already exist and stay.

## 5. Domain layer refactor + `data_eng`

- **`app/domains/rules.py`** (new, shared): move `SignalRule` (public name) and
  `_present` from `genai.py`. `genai.py` imports them; behavior unchanged.
- **`DomainModel.heuristic_type_hints() -> dict[str, tuple[str, ...]]`** —
  ordered mapping claim_type → keyword tuple used by the LLM-free extraction
  fallback. Base implementation returns `{}`; genai returns the mapping
  currently hardcoded as `_TYPE_HINTS` in `claim_extraction.py`; the node now
  asks the active domain instead (removes the domain leak, FR-17).
- **`app/domains/data_eng.py`** — `key="data_eng"`, claim types:
  `etl_pipeline, streaming, warehouse_modeling, orchestration, data_quality,
  generic`. Three `SignalRule`s:
  1. `data_eng.etl_pipeline.coherence` — signals: data volume/scale, tooling
     (spark/airflow/dbt/...), incremental/backfill strategy, monitoring.
     Contradiction 'tell': claims "petabyte/billions of rows" scale with no
     distributed tooling named → coherence −0.30, confidence pinned ≥0.85.
  2. `data_eng.streaming.coherence` — signals: broker (kafka/kinesis/pubsub),
     processing engine (flink/spark streaming), delivery semantics
     (exactly-once/at-least-once), lag/throughput handling.
  3. `data_eng.warehouse.coherence` — signals: warehouse tech, modeling
     approach (star/dimensional/dbt models), testing/quality, cost/perf tuning.
  Registered via import in `app/domains/__init__.py`.

## 6. Ops

- **Dockerfile**: `python:3.12-slim`, `pip install -r requirements.txt`,
  non-root user, `uvicorn app.main:app --host 0.0.0.0 --port 8000`,
  HEALTHCHECK on `/healthz`. `.dockerignore` excludes venvs/caches/.env/data.
- **CI** `.github/workflows/ci.yml`: push/PR → Python 3.11 + 3.12 matrix,
  `pip install -r requirements.txt`, `pytest -q` (offline by design).

## 7. Testing (all offline)

New: `tests/test_report_store.py` (sqlite round-trip in tmp_path, restart
survival, outcomes, delete), `tests/test_api.py` (TestClient over a FakeLLM
engine: evaluate→get, request-id header, caps 422, unknown domain 422, auth
on/off, healthz/domains payloads, outcome POST/GET incl. flywheel record).
Existing 20 tests must stay green (claim_extraction tests will exercise the
new domain-provided hints path).

## 8. Not doing (YAGNI at M1)

Rate limiting, Postgres, async DB drivers, per-claim LLM concurrency,
real embeddings, queue/workers — see REQUIREMENTS.md milestones M2+.
