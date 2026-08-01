# S8.1 — Deployable Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **In THIS repo's sessions, agents may not be spawned unless the user asks.** Execute inline with superpowers:executing-plans unless told otherwise.

**Goal:** Make a fresh container boot into a working, non-public system: it migrates its own schema, refuses to start without an admin credential, keeps reports in the same database as their candidate behind a real `ON DELETE CASCADE`, runs on Postgres, and lives on Railway.

**Architecture:** Four independent changes plus a deploy. (1) A launch-time config guard + an always-enforcing admin gate. (2) `alembic upgrade head` in the lifespan, with a Postgres advisory lock so concurrent workers cannot race. (3) `reports`/`outcomes` move out of a private raw-`sqlite3` database into the main Alembic-managed one as a new `app/reports/` package, deleting `app/services/report_store.py` and `InMemoryReportStore`. (4) Postgres support: `psycopg`, `pool_pre_ping`, a `DEE_TEST_DB_URL` hook that runs the whole suite on PG, and a CI job. No new endpoint, no LLM, no new consent purpose.

**Tech Stack:** Python 3.11/3.12 · FastAPI · SQLAlchemy 2.0 + Alembic · SQLite (dev/test) + Postgres 16 (deploy/CI) · pytest · structlog · Railway.

**Spec:** `docs/superpowers/specs/2026-08-01-s81-deployable-spine-design.md`
**PI design:** `docs/superpowers/specs/2026-08-01-pi8-launch-readiness-design.md`

## Global Constraints

- **TDD.** Test first, watch it fail, then implement. `pytest -q` green before every commit.
- **Fully offline suite.** No network, no API key, no Postgres required for the default `pytest -q`. `NullLLM`/fakes only.
- **Advisory only.** Nothing here auto-rejects; no scoring changes at all.
- **DPDP:** erasure must remain complete. This sprint makes it *structural*.
- **Config:** tunables in `config.yaml`, secrets only in `.env` / environment with the `DEE_` prefix.
- **No knob restores fail-open admin auth**, and there is **no `env == "local"` exemption** (spec §0.1).
- **Commit messages: NO `Co-Authored-By` trailer.** House rule.
- Branch: `s81-deployable-spine`, off `main`.
- Every Alembic migration must spell column types **identically** to the ORM (the drift/index/FK/nullability guards in `tests/test_migrations.py` enforce this and have caught real drift before).

---

### Task 0: Provision Railway Postgres

**Files:** none (infrastructure only).

**Interfaces:**
- Produces: a Postgres connection URL (public proxy form, `postgresql+psycopg://...`) used by Task 8's verification and Task 10's deploy. Keep it out of git — it goes in `.env` locally.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b s81-deployable-spine
```

- [ ] **Step 2: Create the Railway project and a Postgres service**

Use the Railway MCP tools: `create_project` (name: `veritas`), then `create_service` selecting the Postgres database template in that project's `production` environment.

- [ ] **Step 3: Capture the public connection URL**

Read the Postgres service's `DATABASE_PUBLIC_URL` variable via `list_variables`. Convert the driver prefix for SQLAlchemy 2.0 + psycopg 3:

```
postgresql://...        →  postgresql+psycopg://...
```

- [ ] **Step 4: Put it in `.env` (NOT in git)**

```
DEE_TEST_DB_URL=postgresql+psycopg://postgres:<password>@<host>:<port>/railway
```

Confirm `.env` is git-ignored: `git check-ignore -v .env` must print a match.

- [ ] **Step 5: No commit** — nothing in the working tree changed.

---

### Task 1: `verify_launch_config` — the boot guard

**Files:**
- Create: `app/core/boot.py`
- Test: `tests/test_boot_config.py`

**Interfaces:**
- Produces: `app.core.boot.LaunchConfigError` (subclass of `RuntimeError`) and `verify_launch_config(settings: Settings) -> None`. Task 2 calls it from the lifespan.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_boot_config.py`:

```python
"""Launch-time refusals (S8.1). A misconfigured admin plane must stop the
process, not quietly serve an open one."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.core.boot import LaunchConfigError, verify_launch_config


def test_empty_admin_key_refuses_launch(settings):
    locked = settings.model_copy(update={"api_auth_key": SecretStr("")})
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(locked)
    assert "DEE_API_AUTH_KEY" in str(exc.value)


def test_whitespace_admin_key_is_treated_as_unset(settings):
    locked = settings.model_copy(update={"api_auth_key": SecretStr("   ")})
    with pytest.raises(LaunchConfigError):
        verify_launch_config(locked)


def test_configured_admin_key_launches(settings):
    ok = settings.model_copy(update={"api_auth_key": SecretStr("a-real-key")})
    assert verify_launch_config(ok) is None


def test_no_local_exemption(settings):
    """env defaults to 'local'; the guard must not care (spec 0.1)."""
    for env in ("local", "staging", "prod"):
        locked = settings.model_copy(
            update={"api_auth_key": SecretStr(""), "env": env}
        )
        with pytest.raises(LaunchConfigError):
            verify_launch_config(locked)


def test_prod_on_sqlite_refuses_launch(settings):
    """A prod container on SQLite loses every row on redeploy (ephemeral disk)
    and serializes writes across workers."""
    locked = settings.model_copy(update={
        "api_auth_key": SecretStr("a-real-key"),
        "env": "prod",
        "candidates_db_url": "sqlite:///./data/veritas.db",
    })
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(locked)
    assert "DEE_CANDIDATES_DB_URL" in str(exc.value)


def test_prod_on_postgres_launches(settings):
    ok = settings.model_copy(update={
        "api_auth_key": SecretStr("a-real-key"),
        "env": "prod",
        "candidates_db_url": "postgresql+psycopg://u:p@h:5432/db",
    })
    assert verify_launch_config(ok) is None


def test_local_on_sqlite_launches(settings):
    ok = settings.model_copy(update={"api_auth_key": SecretStr("a-real-key")})
    assert verify_launch_config(ok) is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest tests/test_boot_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.boot'`

- [ ] **Step 3: Implement `app/core/boot.py`**

```python
"""Launch-time configuration checks (PI-8 S8.1).

`require_api_key` refuses every request when no credential is configured, but a
service that 401s everything looks merely broken. This module makes the
misconfiguration loud at the one moment an operator is watching: boot.

There is deliberately NO `env` exemption (spec 0.1). `env` DEFAULTS to "local",
so an env-gated escape would make a safe deploy depend on remembering two
variables instead of one -- the same fail-open shape, one indirection deeper.
"""

from __future__ import annotations

from app.core.config import Settings


class LaunchConfigError(RuntimeError):
    """The process must not start with this configuration."""


def verify_launch_config(settings: Settings) -> None:
    """Raise LaunchConfigError if this configuration must not serve traffic."""
    if not settings.api_auth_key.get_secret_value().strip():
        raise LaunchConfigError(
            "DEE_API_AUTH_KEY is not set. The admin plane -- including "
            "POST /candidates/{id}/auth-key, which mints any candidate's access "
            "key -- would be unguarded, so the service refuses to start. Set "
            "DEE_API_AUTH_KEY in the environment or .env (e.g. "
            "`openssl rand -hex 32`). There is no local-development exemption."
        )
    if settings.env == "prod" and settings.candidates_db_url.startswith("sqlite"):
        raise LaunchConfigError(
            "DEE_ENV=prod with a SQLite DEE_CANDIDATES_DB_URL. Container disks "
            "are ephemeral (every row is lost on redeploy) and SQLite "
            "serializes writes across workers. Point DEE_CANDIDATES_DB_URL at "
            "Postgres."
        )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_boot_config.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/core/boot.py tests/test_boot_config.py
git commit -m "feat(s81): boot guard -- refuse to start with no admin key, or prod on SQLite

No env exemption: env DEFAULTS to local, so an env-gated escape would make a
safe deploy depend on remembering two variables instead of one."
```

---

### Task 2: Close the admin gate everywhere

This is the task PI-8 §1.1 warned is wide, not deep. The gate flip breaks every test and smoke that relied on the open door; they are fixed in the same commit because the suite cannot be green in between.

