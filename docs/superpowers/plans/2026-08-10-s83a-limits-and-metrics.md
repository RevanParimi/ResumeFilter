# S8.3 Phase A — Limits and Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the service safe to run for paying customers on the abuse and
spend surface — a durable, dual-scoped rate limiter; an in-place retry for
failed batch items; and counters that make the limiter observable.

**Architecture:** One DB-backed limiter (`app/ratelimit/`) called from the
**service layer**, never from routes — `AuthService` already owns every auth
gate for exactly this reason, and the OTP surface is 8 routes over 2 service
methods. The increment is a conditional `UPDATE` whose `rowcount` is the
decision, following `ScreeningStore._try_claim`. Metrics are in-process
counters hanging off the injected `Services` bundle, rendered as Prometheus
text at an admin-gated `GET /metrics`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 + Alembic (SQLite dev,
Postgres-shaped), Pydantic v2, structlog, pytest. **No new dependencies.**

**Spec:** `docs/superpowers/specs/2026-08-10-s83-operating-safely-design.md`
(§0–§6 are this phase). Read it before Task 1.

## Global Constraints

- **Branch:** `s83a-limits-and-metrics`, cut from `main` at `cf59b14`.
- **Baseline:** `pytest -q` is **1586 passed** on `main`. Re-measure before the
  first commit; every task ends green.
- **TDD, one commit per task.** Write the failing test, run it, watch it fail
  for the stated reason, implement, watch it pass, commit.
- **Fully offline.** `NullLLM` / fake services (`tests/conftest.py`); no network,
  no vendor, no real clock where a window is under test — pass `now` in.
- **No `Co-Authored-By` trailer** in any commit message.
- **Config:** tunables in `config.yaml` **and** `app/core/config.py` (`Settings`);
  secrets only in `.env` under `DEE_*`. Keys in `config.yaml` are field names
  with no prefix.
- **DB:** SQLAlchemy + Alembic, SQLite locally, written Postgres-shaped. New
  migration is `0021_rate_limit_counters`, `down_revision = "0020_outcome_authorship"`.
- **Advisory posture unchanged:** nothing here auto-rejects anything.
- **Every route declares a `response_model`** — `tests/test_openapi_contract.py`
  asserts it for every route with no exemption.
- **⚠ OneDrive trap (S8.4 Phase B):** rewriting a file under `alembic/` and
  immediately running pytest in a subprocess can fail with
  `ImportError: cannot import name 'command' from 'alembic'`. Let the file
  settle (a second or two) before running the suite.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `app/ratelimit/__init__.py` | package marker |
| `app/ratelimit/schema.py` | pure types + key/window functions. No I/O, no session, no clock of its own. |
| `app/ratelimit/models.py` | `RateLimitCounterRow` only |
| `app/ratelimit/store.py` | `RateLimitStore.hit()` — the atomic increment and nothing else |
| `app/ratelimit/service.py` | `RateLimiter.check()` — scope fan-out, `RateLimited`, the rule table |
| `app/metrics/__init__.py` | package marker |
| `app/metrics/registry.py` | `Metrics` — counters + Prometheus rendering |
| `alembic/versions/0021_rate_limit_counters.py` | the migration |
| `tests/test_config_ratelimit.py` | knob defaults and bounds |
| `tests/test_ratelimit_schema.py` | pure functions |
| `tests/test_ratelimit_store.py` | the increment, incl. the interleaved race |
| `tests/test_ratelimit_service.py` | dual scoping |
| `tests/test_ratelimit_auth.py` | the OTP surface end to end |
| `tests/test_ratelimit_spend.py` | screening + ASR |
| `tests/test_screening_retry.py` | in-place retry |
| `tests/test_metrics.py` | counters, labels, the route |
| `scripts/smoke_s83a.py` | the phase smoke |
| `OPERATING.md` | limits · metrics · runbook |

**Modified:** `app/core/config.py` · `config.yaml` · `app/core/boot.py` ·
`app/auth/service.py` · `app/api/routes.py` · `app/screening/service.py` ·
`app/screening/store.py` · `app/interview/service.py` · `app/services/__init__.py` ·
`app/main.py` · `tests/conftest.py` · `tests/test_boot_config.py` ·
`SCREENING.md` · `UI.md`

---

### Task 1: Config knobs and the prod boot refusal

**Files:**
- Modify: `app/core/config.py` (insert after the `ret_batch_item_days` block, ~line 220)
- Modify: `config.yaml` (append after the screening block, ~line 297)
- Modify: `app/core/boot.py:67` (after the `email_provider` refusal)
- Test: `tests/test_config_ratelimit.py` (create), `tests/test_boot_config.py` (modify)

**Interfaces:**
- Consumes: nothing.
- Produces: `Settings.rate_limit_enabled: bool`,
  `Settings.rate_limit_trusted_proxy_hops: int`,
  `Settings.rate_limit_login_per_hour_per_email: int`,
  `Settings.rate_limit_login_per_hour_per_ip: int`,
  `Settings.rate_limit_verify_per_hour_per_email: int`,
  `Settings.rate_limit_verify_per_hour_per_ip: int`,
  `Settings.rate_limit_process_per_hour_per_org: int`,
  `Settings.rate_limit_asr_per_hour_per_candidate: int`.
  `verify_launch_config` raises `LaunchConfigError` on prod + disabled.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_ratelimit.py`:

```python
"""S8.3 Phase A: the rate-limit knobs. Defaults are the SAFE ones -- enabled,
and trusting no proxy -- because the wrong default here fails OPEN."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def test_rate_limiting_is_on_by_default():
    assert _settings().rate_limit_enabled is True


def test_no_proxy_is_trusted_by_default():
    """X-Forwarded-For is attacker-controlled. Trusting it by default would
    hand every caller a free reset of their own per-IP scope."""
    assert _settings().rate_limit_trusted_proxy_hops == 0


def test_default_limits_are_the_spec_values():
    s = _settings()
    assert s.rate_limit_login_per_hour_per_email == 20
    assert s.rate_limit_login_per_hour_per_ip == 100
    assert s.rate_limit_verify_per_hour_per_email == 30
    assert s.rate_limit_verify_per_hour_per_ip == 200
    assert s.rate_limit_process_per_hour_per_org == 400
    assert s.rate_limit_asr_per_hour_per_candidate == 60


@pytest.mark.parametrize(
    "field",
    [
        "rate_limit_login_per_hour_per_email",
        "rate_limit_login_per_hour_per_ip",
        "rate_limit_verify_per_hour_per_email",
        "rate_limit_verify_per_hour_per_ip",
        "rate_limit_process_per_hour_per_org",
        "rate_limit_asr_per_hour_per_candidate",
    ],
)
def test_a_limit_of_zero_is_refused_at_config_time(field):
    """A zero limit denies every caller including the operator. If somebody
    wants the limiter off, rate_limit_enabled is the honest switch."""
    with pytest.raises(ValidationError):
        _settings(**{field: 0})


def test_negative_proxy_hops_are_refused():
    with pytest.raises(ValidationError):
        _settings(rate_limit_trusted_proxy_hops=-1)
```

Append to `tests/test_boot_config.py`:

```python
def test_prod_refuses_to_boot_with_rate_limiting_disabled():
    """No knob restores fail-open admin auth (S8.1); an unthrottled OTP
    endpoint on a public host is the same class of thing."""
    from app.core.boot import LaunchConfigError, verify_launch_config
    from app.core.config import Settings
    from pydantic import SecretStr

    settings = Settings(
        _env_file=None, openrouter_api_key="", api_auth_key=SecretStr("k"),
        env="prod", candidates_db_url="postgresql://x/y",
        session_cookie_secure=True, cors_allowed_origins=["https://ui.example"],
        email_provider="smtp", rate_limit_enabled=False,
    )
    with pytest.raises(LaunchConfigError, match="rate_limit_enabled"):
        verify_launch_config(settings)


def test_local_may_disable_rate_limiting():
    """The refusal is prod-only: the test suite and local development need the
    switch, and `env` defaults to local so a forgotten variable still lands on
    the strict side in a real deploy."""
    from app.core.boot import verify_launch_config
    from app.core.config import Settings
    from pydantic import SecretStr

    verify_launch_config(Settings(
        _env_file=None, openrouter_api_key="", api_auth_key=SecretStr("k"),
        rate_limit_enabled=False,
    ))
```

- [ ] **Step 2: Run them and watch them fail**

```
python -m pytest tests/test_config_ratelimit.py tests/test_boot_config.py -q
```

Expected: `ValidationError`/`AttributeError` for the unknown fields (pydantic
`Settings` forbids nothing by default, so the assertions on values fail with
`AttributeError`), and the boot tests fail because no refusal exists.

- [ ] **Step 3: Add the knobs to `Settings`**

In `app/core/config.py`, immediately after the `ret_batch_item_days` field:

```python
    # --- Rate limiting (PI-8, S8.3 Phase A) -----------------------------------
    # ONE limiter, DB-backed, called from the SERVICE layer (spec §3.1). The
    # defaults are the safe ones in both directions: limiting ON, and NO proxy
    # trusted -- X-Forwarded-For is attacker-controlled, so trusting it by
    # default would leave a limiter that looks installed and bounds nothing.
    # Prod REFUSES TO BOOT with rate_limit_enabled=False (app/core/boot.py).
    rate_limit_enabled: bool = True
    #: 0 = ignore X-Forwarded-For entirely and use the socket peer. Set to the
    #: number of proxies in front of the app (Railway: 1).
    rate_limit_trusted_proxy_hops: int = Field(default=0, ge=0)
    # Dual-scoped: per email AND per IP. Per-email alone lets an attacker spray
    # one guess across ten thousand addresses; per-IP alone lets a botnet grind
    # one address. Neither is a bound on its own (spec §2.3).
    rate_limit_login_per_hour_per_email: int = Field(default=20, ge=1)
    rate_limit_login_per_hour_per_ip: int = Field(default=100, ge=1)
    rate_limit_verify_per_hour_per_email: int = Field(default=30, ge=1)
    rate_limit_verify_per_hour_per_ip: int = Field(default=200, ge=1)
    # Spend. 400 calls x screening_max_items_per_call (5) = 2000 items/hour --
    # far above a human driving the UI, a hard ceiling on a runaway client
    # loop. Bounded per CALL is not bounded per CALLER.
    rate_limit_process_per_hour_per_org: int = Field(default=400, ge=1)
    rate_limit_asr_per_hour_per_candidate: int = Field(default=60, ge=1)
```

- [ ] **Step 4: Mirror them into `config.yaml`**

Append after the screening block:

```yaml
# --- Rate limiting (PI-8, S8.3 Phase A) ---------------------------------------
# ONE DB-backed limiter, called from the service layer. Counters survive a
# redeploy on purpose: an in-process limiter resets every container start,
# which is a silent failure of the exact surface it defends.
# NOTE: rate_limit_default_per_minute from the PI-8 sketch was deliberately
# DROPPED, not deferred (spec 0.5) -- a blanket limit on unauthenticated POSTs
# covers exactly the /auth/* routes already limited by name.
rate_limit_enabled: true              # prod REFUSES to boot with false
rate_limit_trusted_proxy_hops: 0      # 0 = ignore X-Forwarded-For; Railway: 1
rate_limit_login_per_hour_per_email: 20
rate_limit_login_per_hour_per_ip: 100
rate_limit_verify_per_hour_per_email: 30
rate_limit_verify_per_hour_per_ip: 200
rate_limit_process_per_hour_per_org: 400   # x5 items = 2000 items/hour
rate_limit_asr_per_hour_per_candidate: 60
```

- [ ] **Step 5: Add the boot refusal**

In `app/core/boot.py`, after the `email_provider == "capture"` block (it is
already inside the prod-only section that begins with
`if settings.env != "prod": return` at line 50 — the new check MUST go after
that early return, or every local run breaks):

```python
    if not settings.rate_limit_enabled:
        raise LaunchConfigError(
            "DEE_ENV=prod with rate_limit_enabled=false. The OTP endpoints are "
            "the brute-force surface this PI created, and they would be "
            "unthrottled on a public host. No knob restores fail-open admin "
            "auth (S8.1); this is the same class of thing. Set "
            "rate_limit_enabled=true."
        )
```

Also extend the module docstring's second paragraph to say S8.3 adds a sixth
refusal.

- [ ] **Step 6: Run the tests**

```
python -m pytest tests/test_config_ratelimit.py tests/test_boot_config.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/core/config.py config.yaml app/core/boot.py tests/test_config_ratelimit.py tests/test_boot_config.py
git commit -m "feat(s83a): rate-limit knobs, and prod refuses to boot without them

Defaults are safe in BOTH directions: limiting on, and no proxy trusted.
X-Forwarded-For is attacker-controlled, so a default that trusts it would
leave a limiter that passes every test and bounds nothing.

The refusal goes after boot.py's prod-only early return -- above it, every
local run breaks."
```

---

### Task 2: The pure layer — keys, windows, rules

**Files:**
- Create: `app/ratelimit/__init__.py`, `app/ratelimit/schema.py`
- Test: `tests/test_ratelimit_schema.py`

**Interfaces:**
- Consumes: `Settings` (Task 1).
- Produces:
  - `class LimitScope(StrEnum)`: `EMAIL`, `IP`, `ORG`, `CANDIDATE`
  - `@dataclass(frozen=True) class RateRule(name: str, limit: int, window_seconds: int, scope: LimitScope)`
  - `@dataclass(frozen=True) class LimitDecision(allowed: bool, rule: str, scope: LimitScope | None, retry_after_seconds: int)`
  - `def bucket_key(*, rule: str, scope: LimitScope, identity: str, salt: str) -> str`
  - `def window_start(now: datetime, window_seconds: int) -> int` (epoch seconds)
  - `def retry_after(now: datetime, window_start_epoch: int, window_seconds: int) -> int`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ratelimit_schema.py`:

```python
"""S8.3 Phase A: the pure layer. No session, no clock of its own -- every
function takes what it needs, so a window is testable without waiting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.ratelimit.schema import (
    LimitScope, RateRule, bucket_key, retry_after, window_start,
)

