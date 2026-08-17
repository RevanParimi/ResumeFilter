# S8.6 — Production shape (design)

**Date:** 2026-08-12 · **Sprint:** S8.6 (PI-8, the last one) · **Status:** spec,
approved by the user 2026-08-12.
**Read order:** `docs/ROADMAP.md` "Current state" →
`2026-08-01-pi8-launch-readiness-design.md` §5 → `OPERATING.md` §§8, 11 → this.
**Builds as ONE branch:** `s86-production-shape`.

*What would be wrong with this system the first time it runs somewhere that is
not a laptop?* — that is the whole sprint. It is deliberately **not** the
deploy.

---

## 0. Decisions taken before the design (with the user, 2026-08-12)

**0.1 THE SPRINT DOES NOT DEPLOY. Nothing here creates a cloud resource.**
The roadmap has called S8.6 "DEPLOY / launch — Railway, HTTPS, prod config, live
smoke" since PI-8 was shaped. The user struck the first three words:

> *"do we have any customers to do anything now? then why are u in a hurry to
> deploy and go live, hold your horses… i decide when to go live."*

The argument is unanswerable and was already in our own documents: there are
**zero customers and zero pilot orgs** — the fact `2026-08-01-veritas-gtm-
positioning.md` is built on, and the reason PI-9's calibration harness is gated
in the first place. A public URL with no customer serves nobody, starts a bill,
and moves the **IBM IP / outside-activity check** (GTM §8.3, still outstanding)
from "cheap to clear" to "clear it under time pressure".

So the sprint keeps its ID — IDs are stable identifiers here, only order and
scope move — and changes its title to **"Production shape"**. The deliverable is
a system that is *correct to deploy*, proven as far as this machine can prove it.
**Go-live is not a sprint.** It is a checklist in `DEPLOY.md` that the user runs
when the user decides, and this document does not schedule it.

Rejected: *deploy to Railway and simply not advertise the URL.* Railway-generated
domains are public and indexable; "unadvertised" is not a security posture, and
it would put an OTP-sending, PII-storing service on the internet to prove a
property (`the container boots`) that CI proves for free.
Rejected: *a throwaway deploy torn down the same session.* It answers a narrow
question — does the image boot on Railway — at the cost of the exact thing the
user asked me to stop doing, and §5 gets most of that answer without it.

**0.2 The UI is served BY THE API, same origin.** Chosen by the user over a
separate static service. See §2, which includes a correction to the
recommendation I opened with.

**0.3 Locally, email is whatever is convenient.** *"do whatever you want
locally."* The smoke uses a real SMTP conversation against a local sink (§5.3);
no credential is requested, stored, or needed, and the question "which SMTP
vendor" is deferred to go-live, where it belongs.

**0.4 Verification splits by machine, and the split is stated rather than
blurred.** This laptop has **no Docker and no Postgres** — measured, not assumed
(`docker`, `psql`: not found; no install directory). Therefore:

| Property | Proven where |
|---|---|
| Behaviour: refusals, same-origin UI, SMTP, retention CLI | **this machine** (`scripts/smoke_s86.py`) |
| Postgres dialect, migrations up/down/up | **CI** (`postgres` job, exists since S8.1) |
| The image actually builds and contains what it needs | **CI** (`image` job, new — §3) |

**No local run is going to be described as proving the container.** The one
claim this sprint must not make falsely is "it works in production", and the
honest version of that claim has three sources, not one.

---

## 1. The eighth boot refusal — `email_provider=null` in prod

`app/core/boot.py` refuses `email_provider == "capture"` in prod, because
`CaptureEmail` writes OTPs to a file in plaintext. It does **not** refuse
`"null"`, which is the shipped default in `config.yaml`.

So today a production boot with no email configuration **succeeds**, and then:

- `POST /auth/org/signup` → `503 email_unavailable`
- `POST /auth/candidate/signup` → `503`
- every login on all three planes → `503`

Org self-onboard is **PI-8 blocker 5**. Candidate self-registration is **blocker
4**. Both are dead on arrival, and the service reports itself healthy the whole
time — `/healthz` knows nothing about email. An operator's first evidence is a
customer saying the signup button is broken.

This is the repo's most-repeated defect shape, now on the launch path:
`auth_sessions.ip_hash` was declared and never populated (S8.3 Phase A's headline
finding); four metrics were declared with no call site and were deleted rather
than wired; `sweep_active` was a hardcoded `False` telling every data principal
that nothing purges. **A declared-inert capability is worse than an absent one,
because absent is visible.**

