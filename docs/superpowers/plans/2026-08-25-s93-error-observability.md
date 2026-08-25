# S9.3 Error Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every refusal veritas issues findable in the logs by
`request_id`, and make log content assertable in tests for the first time.

**Architecture:** Two FastAPI exception handlers at the app boundary
(`StarletteHTTPException`, `RequestValidationError`) log all 138 of
`routes.py`'s refusals without editing `routes.py` at all, then delegate to
FastAPI's stock responders so the wire format is byte-identical. Two pytest
fixtures give tests a way to assert on log output — one for what a call site
passed, one for what actually leaves the process, because `capture_logs()`
bypasses the processor chain and cannot prove the second.

**Tech Stack:** Python 3.13, FastAPI 0.138.0 (pinned), structlog, pytest,
SQLAlchemy/SQLite.

**Spec:** `docs/superpowers/specs/2026-08-25-s93-error-observability-design.md`

## Global Constraints

- **TDD, fully offline.** No test may need an API key or network. Use the
  NullLLM / fake-services pattern in `tests/conftest.py`.
- **`pytest -q` must be green before merge.** Baseline is recorded in Task 0.
- **No wire-format change.** Response bodies and status codes must be
  byte-identical to `main`. The wired UI (`frontend/api.js`) and the smoke
  scripts parse these bodies.
- **No new try/except around business logic.** Failures stay loud. This sprint
  adds observability, not tolerance. (Spec §3.)
- **Never log `RequestValidationError.errors()` wholesale** — it carries an
  `input` key holding the caller's raw submitted value. Log `loc` only.
  (Spec §2.3a.)
- **Label logs by route TEMPLATE, never raw path** — `_route_template()`.
  Unbounded label cardinality is the rule OPERATING.md §5 already sets for
  metrics.
- **Commit style:** no `Co-Authored-By` trailer.
- **Branch:** `s93-error-observability`, already created from `f15f72e`.
- **Windows/OneDrive:** never `git stash` in this repo. Do not use
  `subprocess.PIPE` for a long-running server's stdout — redirect to a file.

---

### Task 0: Record the baseline

**Files:**
- Modify: none (measurement only)

**Interfaces:**
- Consumes: nothing
- Produces: the passing-test count every later task compares against

**Baseline, already measured on this branch: `2101 passed`, exit 0, 224.89s.**
Every later task must keep that number non-decreasing.

- [ ] **Step 1: Confirm the branch and re-check the baseline**

```bash
git branch --show-current    # must print: s93-error-observability
python -m pytest -q 2>&1 | tail -5
```

Expected: `2101 passed`. If it differs, record the real number here before
going further -- a moved baseline is a finding, not a rounding error.
`data/veritas.db` shows as modified — that is the known
post-demo state; **leave it alone**, do not revert or commit it.

---

### Task 1: Extract the processor chain, and add the two log-capture fixtures

This task is first because nothing else can be tested without it.

**Files:**
- Modify: `src/app/core/logging.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_log_capture.py` (create)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `app.core.logging.build_processors(settings) -> list[structlog.types.Processor]`
    — the shared, renderer-less processor list.
  - pytest fixture `log_events` → `list[dict]`, the events a test emitted.
  - pytest fixture `log_output` → an object with `.text` (`str`), the
    **rendered** output of the production chain.

- [ ] **Step 1: Write the failing test**

Create `tests/test_log_capture.py`:

```python
"""The two log seams, and the reason there are two.

`capture_logs()` REPLACES the configured processor chain, so it can only ever
prove what a call site PASSED. What actually leaves the process is a different
question, and answering it wrongly is how this repo's OTP-leak guard came to
assert a string was absent from an empty string for eight PIs.
"""

import json

import structlog

from app.core.logging import build_processors, get_logger


def test_log_events_captures_what_a_call_site_passed(log_events):
    get_logger("probe").warning("evt_happened", who="alice", n=3)
    assert any(
        e["event"] == "evt_happened" and e["who"] == "alice" and e["n"] == 3
        for e in log_events
    )


def test_log_output_renders_through_the_production_chain(log_output):
    get_logger("probe").warning("evt_rendered", who="alice")
    line = json.loads(log_output.text.strip().splitlines()[-1])
    assert line["event"] == "evt_rendered"
    assert line["who"] == "alice"
    # Proof it is the REAL chain and not a hand-rolled copy: these keys come
    # from processors configure_logging installs, not from the call site.
    assert line["level"] == "warning"
    assert "timestamp" in line


def test_build_processors_is_the_single_source_of_the_chain(settings):
    """The fixture must not own a second copy of the chain -- a copy is free to
    drift, and a drifted copy is a guard that stops guarding silently."""
    assert build_processors(settings), "chain must not be empty"
    names = [getattr(p, "__name__", type(p).__name__) for p in build_processors(settings)]
    assert "add_log_level" in names
    assert "merge_contextvars" in names


def test_log_output_survives_a_module_level_logger_bound_before_the_fixture():
    """Every module in src/app binds its logger at import, and structlog runs
    with cache_logger_on_first_use=True. A fixture that only works for loggers
    created inside its own block would be useless to every real module."""
    pre_bound = get_logger("app.pre.bound")
    pre_bound.info("warmup")
    with structlog.testing.capture_logs() as events:
        pre_bound.warning("after_cache", k="v")
    assert any(e["event"] == "after_cache" for e in events)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_log_capture.py -q
```

Expected: FAIL — `ImportError: cannot import name 'build_processors'`, and
`fixture 'log_events' not found`.

- [ ] **Step 3: Extract `build_processors` in `src/app/core/logging.py`**