NOW = datetime(2026, 8, 10, 14, 37, 12, tzinfo=timezone.utc)


def test_bucket_key_does_not_contain_the_identity():
    """The row would otherwise hold a raw email beside a raw IP for every login
    attempt on the platform -- a worse disclosure than the thing defended."""
    key = bucket_key(
        rule="login_request", scope=LimitScope.EMAIL,
        identity="priya@example.com", salt="s",
    )
    assert "priya" not in key
    assert "@" not in key
    assert len(key) == 64  # sha256 hex


def test_bucket_key_separates_rules_scopes_and_identities():
    common = dict(salt="s")
    a = bucket_key(rule="login_request", scope=LimitScope.EMAIL, identity="x", **common)
    b = bucket_key(rule="login_verify", scope=LimitScope.EMAIL, identity="x", **common)
    c = bucket_key(rule="login_request", scope=LimitScope.IP, identity="x", **common)
    d = bucket_key(rule="login_request", scope=LimitScope.EMAIL, identity="y", **common)
    assert len({a, b, c, d}) == 4


def test_bucket_key_is_salted():
    """Same salt as email_hash/phone_hash: an unsalted hash of an email is a
    rainbow-table lookup away from the email."""
    assert bucket_key(
        rule="r", scope=LimitScope.EMAIL, identity="x", salt="one"
    ) != bucket_key(rule="r", scope=LimitScope.EMAIL, identity="x", salt="two")


def test_window_start_floors_to_the_window():
    hour = 3600
    assert window_start(NOW, hour) == int(
        datetime(2026, 8, 10, 14, 0, 0, tzinfo=timezone.utc).timestamp()
    )


def test_two_times_in_one_window_share_a_start():
    hour = 3600
    assert window_start(NOW, hour) == window_start(NOW + timedelta(minutes=20), hour)


def test_the_next_window_has_a_different_start():
    hour = 3600
    assert window_start(NOW, hour) != window_start(NOW + timedelta(hours=1), hour)


def test_retry_after_is_the_seconds_left_in_the_window():
    hour = 3600
    ws = window_start(NOW, hour)
    # 14:37:12 -> 22m48s remain of the 14:00 window
    assert retry_after(NOW, ws, hour) == 22 * 60 + 48


def test_retry_after_is_never_zero_or_negative():
    """A Retry-After of 0 invites an immediate retry that will also be refused."""
    hour = 3600
    ws = window_start(NOW, hour)
    assert retry_after(NOW.replace(minute=59, second=59), ws, hour) >= 1


def test_a_rule_is_frozen():
    rule = RateRule(name="r", limit=5, window_seconds=60, scope=LimitScope.IP)
    import dataclasses
    assert dataclasses.is_dataclass(rule)
    try:
        rule.limit = 9  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("RateRule must be frozen")
```

- [ ] **Step 2: Run it and watch it fail**

```
python -m pytest tests/test_ratelimit_schema.py -q
```

Expected: `ModuleNotFoundError: No module named 'app.ratelimit'`.

- [ ] **Step 3: Implement**

Create `app/ratelimit/__init__.py` (empty) and `app/ratelimit/schema.py`:

```python
"""Rate limiting: the pure types (S8.3 Phase A).

No I/O, no session, no clock beyond what a caller hands in -- the same split
as app/screening/schema.py, and the reason is the same: a window is only
testable without waiting if `now` is an argument.

The identity is HASHED into the bucket key and never stored. A counter table
keyed on raw emails and raw IPs would hold, for every login attempt on the
platform, exactly the pair of identifiers an attacker wants -- a worse
disclosure than the brute-forcing it defends against. The salt is
`contact_hash_salt`, the same one behind email_hash/phone_hash: precedent, not
invention.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional


class LimitScope(StrEnum):
    """WHAT a rule counts per. A rule names one; a caller may evaluate several
    (see RateLimiter.check) -- that is what "dual-scoped" means."""

    EMAIL = "email"
    IP = "ip"
    ORG = "org"
    CANDIDATE = "candidate"


@dataclass(frozen=True)
class RateRule:
    """`limit` events per `window_seconds`, counted per `scope`."""

    name: str
    limit: int
    window_seconds: int
    scope: LimitScope


@dataclass(frozen=True)
class LimitDecision:
    """`scope` names the scope that REFUSED, and is None when allowed."""

    allowed: bool
    rule: str
    scope: Optional[LimitScope] = None
    retry_after_seconds: int = 0


def bucket_key(*, rule: str, scope: LimitScope, identity: str, salt: str) -> str:
    """One counter's identity, as a salted sha256 hex digest."""
    material = f"{salt}|{rule}|{scope.value}|{identity}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def window_start(now: datetime, window_seconds: int) -> int:
    """The epoch second the current fixed window opened.

    An INTEGER, not a datetime, and that is deliberate: this value is only ever
    compared for exact equality, and epoch seconds carry no timezone semantics
    for a dialect to disagree about. `expires_at` on the row stays a real
    timestamp, because the retention sweep reads it like every other one.

    Fixed windows admit a burst of up to 2x the limit across a window edge.
    For a 20/hour OTP bound that is irrelevant, and OPERATING.md says so rather
    than leaving a reader to discover it.
    """
    return int(now.timestamp()) // window_seconds * window_seconds


def retry_after(now: datetime, window_start_epoch: int, window_seconds: int) -> int:
    """Whole seconds until this window closes, never less than 1.

    Zero would invite an immediate retry that is also refused, which reads to a
    client author like the header is broken.
    """
    remaining = window_start_epoch + window_seconds - int(now.timestamp())
    return max(1, remaining)
```

- [ ] **Step 4: Run the test**

```
python -m pytest tests/test_ratelimit_schema.py -q
```

Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ratelimit/ tests/test_ratelimit_schema.py
git commit -m "feat(s83a): the limiter's pure layer -- salted keys, fixed windows

The identity is hashed into the bucket key and never stored: a counter table
keyed on raw emails and raw IPs would hold, for every login attempt on the
platform, exactly the pair an attacker wants.

window_start returns epoch SECONDS, not a datetime -- it is only ever compared
for exact equality, and an integer has no timezone semantics for a dialect to
disagree about."
```

---

### Task 3: The table and migration 0021

**Files:**
- Create: `app/ratelimit/models.py`, `alembic/versions/0021_rate_limit_counters.py`
- Modify: `tests/conftest.py` (add the model import beside the auth one at line 30)
- Test: `tests/test_ratelimit_store.py` (created here, one test; grown in Task 4)

**Interfaces:**
- Consumes: `app.core.db.Base`.
- Produces: `RateLimitCounterRow` with columns `id: str`, `bucket_key: str`,
  `window_start: int`, `count: int`, `expires_at: datetime`, and a unique
  constraint `uq_rate_limit_counters_key_window` on `(bucket_key, window_start)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ratelimit_store.py`:

```python
"""S8.3 Phase A: the counter row and the atomic increment."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.ratelimit.models import RateLimitCounterRow
from tests.conftest import make_candidate_store


@pytest.fixture
def session_factory():
    """A real SQLite schema built the way every other store test builds one."""
    return make_candidate_store()._session_factory


def test_one_counter_per_key_and_window(session_factory):
    """The unique constraint is what makes the INSERT race resolvable: the
    loser gets an IntegrityError instead of a second row nobody counts."""
    with session_factory() as session:
        session.add(RateLimitCounterRow(
            bucket_key="k", window_start=100, count=1, expires_at=None,
        ))
        session.commit()
    with session_factory() as session:
        session.add(RateLimitCounterRow(
            bucket_key="k", window_start=100, count=1, expires_at=None,
        ))
        with pytest.raises(IntegrityError):
            session.commit()


def test_the_same_key_in_a_later_window_is_a_different_row(session_factory):
    with session_factory() as session:
        session.add(RateLimitCounterRow(bucket_key="k", window_start=100, count=1))
        session.add(RateLimitCounterRow(bucket_key="k", window_start=200, count=1))
        session.commit()
        assert session.query(RateLimitCounterRow).count() == 2
```

- [ ] **Step 2: Run it and watch it fail**

```
python -m pytest tests/test_ratelimit_store.py -q
```

Expected: `ModuleNotFoundError: No module named 'app.ratelimit.models'`.

- [ ] **Step 3: Write the model**

Create `app/ratelimit/models.py`:

```python
"""ORM row for the rate limiter (S8.3 Phase A). Postgres-shaped on SQLite.

There is ONE table and it has no foreign keys, deliberately: a counter must be
writable on the login path BEFORE any principal exists, and an FK to
candidates/organizations would tie a pre-auth write to a subject we have not
identified yet.

`window_start` is an INTEGER of epoch seconds rather than a timestamp. It is
only ever compared for exact equality (the WHERE of the conditional UPDATE),
and an integer has no timezone semantics for SQLite and Postgres to disagree
about. `expires_at` IS a real timestamp, because S8.3 Phase B's retention sweep
reads it the same way it reads every other retention column.

The row holds a salted hash and a count -- never the email, never the IP.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class RateLimitCounterRow(Base):
    __tablename__ = "rate_limit_counters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    #: sha256 hex of salt|rule|scope|identity -- see app/ratelimit/schema.py.
    bucket_key: Mapped[str] = mapped_column(String(128), index=True)
    #: Epoch seconds at which this fixed window opened.
    window_start: Mapped[int] = mapped_column(BigInteger)
    count: Mapped[int] = mapped_column(Integer, default=0)
    #: When this row stops being useful. The Phase B sweep's access path.
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    __table_args__ = (
        # The whole limiter rests on this: it is what turns a lost INSERT race
        # into a catchable IntegrityError instead of a second uncounted row.
        UniqueConstraint(
            "bucket_key", "window_start", name="uq_rate_limit_counters_key_window"
        ),
    )
```

- [ ] **Step 4: Register the model with the test metadata**

In `tests/conftest.py`, beside the existing auth import at line 30:

```python
import app.ratelimit.models  # noqa: F401 — populate Base.metadata with the counter table
```

- [ ] **Step 5: Write the migration**

Create `alembic/versions/0021_rate_limit_counters.py`:

```python
"""rate limit counters: a bound that survives a redeploy (S8.3 Phase A)

Revision ID: 0021_rate_limit_counters
Revises: 0020_outcome_authorship
Create Date: 2026-08-10

The counters live in the database rather than in process memory, and that is
the sprint's load-bearing choice. An in-process limiter resets on every
container start and is per-worker -- both are silent failures of the exact
surface a limiter exists for (OTP brute force), and both pass every unit test.

NO foreign keys, deliberately: the login path writes a counter BEFORE any
principal exists, so there is no subject to reference. The unique constraint is
the important object here -- it is what makes a lost INSERT race a catchable
IntegrityError rather than a second row nobody counts.

`window_start` is BigInteger epoch seconds, not a timestamp: it is compared
only for exact equality, and an integer carries no timezone semantics for two
dialects to disagree about.
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_rate_limit_counters"
down_revision = "0020_outcome_authorship"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("bucket_key", sa.String(length=128), nullable=False),
        sa.Column("window_start", sa.BigInteger(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "bucket_key", "window_start", name="uq_rate_limit_counters_key_window"
        ),
    )
    op.create_index(
        "ix_rate_limit_counters_bucket_key", "rate_limit_counters", ["bucket_key"]
    )
    op.create_index(
        "ix_rate_limit_counters_expires_at", "rate_limit_counters", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_counters_expires_at", table_name="rate_limit_counters")
    op.drop_index("ix_rate_limit_counters_bucket_key", table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")
```

- [ ] **Step 6: Run the model tests AND the migration guards**

Wait a moment after writing under `alembic/` (the OneDrive trap in Global
Constraints), then:

```
python -m pytest tests/test_ratelimit_store.py tests/test_migrations.py -q
```

Expected: PASS. `test_migrated_schema_matches_orm_models` and
`test_migrated_indexes_match_orm` are the ones that matter — they compare the
migration against the ORM and will name any drift.

- [ ] **Step 7: Commit**

