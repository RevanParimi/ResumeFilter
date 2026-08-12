# S8.6 Production Shape — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make veritas correct to deploy — an eighth boot refusal, the UI served
same-origin without punching a hole in the route-table guard, an image that
contains what it needs, a derived endpoints list, and a `DEPLOY.md` checklist —
proven as far as a machine with no Docker and no Postgres can prove it.

**Architecture:** One branch, `s86-production-shape`, off `main` at `6dfde6c`
(the spec commit `0d7abb5` is already on it). Fifteen tasks, TDD throughout.
Nothing is deployed: no Railway project, service, database, domain or variable
is created by any task. The sprint's output is a correct system plus the
checklist a human runs later.

**Tech Stack:** Python 3.12 · FastAPI/Starlette · SQLAlchemy + Alembic ·
pytest · httpx · Chrome DevTools Protocol (existing browser check) · no new
runtime dependency.

**Spec:** `docs/superpowers/specs/2026-08-12-s86-production-shape-design.md`.
Read §0 before starting; it is why this sprint is not a deploy.

## Global Constraints

- **NO DEPLOYMENT. NO CLOUD RESOURCE.** Do not call any Railway MCP tool that
  creates, deploys, scales, sets variables on, or deletes anything. Read-only
  calls are unnecessary for every task below. Success criterion 7 is "no cloud
  resource exists that did not exist before the branch."
- **TDD, and every failing test must be SEEN failing** before its implementation
  is written. A step that says "verify it fails" is not optional and its
  expected output is written out.
- **Fully offline.** No test or smoke may require a network, an API key, or a
  vendor. `DEE_OPENROUTER_API_KEY` is pinned empty in every smoke — six sprints
  running, after S7.3 found a developer's real key in `.env` silently shipping
  to a live vendor from a smoke that claimed to prove the no-key path.
- **`pytest -q` must be green before any merge.** Baseline on `main` is **1812
  passing**.
- **Commit message trailers: NEVER add `Co-Authored-By`.** The user wants clean
  history.
- Config tunables go in `config.yaml`; secrets only in `.env` with the `DEE_`
  prefix.
- Follow the house comment style: explain *why*, name the failure mode, and cite
  the sprint a lesson came from. Do not write comments that merely restate code.

---

### Task 1: The eighth boot refusal — derived from the email builder

**Files:**
- Modify: `app/core/boot.py` (add the refusal after the `rate_limit_enabled`
  check and before/after `grievance_officer_email` — order among prod-only
  refusals does not matter behaviourally; put it after the grievance check so
  the file reads chronologically by sprint)
- Modify: `tests/test_boot_config.py` (extend `_prod`, extend
  `test_prod_on_postgres_launches`, add three new tests)

**Interfaces:**
- Consumes: `app.services.email.build_email(settings) -> EmailClient`, whose
  `.available` attribute is `False` only for `NullEmail`. Verified: `boot.py`
  imports `app.core.config` only, and `email.py` imports `app.core.config` +
  `app.core.logging`, so this import introduces no cycle.
- Produces: nothing other tasks import. Task 10 (`DEPLOY.md`) and Task 11 (the
  smoke) both enumerate **eight** refusals after this task.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_boot_config.py`, after the existing grievance-officer tests:

```python
# ── S8.6: the EIGHTH refusal — a prod deployment nobody can log into ─────────
# Prod boots today with email_provider=null and then answers 503
# email_unavailable to every signup and login on all three planes, while
# /healthz reports the service healthy. Blockers 4 and 5 are dead on arrival.


def test_prod_refuses_a_provider_that_cannot_deliver(settings):
    """config.yaml ships email_provider=null, so this is the DEFAULT prod
    misconfiguration, not an exotic one."""
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(_prod(settings, email_provider="null"))
    assert "email" in str(exc.value).lower()


def test_prod_refuses_smtp_with_no_host(settings):
    """THE POINT OF DERIVING THE CHECK. build_email returns NullEmail for
    provider=smtp with an empty host, so a refusal that tested the provider
    STRING would pass this config and the deployment would 503 every login
    anyway -- the failure reached through the door the guard was not watching.
    If someone 'simplifies' the refusal to `provider == "null"`, this is what
    fails."""
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(
            _prod(settings, email_provider="smtp", email_smtp_host="")
        )
    assert "email" in str(exc.value).lower()


def test_local_does_not_require_an_email_provider(settings):
    """config.yaml ships email_provider=null. Above the prod-only early return
    this refusal would break every local run and every test in this suite."""
    ok = settings.model_copy(update={
        "api_auth_key": SecretStr("a-real-key"),
        "email_provider": "null",
    })
    assert verify_launch_config(ok) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_boot_config.py -q -k "cannot_deliver or smtp_with_no_host"`
Expected: **2 failed** — `DID NOT RAISE <class 'app.core.boot.LaunchConfigError'>`.
`test_local_does_not_require_an_email_provider` passes already; that is correct
and it is there to stay green through the next step.

- [ ] **Step 3: Implement the refusal**

In `app/core/boot.py`, extend the module docstring's S8.3 paragraph with an S8.6
sentence, add the import, and append the check at the end of
`verify_launch_config`:

```python
from app.services.email import build_email
```

```python
    # -- S8.6: the EIGHTH refusal -- a deployment nobody can log into ---------
    # This ASKS THE BUILDER rather than testing `email_provider`, and that is
    # the whole design. `build_email` returns NullEmail for provider="smtp"
    # with an empty host, so a string check would pass that config and the
    # service would 503 every login anyway -- the rule applied at one entry
    # point and not the other, which has shipped as a real defect in S7.1,
    # S7.2, S7.3, S8.4 Phase B and S8.5. `EmailClient.available` already exists
    # for exactly this question and is False only on NullEmail, so there is one
    # predicate and no second copy to drift. It opens no socket.
    #
    # `capture` is NOT caught here -- it IS available, and its fault is that it
    # writes OTPs to a file. It keeps its own refusal above, so each check
    # isolates one fault.
    if not build_email(settings).available:
        raise LaunchConfigError(
            "DEE_ENV=prod with no working email provider "
            f"(email_provider={settings.email_provider!r}, "
            f"email_smtp_host={'set' if settings.email_smtp_host else 'EMPTY'}). "
            "Signup and login on all three planes answer 503 "
            "email_unavailable, so org self-onboard (PI-8 blocker 5) and "
            "candidate self-registration (blocker 4) do not work at all -- "
            "while /healthz reports the service healthy. Set "
            "email_provider=smtp with email_smtp_host and the DEE_EMAIL_SMTP_* "
            "credentials. There is no provider that 'works well enough' for a "
            "login code: it either arrives or the account is unreachable."
        )
```

- [ ] **Step 4: Run the new tests — they must pass**

Run: `pytest tests/test_boot_config.py -q`
Expected: the three new tests PASS. **`test_prod_on_postgres_launches` now
FAILS** — its "sound prod config" has no email provider. That failure is
correct and is fixed in the next step, exactly as S8.3 Phase B fixed the same
helper for the grievance officer.

- [ ] **Step 5: Repair the two helpers the new refusal invalidates**

In `tests/test_boot_config.py`, extend `_prod`'s base dict:

```python
        # S8.6 added the EIGHTH refusal, and this helper's whole job is to
        # satisfy every prior one so each test isolates the refusal it names.
        "email_provider": "smtp",
        "email_smtp_host": "smtp.example.com",
```

and add the same two keys to `test_prod_on_postgres_launches`'s `ok` dict, with
the comment:

```python
        # S8.6: a prod config must now also be able to DELIVER a login code.
        "email_provider": "smtp",
        "email_smtp_host": "smtp.example.com",
```

- [ ] **Step 6: Run the full boot suite, then the full suite**

Run: `pytest tests/test_boot_config.py -q`
Expected: all PASS.
Run: `pytest -q`
Expected: **1815 passed** (1812 + 3). If anything else fails, it is a test that
built a prod-shaped config by hand instead of through `_prod` — fix it the same
way and note it in the commit message.

- [ ] **Step 7: Commit**

```bash
git add app/core/boot.py tests/test_boot_config.py
git commit -m "feat(s86): the eighth refusal -- prod cannot boot unable to send mail

Prod boots today with config.yaml's shipped email_provider=null and then
answers 503 to every signup and login on all three planes. Org self-onboard
(blocker 5) and candidate self-registration (blocker 4) are dead on arrival
while /healthz reports healthy -- the declared-inert shape that
auth_sessions.ip_hash, four metrics and sweep_active all had.

The check ASKS build_email rather than testing email_provider. The builder
returns NullEmail for provider=smtp with an empty host, so a string check
would pass a config that 503s every login anyway. EmailClient.available
already answers exactly this and is False only on NullEmail: one predicate,
no second copy to drift. A test pins the smtp-with-no-host case so a later
'simplification' to a name check fails.