The eighth refusal:

```
DEE_ENV=prod with no working email provider. Signup and login on all three
planes answer 503 email_unavailable, so org self-onboard (PI-8 blocker 5) and
candidate self-registration (blocker 4) do not work at all -- while /healthz
reports the service healthy. Set email_provider=smtp with email_smtp_host and
the DEE_EMAIL_SMTP_* credentials. There is no provider that "works well
enough" for a login code: the code either arrives or the account is
unreachable.
```

### 1.1 The refusal ASKS THE BUILDER; it does not re-test the provider string

The obvious implementation — `if settings.email_provider == "null": raise` — is
**wrong, and wrong in this repo's most-repeated way.** `build_email` does not
key on the provider name alone:

```python
if settings.email_provider == "smtp" and settings.email_smtp_host:
    return SMTPEmail(settings)
...
return NullEmail(settings)
```

So `email_provider=smtp` with an **empty `email_smtp_host`** silently returns
`NullEmail`. A refusal that checked the string would pass that config and the
deployment would 503 every login anyway — the exact failure the refusal exists
to prevent, reached through the door the refusal was not watching. That is "a
rule applied at one entry point and not the other", which has shipped as a real
defect in S7.1, S7.2, S7.3, S8.4 Phase B and S8.5.

`EmailClient.available` already exists for precisely this question — *"Can this
client deliver at all?"* — and is `False` only on `NullEmail`. So the refusal is:

```python
if not build_email(settings).available:
    raise LaunchConfigError(...)
```

One predicate, owned by the builder, with no second copy to drift.
`build_email` opens no socket, so this costs a boot nothing. `capture` is still
caught by its own earlier refusal (it *is* available, and its problem is that it
writes OTPs to a file rather than that it cannot deliver), so the two refusals
stay independent and each isolates one fault.

**A test pins the derivation rather than the string**: `email_provider="smtp"`
with an empty host must be refused. If someone later "simplifies" this to a
provider-name check, that test is what fails.

### 1.2 The consequence, stated because it is the point

With `null` and `capture` both refused, **a prod boot now requires real SMTP
credentials.** That is not a side effect to work around; it is the property. It
means no one — including me, in a future session, moving fast — can put this
service on a public host in a state where nobody can log into it. It converts
go-live from something that can happen by momentum into something that requires
the user to obtain a credential, which is exactly the gate 0.1 establishes.

Rejected: *a warning log instead of a refusal.* The failure is invisible at boot
and surfaces as a customer complaint; a log line in a service nobody is watching
yet is the same as nothing. Rejected: *refuse only when `env=prod` AND a UI
origin is configured* — a conditional refusal is a refusal with a bypass, and
`boot.py`'s own docstring already rejects that shape ("an env-gated escape would
make a safe deploy depend on remembering two variables instead of one").

### 1.3 What it costs the existing tests

`_prod()` in `tests/test_boot_config.py` exists to satisfy every prior refusal so
each test isolates the one it names. It gains `email_provider="smtp"` and the
host/from fields, exactly as it gained `grievance_officer_email` in S8.3 Phase B.
A test asserts the new refusal does **not** fire outside prod, because
`config.yaml` ships `null` and every local run would break above that line.

---

## 2. Same-origin UI

`frontend/` is served by the API itself: `app.mount("/ui", StaticFiles(...))`,
and `COPY frontend ./frontend` in the image.

### 2.1 A correction to the recommendation I opened with

I recommended a **separate** static service, on the stated grounds that
cross-origin was "the posture every S8.5 check measured". That reasoning was
wrong on the one detail that decides it.

`scripts/check_ui_screening_browser.py` serves the UI on `localhost:<UI_PORT>`
and the API on `localhost:<API_PORT>`. Different ports are a different **origin**
(so CORS genuinely applies and is genuinely exercised) but the **same site** —
`SameSite` keys on the registrable domain, not the port. And the check sets, in
as many words:

```python
"DEE_SESSION_COOKIE_SECURE": "false",
"DEE_SESSION_COOKIE_SAMESITE": "lax",
```

So the posture `config.yaml` actually ships for production — `SameSite=None`
with `Secure` — has **never been exercised by any check in this repo**. The
cross-origin story I was defending was half-measured: its CORS half was real,
its cookie half was `lax` all along.

