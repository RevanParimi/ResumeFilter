# S9.3 — Error observability (PI-9, sprint 3)

> **Status:** design approved 2026-08-25, spec written the same day.
> Baseline before any change: `main` at `f15f72e`, branch
> `s93-error-observability`. Tree carries one unrelated modification
> (`data/veritas.db`, the tracked post-demo state noted in OPERATING.md's
> workflow) — deliberately left alone, not reverted.

## 0. The question this sprint answers

S9.1 asked whether the advisory numbers predict a human's judgment. S9.2 asked
whether they were computed from the resume or from a hole where the resume used
to be. This sprint asks the operator's question:

> **When veritas refuses a request, can anyone find out why?**

The answer today is no for every refusal that is not a 500. The system is
well-behaved — it refuses correctly, in the right place, with the right status —
and it refuses **silently**. That is the same shape as S9.2's finding, one
plane out: the system is behaving correctly, and that is the problem.

## 1. What was measured

All figures executed against `f15f72e`, not argued.

### 1.1 The spine that already exists — and is not being rebuilt

| Fact | Where |
|---|---|
| structlog configured, JSON in prod, console in dev | `src/app/core/logging.py` |
| `request_id` bound into contextvars for every request | `src/app/main.py` `request_context` |
| one access line per request: method, path, status, duration | same |
| unhandled 500 → full traceback logged, `internal_error` on the wire | `src/app/main.py:360` |
| **zero** bare `except:` in 27,861 LOC | AST sweep over `src/app` |
| **zero** `except BaseException` | same |

The 156 exception handlers that exist are, on inspection, mostly deliberate and
commented. This sprint adds no handler to business logic.

### 1.2 The five gaps

**Gap 1 — `api/` is a logging blind spot.**

| Subsystem | files | with logger | LOC | except | that log | HTTPException |
|---|---|---|---|---|---|---|
| **api** | 2 | **0** | 2,869 | 95 | **0** | **138** |
| candidates | 15 | 1 | 2,784 | 5 | 1 | 0 |
| verification | 11 | 1 | 2,044 | 7 | 0 | 0 |
| ledger | 6 | 0 | 1,788 | 1 | 0 | 0 |
| features | 17 | 0 | 1,757 | 4 | 0 | 0 |
| **TOTAL** | **179** | **28** | **27,861** | **156** | **15** | **139** |

`routes.py` is 2,869 lines, raises `HTTPException` 138 times, and never
imports a logger. Starlette handles `HTTPException` itself, so **none of those
138 refusals reaches the `Exception` handler at `main.py:360`**. A consent
refusal, a tenancy denial, a quota rejection and a malformed-PDF 422 all leave
exactly one artifact: a status integer in the access line.

OPERATING.md §7 (the runbook) is 100% metrics-based. Every entry says
`GET /metrics`. A counter answers "how many 403s"; it cannot answer **"why did
*this* org get a 403"**, which is the question a staffing-agency customer
actually asks.

**Gap 2 — the repo's only logging test is vacuous, and this was
mutation-proved.**

`tests/test_email_seam.py::test_null_email_logs_neither_code_nor_destination`
exists to prove an OTP and its destination address never reach the logs. It
asserts against `caplog`. But `configure_logging()` uses
`PrintLoggerFactory(file=sys.stdout)` — structlog never passes through stdlib
logging, so `caplog.text` is **always `''`** and the assertion is
`"123456" not in ""`.

Proof, executed: a mutant was planted making `NullEmail.send` log **both** the
OTP body and the destination address —

```python
log.info("email.dispatch.refused", provider="null", to=to, body=body)
```

`pytest tests/test_email_seam.py -q` → **10 passed**. The guard survives the
exact leak it was written to catch.

This matters more than its one test: **there is currently no way to assert
anything about log output in this repo** (1 of 249 test files mentions logging,
and it is this one). Every log line this sprint adds would be equally
unguarded.

**Gap 3 — three silent swallows in advisory paths.**