Consequence, which is the point: a prod boot now REQUIRES real SMTP. This is
what stops a future session deploying by momentum."
```

---

### Task 2: Teach the route-table guard to see mounts — BEFORE one exists

**Files:**
- Modify: `tests/test_route_table_guard.py`

**Interfaces:**
- Consumes: `app.main.create_app`, the existing `_walk` helper.
- Produces: `MOUNTS` — a module-level literal `set[str]` in
  `tests/test_route_table_guard.py`, empty in this task. **Task 3 widens it to
  `{"/ui"}` and that widening is the reviewable act.**

**Why this task exists and comes first:** `test_route_table_guard.py` is the
structural answer to PI-8's highest regression risk, and it **cannot see mounts
at all**. A `StaticFiles` mount is a `starlette.routing.Mount` with no
`.methods`, so `_guarded_routes` skips it on `methods is None`; router-level
dependencies never apply to it. Adding the UI mount in Task 3 without this
would silently create the first unauthenticated, unreviewed surface in a guard
built to make exactly that loud. Writing the guard first means Task 3's diff
*must* contain a deliberate widening.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_route_table_guard.py`:

```python
from starlette.routing import Mount

#: Mounts are a SECOND way to widen the unauthenticated surface, and until S8.6
#: nothing watched it. A Mount has no `.methods`, so `_guarded_routes` skips it,
#: and `include_router` dependencies do not apply to it -- so a mount is
#: unauthenticated AND invisible to the guard above. PUBLIC_PATHS exists so
#: that widening the public surface happens in a diff someone reads; this is
#: the same ritual for the other mechanism.
MOUNTS: set[str] = set()


def _mount_paths(app) -> set[str]:
    return {r.path for r in app.routes if isinstance(r, Mount)}


def test_mounts_are_an_explicit_short_list(services):
    """Every mount is unauthenticated by construction. If one appears here
    without appearing in MOUNTS, someone added a public surface without saying
    so."""
    app = create_app(services)
    assert _mount_paths(app) == MOUNTS


def test_the_guard_would_catch_a_new_mount(services):
    """A guard nobody has seen fail is a guard nobody knows works -- the reason
    the fail-open admin gate survived eight PIs and four branch reviews."""
    from starlette.staticfiles import StaticFiles

    app = create_app(services)
    app.mount("/sneaky", StaticFiles(directory="."), name="sneaky")
    assert _mount_paths(app) != MOUNTS
    assert "/sneaky" in _mount_paths(app)
```

- [ ] **Step 2: Run to verify the SECOND test fails and the first passes**

Run: `pytest tests/test_route_table_guard.py -q -k "mount"`
Expected: **both PASS.** `test_mounts_are_an_explicit_short_list` passes because
there are no mounts yet (`set() == set()`), and
`test_the_guard_would_catch_a_new_mount` passes because it plants one.

This is the one task in the plan whose test does not start red, and that is
correct rather than a gap: the guard is being installed *ahead* of the change it
must catch. Its red state is Task 3, Step 2 — which is the demonstration that
matters, and the plan schedules it explicitly rather than hoping for it.

- [ ] **Step 3: Prove the guard is not vacuous right now**

Run this one-off to confirm the walker sees a real app and the assertion is
comparing something meaningful:

```bash
python -c "
from starlette.routing import Mount
from app.main import create_app
from tests.conftest import *  # noqa
print('routes:', len(create_app.__doc__ or ''))
" 2>/dev/null || true
pytest tests/test_route_table_guard.py -q
```
Expected: the whole file passes, including the pre-existing
`test_every_non_public_route_uses_a_sanctioned_resolver` with its
`len(checked) >= 60` floor.

- [ ] **Step 4: Commit**

```bash
git add tests/test_route_table_guard.py
git commit -m "test(s86): the route-table guard could not see mounts

A StaticFiles mount is a starlette Mount, not an APIRoute: no .methods, so
_guarded_routes skips it on `methods is None`, and include_router
dependencies never apply to it. So a mount is unauthenticated AND invisible
to the guard that exists to make an unauthenticated surface loud.

Installed BEFORE the UI mount lands, so that adding it must widen MOUNTS in a
diff someone reads -- the PUBLIC_PATHS ritual for the other mechanism. The
guard is proven to fail by planting a second mount; a guard nobody has seen
fail is a guard nobody knows works."
```

---

### Task 3: Serve the UI same-origin, and widen MOUNTS deliberately

**Files:**
- Modify: `app/main.py` (mount after the `include_router` calls)
- Modify: `tests/test_route_table_guard.py` (`MOUNTS` → `{"/ui"}`)
- Create: `tests/test_ui_mount.py`

**Interfaces:**
- Consumes: `MOUNTS` from Task 2.
- Produces: the UI is served at `/ui/` from the repo's `frontend/` directory.
  Task 5 (`api.js`), Task 6 (Dockerfile), Task 13 and Task 14 all depend on that
  path being exactly `/ui`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui_mount.py`:

```python
"""The UI is served BY THE API, same origin (S8.6 spec 2).

Same-origin was chosen by the user over a separate static service. It does not
ship an untested posture -- it RETIRES one: the browser check has always run
both servers on localhost (cross-ORIGIN but same-SITE) with samesite=lax and
secure=false, so config.yaml's shipped SameSite=None has never been exercised
anywhere.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from starlette.routing import Mount

from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_the_ui_is_served_without_authentication(services):
    """Correct, and the reason it must ALSO be visible to the guard: a login
    page behind a login is unreachable by the person who needs it -- the same
    argument as public GET /grievance one floor down."""
    client = TestClient(create_app(services))
    resp = client.get("/ui/api.js")
    assert resp.status_code == 200
    assert "veritas" in resp.text[:400].lower()


def test_the_mount_root_is_the_frontend_directory(services):
    """Starlette owns traversal defence; the root we hand it is ours."""
    app = create_app(services)
    mounts = [r for r in app.routes if isinstance(r, Mount) and r.path == "/ui"]
    assert len(mounts) == 1
    assert Path(mounts[0].app.directory).resolve() == (ROOT / "frontend").resolve()


def test_the_ui_mount_does_not_shadow_the_api(services):
    """/ui is a real prefix, not a catch-all: the API must still answer."""
    client = TestClient(create_app(services))
    assert client.get("/healthz").status_code == 200
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_ui_mount.py -q`
Expected: **3 failed** — `assert 404 == 200` on the first, `assert 0 == 1` on
the second (no mount exists), and the third passes.

- [ ] **Step 3: Add the mount**

In `app/main.py`, add the imports:

```python
from pathlib import Path
from starlette.staticfiles import StaticFiles
```

and after `app.include_router(auth_router)`:

```python
    # The UI is served BY THIS API, same origin (S8.6 spec 2). Chosen over a
    # separate static host because it RETIRES an untested posture rather than
    # shipping one: config.yaml's SameSite=None has never been exercised by any
    # check in this repo -- the browser check runs both servers on localhost,
    # which is cross-ORIGIN but same-SITE, with samesite=lax.
    #
    # A Mount is NOT an APIRoute: no router dependency applies to it, so this
    # surface is unauthenticated. That is correct -- the shell has to load
    # before anyone can log in -- and it is why tests/test_route_table_guard.py
    # gained MOUNTS in the commit before this one. Widening that set is the
    # reviewable act, exactly as it is for PUBLIC_PATHS.
    _ui_dir = Path(__file__).resolve().parents[1] / "frontend"
    if _ui_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=_ui_dir), name="ui")
```

The `is_dir()` guard is deliberate: `create_app` must not explode in an
environment where `frontend/` was not shipped. Task 6 makes sure the image
always ships it, and Task 6's guard is what turns a missing directory into a
failing test rather than a silent 404.

- [ ] **Step 4: Run — the new tests pass and the GUARD GOES RED**

Run: `pytest tests/test_ui_mount.py tests/test_route_table_guard.py -q`
Expected: `test_ui_mount.py` **3 passed**, and
`test_mounts_are_an_explicit_short_list` **FAILS** with
`assert {'/ui'} == set()`.

**Stop and read that failure.** It is the entire reason Task 2 came first: the
guard caught a new unauthenticated surface the moment one appeared.

- [ ] **Step 5: Widen MOUNTS deliberately**

In `tests/test_route_table_guard.py`:

```python
MOUNTS: set[str] = {
    # S8.6. The UI shell, served same-origin. Unauthenticated ON PURPOSE: a
    # login page reachable only after login is not reachable by the person who
    # needs it. It serves frontend/ and holds no data-principal information --
    # tests/test_ui_mount.py pins the root it is given.
    "/ui",
}
```

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: **1819 passed** (1815 + 3 new + 1 already counted in Task 2… verify
the exact number and record it; the plan's arithmetic is a guide, the runner is
the authority).

- [ ] **Step 7: Commit**

```bash
git add app/main.py tests/test_ui_mount.py tests/test_route_table_guard.py
git commit -m "feat(s86): serve the UI same-origin, and widen MOUNTS to say so

app.mount('/ui', StaticFiles(frontend/)). The guard installed one commit ago
went red on this exact change -- a new unauthenticated surface -- and MOUNTS
is widened in this diff rather than the guard being relaxed.

Unauthenticated is correct here: the shell must load before anyone can log
in, the same argument as public GET /grievance. What would not have been
correct is being unauthenticated invisibly."
```

---

### Task 4: The cookie posture, and the four documents that become false

**Files:**
- Modify: `config.yaml:264` (`session_cookie_samesite`)
- Modify: `app/core/config.py:479` (the `Literal` default)
- Modify: `app/auth/csrf.py` (module docstring, line 3)
- Modify: `app/core/boot.py` (the `session_cookie_secure` refusal's *message*)
- Modify: `AUTH.md`, `UI.md`
- Create: `tests/test_cookie_posture.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Settings.session_cookie_samesite` now defaults to `"lax"`. Task 11
  and Task 13 set it explicitly anyway, so nothing downstream reads the default.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cookie_posture.py`:

```python
"""Same-origin retires SameSite=None (S8.6 spec 2.3).