**Files:**
- Modify: `app/api/routes.py:76-82` (the gate), `app/main.py` (lifespan), `tests/conftest.py`
- Modify: `tests/test_api.py:179-181` (invert the test that pinned the defect), plus every test module that builds a `TestClient` against admin routes
- Modify: `scripts/smoke_s11.py`, `smoke_s12.py`, `smoke_s13.py`, `smoke_s14.py`, `smoke_s21.py`, `smoke_s22.py`, `smoke_s23.py`, `smoke_s24.py`, `smoke_s31.py`
- Create: `tests/test_api_auth_gate.py`

**Interfaces:**
- Consumes: `verify_launch_config` from Task 1.
- Produces: `tests.conftest.ADMIN_KEY` (str), `tests.conftest.ADMIN_HEADERS` (dict), and an `admin_headers` fixture. Every later task's HTTP test uses these.

- [ ] **Step 1: Write the failing gate tests**

Create `tests/test_api_auth_gate.py`:

```python
"""The admin plane fails CLOSED (S8.1).

These tests assert REFUSALS. A suite that only ever sends a valid credential
cannot tell "authorized" from "unguarded" -- which is exactly how the fail-open
default survived eight PIs and four branch reviews.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.routes import require_api_key
from app.core.boot import LaunchConfigError
from app.main import create_app
from tests.conftest import ADMIN_HEADERS, ADMIN_KEY, make_services

RESUME = "Asha Rao\nEXPERIENCE\n- ML Engineer, Acme AI (2021 - Present)\n"


def _client(settings, flywheel, **client_kwargs):
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    return TestClient(app, raise_server_exceptions=False, **client_kwargs)


def test_no_configured_key_refuses_to_boot(settings, flywheel):
    """The empty key is the MOST refusing state, not the least."""
    open_settings = settings.model_copy(update={"api_auth_key": SecretStr("")})
    with pytest.raises(LaunchConfigError):
        with _client(open_settings, flywheel):
            pass


def test_absent_header_is_401(settings, flywheel):
    with _client(settings, flywheel) as client:
        assert client.post("/evaluate", json={"resume_text": RESUME}).status_code == 401
        assert client.get("/report/rep_x").status_code == 401


def test_wrong_header_is_401(settings, flywheel):
    with _client(settings, flywheel) as client:
        resp = client.post(
            "/evaluate", json={"resume_text": RESUME}, headers={"X-API-Key": "nope"}
        )
        assert resp.status_code == 401


def test_correct_header_is_allowed(settings, flywheel):
    with _client(settings, flywheel) as client:
        resp = client.post(
            "/evaluate", json={"resume_text": RESUME}, headers=ADMIN_HEADERS
        )
        assert resp.status_code == 200


def test_healthz_and_root_stay_open(settings, flywheel):
    with _client(settings, flywheel) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/").status_code == 200


def test_every_admin_route_carries_the_gate(settings, flywheel):
    """Walked from the app, not listed by hand: a new admin endpoint cannot be
    added outside the gate without failing here."""
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    from app.api.routes import router

    gated_paths = {r.path for r in router.routes}
    for route in app.routes:
        if getattr(route, "path", None) not in gated_paths:
            continue
        deps = [d.call for d in getattr(route, "dependencies", [])]
        deps += [d.call for d in route.dependant.dependencies]
        assert require_api_key in deps, f"{route.path} is not behind require_api_key"


def test_admin_key_is_never_echoed(settings, flywheel):
    """A 401 body must not leak the expected value."""
    with _client(settings, flywheel) as client:
        body = client.get("/report/rep_x").text
        assert ADMIN_KEY not in body
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest tests/test_api_auth_gate.py -q`
Expected: FAIL — `ImportError: cannot import name 'ADMIN_KEY' from 'tests.conftest'`

- [ ] **Step 3: Add the test credential to `tests/conftest.py`**

Above the `settings` fixture:

```python
#: The suite runs against a CONFIGURED admin key (S8.1). Before this, the whole
#: suite ran fail-open, so no test could tell "authorized" from "unguarded".
ADMIN_KEY = "test-admin-key"
ADMIN_HEADERS = {"X-API-Key": ADMIN_KEY}
```

Change the `settings` fixture body to set it, and add the header fixture:

```python
@pytest.fixture
def settings(monkeypatch) -> Settings:
    # Hermetic: bypass both .env and config.yaml so tests run on code defaults,
    # independent of any local config the developer may have changed.
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(
        _env_file=None, openrouter_api_key="", api_auth_key=SecretStr(ADMIN_KEY)
    )


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return dict(ADMIN_HEADERS)
```

Add `from pydantic import SecretStr` to the conftest imports.

- [ ] **Step 4: Flip the gate in `app/api/routes.py`**

Replace lines 76-82 with:

```python
async def require_api_key(
    request: Request, x_api_key: Optional[str] = Header(default=None)
) -> None:
    """Admin-plane gate (FR-15), fail-CLOSED since S8.1.

    An unset credential is the MOST refusing state, not the least: before this,
    `DEE_API_AUTH_KEY` being forgotten made all 27 admin endpoints public,
    including the one that mints any candidate's access key. `verify_launch_config`
    stops the process before it can serve in that state; this is the second
    layer, so an app built without the lifespan is still guarded.
    """
    expected = _services(request).settings.api_auth_key.get_secret_value()
    if not expected or not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
```

Add `import hmac` to the stdlib imports at the top of the module.

- [ ] **Step 5: Call the guard from the lifespan in `app/main.py`**

Inside `lifespan`, immediately after `configure_logging()`:

```python
        boot_settings = services.settings if services is not None else get_settings()
        verify_launch_config(boot_settings)
```

Add the imports:

```python
from app.core.boot import verify_launch_config
from app.core.config import get_settings
```

- [ ] **Step 6: Run the gate tests**

Run: `pytest tests/test_api_auth_gate.py -q`
Expected: PASS (7 tests)

- [ ] **Step 7: Invert the test that pinned the defect**

In `tests/test_api.py`, replace `test_auth_open_by_default` (lines 179-181):

```python
def test_auth_refuses_when_no_key_is_sent(api):
    """S8.1: was `test_auth_open_by_default`. The suite now runs WITH a
    configured admin key, and a client that sends none is refused."""
    client, _ = api
    bare = TestClient(client.app, raise_server_exceptions=False)
    with bare:
        assert bare.post("/evaluate", json={"resume_text": RESUME}).status_code == 401
```

- [ ] **Step 8: Give every admin-plane TestClient the header**

`TestClient` accepts default `headers=`, so this is **one line per fixture**, not one per call site.

Find them: `grep -rn "TestClient(" tests/`

For each construction used against admin routes, add the default header:

```python
from tests.conftest import ADMIN_HEADERS
...
    with TestClient(app, raise_server_exceptions=False, headers=ADMIN_HEADERS) as client:
```

Leave alone: clients built *deliberately* to test a refusal (Task 2 Step 1 and Step 7). Org-plane and candidate-plane tests are unaffected by a default `X-API-Key` — `require_org`/`require_candidate` read their own headers.

- [ ] **Step 9: Run the whole suite and fix the stragglers**

Run: `pytest -q`
Expected: some failures remain — every one is a call site that still reaches an admin route without a credential. Fix each by adding the default header to its client. Repeat until green.

Expected final: **1175 passed** plus the 7 new gate tests and Task 1's 7 = **1189**.

- [ ] **Step 10: Fix the nine key-less smokes**

For each of `scripts/smoke_s11.py`, `s12`, `s13`, `s14`, `s21`, `s22`, `s23`, `s24`, `s31`:

1. Add `ADMIN = "smoke-admin-key"` near the other module constants.
2. Add `"DEE_API_AUTH_KEY": ADMIN,` to the subprocess `env.update({...})` block.
3. Add `admin_h = {"X-API-Key": ADMIN}` beside the client setup and pass `headers=admin_h` on every admin call.

Copy the shape from `scripts/smoke_s32.py:53`, which already does exactly this.

- [ ] **Step 11: Run two smokes to prove the shape**

Run: `python scripts/smoke_s13.py` then `python scripts/smoke_s31.py`
Expected: both exit 0, all checks OK.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "feat(s81)!: the admin plane fails closed