Replace the body of `configure_logging()` that builds `shared_processors` so
the list comes from a module-level function. Add this **above**
`configure_logging`:

```python
def build_processors(settings) -> list[structlog.types.Processor]:
    """The processor chain, WITHOUT a renderer, as one source of truth.

    Extracted so tests can render through the REAL chain instead of a second
    copy of it. A copy is free to drift, and the drift is invisible: the tests
    keep passing while they stop describing production. That is precisely the
    failure this sprint exists to close, so the fixture is wired to the
    shipped list by construction rather than by anyone remembering.
    """
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
```

Then inside `configure_logging()`, replace the inline
`shared_processors: list[...] = [...]` literal with:

```python
    shared_processors = build_processors(settings)
```

Leave everything else in `configure_logging` unchanged.

- [ ] **Step 4: Add both fixtures to `tests/conftest.py`**

Append to `tests/conftest.py` (and add `import io`, `import structlog` to its
imports if not already present):

```python
@pytest.fixture
def log_events():
    """Every structlog event a test emits, as dicts -- what a CALL SITE PASSED.

    Built on structlog.testing.capture_logs, which REPLACES the configured
    processor chain. So this proves what a call site passed and NEVER what left
    the process. For an egress claim ("this secret was not written"), use
    `log_output` -- asserting egress here would be a guard that cannot fail.
    """
    with structlog.testing.capture_logs() as events:
        yield events


class _RenderedLog:
    """The rendered bytes a test's logging actually produced."""

    def __init__(self, buf: "io.StringIO") -> None:
        self._buf = buf

    @property
    def text(self) -> str:
        return self._buf.getvalue()


@pytest.fixture
def log_output(settings):
    """What actually LEAVES THE PROCESS, rendered through the production chain.

    The only honest seam for "no OTP reached the logs". `capture_logs` cannot
    answer that: measured on this repo's own configuration, a processor
    installed in the real chain does not run under it, so the captured dict is
    the pre-processor event and any egress assertion made there is answering a
    different question than the one asked.

    Restores the previous structlog configuration on teardown, and disables the
    logger cache for the duration so a module-level logger bound before this
    fixture ran still renders into the buffer.
    """
    import io as _io

    from app.core.logging import build_processors

    buf = _io.StringIO()
    previous = structlog.get_config()
    structlog.configure(
        processors=[*build_processors(settings), structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        logger_factory=structlog.PrintLoggerFactory(file=buf),
        cache_logger_on_first_use=False,
    )
    try:
        yield _RenderedLog(buf)
    finally:
        structlog.configure(**previous)
```

Add `import logging` to `tests/conftest.py` imports if absent.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_log_capture.py -q
```

Expected: 4 passed.

- [ ] **Step 6: Run the full suite — the refactor must move nothing**

```bash
python -m pytest -q 2>&1 | tail -5
```

Expected: baseline + 4, zero failures.

- [ ] **Step 7: Commit**

```bash
git add src/app/core/logging.py tests/conftest.py tests/test_log_capture.py
git commit -m "test(s93): two log seams, because capture_logs proves only half of it

capture_logs REPLACES the processor chain, so it shows what a call site
passed and never what left the process. Egress claims need the real chain
rendered to a buffer, so there are two fixtures and they are not
interchangeable.

build_processors() is extracted so the fixture cannot own a drifting second
copy of the chain."
```

---

### Task 2: Re-arm the OTP-leak guard

**Files:**
- Modify: `tests/test_email_seam.py:23-29`
- Test: same file

**Interfaces:**
- Consumes: `log_output` fixture from Task 1
- Produces: nothing later tasks depend on

- [ ] **Step 1: Replace the vacuous test**

In `tests/test_email_seam.py`, replace the existing
`test_null_email_logs_neither_code_nor_destination` with:

```python
def test_null_email_logs_neither_code_nor_destination(settings, log_output):
    """S7.1's NullNotifier posture: an OTP in a log file is an OTP leak, and so
    is the address it was going to.

    ASSERTED ON RENDERED OUTPUT, not on caplog. The caplog version of this test
    passed for eight PIs while checking nothing: structlog writes through
    PrintLoggerFactory to stdout and never touches stdlib logging, so
    `caplog.text` was always "" and the assertion read `"123456" not in ""`.
    Proved by mutation -- a NullEmail logging BOTH the code and the address
    passed the old test 10/10.
    """
    with pytest.raises(EmailUnavailable):
        NullEmail(settings).send(to="someone@example.in", subject="s", body="code 123456")
    rendered = log_output.text
    assert "email.dispatch.refused" in rendered, "the attempt must still be logged"
    assert "123456" not in rendered
    assert "someone@example.in" not in rendered
```

- [ ] **Step 2: Verify it passes clean**

```bash
python -m pytest tests/test_email_seam.py -q
```

Expected: 10 passed.

- [ ] **Step 3: Verify it FAILS against the leak — this is the point of the task**

Temporarily edit `src/app/services/email.py`, in `NullEmail.send`, changing:

```python
        log.info("email.dispatch.refused", provider="null")
```

to:

```python
        log.info("email.dispatch.refused", provider="null", to=to, body=body)
```

Then run:

```bash
python -m pytest tests/test_email_seam.py -q
```

Expected: **FAIL** on `assert "123456" not in rendered`. If it passes, the
fixture is not wired to the logger the module actually uses — stop and fix
that before continuing; a green result here means the guard is still fake.

- [ ] **Step 4: Revert the mutant**

```bash
git checkout src/app/services/email.py
grep -c "body=body" src/app/services/email.py   # must print 0
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_email_seam.py
git commit -m "test(s93): the OTP-leak guard now fails when the OTP leaks