```bash
git add app/ratelimit/models.py alembic/versions/0021_rate_limit_counters.py tests/conftest.py tests/test_ratelimit_store.py
git commit -m "feat(s83a): rate_limit_counters, and migration 0021

No foreign keys, deliberately: the login path writes a counter before any
principal exists. The unique constraint on (bucket_key, window_start) is the
load-bearing object -- it turns a lost INSERT race into a catchable
IntegrityError rather than a second row nobody counts."
```

---

### Task 4: `RateLimitStore.hit()` — the atomic increment

**Files:**
- Create: `app/ratelimit/store.py`
- Test: `tests/test_ratelimit_store.py` (extend)

**Interfaces:**
- Consumes: `RateLimitCounterRow` (Task 3).
- Produces:
  - `class RateLimitStore(session_factory)`
  - `RateLimitStore.hit(*, bucket_key: str, window_start: int, limit: int, expires_at: datetime | None) -> bool` — True = allowed and counted.
  - `RateLimitStore._try_increment(session, *, bucket_key, window_start, limit) -> bool` — the conditional UPDATE, exposed as a seam.
  - `def build_rate_limit_store(session_factory) -> RateLimitStore`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ratelimit_store.py`:

```python
from datetime import datetime, timezone

from app.ratelimit.store import RateLimitStore


def _store(session_factory) -> RateLimitStore:
    return RateLimitStore(session_factory)


def test_the_first_hit_is_allowed_and_creates_the_row(session_factory):
    store = _store(session_factory)
    assert store.hit(bucket_key="k", window_start=100, limit=3, expires_at=None)
    with session_factory() as session:
        row = session.query(RateLimitCounterRow).one()
        assert row.count == 1


def test_hits_are_allowed_up_to_the_limit_then_refused(session_factory):
    store = _store(session_factory)
    assert [
        store.hit(bucket_key="k", window_start=100, limit=3, expires_at=None)
        for _ in range(5)
    ] == [True, True, True, False, False]


def test_a_refused_hit_does_not_increment_past_the_limit(session_factory):
    """Otherwise the count climbs forever under attack and the row is useless
    for the metrics that make the limit observable."""
    store = _store(session_factory)
    for _ in range(6):
        store.hit(bucket_key="k", window_start=100, limit=2, expires_at=None)
    with session_factory() as session:
        assert session.query(RateLimitCounterRow).one().count == 2


def test_a_new_window_starts_a_fresh_count(session_factory):
    store = _store(session_factory)
    for _ in range(3):
        store.hit(bucket_key="k", window_start=100, limit=3, expires_at=None)
    assert store.hit(bucket_key="k", window_start=100, limit=3, expires_at=None) is False
    assert store.hit(bucket_key="k", window_start=200, limit=3, expires_at=None) is True


def test_opening_a_new_window_purges_the_old_row_for_that_key(session_factory):
    """Bounded housekeeping on a path that already runs -- the S7.1 challenge
    hygiene precedent. The Phase B sweep still owns the general case, for keys
    that are never seen again."""
    store = _store(session_factory)
    store.hit(bucket_key="k", window_start=100, limit=3, expires_at=None)
    store.hit(bucket_key="k", window_start=200, limit=3, expires_at=None)
    with session_factory() as session:
        rows = session.query(RateLimitCounterRow).all()
        assert [r.window_start for r in rows] == [200]


def test_keys_do_not_share_a_counter(session_factory):
    store = _store(session_factory)
    for _ in range(3):
        store.hit(bucket_key="a", window_start=100, limit=3, expires_at=None)
    assert store.hit(bucket_key="a", window_start=100, limit=3, expires_at=None) is False
    assert store.hit(bucket_key="b", window_start=100, limit=3, expires_at=None) is True


def test_a_limit_of_zero_refuses_without_creating_a_row(session_factory):
    """Config forbids 0 (ge=1), so this is defence in depth -- but the naive
    implementation would INSERT count=1 and ALLOW, which is the opposite of
    what a zero limit means."""
    store = _store(session_factory)
    assert store.hit(bucket_key="k", window_start=100, limit=0, expires_at=None) is False
    with session_factory() as session:
        assert session.query(RateLimitCounterRow).count() == 0


def test_expires_at_is_written_for_the_phase_b_sweep(session_factory):
    store = _store(session_factory)
    when = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
    store.hit(bucket_key="k", window_start=100, limit=3, expires_at=when)
    with session_factory() as session:
        assert session.query(RateLimitCounterRow).one().expires_at is not None


def test_the_conditional_update_refuses_a_row_already_at_its_limit(session_factory):
    """THE RACE, built directly on the seam.

    S8.4 Phase B measured this exact trap: two mutants on ScreeningStore's
    claim SURVIVED every end-to-end test, because the race they defend against
    is unreachable through two sequential public calls -- the second call's own
    read filters the row out long before the UPDATE matters. So the conditional
    UPDATE is driven here directly, in the one state where ONLY its
    `count < limit` clause can refuse.
    """
    store = _store(session_factory)
    store.hit(bucket_key="k", window_start=100, limit=1, expires_at=None)
    with session_factory() as session:
        assert store._try_increment(
            session, bucket_key="k", window_start=100, limit=1
        ) is False
        # ...and the same row IS incrementable under a higher limit, which is
        # what proves the refusal came from the clause and not from the row
        # being missing.
        assert store._try_increment(
            session, bucket_key="k", window_start=100, limit=5
        ) is True
```

- [ ] **Step 2: Run them and watch them fail**

```
python -m pytest tests/test_ratelimit_store.py -q
```

Expected: `ModuleNotFoundError: No module named 'app.ratelimit.store'`.

- [ ] **Step 3: Implement**

Create `app/ratelimit/store.py`:

```python
"""The rate limiter's only I/O (S8.3 Phase A).

`hit` is check-and-increment as ONE decision. Two concurrent requests on one
bucket must not both read count=19 and both write 20, so the check lives in the
WHERE clause of a conditional UPDATE and `rowcount` is the answer -- the exact
shape ScreeningStore._try_claim uses, for the exact same reason.

`_try_increment` is a separate method because the race it defends against is
UNREACHABLE through two sequential `hit` calls: the second call's UPDATE simply
finds a row at its limit. S8.4 Phase B measured two mutants surviving that way,
so the seam exists to let a test build the interleaved state directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.ratelimit.models import RateLimitCounterRow


class RateLimitStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def hit(
        self,
        *,
        bucket_key: str,
        window_start: int,
        limit: int,
        expires_at: Optional[datetime],
    ) -> bool:
        """Count one event against a bucket. True = allowed.

        A refused hit does NOT increment: the count would otherwise climb
        forever under attack, and the number is what the deny metric reports.
        """
        if limit <= 0:
            # Config forbids this (ge=1). Defence in depth, because the naive
            # path below would INSERT count=1 and ALLOW -- the opposite of what
            # a zero limit means.
            return False

        with self._session_factory() as session:
            if self._try_increment(
                session, bucket_key=bucket_key, window_start=window_start, limit=limit
            ):
                session.commit()
                return True

            # rowcount 0 means EITHER the row is at its limit OR it does not
            # exist yet. Those need opposite answers, so distinguish them.
            existing = session.execute(
                select(RateLimitCounterRow.id).where(
                    RateLimitCounterRow.bucket_key == bucket_key,
                    RateLimitCounterRow.window_start == window_start,
                )
            ).first()
            if existing is not None:
                session.rollback()
                return False

            try:
                # Housekeeping on a path that already runs (S7.1 precedent):
                # opening a new window for this key retires the previous one.
                # Bounded to this key; the Phase B sweep owns keys never seen
                # again.
                session.execute(
                    delete(RateLimitCounterRow).where(
                        RateLimitCounterRow.bucket_key == bucket_key,
                        RateLimitCounterRow.window_start < window_start,
                    )
                )
                session.add(
                    RateLimitCounterRow(
                        bucket_key=bucket_key,
                        window_start=window_start,
                        count=1,
                        expires_at=expires_at,
                    )
                )
                session.commit()
                return True
            except IntegrityError:
                # Somebody else opened the window between our SELECT and our
                # INSERT. Their row is authoritative; count against it.
                session.rollback()
                allowed = self._try_increment(
                    session, bucket_key=bucket_key,
                    window_start=window_start, limit=limit,
                )
                session.commit()
                return allowed

    @staticmethod
    def _try_increment(
        session: Session, *, bucket_key: str, window_start: int, limit: int
    ) -> bool:
        """Increment IF under the limit. The check and the write, one statement.

        Driven directly by tests/test_ratelimit_store.py -- see the module
        docstring for why an end-to-end test cannot reach the state this
        defends.
        """
        res = session.execute(
            update(RateLimitCounterRow)
            .where(
                RateLimitCounterRow.bucket_key == bucket_key,
                RateLimitCounterRow.window_start == window_start,
                RateLimitCounterRow.count < limit,
            )
            .values(count=RateLimitCounterRow.count + 1)
        )
        return res.rowcount == 1


def build_rate_limit_store(session_factory: sessionmaker) -> RateLimitStore:
    return RateLimitStore(session_factory)
```

- [ ] **Step 4: Run the tests**

```
python -m pytest tests/test_ratelimit_store.py -q
```

Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ratelimit/store.py tests/test_ratelimit_store.py
git commit -m "feat(s83a): the atomic increment -- check and count in one statement

The check lives in the WHERE clause of a conditional UPDATE and rowcount is the
answer, so two concurrent requests cannot both read 19 and both write 20.

_try_increment is a seam, not decomposition for its own sake: the race is
unreachable through two sequential hit() calls, which is precisely how two
mutants survived the same shape in S8.4 Phase B. A test drives it directly and
proves the refusal comes from the count<limit clause -- the same row increments
under a higher limit."
```

---

### Task 5: `RateLimiter.check()` — dual scoping

**Files:**
- Create: `app/ratelimit/service.py`
- Test: `tests/test_ratelimit_service.py`

**Interfaces:**
- Consumes: `RateLimitStore` (Task 4), `RateRule`/`LimitScope`/`LimitDecision` (Task 2), `Settings` (Task 1).
- Produces:
  - `class RateLimited(Exception)` with `.rule: str`, `.scope: LimitScope`, `.retry_after_seconds: int`
  - `class RateLimiter(store, *, settings, metrics=None)`
  - `RateLimiter.check(rules: list[RateRule], identities: dict[LimitScope, str | None], *, now: datetime) -> LimitDecision`
  - `RateLimiter.enforce(...)` — same signature, raises `RateLimited` when denied
  - `RateLimiter.rules_for(name: str) -> list[RateRule]` built from settings, where `name` is one of `"login_request"`, `"login_verify"`, `"screening_process"`, `"asr_transcribe"`
  - `def build_rate_limiter(settings, session_factory, *, metrics=None) -> RateLimiter`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ratelimit_service.py`:

```python
"""S8.3 Phase A: dual scoping. ALL scopes are counted; ANY denial denies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.ratelimit.models import RateLimitCounterRow
from app.ratelimit.schema import LimitScope, RateRule
from app.ratelimit.service import RateLimited, RateLimiter, build_rate_limiter
from tests.conftest import make_candidate_store

NOW = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def session_factory():
    return make_candidate_store()._session_factory


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


@pytest.fixture
def limiter(settings, session_factory) -> RateLimiter:
    return build_rate_limiter(settings, session_factory)


def _rules(email_limit: int, ip_limit: int) -> list[RateRule]:
    return [
        RateRule("r", email_limit, 3600, LimitScope.EMAIL),
        RateRule("r", ip_limit, 3600, LimitScope.IP),
    ]


def test_the_email_scope_can_deny_on_its_own(limiter):
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    rules = _rules(email_limit=2, ip_limit=100)
    for _ in range(2):
        assert limiter.check(rules, ids, now=NOW).allowed
    denied = limiter.check(rules, ids, now=NOW)
    assert denied.allowed is False
    assert denied.scope == LimitScope.EMAIL


def test_the_ip_scope_can_deny_on_its_own(limiter):
    """Spraying ONE guess across many addresses never trips a per-email
    counter. This is the half a per-email limit cannot see."""
    rules = _rules(email_limit=100, ip_limit=2)
    for i in range(2):
        assert limiter.check(
            rules, {LimitScope.EMAIL: f"{i}@x", LimitScope.IP: "1.1.1.1"}, now=NOW
        ).allowed
    denied = limiter.check(
        rules, {LimitScope.EMAIL: "third@x", LimitScope.IP: "1.1.1.1"}, now=NOW
    )
    assert denied.allowed is False
    assert denied.scope == LimitScope.IP


def test_one_address_from_many_ips_still_trips_the_email_scope(limiter):
    """The botnet half. A per-IP limit alone would let this through."""
    rules = _rules(email_limit=2, ip_limit=100)
    for i in range(2):
        assert limiter.check(
            rules, {LimitScope.EMAIL: "a@x", LimitScope.IP: f"10.0.0.{i}"}, now=NOW
        ).allowed
    assert limiter.check(
        rules, {LimitScope.EMAIL: "a@x", LimitScope.IP: "10.0.0.9"}, now=NOW
    ).allowed is False