**Same-origin therefore does not ship an untested posture. It retires one.**
This is worth recording as more than an apology: I reached for "we tested it" as
a decisive argument without checking *which* property the test pinned, and the
repo's own history (S8.3 Phase A: "the fixture was more correct than
production") says that is precisely where confidence is least reliable.

### 2.2 The hole a mount would otherwise open — the load-bearing part of §2

`tests/test_route_table_guard.py` is the structural answer to PI-8's highest
regression risk: it walks the live route table and asserts every non-public route
establishes its principal through one of four sanctioned resolvers. It cost real
effort to make it see all 63 routes rather than nine.

**It cannot see mounts at all.** A `StaticFiles` mount is a
`starlette.routing.Mount`, not an `APIRoute`. It has no `.methods`, and
`_guarded_routes` skips on exactly that:

```python
if path is None or methods is None or path in PUBLIC_PATHS:
    continue
```

Router-level dependencies do not apply to it either, so **the mount is
unauthenticated and the guard is silent about it**. Being unauthenticated is
*correct* — the UI shell has to load before anyone can log in, and a login page
behind a login is the `GET /grievance` argument one floor down. What is not
correct is that it would be correct *invisibly*.

`PUBLIC_PATHS` exists so that widening the unauthenticated surface is a
reviewable act in a diff someone reads. Mounts are a second way to widen that
surface, with no equivalent. **So the mount ships with the guard extended to
enumerate mounts and assert them against a literal allow-list**, the same shape
and for the same reason as `test_public_paths_is_an_explicit_short_list`.

The new assertions:

1. Every `Mount` in the live app is in a pinned literal set (`{"/ui"}`).
2. The guard fails when a second mount is added — proven by adding one in the
   test, the way `test_the_guard_would_catch_a_new_unguarded_route` does. A guard
   nobody has seen fail is a guard nobody knows works.
3. The mount serves `frontend/` and nothing above it. Path traversal out of the
   static root is Starlette's job, not ours, but the *root we hand it* is ours,
   and a test pins it.

**This is the highest-value item in the sprint** and it is not the UI. It is
that adding the UI would otherwise have quietly created the first hole in a
guard built specifically to make holes loud.

### 2.3 What same-origin retires, and what it does not

| Thing | Before | After |
|---|---|---|
| `session_cookie_samesite` | `none` (forced) | `lax` (default) |
| `session_cookie_secure` | true in prod | **unchanged** — still true, still refused if false |
| `cors_allowed_origins` for the shipped UI | required | not required |
| CORS machinery + prod wildcard refusal | present | **unchanged** |
| CSRF (`dee_csrf` + `X-CSRF-Token`) | required | **unchanged — kept** |

**CSRF stays.** `SameSite=Lax` already blocks cross-site `POST`, so the naive
read is that CSRF is now redundant. It is kept for three reasons: it is built,
tested and free; `Lax` is a browser-side control and the server should not
delegate its only defence to the client's correctness; and removing it is a
large change to the authenticated write path of every plane, to delete code that
costs nothing. Deleting a working defence during the sprint that changes the
cookie posture is how one property gets traded for another by accident.

**CORS machinery stays** because the API is not only called by our UI — an
org's own integration is a first-class consumer (`UI.md` §2, `OPERATING.md` §7
step 3 assumes one). What changes is that the *shipped* UI no longer needs an
entry in `cors_allowed_origins`, so the list can be empty in a normal deploy and
the wildcard refusal keeps its meaning.

### 2.4 The documents that become false, and are corrected rather than left

- `app/auth/csrf.py:3` — *"SameSite=None is required rather than chosen — the UI
  is separately hosted"*. The premise stops being true. The docstring is
  rewritten to say what is now true and **why the CSRF layer survives the change
  anyway** (§2.3), because a reader who only fixes the first sentence would
  reasonably conclude the layer can go.
- `AUTH.md` — same claim, same fix.
- `app/core/boot.py:58-64` — the `session_cookie_secure` refusal's message cites
  `SameSite=None (required, because the UI is separately hosted)` as its
  justification. The refusal is still right; its stated reason is not. `Secure`
  is now required because the session cookie travels over the public internet,
  which is the simpler and more durable argument.
- `UI.md` §"CORS is fail-closed and server-side" — gains the same-origin case.

A stale comment that *justifies* a live check is worse than a stale comment
beside dead code: the next person to touch the check reads a reason that no
longer holds and concludes the check is obsolete.

