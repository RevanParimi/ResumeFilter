# S8.1 — Deployable spine (design)

**Date:** 2026-08-01
**Sprint:** PI-8, S8.1 — the first of four (`S8.1` spine · `S8.2` identity &
access · `S8.3` operating safely · `S8.4` UI integration surface).
**Status:** Design approved by the user 2026-08-01, before any code.
**Read order:** `docs/ROADMAP.md` "Next action" →
`2026-08-01-pi8-launch-readiness-design.md` (the PI-level decisions this sprint
inherits) → this.

**S8.1's question:** *what stops a fresh container from booting into a working,
non-public system?*

Four things, measured: nothing migrates the schema, the admin plane is open by
default, the main store is single-process SQLite, and the reports live in a
second database that no foreign key reaches.

---

## 0. The two decisions taken with the user for this sprint

The PI-level design fixed five decisions spanning all four sprints (§0 there).
These two are S8.1's own, taken 2026-08-01 before any code, and one of them
**tightens** the approved PI design rather than merely implementing it.

| # | Decision | Rejected | Why |
|---|---|---|---|
| 0.1 | **The admin credential is required in EVERY environment. There is no `env == "local"` escape.** | PI-8 §1's "…and the environment is not explicitly declared local" | `env` **defaults to `"local"`** ([`app/core/config.py:366`](../../../app/core/config.py#L366)). An env-gated escape therefore means a deploy is safe only if **two** variables are remembered — `DEE_ENV` *and* `DEE_API_AUTH_KEY` — and forgetting either leaves 27 admin endpoints public. That is the same fail-open shape, one indirection deeper. Local dev sets `DEE_API_AUTH_KEY=anything` in `.env` once; the suite sets a test key in `conftest`. This is what decision 0.5's "fail-closed is not trimmable" and §1's "no config knob restores the old behaviour" actually require. |
| 0.2 | **Railway Postgres is provisioned at the START of this sprint; the API service deploys at the END.** | deploy-ready artifacts only, PG verified solely in GitHub Actions | There is **no docker and no psql on the development machine** (verified). Without a hosted Postgres, the cutover could only ever be observed in CI, asynchronously, after a push — a bad way to debug a dialect problem. Provisioning the database first turns Postgres into something this sprint can run the full suite against interactively. The API service deploys once the plane in front of it fails closed, which is the same sprint. |

## 1. What this sprint is, in one paragraph

S8.1 makes the repository deployable **and** closes the defect that makes
deploying it dangerous. It adds `alembic upgrade head` to the boot path, makes
the admin plane refuse to boot without a credential, moves `reports` and
`outcomes` out of their private raw-`sqlite3` database and into the main
Alembic-managed one behind a real `ON DELETE CASCADE`, proves the schema and the
suite on Postgres, and puts the container on Railway. No new product surface, no
LLM, no new consent purpose, no new endpoint — the only route change is a
*deletion* (the two hand-written erasure orchestrations collapse into one call).

## 2. Task order — and why it is not negotiable

1. **Fail-closed admin auth + boot refusal.**
2. **Migrate-on-boot** (+ the Dockerfile fix that makes it possible at all).
3. **The fold** — `reports` + `outcomes` into the main DB.
4. **Postgres** — engine, test hook, CI job, migrations up/down/up.
5. **Railway** — the Postgres from §0.2 exists before task 4 needs it; the API
   service deploys after task 1 has made the plane safe to expose.

Task 1 is first because PI-8 §1.1 measured why: closing the gate touches
`conftest`, 7 test files and 9 smoke scripts. Every later task in this sprint
moves or rewrites files in that same set. Any other order re-touches all of them.

Task 3's **internal** order is fixed by PI-8 §5: the cascade regression test is
written *first* and must pass with **no route-layer orchestration at all**.
Written last, it would let the old convention quietly survive the migration and
prove nothing.

## 3. Fail-closed admin auth

### 3.1 The defect, restated with this sprint's measurements