def test_every_scope_is_counted_even_when_an_earlier_one_denies(
    limiter, session_factory
):
    """A limiter that stops counting at the first denial under-reports the
    attacker who tripped it -- and the second scope's window then looks clean
    to the operator reading the metrics."""
    rules = _rules(email_limit=1, ip_limit=100)
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    limiter.check(rules, ids, now=NOW)   # allowed
    limiter.check(rules, ids, now=NOW)   # denied by email
    with session_factory() as session:
        counts = sorted(
            r.count for r in session.query(RateLimitCounterRow).all()
        )
    assert counts == [1, 2], "the IP scope must have counted both attempts"


def test_a_missing_identity_skips_that_scope_and_keeps_the_others(limiter):
    """No client IP is determinable under some ASGI transports. A partial bound
    is correct; refusing a legitimate caller for a reason they cannot act on is
    not, and neither is skipping the whole rule."""
    rules = _rules(email_limit=1, ip_limit=1)
    assert limiter.check(
        rules, {LimitScope.EMAIL: "a@x", LimitScope.IP: None}, now=NOW
    ).allowed
    denied = limiter.check(
        rules, {LimitScope.EMAIL: "a@x", LimitScope.IP: None}, now=NOW
    )
    assert denied.allowed is False
    assert denied.scope == LimitScope.EMAIL


def test_a_later_window_is_a_clean_slate(limiter):
    rules = _rules(email_limit=1, ip_limit=100)
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    assert limiter.check(rules, ids, now=NOW).allowed
    assert limiter.check(rules, ids, now=NOW).allowed is False
    assert limiter.check(rules, ids, now=NOW + timedelta(hours=1)).allowed


def test_the_decision_carries_a_usable_retry_after(limiter):
    rules = _rules(email_limit=1, ip_limit=100)
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    limiter.check(rules, ids, now=NOW)
    denied = limiter.check(rules, ids, now=NOW + timedelta(minutes=20))
    assert denied.retry_after_seconds == 40 * 60


def test_disabled_means_allowed_without_touching_the_table(
    settings, session_factory
):
    off = settings.model_copy(update={"rate_limit_enabled": False})
    limiter = build_rate_limiter(off, session_factory)
    rules = _rules(email_limit=1, ip_limit=1)
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    for _ in range(5):
        assert limiter.check(rules, ids, now=NOW).allowed
    with session_factory() as session:
        assert session.query(RateLimitCounterRow).count() == 0


def test_enforce_raises_with_the_scope_and_the_wait(limiter):
    rules = _rules(email_limit=1, ip_limit=100)
    ids = {LimitScope.EMAIL: "a@x", LimitScope.IP: "1.1.1.1"}
    limiter.enforce(rules, ids, now=NOW)
    with pytest.raises(RateLimited) as exc:
        limiter.enforce(rules, ids, now=NOW)
    assert exc.value.scope == LimitScope.EMAIL
    assert exc.value.retry_after_seconds > 0


def test_rules_for_reads_the_configured_limits(settings, session_factory):
    tuned = settings.model_copy(update={
        "rate_limit_login_per_hour_per_email": 7,
        "rate_limit_login_per_hour_per_ip": 9,
    })
    limiter = build_rate_limiter(tuned, session_factory)
    by_scope = {r.scope: r for r in limiter.rules_for("login_request")}
    assert by_scope[LimitScope.EMAIL].limit == 7
    assert by_scope[LimitScope.IP].limit == 9
    assert by_scope[LimitScope.EMAIL].window_seconds == 3600


def test_every_named_rule_resolves(limiter):
    """A call site naming a rule that does not exist must fail loudly here, not
    silently limit nothing."""
    for name in ("login_request", "login_verify", "screening_process",
                 "asr_transcribe"):
        assert limiter.rules_for(name), name
    with pytest.raises(KeyError):
        limiter.rules_for("no_such_rule")
```

- [ ] **Step 2: Run them and watch them fail**

```
python -m pytest tests/test_ratelimit_service.py -q
```

Expected: `ModuleNotFoundError: No module named 'app.ratelimit.service'`.

- [ ] **Step 3: Implement**

Create `app/ratelimit/service.py`:

```python
"""RateLimiter (S8.3 Phase A) -- the object every call site talks to.

It is called from the SERVICE layer, never from a route. AuthService's own
docstring gives the reason: "Every gate lives here rather than on a route ... a
rule applied at one entry point and not the other has shipped as a real defect
in S7.1, S7.2 and S7.3." The OTP surface is EIGHT routes across three planes
and exactly TWO service methods.

DUAL SCOPING is the whole design. A rule is evaluated against every scope it
declares, ALL of them are counted, and any single denial denies. Per-email
alone lets an attacker spray one guess across ten thousand addresses; per-IP
alone lets a botnet grind one address.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional

from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ratelimit.schema import (
    LimitDecision, LimitScope, RateRule, bucket_key, retry_after, window_start,
)
from app.ratelimit.store import RateLimitStore, build_rate_limit_store

log = get_logger(__name__)

_HOUR = 3600


class RateLimited(Exception):
    """A caller exceeded a rule. Carries what the HTTP layer needs and nothing
    that tells an attacker which of their assumptions was right."""

    def __init__(
        self, rule: str, scope: LimitScope, retry_after_seconds: int
    ) -> None:
        super().__init__(f"rate limited by {rule}/{scope.value}")
        self.rule = rule
        self.scope = scope
        self.retry_after_seconds = retry_after_seconds


class RateLimiter:
    def __init__(
        self,
        store: RateLimitStore,
        *,
        settings: Settings,
        metrics=None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._metrics = metrics

    def rules_for(self, name: str) -> list[RateRule]:
        """The configured rules under one name. KeyError for an unknown name --
        a call site naming a rule that does not exist must fail loudly rather
        than silently limiting nothing."""
        s = self._settings
        table: dict[str, list[RateRule]] = {
            "login_request": [
                RateRule("login_request", s.rate_limit_login_per_hour_per_email,
                         _HOUR, LimitScope.EMAIL),
                RateRule("login_request", s.rate_limit_login_per_hour_per_ip,
                         _HOUR, LimitScope.IP),
            ],
            "login_verify": [
                RateRule("login_verify", s.rate_limit_verify_per_hour_per_email,
                         _HOUR, LimitScope.EMAIL),
                RateRule("login_verify", s.rate_limit_verify_per_hour_per_ip,
                         _HOUR, LimitScope.IP),
            ],
            "screening_process": [
                RateRule("screening_process", s.rate_limit_process_per_hour_per_org,
                         _HOUR, LimitScope.ORG),
            ],
            "asr_transcribe": [
                RateRule("asr_transcribe", s.rate_limit_asr_per_hour_per_candidate,
                         _HOUR, LimitScope.CANDIDATE),
            ],
        }
        return table[name]

    def check(
        self,
        rules: list[RateRule],
        identities: Mapping[LimitScope, Optional[str]],
        *,
        now: datetime,
    ) -> LimitDecision:
        """Count this event against every rule and return the decision.

        EVERY scope is counted before returning, even after one has denied. A
        limiter that stops at the first denial under-reports the attacker who
        tripped it, and leaves the second scope's window looking clean to
        whoever reads the metrics.
        """
        if not self._settings.rate_limit_enabled:
            return LimitDecision(allowed=True, rule=rules[0].name if rules else "")

        denial: Optional[LimitDecision] = None
        for rule in rules:
            identity = identities.get(rule.scope)
            if not identity:
                # No IP is determinable under some ASGI transports. A partial
                # bound is correct; refusing a legitimate caller for a reason
                # they cannot act on is not.
                continue
            opened = window_start(now, rule.window_seconds)
            allowed = self._store.hit(
                bucket_key=bucket_key(
                    rule=rule.name, scope=rule.scope, identity=identity,
                    salt=self._settings.contact_hash_salt,
                ),
                window_start=opened,
                limit=rule.limit,
                expires_at=datetime.fromtimestamp(opened, tz=timezone.utc)
                + timedelta(seconds=rule.window_seconds),
            )
            self._count(rule, allowed)
            if not allowed and denial is None:
                denial = LimitDecision(
                    allowed=False,
                    rule=rule.name,
                    scope=rule.scope,
                    retry_after_seconds=retry_after(now, opened, rule.window_seconds),
                )
        if denial is not None:
            log.info(
                "rate_limited", rule=denial.rule,
                scope=denial.scope.value if denial.scope else None,
            )
            return denial
        return LimitDecision(allowed=True, rule=rules[0].name if rules else "")

    def enforce(
        self,
        rules: list[RateRule],
        identities: Mapping[LimitScope, Optional[str]],
        *,
        now: datetime,
    ) -> None:
        """`check`, raising :class:`RateLimited` on a denial."""
        decision = self.check(rules, identities, now=now)
        if not decision.allowed and decision.scope is not None:
            raise RateLimited(
                decision.rule, decision.scope, decision.retry_after_seconds
            )

    def _count(self, rule: RateRule, allowed: bool) -> None:
        if self._metrics is None:
            return
        self._metrics.increment(
            "rate_limit_decisions",
            rule=rule.name,
            scope=rule.scope.value,
            decision="allowed" if allowed else "denied",
        )


def build_rate_limiter(
    settings: Optional[Settings],
    session_factory: sessionmaker,
    *,
    metrics=None,
) -> RateLimiter:
    settings = settings or get_settings()
    return RateLimiter(
        build_rate_limit_store(session_factory), settings=settings, metrics=metrics
    )
```

- [ ] **Step 4: Run the tests**

```
python -m pytest tests/test_ratelimit_service.py -q
```

Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ratelimit/service.py tests/test_ratelimit_service.py
git commit -m "feat(s83a): RateLimiter -- all scopes counted, any denial denies

Per-email alone lets an attacker spray one guess across ten thousand
addresses; per-IP alone lets a botnet grind one address. Neither is a bound, so
a rule is a LIST of scopes and every one of them is evaluated.

Every scope is counted even after an earlier one denied: stopping at the first
denial under-reports the attacker who tripped it and leaves the second scope's
window looking clean to whoever reads the metrics.

A missing identity SKIPS that scope and keeps the others -- no client IP is
determinable under some ASGI transports, and a partial bound beats refusing a
legitimate caller for a reason they cannot act on."
```

---

### Task 6: The metrics registry

Built before the auth wiring so the limiter's `metrics=` argument has a real
object to take, rather than being retrofitted through four call sites.

**Files:**
- Create: `app/metrics/__init__.py`, `app/metrics/registry.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class Metrics()` with `.increment(name: str, **labels: str) -> None`,
    `.observe_duration(route: str, ms: float) -> None`,
    `.render() -> str`, `.snapshot() -> dict[tuple, int]`
  - `def build_metrics() -> Metrics`

- [ ] **Step 1: Write the failing test**

Create `tests/test_metrics.py`:

```python
"""S8.3 Phase A: in-process counters. Per-app, never module-global."""

from __future__ import annotations

from app.metrics.registry import Metrics, build_metrics


def test_counters_start_at_zero_and_increment():
    m = Metrics()
    m.increment("http_requests", route="/healthz", method="GET", status="200")
    m.increment("http_requests", route="/healthz", method="GET", status="200")
    assert m.snapshot()[("http_requests", (("method", "GET"), ("route", "/healthz"), ("status", "200")))] == 2


def test_label_sets_are_distinct_series():
    m = Metrics()
    m.increment("http_requests", route="/a", method="GET", status="200")
    m.increment("http_requests", route="/b", method="GET", status="200")
    assert len(m.snapshot()) == 2


def test_two_registries_do_not_share_state():
    """A module-level counter would be shared by every test in the suite, and
    the first ordering-dependent assertion would be an unreproducible flake.
    This is why Metrics hangs off the injected Services bundle."""
    a, b = build_metrics(), build_metrics()
    a.increment("http_requests", route="/x", method="GET", status="200")
    assert b.snapshot() == {}


def test_render_is_prometheus_text():
    m = Metrics()
    m.increment("rate_limit_decisions", rule="login_request", scope="email",
                decision="denied")
    out = m.render()
    assert "# TYPE veritas_rate_limit_decisions_total counter" in out
    assert 'veritas_rate_limit_decisions_total{decision="denied",rule="login_request",scope="email"} 1' in out


def test_render_emits_a_type_line_once_per_metric():
    m = Metrics()
    m.increment("http_requests", route="/a", method="GET", status="200")
    m.increment("http_requests", route="/b", method="GET", status="200")
    assert m.render().count("# TYPE veritas_http_requests_total counter") == 1


def test_label_values_are_escaped():
    """A label value carrying a quote or a newline would produce a document no
    parser can read -- and route templates are ours, but an __unmatched__
    fallback is only as safe as the escaping behind it."""
    m = Metrics()
    m.increment("http_requests", route='/a"b\\c', method="GET", status="200")
    line = [x for x in m.render().splitlines() if x.startswith("veritas_http_requests")][0]
    assert '\\"' in line and "\\\\" in line


def test_duration_renders_as_a_sum_and_a_count():
    """An average, deliberately: no buckets, no quantiles, and OPERATING.md
    says so rather than letting a reader assume a histogram."""
    m = Metrics()
    m.observe_duration("/healthz", 10.0)
    m.observe_duration("/healthz", 30.0)
    out = m.render()
    assert 'veritas_http_request_duration_ms_sum{route="/healthz"} 40' in out
    assert 'veritas_http_request_duration_ms_count{route="/healthz"} 2' in out


def test_an_empty_registry_renders_an_empty_document():
    assert build_metrics().render() == ""
```

- [ ] **Step 2: Run it and watch it fail**

```
python -m pytest tests/test_metrics.py -q
```

Expected: `ModuleNotFoundError: No module named 'app.metrics'`.

- [ ] **Step 3: Implement**

Create `app/metrics/__init__.py` (empty) and `app/metrics/registry.py`:

```python
"""In-process counters (S8.3 Phase A).

