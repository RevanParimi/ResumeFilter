# UI ⇄ API wiring — design

**Date:** 2026-08-03 · **Status:** approved, ready to plan
**Inputs:** `UI.md` (client contract) · `UI-Spec.md` (screen inventory + gap list)
· `AUTH.md` · `docs/ROADMAP.md` "Current state" (the session handoff)

This is not a sprint. It is the integration step PI-8 was re-sequenced around:
`S8.2 → S8.4 → UI → integrate → S8.3 → deploy`. The UI exists (built externally
via claude.ai/design, mock data only); the API exists (83 routes, three auth
planes). Nothing connects them.

---

## 0. Decisions

### 0.1 The wiring lives in a new `frontend/api.js`, not inline

`Veritas.dc.html` is a **design artifact, not a build system** — no npm, no
bundler, no module imports. PI-8 decision 0.1 says this repo ships no HTML/JS
toolchain so CI stays Python-only; `frontend/` is a deliberate departure and
**does not enter CI**.

The file is 1838 lines, of which ~800 are a single `<script data-dc-script>`
logic class. Putting fetch/CSRF/error-taxonomy logic inside that block would
bury the one part of this work that has real invariants inside the one part
that is pure presentation.

So: a new plain `frontend/api.js` defining `window.VeritasAPI`, loaded by **one
added line** in `<head>` beside the existing `<script src="./support.js">`.

- No `import`/`export` — the runtime evaluates the logic class through
  `new Function("DCLogic","StreamableLogic","React", src)`, a function scope,
  not a module. A global is the only seam that works.
- **Rejected — inline everything:** one 138 KB file where the auth invariants
  are unreviewable and a re-export from claude.ai/design silently reverts them.
- **Rejected — a bundler/npm:** directly contradicts decision 0.1 and buys
  nothing a `<script>` tag does not.

### 0.2 Base URL is configurable and *visible*

Resolution order: `?api=<url>` query param → `localStorage.veritas_api_base` →
`http://localhost:8000`.

The resolved value renders in the rail footer. A demo that cannot tell which
backend it is talking to is a demo that will eventually show mock data to a
buyer and call it real.

### 0.3 `403` forks on a **measured** detail string, not a guess

The brief flagged that `403` carries two unrelated meanings. Both strings are
now read off the code rather than remembered:

| Source | Detail | Meaning |
|---|---|---|
| `app/api/routes.py:122` | `missing or invalid CSRF token` | the double-submit check failed |
| `app/ledger/consent.py:58` | `no active consent for purpose '<purpose>'` | the candidate has not shared this |

`api.js` classifies: `403` whose `detail` matches `/csrf/i` → `kind:"csrf"`;
**every other** `403` → `kind:"consent"`. The default is deliberately `consent`,
because that is the *normal* state (UI.md §6) and mislabelling it as an auth
failure would turn an expected empty section into a red error.

### 0.4 Unwired screens keep mock data and say so, on screen

Screens 2/4/5/6 (queue, batch summary, upload, batches) have **no endpoints at
all** and stay mock until S8.4. They gain a visible "sample data" chip.

UI.md §7 is explicit that a confident-looking UI can make an honest backend lie.
An unlabelled mock screening queue beside four live screens is exactly that
failure, and it is the screen the whole GTM rests on. Wired screens drop their
mock constant outright — no fallback-to-mock on error, because a fallback makes
a broken backend look like a working one.

### 0.5 Scope: through roles/comp (user decision, 2026-08-03)

**In:** auth (3 planes, signup/login/verify) · `GET /auth/me` on load ·
portal (`/portal/me`, `/access-log`, `/consents`, revoke, erasure) ·
devices (`/auth/sessions`, revoke, `/auth/logout`) · roles + comp
(`/jobs*`, `/jobs/{id}/board`, `/comp/estimate`).

**Out this pass:** `GET /report/{id}` + outcome, `POST /evaluate`, the operator
console, the interview runner. All are admin-router or may move to the org plane
in S8.4; wiring them now risks an integration rewrite.

### 0.6 `frontend/` enters git; its binaries do not (user decision, 2026-08-03)

Commit the `.dc.html` files, `support.js`, `api.js`, `_ds/`, `PLAN.md`,
`UI-SPEC.md`. Gitignore `frontend/uploads/` (a 659 KB paste screenshot),
`frontend/.thumbnail`, and `tmp_mail.jsonl` (captured OTPs — secret material).

---

## 1. The three preconditions, restated as config

All three default to **broken-for-a-browser**. None is a code change; all live
in a local `.env` and cannot ship (prod refuses to boot with any of them).

```dotenv
DEE_CORS_ALLOWED_ORIGINS=["http://localhost:5173"]   # JSON array; a bare string fails at boot
DEE_SESSION_COOKIE_SECURE=false                      # BOTH, not one —
DEE_SESSION_COOKIE_SAMESITE=lax                      # SameSite=None without Secure is also rejected
DEE_EMAIL_PROVIDER=capture
DEE_EMAIL_CAPTURE_PATH=./tmp_mail.jsonl
DEE_API_AUTH_KEY=<32+ chars>
```

Symptoms if skipped, in the order they bite: CORS kills request #1 while Postman
works fine · the session cookie is silently dropped over http (a `200` with a
`Set-Cookie` that never becomes a cookie, then everything `401`s) · login
returns `503 email_unavailable` with no OTP anywhere.

**Serve over HTTP, never `file://`** — a `file://` origin is `null` and fails
CORS with credentials. `python -m http.server 5173` from `frontend/`.

**First operator** (there is no `/auth/admin/signup`):

```
POST /admin/users  -H "X-API-Key: <key>"  {"email": "...", "label": "dev"}
```