It did not before. caplog cannot see structlog, so this test asserted a
string was absent from an empty string; a NullEmail logging both the code
and the destination address passed it 10/10. Re-armed on rendered output
and re-checked against that same mutant."
```

---

### Task 3: Log every HTTP refusal at the boundary

**Files:**
- Modify: `src/app/main.py` (add a handler beside `unhandled_error`)
- Test: `tests/test_error_logging.py` (create)

**Interfaces:**
- Consumes: `_route_template(request)` (exists, `src/app/main.py`),
  `log_events` fixture (Task 1)
- Produces: log event `"request_refused"` with keys `status`, `route`,
  `method`, `reason`, `request_id`

- [ ] **Step 1: Write the failing test**

Create `tests/test_error_logging.py`:

```python
"""Every refusal is findable. 138 HTTPException raises in routes.py reach one
handler, and none of routes.py is edited to make that true."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(services):
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c


def _refusals(events):
    return [e for e in events if e.get("event") == "request_refused"]


def test_a_404_is_logged_with_status_and_request_id(client, log_events):
    r = client.get("/candidates/does-not-exist-at-all")
    assert r.status_code == 404
    hits = _refusals(log_events)
    assert hits, "a 404 must leave a refusal line"
    assert hits[0]["status"] == 404
    assert hits[0]["request_id"], "must carry the id the caller was given"


def test_the_refusal_line_carries_the_request_id_the_caller_received(client, log_events):
    r = client.get("/candidates/does-not-exist-at-all")
    assert _refusals(log_events)[0]["request_id"] == r.headers["X-Request-ID"]


def test_a_refusal_is_logged_exactly_once(client, log_events):
    client.get("/candidates/does-not-exist-at-all")
    assert len(_refusals(log_events)) == 1, "a double-registered handler double-logs"


def test_an_unmatched_path_is_labelled_by_template_not_by_the_raw_path(client, log_events):
    """Bounded cardinality, the rule OPERATING.md §5 already sets for metrics:
    a scanner walking random URLs must not become unbounded log volume."""
    for suffix in ("aaa", "bbb", "ccc"):
        client.get(f"/no/such/route/{suffix}")
    routes = {e["route"] for e in _refusals(log_events)}
    assert routes == {"__unmatched__"}


def test_an_unmatched_path_logs_at_info_not_warning(client, log_events):
    """Scanner noise at warning is how an operator learns to ignore the
    channel, and then misses the customer being refused."""
    client.get("/no/such/route/at/all")
    assert _refusals(log_events)[0]["log_level"] == "info"


def test_a_matched_refusal_logs_at_warning(client, log_events):
    """A real request to a real route, refused, is the line an operator wants."""
    r = client.post("/candidates", json={})
    assert r.status_code in (401, 403, 422)
    events = [e for e in log_events if e.get("event") in ("request_refused", "request_invalid")]
    assert events and events[0]["log_level"] == "warning"


def test_the_response_body_is_unchanged_by_the_handler(client):
    """The wired UI and every smoke parse these bodies. Logging must be
    invisible on the wire."""
    r = client.get("/candidates/does-not-exist-at-all")
    assert r.status_code == 404
    assert "detail" in r.json()


def test_routes_py_contains_no_logging_call(client):
    """The 138 refusals are logged BECAUSE THEY HAPPENED, not because someone
    remembered. If this ever fails, the boundary handler has been bypassed and
    the next refusal added will be silent again."""
    from pathlib import Path

    import app.api.routes as routes_mod

    src = Path(routes_mod.__file__).read_text(encoding="utf-8")
    assert "log.warning" not in src and "log.error" not in src
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_error_logging.py -q
```

Expected: FAIL — no `request_refused` events exist yet.

- [ ] **Step 3: Add the handler in `src/app/main.py`**

Add to the imports at the top of `src/app/main.py`:

```python
from fastapi.exception_handlers import http_exception_handler
from starlette.responses import Response
```

Then, inside `create_app`, **immediately before** the existing
`@app.exception_handler(Exception)` block, insert:

```python
    @app.exception_handler(StarletteHTTPException)
    async def refused(request: Request, exc: StarletteHTTPException) -> Response:
        """Log every refusal ONCE, then answer exactly as FastAPI would.

        All 138 HTTPException raises in routes.py land here, plus Starlette's
        own 404s and 405s -- measured with a TestClient probe, not assumed. So
        routes.py is not edited at all: a refusal is logged because it
        happened, not because whoever wrote it remembered to.

        This is the gap the sprint opened on. Starlette answers HTTPException
        itself, so NONE of those 138 refusals ever reached the Exception
        handler below, and every 4xx veritas issued left exactly one artifact:
        a status integer in the access line. The runbook could count refusals
        and could not explain a single one.

        The detail goes on the line. That is consistent with the handler
        below, which already logs repr(exc) plus a full traceback -- this repo
        has already decided the operator's own log plane may hold exception
        text, and inventing a stricter second rule for 4xx would leave two.
        """
        rid = getattr(request.state, "request_id", "")
        template = _route_template(request)
        if exc.status_code >= 500:
            # A 503 (email_unavailable) is a real outage, not a refusal.
            emit = log.error
        elif template == "__unmatched__":
            # Nothing matched: a scanner walking URLs. At warning it is
            # indistinguishable from a customer being refused, which is how
            # alert fatigue starts and how the real line gets missed.
            emit = log.info
        else:
            emit = log.warning
        emit(
            "request_refused",
            status=exc.status_code,
            route=template,
            method=request.method,
            reason=str(exc.detail),
            request_id=rid,
        )
        return await http_exception_handler(request, exc)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_error_logging.py -q
```

Expected: 8 passed.

- [ ] **Step 5: Kill the mutant — delete the log call and confirm red**

Temporarily comment out the `emit(...)` call in the handler, then:

```bash
python -m pytest tests/test_error_logging.py -q
```

Expected: **FAIL**. Restore it with `git checkout src/app/main.py` **only if
you have not yet staged other work in that file** — otherwise re-add the call
by hand and verify with `grep -c request_refused src/app/main.py` (must be 1).

- [ ] **Step 6: Run the full suite**

```bash
python -m pytest -q 2>&1 | tail -5
```

Expected: baseline + 12, zero failures. **If any existing test now fails,
the wire format changed — that is a stop-and-fix, not an update-the-test.**

- [ ] **Step 7: Commit**

```bash
git add src/app/main.py tests/test_error_logging.py
git commit -m "feat(s93): log every HTTP refusal at the boundary

routes.py raises HTTPException 138 times and binds no logger. Starlette
answers those itself, so not one reached the 500 handler: every 4xx veritas
issued left a status integer in the access line and nothing else.

One handler covers all 138 plus Starlette's own 404s and 405s, and routes.py
is not edited -- a refusal is logged because it happened. Labelled by route
template so a scanner cannot become unbounded log volume, and unmatched paths
log at info so scanner noise does not drown the customer being refused."
```

---

### Task 4: Log validation refusals without leaking what was submitted

**Files:**
- Modify: `src/app/main.py`
- Test: `tests/test_error_logging.py` (append)

**Interfaces:**
- Consumes: `_route_template`, `log_events`, `log_output` (Tasks 1, 3)
- Produces: log event `"request_invalid"` with keys `status`, `route`,
  `method`, `fields` (a `list[str]`), `request_id`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_error_logging.py`:

```python
def test_a_validation_failure_is_logged_with_the_field_locations(client, log_events):
    r = client.post("/candidates", json={"resume_text": 12345, "domain": "genai"})
    assert r.status_code in (401, 403, 422)
    if r.status_code != 422:
        pytest.skip("route is auth-gated before validation on this build")
    hits = [e for e in log_events if e.get("event") == "request_invalid"]
    assert hits, "a 422 must leave a line"
    assert any("resume_text" in f for f in hits[0]["fields"])


def test_a_validation_failure_never_logs_the_submitted_value(client, log_output):
    """RequestValidationError.errors() carries an `input` key holding the RAW
    submitted value -- probed. Logging errors() wholesale would write resume
    text, candidate emails and login codes into the log, committing in this
    very sprint the leak the sprint exists to close."""
    secret = "alice@example.in-SECRET-OTP-123456"
    client.post("/candidates", json={"resume_text": secret, "domain": 999})
    assert secret not in log_output.text
    assert "SECRET-OTP" not in log_output.text
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_error_logging.py -q -k validation
```

Expected: FAIL — no `request_invalid` event exists.

- [ ] **Step 3: Add the handler in `src/app/main.py`**

Add to the imports:

```python
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
```

Insert immediately after the `refused` handler from Task 3:

```python
    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> Response:
        """Log WHERE the body failed, never WHAT was in it.

        `exc.errors()` carries an `input` key holding the caller's raw
        submitted value -- probed, not assumed:

            {"type": "int_parsing", "loc": ["body", "age"],
             "input": "alice@example.in-SECRET-OTP-123456"}

        So the obvious `errors=exc.errors()` would write resume text,
        candidate addresses and login codes straight into the log, committing
        in the sprint that closes the OTP-leak gap exactly the leak that gap
        was about. Only `loc` is copied, and a test asserts a submitted secret
        never reaches the rendered output.
        """
        rid = getattr(request.state, "request_id", "")
        fields = [".".join(str(p) for p in e.get("loc", ())) for e in exc.errors()]
        log.warning(
            "request_invalid",
            status=422,
            route=_route_template(request),
            method=request.method,
            fields=fields,
            request_id=rid,
        )
        return await request_validation_exception_handler(request, exc)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_error_logging.py -q
```

Expected: 10 passed (2 new).

- [ ] **Step 5: Prove the leak test can fail**

Temporarily change `fields=fields` to `fields=[str(e) for e in exc.errors()]`
and run:

```bash
python -m pytest tests/test_error_logging.py -q -k submitted_value
```

Expected: **FAIL** — the secret appears in the rendered output. Revert the
change and re-run; expected PASS.

- [ ] **Step 6: Full suite, then commit**

```bash
python -m pytest -q 2>&1 | tail -5
git add src/app/main.py tests/test_error_logging.py
git commit -m "feat(s93): log validation refusals by field, never by value

RequestValidationError.errors() carries an `input` key holding the caller's
raw submitted value, so the obvious errors=exc.errors() would have written
resume text and login codes into the log -- the leak this sprint exists to
close, committed by the sprint closing it. Only loc is logged, and the test
that proves it was checked against the leaking version."
```

---

### Task 5: End the three silent swallows

**Files:**
- Modify: `src/app/graph/nodes/ai_signals.py`
- Modify: `src/app/graph/nodes/plausibility.py`
- Modify: `src/app/profile_sources/service.py:111`
- Test: `tests/test_silent_swallows.py` (create)

**Interfaces:**
- Consumes: `log_events` (Task 1)
- Produces: log events `"ai_signals_llm_failed"`, `"plausibility_llm_failed"`,
  `"unmapped_skill_capture_failed"`

**Note on scope:** in both graph nodes the swallow sits in a **module-level**
`_llm_assessment` helper, while every node binds its logger *inside* the
factory (`ai_signals.py:58`, `plausibility.py:77`). The helper has no `log` in
scope, so each file needs a module-level logger. That is why these two were
silent while their siblings were not — not a decision, an accident of scope.

- [ ] **Step 1: Write the failing test**

Create `tests/test_silent_swallows.py`:

```python
"""An LLM outage must be visible. These three handlers degrade correctly and
said nothing, while their siblings (claim_extraction, probe_generation,
provenance) logged the identical failure."""

import pytest

from app.graph.nodes.ai_signals import _llm_assessment as ai_assess
from app.graph.nodes.plausibility import _llm_assessment as plaus_assess
from app.schemas.claims import CandidateContext, Claim


class _BoomLLM:
    async def acomplete_json(self, **kw):
        raise RuntimeError("vendor outage")


@pytest.mark.asyncio
async def test_ai_signals_logs_when_the_llm_fails(services, log_events):
    services.llm = _BoomLLM()
    result = await ai_assess(services, "some resume text")
    assert result == (None, [], ""), "the degradation itself must not change"
    assert any(e["event"] == "ai_signals_llm_failed" for e in log_events)


@pytest.mark.asyncio
async def test_plausibility_logs_when_the_llm_fails(services, log_events):
    services.llm = _BoomLLM()
    claim = Claim(id="c1", text="Built a thing", claim_type="project", specificity=0.5)
    ctx = CandidateContext()
    result = await plaus_assess(services, "genai", claim, ctx, [])
    assert result == (None, None, [], [], ""), "the degradation itself must not change"
    assert any(e["event"] == "plausibility_llm_failed" for e in log_events)


def test_unmapped_skill_capture_logs_when_curation_fails(services, log_events):
    from app.profile_sources.service import build_profile_source_service

    class _BoomCuration:
        def record_unmapped(self, *a, **kw):
            raise RuntimeError("curation down")

    svc = build_profile_source_service(services.settings)
    svc._curation = _BoomCuration()

    class _Skill:
        canonical = None
        name = "kubernetes"

    class _Signal:
        skills = [_Skill()]

        class source_type:
            value = "github"

    svc._capture_unmapped(_Signal())
    assert any(e["event"] == "unmapped_skill_capture_failed" for e in log_events)
```

If `Claim` or `CandidateContext` require different constructor arguments on
this build, read `src/app/schemas/claims.py` and adjust the literals — the
assertion is about the log event, not the claim's contents.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_silent_swallows.py -q
```

Expected: FAIL — no such events.

- [ ] **Step 3: Fix `src/app/graph/nodes/ai_signals.py`**

Add a module-level logger after the imports (near `_LLM_MAX_CONFIDENCE`):

```python
# Module level, because the swallow below lives in a module-level helper while
# the node factory binds its own logger locally. That scope mismatch is the
# whole reason this failure was silent and claim_extraction's was not.
_log = get_logger("node.ai_signals")
```

Then change the handler at line 43 from:

```python
    except Exception:
        return None, [], ""
```

to:

```python
    except Exception as exc:  # an LLM outage degrades this signal, loudly
        _log.warning("ai_signals_llm_failed", error=str(exc))
        return None, [], ""
```

- [ ] **Step 4: Fix `src/app/graph/nodes/plausibility.py`**

Add after the imports:

```python
# Module level; see ai_signals.py for why the node's own local logger is not
# in scope at the swallow below.
_log = get_logger("node.plausibility")
```

Change the handler at line 56 from:

```python
    except Exception:
        return None, None, [], [], ""
```

to:

```python
    except Exception as exc:  # an LLM outage degrades this claim, loudly
        _log.warning("plausibility_llm_failed", error=str(exc))
        return None, None, [], [], ""
```

- [ ] **Step 5: Fix `src/app/profile_sources/service.py`**

Add to the imports:

```python
from app.core.logging import get_logger
```

and a module-level binding after them:

```python
_log = get_logger("profile_sources.service")
```

Change lines 111-112 from:

```python
                except Exception:  # noqa: BLE001 — advisory capture, never fatal
                    pass
```

to:

```python
                except Exception as exc:  # noqa: BLE001 — advisory, never fatal
                    # Still never fatal. But a capture queue that has stopped
                    # accepting anything looks exactly like a taxonomy with
                    # nothing left to map, and those need telling apart.
                    _log.warning(
                        "unmapped_skill_capture_failed",
                        source_type=signal.source_type.value,
                        error=str(exc),
                    )
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python -m pytest tests/test_silent_swallows.py -q
```

Expected: 3 passed.

- [ ] **Step 7: Full suite, then commit**

```bash
python -m pytest -q 2>&1 | tail -5
git add src/app/graph/nodes/ai_signals.py src/app/graph/nodes/plausibility.py src/app/profile_sources/service.py tests/test_silent_swallows.py
git commit -m "fix(s93): an LLM outage in the two costliest signals is no longer silent

Both swallows sit in module-level _llm_assessment helpers while every node
binds its logger inside the factory, so the helper had no log in scope. That
scope accident -- not a decision -- is why these two said nothing while
claim_extraction, probe_generation and provenance all logged the identical
failure. The degradation is unchanged; only the silence goes."
```

---

### Task 6: The audit sink must not take the pipeline down, or vanish quietly

**Files:**
- Modify: `src/app/services/flywheel.py`
- Test: `tests/test_flywheel_io.py` (create)

**Interfaces:**
- Consumes: `log_events` (Task 1)
- Produces: log event `"flywheel_write_failed"`

- [ ] **Step 1: Write the failing test**

Create `tests/test_flywheel_io.py`:

```python
"""The flywheel is append-only audit. A blocked write must neither crash the
pipeline nor disappear -- on this machine (Windows/OneDrive) a locked file is
a recorded trap, not a hypothetical."""

from app.services.flywheel import JsonlFlywheel


def test_a_blocked_write_does_not_raise(settings, tmp_path, log_events, monkeypatch):
    fw = JsonlFlywheel(path=str(tmp_path / "fw.jsonl"), settings=settings)

    def _boom(*a, **kw):
        raise OSError("file is locked by another process")

    monkeypatch.setattr("builtins.open", _boom)
    fw.log({"event": "claim_verified"})   # must not raise
    assert any(e["event"] == "flywheel_write_failed" for e in log_events)


def test_a_normal_write_still_lands(settings, tmp_path):
    path = tmp_path / "fw.jsonl"
    fw = JsonlFlywheel(path=str(path), settings=settings)
    fw.log({"event": "claim_verified"})
    assert "claim_verified" in path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_flywheel_io.py -q
```

Expected: FAIL — `OSError: file is locked by another process` propagates.

- [ ] **Step 3: Guard the writer in `src/app/services/flywheel.py`**

Add to the imports:

```python
from app.core.logging import get_logger
```

and after them:

```python
_log = get_logger("flywheel")
```

Replace `JsonlFlywheel.log` with:

```python
    def log(self, record: dict) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(_stamp(record), ensure_ascii=False) + "\n")
        except OSError as exc:
            # An audit sink that cannot write must not take an evaluation down
            # with it -- but it must not disappear either. On Windows/OneDrive
            # a locked file is a recorded trap in this repo, and a flywheel
            # that has silently stopped recording looks identical to a quiet
            # week right up until someone tries to train on it.
            _log.error("flywheel_write_failed", path=self.path, error=str(exc))
```

Also guard `__init__`, which calls `os.makedirs` unguarded:

```python
    def __init__(self, path: Optional[str] = None, settings: Optional[Settings] = None) -> None:
        settings = settings or get_settings()
        self.path = path or settings.flywheel_path
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        except OSError as exc:
            # Same reasoning as log(): construction happens during service
            # build, so raising here refuses the whole process a working app
            # over an advisory sink.
            _log.error("flywheel_mkdir_failed", path=self.path, error=str(exc))
```

**`OSError`, not `Exception`:** a `TypeError` from a non-serializable record
is a real bug and must stay loud. Only the IO is tolerated.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_flywheel_io.py -q
```

Expected: 2 passed.

- [ ] **Step 5: Full suite, then commit**

```bash
python -m pytest -q 2>&1 | tail -5
git add src/app/services/flywheel.py tests/test_flywheel_io.py
git commit -m "fix(s93): a locked flywheel file no longer takes the pipeline with it

Append-only audit had unguarded IO, on a machine whose OneDrive file locks
are already a recorded trap. OSError only -- a non-serializable record is a
real bug and stays loud -- and the failure is logged, because a flywheel
that has silently stopped recording is indistinguishable from a quiet week."
```

---

### Task 7: Make store-layer races visible

**Files:**
- Modify: `src/app/auth/store.py:394`, `src/app/ledger/store.py:233`,
  `src/app/ratelimit/store.py:97`, `src/app/reports/store.py:88`,
  `src/app/reports/store.py:139`, `src/app/rights/store.py:82`
- Test: `tests/test_race_visibility.py` (create)

**Interfaces:**
- Consumes: `log_events` (Task 1)
- Produces: log event `"integrity_race"` with a `where` key

- [ ] **Step 1: Write the failing test**

Create `tests/test_race_visibility.py`:

```python
"""Six IntegrityError handlers do correct race handling and say nothing. A race
going from one a day to a thousand a minute is currently undetectable."""

import pytest

from app.auth.store import OrgNameTaken


def test_a_duplicate_org_name_race_is_logged(services, log_events):
    store = services.auth_store if hasattr(services, "auth_store") else None
    if store is None:
        pytest.skip("auth store not on the services bundle in this build")
    store.create_org(name="Acme Staffing", admin_email="a@acme.in")
    with pytest.raises(OrgNameTaken):
        store.create_org(name="Acme Staffing", admin_email="b@acme.in")
    assert any(e["event"] == "integrity_race" for e in log_events)
```

Read `tests/conftest.py` and `src/app/auth/store.py` for the real constructor
and method names before running; adjust the call, not the assertion. If no
store on the bundle exposes org creation directly, build it the way
`tests/test_auth_org_name_taken.py` does.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_race_visibility.py -q
```

Expected: FAIL — no `integrity_race` event.

- [ ] **Step 3: Add a logger and one line to each of the six handlers**

For **each** of the six files, add (if absent) to its imports:

```python
from app.core.logging import get_logger
```

and a module-level binding after them, named for the module, e.g. in
`src/app/auth/store.py`:

```python
_log = get_logger("auth.store")
```

Then add **one line as the first statement inside each `except IntegrityError`
block**, before the existing `rollback()`. For `auth/store.py:394`:

```python
            except IntegrityError as exc:
                _log.info("integrity_race", where="create_org", error=str(exc))
                session.rollback()
```

Use these `where` values, one per site — do not invent others, the label is
the whole point:

| File | line | `where` |
|---|---|---|
| `auth/store.py` | 394 | `"create_org"` |
| `ledger/store.py` | 233 | `"create_org"` |
| `ratelimit/store.py` | 97 | `"open_window"` |
| `reports/store.py` | 88 | `"save_report"` |
| `reports/store.py` | 139 | `"record_outcome"` |
| `rights/store.py` | 82 | `"record_request"` |

Where the existing handler has no `as exc` (e.g. `ratelimit/store.py:97`,
`reports/store.py:88`), add it.

**`info`, not `warning`:** these races are expected and handled correctly. The
value is the rate, not the event. At warning they would be noise that trains
an operator to ignore the channel.

**Behaviour must not change.** Add only the log line; leave every
`rollback()`, `raise`, and return exactly as it is.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_race_visibility.py -q
```

Expected: 1 passed.

- [ ] **Step 5: Full suite, then commit**

```bash
python -m pytest -q 2>&1 | tail -5
```

Expected: baseline + all new tests, zero failures. Six store files changed and
**no existing store test may move** — if one does, behaviour changed and that
is a stop-and-fix.

```bash
git add src/app/auth/store.py src/app/ledger/store.py src/app/ratelimit/store.py src/app/reports/store.py src/app/rights/store.py tests/test_race_visibility.py
git commit -m "feat(s93): make the six IntegrityError races visible

All six handle their race correctly and none said anything, so a race going
from one a day to a thousand a minute was undetectable. Labelled by site and
logged at info -- the value is the rate, not the event; at warning they would
train an operator to ignore the channel."
```

---

### Task 8: Smoke over real HTTP, and the runbook entry

**Files:**
- Create: `scripts/smoke_s93.py`
- Modify: `OPERATING.md` (add §12)

**Interfaces:**
- Consumes: `scripts/_smoke.py` (`Smoke`, `base_env`, `client`,
  `uvicorn_argv`, `wait_healthy`)
- Produces: nothing later tasks depend on

- [ ] **Step 1: Write the smoke**

Create `scripts/smoke_s93.py`:

```python
"""S9.3 smoke: refusals are findable in a REAL server's logs.