### 2.5 `frontend/api.js`

`DEFAULT_BASE` is `"http://localhost:8000"`. Served same-origin, the default
becomes `""` — every call relative to the page. The `?api=` override and the
`localStorage` precedence are **kept exactly as they are**: they exist so the
base URL is never invisible, and the same-origin default does not change that
argument. A UI loaded from the API that silently talked to a *different* API
because of a stale `localStorage` entry is precisely the failure that comment
was written about.

The `credentials: "include"` rule stays. It is a no-op for same-origin requests
and remains correct for the `?api=` case, and removing it would break the one
configuration a developer uses most.

### 2.6 What is NOT in scope

The UI is served, not rebuilt. No screen is redesigned, no `.dc.html` logic is
touched beyond `api.js`'s base URL. `frontend/uploads/` is a fixture directory
for the browser check and is **not** copied into the image.

---

## 3. The Dockerfile's `COPY` list is a hand-maintained list

```dockerfile
COPY app ./app
COPY config.yaml .
COPY alembic ./alembic
COPY alembic.ini .
```

That is a hand-maintained enumeration of everything the app needs at runtime,
and this repo has found four of those drifted in the last three sprints alone —
`tests/conftest.py`'s model imports (which failed a test *when run alone*),
`alembic/env.py`'s imports (six missing, which would have made
`--autogenerate` emit `DROP TABLE` for six live tables), the `RateLimited` → 429
translation copied four times, and `test_ratelimit_wiring.py`'s `LIMITED` tuple.

It has already drifted here: **`frontend/` is missing**, which was invisible
while nothing served the UI and becomes a blank page the moment §2 lands.

Two changes:

1. `COPY frontend ./frontend` (excluding `uploads/`, via `.dockerignore`).
2. **A guard**, in the shape this repo has settled on: a test that derives the
   set of runtime paths the application actually reads and asserts each is
   `COPY`-ed. Derived, not typed — a second hand-maintained list checking the
   first is the S8.3 Phase B `SweepTarget.knob` mistake.

### 3.1 A CI job that builds the image

CI has a `test` matrix and a `postgres` job. **Nothing has ever built the
Dockerfile.** GitHub's runners have Docker; this laptop does not. A third job
builds the image and runs one command inside it — `python -m app.retention.sweep`
(preview mode, which needs no database write and exercises the CLI's real import
graph). That is the cheapest possible proof that the image contains a working
application rather than a working `pip install`.

It is a genuine limitation that this job only runs when the user pushes, and the
last push was a month before S8.4. Stated here so nobody reads a green local run
as covering it.

---

## 4. Retention: a cron specification, not a scheduler

`OPERATING.md` §8 is explicit — *"Nothing in `app/` runs this on a timer. If
nobody invokes it, nothing is deleted."* The ROADMAP names wiring it as the
thing S8.6 must not forget, because deploying without it ships a portal that
promises a purge nobody invokes, and `/portal/me` now derives `sweep_active`
from config, so it would be **actively telling every data principal** that a
mechanical purge runs.

**No in-process scheduler.** Rejected explicitly: with more than one replica,
an in-process timer runs the most destructive operation in the repo N times
concurrently; and it would fire inside a web worker, where a long `DELETE`
holding locks competes with request handling. The correct shape for a container
platform is an external scheduled invocation of the CLI door that already
exists.

What ships:

- The cron **specification** in `DEPLOY.md` §retention — schedule, command
  (`python -m app.retention.sweep --apply`), the `retention_sweep_enabled` knob,
  what a truncated report means and that it must be re-run.
- A test pinning the CLI contract the cron depends on: **report is the last line
  of stdout and is JSON** (found by a test in Phase B, not designed — the process
  shares stdout with the structured log), **exit `2`** when the sweep is
  disabled, exit `0` on a preview.
- The smoke runs the CLI for real (§5.4).

Nothing is scheduled by this sprint, because nothing is deployed by this sprint.
The cron is configured at go-live, and `DEPLOY.md` refuses to call the checklist
complete without it.

---

## 5. `scripts/smoke_s86.py` — prod config, no Docker

Every prior smoke boots uvicorn with a local config and drives HTTP. This one is
different in kind: **its subject is the configuration, not the feature.**

### 5.1 All eight refusals fire

For each of the eight, start the process with a prod-shaped environment and
**exactly one variable flipped to the bad value**, and assert it exits non-zero
with the refusal named. One variable at a time is the whole design: a config with
two faults that exits proves only that it exits.