A Metrics instance hangs off the injected Services bundle and is therefore
PER-APP. A module-level registry would be shared by every test in the suite and
the first ordering-dependent assertion would be a flake nobody could reproduce
-- which is the same reason Services exists at all.

Rendered as Prometheus text with no dependency: the exposition format is a
handful of lines, and adding prometheus_client to buy them would put a package
in the tree that only this file uses.

Durations are a SUM and a COUNT -- an average. No buckets, no quantiles.
Stating that is better than shipping a histogram whose buckets nobody chose.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Dict, Tuple

_PREFIX = "veritas_"

#: Counter name -> the metric's help text. A name absent here still renders;
#: this only supplies HELP, so a new counter is never blocked on documentation.
_HELP: Dict[str, str] = {
    "http_requests": "HTTP requests by route template, method and status.",
    "rate_limit_decisions": "Rate-limit decisions by rule, scope and outcome.",
    "llm_calls": "LLM calls by tier and outcome.",
    "asr_calls": "Speech-to-text calls by outcome.",
    "screening_items": "Screening items finished, by outcome.",
    "retention_deleted": "Rows deleted by the retention sweep, by data class.",
}

_LabelKey = Tuple[Tuple[str, str], ...]


def _escape(value: str) -> str:
    """Prometheus label-value escaping: backslash, quote, newline."""
    return (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )


class Metrics:
    def __init__(self) -> None:
        self._counters: Dict[Tuple[str, _LabelKey], int] = defaultdict(int)
        self._duration_sum: Dict[str, float] = defaultdict(float)
        self._duration_count: Dict[str, int] = defaultdict(int)
        self._lock = Lock()

    def increment(self, name: str, **labels: str) -> None:
        key = (name, tuple(sorted((k, str(v)) for k, v in labels.items())))
        with self._lock:
            self._counters[key] += 1

    def observe_duration(self, route: str, ms: float) -> None:
        with self._lock:
            self._duration_sum[route] += ms
            self._duration_count[route] += 1

    def snapshot(self) -> Dict[Tuple[str, _LabelKey], int]:
        with self._lock:
            return dict(self._counters)

    def render(self) -> str:
        """The Prometheus text exposition format, sorted for a stable document."""
        with self._lock:
            counters = dict(self._counters)
            d_sum = dict(self._duration_sum)
            d_count = dict(self._duration_count)

        lines: list[str] = []
        by_metric: Dict[str, list[Tuple[_LabelKey, int]]] = defaultdict(list)
        for (name, labels), value in counters.items():
            by_metric[name].append((labels, value))

        for name in sorted(by_metric):
            full = f"{_PREFIX}{name}_total"
            if name in _HELP:
                lines.append(f"# HELP {full} {_HELP[name]}")
            lines.append(f"# TYPE {full} counter")
            for labels, value in sorted(by_metric[name]):
                rendered = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
                lines.append(f"{full}{{{rendered}}} {value}")

        if d_count:
            lines.append(f"# TYPE {_PREFIX}http_request_duration_ms_sum counter")
            for route in sorted(d_sum):
                lines.append(
                    f'{_PREFIX}http_request_duration_ms_sum'
                    f'{{route="{_escape(route)}"}} {d_sum[route]:g}'
                )
            lines.append(f"# TYPE {_PREFIX}http_request_duration_ms_count counter")
            for route in sorted(d_count):
                lines.append(
                    f'{_PREFIX}http_request_duration_ms_count'
                    f'{{route="{_escape(route)}"}} {d_count[route]}'
                )

        return "\n".join(lines)


def build_metrics() -> Metrics:
    return Metrics()
```

- [ ] **Step 4: Run the tests**

```
python -m pytest tests/test_metrics.py -q
```

Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add app/metrics/ tests/test_metrics.py
git commit -m "feat(s83a): in-process counters, rendered as Prometheus text

Per-app, hanging off the Services bundle: a module-level registry would be
shared by every test in the suite and the first ordering-dependent assertion
would be an unreproducible flake.

No dependency -- the exposition format is a handful of lines, and
prometheus_client would put a package in the tree that one file uses.
Durations are a sum and a count, an average, with no buckets nobody chose."
```

---

### Task 7: Wire the limiter into the auth service, and populate `ip_hash`

**Files:**
- Modify: `app/auth/service.py` (`build_auth_service`, `AuthService.__init__`, `request_code`, `verify_code`)
- Modify: `app/api/routes.py` (add `_client_ip`, pass it to both auth helpers, translate `RateLimited` to 429)
- Modify: `app/services/__init__.py` (build `Metrics`, put it on the bundle, thread it into `build_auth_service`)
- Modify: `tests/conftest.py` (`make_services` builds a `Metrics` and passes it)
- Test: `tests/test_ratelimit_auth.py`

**Interfaces:**
- Consumes: `RateLimiter`/`RateLimited` (Task 5), `Metrics` (Task 6).
- Produces:
  - `AuthService.request_code(..., ip_hash: Optional[str] = None)` — raises `RateLimited`
  - `AuthService.verify_code(..., ip_hash: Optional[str] = None)` — raises `RateLimited`; now actually stores `ip_hash`
  - `Services.metrics: Metrics`
  - `routes._client_ip(request) -> Optional[str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ratelimit_auth.py`:

```python
"""S8.3 Phase A: the OTP surface, limited. The brute-force surface PI-8
created is the one the limiter exists for."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_services


@pytest.fixture
def client(services):
    return TestClient(create_app(services))


def _login(client, email: str, **kw):
    return client.post("/auth/org/login", json={"email": email}, **kw)


def test_login_is_refused_after_the_per_email_limit(client, services):
    limit = services.settings.rate_limit_login_per_hour_per_email
    for _ in range(limit):
        assert _login(client, "a@example.com").status_code == 202
    refused = _login(client, "a@example.com")
    assert refused.status_code == 429
    assert refused.json()["detail"] == "rate_limited"


def test_the_429_carries_a_retry_after_header(client, services):
    limit = services.settings.rate_limit_login_per_hour_per_email
    for _ in range(limit):
        _login(client, "a@example.com")
    refused = _login(client, "a@example.com")
    assert int(refused.headers["Retry-After"]) > 0


def test_a_known_and_an_unknown_address_are_refused_IDENTICALLY(client, services):
    """AUTH.md's anti-enumeration rule, from the other side. A 429 that only
    appeared for registered addresses would reopen the hole the uniform 202
    closed -- so the counter keys on the SUBMITTED address, whether or not it
    has an account.
    """
    limit = services.settings.rate_limit_login_per_hour_per_email
    for _ in range(limit):
        _login(client, "registered@example.com")
    for _ in range(limit):
        _login(client, "nobody@example.com")
    a = _login(client, "registered@example.com")
    b = _login(client, "nobody@example.com")
    assert a.status_code == b.status_code == 429
    assert a.json() == b.json()


def test_a_second_address_from_the_same_ip_is_unaffected_below_the_ip_limit(client):
    """Proves the email scope is per-address and not a global counter."""
    for _ in range(20):
        _login(client, "a@example.com")
    assert _login(client, "a@example.com").status_code == 429
    assert _login(client, "b@example.com").status_code == 202


def test_the_ip_scope_denies_a_spray_across_many_addresses(settings, fake_github,
                                                           flywheel):
    """One guess against many addresses never trips a per-email counter. With
    a low IP limit the spray is refused on an address that has never been
    seen -- which is the half a per-email limit cannot see."""
    tuned = settings.model_copy(update={"rate_limit_login_per_hour_per_ip": 3})
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    client = TestClient(create_app(services))
    for i in range(3):
        assert _login(client, f"user{i}@example.com").status_code == 202
    assert _login(client, "never-seen@example.com").status_code == 429


def test_x_forwarded_for_is_IGNORED_when_no_proxy_is_trusted(settings, fake_github,
                                                              flywheel):
    """THE decision that makes the per-IP scope worth anything. If the header
    were trusted by default, an attacker would reset their own scope on every
    request with a header they fully control, and the limiter would pass every
    other test in this file while bounding nothing."""
    tuned = settings.model_copy(update={"rate_limit_login_per_hour_per_ip": 3})
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    client = TestClient(create_app(services))
    for i in range(3):
        _login(client, f"u{i}@example.com", headers={"X-Forwarded-For": f"9.9.9.{i}"})
    refused = _login(
        client, "u9@example.com", headers={"X-Forwarded-For": "9.9.9.99"}
    )
    assert refused.status_code == 429


def test_x_forwarded_for_is_honoured_when_one_proxy_is_trusted(settings, fake_github,
                                                               flywheel):
    tuned = settings.model_copy(update={
        "rate_limit_login_per_hour_per_ip": 3,
        "rate_limit_trusted_proxy_hops": 1,
    })
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    client = TestClient(create_app(services))
    for i in range(3):
        _login(client, f"u{i}@example.com", headers={"X-Forwarded-For": "9.9.9.1"})
    assert _login(
        client, "u9@example.com", headers={"X-Forwarded-For": "9.9.9.2"}
    ).status_code == 202


def test_verify_has_its_own_rule_and_does_not_share_login_s_counter(client, services):
    limit = services.settings.rate_limit_login_per_hour_per_email
    for _ in range(limit):
        _login(client, "a@example.com")
    assert _login(client, "a@example.com").status_code == 429
    # verify is a different rule with its own window
    resp = client.post(
        "/auth/org/verify", json={"email": "a@example.com", "code": "000000"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_code"


def test_a_verify_storm_is_refused(client, services):
    limit = services.settings.rate_limit_verify_per_hour_per_email
    for _ in range(limit):
        client.post("/auth/org/verify",
                    json={"email": "a@example.com", "code": "000000"})
    refused = client.post(
        "/auth/org/verify", json={"email": "a@example.com", "code": "000000"}
    )
    assert refused.status_code == 429


def test_disabling_the_limiter_restores_the_old_behaviour(settings, fake_github,
                                                           flywheel):
    off = settings.model_copy(update={"rate_limit_enabled": False})
    services = make_services(off, github=fake_github, flywheel=flywheel)
    client = TestClient(create_app(services))
    for _ in range(40):
        assert _login(client, "a@example.com").status_code == 202
```

Add to `tests/test_auth_sessions.py` (or wherever session rows are inspected —
if no such file has a direct row read, put it in `tests/test_ratelimit_auth.py`):

```python
def test_a_session_records_the_ip_hash_and_never_the_ip(services):
    """auth_sessions.ip_hash was declared, plumbed through AuthStore and
    AuthService, and NEVER POPULATED -- the route did not pass it. PI-8 §7
    states the rule as though it were implemented. S8.3 needs IP extraction for
    the limiter anyway, so one helper closes both."""
    from app.auth.models import AuthSessionRow

    client = TestClient(create_app(services))
    client.post("/auth/org/signup",
                json={"email": "founder@example.com",
                      "organization_name": "Acme Staffing"})
    code = services.email.sent[-1].code if hasattr(services.email, "sent") else None
    if code is None:
        pytest.skip("email capture unavailable in this fixture")
    resp = client.post("/auth/org/verify",
                       json={"email": "founder@example.com", "code": code})
    assert resp.status_code == 200
    with services.candidates._session_factory() as session:
        row = session.query(AuthSessionRow).one()
        assert row.ip_hash, "ip_hash must be populated"
        assert "." not in row.ip_hash, "an ip_hash is a hash, never an address"
```

> **Note for the implementer:** read `tests/test_auth_api.py` first to copy this
> repo's established way of retrieving a captured OTP code — use that idiom
> rather than the `hasattr` probe above, and delete the `skip`.

- [ ] **Step 2: Run them and watch them fail**

```
python -m pytest tests/test_ratelimit_auth.py -q
```

Expected: every limit test fails with `202` where `429` is expected — the
limiter is not wired yet.

- [ ] **Step 3: Add the client-IP helper to routes**

In `app/api/routes.py`, beside `_session_cookie`:

```python
def _client_ip(request: Request) -> Optional[str]:
    """The caller's address, or None.

    X-Forwarded-For is IGNORED unless `rate_limit_trusted_proxy_hops` says how
    many proxies sit in front of us. This is the decision that determines
    whether the per-IP scope is worth anything: the header is entirely
    attacker-controlled, so trusting it by default would hand every caller a
    free reset of their own scope, and the limiter would pass its tests while
    bounding nothing.

    With `hops = n` we take the n-th entry FROM THE RIGHT -- the rightmost
    entries are the ones our own infrastructure appended, and everything to the
    left of them was supplied by the client.
    """
    settings = _services(request).settings
    hops = settings.rate_limit_trusted_proxy_hops
    if hops > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else None
```