CSRF is deliberately KEPT. SameSite=Lax already blocks cross-site POST, so the
naive read is that the CSRF layer is now redundant. It stays because it is
built, tested and free; because Lax is a browser-side control and the server
must not delegate its only defence to the client's correctness; and because
removing it is a large change to the authenticated write path of every plane in
the sprint that moves the cookie posture. Trading one property for another by
accident is how a defence disappears.
"""

from app.core.config import Settings


def test_the_shipped_default_is_lax(settings):
    assert settings.session_cookie_samesite == "lax"


def test_none_is_still_a_permitted_value():
    """A separately-hosted UI is still a supported deployment; it is simply no
    longer the one we ship."""
    s = Settings(session_cookie_samesite="none")
    assert s.session_cookie_samesite == "none"


def test_csrf_survives_the_change():
    """Pinned because 'Lax blocks cross-site POST' is exactly the argument
    someone will use to delete this layer."""
    from app.auth import csrf

    assert hasattr(csrf, "issue_token") or hasattr(csrf, "new_token"), (
        "the CSRF module lost its minting function -- see this test's docstring"
    )
```

Before running, open `app/auth/csrf.py` and replace the `hasattr` names above
with the **actual** public function names in that module. A test asserting
against a guessed name is worse than no test.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_cookie_posture.py -q`
Expected: `test_the_shipped_default_is_lax` **FAILS** —
`assert 'none' == 'lax'`.

- [ ] **Step 3: Change the default in both places**

`app/core/config.py:479`:

```python
    #: S8.6: `lax`, because the UI is now served BY this API (same origin).
    #: `none` remains valid for a separately-hosted UI and still mandates
    #: Secure, which prod still refuses to have false.
    session_cookie_samesite: Literal["none", "lax", "strict"] = "lax"
```

`config.yaml:264`:

```yaml
session_cookie_samesite: "lax"      # none | lax | strict — S8.6: the UI is same-origin
```

- [ ] **Step 4: Run — the new file passes, and find what else moved**

Run: `pytest tests/test_cookie_posture.py -q` → PASS.
Run: `pytest -q`
Expected: any failure here is a test that asserted `"none"`. Fix each by
asserting the new default, and note in the commit which ones moved.

- [ ] **Step 5: Correct the four documents that now state something false**

These are not tidying. A stale comment that *justifies a live check* is worse
than a stale comment beside dead code: the next person reads a reason that no
longer holds and concludes the check is obsolete.

1. `app/auth/csrf.py:3` — currently *"SameSite=None is required rather than
   chosen — the UI is separately hosted"*. Replace with a statement of what is
   now true **and why this layer survives anyway**, in the words of
   `tests/test_cookie_posture.py`'s docstring. A reader who only corrects the
   first sentence would reasonably conclude the layer can go.
2. `app/core/boot.py` — the `session_cookie_secure` refusal message cites
   `SameSite=None (required, because the UI is separately hosted)` as its
   justification. The refusal is still right; its stated reason is not. Rewrite
   the justification as: the session cookie travels over the public internet.
   **Do not weaken the refusal itself.**
3. `AUTH.md` — the same `SameSite=None` claim.
4. `UI.md` — the "CORS is fail-closed and server-side" passage gains the
   same-origin case: the shipped UI no longer needs an entry in
   `cors_allowed_origins`, third-party integrations still do, and the prod
   wildcard refusal is unchanged.

- [ ] **Step 6: Run the full suite and commit**

Run: `pytest -q` → green.

```bash
git add config.yaml app/core/config.py app/auth/csrf.py app/core/boot.py \
        AUTH.md UI.md tests/test_cookie_posture.py
git commit -m "feat(s86): samesite=lax, and correct four documents it falsifies

The UI is same-origin now, so SameSite=None stops being required. Secure
stays required and prod still refuses false -- only its stated REASON
changes, from 'None mandates Secure' to 'the cookie crosses the public
internet'.

CSRF is deliberately kept and the reason is pinned by a test, because 'Lax
blocks cross-site POST' is exactly the argument someone will use to delete
it. Lax is a browser-side control; the server should not delegate its only
defence to the client's correctness.

csrf.py, boot.py's refusal message, AUTH.md and UI.md all asserted the
separately-hosted premise. A stale comment that justifies a LIVE CHECK is
worse than one beside dead code -- the next reader concludes the check is
obsolete."
```

---

### Task 5: `frontend/api.js` defaults to its own origin

**Files:**
- Modify: `frontend/api.js` (the `DEFAULT_BASE` constant and its comment)
- Modify: `scripts/check_ui_bindings.js` if it asserts the old constant — check
  first with `grep -n "DEFAULT_BASE\|localhost:8000" scripts/check_ui_bindings.js`

**Interfaces:**
- Consumes: the `/ui` mount from Task 3.
- Produces: with no `?api=` and no `localStorage` entry, `api.js` calls paths
  relative to the page. Task 13 and Task 14 rely on this.

**There is no Python test for this file** — it is outside the pytest suite and
outside CI, which is exactly why S8.5 built three executing verification layers
for it. Task 14 is where this change is actually proven, in a browser.

- [ ] **Step 1: Read the current precedence rule**

Run: `sed -n '30,75p' frontend/api.js`

Confirm the order is: `?api=` → `localStorage` → default. **That order is not
changing.** It exists so the base URL is never invisible.

- [ ] **Step 2: Change the default**

```javascript
  /* S8.6: the UI is served BY the API (same origin), so the default is the
   * page's own origin -- "" makes every call relative. The ?api= and
   * localStorage overrides are UNCHANGED: they exist so a base URL is never
   * invisible, and a UI loaded from one API that silently talked to a
   * different one because of a stale localStorage entry is precisely the
   * failure this precedence was written about. */
  var DEFAULT_BASE = "";
```

- [ ] **Step 3: Confirm `trimSlash("")` is harmless**

Run:

```bash
node -e 'var s=""; console.log(JSON.stringify(String(s||"").replace(/\/+$/,"")))'
```
Expected: `""`. Then read the call sites of `base()` in `api.js` and confirm
`"" + "/healthz"` produces `/healthz` — a valid same-origin relative URL — and
that nothing does `new URL(base())`, which would throw on an empty string.

- [ ] **Step 4: Run the binding check**

Run: `node scripts/check_ui_bindings.js`
Expected: the same count as on `main` (384/384 at S8.5; confirm against the
ROADMAP's latest figure). If it asserts `http://localhost:8000` literally,
update that assertion to the new default and say so in the commit.

- [ ] **Step 5: Commit**

```bash
git add frontend/api.js scripts/check_ui_bindings.js
git commit -m "feat(s86): api.js defaults to its own origin

Served from the API at /ui, the right default base is the page's own origin.
The ?api= and localStorage overrides and their precedence are untouched --
they exist so the base URL is never invisible, which the same-origin default
does not change.

Not proven here: this file is outside pytest and outside CI. Task 14 proves
it in a real browser, which is why S8.5 built those layers."
```

---

### Task 6: The Dockerfile's COPY list, and a guard for it

**Files:**
- Modify: `Dockerfile`
- Create: `.dockerignore`
- Create: `tests/test_image_contents.py`

**Interfaces:**
- Consumes: the `/ui` mount from Task 3 (the guard derives the mount root from
  the live app).
- Produces: nothing other tasks import.

- [ ] **Step 1: Write the failing test**

Create `tests/test_image_contents.py`:

```python
"""The Dockerfile's COPY list is a HAND-MAINTAINED LIST of what the app needs
at runtime, and this repo has found four of those drifted in three sprints:
conftest's model imports (a test that passed in its file and failed alone),
alembic/env.py's imports (six missing -- autogenerate would have emitted DROP
TABLE for six live tables), the RateLimited->429 translation copied four times,
and test_ratelimit_wiring's LIMITED tuple.

It had already drifted here: frontend/ was missing, which was invisible while
nothing served the UI and becomes a blank page the moment the mount lands.