This is the first time the refusals are checked **as a process boundary** rather
than by calling `verify_launch_config` directly. Unit tests prove the function
raises; only starting the real process proves the raise is not caught, logged and
swallowed somewhere between `create_app` and uvicorn's worker.

**How five of them are reachable on a machine with no Postgres.** Refusals 4–8
are prod-only, so they need `DEE_ENV=prod` — which puts refusal 2 (prod on
SQLite) in front of them, and this machine cannot satisfy it with a real
database. It does not need to: refusal 2 tests
`candidates_db_url.startswith("sqlite")`, a **string**, and
`verify_launch_config` runs at `app/main.py:84`, *before* `upgrade_to_head` at
line 89 — verified, not assumed. So a syntactically valid Postgres URL pointing
at nothing satisfies refusal 2 and the process still exits on the refusal under
test, never having opened a socket.

That ordering is load-bearing for this whole section, so **the smoke asserts it
directly**: with a bogus Postgres URL and an otherwise-correct prod config, the
process must fail on a *connection* error and never on a refusal — proving the
refusals ran first and that the earlier checks were genuinely satisfied rather
than skipped. Without that check, a passing refusal suite would be equally
consistent with "the config is wrong in a way that exits early", which is the
vacuous-guard shape this repo keeps finding.

### 5.2 The prod-config run

`DEE_ENV=prod` with everything correct. The obstacle is that prod refuses SQLite
and this machine has no Postgres, so the run that boots into a serving state
**cannot be `env=prod` here** — that is a real limit and §0.4 records it rather
than papering over it. The smoke therefore has two phases: the eight refusals
above (which need only the process to *exit*, so SQLite is fine), and a serving
phase at `env=staging` with every other prod value set — `secure` cookies,
`samesite=lax`, real SMTP, rate limits on, sweep enabled.

**The gap is named in the smoke's own output**, not just here: the serving phase
prints that it is `staging` and that Postgres + `env=prod` are covered by CI.
A smoke that silently proves less than its name implies is the "check whose name
claims more than its assertion makes" defect that hid a real bug for an afternoon
in Phase B.

### 5.3 A local SMTP sink — `SMTPEmail`'s first real delivery

`app/services/email.py`'s own docstring:

> *"This also closes a standing gap: S7.1's L2 contact-control assurance ships,
> is tested, and has **NEVER delivered an OTP to a human**."*

It still has not delivered to anything. `SMTPEmail` is selected by config that no
test selects, because selecting it means opening a socket. The smoke stands up a
**minimal SMTP sink on `localhost`** (a plain socket server speaking enough of
RFC 5321 to accept one message: `EHLO`/`MAIL`/`RCPT`/`DATA`/`QUIT`, with
`DEE_EMAIL_SMTP_STARTTLS=false`), points `email_provider=smtp` at it, and drives
a **complete login**: request a code, read it out of the delivered message, verify
it, land an authenticated session.

No new dependency: `aiosmtpd` is not in `requirements.txt` and adding a package
to production requirements to support a smoke is the wrong trade. The sink is
~60 lines in the smoke script and exists only there.

What this actually buys: the first evidence that `SMTPEmail.send` composes a
message a mail server accepts, that `EmailSendFailed` is not raised on the happy
path, and that the OTP body a real recipient receives contains a usable code. All
three are currently believed, not known.

### 5.4 The rest

- The UI is served at `/ui` **same origin**, and the browser check's driver runs
  against it — CDP, real Chrome, a real login, one screen driven end to end. The
  point is that the cookie and CSRF path works in the posture that will ship,
  which §2.1 established has never been true before.
- `python -m app.retention.sweep` preview and `--apply`, asserting the last-line
  JSON contract and the exit codes.
- `/metrics` responds and carries the route-template labels.
- `GET /` returns an `endpoints` list that matches the live route table (§6).

### 5.5 Regression set

The nineteen existing smokes stay green. `smoke_s85_outcome`,
`check_ui_screening_browser.py` and `check_ui_screening_contract.py` are the ones
genuinely at risk, because §2 moves the cookie posture and `api.js`'s base URL
underneath them — so they are re-run, and the browser check is re-pointed at the
same-origin UI rather than left proving the old arrangement.

---

## 6. `GET /`'s `endpoints` list, derived at last