- [ ] **Step 4: Accept and enforce the limit in `AuthService`**

In `app/auth/service.py`:

1. Add `limiter` to `AuthService.__init__` (keyword-only, **required**) and
   store it as `self._limiter`. A required argument cannot be forgotten
   silently; an optional one is a fail-open waiting for the next builder.
2. Add `ip_hash: Optional[str] = None` to `request_code`.
3. At the very top of `request_code`, **before** the provider probe:

```python
        self._limiter.enforce(
            self._limiter.rules_for("login_request"),
            {LimitScope.EMAIL: self._hash_email(email), LimitScope.IP: ip_hash},
            now=at,
        )
```

4. At the very top of `verify_code`, the same with `rules_for("login_verify")`.
5. Pass `ip_hash` through to `self._store.create_session(...)` where
   `verify_code` already accepts it (it does — the parameter exists and is
   forwarded at `app/auth/service.py:350`; nothing changes there).
6. In `build_auth_service`, construct the limiter from the session factory that
   is already in hand and add a `metrics` parameter:

```python
def build_auth_service(
    settings: Optional[Settings] = None,
    *,
    candidates: CandidateStore,
    ledger: LedgerStore,
    email: Optional[EmailClient] = None,
    metrics=None,
) -> AuthService:
    from app.ratelimit.service import build_rate_limiter
    from app.services.email import build_email

    settings = settings or get_settings()
    store = AuthStore(candidates._session_factory, ledger=ledger, settings=settings)
    return AuthService(
        store,
        candidates,
        ledger,
        email=email or build_email(settings),
        settings=settings,
        # Built HERE from the session factory already in hand rather than taken
        # as an optional argument: a limiter that can be omitted is a limiter
        # somebody omits, and the failure is silent.
        limiter=build_rate_limiter(
            settings, candidates._session_factory, metrics=metrics
        ),
    )
```

**Important:** the counter must be incremented **before** the "does this
address have an account?" branch, so that a registered and an unregistered
address consume the same budget. That is what makes the 429 identical for both.

- [ ] **Step 5: Translate `RateLimited` to 429 in the routes**

In `app/api/routes.py`, in both `_request_code` and `_verify`, pass
`ip_hash=contact_hash(ip, settings.contact_hash_salt) if ip else None` (use the
existing `contact_hash` import from `app.candidates.hashing`) and add:

```python
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail="rate_limited",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
```

Place it **before** the `except ChallengeRefused` clause. The detail is one
opaque string: which rule and which scope refused is operator information, and
it goes to the log line the limiter already emits, not to the caller.

- [ ] **Step 6: Put `Metrics` on the Services bundle**

In `app/services/__init__.py`: add `metrics: Metrics` to the `Services`
dataclass, build it in `build_default_services` (`metrics = build_metrics()`)
**before** `auth`, pass `metrics=metrics` into `build_auth_service`, and include
`metrics=metrics` in the returned `Services(...)`.

In `tests/conftest.py`'s `make_services`, add a `metrics=None` parameter,
default it with `metrics = metrics or build_metrics()`, pass it into
`build_auth_service`, and include it in the returned `Services(...)`.

- [ ] **Step 7: Run the new tests**

```
python -m pytest tests/test_ratelimit_auth.py -q
```

Expected: PASS.

- [ ] **Step 8: Run the WHOLE suite and fix the fallout**

```
python -m pytest -q
```

**Expect failures, and treat them as evidence rather than noise.** Any existing
test that now 429s is a test making more than 20 login attempts against one
address — which proves the limiter is live on the real path. Fix each by
building its services from
`settings.model_copy(update={"rate_limit_enabled": False})` **only** where the
test's subject is something else; if the test is about auth volume, keep the
limiter on and assert the new behaviour.

Do **not** globally disable the limiter in the `settings` fixture. A fixture
that cannot enforce an invariant will hide it — S8.2 recorded that lesson and
S8.4 Phase B paid for it twice.

- [ ] **Step 9: Commit**

```bash
git add app/auth/service.py app/api/routes.py app/services/__init__.py tests/conftest.py tests/test_ratelimit_auth.py tests/
git commit -m "feat(s83a): the OTP surface is limited, and ip_hash is finally real

The limiter is enforced inside AuthService.request_code/verify_code, not on
the eight routes: AuthService already owns every gate for exactly this reason,
and eight routes are eight chances to forget plus one more for route nine.

The counter is incremented BEFORE the has-an-account branch, so a registered
and an unregistered address consume the same budget and the 429 is
byte-identical for both -- otherwise the limiter reopens the enumeration hole
the uniform 202 closed.

X-Forwarded-For is ignored unless trusted_proxy_hops > 0, and the test proves
a spray with a rotating forged header is still refused.

auth_sessions.ip_hash was declared, plumbed through two layers and NEVER
populated -- routes.py did not pass it. The same helper the limiter needs
closes it."
```

---

### Task 8: Limit the spend paths — screening `process` and ASR

**Files:**
- Modify: `app/screening/service.py` (`ScreeningService.__init__`, `process`, `build_screening_service`)
- Modify: `app/interview/service.py` (`InterviewService.__init__`, `answer`)
- Modify: `app/api/routes.py` (429 translation on both routes)
- Modify: `app/services/__init__.py`, `tests/conftest.py` (pass the limiter)
- Test: `tests/test_ratelimit_spend.py`

**Interfaces:**
- Consumes: `RateLimiter` (Task 5).
- Produces: `ScreeningService.__init__(..., limiter: RateLimiter)` (required),
  `InterviewService.__init__(..., limiter: RateLimiter)` (required). Both raise
  `RateLimited` from `process` / `answer`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ratelimit_spend.py`:

```python
"""S8.3 Phase A: bounded per CALL is not bounded per CALLER.

`process` is capped at screening_max_items_per_call, which bounds one request
and says nothing at all about a client in a loop -- and every call bills a
model. The S8.5 wiring session named this gap when it made ANY error stop the
browser's driver loop, because there was no limiter to stop it properly.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_services


def _org_headers(services) -> dict:
    """Create an organisation and return its X-Org-Key header."""
    org = services.ledger.create_organization(name="Acme Staffing")
    key = services.ledger.issue_api_key(org.id)
    return {"X-Org-Key": key}


def test_process_is_refused_past_the_per_org_hourly_limit(settings, fake_github,
                                                           flywheel):
    tuned = settings.model_copy(update={"rate_limit_process_per_hour_per_org": 2})
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    client = TestClient(create_app(services))
    headers = _org_headers(services)
    batch = client.post(
        "/screening/batches",
        json={"name": "b", "domain": "genai",
              "items": [{"resume_text": "x"}, {"resume_text": "y"}]},
        headers=headers,
    ).json()
    for _ in range(2):
        assert client.post(
            f"/screening/batches/{batch['batch_id']}/process", headers=headers
        ).status_code == 200
    refused = client.post(
        f"/screening/batches/{batch['batch_id']}/process", headers=headers
    )
    assert refused.status_code == 429
    assert refused.json()["detail"] == "rate_limited"
    assert int(refused.headers["Retry-After"]) > 0


def test_one_org_s_spend_does_not_limit_another(settings, fake_github, flywheel):
    """The scope is the ORG. A global counter would let one noisy customer
    stop every other customer's screening -- a denial of service we would be
    inflicting on ourselves."""
    tuned = settings.model_copy(update={"rate_limit_process_per_hour_per_org": 1})
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    client = TestClient(create_app(services))
    a = _org_headers(services)
    b = _org_headers(services)
    for headers in (a, b):
        batch = client.post(
            "/screening/batches",
            json={"name": "b", "domain": "genai", "items": [{"resume_text": "x"}]},
            headers=headers,
        ).json()
        assert client.post(
            f"/screening/batches/{batch['batch_id']}/process", headers=headers
        ).status_code == 200
    # a is now at its limit; b's own first call already succeeded above.
    batch_a = client.post(
        "/screening/batches",
        json={"name": "b2", "domain": "genai", "items": [{"resume_text": "z"}]},
        headers=a,
    ).json()
    assert client.post(
        f"/screening/batches/{batch_a['batch_id']}/process", headers=a
    ).status_code == 429


def test_the_limit_is_checked_before_any_item_is_claimed(settings, fake_github,
                                                          flywheel):
    """A refused call must not leave items stuck in `processing` waiting for a
    claim timeout -- the S8.4 Phase B finding (4) shape: a bound that runs
    AFTER the work it bounds."""
    tuned = settings.model_copy(update={"rate_limit_process_per_hour_per_org": 1})
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    client = TestClient(create_app(services))
    headers = _org_headers(services)
    batch = client.post(
        "/screening/batches",
        json={"name": "b", "domain": "genai",
              "items": [{"resume_text": "x"}, {"resume_text": "y"}]},
        headers=headers,
    ).json()
    client.post(f"/screening/batches/{batch['batch_id']}/process", headers=headers)
    client.post(f"/screening/batches/{batch['batch_id']}/process", headers=headers)
    detail = client.get(
        f"/screening/batches/{batch['batch_id']}", headers=headers
    ).json()
    assert detail["counts"].get("processing", 0) == 0
```

> **Implementer note:** `_org_headers` above uses `services.ledger` methods —
> confirm the exact names against `app/ledger/store.py` and against how
> `tests/test_screening_api.py` already creates an org with a key, and copy
> that idiom rather than inventing one.

- [ ] **Step 2: Run them and watch them fail**

```
python -m pytest tests/test_ratelimit_spend.py -q
```

Expected: the 429 assertions fail with `200` — nothing is limited yet.

- [ ] **Step 3: Wire `ScreeningService`**

In `app/screening/service.py`:

```python
    def __init__(
        self,
        store: ScreeningStore,
        deps: IngestDeps,
        *,
        settings: Settings,
        limiter: "RateLimiter",
    ) -> None:
        ...
        self._limiter = limiter
```

At the top of `process`, **before** `self._store.batch_row(...)` and therefore
before any claim:

```python
        # BEFORE the claim, deliberately. A bound that runs after the work it
        # bounds is the S8.4 Phase B finding (4) shape -- and here it would
        # additionally leave items stuck `processing` until the claim timeout.
        self._limiter.enforce(
            self._limiter.rules_for("screening_process"),
            {LimitScope.ORG: org_id},
            now=self._now(),
        )
```

and in `build_screening_service`, take `metrics=None` and build the limiter
from the store's session factory:

```python
def build_screening_service(
    settings: Optional[Settings] = None, *, deps: IngestDeps, metrics=None
) -> ScreeningService:
    from app.ratelimit.service import build_rate_limiter

    settings = settings or get_settings()
    store = build_screening_store(settings)
    return ScreeningService(
        store, deps, settings=settings,
        limiter=build_rate_limiter(
            settings, store._session_factory, metrics=metrics
        ),
    )
```

- [ ] **Step 4: Wire `InterviewService`**

Same pattern: a required `limiter` on `__init__`, and at the top of `answer`,
**only when audio is present** (a typed answer costs nothing and must not
consume an ASR budget):

```python
        if audio_b64:
            self._limiter.enforce(
                self._limiter.rules_for("asr_transcribe"),
                {LimitScope.CANDIDATE: candidate_id},
                now=datetime.now(timezone.utc),
            )
```

Place it before `_resolve_answer` is awaited. Update `build_interview_service`
the same way `build_screening_service` was updated.

- [ ] **Step 5: Translate to 429 on both routes**

`process_screening_batch` and the interview answer route each gain:

```python
    except RateLimited as exc:
        raise HTTPException(
            status_code=429, detail="rate_limited",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
```

- [ ] **Step 6: Update the builders in `app/services/__init__.py` and `tests/conftest.py`**

Pass `metrics=metrics` into `build_screening_service` and
`build_interview_service`. In `conftest.make_services`, where
`ScreeningService(...)` is constructed directly (~line 325), add
`limiter=build_rate_limiter(settings, candidates._session_factory, metrics=metrics)`.

**Do not give `limiter` a default of `None`.** A required argument fails at
construction; an optional one fails silently at runtime, in production, on the
spend path.

- [ ] **Step 7: Run the tests, then the whole suite**

```
python -m pytest tests/test_ratelimit_spend.py -q
python -m pytest -q
```

Expected: PASS, PASS.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(s83a): bound the two spend paths -- screening process and ASR

Bounded per CALL is not bounded per CALLER: screening_max_items_per_call caps
one request and says nothing about a client in a loop, and every call bills a
model.

The check runs BEFORE the claim. A bound that runs after the work it bounds is
the S8.4 Phase B finding (4) shape, and here it would additionally strand items
in `processing` until the claim timeout.

The ASR rule fires only when audio is present -- a typed answer costs nothing
and must not consume a transcription budget.

Both services take `limiter` as a REQUIRED argument. An optional one is a
fail-open that surfaces in production, on the path that spends money."
```

---

### Task 9: In-place retry of failed items

**Files:**
- Modify: `app/screening/store.py` (add `requeue_failed`)
- Modify: `app/screening/service.py` (add `retry`)
- Modify: `app/screening/schema.py` (add `RetryResult`)
- Modify: `app/api/routes.py` (add the route)
- Test: `tests/test_screening_retry.py`

**Interfaces:**
- Consumes: `ScreeningStore`, `OrgScopedAccess` ownership semantics.
- Produces:
  - `class RetryResult(BaseModel)`: `batch_id: str`, `requeued: int`, `skipped: int`
  - `ScreeningStore.requeue_failed(org_id: str, batch_id: str) -> tuple[int, int]` — `(requeued, skipped)`, or `None` when the batch is not this org's
  - `ScreeningService.retry(org_id: str, batch_id: str) -> Optional[RetryResult]`
  - `POST /screening/batches/{batch_id}/retry` → `RetryResult`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_screening_retry.py`:

```python
"""S8.3 Phase A: in-place retry.