An unset DEE_API_AUTH_KEY made all 27 admin endpoints public, including
POST /candidates/{id}/auth-key (mints any candidate's key = full impersonation
of a data principal). It is the house fail-open shape for the fourth time.

Two layers, because they fail differently: the gate now refuses when no key is
configured, and verify_launch_config stops the process before it can serve in
that state. No knob and no env exemption restores the old behaviour.

Wide, as measured: conftest now configures a test credential, every admin-plane
TestClient carries it by default, and the nine smokes that never sent one
(s11..s31) now do. test_auth_open_by_default is INVERTED -- it was the test
pinning the defect in place."
```

---

### Task 3: Migrate on boot

**Files:**
- Create: `app/core/migrate.py`, `tests/test_migrate_on_boot.py`
- Modify: `app/main.py` (lifespan), `app/core/config.py` (one knob), `config.yaml`, `Dockerfile`

**Interfaces:**
- Consumes: `Settings.candidates_db_url`.
- Produces: `app.core.migrate.upgrade_to_head(settings: Settings) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_migrate_on_boot.py`:

```python
"""Blocker 1 (gap-analysis v2 §9): nothing ran `alembic upgrade head` in the
boot path, so a fresh container started against no schema at all."""

from __future__ import annotations

from sqlalchemy import inspect

from app.core.db import make_engine
from app.core.migrate import upgrade_to_head


def test_upgrade_to_head_builds_the_schema_from_empty(settings, tmp_path):
    url = "sqlite:///" + (tmp_path / "fresh.db").as_posix()
    fresh = settings.model_copy(update={"candidates_db_url": url})

    upgrade_to_head(fresh)

    names = set(inspect(make_engine(url)).get_table_names())
    assert {"candidates", "organizations", "interview_sessions"} <= names
    assert "alembic_version" in names


def test_upgrade_to_head_is_idempotent(settings, tmp_path):
    url = "sqlite:///" + (tmp_path / "twice.db").as_posix()
    fresh = settings.model_copy(update={"candidates_db_url": url})

    upgrade_to_head(fresh)
    upgrade_to_head(fresh)  # a second boot must be a no-op, not an error

    assert "candidates" in set(inspect(make_engine(url)).get_table_names())
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_migrate_on_boot.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.migrate'`

- [ ] **Step 3: Implement `app/core/migrate.py`**

```python
"""Run Alembic to head at boot (PI-8 blocker 1).

Nothing in the repo migrated anything: `alembic upgrade head` lived only in
developer muscle memory and in the smoke scripts. A fresh container therefore
started against an empty database and failed at the first query.

Postgres boots take an advisory lock for the duration. Blocker 2's fix is
multiple uvicorn workers, and multiple workers boot at once -- without the lock
they race the same migration. SQLite serializes writes already.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import Settings
from app.core.db import make_engine
from app.core.logging import get_logger

log = get_logger("migrate")

ROOT = Path(__file__).resolve().parents[2]

#: Arbitrary but FIXED -- every process must ask for the same lock.
_MIGRATION_LOCK_KEY = 81_000_001


def _alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade_to_head(settings: Settings) -> None:
    """Bring settings.candidates_db_url up to the latest revision."""
    url = settings.candidates_db_url
    cfg = _alembic_config(url)

    if url.startswith("sqlite"):
        command.upgrade(cfg, "head")
    else:
        # Session-scoped lock: held on THIS connection while Alembic migrates on
        # its own. A second worker blocks here until the first is done.
        engine = make_engine(url)
        try:
            with engine.connect() as conn:
                conn.execute(
                    text("SELECT pg_advisory_lock(:k)"), {"k": _MIGRATION_LOCK_KEY}
                )
                conn.commit()
                try:
                    command.upgrade(cfg, "head")
                finally:
                    conn.execute(
                        text("SELECT pg_advisory_unlock(:k)"),
                        {"k": _MIGRATION_LOCK_KEY},
                    )
                    conn.commit()
        finally:
            engine.dispose()

    log.info("migrations_applied", backend=url.split("://", 1)[0])
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_migrate_on_boot.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Add the knob**

In `app/core/config.py`, in the `--- Service ---` block beside `env`:

```python
    # Run `alembic upgrade head` at startup (PI-8 blocker 1). This exists for
    # the operator who migrates as a separate deploy step -- NOT as a bypass: a
    # False boot against an empty DB fails loudly at the first query.
    db_migrate_on_boot: bool = True
```

In `config.yaml`, beside the other service settings:

```yaml
db_migrate_on_boot: true
```

- [ ] **Step 6: Wire it into the lifespan**

In `app/main.py`, after `verify_launch_config(boot_settings)`:

```python
        # Injected services (tests) already own a schema; only a real boot migrates.
        if services is None and boot_settings.db_migrate_on_boot:
            upgrade_to_head(boot_settings)
```

Import: `from app.core.migrate import upgrade_to_head`.

- [ ] **Step 7: Fix the Dockerfile**

`COPY app ./app` and `COPY config.yaml .` are all the image gets today, so `upgrade_to_head` would raise in the container and nowhere else. After the `COPY config.yaml .` line add:

```dockerfile
# Alembic ships in the image: the app migrates itself on boot (PI-8 blocker 1).
COPY alembic ./alembic
COPY alembic.ini .
```

- [ ] **Step 8: Run the full suite**

Run: `pytest -q`
Expected: green (no count change beyond Task 3's 2 new tests).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(s81): migrate on boot, and ship alembic in the image

alembic upgrade head ran NOWHERE in the boot path, so a fresh container started
against no schema. Postgres boots take a session-scoped advisory lock: blocker
2's fix is multiple workers, and multiple workers boot at once.

The Dockerfile copied app/ and config.yaml only -- without alembic/ and
alembic.ini in the image this would have failed in the container and nowhere
else."
```

---

### Task 4: `reports` + `outcomes` ORM, migration `0016`, and the cascade test FIRST

Spec §5.3 and PI-8 §5 fix this order: the cascade regression test is written **before** the store and must pass with **no route-layer orchestration**. Written last, it would let the old convention quietly survive the migration.

**Files:**
- Create: `app/reports/__init__.py`, `app/reports/schema.py`, `app/reports/models.py`, `alembic/versions/0016_reports_outcomes.py`, `tests/test_report_cascade.py`
- Modify: `tests/conftest.py` (register the new models on `Base.metadata`), `tests/test_migrations.py` (extend the guards), `alembic/env.py`

**Interfaces:**
- Produces: `app.reports.models.ReportRow`, `app.reports.models.OutcomeRow`; `app.reports.schema.OutcomeLabel`, `app.reports.schema.OutcomeRecord`. Task 5 builds the store on these.

- [ ] **Step 1: Write the failing cascade test**

Create `tests/test_report_cascade.py`:

```python
"""The point of folding reports into the main DB (PI-8 §2.1).

Before this, `reports` lived in a second SQLite database with no foreign key to
`candidates`. Erasure worked only because two route handlers each remembered to
call `delete_for_candidate` before `delete_candidate`. Nothing enforced it, no
FK could catch a third entry point forgetting, and no error would be raised --
the full depth evaluation, verdicts and fabrication analysis of an erased person
would simply be orphaned.

These tests use NO route and NO report store. If they pass, the guarantee is in
the database.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.reports.models import OutcomeRow, ReportRow
from tests.conftest import make_candidate_store


def _seed(store, *, candidate_id: str | None) -> str:
    with store._session_factory() as s:
        s.add(ReportRow(
            id="rep_cascade_1", domain="genai", depth_band="solid",
            candidate_id=candidate_id, body={"id": "rep_cascade_1"},
            created_at=datetime.now(timezone.utc),
        ))
        s.add(OutcomeRow(
            report_id="rep_cascade_1", claim_id=None, outcome="inconclusive",
            notes="", recorded_at=datetime.now(timezone.utc),
        ))
        s.commit()
    return "rep_cascade_1"


def test_deleting_a_candidate_cascades_their_reports():
    store = make_candidate_store()
    cid = store.upsert_candidate_profile_only()
    _seed(store, candidate_id=cid)

    store.delete_candidate(cid)

    with store._session_factory() as s:
        assert s.execute(select(ReportRow)).scalars().all() == []


def test_deleting_a_candidate_cascades_outcomes_too():
    store = make_candidate_store()
    cid = store.upsert_candidate_profile_only()
    _seed(store, candidate_id=cid)

    store.delete_candidate(cid)

    with store._session_factory() as s:
        assert s.execute(select(OutcomeRow)).scalars().all() == []


def test_an_unattached_report_survives_every_erasure():
    """POST /evaluate makes reports with no candidate. Nullable + CASCADE is
    correct: an attached report dies with its subject, an unattached one was
    never personal data."""
    store = make_candidate_store()
    cid = store.upsert_candidate_profile_only()
    _seed(store, candidate_id=None)

    store.delete_candidate(cid)

    with store._session_factory() as s:
        assert len(s.execute(select(ReportRow)).scalars().all()) == 1
```