What a unit test cannot prove and this does:
  * the handlers are installed in the app uvicorn actually serves, not only in
    one built by a fixture;
  * the refusal line is JSON on stdout, as a log shipper would receive it --
    the unit tests assert on captured dicts, which is a different artifact;
  * `X-Request-ID` on the response is the SAME id as on the refusal line, so
    the correlation OPERATING.md §12 promises an operator actually works;
  * a submitted secret does not reach the log through the 422 path.

Run from the repo root:   python scripts/smoke_s93.py
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy

S = Smoke("smoke_s93")
PORT = 8093
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}
ROOT = Path(__file__).resolve().parent.parent
SECRET = "alice@example.in-SECRET-OTP-123456"


def main() -> int:
    scratch = Path(tempfile.mkdtemp(prefix="smoke_s93_"))
    env = base_env(scratch=scratch)
    env["DEE_ADMIN_API_KEY"] = ADMIN
    env["DEE_LOG_JSON"] = "true"

    # A FILE, never subprocess.PIPE: the server runs while we drive it, and a
    # full pipe buffer would deadlock the very process under test.
    logfile = scratch / "server.log"
    with open(logfile, "w", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            uvicorn_argv(PORT), env=env, cwd=str(ROOT), stdout=fh,
            stderr=subprocess.STDOUT, text=True,
        )
        try:
            with client(BASE, headers=ADMIN_H) as c:
                if not S.check("server_healthy", wait_healthy(c)):
                    return S.summary()

                r = c.get("/candidates/no-such-candidate-at-all")
                S.check("refusal_status_404", r.status_code == 404, f"HTTP {r.status_code}")
                rid = r.headers.get("X-Request-ID", "")
                S.check("response_carries_request_id", bool(rid))

                c.post("/candidates", json={"resume_text": SECRET, "domain": 999})

                # Give the server a moment to flush its stdout to the file.
                time.sleep(1.0)
        finally:
            proc.terminate()
            proc.wait(timeout=30)

    text = logfile.read_text(encoding="utf-8", errors="replace")
    lines = []
    for raw in text.splitlines():
        raw = raw.strip()
        if raw.startswith("{"):
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                pass

    refusals = [l for l in lines if l.get("event") == "request_refused"]
    S.check("refusal_line_emitted", bool(refusals), f"{len(lines)} json lines parsed")
    if refusals:
        S.check("refusal_line_has_status", refusals[0].get("status") == 404)
        S.check("refusal_line_has_route", bool(refusals[0].get("route")))
        S.check(
            "request_id_correlates",
            any(l.get("request_id") == rid for l in refusals),
            "no refusal line carried the id the caller received",
        )
    S.check("secret_not_in_logs", SECRET not in text, "a submitted value reached the log")
    S.check("otp_fragment_not_in_logs", "SECRET-OTP" not in text)
    return S.summary()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the smoke**

