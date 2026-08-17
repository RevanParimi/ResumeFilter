# S8.7 — src layout: a standard repository, and no behaviour change

**Date:** 2026-08-15
**Status:** approved (design), building
**Sprint:** S8.7 (PI-8). Follows S8.6 (production shape, merged `6f19d32`).

## 1. Why

The motivation is **reviewability**, and it is measured, not aesthetic. S8.6's
diff was 4,354 lines of which 2,711 were markdown prose, so a reviewer with a
12,000-line ceiling spends most of its budget reading documentation. With the
importable package under `src/`, `/code-review ultra src/` targets the core
code and nothing else.

The secondary benefit is the one src layouts exist for: with the package no
longer sitting in the working directory, an accidental import of the source
tree instead of the installed package becomes impossible by construction, so
what the tests exercise is what ships.

## 2. The contract

**A pure move.**

- `app/` → `src/app/`. The package **keeps the name `app`**.
- 1,489 `from app.` / `import app` occurrences across 368 files are
  **untouched**. Measured, not estimated.
- 1852 tests green before and after; all 20 smokes green after.
- **Zero logic edits in the same commit as a move**, so `git log --follow` and
  a human reviewer can both tell a rename from a change.

### 2.1 The rename question, settled

The roadmap left one open decision: rename the package `app` → `veritas` at the
same time? **Decided 2026-08-15 by the user: no.** Reasons, in the order they
carried weight:

1. It buys nothing for this sprint's stated goal. `/code-review ultra src/`
   scopes identically whether the directory under `src/` is called `app` or
   `veritas`.
2. The "pay the disruption twice" argument does not survive inspection. The
   rename is a mechanical edit the suite verifies, and it is **cheaper after
   this move than before it**, because afterwards the package sits alone in
   `src/` with no root-level namespace to disambiguate.
3. It would take this sprint's diff from nine files to every Python file in the
   repo, in a sprint whose entire justification is making diffs reviewable.

The rename remains available as its own single-commit change at any time.

## 3. What moves and what does not

Only the importable package moves:

```
<repo>/
  src/app/          <- MOVED (the only thing that moves)
  tests/            stays
  scripts/          stays
  alembic/          stays
  frontend/         stays
  config.yaml       stays
  alembic.ini       stays
  Dockerfile        stays
```

This is deliberate and load-bearing, not convention-following. Both surviving
`parents[N]` expressions in the package resolve to **the repository root**, and
the root is what holds `alembic.ini` and `frontend/`. Moving anything else
under `src/` would break that anchor.

## 4. Import resolution — three consumers, three mechanisms

This is the part the roadmap's touchpoint list does not cover, and it is where
the sprint can silently fail. Today `import app` resolves because `app/` sits
in the working directory. After the move it does not, and **three different
consumers need three different answers**.

| Consumer | How `import app` resolves today | After |
|---|---|---|
| `pytest` (local + both CI jobs) | `pythonpath = ["."]` | `pythonpath = [".", "src"]` |
| ~20 `scripts/smoke_*.py` subprocesses | `cwd=ROOT` holds `app/` | the editable install |
| the container | `WORKDIR /srv/app` holds `app/` | `ENV PYTHONPATH=/srv/app/src` |

Notes on each:

- **pytest.** The `"."` entry stays and is load-bearing:
  `tests/test_report_data_migration.py` does `from scripts.migrate_reports_into_main_db
  import migrate`. Keeping resolution in `pythonpath` rather than requiring an
  install means CI's existing `pip install -r requirements.txt && pytest -q`
  keeps working with no new step, and a fresh clone runs the suite green.
- **The smokes.** These are `subprocess.Popen([sys.executable, "-m", "uvicorn",
  "app.main:app"], cwd=ROOT)` — separate processes, so pytest's `pythonpath`
  does not reach them. They depend on the venv at `.resume/`, which already
  holds an **editable** install (`_editable_impl_depth_eval_engine.pth`). That
  `.pth` is generated at install time and pins the current layout, so
  `pip install -e .` **must be re-run** after the `pyproject.toml` edit. This is
  the one manual step in the sprint.
- **The container.** `PYTHONPATH` rather than switching the image to
  `pip install .`, because changing the image's install strategy is a behaviour
  change and this sprint is a move. `uvicorn app.main:app` in the Dockerfile
  `CMD` and in `railway.json` stays byte-identical.

## 5. The touchpoints

Nine, not the six the roadmap listed. Two of the extras were found by reading
the tree rather than the roadmap.

### 5.1 Inside the package — depth changes because the file moved

| File | Now | After | In the container |
|---|---|---|---|
| `app/core/migrate.py:29` | `parents[2]` | `parents[3]` | `/srv/app/src/app/core/migrate.py` → `/srv/app` ✓ |
| `app/main.py:249` | `parents[1]` | `parents[2]` | `/srv/app/src/app/main.py` → `/srv/app` ✓ |

### 5.2 Build and runtime configuration