Carried forward from S8.3 Phase A, Phase B and the S8.5 outcome sprint, each time
with the same correct reasoning: patching in the missing entries by hand would
make an unmaintained list look maintained. It is now stale by every `/screening/*`
route, `/metrics`, and all seven S8.3 Phase B routes.

**The real fix, named in `app/main.py:192-194`, is to derive it from the route
table**, which is generated from the code and is the authority. This is the
sprint whose subject is "the deployable surface tells the truth about itself", so
it is the right sprint and there will not be a better one.

Shape: derive from the live route table, with the filter written as an explicit
rule rather than a taste judgement — **every `APIRoute`, excluding FastAPI's own
documentation paths (`/docs`, `/docs/oauth2-redirect`, `/redoc`,
`/openapi.json`), `/` itself, and any `Mount`.** Nothing else is excluded; in
particular the admin plane is *included*, because the list has always advertised
admin routes and hiding them would be security by obscurity on a plane that is
already credential-gated.

The test that pins it does not re-implement the filter — that would be a second
derivation agreeing with the first by construction, which is the
`SweepTarget.knob` test the Phase B plan correctly deleted. It asserts the
*consequence*: a route added to the app appears in `GET /`, and a documentation
path does not. The literal array is deleted, not commented out.

---

## 7. `DEPLOY.md` — the go-live checklist, machine-checked

A new root document, in the `OPERATING.md` register: written for whoever runs
this for a paying customer, complete enough that go-live is a checklist rather
than a recollection.

Contents: every `DEE_*` variable with its value and why; the eight boot refusals
as a pre-flight table (each one is a thing the checklist must satisfy anyway);
`rate_limit_trusted_proxy_hops: 1` behind a proxy, with `OPERATING.md` §3's
failure mode quoted — set it wrong and every caller shares one bucket, which
looks exactly like an attack; `vectorstore_backend: memory` unless a volume is
mounted; Postgres; the retention cron (§4); the SMTP credential; the CORS entry
that is now usually empty (§2.3).

**And the IBM IP / outside-activity check, as a blocking line item** — not
because it is technical, but because `DEPLOY.md` is now the document a future
session opens when the user says "go live", and GTM §8.3's warning is
materially worse if it is retrofitted after a customer signs. It has no better
home.

### 7.1 The checklist is machine-checked

A runbook that lists a variable the code does not read, or omits one it requires,
is the `GET /` endpoints defect wearing a different hat. A test asserts every
`DEE_*` name in `DEPLOY.md` resolves to a real `Settings` field, and that every
setting the eight refusals read is named in `DEPLOY.md`. Both directions, for the
same reason `tests/test_retention_plan.py` asserts set equality both ways.

---

## 8. Explicitly out of scope

- **The deploy** (§0.1). No Railway project, service, database, domain, or
  variable is created. Read-only Railway calls made while writing this spec
  (`whoami`, `list_projects`) established that the `veritas` project exists with
  **zero services**; nothing was changed.
- **An in-process scheduler** (§4).
- **A scraper, dashboards, alerting.** `OPERATING.md` §11 defers these to
  "deploy-time", and with no deploy there is nothing to point them at. The
  format is standard and the endpoint exists.
- **HTTPS termination / certificates.** The platform's job wherever this
  eventually runs; nothing in the app changes for it beyond `session_cookie_
  secure`, which is already refused when false in prod.
- **Multi-worker / replica configuration.** One process is correct until there
  is load to measure, and the two things that would break under replicas are
  already handled: rate-limit counters are in the database (S8.3 Phase A) and
  the sweep is external (§4).
- **The six "byte-identical 404-vs-absence" claims** in `SCREENING.md` and
  `TENANCY.md`, carried since S8.3 Phase A. They are documentation accuracy in
  subsystems this sprint does not touch, and folding them in here would make the
  branch's diff harder to review for no gain. They stay on the carried list.

---

## 9. Success criteria

1. `pytest -q` green, ahead of 1812.
2. `scripts/smoke_s86.py` green, including all eight refusals as process exits
   and a complete login delivered over a real SMTP conversation.
3. All nineteen prior smokes green, plus the UI binding, contract and browser
   checks re-run against the **same-origin** posture.
4. The route-table guard fails when a second mount is added — demonstrated, not
   asserted.
5. `GET /` derives its endpoint list; the literal array is gone.
6. `DEPLOY.md` exists and its variables are machine-checked against `Settings`.
7. **No cloud resource exists that did not exist before the branch.**