SCREENING.md §7 has been admitting since S8.4 Phase B that batch_items.raw_text
is "kept on failure -- for a retry path that DOES NOT EXIST YET". This is that
path, and it is what justifies retaining the text at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.screening.models import BatchItemRow
from app.screening.schema import ItemStatus


def _fail_item(services, item_id: str, *, error: str = "internal_error",
               clear_text: bool = False) -> None:
    with services.candidates._session_factory() as session:
        row = session.get(BatchItemRow, item_id)
        row.status = ItemStatus.FAILED.value
        row.error = error
        if clear_text:
            row.raw_text = ""
        session.commit()


def test_a_failed_item_is_requeued_and_becomes_claimable(services, org_headers):
    client = TestClient(create_app(services))
    batch = client.post(
        "/screening/batches",
        json={"name": "b", "domain": "genai", "items": [{"resume_text": "x"}]},
        headers=org_headers,
    ).json()
    with services.candidates._session_factory() as session:
        item_id = session.query(BatchItemRow).one().id
    _fail_item(services, item_id)

    resp = client.post(
        f"/screening/batches/{batch['batch_id']}/retry", headers=org_headers
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "batch_id": batch["batch_id"], "requeued": 1, "skipped": 0
    }
    with services.candidates._session_factory() as session:
        row = session.get(BatchItemRow, item_id)
        assert row.status == ItemStatus.PENDING.value
        assert row.error is None
        assert row.claimed_at is None
        assert row.processed_at is None


def test_an_item_with_no_text_is_SKIPPED_not_requeued(services, org_headers):
    """Either the text was cleared on success or the failure was empty_resume.
    Re-queueing it would report `requeued: 1` and then fail identically -- a
    promise the next process call breaks."""
    client = TestClient(create_app(services))
    batch = client.post(
        "/screening/batches",
        json={"name": "b", "domain": "genai", "items": [{"resume_text": "x"}]},
        headers=org_headers,
    ).json()
    with services.candidates._session_factory() as session:
        item_id = session.query(BatchItemRow).one().id
    _fail_item(services, item_id, error="empty_resume", clear_text=True)

    body = client.post(
        f"/screening/batches/{batch['batch_id']}/retry", headers=org_headers
    ).json()
    assert body == {"batch_id": batch["batch_id"], "requeued": 0, "skipped": 1}
    with services.candidates._session_factory() as session:
        assert session.get(BatchItemRow, item_id).status == ItemStatus.FAILED.value


def test_done_and_pending_items_are_untouched(services, org_headers):
    """Retry means 'try the failures again', not 'run everything again'. A
    finished item has had its text cleared and is not re-runnable at all."""
    client = TestClient(create_app(services))
    batch = client.post(
        "/screening/batches",
        json={"name": "b", "domain": "genai",
              "items": [{"resume_text": "a"}, {"resume_text": "b"}]},
        headers=org_headers,
    ).json()
    with services.candidates._session_factory() as session:
        rows = session.query(BatchItemRow).order_by(BatchItemRow.id).all()
        done_id, pending_id = rows[0].id, rows[1].id
        rows[0].status = ItemStatus.DONE.value
        rows[0].raw_text = ""
        session.commit()

    body = client.post(
        f"/screening/batches/{batch['batch_id']}/retry", headers=org_headers
    ).json()
    assert body["requeued"] == 0 and body["skipped"] == 0
    with services.candidates._session_factory() as session:
        assert session.get(BatchItemRow, done_id).status == ItemStatus.DONE.value
        assert session.get(BatchItemRow, pending_id).status == ItemStatus.PENDING.value


def test_another_org_gets_404_never_403(services, org_headers, other_org_headers):
    """403 confirms the batch exists to anyone guessing ids. The same rule S8.5
    asserted on both outcome verbs."""
    client = TestClient(create_app(services))
    batch = client.post(
        "/screening/batches",
        json={"name": "b", "domain": "genai", "items": [{"resume_text": "x"}]},
        headers=org_headers,
    ).json()
    theirs = client.post(
        f"/screening/batches/{batch['batch_id']}/retry", headers=other_org_headers
    )
    unknown = client.post(
        "/screening/batches/00000000-0000-0000-0000-000000000000/retry",
        headers=other_org_headers,
    )
    assert theirs.status_code == unknown.status_code == 404
    assert theirs.json() == unknown.json()


def test_a_requeued_item_is_actually_picked_up_by_process(services, org_headers):
    """The point of the whole task: retry re-queues, and the EXISTING process
    door does the work. There is no second processing path."""
    client = TestClient(create_app(services))
    batch = client.post(
        "/screening/batches",
        json={"name": "b", "domain": "genai", "items": [{"resume_text": "x"}]},
        headers=org_headers,
    ).json()
    with services.candidates._session_factory() as session:
        item_id = session.query(BatchItemRow).one().id
    _fail_item(services, item_id)
    client.post(f"/screening/batches/{batch['batch_id']}/retry", headers=org_headers)
    result = client.post(
        f"/screening/batches/{batch['batch_id']}/process", headers=org_headers
    ).json()
    assert result["processed"] + result["failed"] == 1
```

> **Implementer note:** `org_headers` / `other_org_headers` fixtures — reuse the
> ones `tests/test_screening_api.py` already defines (copy them into this file
> or lift them into `conftest.py` if they are local). Check the exact
> `ProcessResult` field names off `app/screening/schema.py` before asserting on
> them.

- [ ] **Step 2: Run them and watch them fail**

```
python -m pytest tests/test_screening_retry.py -q
```

Expected: `404` on the retry route — it does not exist.

- [ ] **Step 3: Add `RetryResult` to the schema**

In `app/screening/schema.py`:

```python
class RetryResult(BaseModel):
    """The result of re-queueing a batch's failed items (S8.3 Phase A).

    `skipped` is not padding: an item whose raw_text is gone cannot be retried,
    and reporting it as requeued would be a promise the next `process` call
    breaks.
    """

    batch_id: str
    requeued: int = 0
    skipped: int = 0
```

- [ ] **Step 4: Add `requeue_failed` to the store**

In `app/screening/store.py`:

```python
    def requeue_failed(
        self, org_id: str, batch_id: str
    ) -> Optional[tuple[int, int]]:
        """Flip this batch's FAILED items back to pending. (requeued, skipped).

        None when the batch is not this organisation's, so the route answers
        404 -- another org's batch must be indistinguishable from one that does
        not exist.

        An item whose `raw_text` is empty is SKIPPED: either it succeeded and
        its text was cleared, or it failed as `empty_resume` and would fail
        identically. The status change is all this does; the existing `process`
        call is still the only door that evaluates anything.
        """
        with self._session_factory() as session:
            batch = session.execute(
                select(ScreeningBatchRow).where(
                    ScreeningBatchRow.id == batch_id,
                    ScreeningBatchRow.org_id == org_id,
                )
            ).scalar_one_or_none()
            if batch is None:
                return None

            failed = session.execute(
                select(BatchItemRow).where(
                    BatchItemRow.batch_id == batch_id,
                    BatchItemRow.status == ItemStatus.FAILED.value,
                )
            ).scalars().all()

            requeued = skipped = 0
            for row in failed:
                if not row.raw_text:
                    skipped += 1
                    continue
                row.status = ItemStatus.PENDING.value
                row.error = None
                row.claimed_at = None
                row.processed_at = None
                requeued += 1
            session.commit()
            return requeued, skipped
```

- [ ] **Step 5: Add `retry` to the service**

```python
    def retry(self, org_id: str, batch_id: str) -> Optional[RetryResult]:
        """Re-queue this batch's failed items. None = not this org's, or absent."""
        found = self._store.requeue_failed(org_id, batch_id)
        if found is None:
            return None
        requeued, skipped = found
        return RetryResult(batch_id=batch_id, requeued=requeued, skipped=skipped)