```bash
python scripts/smoke_s93.py
```

Expected: all checks pass. If `refusal_line_emitted` fails with `0 json lines
parsed`, `DEE_LOG_JSON` is not reaching the server — check `base_env` and the
settings name in `src/app/core/config.py` (`log_json`), and fix the env key
rather than loosening the check.

- [ ] **Step 3: Write OPERATING.md §12**

Insert a new section **before** `## 11. Deliberately not here` (so §11 stays
last), and renumber nothing else:

````markdown
## 12. Reading the logs

Until S9.3 the runbook could only count. `/metrics` answers "how many 403s";
it cannot answer **"why did *this* customer get one"**, and that is the
question a staffing agency actually asks. Every refusal now leaves a line.

**The vocabulary.** One line per failed request, alongside the `access` line
that has always been emitted. Correlate them by `request_id`, which is also
returned to the caller as the `X-Request-ID` header — so a customer quoting
that header is handing you the exact grep key.

| event | level | when |
|---|---|---|
| `access` | info | every request, with `status` and `duration_ms` |
| `request_refused` | warning | a 4xx on a route that matched |
| `request_refused` | info | a 404/405 that matched nothing (scanner noise) |
| `request_refused` | error | a 5xx HTTPException, e.g. `503 email_unavailable` |
| `request_invalid` | warning | a body Pydantic rejected; `fields` says where |
| `unhandled_error` | error | a bug — carries the full traceback |