| File | Change |
|---|---|
| `pyproject.toml` | `[tool.hatch.build.targets.wheel] packages = ["app"]` → `["src/app"]`; `[tool.pytest.ini_options] pythonpath = ["."]` → `[".", "src"]` |
| `Dockerfile` | `COPY app ./app` → `COPY src/app ./src/app`; add `ENV PYTHONPATH=/srv/app/src` |

### 5.3 Tests that reference `app/` as a path

| File | Change |
|---|---|
| `tests/test_image_contents.py:38` | `FLOOR = {"app", ...}` → `{"src/app", ...}` |
| `tests/test_model_registration.py:37` | globs `ROOT / "app"`; and line 41 builds a dotted module name from `path.relative_to(ROOT)`, which would emit `src.app.rights.models` — the relative base must become `ROOT / "src"` |
| `tests/test_deploy_doc.py:64` | reads `ROOT / "app" / "core" / "boot.py"` |
| `tests/test_metrics.py:125` | `parent.parent / "app"` — **absent from the roadmap's list** |

### 5.4 Not touched, and why

- `railway.json` — `uvicorn app.main:app` still resolves, via `PYTHONPATH`.
- `alembic/env.py` — imports `app.*` by module name only.
- `alembic.ini` — `script_location = alembic`, relative to the root, unmoved.
- `.dockerignore` — nothing there names `app` or `src`. Confirmed against
  `test_dockerignore_does_not_cancel_a_copy`, which will now check `src/app`.
- `.github/workflows/ci.yml` — every reference is the module path
  `app.retention.sweep` or `app.core.*`, resolved inside the image by
  `PYTHONPATH`.

## 6. The image must mirror the repo, not flatten it

`COPY src/app ./app` would be the tempting one-line edit: the container keeps
its current shape and `uvicorn app.main:app` works with no `PYTHONPATH` at all.
**It is wrong, and wrong in the expensive direction.**

With the package at `/srv/app/app/core/migrate.py`, the new `parents[3]`
resolves to `/srv` — not `/srv/app`, where `alembic.ini` lives. Migrate-on-boot
would then fail at **runtime, after the container reports itself started**,
which is the same failure class as S8.6's missing `frontend/`.

So the container layout mirrors the repository exactly:
`/srv/app/src/app/...` with `alembic.ini`, `config.yaml`, `alembic/` and
`frontend/` at `/srv/app/`. One depth arithmetic, valid in both places.

## 7. The guard, written red first

`tests/test_src_layout.py`:

```python
assert Path(app.__file__).resolve().parents[1] == ROOT / "src"
```

It fails on today's layout and passes after the move, which makes this
restructure genuine TDD rather than a move with tests run afterwards.

It is also the only thing that catches the three ways this sprint fails
silently:

1. **A stale editable install** — `.resume/` still resolving `app` to the old
   location, so the suite passes while testing code at a path that no longer
   exists in the tree.
2. **A missing `PYTHONPATH`** in a context nobody thought to check.
3. **A leftover `app/` at the repository root** — the worst outcome of a
   half-completed `git mv`, because imports resolve to it quietly and
   everything looks green.

This follows the repo's established shape: derive the assertion from the live
object, do not hand-maintain a list. The repo has now been bitten five times by
two hand-maintained lists that must agree (conftest vs `alembic/env.py`, the
Dockerfile vs `.dockerignore`, the `/ui` denylist twice, `test_ratelimit_wiring`'s
tuple).

## 8. Commit discipline

Two commits.

1. **`refactor(s87): app/ -> src/app/, pure move`** — nothing but `git mv`, at
   100% similarity. **Red by construction**, and its message says so out loud:
   the tree does not import until commit 2. This is what makes `git log
   --follow` work and what lets a reviewer skip the rename in one glance.
2. **`fix(s87): the nine references the move invalidated`** — the table in §5
   plus the guard from §7. Green.

Merging happens only on green, so the repo's "`pytest -q` must be green before
merge" convention is honoured; it constrains merges, not intermediate commits.

## 9. Verification

| Layer | Command | Expectation |
|---|---|---|
| Suite | `pytest -q` | baseline + 1 (the new guard) |
| Smokes | all 20 `scripts/smoke_*.py` | green — this is what proves the editable install and the subprocess `cwd` story |
| Image lists | `tests/test_image_contents.py` | `src/app` in the floor, no `.dockerignore` collision |
| UI mount | `tests/test_ui_mount.py` | the mount root still resolves to `<repo>/frontend` |

**Not proven here, and said plainly:** the image itself. This machine has no
Docker; the `image` CI job is push-only and nothing has been pushed since
S8.4a. `DEPLOY.md` already states the image is unproven until a push, and this
sprint does not change that.

## 10. Out of scope

- The package rename (§2.1).
- Any behaviour change, anywhere.
- The owed `/code-review ultra` of `8ae08cb..6f19d32`. That range is **fixed**,
  so its diff is frozen and this sprint landing afterwards cannot disturb it —
  the roadmap's "do S8.7 after the review" caution only applies to a review
  invoked with no base, which would diff against `origin/main` (~80 commits
  behind) and blow the reviewer's ceiling regardless.
- Deployment. Nothing here creates a cloud resource.