```

- [ ] **Step 6: Add the route**

In `app/api/routes.py`, immediately after `process_screening_batch`:

```python
@org_router.post("/screening/batches/{batch_id}/retry", response_model=RetryResult)
async def retry_screening_batch(
    batch_id: str, request: Request, org_id: str = Depends(require_org)
) -> RetryResult:
    """Re-queue this batch's failed items, then call `process` as usual.

    It re-queues; it does NOT process. There is exactly one door that evaluates
    an item, and this is not a second one -- which is why an item with no
    remaining text is reported as `skipped` rather than quietly re-queued.
    """
    result = _services(request).screening.retry(org_id, batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return result
```

Import `RetryResult` alongside the other screening schema imports.

- [ ] **Step 7: Run the tests, then the whole suite**

```
python -m pytest tests/test_screening_retry.py -q
python -m pytest -q
```

Expected: PASS, PASS. `tests/test_openapi_contract.py` and
`tests/test_route_table_guard.py` cover the new route automatically — the
route-table guard should stay green because `org_router` already carries
`require_org`.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(s83a): in-place retry -- re-queue the failures, one door still processes

SCREENING.md §7 has said since S8.4 Phase B that raw_text is kept on failure
for a retry path that does not exist. This is that path, and it is what
justifies retaining the text at all.

It re-queues and stops: the existing process call does the work, so there is
exactly one door that evaluates an item. An item whose text is gone is reported
as SKIPPED rather than quietly re-queued -- requeued:1 on an item that cannot
run is a promise the next process call breaks.

Batch-level, not per-item: the real input is 3 failures in a 200-item batch,
and the wired UI has no per-item action to hang one on. 404 never 403 on
another org's batch."
```

---

### Task 10: The `/metrics` route and the counting middleware

**Files:**
- Modify: `app/main.py` (count inside the existing `request_context` middleware)
- Modify: `app/api/routes.py` (add `GET /metrics`)
- Test: `tests/test_metrics.py` (extend)

**Interfaces:**
- Consumes: `Metrics` (Task 6), `Services.metrics` (Task 7).
- Produces: `GET /metrics` → `text/plain` Prometheus exposition, admin-gated.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_metrics.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(services):
    return TestClient(create_app(services))


def test_metrics_requires_the_admin_credential(client):
    """It is on the admin router, so the gate is inherited rather than
    remembered -- there is no second place to forget it."""
    assert client.get("/metrics").status_code == 401


def test_metrics_renders_prometheus_text(client, admin_headers):
    client.get("/healthz")
    resp = client.get("/metrics", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "veritas_http_requests_total" in resp.text


def test_requests_are_labelled_by_ROUTE_TEMPLATE_not_by_path(client, admin_headers,
                                                              services):
    """THE cardinality decision. Labelling by raw path makes one series per
    batch id, and a scanner walking random URLs is an unbounded memory leak
    dressed as observability."""
    client.get("/screening/batches/aaaaaaaa-0000-0000-0000-000000000000")
    client.get("/screening/batches/bbbbbbbb-0000-0000-0000-000000000000")
    text = client.get("/metrics", headers=admin_headers).text
    assert 'route="/screening/batches/{batch_id}"' in text
    assert "aaaaaaaa" not in text and "bbbbbbbb" not in text


def test_an_unmatched_path_gets_one_shared_label(client, admin_headers):
    client.get("/no/such/thing/1")
    client.get("/no/such/thing/2")
    text = client.get("/metrics", headers=admin_headers).text
    assert 'route="__unmatched__"' in text
    assert "no/such/thing" not in text


def test_a_rate_limited_request_is_counted_as_denied(settings, fake_github,
                                                      flywheel, admin_headers):
    from tests.conftest import make_services

    tuned = settings.model_copy(update={"rate_limit_login_per_hour_per_email": 1})
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    client = TestClient(create_app(services))
    client.post("/auth/org/login", json={"email": "a@example.com"})
    client.post("/auth/org/login", json={"email": "a@example.com"})
    text = client.get("/metrics", headers=admin_headers).text
    assert 'decision="denied"' in text
    assert 'rule="login_request"' in text
```

- [ ] **Step 2: Run them and watch them fail**

```
python -m pytest tests/test_metrics.py -q
```

Expected: `404` on `/metrics`.

- [ ] **Step 3: Count in the middleware**

In `app/main.py`, inside `request_context`'s `finally` block, after the existing
`log.info("access", ...)`:

```python
            # Label by the ROUTE TEMPLATE, never the raw path: the raw path is
            # one series per batch id, and a scanner walking random URLs would
            # be an unbounded memory leak dressed as observability.
            route = request.scope.get("route")
            template = getattr(route, "path", None) or "__unmatched__"
            metrics = getattr(app.state, "services", None)
            if metrics is not None:
                metrics.metrics.increment(
                    "http_requests",
                    route=template,
                    method=request.method,
                    status=str(status),
                )
                metrics.metrics.observe_duration(
                    template, round((time.perf_counter() - start) * 1000, 1)
                )
```

> **If `request.scope.get("route")` is None for matched routes** (Starlette's
> `BaseHTTPMiddleware` can hand the endpoint a copied scope), fall back to
> resolving the template yourself:
> ```python
> from starlette.routing import Match
> def _template(app, request) -> str:
>     for route in app.routes:
>         if route.matches(request.scope)[0] == Match.FULL:
>             return getattr(route, "path", "__unmatched__")
>     return "__unmatched__"
> ```
> Use whichever the test proves works; do not ship both.

- [ ] **Step 4: Add the route**

In `app/api/routes.py`, beside `GET /domains`:

```python
@router.get("/metrics", response_model=str, response_class=PlainTextResponse)
async def metrics(request: Request) -> PlainTextResponse:
    """Prometheus text exposition (S8.3 Phase A).

    On the admin router, so `require_api_key` is inherited rather than
    remembered. `response_model=str` is honest -- the body IS a string -- and
    keeps tests/test_openapi_contract.py's every-route-declares-a-model rule
    intact without an exemption.
    """
    return PlainTextResponse(
        _services(request).metrics.render(),
        media_type="text/plain; version=0.0.4",
    )
```

Add `from fastapi.responses import PlainTextResponse` to the imports.

- [ ] **Step 5: Run the tests, then the whole suite**

```
python -m pytest tests/test_metrics.py -q
python -m pytest -q
```

Expected: PASS, PASS. Watch `tests/test_openapi_contract.py` specifically —
`test_every_route_declares_a_response_model` is the one that would object to a
plain-text route.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(s83a): GET /metrics, labelled by route template

Labelling by raw path would make one series per batch id, and a scanner
walking random URLs would be an unbounded memory leak dressed as
observability. Unmatched requests collapse to one __unmatched__ label.

On the admin router, so the credential gate is inherited rather than
remembered. response_model=str is honest -- the body is a string -- and keeps
the every-route-declares-a-model rule intact with no exemption."
```

---

### Task 11: Mutation probes

Not a feature — the evidence that Tasks 4–10 are actually load-bearing. S8.4
Phase B found **two surviving mutants** on the same conditional-UPDATE shape,
so this is not ceremony.

**Files:** none committed (probes are applied and reverted).

- [ ] **Step 1: Plant each mutant, run the named test file, revert**

For each row: apply the change, run the command, confirm it goes **RED** and
that the failure names the test in the third column, then `git checkout --` the
file.

| # | Mutation | Must be killed by |
|---|---|---|
| 1 | `app/ratelimit/store.py`: delete `RateLimitCounterRow.count < limit` from `_try_increment`'s WHERE | `tests/test_ratelimit_store.py::test_the_conditional_update_refuses_a_row_already_at_its_limit` |
| 2 | `app/ratelimit/store.py`: change `res.rowcount == 1` to `res.rowcount >= 0` | `tests/test_ratelimit_store.py::test_hits_are_allowed_up_to_the_limit_then_refused` |
| 3 | `app/ratelimit/store.py`: delete the `if limit <= 0: return False` guard | `tests/test_ratelimit_store.py::test_a_limit_of_zero_refuses_without_creating_a_row` |
| 4 | `app/ratelimit/service.py`: `break` out of the rule loop on the first denial | `tests/test_ratelimit_service.py::test_every_scope_is_counted_even_when_an_earlier_one_denies` |
| 5 | `app/ratelimit/service.py`: `continue` past a rule when `identity` is falsy → change to `return LimitDecision(allowed=True, ...)` | `tests/test_ratelimit_service.py::test_a_missing_identity_skips_that_scope_and_keeps_the_others` |
| 6 | `app/api/routes.py`: make `_client_ip` read `X-Forwarded-For` unconditionally | `tests/test_ratelimit_auth.py::test_x_forwarded_for_is_IGNORED_when_no_proxy_is_trusted` |
| 7 | `app/auth/service.py`: move the `enforce` call in `request_code` to **after** the account-existence branch | `tests/test_ratelimit_auth.py::test_a_known_and_an_unknown_address_are_refused_IDENTICALLY` |
| 8 | `app/screening/service.py`: move the `enforce` call in `process` to **after** `self._store.claim(...)` | `tests/test_ratelimit_spend.py::test_the_limit_is_checked_before_any_item_is_claimed` |
| 9 | `app/screening/store.py`: in `requeue_failed`, re-queue rows with empty `raw_text` too | `tests/test_screening_retry.py::test_an_item_with_no_text_is_SKIPPED_not_requeued` |
| 10 | `app/main.py`: label with `request.url.path` instead of the route template | `tests/test_metrics.py::test_requests_are_labelled_by_ROUTE_TEMPLATE_not_by_path` |

- [ ] **Step 2: If any mutant SURVIVES, do not weaken it — strengthen the test**

A survivor means the behaviour is not covered. Write the test that kills it,
then re-run. Record any survivor and its fix in the roadmap entry (Task 13) —
S8.4 Phase B's two survivors were the most useful thing that sprint learned.

- [ ] **Step 3: Confirm the tree is clean and the suite is green**

```
git status --porcelain
python -m pytest -q
```

Expected: no output from the first; PASS from the second.

---

### Task 12: `smoke_s83a.py`

**Files:**
- Create: `scripts/smoke_s83a.py`

**Interfaces:**
- Consumes: the running app over real HTTP.
- Produces: exit 0 and an `N/N` line, following `scripts/smoke_s84b.py`'s
  structure exactly (read it first and copy its harness).

- [ ] **Step 1: Read the existing smoke and copy its shape**

```
cat scripts/smoke_s85_outcome.py
```

Copy: the uvicorn launch, the check counter, the `DEE_OPENROUTER_API_KEY=""`
pin (**mandatory** — five smokes were found making live billed calls in S8.4
Phase A, and `smoke_s63` was found doing it again one sprint later), the
throwaway cookie jar for org onboarding, and the CSRF handling.

- [ ] **Step 2: Write the smoke with these checks**

The checks, in order. **Check 6 is the one that justifies the whole sprint's
storage decision and must not be dropped:**

1. `GET /healthz` → 200.
2. Sign up an org through a real session; drive `/auth/org/login` to the
   configured per-email limit; the next call is **429**.
3. That 429 carries a numeric `Retry-After` > 0.
4. An address that was never registered, driven to the same limit, produces a
   **byte-identical** 429 body and status.
5. With the limit reached for address A, address B still gets 202 (the email
   scope is per address, not global).
6. **RESTART THE APP against the SAME database** — terminate the uvicorn
   process, start a new one on the same `DEE_CANDIDATES_DB_URL`, and confirm
   address A is **still 429**. *An in-process limiter would pass checks 2–5 and
   fail this one; this check is the entire argument for the DB-backed choice.*
7. Register a two-item batch as an org, `process` it to completion.
8. Force one item to `failed` over the DB, `POST .../retry` → `requeued: 1`.
9. `process` again → the item is picked up (`processed + failed == 1`).
10. `POST .../retry` on a batch id that does not exist → **404**, byte-identical
    to a retry on another org's batch.
11. `GET /metrics` without the admin key → 401.
12. `GET /metrics` with it → 200, `text/plain`, containing
    `veritas_rate_limit_decisions_total` with `decision="denied"`.
13. `/metrics` contains `route="/screening/batches/{batch_id}"` and does **not**
    contain the literal batch id.

- [ ] **Step 3: Run it**

```
python scripts/smoke_s83a.py
```

Expected: `13/13`, exit 0.

- [ ] **Step 4: Re-run the regression smokes**

```
python scripts/smoke_s84a.py
python scripts/smoke_s84b.py
python scripts/smoke_s85_outcome.py
python scripts/smoke_s82.py
```

Expected: all green. `smoke_s82` is the auth smoke and is the one most likely
to trip the new limiter — if it does, that is a **real finding** about how many
login attempts a normal onboarding makes, and it belongs in the roadmap entry.

- [ ] **Step 5: Commit**

```bash
git add scripts/smoke_s83a.py
git commit -m "test(s83a): smoke -- and the check that a unit test cannot reach

Check 6 restarts the app against the same database and confirms the limit
still holds. That is the entire argument for DB-backed counters: an in-process
limiter passes every other check in this file and fails exactly that one."
```

---

### Task 13: Documentation

**Files:**
- Create: `OPERATING.md`
- Modify: `SCREENING.md` §7, `UI.md` §4.A
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Write `OPERATING.md`**

Sections, in this order:

1. **What is limited, and where the check lives** — the rule table (name, scopes,
   defaults, call site), and the reason it is in the service layer rather than
   on routes (AuthService's docstring; 8 routes vs 2 methods).
2. **Fixed windows, stated honestly** — a burst of up to 2× the limit is
   reachable across a window edge; for a 20/hour OTP bound that is irrelevant,
   and sliding windows cost a row per event.
3. **`X-Forwarded-For` and `rate_limit_trusted_proxy_hops`** — the default is 0,
   what to set it to on Railway, and why the wrong value fails open.
4. **429 and the enumeration rule** — why the 429 is identical for registered
   and unregistered addresses, and why the 60-second resend cooldown keeps its
   silent 202 (different key, different oracle).
5. **Metrics** — the counter list, the route-template cardinality rule, that
   durations are an average with no quantiles, and that `/metrics` is
   admin-gated.
6. **Retry** — what it does (re-queue), what it does not (process), what
   `skipped` means, and **that a retry window will be bounded by
   `ret_batch_item_days` once Phase B's sweep lands**.
7. **Runbook** — what to do when a customer reports a 429, how to raise a limit,
   and the fact that raising `rate_limit_enabled` to false is refused in prod.

- [ ] **Step 2: Correct `SCREENING.md` §7**

Replace the "kept on failure — for a retry path that DOES NOT EXIST YET"
paragraph with the truth: the path exists
(`POST /screening/batches/{id}/retry`), it re-queues rather than processes, an
item with no text is skipped, and the retention window that will eventually
bound it is `ret_batch_item_days` (Phase B). **Do not claim the sweep exists
yet** — that is the exact overclaim the S8.4 Phase B review corrected here.

- [ ] **Step 3: Update `UI.md` §4.A**

Add to the WIRED note: a failed row is now genuinely retryable via
`POST /screening/batches/{id}/retry`, so the "it is not a verdict about the
person" sentence is now backed by an action. Note that the client's driver loop
may now receive a **429** and must stop and surface a wait, not retry — the
existing "any error stops it" behaviour is correct and now has a named case.

- [ ] **Step 4: Update `docs/ROADMAP.md`**

Add a "Current state" bullet at the top following the established form: what
was built, the test count delta, the smoke result, the load-bearing decisions,
any mutant that survived, anything measured that contradicted an assumption,
and `➤ NEXT STEP: S8.3 Phase B`. Mark S8.3 partially done in the status board.

- [ ] **Step 5: Final verification and commit**

```
python -m pytest -q
git add -A
git commit -m "docs(s83a): OPERATING.md, and SCREENING.md stops promising a retry it lacked"
```

---

## Self-Review

**Spec coverage:**

| Spec § | Task |
|---|---|
| §2.1 table | 3 |
| §2.2 atomic increment | 4 (+ probes 1–3 in 11) |
| §2.3 dual scoping | 5 (+ probes 4–5) |
| §2.4 rule table | 5 |
| §3.1 service-layer call sites | 7, 8 |
| §3.2 `_client_ip` + `ip_hash` | 7 (+ probe 6) |
| §3.3 429 not an oracle | 7 (+ probe 7) |
| §3.4 prod boot refusal | 1 |
| §4 in-place retry | 9 (+ probe 9) |
| §5.1 per-app registry | 6 |
| §5.2 route-template labels | 10 (+ probe 10) |
| §5.3 counter list | 6, 10 |
| §5.4 `GET /metrics` | 10 |
| §6 verification | 11, 12 |
| §12 documentation | 13 |

**Deliberately not in this plan:** §5.3's `llm_calls` / `asr_calls` /
`screening_items` counters are declared in `_HELP` (Task 6) but no call site
increments them. Adding four increments across the LLM client, the speech
client and the screening service is a fifth wiring job for counters nothing
reads yet, and `rate_limit_decisions` is the one the phase's argument depends
on. **Recorded here rather than silently skipped** — they belong with the
`retention_deleted` counter in Phase B, where the sweep gives them a reason to
be read together. If the reviewer disagrees, it is one increment per call site
and no new structure.

**Type consistency:** `LimitScope`, `RateRule`, `LimitDecision`, `RateLimited`,
`RateLimiter.check/enforce/rules_for`, `RateLimitStore.hit/_try_increment`,
`Metrics.increment/observe_duration/render/snapshot`, `RetryResult`,
`ScreeningStore.requeue_failed`, `ScreeningService.retry` — each is defined once
in an Interfaces block and used with the same signature everywhere after.