| Site | Handler |
|---|---|
| `graph/nodes/ai_signals.py:43` | `except Exception: return None, [], ""` |
| `graph/nodes/plausibility.py:56` | `except Exception: return None, None, [], [], ""` |
| `profile_sources/service.py:111` | `except Exception: pass` |

The first two are in files that **already bind `log`**, and their sibling nodes
(`claim_extraction.py:126`, `probe_generation.py:39`) log the identical failure
with `log.warning(...)`. So an LLM outage silently zeroes the two most
expensive signals in the pipeline while its neighbours report theirs. This is
an inconsistency, not a design choice.

**Gap 4 — unguarded IO in the append-only flywheel.**

`services/flywheel.py:35` appends to a JSONL file with no guard, and
`__init__` calls `os.makedirs` with none either. On this machine — OneDrive,
Windows — a locked file is not hypothetical; it is a trap already recorded
against this repo. A blocked audit write currently raises straight out into
whatever pipeline node called it.

**Gap 5 — 10 of 156 handlers log; 28 of 179 modules bind a logger.**

The six `IntegrityError` handlers (`auth/store.py:394`, `ledger/store.py:233`,
`ratelimit/store.py:97`, `reports/store.py:88`, `reports/store.py:139`,
`rights/store.py:82`) are all correct race handling and all invisible. A race
going from 1/day to 1000/min is currently undetectable.

## 2. What is being built

### 2.1 Two boundary handlers, not 138 edits

A probe (`TestClient`, fastapi 0.138.0) established which handler fires for
each status class. Executed, not assumed:

| Request | Handler that fired | `scope["route"]` |
|---|---|---|
| route raises `HTTPException(403)` | `StarletteHTTPException` | `/raise403` |
| no route matches | `StarletteHTTPException` (404) | `None` |
| wrong method | `StarletteHTTPException` (405) | `/raise403` |
| Pydantic body rejection | `RequestValidationError` (422) | — |
| route raises `RuntimeError` | `Exception` (500) | — |

So **one** `StarletteHTTPException` handler covers all 138 raise sites plus
Starlette's own 404s and 405s, and **one** `RequestValidationError` handler
covers the Pydantic 422s. `routes.py` is not edited at all.

Both handlers delegate to FastAPI's stock responder
(`fastapi.exception_handlers.http_exception_handler` /
`request_validation_exception_handler`) after logging, so **the wire format is
byte-identical to today**. That is a hard requirement: the wired UI and the
smoke scripts both parse these bodies.

**Labelling.** By route **template**, via the existing `_route_template()`
helper — never the raw path. This reuses the bounded-cardinality rule
OPERATING.md §5 already established for metrics, and for the same reason: a
scanner walking random URLs must not become unbounded log volume. The probe
confirmed `request.scope["route"]` is populated inside the exception handler
for matched routes, so the helper works there unchanged.

**Levels**, chosen so the signal survives:

| Case | Level | Why |
|---|---|---|
| 4xx on a **matched** route | `warning` | a real refusal of a real request |
| 404/405 with **no route matched** | `info` | scanner noise; at `warning` it is how alert fatigue starts |
| 422 validation | `warning` | a caller integration bug worth seeing |
| 5xx | `error` | unchanged, already exists |

**Fields:** `status`, `route` (template), `method`, `reason` (the detail), and
`request_id` — already bound by the middleware, so no plumbing.

### 2.2 The PII decision, made by measurement

Of the 13 interpolated `detail=f"..."` strings in `routes.py`, **11 interpolate
config values** — caps, counts, batch indices — and carry no user data. Four
can quote input: `pdf_parse_failed: {exc}` (×2), `speech_unavailable/{exc}`,
`speech_failed: {exc}`, and `unknown view '{body.view_name}'`.

The detail **is logged in full**. The reasoning is consistency, not
convenience: the `Exception` handler at `main.py:360` already logs `repr(exc)`
plus a full traceback, which can contain anything a 4xx detail can. This repo
has therefore already decided that the operator's own log plane may hold
exception text. Inventing a second, stricter standard for 4xx would leave two
rules where one exists.

What is *added* is the ability to check. Gap 2's fixture makes "no OTP reaches
the log" an assertable property rather than a hoped-for one — for the first
time.