**"A customer says they got a 403."**
1. Ask for the `X-Request-ID` from the response. Then:
   `grep '"request_id":"req_abc123"' server.log`
2. The `request_refused` line carries `reason` — the same detail string the
   caller received — plus `route` (the template) and `method`.
3. No `request_refused` line at that id means it was not a refusal. Look for
   `unhandled_error` at the same id: that is a bug, and the traceback is on it.

**"Is anything failing that nobody reported?"**
`grep '"event":"request_refused"' server.log | grep '"level":"error"'` — 5xx
refusals only. `503 email_unavailable` here means the email provider is down,
and logins are failing for everyone.

**What is deliberately NOT logged.** The `input` of a rejected body.
`RequestValidationError.errors()` carries the caller's raw submitted value,
which for this product is resume text, candidate addresses and login codes.
`request_invalid` logs `fields` (the locations) and never the values. If you
are ever tempted to add `errors=exc.errors()` to that handler, read
`tests/test_error_logging.py::test_a_validation_failure_never_logs_the_submitted_value`
first — it exists to stop exactly that.

**Log labels are bounded on purpose.** `route` is the route TEMPLATE, never
the raw path, and anything unmatched collapses to `__unmatched__` — the same
rule as §5's metrics labels, for the same reason: a scanner walking random
URLs must not become unbounded log volume.
````