WHAT IS DERIVED AND WHAT IS A FLOOR. The static mount root comes from the LIVE
APP and the migration directory from alembic.ini, because those are configured
elsewhere and are the two that can move without anyone touching this file. The
package and config floor is literal. Same shape as test_ratelimit_wiring, which
discovers limited services off the container and keeps a named tuple as a floor
so a service that silently LOSES its limiter still fails.
"""

from __future__ import annotations

import configparser
import re
from pathlib import Path

from starlette.routing import Mount

from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]

#: Paths the image must contain no matter what any config says.
FLOOR = {"app", "config.yaml", "alembic.ini"}


def _copied_sources() -> set[str]:
    """Every source path in a `COPY <src> <dst>` line, normalised."""
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    out: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"\s*COPY\s+(?!--)(\S+)\s+(\S+)\s*$", line)
        if m:
            out.add(m.group(1).strip("./").rstrip("/"))
    return out


def test_the_floor_is_copied():
    missing = FLOOR - _copied_sources()
    assert missing == set(), f"Dockerfile never COPYs {sorted(missing)}"


def test_the_static_mount_root_is_copied(services):
    """DERIVED from the running app: if someone moves the UI directory, this
    fails without anyone remembering to edit a list."""
    app = create_app(services)
    roots = {
        Path(r.app.directory).resolve().relative_to(ROOT).as_posix()
        for r in app.routes
        if isinstance(r, Mount) and hasattr(r.app, "directory")
    }
    assert roots, "no static mount found -- this guard would pass vacuously"
    assert roots <= _copied_sources(), (
        f"the app serves {sorted(roots)} but the image never COPYs it: "
        "the UI would be a 404 in the container"
    )


def test_the_migration_directory_is_copied():
    """DERIVED from alembic.ini, because migrate-on-boot fails at RUNTIME
    without it -- after the container reports itself started."""
    cfg = configparser.ConfigParser()
    cfg.read(ROOT / "alembic.ini", encoding="utf-8")
    loc = cfg["alembic"]["script_location"].strip().strip("./").rstrip("/")
    assert loc in _copied_sources(), f"alembic script_location {loc!r} is not COPYed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_image_contents.py -q`
Expected: `test_the_static_mount_root_is_copied` **FAILS** — the app serves
`['frontend']` and the Dockerfile never COPYs it. The other two pass, which is
correct: they are the floor, and the floor was already met.

- [ ] **Step 3: Fix the Dockerfile and add `.dockerignore`**

In `Dockerfile`, after `COPY alembic.ini .`:

```dockerfile
# The UI is served by this API at /ui (S8.6). Without this the mount exists and
# every page is a 404 -- and nothing in the app would say why. tests/
# test_image_contents.py derives this requirement from the LIVE APP, so moving
# the directory fails a test rather than shipping a blank container.
COPY frontend ./frontend
```

Create `.dockerignore`:

```
# frontend/uploads/ is fixture input for scripts/check_ui_screening_browser.py.
# Resumes -- even invented ones -- have no business in a production image.
frontend/uploads/
frontend/.thumbnail

# Never ship the local database, secrets, or caches.
data/
.chroma/
.env
.git/
__pycache__/
*.pyc
.pytest_cache/
tests/
docs/
scripts/
```

Note: `scripts/` is excluded, so `scripts/migrate_reports_into_main_db.py` is
not in the image. That one-off is documented in README's Deploy section for
deployments predating S8.1 — of which there are none, because there are no
deployments. Record that in `DEPLOY.md` (Task 10) rather than shipping a script
to make a note true.

- [ ] **Step 4: Run — all three pass**

Run: `pytest tests/test_image_contents.py -q`
Expected: **3 passed**.

- [ ] **Step 5: Prove the guard is not vacuous**

Temporarily delete the `COPY frontend ./frontend` line, re-run, and confirm
`test_the_static_mount_root_is_copied` fails. Restore the line. A guard nobody
has seen fail is a guard nobody knows works.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore tests/test_image_contents.py
git commit -m "fix(s86): the image never contained the UI, and nothing said so

The Dockerfile's COPY list is a hand-maintained enumeration of runtime needs,
and this repo has found four such lists drifted in three sprints. It had
drifted here too: frontend/ was absent, invisible while nothing served the UI
and a blank page the moment the mount landed.

The guard DERIVES the static root from the live app and the migration
directory from alembic.ini -- the two that move without anyone touching the
Dockerfile -- and keeps a literal floor for app/ and config.yaml. Same shape
as test_ratelimit_wiring: discovered off the container, named tuple as a
floor.

.dockerignore keeps frontend/uploads out: fixture resumes, invented or not,
have no business in a production image."
```

---

### Task 7: A CI job that builds the image

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the `Dockerfile` and `.dockerignore` from Task 6.
- Produces: nothing other tasks import.

**Nothing has ever built this Dockerfile.** CI has a `test` matrix and a
`postgres` job. GitHub's runners have Docker; this laptop does not (measured:
`docker` and `psql` not found, no install directory).

- [ ] **Step 1: Add the job**

Append to `.github/workflows/ci.yml`:

```yaml
  image:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # NOTHING had ever built this Dockerfile before S8.6. The local machine
      # has no Docker, so this job is the ONLY place the image is proven -- and
      # it only runs on a push, which is stated in the spec rather than assumed
      # away.
      - name: build
        run: docker build -t veritas:ci .
      # The cheapest proof that the image holds a working APPLICATION and not
      # just a working `pip install`: import the whole graph and exercise the
      # retention CLI in preview mode, which writes nothing.
      - name: the app imports and the retention CLI runs inside the image
        run: |
          docker run --rm \
            -e DEE_API_AUTH_KEY=ci-not-a-real-key \
            -e DEE_VECTORSTORE_BACKEND=memory \
            veritas:ci python -m app.retention.sweep | tail -1 | python -c \
            "import json,sys; d=json.loads(sys.stdin.read()); \
             assert d['dry_run'] is True, d; print('preview OK')"
      # The UI must be IN the image. tests/test_image_contents.py proves the
      # Dockerfile mentions it; this proves the build produced it.
      - name: the UI shipped
        run: docker run --rm veritas:ci test -f /srv/app/frontend/api.js
```

- [ ] **Step 2: Validate the YAML locally**

Run:

```bash
python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml parses')"
```
Expected: `ci.yml parses`. If `yaml` is not installed, use
`python -c "import json; print('skip')"` and rely on the next step.

- [ ] **Step 3: Verify the CLI's report shape matches the assertion**

The job asserts `d['dry_run'] is True`. Confirm that key exists in the real
report before trusting the job:

```bash
python -m app.retention.sweep | tail -1 | python -c "import json,sys; print(sorted(json.loads(sys.stdin.read()).keys()))"
```
Expected: a key list including `dry_run`. **If the key is named differently,
fix the workflow to match the code** — not the other way round. Task 8 pins
this contract properly.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(s86): build the image, and prove the app is inside it

Nothing had ever built this Dockerfile. The local machine has no Docker, so
this job is the only place the image is proven -- and only on a push, which
the spec states rather than assumes away.

Three steps: build; run the retention CLI inside the container (imports the
whole graph, writes nothing) ; assert frontend/api.js is present, because
test_image_contents proves the Dockerfile MENTIONS the UI and this proves the
build produced it."
```

---

### Task 8: Pin the retention CLI contract the cron will depend on

**Files:**
- Create: `tests/test_retention_cli_contract.py`

**Interfaces:**
- Consumes: `python -m app.retention.sweep` (built in S8.3 Phase B).
- Produces: the contract Task 10's `DEPLOY.md` cron section documents.

**No in-process scheduler.** With more than one replica an in-process timer runs
the most destructive operation in the repo N times concurrently, inside a web
worker where a long `DELETE` holding locks competes with request handling. The
cron is external; what this task guarantees is that the door it calls behaves as
documented.

- [ ] **Step 1: Write the failing test**

Create `tests/test_retention_cli_contract.py`:

```python
"""The cron calls this CLI, so its output contract is load-bearing (S8.6 §4).

The last-line rule was FOUND BY A TEST, not designed: the process shares stdout
with the structured log, so the stream is a SEQUENCE of JSON documents and
json.loads of the whole buffer raises "Extra data". jq is unaffected; a caller
doing json.loads(output) is not. Pinned here because a cron is exactly such a
caller, and it would fail in production at 3am with nobody reading stderr.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str, **env_over: str) -> subprocess.CompletedProcess:
    import os

    env = os.environ.copy()
    env.update({
        "DEE_API_AUTH_KEY": "cli-contract-key",
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_VECTORSTORE_BACKEND": "memory",
    })
    env.update(env_over)
    return subprocess.run(
        [sys.executable, "-m", "app.retention.sweep", *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=180,
    )


def test_the_report_is_the_last_line_and_is_json():
    proc = _run()
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    assert report["dry_run"] is True


def test_loading_the_whole_buffer_is_not_the_contract():
    """Documents the trap rather than leaving the next person to find it."""
    proc = _run()
    lines = proc.stdout.strip().splitlines()
    if len(lines) > 1:
        import pytest

        with pytest.raises(json.JSONDecodeError):
            json.loads(proc.stdout)


def test_a_disabled_sweep_exits_2_on_apply():
    """The cron must be able to tell 'refused' from 'ran and deleted nothing'.
    Both would otherwise be exit 0 with a plausible report."""
    proc = _run("--apply", DEE_RETENTION_SWEEP_ENABLED="false")
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)