## 2. `api.js` — the contract

One global, `window.VeritasAPI`, with a deliberately small surface.

```
VeritasAPI.base()                      → resolved base URL (0.2)
VeritasAPI.setBase(url)                → persists to localStorage
VeritasAPI.request(method, path, body) → parsed JSON, or throws ApiError
VeritasAPI.get/post/patch/del(...)     → thin wrappers
VeritasAPI.onSessionLost(fn)           → single subscriber, fired on 401
```

Invariants it owns, so no caller can forget them:

1. **`credentials: "include"` on every call, including GETs.** Not a per-call
   option — there is no way to make a call without it.
2. **`X-CSRF-Token` on every `POST`/`PATCH`/`PUT`/`DELETE`**, read from the
   `dee_csrf` cookie at call time (not cached at login — a re-login rotates it).
   Safe methods never send it.
3. **`401` → fire `onSessionLost`, then throw.** Never retried. A retry loop
   against a dead session is exactly what S8.3's absent rate limiter would not
   catch.
4. **Errors are typed, never raw.** `ApiError{status, detail, kind}` where
   `kind ∈ {session_lost, csrf, consent, invalid_code, email_down, network,
   http}`. The UI branches on `kind`, never on a parsed message.

`detail` is read from FastAPI's `{"detail": ...}` body, tolerating a non-JSON
body (a proxy 502 is not JSON) without throwing inside the error path.

## 3. State convention in the logic class

The class is a `DCLogic` subclass: `state`, `setState`, `props`, and a
`renderVals()` returning one flat bag the template binds through `{{ }}`.
`componentDidMount()` exists and is the load hook.

Every remote resource occupies **one** state key holding
`{data, loading, error}`, populated through a single helper:

```js
load = (key, fn) => { ...setState loading → await fn() → data | error... }
```

`renderVals()` stays synchronous and pure over `state`. Async work happens only
in handlers and `componentDidMount`. This keeps the existing architecture rather
than fighting it.

**Boot sequence:** `componentDidMount` → `GET /auth/me` → on `200` set
`plane` from `kind` and route to that plane's landing screen; on `401` show
login. This replaces today's `enterApp()`, which just flips a local flag.

## 4. Screen-by-screen mapping

| Screen | Calls | Notes |
|---|---|---|
| Sign in | `POST /auth/{org,candidate,admin}/{signup,login}` | always `202`; copy already correct. Inputs must be **bound** — today they carry no `value`/`onInput` |
| Enter code | `POST /auth/{plane}/verify` | 6 boxes → one string; `400` → the single `invalid_code` message |
| Portal overview | `GET /portal/me` | `MyData`: profile, resumes, report **refs only**, identity ladder, retention windows |
| Access log | `GET /portal/access-log` | `actor_name` is the resolved org name; `allowed` drives the chip |
| Consents | `GET /portal/consents` · `POST /portal/consents/{id}/revoke` | revoke needs CSRF |
| Delete everything | `DELETE /portal/me` | type-to-confirm already designed; on success → login |
| Devices | `GET /auth/sessions` · `POST /auth/sessions/{id}/revoke` | `current` session cannot revoke itself |
| Sign out | `POST /auth/logout` | then clear state, show login |
| Roles | `GET /jobs` · `GET /jobs/{id}/board` | board = requisition + comp benchmark + top-N match. A `403` here renders the **already-designed** "not shared with you" block |
| Comp | `GET /jobs/{id}/comp` · `POST /comp/estimate` | k-anonymity floor and `k₀` come from the response, not hard-coded |

Unwired, staying mock with a chip: queue · batch summary · upload · batches ·
report detail · instant check · interview runner · operator console.

## 5. What could go wrong, and what catches it

| Risk | Catch |
|---|---|
| CORS/cookie/CSRF misconfigured — the failure mode the handoff warns about three times | §6 scripted run asserts a real cross-origin round trip before any browser work |
| CSRF token cached at login, stale after re-login | read from cookie **at call time** (§2.2); the scripted run re-logins and mutates |
| A `403` rendered as a hard error, hiding a normal consent state | fork on the measured string (0.3), default to `consent` |
| Mock data mistaken for live in a demo | visible per-screen chip (0.4) + visible base URL (0.2) |
| `401` retry loop with no server-side limiter (S8.3 is after this) | `onSessionLost` throws and never retries (§2.3) |
| A re-export from claude.ai/design reverts the wiring | wiring concentrated in `api.js`; the `.dc.html` diff is small and reviewable |

## 6. Verification

No JS toolchain and no CI for `frontend/` (0.1), so verification is explicit:

1. **Scripted cross-origin HTTP run** against live uvicorn with a cookie jar and
   a real `Origin: http://localhost:5173` header, asserting: preflight passes ·
   `202` for known **and** unknown addresses · the OTP lands in the capture file
   · `verify` sets both cookies · `GET /auth/me` round-trips on the cookie alone
   · a mutating call **without** `X-CSRF-Token` is `403` with the CSRF detail ·
   the same call **with** it succeeds · a consent-gated read is `403` with the
   consent detail. This is what proves the contract; the browser only proves the
   binding.
2. **Manual browser pass** at `http://localhost:5173/Veritas.dc.html` through
   every wired screen on all three planes, both themes.
3. **`pytest -q` stays green** — this session touches no `app/` code, so a
   regression would mean something unintended was edited.

## 7. Out of scope, explicitly

Rate limiting (S8.3) · tenancy / the org column (`UI.md` §2.1, unsettled) ·
batch identity (§9 Q3, unsettled) · pagination UI (no cursor exists until S8.4)
· any of the seventeen `UI-Spec.md` gap items · deployment.