- [ ] **Step 4: Full suite and every smoke that touches the API**

```bash
python -m pytest -q 2>&1 | tail -5
python scripts/smoke_s93.py
python scripts/smoke_s92.py
python scripts/smoke_s86.py
```

Expected: suite green; all three smokes pass. **A smoke failure here means the
wire format moved** — stop and fix the handler, do not adjust the smoke.

- [ ] **Step 5: Commit**

```bash
git add scripts/smoke_s93.py OPERATING.md
git commit -m "test(s93): smoke the refusal log over real HTTP, and write the runbook

The unit tests assert on captured dicts; a log shipper receives JSON on
stdout, which is a different artifact, so the smoke parses the real server's
real output. Also asserts the X-Request-ID a caller receives is the id on the
refusal line -- the correlation OPERATING.md §12 promises.

§12 gives the runbook its first log-based entry: every existing one says
GET /metrics, and a counter cannot explain a single refusal."
```

---

### Task 9: Whole-branch verification and roadmap

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Confirm the sprint's own claims**

```bash
python -m pytest -q 2>&1 | tail -5
git diff --stat main...HEAD
grep -c "get_logger" src/app/api/routes.py    # must print 0 — routes.py stays clean
```

- [ ] **Step 2: Re-check the two mutants that define the sprint**