**Explicitly NOT built: a redaction processor.** It would tax every log line
and mis-fire on numeric ids that look like OTPs. The honest fix for Gap 2 is
detectability, which §2.3 delivers. Revisit only if a real leak is found.

### 2.3 Two test seams, because they prove different things

A probe established that `structlog.testing.capture_logs()` **replaces the
configured processor chain**. Executed with a redaction processor installed:

| Seam | Redaction applied? | Therefore proves |
|---|---|---|
| `capture_logs()` | **False** — raw event dict | what a call site **passed** |
| real chain → `StringIO` | **True** — `{"to": "<redacted>"}` | what **leaves the process** |

Building the OTP guard on `capture_logs` would be a *different* vacuous guard.
So `tests/conftest.py` gains **two** fixtures:

- **`log_events`** — `capture_logs`-based, yields a list of event dicts. For
  call-site contracts: *"the 403 was logged with this route and this reason."*
- **`log_output`** — reconfigures structlog with the **real** production
  processor chain rendering to a `StringIO`, yields the rendered text, and
  restores the previous configuration on teardown. For egress claims: *"this
  string never left the process."*

A third probe confirmed `capture_logs` works against **cached module-level
loggers** bound at import time (every module binds one), despite
`cache_logger_on_first_use=True`. So **no production change is required** to
make logging testable — the fixtures work against the shipped configuration.

### 2.4 The targeted fixes

- **Gap 2:** re-arm the OTP test on `log_output`. It must fail against the
  planted mutant before it passes.
- **Gap 3:** `log.warning(...)` in the three swallows, matching the wording
  their sibling nodes already use (`*_llm_failed`, `error=str(exc)`). Return
  values unchanged — the degradation stays, the silence goes.
- **Gap 4:** guard `JsonlFlywheel.log` and `__init__` — log and continue. An
  audit sink that cannot write must not take the pipeline down with it, and
  must not vanish quietly either.
- **Gap 5:** `log.info` on the six `IntegrityError` race handlers, so a race
  changing frequency is visible. Behaviour unchanged.

### 2.5 Documentation

OPERATING.md gains **§12 — Reading the logs**: the event vocabulary, the
`request_id` correlation path, and the runbook entry §7 has never had —
*"a customer says they got a 403"*, answered from logs rather than counters.

## 3. What is NOT in this sprint

- **try/except across all 179 modules.** Scoped out by the user on 2026-08-25
  after the trade-off was put to them. This repo's own history is a catalogue
  of defects that were invisible **because something degraded quietly** — S9.2's
  dropped sections, the coverage instrument going vacuous, the CI collection
  failure that 2,086 local greens could not see. A blanket `except Exception`
  around business logic converts loud bugs into silent wrong answers, which is
  the costlier failure here. **Failures stay loud.**
- **A redaction processor** (§2.2).
- **Alerting / log shipping.** Same standing reason as OPERATING.md §11: a
  deploy-time concern, and nothing is deployed.
- **Any wire-format change.** The UI and the smokes parse these bodies.

## 4. Success criteria

1. Every 4xx and 5xx produces exactly **one refusal line**, carrying
   `request_id`, `route` (template), `status` and `reason` — **in addition to
   the existing access line**, which is unchanged and still emitted for every
   request. Two lines per failed request, correlated by `request_id`, is the
   intended shape; the refusal line carries the *why*, the access line the
   *timing*. A test asserts the refusal line appears exactly once, so a
   double-registered handler is caught.
2. Response bodies and status codes are **unchanged** — asserted, not assumed.
3. The re-armed OTP guard **fails** against the leak mutant and passes clean.
4. Log volume stays bounded under scanner traffic: unmatched paths collapse to
   one `route` label.
5. `pytest -q` green, and **the new tests kill their mutants**: deleting each
   new log call must turn a test red. A logging line no test observes is the
   very defect Gap 2 records.
6. A smoke run (`scripts/smoke_s93.py`) drives real HTTP and asserts on real
   emitted log lines.
7. OPERATING.md §12 exists and answers the 403 question from logs.