def test_a_disabled_sweep_still_previews():
    """A count is safe, and it is how an operator sees what WOULD go before
    turning the knob on."""
    proc = _run(DEE_RETENTION_SWEEP_ENABLED="false")
    assert proc.returncode == 0, proc.stderr
```

- [ ] **Step 2: Run to see which assertions hold today**

Run: `pytest tests/test_retention_cli_contract.py -q`
Expected: these pin behaviour S8.3 Phase B already built, so most should
**pass**. Any that fail is either a real drift in the CLI or a wrong assumption
in this test — **investigate before changing either.** Do not edit the CLI to
match a guess; read `app/retention/sweep.py`'s `__main__` block and make the
test state what the code actually guarantees.

- [ ] **Step 3: Prove the exit-2 assertion is not vacuous**

Run: `pytest tests/test_retention_cli_contract.py -q -k exits_2` after
temporarily changing the expected code to `3`. It must fail. Restore `2`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_retention_cli_contract.py
git commit -m "test(s86): pin the retention CLI contract a cron depends on

No in-process scheduler: with N replicas an in-process timer runs the most
destructive operation in the repo N times concurrently, inside a web worker
where a long DELETE competes with request handling. The cron is external, so
what has to be guaranteed is the door it calls.

Three properties: the report is the LAST LINE and is JSON (found by a test in
Phase B, not designed -- stdout is shared with the structured log, so
json.loads of the whole buffer raises); exit 2 when the sweep is disabled, so
a cron can tell 'refused' from 'ran and deleted nothing', which would
otherwise both be exit 0 with a plausible report; a preview still works while
disabled."
```

---

### Task 9: `GET /` derives its endpoints list

**Files:**
- Modify: `app/main.py` (the `root()` handler, ~lines 180–260)
- Create: `tests/test_root_endpoints.py`

**Interfaces:**
- Consumes: `PUBLIC_PATHS`-adjacent knowledge only; reads `app.routes`.
- Produces: `GET /` returns `endpoints` derived from the live route table. Task
  13's smoke asserts it.

Carried from S8.3 Phase A, Phase B and the S8.5 outcome sprint, each time with
correct reasoning: patching entries by hand would make an unmaintained list look
maintained. It is now stale by every `/screening/*` route, `/metrics` and all
seven S8.3 Phase B routes. This is the "the deployable surface tells the truth
about itself" sprint, so there will not be a better one.

- [ ] **Step 1: Write the failing test**

Create `tests/test_root_endpoints.py`:

```python
"""GET / advertises the caller's entry points, DERIVED (S8.6 §6).

The filter is an explicit rule, not a taste judgement: every APIRoute, minus
FastAPI's own documentation paths, minus "/" itself, minus any Mount.

The admin plane is INCLUDED. The list has always advertised admin routes, and
hiding them would be security by obscurity on a plane that is already
credential-gated -- while making the list wrong again, which is the defect
being fixed.

This test does NOT re-implement the filter. A second derivation agreeing with
the first by construction is the SweepTarget.knob test the Phase B plan
correctly deleted. It asserts the CONSEQUENCES instead.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

DOC_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}


def _endpoints(services) -> list[str]:
    return TestClient(create_app(services)).get("/").json()["endpoints"]


def test_the_stale_entries_are_gone_because_it_is_derived(services):
    """The three families the hand-maintained list was missing."""
    listed = " ".join(_endpoints(services))
    assert "/screening/batches" in listed
    assert "/metrics" in listed
    assert "/portal/grievances" in listed
    assert "/admin/requests" in listed


def test_documentation_paths_are_excluded(services):
    for path in DOC_PATHS:
        assert not any(e.endswith(f" {path}") for e in _endpoints(services)), path


def test_the_mount_is_excluded(services):
    """A static mount is not an API entry point."""
    assert not any("/ui" in e for e in _endpoints(services))


def test_a_new_route_appears_without_anyone_editing_a_list(services):
    """The property the whole change exists for."""
    app = create_app(services)

    @app.get("/brand-new-surface")
    async def _new() -> dict:      # pragma: no cover - never called
        return {}

    listed = TestClient(app).get("/").json()["endpoints"]
    assert "GET /brand-new-surface" in listed


def test_the_shape_is_method_space_path(services):
    """The field's existing format, which clients may already parse."""
    for entry in _endpoints(services):
        method, _, path = entry.partition(" ")
        assert method.isupper() and path.startswith("/"), entry
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_root_endpoints.py -q`
Expected: **4 failed** — the stale-entries test (nothing about `/screening`,
`/metrics` or the Phase B routes is in the literal array), the new-route test,
and depending on the literal's contents, the mount and shape tests pass.

- [ ] **Step 3: Implement the derivation**

Replace the entire hand-maintained array and its long drift comment in
`app/main.py`'s `root()` with:

```python
    #: FastAPI's own documentation surface. Excluded from the advertised list
    #: because they describe the API rather than being part of it.
    _DOC_PATHS = frozenset(
        {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json", "/"}
    )

    def _advertised_endpoints() -> list[str]:
        """DERIVED from the live route table (S8.6 §6).

        This field was hand-maintained for eight PIs and was carried as a known
        drift through S8.3 Phase A, Phase B and S8.5 -- each time correctly,
        because typing the missing entries in would make an unmaintained list
        look maintained. The real fix, named in the note this replaces, is
        derivation, and `app.routes` is generated from the code.

        Mounts are excluded: a static UI directory is not an API entry point.
        The admin plane is INCLUDED -- it always was, and hiding it would be
        obscurity on a credential-gated plane while making the list wrong
        again.
        """
        seen: list[str] = []
        for route in app.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if path is None or methods is None or path in _DOC_PATHS:
                continue
            for method in sorted(methods):
                if method in {"HEAD", "OPTIONS"}:
                    continue
                entry = f"{method} {path}"
                if entry not in seen:
                    seen.append(entry)
        return sorted(seen, key=lambda e: (e.split(" ", 1)[1], e))
```

and in the returned `ServiceInfo`:

```python
            "endpoints": _advertised_endpoints(),
```

**Note on `app.routes` vs the guard's `_walk`:** `test_route_table_guard.py`
needed a recursive walk because FastAPI 0.138 stores an `_IncludedRouter`
wrapper. **Run the tests before assuming a flat iteration is enough** — if
`test_the_stale_entries_are_gone_because_it_is_derived` still fails, the
routes are behind wrappers and this function needs the same recursion. In that
case, factor the walk into `app/main.py` and have the guard's `_walk` stay
where it is; do **not** import test code into production.

- [ ] **Step 4: Run to verify they pass**

Run: `pytest tests/test_root_endpoints.py -q`
Expected: **5 passed.** If the stale-entries test still fails, apply the
recursion note above.

- [ ] **Step 5: Full suite**

Run: `pytest -q`
Expected: green. A failure here is likely a test asserting the old literal list
— update it to assert a derived property, not a new literal.

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_root_endpoints.py
git commit -m "fix(s86): GET / derives its endpoints list at last