The OTP mutant (Task 2 Step 3) and the `errors()` leak (Task 4 Step 5) are the
sprint's two load-bearing claims. Re-run both against the finished branch and
confirm each still turns a test red. A mutant that has stopped being killed
means a later task broke the guard.

- [ ] **Step 3: Update `docs/ROADMAP.md`**

Add S9.3 to the PI-9 board with the measured numbers (passing count, smoke
tally, mutants killed), and write a "Current state" entry covering: the
138-refusal blind spot and its one-handler fix; the vacuous OTP guard and the
mutation that proved it; the `input`-key leak the fix itself would have
introduced; and the `capture_logs`-bypasses-processors finding, which is the
reusable lesson.

- [ ] **Step 4: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(s93): roadmap — error observability complete"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1.2 Gap 1 (api blind spot) | Task 3, Task 4 |
| §1.2 Gap 2 (vacuous guard) | Task 1, Task 2 |
| §1.2 Gap 3 (silent swallows) | Task 5 |
| §1.2 Gap 4 (flywheel IO) | Task 6 |
| §1.2 Gap 5 (invisible races) | Task 7 |
| §2.1 two boundary handlers | Task 3, Task 4 |
| §2.2 PII decision (detail logged) | Task 3 |
| §2.3 two test seams | Task 1 |
| §2.3 `build_processors` refactor | Task 1 Step 3 |
| §2.3a `input`-key leak | Task 4 |
| §2.4 targeted fixes | Tasks 2, 5, 6, 7 |
| §2.5 OPERATING.md §12 | Task 8 |
| §4 success criteria 1–7 | Tasks 3, 8, 9 |

**Type consistency:** `build_processors(settings)` is defined in Task 1 Step 3
and consumed in Task 1 Step 4 only. `_route_template(request)` already exists
in `src/app/main.py` and is consumed unchanged in Tasks 3 and 4. Event names
(`request_refused`, `request_invalid`, `ai_signals_llm_failed`,
`plausibility_llm_failed`, `unmapped_skill_capture_failed`,
`flywheel_write_failed`, `flywheel_mkdir_failed`, `integrity_race`) are each
defined once and used consistently in their task's test, implementation, and
in OPERATING.md §12.

**Known soft spots, flagged rather than hidden:** Task 5's and Task 7's test
scaffolding constructs domain objects (`Claim`, `CandidateContext`, the auth
store) whose exact constructors were not read while planning. Each of those
steps says to read the real signature and adjust the *call*, never the
assertion. Task 3's `test_a_matched_refusal_logs_at_warning` accepts several
status codes because `POST /candidates` may be auth-gated before validation on
this build; the assertion is about the level, not the code.