**Note for the implementer:** `upsert_candidate_profile_only` is a placeholder for whatever minimal candidate-creation helper `CandidateStore` exposes. Open `app/candidates/store.py`, find the method the existing tests use to create a bare candidate (e.g. `tests/test_candidate_store.py`), and use that. Do not add a new store method.

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_report_cascade.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reports'`

- [ ] **Step 3: Create the package and the schema module**

`app/reports/__init__.py`:

```python
"""Durable reports + human outcome records, in the MAIN database (S8.1).

Folded out of `app/services/report_store.py`, which was raw stdlib sqlite3 in a
second database file: no foreign key to `candidates`, no cascade, no atomicity
with candidate erasure, and a bespoke `ALTER TABLE ... ADD COLUMN` in a
try/except standing in for a migration system. See PI-8 §2.1.
"""
```

`app/reports/schema.py` — moved verbatim from `app/services/report_store.py`:

```python
"""Human outcome records (FR-7/FR-8): how a reviewer closed the loop."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class OutcomeLabel(StrEnum):
    """How a human closed the loop on a report/claim."""

    VERIFIED_GENUINE = "verified_genuine"
    VERIFIED_FABRICATED = "verified_fabricated"
    CANDIDATE_CLARIFIED = "candidate_clarified"
    INCONCLUSIVE = "inconclusive"


class OutcomeRecord(BaseModel):
    """One human judgment; claim_id=None means it applies to the whole report."""

    report_id: str
    claim_id: Optional[str] = None
    outcome: OutcomeLabel
    notes: str = ""
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: Create `app/reports/models.py`**

```python
"""ORM rows for reports + outcomes (S8.1). Postgres-shaped on SQLite.

`candidate_id` is nullable AND cascading, and both halves are deliberate:
`POST /evaluate` produces reports with no candidate attached (it predates the
candidate backbone), while an ATTACHED report must die with its subject. An
unattached report was never personal data.

`body` is the serialized Report. Schema evolution stays Pydantic's job, not
SQL's -- the same call the raw-sqlite3 store made, kept.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON, DateTime, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ReportRow(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    domain: Mapped[str] = mapped_column(String(32))
    depth_band: Mapped[str] = mapped_column(String(32))
    candidate_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True
    )
    body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Composite: `for_candidate` filters on candidate_id and orders by
    # created_at, and the leftmost column serves the plain lookup too.
    __table_args__ = (
        Index("ix_reports_candidate_created", "candidate_id", "created_at"),
    )


class OutcomeRow(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True
    )
    claim_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(Text, default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 5: Register the models with `Base.metadata` in both loaders**

In `tests/conftest.py`, beside the other `noqa: F401` model imports:

```python
import app.reports.models  # noqa: F401 — populate Base.metadata with report tables
```

In `alembic/env.py`, beside the other model imports:

```python
import app.reports.models  # noqa: F401 — register report tables on Base.metadata
```

- [ ] **Step 6: Run the cascade test — it must still fail, now for the right reason**

Run: `pytest tests/test_report_cascade.py -q`
Expected: PASS. (`make_candidate_store` runs `Base.metadata.create_all`, so the tables exist and the cascade is real.) If it FAILS with rows still present, the FK or `PRAGMA foreign_keys=ON` is wrong — fix before continuing; this test is the sprint's whole point.

- [ ] **Step 7: Write the migration `alembic/versions/0016_reports_outcomes.py`**

```python
"""reports + outcomes folded into the main database (S8.1)

Revision ID: 0016_reports_outcomes
Revises: 0015_ai_interviews
Create Date: 2026-08-01

These two tables lived in a second, raw-sqlite3 database with no foreign key to
`candidates`. DPDP erasure across the two was a CONVENTION -- two route handlers
that each remembered to delete reports before the candidate -- and a third entry
point forgetting one line would orphan an erased person's full evaluation.