[`app/api/routes.py:76-82`](../../../app/api/routes.py#L76-L82) treats an unset
`api_auth_key` as "auth disabled". `api_auth_key` defaults to `SecretStr("")`
([`config.py:361`](../../../app/core/config.py#L361)), so **fail-open is the
default posture**, and `DEE_API_AUTH_KEY` is a variable a deploy can silently
forget.

Measured blast radius at `b37788f` — **wider than PI-8 §1.1 recorded**:

- `tests/conftest.py` never sets the key, so all 1175 tests run unguarded.
- **7 test files** call admin routes with no key and pass *because of* the defect.
- **9 smoke scripts** (`smoke_s11`..`smoke_s31`) send no `X-API-Key` at all.
  The remaining 17 (`smoke_s32` onward) already set `DEE_API_AUTH_KEY` and send
  the header — so the fix splits the smokes into "already correct" and "never
  had a key", not "all 26 need work".

### 3.2 The fix

**Two independent layers, because they fail differently.**

**(a) The request gate.** `require_api_key` refuses whenever the configured key
is empty *or* does not match:

```python
expected = _services(request).settings.api_auth_key.get_secret_value()
if not expected or not hmac.compare_digest(x_api_key or "", expected):
    raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
```

An empty configured key is now the *most* refusing state, not the least.
`hmac.compare_digest` follows S7.1's own review finding on OTP comparison.

**(b) The boot guard.** New `app/core/boot.py`:

```python
def verify_launch_config(settings: Settings) -> None:
    """Refuse to start rather than serve an unguarded admin plane."""
```

Raises `LaunchConfigError` (a `RuntimeError` subclass) naming the missing
variable and how to set it. Called from `create_app`'s lifespan **always** —
including when a test injects a `Services` bundle, because a test that boots
without a credential is exactly the blind spot §3.1 describes.

Layer (a) alone would leave a deployment that answers 401 to everything and
looks merely broken. Layer (b) makes it loud at the only moment an operator is
watching. Layer (b) alone would be bypassable by anything that builds an app
without the lifespan.

**No knob, no `env` exemption, no bypass** (decision 0.1).

**A second launch check, added while planning:** `env == "prod"` **with a SQLite
`candidates_db_url` also refuses to boot.** This sprint is the one that makes
deployment possible, and it therefore creates the hazard: a Railway container's
disk is ephemeral, so a prod boot on SQLite loses every row on the next
redeploy — silently, and only discovered by the person whose data is gone. It is
also blocker 2 (single-process write locks) shipped to production by accident.
The check costs four lines and is the same fail-closed reflex as the first, so
it belongs here rather than in a follow-up. Note this is a check on `env`, not
an *exemption* keyed on it — decision 0.1 stands.

### 3.3 What changes in the suite

- `conftest.settings` sets `api_auth_key=SecretStr("test-admin-key")`, and a new
  `admin_headers` fixture (plus an importable `ADMIN_HEADERS` constant) is the
  one place the header is spelled.
- The 7 test files gain `headers=admin_headers` on admin calls.
- The 9 key-less smokes set `DEE_API_AUTH_KEY` in their subprocess env and send
  the header, matching the 17 that already do.

### 3.4 The tests that matter

PI-8 §1.1's warning is the design driver here: *a test that never sends a
credential cannot distinguish "authorized" from "unguarded"*. So the new tests
assert **refusals**:

1. An admin route with **no key configured and no header** → **401** (this is
   the test that would have failed for eight PIs).
2. No key configured, *any* header value → 401.
3. Key configured, absent header → 401; wrong header → 401; right header → 200.
4. `verify_launch_config` with an empty key **raises**; with a key, returns.
5. Booting the real app (empty key) raises rather than serving.
6. **Coverage guard:** every route registered on `router` carries the
   `require_api_key` dependency — walked from `app.routes`, not listed by hand,
   so a future endpoint cannot be added outside the gate. (`org_router`,
   `candidate_router` and `public_router` are deliberately excluded: they have
   their own always-enforced gates, or are `/` and `/healthz`.)

## 4. Migrate-on-boot

**Blocker 1 (v2 §9):** `alembic upgrade head` runs nowhere in the boot path, so
a fresh container starts against no schema.

New `app/core/migrate.py`:

```python
def upgrade_to_head(settings: Settings) -> None:
    """Run Alembic to head against settings.candidates_db_url."""
```

- Builds an Alembic `Config` programmatically and sets `sqlalchemy.url` from
  settings — the precedent every smoke script already uses.
- **Postgres: takes a `pg_advisory_lock` for the duration.** Concurrent uvicorn
  workers otherwise race the same migration on first boot, which is precisely
  what blocker 2's multi-worker deployment creates. SQLite serializes writes
  already and needs no lock.
- Called from the lifespan **before** `build_default_services`, since the stores
  open connections expecting tables.
- Knob `db_migrate_on_boot: bool = True`. It exists for the operator who runs
  migrations as a separate deploy step, **not** as a bypass — a `False` boot
  against an empty DB fails loudly at the first query, which is honest.
- Tests that inject `Services` do not migrate (they already `create_all` on
  in-memory SQLite): the lifespan migrates only when `services is None` **and**
  `settings.db_migrate_on_boot` — both conditions, so neither an injected bundle
  nor a disabled knob reaches Alembic.

**The Dockerfile cannot do this today** — [`Dockerfile:19-20`](../../../Dockerfile#L19-L20)
copies `app/` and `config.yaml` only. Without `alembic/` and `alembic.ini` in
the image, `upgrade_to_head` raises at boot in the container and nowhere else.
Both are added.

## 5. The fold — `reports` + `outcomes` into the main database

The decision, its five reasons and its cost are PI-8 §2.1 and are not relitigated
here. This section is the shape.

### 5.1 Package

New package **`app/reports/`**, peer of `app/portal/`, `app/verification/`,
`app/interview/`:

| Module | Contents |
|---|---|
| `schema.py` | `OutcomeLabel` (StrEnum), `OutcomeRecord` (Pydantic) — moved verbatim |
| `models.py` | `ReportRow`, `OutcomeRow` on the shared `Base` |
| `store.py` | the `ReportStore` Protocol + `SqlReportStore` + `build_report_store` |

`app/services/report_store.py` is **deleted**, including its 212 lines of raw
`sqlite3`, its `INSERT OR REPLACE`, its process-wide write lock and the
`ALTER TABLE ... ADD COLUMN` in a `try/except` at construction
([`report_store.py:76`](../../../app/services/report_store.py#L76)) — a
migration system reimplemented badly beside fifteen real ones.

The Pydantic `Report` stays where it is (`app/schemas/report.py`); it is imported
across the whole graph and moving it is unrelated churn.

Import sites updated (measured, 6 modules + tests): `app/api/routes.py`,
`app/features/context.py`, `app/features/materialize.py`,
`app/interview/service.py`, `app/portal/service.py`, `app/services/__init__.py`,
and 8 test modules.

### 5.2 Migration `0016_reports_outcomes`

| Table | Column | Note |
|---|---|---|
| `reports` | `id` | String PK — the existing report id |
| | `domain`, `depth_band` | String, NOT NULL |
| | `created_at` | DateTime, NOT NULL, indexed with `candidate_id` |
| | `candidate_id` | String, **nullable**, FK → `candidates.id` **ON DELETE CASCADE** |
| | `body` | JSON, NOT NULL — the serialized `Report` |
| `outcomes` | `id` | Integer PK autoincrement |
| | `report_id` | String, NOT NULL, FK → `reports.id` **ON DELETE CASCADE** |
| | `claim_id`, `notes` | nullable / defaulted |
| | `outcome` | String, NOT NULL |
| | `recorded_at` | DateTime, NOT NULL |

`candidate_id` is nullable **and** cascading: `POST /evaluate` produces reports
with no candidate attached and predates the candidate backbone. An attached
report dies with its subject; an unattached one was never personal data.

`body` is a `JSON` column, matching the main DB's existing use throughout, rather
than the old Text blob. Column types are spelled identically in the ORM and the
migration — the SQLite `VARCHAR` / nullability drift trap the metadata guard
caught during S7.1. The drift / index / FK-ondelete / nullability guards in
`tests/test_migrations.py` extend to both tables.

### 5.3 The cascade test, written first

```
create candidate → save a report against them → candidates.delete_candidate(id)
  ⇒ the report is gone, and outcomes with it
```

with **no route-layer orchestration and no report-store call**. This is the
whole point of folding (PI-8 §2.1: it converts a convention into a structural
guarantee), and it is written before the store exists so it cannot be satisfied
by accident.

`session.delete(cand)` issues a plain `DELETE FROM candidates`; the database
cascades. SQLite honours this because [`db.py:30-34`](../../../app/core/db.py#L30-L34)
sets `PRAGMA foreign_keys=ON` per connection — the same mechanism the ledger and
interview tables already rely on.

### 5.4 `delete_for_candidate` is removed, not kept

PI-8 §2.1 leaves it "on the Protocol for as long as something still needs it
explicitly". Measured: **nothing does.** Its only two callers are the two route
sites being deleted. It comes off the Protocol and out of the store.

[`routes.py:354-355`](../../../app/api/routes.py#L354-L355) (admin) and
[`routes.py:988-989`](../../../app/api/routes.py#L988-L989) (portal) each
collapse to a single `delete_candidate`.

**`reports_deleted` stays in both responses**, computed as `len(for_candidate(id))`
*before* the delete. It is asserted by `tests/test_candidates_api.py:193` and
`scripts/smoke_s13.py:105`, and in the portal case it is a transparency
disclosure to the data principal — "we erased N reports" — which is worth
keeping. The distinction that matters: this is a **read**, not an erasure
orchestration. A future entry point that forgets it loses a number in a
response; it can no longer orphan a person's data, because the deletion is the
database's job now.

### 5.5 `InMemoryReportStore` is deleted too

This is a consequence of folding that PI-8 §2.1 does not state, and it is the
one that decides whether the sprint actually proves anything.

`InMemoryReportStore` is a dict. It has no foreign keys and cannot cascade. If
`conftest.make_services` keeps using it, every erasure test in the suite passes
**without** the cascade — the fake would paper over precisely the guarantee this
sprint exists to create.

The fake existed because the real store needed a file. It no longer does: the
real `SqlReportStore` binds to the **same in-memory SQLite session factory** the
candidate store already uses in tests, so it is offline, free, and cascades for
real. `InMemoryReportStore` is deleted and its 8 test modules move to the real
store via the existing fixtures.

The `ReportStore` Protocol **stays** — 6 modules type against it, and S8.4's
read-models will too.

### 5.6 Data migration for existing rows

`scripts/migrate_reports_into_main_db.py` — one-shot, explicit, idempotent:

1. Open the old `data/reports.db` read-only. **Absent file ⇒ clean no-op**.
2. For each report, check its `candidate_id` exists in the main DB.
3. **Report and drop orphans** — reports whose candidate is already erased.
   These are the old convention's actual failures, and the script counts them
   out loud. They cannot be inserted anyway: the new FK would reject them, which
   is the point.
4. Insert the rest plus their outcomes inside one transaction.

**Not an Alembic step.** A migration must not read a filesystem path out of
`Settings`, must not depend on a second database engine being reachable, and
must stay runnable on a fresh deployment that never had a `reports.db`. Alembic
`0016` creates schema only.

`report_db_path` is removed from `Settings`. The 26 smokes that set
`DEE_REPORT_DB_PATH` are harmless without it (`extra="ignore"` on
`SettingsConfigDict`), and the line is removed as each smoke is touched.

## 6. Postgres

**Blocker 2 (v2 §9):** SQLite is single-process; concurrent uvicorn workers
contend on write locks.

- `psycopg[binary]>=3.1` added to `requirements.txt`.
- `make_engine` gains `pool_pre_ping=True` for non-SQLite URLs (Railway and
  every managed PG close idle connections; without it the first request after an
  idle period 500s). The SQLite branch is untouched.
- **SQLite stays the default and the local test backend.** CLAUDE.md's fully
  offline rule is not up for negotiation, and a required PG service would break
  `pytest -q` on a clean checkout.

### 6.1 Running the suite on Postgres

`conftest.make_candidate_store()` honours **`DEE_TEST_DB_URL`**. Unset (the
normal case) ⇒ today's `sqlite://` in-memory behaviour, unchanged.

Set ⇒ each call creates a throwaway `CREATE SCHEMA s_<uuid8>` and pins
`search_path` to it via a `connect` event, so `Base.metadata.create_all` lands
inside it and tests stay isolated the way a fresh in-memory SQLite DB isolates
them today. A session-scoped fixture drops every `s_%` schema at the end.

Any test that genuinely cannot run on Postgres gets an **explicit `skip` with a
stated reason**. No silent exclusions — an unexplained skip is how a dialect bug
survives.

### 6.2 CI

A new `postgres` job beside the existing 3.11/3.12 matrix, with a `postgres:16`
service container:

1. `alembic upgrade head` → `downgrade base` → `upgrade head`. This is what
   proves the three `batch_alter_table` migrations (`0004`, `0006`, `0014`) on a
   dialect where batch mode is a plain `ALTER` — and it proves the downgrades,
   which have never run anywhere (the S3.1 residual "0004 downgrade untested").
2. `DEE_TEST_DB_URL=postgresql+psycopg://... pytest -q`.

The existing offline matrix job is unchanged and remains the merge gate.

## 7. Railway

Provisioned at the start of the sprint (decision 0.2), used as the Postgres that
§6 is developed against, over its public proxy URL.

- Project + Postgres service first.
- API service from the repo's Dockerfile at the **end** of the sprint, after §3
  has closed the admin plane — the deploy is what makes the fail-open defect
  reachable from the internet, so the order matters.
- Environment: `DEE_API_AUTH_KEY` (generated, not reused from anywhere),
  `DEE_CANDIDATES_DB_URL` (Railway's reference variable), `DEE_ENV=prod`,
  `DEE_LOG_JSON=true`. No OpenRouter key — extraction falls back to heuristics,
  and this sprint deliberately proves the key-less path in production too.
- `railway.json` + a Deploy section in `README.md`.

**Not in this sprint:** custom domain, HTTPS-only enforcement for the cookie
posture (PI-8 §4.3 — S8.2 needs it, S8.1 has no cookies), and any public
announcement of the URL.

## 8. Config changes

```yaml
db_migrate_on_boot: true      # NEW — run alembic upgrade head at startup
```

Removed: `report_db_path`.
Unchanged but now **mandatory**: `DEE_API_AUTH_KEY` (secret, `.env`/environment
only — never YAML).

No other knob. In particular **no knob restores fail-open admin auth** (PI-8
§0.5, decision 0.1).

## 9. Testing and smoke

Beyond §3.4's refusal tests and §5.3's cascade test:

- **Store parity** — the existing `test_report_store.py` suite runs against
  `SqlReportStore` and must pass unchanged apart from construction. The Protocol
  surface is the contract; the backend changed underneath it.
- **Erasure through both entry points** — admin `DELETE /candidates/{id}` and
  portal `DELETE /portal/me` both leave no report behind, now via the cascade
  rather than via two hand-written call sites.
- **Unattached reports survive** — `POST /evaluate` produces a report with
  `candidate_id=None`; no candidate deletion touches it.
- **Migration guards** — drift, index, FK-ondelete and nullability extended to
  `reports` and `outcomes`.
- **The data-migration script** — a fixture old-style `reports.db` with one
  linked report, one orphan and one outcome: 2 imported, 1 orphan reported and
  dropped, and a second run is a no-op.

### 9.1 `scripts/smoke_s81.py` — key-less, uvicorn, exit 0

The sprint's proof, and unusually it starts from **nothing**: no pre-migrated
database, which every prior smoke has done for itself.

1. **empty scratch DB, no `alembic upgrade` first** → boot → `/healthz` 200:
   *migrate-on-boot works.*
2. admin route, **no header** → **401**.
3. admin route, wrong key → 401.
4. admin route, correct key → 200.
5. create candidate → `/evaluate` → report readable at `GET /report/{id}`.
6. `DELETE /candidates/{id}` → `GET /report/{id}` **404**: *the cascade, over
   HTTP, with no report-store orchestration left in the route.*
7. an unattached `/evaluate` report is still readable afterwards.
8. a **second uvicorn started with no `DEE_API_AUTH_KEY` exits non-zero** and
   never serves: *the boot refusal, observed as a process exit rather than
   asserted in a unit test.*

Run against SQLite locally, and — new for this sprint — repeated against the
Railway Postgres via `DEE_CANDIDATES_DB_URL`.

## 10. Non-goals for S8.1

- **Sessions, cookies, CORS, CSRF, `org_users`, `admin_users`, email, OTP
  login** — all S8.2. The admin plane stays a shared secret this sprint; it just
  stops being optional.
- **Rate limiting, metrics, retention sweep, DPDP correction/grievance** — S8.3.
- **Batch upload, cursor pagination, the fraud-screen read-model** — S8.4.
- **Any UI, HTML, template or JS toolchain** — PI-8 decision 0.1, standing.
- **Moving the Pydantic `Report`** out of `app/schemas/` — unrelated churn.
- **The flywheel delete-or-repurpose call** — v2 §3.2, still open, still not
  urgent.

## 11. Definition of done

1. `pytest -q` green on SQLite; the new refusal, cascade and parity tests present.
2. The suite green on Postgres via `DEE_TEST_DB_URL`, with every skip explained.
3. `upgrade head → downgrade base → upgrade head` clean on Postgres in CI.
4. A fresh empty database boots, migrates itself, and serves.
5. No admin credential ⇒ **the process refuses to start**, and the smoke proves
   it by exit code.
6. `app/services/report_store.py` and `InMemoryReportStore` are gone; no route
   orchestrates report erasure.
7. `scripts/smoke_s81.py` green on SQLite and on Railway Postgres, exit 0.
8. The API is deployed on Railway, booting against Railway Postgres with its
   admin plane closed.

## 12. Follow-ups this sprint deliberately leaves open

- **`add_turn`'s `sequence = count + 1` TOCTOU** (S7.3 review, deferred to
  "revisit under blocker 2"). Postgres removes SQLite's write serialization, so
  the guard is now only the current-question 409. Real but narrow; it belongs
  with S8.3's concurrency work, not with a schema move.
- **Multi-worker deployment** — the advisory lock makes concurrent boots safe,
  but nothing else in the repo has been examined for worker-count assumptions.
  S8.3 owns it, alongside metrics that would make a contention problem visible.
- **Connection-pool sizing** — defaults until there is one real usage pattern.
- **`InMemoryFlywheel` / the flywheel's fate** — untouched here.