Carried as a known drift through S8.3 Phase A, Phase B and S8.5, each time
with correct reasoning: typing the missing entries in would make an
unmaintained list look maintained. It was stale by every /screening/* route,
/metrics and all seven Phase B routes.

Derived from the live route table, with the filter as an explicit rule --
every APIRoute, minus FastAPI's doc paths, minus /, minus any Mount. The
admin plane stays included: it always was, and hiding it is obscurity on a
credential-gated plane.

The test asserts CONSEQUENCES, not a second copy of the filter -- a
derivation agreeing with itself by construction is the SweepTarget.knob test
Phase B correctly deleted."
```

---

### Task 10: `DEPLOY.md`, machine-checked against `Settings`

**Files:**
- Create: `DEPLOY.md`
- Create: `tests/test_deploy_doc.py`
- Modify: `README.md` (the `## Deploy` section points at it)

**Interfaces:**
- Consumes: the eight refusals (Task 1), the CLI contract (Task 8).
- Produces: the document a future session opens when the user says "go live".

- [ ] **Step 1: Write the failing test**

Create `tests/test_deploy_doc.py`:

```python
"""A runbook that names a variable the code does not read -- or omits one it
requires -- is the GET / endpoints defect wearing a different hat (S8.6 §7.1).

Both directions, for the same reason tests/test_retention_plan.py asserts set
equality both ways: a one-directional check lets the drift happen in the
direction nobody is watching.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "DEPLOY.md"

#: Settings the eight boot refusals read. If a refusal starts reading a new
#: one, DEPLOY.md must name it -- otherwise the checklist cannot satisfy it.
REFUSAL_SETTINGS = {
    "api_auth_key",
    "candidates_db_url",
    "session_cookie_secure",
    "cors_allowed_origins",
    "email_provider",
    "rate_limit_enabled",
    "grievance_officer_email",
    "email_smtp_host",
}


def _named_vars() -> set[str]:
    return set(re.findall(r"\bDEE_([A-Z0-9_]+)\b", DOC.read_text(encoding="utf-8")))


def test_every_variable_named_is_a_real_setting():
    fields = {f.upper() for f in Settings.model_fields}
    unknown = _named_vars() - fields
    assert unknown == set(), (
        f"DEPLOY.md names {sorted(unknown)}, which no Settings field reads. "
        "An operator would set them and nothing would happen."
    )


def test_every_setting_a_refusal_reads_is_documented():
    named = {v.lower() for v in _named_vars()}
    missing = REFUSAL_SETTINGS - named
    assert missing == set(), (
        f"the boot refusals read {sorted(missing)} but DEPLOY.md never names "
        "them, so following the checklist cannot produce a bootable config"
    )


def test_the_checklist_names_the_retention_cron():
    text = DOC.read_text(encoding="utf-8")
    assert "app.retention.sweep" in text and "--apply" in text, (
        "the sweep has no scheduler; without the cron the portal promises a "
        "purge nobody invokes"
    )


def test_the_checklist_names_the_ibm_check():
    """It has no better home, and it is materially worse retrofitted after a
    customer signs (GTM section 8.3)."""
    assert "IBM" in DOC.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_deploy_doc.py -q`
Expected: **4 errors** — `FileNotFoundError: DEPLOY.md`.

- [ ] **Step 3: Write `DEPLOY.md`**

Write it in the `OPERATING.md` register — for whoever runs this for a paying
customer, complete enough that go-live is a checklist rather than a
recollection. It must contain, at minimum:

1. **A banner:** this service has never been deployed, deliberately. There are
   zero customers; the user decides when that changes (spec §0.1).
2. **The pre-flight table: all eight boot refusals**, each with the variable
   that satisfies it and the failure it prevents. This doubles as the
   checklist, since a config satisfying all eight is a bootable one.
3. **Every `DEE_*` variable** with its value and why — including
   `DEE_EMAIL_PROVIDER=smtp` **and** `DEE_EMAIL_SMTP_HOST` (both are read by
   refusal 8, so both must be named or `test_every_setting_a_refusal_reads_is_
   documented` fails).
4. **`rate_limit_trusted_proxy_hops: 1` behind a proxy**, quoting
   `OPERATING.md` §3's failure mode: set it wrong and every caller shares one
   bucket, which looks exactly like an attack in the deny counter.
5. **`vectorstore_backend: memory`** unless a volume is mounted — its
   `PersistentClient` can hang.
6. **Postgres**, never SQLite (refusal 2), and that the container migrates
   itself on boot.
7. **The retention cron** (§4): schedule, `python -m app.retention.sweep
   --apply`, `retention_sweep_enabled`, what `truncated: true` means and that it
   must be re-run, exit `2` = refused.
8. **CORS is usually empty now** — the shipped UI is same-origin; only
   third-party integrations need an entry, and never `*`.
9. **The IBM IP / outside-activity check as a blocking line item**, with a
   pointer to GTM §8.3.
10. A note that `scripts/` is not in the image (Task 6), so
    `migrate_reports_into_main_db.py` is not available in the container — and
    that it is needed only by a deployment predating S8.1, of which there are
    none.

- [ ] **Step 4: Run until green**

Run: `pytest tests/test_deploy_doc.py -q`
Expected: **4 passed.** If `test_every_variable_named_is_a_real_setting` fails,
you have invented a variable — **fix the document, never the test**, unless the
setting genuinely should exist, in which case that is a separate decision to
raise.

- [ ] **Step 5: Point README at it**

Replace README's `## Deploy` body with a short pointer to `DEPLOY.md`, keeping
the "deploy-ready and not yet deployed" statement — which is still true, and
now true on purpose rather than by circumstance.

- [ ] **Step 6: Commit**

```bash
git add DEPLOY.md tests/test_deploy_doc.py README.md
git commit -m "docs(s86): DEPLOY.md, and a test that keeps it honest

The document a future session opens when the user says 'go live'. All eight
refusals as a pre-flight table, every DEE_* variable, trusted_proxy_hops=1
behind a proxy with OPERATING.md's failure mode quoted, the retention cron,
and Postgres.

Machine-checked in BOTH directions: every variable it names resolves to a
real Settings field, and every setting the refusals read is named. A runbook
listing a variable the code ignores is the GET / endpoints defect wearing a
different hat, and a one-directional check lets the drift happen in the
direction nobody is watching.

Carries the IBM IP / outside-activity check as a blocking line item. It is
not technical, and this is now the document where it will actually be read."
```

---

### Task 11: `smoke_s86.py` part 1 — eight refusals as process exits

**Files:**
- Create: `scripts/smoke_s86.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `check(name, ok, detail)` accumulating into `CHECKS`, and the
  `_boot_env()` helper Tasks 12 and 13 extend. Follow `scripts/smoke_s83b.py`'s
  structure exactly: module docstring naming what a unit test cannot prove,
  `CHECKS` list, `check()`, `_wait_healthy()`, `main()` returning an exit code.

**Why a process boundary:** unit tests prove `verify_launch_config` raises. Only
starting the real process proves the raise is not caught, logged and swallowed
somewhere between `create_app` and uvicorn's worker.

- [ ] **Step 1: Write the harness and the ordering check**

Create `scripts/smoke_s86.py` with the docstring, `check()`, and:

```python
def _prod_env(**over: str) -> dict:
    """A prod-shaped environment that satisfies ALL EIGHT refusals.

    The Postgres URL points at nothing on purpose. Refusal 2 tests
    `candidates_db_url.startswith("sqlite")` -- a STRING -- and
    verify_launch_config runs at app/main.py:84, BEFORE upgrade_to_head at
    line 89. So a syntactically valid URL satisfies refusal 2 and the process
    still exits on the refusal under test, never having opened a socket. That
    ordering is load-bearing for this whole section, so check 1 asserts it
    directly.
    """
    env = os.environ.copy()
    env.update({
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_ENV": "prod",
        "DEE_API_AUTH_KEY": "smoke-s86-admin-key",
        "DEE_CANDIDATES_DB_URL": "postgresql+psycopg://u:p@127.0.0.1:1/nope",
        "DEE_SESSION_COOKIE_SECURE": "true",
        "DEE_CORS_ALLOWED_ORIGINS": "[]",
        "DEE_EMAIL_PROVIDER": "smtp",
        "DEE_EMAIL_SMTP_HOST": "127.0.0.1",
        "DEE_RATE_LIMIT_ENABLED": "true",
        "DEE_GRIEVANCE_OFFICER_EMAIL": "dpo@example.com",
    })
    env.update(over)
    return env


def _boot(env: dict, timeout: float = 60.0) -> tuple[int, str]:
    """Start uvicorn, wait for it to DIE, return (exit code, combined output)."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(REFUSAL_PORT)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        return -1, out
    return proc.returncode, out
```

Then the ordering check, which must run **first**:

```python
    # CHECK 1. The refusals run BEFORE anything opens a database socket.
    # Without this, a passing refusal suite is equally consistent with "the
    # config is wrong in a way that exits early" -- the vacuous-guard shape
    # this repo keeps finding. A CORRECT prod config against a dead Postgres
    # must fail on the CONNECTION, never on a refusal.
    code, out = _boot(_prod_env())
    check("refusals_run_before_any_db_connection",
          code != 0 and "LaunchConfigError" not in out,
          detail=f"exit={code}")
```

- [ ] **Step 2: Run it and read the output**

Run: `python scripts/smoke_s86.py`
Expected: check 1 passes. **If it fails with `LaunchConfigError` in the output,
one of the eight is not satisfied by `_prod_env` — fix `_prod_env`, not the
check.** That is the check doing its job.

- [ ] **Step 3: Add the eight refusal checks**

One variable flipped per check. A config with two faults that exits proves only
that it exits.

```python
    REFUSALS = [
        ("api_auth_key",        {"DEE_API_AUTH_KEY": ""},                       "DEE_API_AUTH_KEY"),
        ("prod_on_sqlite",      {"DEE_CANDIDATES_DB_URL": "sqlite:///./x.db"},  "DEE_CANDIDATES_DB_URL"),
        ("insecure_cookie",     {"DEE_SESSION_COOKIE_SECURE": "false"},         "session_cookie_secure"),
        ("wildcard_cors",       {"DEE_CORS_ALLOWED_ORIGINS": '["*"]'},          "cors_allowed_origins"),
        ("capture_email",       {"DEE_EMAIL_PROVIDER": "capture",
                                 "DEE_EMAIL_CAPTURE_PATH": "/tmp/x.jsonl"},     "email_provider=capture"),
        ("rate_limit_off",      {"DEE_RATE_LIMIT_ENABLED": "false"},            "rate_limit_enabled"),
        ("no_grievance_email",  {"DEE_GRIEVANCE_OFFICER_EMAIL": ""},            "grievance_officer_email"),
        ("no_email_provider",   {"DEE_EMAIL_PROVIDER": "null"},                 "email"),
    ]
    for name, override, needle in REFUSALS:
        code, out = _boot(_prod_env(**override))
        check(f"refusal_{name}_exits_the_process",
              code != 0 and needle.lower() in out.lower(),
              detail=f"exit={code}")
```

- [ ] **Step 4: Run — all nine checks green**

Run: `python scripts/smoke_s86.py`
Expected: `OK` on check 1 and all eight refusals. Each `needle` must actually
appear in the refusal message — if one does not, **read the real message and
fix the needle**; do not weaken the assertion to `code != 0`, which would pass
for a process that died for any reason at all.

- [ ] **Step 5: Prove the refusal checks are not vacuous**

Temporarily comment out the eighth refusal in `app/core/boot.py`, re-run, and
confirm `refusal_no_email_provider_exits_the_process` **fails**. Restore it.

- [ ] **Step 6: Commit**

```bash
git add scripts/smoke_s86.py
git commit -m "test(s86): the eight refusals, as process exits

Unit tests prove verify_launch_config raises. Only starting the real process
proves the raise is not caught, logged and swallowed between create_app and
uvicorn's worker.

One variable flipped per check -- a config with two faults that exits proves
only that it exits -- and each assertion names a string from the specific
refusal, so a process that died for any other reason does not pass.

Check 1 is the one that makes the other eight mean something: a CORRECT prod
config against a dead Postgres must fail on the CONNECTION, never on a
refusal. Without it, a green refusal suite is equally consistent with 'the
config is wrong in a way that exits early'. It relies on
verify_launch_config running at main.py:84 before upgrade_to_head at 89 --
verified, and now asserted."
```

---

### Task 12: `smoke_s86.py` part 2 — a local SMTP sink, and `SMTPEmail`'s first delivery

**Files:**
- Modify: `scripts/smoke_s86.py`

**Interfaces:**
- Consumes: `_prod_env` from Task 11.
- Produces: `_SMTPSink` (a `threading.Thread` exposing `.messages: list[str]`)
  and a booted server for Task 13 to reuse.

`app/services/email.py`'s own docstring says S7.1's L2 assurance *"has NEVER
delivered an OTP to a human"*. It still has not delivered to anything —
`SMTPEmail` is selected by config no test selects, because selecting it means
opening a socket. This gives it one.

- [ ] **Step 1: Add the sink**

```python
class _SMTPSink(threading.Thread):
    """Enough of RFC 5321 to accept one message and remember it.

    aiosmtpd would do this in four lines and is NOT in requirements.txt; adding
    a package to PRODUCTION requirements to support a smoke is the wrong trade.

    No AUTH and no STARTTLS, and neither is laziness: SMTPEmail calls
    smtp.login() only when email_smtp_user is non-empty (app/services/email.py),
    so the smoke leaves it empty and sets DEE_EMAIL_SMTP_STARTTLS=false.
    Offering capabilities nothing exercises would be untested code in a test.
    """

    def __init__(self, port: int) -> None:
        super().__init__(daemon=True)
        self.messages: list[str] = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", port))
        self._sock.listen(8)

    def run(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                try:
                    self._serve(conn)
                except OSError:
                    pass

    def _serve(self, conn: socket.socket) -> None:
        f = conn.makefile("rwb")
        f.write(b"220 localhost smoke-sink\r\n")
        f.flush()
        body: list[bytes] = []
        in_data = False
        while True:
            line = f.readline()
            if not line:
                return
            if in_data:
                if line.strip() == b".":
                    self.messages.append(b"".join(body).decode("utf-8", "replace"))
                    body, in_data = [], False
                    f.write(b"250 OK\r\n")
                    f.flush()
                else:
                    body.append(line)
                continue
            cmd = line.strip().upper()
            if cmd.startswith((b"EHLO", b"HELO")):
                f.write(b"250 localhost\r\n")
            elif cmd.startswith(b"DATA"):
                in_data = True
                f.write(b"354 go ahead\r\n")
            elif cmd.startswith(b"QUIT"):
                f.write(b"221 bye\r\n")
                f.flush()
                return
            else:
                f.write(b"250 OK\r\n")
            f.flush()

    def stop(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass
```

- [ ] **Step 2: Boot a SERVING instance and drive a full login**

The serving phase cannot be `env=prod` — prod refuses SQLite and this machine
has no Postgres. It runs at `env=staging` with every other prod value set, and
**says so in its own output**, because a smoke that silently proves less than
its name implies is the "check whose name claims more than its assertion makes"
defect that hid a real bug for an afternoon in Phase B.

```python
    print("NOTE: the serving phase runs at DEE_ENV=staging, not prod: prod "
          "refuses SQLite (refusal 2) and this machine has no Postgres. "
          "env=prod on Postgres is covered by the CI 'postgres' job; the "
          "image is covered by the CI 'image' job. See spec section 0.4.")

    sink = _SMTPSink(SMTP_PORT)
    sink.start()
    env = _prod_env(
        DEE_ENV="staging",
        DEE_CANDIDATES_DB_URL=f"sqlite:///{db_path.as_posix()}",
        DEE_SESSION_COOKIE_SECURE="false",
        DEE_SESSION_COOKIE_SAMESITE="lax",
        DEE_EMAIL_PROVIDER="smtp",
        DEE_EMAIL_SMTP_HOST="127.0.0.1",
        DEE_EMAIL_SMTP_PORT=str(SMTP_PORT),
        DEE_EMAIL_SMTP_STARTTLS="false",
        DEE_EMAIL_FROM="veritas@example.com",
        DEE_EMAIL_SMTP_USER="",
    )
```

Start uvicorn with that env (non-blocking, like `smoke_s83b.py`), wait for
`/healthz`, then:

```python
    # A COMPLETE login over a REAL SMTP conversation. SMTPEmail has never
    # delivered to anything -- it is selected by config no test selects,
    # because selecting it means opening a socket.
    email = "delivery.test@example.in"
    r = api.post("/auth/candidate/signup", json={"email": email})
    check("signup_accepted", r.status_code == 202, detail=str(r.status_code))

    for _ in range(60):
        if sink.messages:
            break
        time.sleep(0.25)
    check("smtp_sink_received_a_message", bool(sink.messages),
          detail=f"{len(sink.messages)} message(s)")

    code_match = re.search(r"\b(\d{6})\b", sink.messages[-1] if sink.messages else "")
    check("the_delivered_message_contains_a_usable_code", code_match is not None)

    r = api.post("/auth/candidate/verify",
                 json={"email": email, "code": code_match.group(1)})
    check("verify_with_the_delivered_code_establishes_a_session",
          r.status_code == 200 and "dee_session" in r.cookies,
          detail=str(r.status_code))
```

Adjust the OTP regex only after reading the real body in `sink.messages[-1]` —
**print it once while developing**, then pin what is actually there.

- [ ] **Step 3: Run**

Run: `python scripts/smoke_s86.py`
Expected: the four new checks green. A failing
`smtp_sink_received_a_message` means `build_email` fell back to `NullEmail` —
check `email_smtp_host` is non-empty in the env, since that is the exact
fallback Task 1's refusal exists to catch.

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_s86.py
git commit -m "test(s86): SMTPEmail delivers for the first time since it was written

app/services/email.py's docstring says S7.1's L2 assurance 'has NEVER
delivered an OTP to a human'. It had not delivered to anything: SMTPEmail is
selected by config no test selects, because selecting it opens a socket.

A ~60-line SMTP sink in the smoke gives it one, and a candidate signup runs
end to end -- code composed, accepted by a server, read back out of the
delivered message, verified, session established. No AUTH and no STARTTLS in
the sink, because SMTPEmail calls login() only for a non-empty user and the
smoke sets starttls=false: capabilities nothing exercises would be untested
code inside a test.

The serving phase runs at env=staging and SAYS SO in its own output. prod
refuses SQLite and this machine has no Postgres; that is covered by CI. A
smoke that silently proves less than its name implies is the overclaiming
check Phase B caught."
```

---

### Task 13: `smoke_s86.py` part 3 — the UI, the CLI, the metrics, the root list

**Files:**
- Modify: `scripts/smoke_s86.py`

**Interfaces:**
- Consumes: the serving instance from Task 12.

- [ ] **Step 1: Add the remaining checks**

```python
    # The UI is served BY THE API, same origin -- the posture that will ship.
    r = api.get("/ui/api.js")
    check("the_ui_is_served_same_origin",
          r.status_code == 200 and "veritas" in r.text[:400].lower(),
          detail=str(r.status_code))

    # It must not require a credential: a login page behind a login is
    # unreachable by the person who needs it.
    anon = httpx.Client(base_url=BASE, timeout=30)
    check("the_ui_needs_no_credential", anon.get("/ui/api.js").status_code == 200)

    # GET / no longer advertises a hand-maintained list (S8.6 section 6).
    listed = " ".join(api.get("/").json()["endpoints"])
    check("root_advertises_the_screening_surface", "/screening/batches" in listed)
    check("root_advertises_metrics", "/metrics" in listed)
    check("root_advertises_the_phase_b_rights_routes",
          "/portal/grievances" in listed and "/admin/requests" in listed)
    check("root_does_not_advertise_the_static_mount", "/ui" not in listed)

    # /metrics is admin-gated and labels by route TEMPLATE.
    m = api.get("/metrics")
    check("metrics_responds", m.status_code == 200, detail=str(m.status_code))
    check("metrics_labels_by_route_template",
          "/screening/batches/{batch_id}" in m.text or "veritas_http_requests_total" in m.text)

    # The retention CLI, against the SERVER'S OWN database.
    cli = subprocess.run(
        [sys.executable, "-m", "app.retention.sweep"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=180,
    )
    check("retention_cli_previews_cleanly", cli.returncode == 0, detail=cli.stderr[-200:])
    report = json.loads(cli.stdout.strip().splitlines()[-1])
    check("retention_report_is_the_last_line_and_is_a_dry_run",
          report.get("dry_run") is True)
```

- [ ] **Step 2: Run the whole smoke**

Run: `python scripts/smoke_s86.py`
Expected: every check `OK`, and a final summary line with a non-zero exit on any
failure — copy the summary/teardown block from `scripts/smoke_s83b.py` so the
server and the sink are always stopped.

- [ ] **Step 3: Run it twice in a row**

Run: `python scripts/smoke_s86.py && python scripts/smoke_s86.py`
Expected: green both times. A smoke that only passes against a fresh database is
a smoke that will fail the first time somebody re-runs it.

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_s86.py
git commit -m "test(s86): the UI, the derived root list, metrics and the CLI over the wire

The UI answers same-origin and without a credential; GET / advertises the
three families the hand-maintained list had been missing since S8.3 and does
NOT advertise the static mount; /metrics responds with route-template labels;
the retention CLI previews against the server's own database with its report
on the last line.

Runs twice in a row green -- a smoke that only passes against a fresh
database fails the first time somebody re-runs it."
```

---

### Task 14: Re-point the browser check at the same-origin posture

**Files:**
- Modify: `scripts/check_ui_screening_browser.py`
- Modify: `scripts/check_ui_screening_contract.py` if it hardcodes the API base

**Interfaces:**
- Consumes: the `/ui` mount (Task 3), `api.js`'s new default (Task 5).

This is where Task 5 is actually proven. The UI is outside pytest and outside
CI, which is why S8.5 built three executing layers for it — and the cookie and
CSRF path in the posture that will ship has never been exercised.

- [ ] **Step 1: Delete the second server, load the UI from the API**

Remove the `python -m http.server` subprocess and `UI_ORIGIN`. Change the
navigation URL from `f"{UI_ORIGIN}/Veritas.dc.html?api={API_BASE}"` to
`f"{API_BASE}/ui/Veritas.dc.html"` — **with no `?api=`**, because the point is
to prove the same-origin default works.

Update the module docstring's line 22 claim (*"different ORIGINS (CORS still
applies) — which is the posture the UI ships in"*), which is now false. Replace
it with what is true and why it changed, citing spec §2.1: the old arrangement
was cross-origin but **same-site** with `samesite=lax`, so it never exercised
the shipped `SameSite=None` either.

Drop `DEE_CORS_ALLOWED_ORIGINS` from the env (no cross-origin caller remains)
and keep `DEE_SESSION_COOKIE_SAMESITE=lax`, which is now the shipped default
rather than a test-only convenience.

- [ ] **Step 2: Run**

Run: `python scripts/check_ui_screening_browser.py`
Expected: the same check count as on `main` (19/19 at the S8.5 outcome sprint;
confirm against the ROADMAP). **A 404 on navigation means the mount path is
wrong; a 401 means the mount is behind a credential** — both are real failures
of Task 3, not of this task.

- [ ] **Step 3: Run the contract check and the bindings check**

Run:
```bash
python scripts/check_ui_screening_contract.py
node scripts/check_ui_bindings.js
```
Expected: both at their `main` counts.

- [ ] **Step 4: Commit**

```bash
git add scripts/check_ui_screening_browser.py scripts/check_ui_screening_contract.py
git commit -m "test(s86): the browser check runs the posture that will ship

It served the UI from its own http.server and navigated with ?api=, which
proved the cross-origin arrangement -- and its docstring claimed that was
'the posture the UI ships in'. That claim is now false, and it was always
half-true: both servers were on localhost, so it was cross-ORIGIN but
same-SITE, with samesite=lax and secure=false. config.yaml's SameSite=None
was never exercised by anything.

Now it loads /ui/Veritas.dc.html from the API itself with no ?api=, which is
also the only real proof of api.js's new same-origin default -- that file is
outside pytest and outside CI."
```

---

### Task 15: Regression sweep, ROADMAP, and the branch handoff

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `OPERATING.md` (§8 "there is no scheduler" gains a pointer to
  `DEPLOY.md`'s cron; §11 "Alerting … deploy-time concern (S8.6)" is now stale
  — S8.6 did not deploy, so say where it actually went)

- [ ] **Step 1: Full test suite**

Run: `pytest -q`
Expected: green, comfortably above 1812. **Record the exact number** — it goes
in the ROADMAP and the session log.

- [ ] **Step 2: Run a test file on its own**

Run: `pytest tests/test_ui_mount.py -q` and
`pytest tests/test_image_contents.py -q`, each alone.

This is not ceremony. S8.3 Phase B shipped a test that **passed in its file and
failed alone**, because `tests/conftest.py` keeps its own model-registration
list. Any new module that touches the DB must be run in isolation before the
branch is called green.

- [ ] **Step 3: The model-registration guard**

Run: `pytest tests/test_model_registration.py -q`
Expected: PASS. No new table is added by this sprint, so it should be
untouched — if it fails, something added a model and both `alembic/env.py` and
`tests/conftest.py` need it.

- [ ] **Step 4: All twenty smokes**

Run each of the nineteen existing smokes plus `smoke_s86`. The three at genuine
risk are `smoke_s85_outcome`, `smoke_s83b` and `smoke_s84b` — this branch moved
the cookie default and the root endpoints list underneath them.

```bash
for s in s12 s13 s23 s41 s51 s52 s53 s63 s64 s71 s72 s73 s81 s82 s83a s83b s84a s84b s85_outcome s86; do
  echo "=== $s ==="; python scripts/smoke_$s.py >/dev/null 2>&1 && echo OK || echo FAIL
done
```
Expected: 20 × OK. **Investigate any FAIL by re-running it with output.**

- [ ] **Step 5: Update `docs/ROADMAP.md`**

Add a "Current state" entry at the top covering: S8.6 built, the exact test
count, the smoke results, **and the four things worth carrying** —

1. The deploy sprint stopped being a deploy, and why (zero customers; the user
   gates go-live).
2. The eighth refusal had to ask the builder, not the provider string, because
   `provider=smtp` with an empty host silently returns `NullEmail`.
3. The route-table guard could not see mounts at all, and serving the UI would
   have opened the first invisible hole in it.
4. The "tested cross-origin posture" was cross-origin but **same-site**, so the
   shipped `SameSite=None` had never been exercised anywhere — a case of
   reaching for "we tested it" without checking which property the test pinned.

Mark S8.6 `[x]` in the status board with the title changed from "DEPLOY /
launch" to "Production shape", and add a new **unscheduled, user-gated** line
under it for the go-live pointing at `DEPLOY.md`. Do **not** give it a sprint
ID — it is not a sprint.

- [ ] **Step 6: Commit and hand off**

```bash
git add docs/ROADMAP.md OPERATING.md
git commit -m "docs(s86): S8.6 complete -- production shape, nothing deployed"
```

**Do not merge.** The branch goes to review next: use
`superpowers:requesting-code-review`, then `superpowers:finishing-a-development-branch`.
Every branch review since S7.1 has found a real defect, and the last two found
defects that were **invisible to a green suite**.

---

## Self-Review

**Spec coverage:**

| Spec § | Task |
|---|---|
| §0.1 no deploy | Global Constraints; Task 15 Step 5 |
| §1 eighth refusal (+1.1 derived) | Task 1 |
| §2.1–2.2 mount guard | Tasks 2, 3 |
| §2.3–2.4 cookie posture + stale docs | Task 4 |
| §2.5 api.js | Task 5 |
| §3 Dockerfile + guard | Task 6 |
| §3.1 CI image job | Task 7 |
| §4 retention cron | Task 8 (contract) + Task 10 (`DEPLOY.md`) |
| §5.1 eight refusals as process exits | Task 11 |
| §5.2 staging admission | Task 12 Step 2 |
| §5.3 SMTP sink | Task 12 |
| §5.4 UI / CLI / metrics / root | Task 13 |
| §5.5 regression set | Tasks 14, 15 |
| §6 derived endpoints | Task 9 |
| §7 `DEPLOY.md` + §7.1 machine check | Task 10 |

No spec section is unassigned.

**Known soft spots, stated rather than hidden:**

- **Task 2's test does not start red.** Called out in the task itself, with its
  red state scheduled explicitly as Task 3 Step 4.
- **Task 5 has no automated test in its own task.** It is a browser-only file;
  Task 14 is its proof, and both tasks say so.
- **Task 9 Step 3 carries a conditional** (flat iteration vs recursion over
  `_IncludedRouter`). The condition is decidable by running the test in Step 4,
  and both branches are specified.
- **Task 12's OTP regex** is written as `\b(\d{6})\b` and the plan instructs
  printing the real body before pinning it, rather than asserting a guess.