reports.candidate_id -> candidates.id ON DELETE CASCADE makes that
unrepresentable. Nullable, because POST /evaluate produces candidate-less
reports.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_reports_outcomes"
down_revision = "0015_ai_interviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("depth_band", sa.String(length=32), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_reports_candidate_created", "reports", ["candidate_id", "created_at"]
    )

    op.create_table(
        "outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("report_id", sa.String(length=64), nullable=False),
        sa.Column("claim_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_outcomes_report_id", "outcomes", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_outcomes_report_id", table_name="outcomes")
    op.drop_table("outcomes")
    op.drop_index("ix_reports_candidate_created", table_name="reports")
    op.drop_table("reports")
```

- [ ] **Step 8: Extend the migration guards in `tests/test_migrations.py`**

Add the model import beside the others:

```python
import app.reports.models  # noqa: F401 — populate Base.metadata
```

Add the table tuple beside `VERIFICATION_TABLES`:

```python
REPORT_TABLES = ("reports", "outcomes")  # S8.1 — reports CASCADE from candidates
```

Append `+ REPORT_TABLES` to the loop tuples in **both** `test_migrated_indexes_match_orm` and `test_migrated_fks_and_nullability_match_orm`.

In `test_upgrade_head_creates_candidate_tables`, add:

```python
    assert "reports" in names  # S8.1 migration 0016
    assert "outcomes" in names  # S8.1 migration 0016
```

- [ ] **Step 9: Run the migration guards**

Run: `pytest tests/test_migrations.py -q`
Expected: PASS. The drift guard (`test_migrated_schema_matches_orm_models`) is the one that catches a type or nullability mismatch between Step 4 and Step 7 — if it fails, the migration is wrong, not the test.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(s81): reports + outcomes ORM and migration 0016 -- cascade first

The cascade regression test is written BEFORE the store and passes with no
route-layer orchestration at all. That ordering is the point: written last, it
would let the old convention quietly survive the migration and prove nothing.

reports.candidate_id -> candidates.id ON DELETE CASCADE, nullable because
POST /evaluate produces candidate-less reports. An attached report now dies with
its subject structurally; an unattached one was never personal data."
```

---

### Task 5: `SqlReportStore` — and delete both old stores

**Files:**
- Create: `app/reports/store.py`
- Delete: `app/services/report_store.py`
- Modify: `app/services/__init__.py`, `app/api/routes.py` (import only), `app/features/context.py`, `app/features/materialize.py`, `app/interview/service.py`, `app/interview/models.py` (a stale comment), `app/portal/service.py`, `tests/conftest.py`, and the 8 test modules that import `InMemoryReportStore`
- Modify: `tests/test_report_store.py`

**Interfaces:**
- Consumes: `ReportRow`, `OutcomeRow`, `OutcomeRecord`, `OutcomeLabel` (Task 4).
- Produces: `app.reports.store.ReportStore` (Protocol), `app.reports.store.SqlReportStore(session_factory)`, `app.reports.store.build_report_store(settings) -> ReportStore`. The Protocol keeps 6 methods: `save`, `get`, `add_outcome`, `outcomes`, `delete`, `for_candidate`. **`delete_for_candidate` is gone.**

- [ ] **Step 1: Point the existing store tests at the new store**

In `tests/test_report_store.py`, replace the imports and the fixture:

```python
from app.reports.schema import OutcomeLabel, OutcomeRecord
from app.reports.store import SqlReportStore, build_report_store
from app.schemas.report import Report
from tests.conftest import make_candidate_store


@pytest.fixture
def store():
    """The REAL store on an in-memory SQLite session factory. There is no
    in-memory fake any more: a dict cannot cascade, and a fake that cannot
    cascade would hide the guarantee this sprint exists to create."""
    return SqlReportStore(make_candidate_store()._session_factory)
```

Delete any test that asserts on `delete_for_candidate` and any `Path`/`tmp_path` plumbing the SQLite file store needed.

**Expected new failure mode, and it is real:** a test that saves a `Report` with `candidate_id="c1"` when no such candidate row exists now hits an FK violation. That is the constraint working. Fix such tests by creating the candidate first through `make_candidate_store()`, exactly as production does (`POST /candidates` stores the candidate before evaluating).

- [ ] **Step 2: Run and watch it fail**

Run: `pytest tests/test_report_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reports.store'`

- [ ] **Step 3: Implement `app/reports/store.py`**

```python
"""Report store — durable reports + human outcome records, on the MAIN database.

Reports must survive a process restart (FR-6) and human reviewers close the
flywheel loop by recording outcomes against them (FR-7/FR-8). The resume text
itself is never persisted (DPDP / NFR-4): the Report schema does not contain it,
only derived claims.

S8.1 moved this off raw stdlib sqlite3 in a second database file. Erasure is no
longer a convention two route handlers remember -- it is
`reports.candidate_id -> candidates.id ON DELETE CASCADE`, which is why this
module has no `delete_for_candidate` at all.
"""

from __future__ import annotations

from typing import Optional, Protocol

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.ledger.consent import as_utc
from app.reports.models import OutcomeRow, ReportRow
from app.reports.schema import OutcomeLabel, OutcomeRecord
from app.schemas.report import Report


class ReportStore(Protocol):
    def save(self, report: Report) -> None: ...
    def get(self, report_id: str) -> Optional[Report]: ...
    def add_outcome(self, rec: OutcomeRecord) -> None: ...
    def outcomes(self, report_id: str) -> list[OutcomeRecord]: ...
    def delete(self, report_id: str) -> bool: ...
    def for_candidate(self, candidate_id: str) -> list[Report]: ...


class SqlReportStore:
    """SQLAlchemy-backed, sharing the main DB's session factory."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def save(self, report: Report) -> None:
        """Upsert. (The old store used INSERT OR REPLACE, which Postgres does
        not have -- the SQL had to be rewritten whatever we did here.)"""
        with self._session_factory() as s:
            row = s.get(ReportRow, report.id)
            if row is None:
                row = ReportRow(id=report.id)
                s.add(row)
            row.domain = report.domain
            row.depth_band = report.depth_band.value
            row.candidate_id = report.candidate_id
            row.body = report.model_dump(mode="json")
            row.created_at = as_utc(report.created_at)
            s.commit()

    def get(self, report_id: str) -> Optional[Report]:
        with self._session_factory() as s:
            row = s.get(ReportRow, report_id)
            return Report.model_validate(row.body) if row is not None else None

    def add_outcome(self, rec: OutcomeRecord) -> None:
        with self._session_factory() as s:
            s.add(OutcomeRow(
                report_id=rec.report_id, claim_id=rec.claim_id,
                outcome=rec.outcome.value, notes=rec.notes,
                recorded_at=as_utc(rec.recorded_at),
            ))
            s.commit()

    def outcomes(self, report_id: str) -> list[OutcomeRecord]:
        with self._session_factory() as s:
            rows = s.execute(
                select(OutcomeRow)
                .where(OutcomeRow.report_id == report_id)
                .order_by(OutcomeRow.id)
            ).scalars().all()
            return [
                OutcomeRecord(
                    report_id=r.report_id, claim_id=r.claim_id,
                    outcome=OutcomeLabel(r.outcome), notes=r.notes or "",
                    recorded_at=as_utc(r.recorded_at),
                )
                for r in rows
            ]

    def delete(self, report_id: str) -> bool:
        """Delete one report; its outcomes CASCADE in the database."""
        with self._session_factory() as s:
            row = s.get(ReportRow, report_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    def for_candidate(self, candidate_id: str) -> list[Report]:
        with self._session_factory() as s:
            rows = s.execute(
                select(ReportRow)
                .where(ReportRow.candidate_id == candidate_id)
                .order_by(ReportRow.created_at)
            ).scalars().all()
            return [Report.model_validate(r.body) for r in rows]


def build_report_store(settings: Optional[Settings] = None) -> ReportStore:
    """Store on the shared candidates DB URL (one metadata root, one Alembic
    env). Schema is Alembic's job, NOT the builder's."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return SqlReportStore(make_session_factory(engine))
```

- [ ] **Step 4: Run the store tests**

Run: `pytest tests/test_report_store.py tests/test_report_cascade.py -q`
Expected: PASS.

- [ ] **Step 5: Delete the old module**

```bash
git rm app/services/report_store.py
```

- [ ] **Step 6: Repoint every import**

Run `grep -rn "services.report_store\|InMemoryReportStore\|SqliteReportStore" app/ tests/ scripts/`.

- `from app.services.report_store import ReportStore` → `from app.reports.store import ReportStore`
- `from app.services.report_store import OutcomeLabel, OutcomeRecord` → `from app.reports.schema import OutcomeLabel, OutcomeRecord`
- `from app.services.report_store import ReportStore, build_report_store` → `from app.reports.store import ReportStore, build_report_store`

In `tests/conftest.py`, `make_services` builds the real store on the candidate store's own session factory — so reports live in the same in-memory DB as candidates and the cascade is exercised by the whole suite:

```python
    report_store = SqlReportStore(candidates._session_factory)
```

with `from app.reports.store import SqlReportStore` replacing the `InMemoryReportStore` import.

Every test module that imported `InMemoryReportStore` gets the same substitution; where a test built one standalone, use `SqlReportStore(make_candidate_store()._session_factory)`.

- [ ] **Step 7: Fix the now-false comment in `app/interview/models.py:42-45`**

It says reports "live in a separate SQLite database (report_db_path), so the constraint is not expressible". That is no longer true. Replace with:

```python
    # Which depth report supplied the probes. Still NOT a FK: since S8.1 the
    # constraint IS expressible (reports are in this database now), but adding
    # it needs a batch_alter_table on a live table and a decision about what a
    # deleted report should do to a finished interview. Deferred deliberately --
    # see the S8.1 spec's follow-ups.
```

- [ ] **Step 8: Remove the dead config knob**

Delete `report_db_path` from `app/core/config.py` (line ~221) and from `config.yaml` if present. `getattr(svc.report_store, "path", "memory")` in `app/main.py:42` no longer resolves to anything meaningful — change that log field to `db=svc.settings.candidates_db_url.split("://", 1)[0]`.

- [ ] **Step 9: Run the whole suite**

Run: `pytest -q`
Expected: green. Failures here are almost always one of two shapes: (a) a stale import, or (b) a test saving a report for a candidate that was never created — see Step 1's note.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(s81): SqlReportStore on the main DB; both old stores deleted

app/services/report_store.py is gone -- 212 lines of raw sqlite3, an
INSERT OR REPLACE that Postgres does not have, a process-wide write lock, and an
ALTER TABLE ADD COLUMN in a try/except at construction standing in for a
migration system beside fifteen real ones.

InMemoryReportStore is gone too, and that is not incidental cleanup: it is a
dict, it cannot cascade, and leaving it in make_services would let every erasure
test in the suite pass WITHOUT the guarantee the fold exists to create. The real
store runs on the same in-memory SQLite session factory the candidate store
already uses in tests, so it is offline and free.

delete_for_candidate is off the Protocol entirely -- its only two callers are
the route sites Task 6 collapses."
```

---

### Task 6: Collapse the two erasure call sites

**Files:**
- Modify: `app/api/routes.py:347-360` (admin) and `app/api/routes.py:980-990` (portal)
- Test: `tests/test_candidates_api.py`, `tests/test_portal_api.py`

**Interfaces:**
- Consumes: `ReportStore.for_candidate` (a read), `CandidateStore.delete_candidate`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_candidates_api.py`:

```python
def test_admin_erasure_removes_reports_via_the_cascade(api):
    """No report-store deletion in the handler -- the database does it."""
    client, services = api
    created = client.post("/candidates", json={"resume_text": RESUME}).json()
    cid, rid = created["candidate_id"], created["report"]["id"]
    assert services.report_store.get(rid) is not None

    resp = client.delete(f"/candidates/{cid}")

    assert resp.status_code == 200
    assert resp.json()["reports_deleted"] == 1
    assert services.report_store.get(rid) is None
```

Add to `tests/test_portal_api.py` the same assertion shape against `DELETE /portal/me` (reuse that module's existing candidate + key fixtures).

- [ ] **Step 2: Run them**

Run: `pytest tests/test_candidates_api.py -q -k erasure`
Expected: FAIL — `AttributeError: 'SqlReportStore' object has no attribute 'delete_for_candidate'` (the handler still calls it).

- [ ] **Step 3: Collapse the admin handler**

Replace `app/api/routes.py:347-360`:

```python
@router.delete("/candidates/{candidate_id}")
async def delete_candidate(candidate_id: str, request: Request) -> dict:
    """DPDP erasure: candidate + resumes (raw text) + extractions + all reports
    derived from them. Hard delete — there is nothing to un-delete.

    Since S8.1 the reports go with the candidate through
    `reports.candidate_id ON DELETE CASCADE`, not through a call this handler
    has to remember. `reports_deleted` is a COUNT READ taken before the delete:
    a future entry point that forgets it loses a number in a response, not a
    person's data.
    """
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    reports_deleted = len(services.report_store.for_candidate(candidate_id))
    services.candidates.delete_candidate(candidate_id)
    return {
        "candidate_id": candidate_id,
        "deleted": True,
        "reports_deleted": reports_deleted,
    }
```

- [ ] **Step 4: Collapse the portal handler**

Replace `app/api/routes.py:987-990`:

```python
    services = _services(request)
    reports_deleted = len(services.report_store.for_candidate(candidate_id))
    services.candidates.delete_candidate(candidate_id)
    return {"candidate_id": candidate_id, "deleted": True, "reports_deleted": reports_deleted}
```

- [ ] **Step 5: Run the suite**

Run: `pytest -q`
Expected: green, including `tests/test_candidates_api.py:193`'s existing `reports_deleted == 1` assertion, which still holds.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(s81): erasure is the database's job, not the route's

Both handlers called report_store.delete_for_candidate and THEN
candidates.delete_candidate. Both remembered; nothing enforced it; a third entry
point forgetting one line would orphan an erased person's evaluation with no FK
to catch it and no error to notice it. It was also non-atomic -- no transaction
spans two databases, so a failure between the two lines destroyed the reports
and kept the candidate.

reports_deleted survives as a pre-count READ, which is a number in a response."
```

---

### Task 7: Data migration for existing rows

**Files:**
- Create: `scripts/migrate_reports_into_main_db.py`, `tests/test_report_data_migration.py`

**Interfaces:**
- Produces: `scripts.migrate_reports_into_main_db.migrate(old_db_path: str, session_factory) -> dict` returning `{"imported": int, "orphaned": int, "outcomes": int}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report_data_migration.py`:

```python
"""One-shot import of the pre-S8.1 reports.db into the main database.

Deliberately NOT an Alembic step: a migration must not read a filesystem path
out of Settings, must not need a second database engine to be reachable, and
must stay runnable on a fresh deployment that never had a reports.db.
"""

from __future__ import annotations

import sqlite3

from sqlalchemy import select

from app.reports.models import OutcomeRow, ReportRow
from scripts.migrate_reports_into_main_db import migrate
from tests.conftest import make_candidate_store


def _old_db(tmp_path, rows):
    path = str(tmp_path / "reports.db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE reports (id TEXT PRIMARY KEY, domain TEXT, created_at TEXT,"
        " depth_band TEXT, candidate_id TEXT, body TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE outcomes (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " report_id TEXT NOT NULL, claim_id TEXT, outcome TEXT NOT NULL,"
        " notes TEXT, recorded_at TEXT NOT NULL)"
    )
    for r in rows:
        conn.execute("INSERT INTO reports VALUES (?,?,?,?,?,?)", r)
    conn.execute(
        "INSERT INTO outcomes (report_id, claim_id, outcome, notes, recorded_at)"
        " VALUES ('rep_live', NULL, 'inconclusive', '', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()
    return path


def test_missing_old_db_is_a_clean_no_op(tmp_path):
    store = make_candidate_store()
    result = migrate(str(tmp_path / "absent.db"), store._session_factory)
    assert result == {"imported": 0, "orphaned": 0, "outcomes": 0}


def test_imports_linked_reports_and_drops_orphans(tmp_path):
    store = make_candidate_store()
    cid = store.upsert_candidate_profile_only()
    body = '{"id": "rep_live", "domain": "genai", "depth_band": "solid"}'
    path = _old_db(tmp_path, [
        ("rep_live", "genai", "2026-01-01T00:00:00+00:00", "solid", cid, body),
        # The old convention's actual failures: a report whose candidate is
        # already erased. No FK caught this; nothing ever would have.
        ("rep_orphan", "genai", "2026-01-01T00:00:00+00:00", "solid", "gone",
         '{"id": "rep_orphan"}'),
        # Ad-hoc POST /evaluate output: never personal data, always kept.
        ("rep_free", "genai", "2026-01-01T00:00:00+00:00", "solid", None,
         '{"id": "rep_free"}'),
    ])

    result = migrate(path, store._session_factory)

    assert result == {"imported": 2, "orphaned": 1, "outcomes": 1}
    with store._session_factory() as s:
        ids = {r.id for r in s.execute(select(ReportRow)).scalars()}
        assert ids == {"rep_live", "rep_free"}
        assert len(s.execute(select(OutcomeRow)).scalars().all()) == 1


def test_second_run_is_a_no_op(tmp_path):
    store = make_candidate_store()
    cid = store.upsert_candidate_profile_only()
    path = _old_db(tmp_path, [
        ("rep_live", "genai", "2026-01-01T00:00:00+00:00", "solid", cid,
         '{"id": "rep_live"}'),
    ])

    migrate(path, store._session_factory)
    again = migrate(path, store._session_factory)

    assert again["imported"] == 0
    with store._session_factory() as s:
        assert len(s.execute(select(ReportRow)).scalars().all()) == 1
```

Use the same real candidate-creation helper you settled on in Task 4 Step 1 in place of `upsert_candidate_profile_only`.

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_report_data_migration.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.migrate_reports_into_main_db'`

(If `scripts/` has no `__init__.py`, add an empty one so the test can import it.)

- [ ] **Step 3: Implement the script**

```python
"""One-shot: import the pre-S8.1 reports.db into the main database (S8.1).

    python scripts/migrate_reports_into_main_db.py [--old-db ./data/reports.db]

Run once per deployment that has a reports.db. Absent file => clean no-op, so it
is safe on a fresh install. Idempotent: a report already present is skipped.

Reports whose candidate no longer exists are REPORTED AND DROPPED. They are the
old convention's actual failures -- an erased person's depth evaluation, kept
alive because nothing enforced the two-step delete -- and the new foreign key
would reject them anyway.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.candidates.models import CandidateRow  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.reports.models import OutcomeRow, ReportRow  # noqa: E402


def _dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


def migrate(old_db_path: str, session_factory) -> dict:
    if not os.path.exists(old_db_path):
        return {"imported": 0, "orphaned": 0, "outcomes": 0}

    conn = sqlite3.connect(f"file:{old_db_path}?mode=ro", uri=True)
    try:
        reports = conn.execute(
            "SELECT id, domain, created_at, depth_band, candidate_id, body"
            " FROM reports"
        ).fetchall()
        outcomes = conn.execute(
            "SELECT report_id, claim_id, outcome, notes, recorded_at FROM outcomes"
        ).fetchall()
    finally:
        conn.close()

    imported = orphaned = kept_outcomes = 0
    with session_factory() as s:
        known = {c for (c,) in s.execute(select(CandidateRow.id))}
        existing = {r for (r,) in s.execute(select(ReportRow.id))}
        landed: set[str] = set()

        for rid, domain, created_at, depth_band, candidate_id, body in reports:
            if rid in existing:
                continue
            if candidate_id is not None and candidate_id not in known:
                orphaned += 1
                continue
            s.add(ReportRow(
                id=rid, domain=domain or "genai",
                depth_band=depth_band or "insufficient_signal",
                candidate_id=candidate_id, body=json.loads(body),
                created_at=_dt(created_at),
            ))
            landed.add(rid)
            imported += 1

        for report_id, claim_id, outcome, notes, recorded_at in outcomes:
            if report_id not in landed:
                continue
            s.add(OutcomeRow(
                report_id=report_id, claim_id=claim_id, outcome=outcome,
                notes=notes or "", recorded_at=_dt(recorded_at),
            ))
            kept_outcomes += 1

        s.commit()

    return {"imported": imported, "orphaned": orphaned, "outcomes": kept_outcomes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-db", default="./data/reports.db")
    args = parser.parse_args()

    settings = get_settings()
    factory = make_session_factory(make_engine(settings.candidates_db_url))
    result = migrate(args.old_db, factory)

    print(f"imported: {result['imported']} reports, {result['outcomes']} outcomes")
    if result["orphaned"]:
        print(
            f"DROPPED {result['orphaned']} orphaned report(s): their candidate "
            "was already erased. These are what the pre-S8.1 convention actually "
            "leaked."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_report_data_migration.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Run it for real against the local dev database**

Run: `python scripts/migrate_reports_into_main_db.py`
Expected: exit 0. Record the numbers it prints — the orphan count is a measurement of what the old convention actually leaked, and it goes in the ROADMAP session log.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(s81): one-shot import of the old reports.db, orphans reported and dropped

Not an Alembic step on purpose: a migration must not read a filesystem path out
of Settings, must not need a second engine reachable, and must stay runnable on
a fresh install that never had a reports.db.

Reports whose candidate no longer exists are counted out loud and dropped. They
are what the pre-S8.1 two-step convention actually leaked, and the new FK would
reject them anyway."
```

---

### Task 8: Postgres

**Files:**
- Modify: `requirements.txt`, `app/core/db.py`, `tests/conftest.py`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `DEE_TEST_DB_URL` as a test-only environment hook. Unset ⇒ today's `sqlite://` in-memory behaviour, unchanged.

- [ ] **Step 1: Add the driver**

In `requirements.txt`, under the relational store block:

```
psycopg[binary]>=3.1   # Postgres driver (S8.1 cutover); SQLite stays the dev/test default
```

Run: `pip install -r requirements.txt`

- [ ] **Step 2: Write the failing test**

Add to `tests/test_migrations.py`:

```python
def test_non_sqlite_engines_pre_ping(monkeypatch):
    """Managed Postgres closes idle connections; without pool_pre_ping the first
    request after an idle period 500s."""
    engine = make_engine("postgresql+psycopg://u:p@localhost:5432/nope")
    assert engine.pool._pre_ping is True
```

- [ ] **Step 3: Run it**

Run: `pytest tests/test_migrations.py -q -k pre_ping`
Expected: FAIL — `assert False is True`

- [ ] **Step 4: Add `pool_pre_ping` in `app/core/db.py`**

In `make_engine`, in the non-SQLite path:

```python
    kwargs: dict = {}
    if url.startswith("sqlite"):
        ...  # unchanged
    else:
        # Managed Postgres (Railway et al.) drops idle connections; without this
        # the first request after a quiet period fails on a dead socket.
        kwargs["pool_pre_ping"] = True
```

- [ ] **Step 5: Run it**

Run: `pytest tests/test_migrations.py -q -k pre_ping`
Expected: PASS

- [ ] **Step 6: Teach `make_candidate_store` the `DEE_TEST_DB_URL` hook**

In `tests/conftest.py`:

```python
def make_candidate_store() -> CandidateStore:
    """In-memory candidate store for tests. create_all is a TEST convenience;
    real deployments migrate via Alembic (S1.2 decision).

    DEE_TEST_DB_URL runs the SAME suite against Postgres (S8.1). Each store gets
    a throwaway schema so tests stay as isolated as a fresh in-memory SQLite DB
    makes them.
    """
    url = os.environ.get("DEE_TEST_DB_URL", "").strip()
    if not url:
        engine = make_engine("sqlite://")
    else:
        schema = f"s_{uuid.uuid4().hex[:8]}"
        bootstrap = create_engine(url)
        with bootstrap.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        bootstrap.dispose()
        engine = create_engine(
            url, pool_pre_ping=True,
            connect_args={"options": f"-csearch_path={schema}"},
        )
    Base.metadata.create_all(engine)
    return CandidateStore(make_session_factory(engine))
```

Add the imports `os`, `uuid`, and `from sqlalchemy import create_engine, text` to conftest.

Add the session-scoped cleanup fixture:

```python
@pytest.fixture(scope="session", autouse=True)
def _drop_postgres_test_schemas():
    """Throwaway schemas are cheap to make and must not accumulate."""
    yield
    url = os.environ.get("DEE_TEST_DB_URL", "").strip()
    if not url:
        return
    engine = create_engine(url)
    with engine.begin() as conn:
        names = [
            n for (n,) in conn.execute(
                text(r"SELECT nspname FROM pg_namespace WHERE nspname LIKE 's\_%'")
            )
        ]
        for name in names:
            conn.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
    engine.dispose()
```

- [ ] **Step 7: Prove the default path is untouched**

Run: `pytest -q`
Expected: green, same count as after Task 7. `DEE_TEST_DB_URL` is unset, so nothing changed.

- [ ] **Step 8: Run the migrations against the real Railway Postgres**

```bash
python -c "
from alembic import command; from alembic.config import Config
import os
cfg = Config('alembic.ini'); cfg.set_main_option('sqlalchemy.url', os.environ['DEE_TEST_DB_URL'])
command.upgrade(cfg, 'head'); command.downgrade(cfg, 'base'); command.upgrade(cfg, 'head')
print('up/down/up clean')
"
```

Expected: `up/down/up clean`. This is what proves the three `batch_alter_table` migrations (`0004`, `0006`, `0014`) on a dialect where batch mode is a plain `ALTER`, **and** proves the downgrades, which have never run anywhere (the S3.1 residual "0004 downgrade untested").

Fix any migration that fails here. Postgres is stricter than SQLite about types, server defaults and constraint naming.

- [ ] **Step 9: Run the whole suite against Postgres**

```bash
DEE_TEST_DB_URL=<railway url> pytest -q
```

Expected: green. Every failure is a real dialect difference — fix it in the code, not the test, unless the test itself encodes a SQLite-only assumption. If a test genuinely cannot run on Postgres, mark it:

```python
@pytest.mark.skipif(
    bool(os.environ.get("DEE_TEST_DB_URL")),
    reason="<state the actual dialect reason here>",
)
```

**No unexplained skips.** An unexplained skip is how a dialect bug survives.

- [ ] **Step 10: Add the CI job**

In `.github/workflows/ci.yml`, add beside the existing `test` job (leave that one untouched — it stays the merge gate):

```yaml
  postgres:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: veritas_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
    env:
      DEE_TEST_DB_URL: postgresql+psycopg://postgres:postgres@localhost:5432/veritas_test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -r requirements.txt
      # Proves the three batch_alter_table migrations on a dialect where batch
      # mode is a plain ALTER -- and proves the downgrades, which until S8.1 had
      # never run anywhere.
      - name: migrations up/down/up
        run: |
          python -c "
          from alembic import command; from alembic.config import Config
          import os
          cfg = Config('alembic.ini')
          cfg.set_main_option('sqlalchemy.url', os.environ['DEE_TEST_DB_URL'])
          command.upgrade(cfg, 'head')
          command.downgrade(cfg, 'base')
          command.upgrade(cfg, 'head')
          "
      - run: pytest -q
```

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat(s81): Postgres -- driver, pre-ping, a DEE_TEST_DB_URL suite hook, and CI

SQLite stays the default and the local test backend; the fully offline pytest -q
on a clean checkout is not negotiable. DEE_TEST_DB_URL runs the SAME suite on
Postgres, each store isolated in a throwaway schema.

The CI job runs upgrade head -> downgrade base -> upgrade head, which is what
proves the three batch_alter_table migrations on a dialect where batch mode is a
plain ALTER -- and proves the downgrades, which had never run anywhere."
```

---

### Task 9: `scripts/smoke_s81.py`

**Files:**
- Create: `scripts/smoke_s81.py`

- [ ] **Step 1: Write the smoke**

Model it on `scripts/smoke_s73.py` (subprocess uvicorn, `_wait_healthy`, numbered checks, exit code from the failure count) with **one structural difference: it does NOT pre-migrate.** Every prior smoke ran `command.upgrade(cfg, "head")` before booting; this one hands uvicorn an empty database file and lets the app migrate itself.

Checks, in order:

```
1  boots_and_migrates_from_empty      GET /healthz == 200 on an unmigrated DB
2  admin_without_key_401              POST /candidates, no header      -> 401
3  admin_with_wrong_key_401           POST /candidates, "nope"         -> 401
4  admin_with_key_200                 POST /candidates, admin_h        -> 200
5  report_readable                    GET /report/{rid}                -> 200
6  erasure_cascades_the_report        DELETE /candidates/{cid} -> 200,
                                      then GET /report/{rid}           -> 404
7  unattached_report_survives         POST /evaluate before the delete,
                                      still 200 after it
8  no_admin_key_refuses_to_boot       a second uvicorn with no
                                      DEE_API_AUTH_KEY exits non-zero and
                                      never answers /healthz
```

Check 8 is the sprint's headline, observed as a **process exit** rather than asserted in a unit test:

```python
def _boot_without_admin_key(scratch) -> bool:
    """The boot refusal, seen the way an operator sees it."""
    env = os.environ.copy()
    env.pop("DEE_API_AUTH_KEY", None)
    env.update({
        "DEE_API_AUTH_KEY": "",
        "DEE_CANDIDATES_DB_URL": "sqlite:///" + (scratch / "refuse.db").as_posix(),
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT + 1)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        out = proc.communicate(timeout=45)[0]
    except subprocess.TimeoutExpired:
        proc.kill()
        return False   # it stayed up: the guard did not fire
    return proc.returncode != 0 and "DEE_API_AUTH_KEY" in out
```

Set `DEE_OPENROUTER_API_KEY=""` in the main subprocess env, as `smoke_s73.py` does — the smoke claims to prove the key-less path and a developer with a real key in `.env` would otherwise be shipping live calls.

- [ ] **Step 2: Run it on SQLite**

Run: `python scripts/smoke_s81.py`
Expected: `8/8 OK`, exit 0.

- [ ] **Step 3: Run it against Railway Postgres**

```bash
DEE_CANDIDATES_DB_URL=<railway url> python scripts/smoke_s81.py
```

Expected: `8/8 OK`, exit 0. The script must honour an externally supplied `DEE_CANDIDATES_DB_URL` instead of its scratch SQLite path — read it from the environment with the scratch file as the fallback.

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_s81.py
git commit -m "test(s81): smoke -- empty DB boots and migrates itself, and the gate refuses

Unlike every prior smoke, this one does NOT pre-migrate: it hands uvicorn an
empty database and lets the app do it. The boot refusal is observed as a process
exit code, not asserted in a unit test -- that is how an operator meets it."
```

---

### Task 10: Deploy to Railway + docs

**Files:**
- Create: `railway.json`
- Modify: `README.md`, `docs/ROADMAP.md`

- [ ] **Step 1: Add `railway.json`**

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/healthz",
    "healthcheckTimeout": 120,
    "restartPolicyType": "ON_FAILURE"
  }
}
```

- [ ] **Step 2: Create the API service and set its environment**

Use the Railway MCP: `create_service` from the GitHub repo (or `deploy` from the local directory) into the `veritas` project, then `set_variables`:

| Variable | Value |
|---|---|
| `DEE_API_AUTH_KEY` | freshly generated, e.g. `openssl rand -hex 32` — **not** reused from any smoke or test |
| `DEE_CANDIDATES_DB_URL` | `postgresql+psycopg://` + the Postgres service's **internal** reference variable |
| `DEE_ENV` | `prod` |
| `DEE_LOG_JSON` | `true` |
| `DEE_VECTORSTORE_BACKEND` | `memory` — Chroma's PersistentClient hangs on some hosts and grounding is best-effort |

No OpenRouter key: extraction falls back to heuristics, and this sprint proves the key-less path in production too.

- [ ] **Step 3: Deploy and generate a domain**

`deploy`, then `generate_domain`. Watch `get_logs` for `migrations_applied` and `startup_complete`.

- [ ] **Step 4: Verify the deployment by hand**

```bash
curl -s https://<domain>/healthz                      # 200
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/domains   # 401
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: <key>" https://<domain>/domains  # 200
```

The 401 is the check that matters: it is the defect this sprint closed, verified from outside.

- [ ] **Step 5: Prove the prod guard fires**

Temporarily unset `DEE_API_AUTH_KEY` on the service and redeploy. The container must fail its healthcheck with `DEE_API_AUTH_KEY is not set` in the logs. **Restore the variable and redeploy.** Record the log line.

- [ ] **Step 6: Write the README Deploy section**

Add a `## Deploy` section covering: the required environment variables (with the two boot refusals stated as behaviour, not warnings), the fact that the container migrates itself on boot, the one-shot `scripts/migrate_reports_into_main_db.py` for deployments with a pre-S8.1 `reports.db`, and the Railway specifics.

- [ ] **Step 7: Full verification pass**

```bash
pytest -q
python scripts/smoke_s81.py
python scripts/smoke_s73.py
python scripts/smoke_s64.py
python scripts/smoke_s13.py
```

Expected: suite green; all four smokes exit 0. The last three are the regression check — S8.1 touched the erasure path, the report store and every smoke's auth.

- [ ] **Step 8: Update `docs/ROADMAP.md`**

Rewrite "Current state" and "Next action" for S8.1 complete, update the PI-8 status board, and add the session log entry. Record: the final test count, the smoke results, the orphan count from Task 7 Step 5, the deployed URL, and anything the Postgres run surfaced.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(s81): Railway deploy, railway.json, README deploy section

The container migrates itself on boot, refuses to start without an admin
credential, and refuses prod on SQLite. Verified from outside: /domains is 401
without the header and 200 with it -- the defect this sprint closed, checked
from the internet rather than from a test."
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §0.1 no env exemption | 1 (`test_no_local_exemption`) |
| §0.2 Railway PG first, app last | 0, 10 |
| §3.2(a) request gate | 2 |
| §3.2(b) boot guard | 1, 2 |
| §3.3 conftest + call sites + 9 smokes | 2 |
| §3.4 refusal tests + coverage guard | 2 |
| §4 migrate-on-boot, advisory lock, Dockerfile | 3 |
| §5.1 `app/reports/` package | 4, 5 |
| §5.2 migration `0016` + guards | 4 |
| §5.3 cascade test first | 4 |
| §5.4 `delete_for_candidate` removed, `reports_deleted` kept | 5, 6 |
| §5.5 `InMemoryReportStore` deleted | 5 |
| §5.6 data migration script | 7 |
| §6 psycopg, pre-ping, `DEE_TEST_DB_URL`, CI | 8 |
| §7 Railway | 0, 10 |
| §8 config: `db_migrate_on_boot` added, `report_db_path` removed | 3, 5 |
| §9 store parity, both erasure entry points, unattached reports, guards, data-migration tests | 4, 5, 6, 7 |
| §9.1 smoke | 9 |
| §11 definition of done | 8, 9, 10 |

**One addition beyond the spec as written:** the `env == "prod"` + SQLite boot refusal (Task 1). Railway container disks are ephemeral, so a prod boot on SQLite silently loses every row on the next redeploy — a hazard this sprint creates by making deployment possible. The spec is amended to match.

**Placeholder scan:** one deliberate marker — `upsert_candidate_profile_only` in Tasks 4 and 7, flagged in-line as "use the real helper `CandidateStore` exposes, do not add a store method". Its exact name is the only thing not pinned, and it is a lookup, not a decision.

**Type consistency:** `ReportRow.id` `String(64)` matches `outcomes.report_id` `String(64)`; `candidate_id` `String(36)` matches `candidates.id` `String(36)`; the ORM `Index("ix_reports_candidate_created", ...)` matches the migration's `create_index` name and column order (the drift guard compares both); `ReportStore` Protocol has 6 methods in Task 5 and every consumer calls only `save`/`get`/`add_outcome`/`outcomes`/`delete`/`for_candidate`.
