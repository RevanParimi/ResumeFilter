# S8.2 — Identity & access (design)

**Date:** 2026-08-02
**Sprint:** S8.2, the second sprint of PI-8 (launch readiness).
**Status:** Design approved by the user, 2026-08-02. Implementation plan follows.
**Baseline:** `main` at `ec560a0`, 1200 tests green, S8.1 merged.
**Read order:** `docs/ROADMAP.md` "Next action" →
`2026-08-01-pi8-launch-readiness-design.md` (§4 auth architecture, §5.2) → this.

**The sprint's question:** *can a real org and a real candidate get in without an
operator touching the database?*

---

## 0. Decisions taken with the user for this sprint

Taken 2026-08-02, before any code. Two of them close open questions PI-8 §12
left for the sprint specs; two are new and are the ones that could have been
guessed wrong expensively.

| # | Decision | Rejected | Why |
|---|---|---|---|
| 0.1 | **PI-8 is re-sequenced: S8.2 → S8.4 → UI → integrate → S8.3 → deploy.** Sprint IDs stay stable; only the execution order moves. | keep S8.2 → S8.3 → S8.4 | The UI is now built *after* S8.4 ships real endpoints instead of in parallel against stubs, so it is designed against working contracts. It also puts the wedge demo mid-PI, which is the mitigation GTM §7 named for the whole-platform scope the user chose. S8.3 still lands before the deploy, because the deploy is last now. |
| 0.2 | **S8.2 does NOT pin S8.4's contracts.** PI-8 §5.5 is superseded by 0.1. | commit S8.4 Pydantic schemas + `501` handlers | §5.5 existed only because the UI was to be designed *in parallel* against a moving target. Sequentially, pinning a contract one sprint before its implementation buys nothing and costs a sync burden. S8.2 publishes OpenAPI for what it actually ships; S8.4 publishes its own. |
| 0.3 | **`admin_users` rides S8.2** (PI-8 §12's open question, and §0.5's "most trimmable item"). | cut it; defer to S8.3 | S8.1 made admin fail closed on a *shared secret*, which still cannot attribute an action to a person — S7.1's review already caught one audit misattribution. Since this sprint builds `auth_sessions` + OTP login anyway, operator accounts are a third principal on machinery already being written, not a separate subsystem. Deferring to S8.3 would mean doing §2's regression work twice. |
| 0.4 | **Candidate self-registration CLAIMS an existing candidate record** by email OTP against `candidates.email_hash`, rather than always creating a new row. | always create a fresh candidate; require an operator to link | §6.2. This is the most security-consequential line in the sprint and is stated loudly for that reason. |
| 0.5 | **Session-mode coverage is one resolver + a route-table guard + targeted twins**, not PI-8 §9's literal "every authorization test gains a session-mode twin". | hand-write ~33 files of twins | §2. Same guarantee, a fraction of the code, and — unlike twins — it also covers routes that do not exist yet. |
| 0.6 | **No rate limiting in S8.2.** It stays S8.3's. | pull the login limiter forward | OTP signup/login is a brute-force surface and it will exist unlimited for two sprints. That is acceptable **only because 0.1 moved the deploy to last**, so nothing is publicly reachable in the window. Per-challenge attempt caps and cooldowns still apply (§5); it is the per-email / per-IP *spraying* limits that wait. Recorded as a dated, accepted gap rather than an oversight. |

## 1. What this sprint is, in one paragraph

Today every principal in the system is a long-lived header key that an operator
mints by hand: `X-API-Key` is a shared secret, `X-Org-Key` is minted through the
admin plane, `X-Candidate-Key` is minted through the admin plane. A browser has
no way to obtain any of them and no human identity behind any of them. S8.2 adds
the second, human way in — **email-OTP login issuing an opaque, revocable,
server-side session carried in an httpOnly cookie** — across all three planes,
plus the self-onboarding paths (gap-analysis v2 blockers 4 and 5) that let an org
and a candidate get in with no operator at all, plus the CORS and CSRF layers a
separately-hosted browser client requires. Header keys are untouched and stay
first-class: browsers get cookies, machines get keys (PI-8 decision 0.4).

## 2. The one-entry-point problem, and the structural answer

PI-8 §4.7 is the highest-risk sentence in the PI: *sessions change how a
principal is established and nothing about what it may do.* The reason it is
high-risk is measured, not theoretical — **a rule applied at one entry point and
not the other has shipped as a real defect in S7.1, S7.2 and S7.3**, and every
one of those three whole-branch reviews found it independently.

### 2.1 The seam today

Three sibling dependencies in [`app/api/routes.py:78-114`](../../../app/api/routes.py#L78-L114),
each reading its own header and each the sole gate for its plane:

```python
async def require_api_key(request, x_api_key = Header(default=None)) -> None: ...
async def require_org(request, x_org_key = Header(default=None)) -> str: ...
async def require_candidate(request, x_candidate_key = Header(default=None)) -> str: ...
```

The naive implementation of sessions adds a *fourth* way to establish a
principal, then relies on every current and future route remembering to accept
both. That is the failure mode, restated as a plan.

### 2.2 One resolver per plane

The three names stay — every route keeps depending on exactly what it depends on
today — and each becomes a thin call into a single service-layer resolver:

```python
async def require_candidate(request, ...) -> str:
    return (await resolve_principal(request, kind=PrincipalKind.CANDIDATE)).candidate_id
```

`AuthService.resolve_principal` tries the session cookie first, then falls back
to the plane's header key, and returns a `Principal`. **Return types do not
change**: handlers still receive `candidate_id: str` / `org_id: str`, so no
handler is edited and every existing authorization test now executes *through*
the new code path rather than around it.

`Principal` carries everything a downstream gate or audit line could need, and
nothing it should have to re-derive:

```python
class Principal(BaseModel):
    kind: PrincipalKind                  # CANDIDATE | ORG | ADMIN
    via: PrincipalVia                    # SESSION | KEY   <- CSRF reads this (§4.2)
    candidate_id: str | None = None
    org_id: str | None = None            # for ORG, resolved via org_user.organization_id
    org_user_id: str | None = None       # None when established by X-Org-Key
    admin_user_id: str | None = None     # None when established by the shared X-API-Key
    session_id: str | None = None
```

`org_user_id` / `admin_user_id` being `None` is exactly what distinguishes a
machine caller from a named human, which is what makes §6.3's attribution work.

The consequence worth stating plainly: after §2.2, an existing header-key test
such as "candidate B gets 404 for candidate A's consents" already covers every
line a cookie request would execute *after* the principal is established. The
404 logic is literally shared code. A hand-written cookie twin of it re-tests
what is already covered.

### 2.3 What genuinely differs is per-resolver, not per-route

The one thing a twin really checks is whether the cookie path resolves the right
person and refuses the wrong one. That lives in `resolve_principal`, and there
are **three** of those, not sixty-three routes. So the resolvers are tested hard
and directly: cookie vs header, revoked, absolutely expired, idle-timed-out,
wrong principal kind, a session whose subject was erased, and both credentials
present at once (§4.2).

### 2.4 The route-table guard — the part that holds for code not yet written

A structural test walks the FastAPI route table and asserts that every
non-public route establishes its principal through one of the sanctioned
resolvers:

```python
RESOLVERS = {require_api_key, require_org, require_candidate, require_any_principal}

for route in app.routes:
    if route.path in PUBLIC_PATHS:
        continue
    assert _dependencies(route) & RESOLVERS
```

**`require_any_principal` is the fourth resolver and it is not a loophole.** The
session-lifecycle routes in §6.4 (`/auth/me`, `/auth/logout`, `/auth/sessions`,
`/auth/sessions/{id}/revoke`) are genuinely cross-plane: a candidate, an org user
and an operator all need to see and revoke their own sessions through one route.
Without a name for that, those four routes would either need three copies each or
would sit outside the guard — and a route outside the guard is the whole problem.
It resolves a **session only** (never a header key, since a header key has no
session to list or revoke) and it is the *only* resolver permitted on those four
paths.

Add `POST /candidates/batch` in S8.4 with hand-rolled auth and **this test fails
the moment the route is added.** A twin suite cannot do that, because it does not
know the route exists.

This is not a new pattern in this repo — it is the metadata drift / index /
FK-ondelete / nullability guard applied to authorization. That guard does not
hand-write per-column assertions per table; it walks the metadata and asserts
every table conforms, which is exactly why it caught a real migration-vs-ORM
drift during S7.1 without anyone remembering to extend it.

`PUBLIC_PATHS` is an explicit allowlist (`/`, `/healthz`, `/docs`, `/openapi.json`,
and the `POST /auth/*` signup/login/verify routes, which by definition precede a
principal). **Adding a path to that allowlist is the reviewable act** — the guard
converts "someone forgot a gate" into "someone widened a named list."

### 2.5 The twins that are still worth hand-writing

Six, where authorization means something *beyond* identity resolution and which
therefore reach interactions the resolver tests do not: cross-candidate isolation
(404, indistinguishable), a consent-gated org read, a revoked session refused
immediately, an erased candidate's sessions dying with them, absolute expiry, and
idle timeout.

## 3. Data model — migration `0017_auth_identity`

Four tables, all in the main database, all Alembic, all Postgres-shaped.

| Table | Columns (beyond `id`) | FKs | Erasure |
|---|---|---|---|
| `org_users` | `organization_id`, `email_hash`, `role`, `created_at`, `disabled_at?` | `organization_id` → `organizations` **CASCADE** | dies with the org |
| `admin_users` | `email_hash`, `label`, `created_at`, `disabled_at?` | none | operators are not data principals in the DPDP sense |
| `auth_sessions` | `candidate_id?`, `org_user_id?`, `admin_user_id?`, `token_hash`, `issued_at`, `expires_at`, `last_seen_at`, `revoked_at?`, `user_agent?`, `ip_hash?` | all three → **CASCADE**, plus a CHECK that exactly one is non-null | dies with any of its three possible principals |
| `login_challenges` | `email_hash`, `purpose`, `plane`, `code_hash`, `payload?`, `expires_at`, `attempts`, `last_sent_at`, `cooldown_until?` | none (no principal exists at signup time) | **DELETED on consume**, plus §8.3 |

Notes that are decisions, not details:

- **The exclusive arc on `auth_sessions` is three nullable FKs, not a polymorphic
  `subject_type`+`subject_id`.** PI-8 §4.2 settled this: a polymorphic id column
  cannot carry a foreign key, so erasure would stop cascading, silently breaking
  a guarantee that has held for eight PIs. `DELETE /portal/me` then kills every
  session of that candidate for free, exactly as S7.3's interview tables did.
- **`org_users.role`** is `owner | member`. The invite endpoints are a non-goal
  (§12), but the column ships now so adding them later needs no migration. This
  is the one piece of deliberate forward-provision in the sprint and it is cheap:
  a role column on a users table is near-certain, not speculative.
- **`login_challenges.payload`** is a small JSON column carrying signup-only data
  that must survive the OTP round trip — today just the organization name. It is
  never read on a `login` purpose.
- **`token_hash` is sha256 and the plaintext is returned once, never stored**,
  mirroring `issue_access_key` ([`app/candidates/store.py:279`](../../../app/candidates/store.py#L279)).
- **Expiry — absolute and idle — is computed at read time, never written by a
  job.** The S7.1 `effective_status` precedent, for the same reason: no scheduler
  exists, and a stored `expired` that nothing corrects is a lie.
- **`last_seen_at` is written at most once per `session_last_seen_write_seconds`
  (default 60), not on every request.** Idle timeout needs it, but a naive
  implementation turns every authenticated `GET` into a write — which on Postgres
  is a row lock and a WAL entry per request, on the hottest path in the system.
  The staleness this admits is bounded by the knob and is an order of magnitude
  below the 120-minute idle window, so it cannot change a timeout decision.

The metadata-wide drift / index / FK-ondelete / nullability guards extend to all
four tables.

## 4. Transport — cookie, plus CSRF

### 4.1 The cookies

On a successful verify the server sets two cookies:

| Cookie | httpOnly | Contents |
|---|---|---|
| `dee_session` | **yes** | the opaque session token |
| `dee_csrf` | no (the UI must read it) | the double-submit CSRF token |

`Secure` + `SameSite=None` in any deployed environment, because the UI is
separately hosted and every request is therefore cross-site — `Lax` would drop
the cookie entirely (PI-8 §4.3). Mutating requests (`POST`/`PUT`/`PATCH`/
`DELETE`) authenticated **by session** must echo the CSRF token in
`X-CSRF-Token`, compared with `hmac.compare_digest`.

`SameSite=None` mandates `Secure`, which mandates HTTPS, which the key-less
localhost smoke does not have. So both are config (§9) and both are covered by a
new boot refusal (§4.3) rather than by trust.

### 4.2 The CSRF exemption trap

Machine clients carry no cookie and need no CSRF token. **The exemption must key
on "this request was authenticated by a header key", not on "a header was
present."** Otherwise a browser carrying a valid session cookie plus an
attacker-supplied `X-Org-Key` header skips CSRF entirely — the house fail-open
shape in miniature, and precisely the class of bug §2 exists to prevent.

Concretely, `resolve_principal` returns *how* the principal was established, and
CSRF enforcement reads that field. A request presenting **both** a session cookie
and a header key resolves as **session** (the stronger requirement wins) and is
CSRF-checked. This is an explicit test, not a comment.

### 4.3 Boot refusals gained

`app/core/boot.py::verify_launch_config` is the natural home for launch-time
refusals, and the roadmap already nominated CORS as the next candidate. Three
are added, all `env == "prod"`:

1. `session_cookie_secure` is False → refuse. A session cookie over plain HTTP
   is a session token in the clear.
2. `cors_allowed_origins` contains `"*"` → refuse. Never a wildcard with
   credentials.
3. `email_provider == "capture"` → refuse. `CaptureEmail` writes OTP codes to a
   file; in production that is an OTP leak wearing a test harness's clothes.

## 5. OTP mechanics — reused, not rewritten

The pure functions in [`app/verification/otp.py`](../../../app/verification/otp.py)
— `generate_code`, `hash_code`, `is_challenge_expired`, `attempts_exhausted`,
`cooldown_active` — are already pure, clock-injected, RNG-injected and tested.
S8.2 reuses **the functions, not the table**: `verification_challenges` is
candidate-scoped *identity* verification and stays that way, while
`login_challenges` is authentication and belongs to a principal that may not
exist yet.

Cooldown and attempt limits are scoped to **`email_hash` + `purpose` + `plane`**,
applying S7.1's own review finding verbatim: *a limit scoped to a row that the
flow re-mints limits nothing.* (PI-8 §4.4 wrote this as `email_hash` + `purpose`;
`plane` is added because one address can legitimately be both a candidate and an
org user, and collapsing those would let activity on one plane lock the other.) Rows are deleted on consume or supersession —
short-TTL secret material is hygiene, not a retention policy, and is a deliberate
exception to the S8.3 sweep.

## 6. The flows

### 6.1 Org self-onboard (blocker 5)

```
POST /auth/org/signup   {email, organization_name}   -> 202 always
POST /auth/org/login    {email}                      -> 202 always
POST /auth/org/verify   {email, code}                -> 200 + cookies
```

- **`202` always, on both signup and login, regardless of whether the email is
  known.** No account enumeration: an unknown login email mints nothing and sends
  nothing, and the response is indistinguishable from success.
- **Signup with an already-registered email mints nothing and sends nothing.**
  Deliberately not "silently send a login code instead" — that is the kind of
  cleverness that becomes a confused-deputy bug. The UI's "check your email"
  screen offers a "already have an account? log in" path.
- On `verify` of a `signup` challenge, the organization **and** its first
  `org_user` (`role="owner"`) are created in one transaction, then the challenge
  row is deleted and a session is issued. An org therefore never exists in a
  half-created state, and an unverified email never creates one.
- The org's `X-Org-Key` is unaffected and is still mintable through the admin
  plane. The two modes coexist permanently (PI-8 decision 0.4).

### 6.2 Candidate self-registration (blocker 4) — the claim decision

```
POST /auth/candidate/signup {email}         -> 202 always
POST /auth/candidate/login  {email}         -> 202 always
POST /auth/candidate/verify {email, code}   -> 200 + cookies
```

**`candidates` rows already exist for people who never signed up.** They are
created when an org uploads a resume, and deduped on `email_hash` (S1.1). So
self-registration must answer: what happens when the email hashes to a candidate
that already exists?

**Decision 0.4: it attaches to that candidate.** Not a duplicate row, not an
operator-mediated link. The reasoning is S7.1's destination-binding argument
applied one level up:

- The candidate supplies the email; the platform normalizes and hashes it and
  matches against `candidates.email_hash`. The raw value stays transient.
- A completed OTP proves control of that mailbox — which is exactly what S7.1's
  L2 `otp_email` assurance already means in this system.
- Under DPDP, the data principal has a right of access to the record *about
  them*. Refusing to connect a verified mailbox to the record built from their
  own resume would make the portal's access, correction and erasure rights
  unreachable for every candidate an org uploaded — which is all of them.

No match → a new bare `candidates` row is created with the `email_hash` set.

**The risk, stated rather than buried:** whoever controls that mailbox gets the
candidate's data. That is the same trust boundary as every OTP login on the
internet and the same one S7.1 already shipped for L2, but it is worth writing
down because the blast radius here is a full depth report, not a login.

**Explicitly out of scope:** self-registration grants no identity assurance level
by itself. Signing up does not silently mint an S7.1 `otp_email` verification —
the ladder stays where it is, and fusing "logged in" with "verified" would repeat
S7.2's two-ladders mistake.

### 6.3 Admin operator accounts (decision 0.3)

```
POST /admin/users            {email, label}   -> behind the existing X-API-Key
GET  /admin/users
DELETE /admin/users/{id}
POST /auth/admin/login       {email}          -> 202 always
POST /auth/admin/verify      {email, code}    -> 200 + cookies
```

**Bootstrap reuses the shared key** — no boot-time side effects, no
`DEE_ADMIN_BOOTSTRAP_EMAIL`, no chicken-and-egg. `X-API-Key` already exists and
already fails closed after S8.1, so it becomes the machine/root credential and
operator accounts become the human one. That is decision 0.4 applied to the third
plane. There is no admin *signup*: operators are created by an existing operator.

**The attribution win, which is the whole point of 0.3:** `resolve_principal`
returns a `Principal` carrying `admin_user_id` when the request came from an
operator session, and `None` when it came from the shared key. Audit entries can
then distinguish a named operator from an unattributable machine action, closing
the gap S7.1's review found where an operator-recorded manual review was audited
as if the candidate had done it.

### 6.4 Session lifecycle — all three planes

```
GET  /auth/me                      -> principal kind + id (what the UI calls on load)
POST /auth/logout                  -> revoke the current session
GET  /auth/sessions                -> the caller's own active sessions
POST /auth/sessions/{id}/revoke    -> revoke one of the caller's own
```

These four are the cross-plane routes, and they are the **only** users of
`require_any_principal` (§2.4). They resolve a session and never a header key: a
machine holding `X-Org-Key` has no session to list, and `POST /auth/logout` from
a key-authenticated caller is meaningless, so it 401s rather than pretending to
succeed.

Ownership is structural: every one of these resolves the principal from the
credential and never from a path or body param. A session id belonging to another
principal is an indistinguishable 404 — the S6.4 rule, unchanged.

## 7. CORS

A config-driven allowlist `cors_allowed_origins`, **defaulting to empty**
(fail-closed), with credentials enabled and never `"*"`. Browsers already forbid
`"*"` with credentials, but relying on that as the guard would leave a defect
waiting for someone to "fix" the console error — so it is refused explicitly at
boot in prod (§4.3) and tested directly.

## 8. DPDP posture

- **No new `ConsentPurpose`.** Authentication is not a disclosure; it is how a
  data principal proves they are the subject. S6.4's argument for the portal,
  applied to sessions. (PI-8 §7.)
- **`MyData` gains `sessions: list[SessionView]`** so a candidate can see and
  revoke their own devices — a transparency right consistent with the access log.
- **`ip_hash`, never a raw IP.** The precedent is `email_hash`/`phone_hash` in
  `candidates`: store what identifies, not what re-identifies.
- **Session create / refuse / revoke are audited** where a candidate is the
  subject, so they appear in `GET /portal/access-log`. Org-user and admin session
  events have no candidate subject and are structured-logged only — the ledger's
  audit table is candidate-scoped by design and is not being widened here.

### 8.1 The erasure hole `login_challenges` would otherwise open

`login_challenges` has **no FK** (§3) — at signup time no principal exists — so
it cannot cascade. A candidate who erases themselves while a challenge is
outstanding would leave a row keyed by their `email_hash` behind.

**`DELETE /portal/me` therefore deletes `login_challenges` by `email_hash`
explicitly**, inside the same erasure path. This is the one place in the sprint
where a guarantee is *not* structural, so it gets a direct test rather than a
convention — the S8.1 lesson about conventions applied the moment it recurs.

Abandoned (never-consumed, expired) challenges are deleted opportunistically the
next time the same `email_hash` requests a code. No scheduler is invented here;
the mechanical sweep is still S8.3's.

## 9. Config changes

```yaml
# --- Auth sessions + login (PI-8, S8.2) --------------------------------------
session_ttl_minutes: 720
session_idle_timeout_minutes: 120
session_token_bytes: 32
session_last_seen_write_seconds: 60   # throttles the per-request write (§3)
session_cookie_name: "dee_session"
session_cookie_secure: true       # false ONLY for localhost; refused in prod
session_cookie_samesite: "none"   # none | lax | strict
csrf_cookie_name: "dee_csrf"
csrf_token_bytes: 32
login_otp_length: 6
login_otp_ttl_seconds: 600
login_otp_max_attempts: 5
login_otp_cooldown_seconds: 60
cors_allowed_origins: []          # fail-closed; never "*"

# --- Email seam (PI-8, S8.2) --------------------------------------------------
email_provider: "null"            # null | smtp | capture — capture NEVER by fallback
email_from: ""
email_smtp_host: ""
email_smtp_port: 587
email_smtp_starttls: true
email_capture_path: ""            # where CaptureEmail writes; smoke reads this
```

Secrets stay in `.env` under `DEE_*`: `DEE_EMAIL_SMTP_USER`,
`DEE_EMAIL_SMTP_PASSWORD`. The rate-limit knobs listed in PI-8 §8 are **not**
added here — they ship with the limiter in S8.3 (decision 0.6), because a knob
that throttles nothing is worse than an absent one.

**Hygiene fix carried in this sprint:** `api_auth_key`'s field comment in
[`app/core/config.py:361`](../../../app/core/config.py#L361) still reads
"Empty (default) = auth disabled (local/dev)". S8.1 made that false. It is
corrected here, because a stale comment describing a fail-open default is how the
next reader re-derives the wrong mental model.

## 10. Email seam

New `app/services/email.py`, shaped exactly like `llm.py` and `speech.py` —
`EmailClient` / `SMTPEmail` / `NullEmail` / `CaptureEmail` / `build_email`.

- **`NullEmail` refuses.** With no provider configured, signup and login return
  `503 email_unavailable` rather than appearing to succeed. This is `NullSpeech`'s
  posture from S7.3, and it is what lets the key-less smoke assert something
  honest instead of pretending.
- **`CaptureEmail` is selected only by explicit config, never by fallback.** It
  appends JSON lines to `email_capture_path`, which is how the smoke drives a
  real login end to end with no provider. Silent degradation into it would be
  PI-8 §1's bug again, so `build_email` returns `NullEmail` — not `CaptureEmail`
  — whenever `email_provider` is unrecognized, and prod refuses to boot with it
  (§4.3).
- It also closes a standing gap: **S7.1's L2 contact-control assurance ships, is
  tested, and has never delivered an OTP to a human**, because `NullNotifier`
  logs neither code nor destination. `SMTPEmail` gives it a real delivery path
  for the first time since 2026-07-31.

## 11. Testing and smoke

Fully offline, as always: `CaptureEmail` plus an injected clock make the entire
OTP path deterministic — no network, no provider, no sleeping.

**Adversarial cases that must be tests, not hopes:**

- an expired OTP, a reused OTP and an over-attempted OTP all refuse;
- cooldown is scoped to `email_hash`+`purpose`+`plane`, **not** to a row;
- signup and login return `202` for unknown and known emails alike (no
  enumeration);
- a revoked session 401s immediately; an absolutely-expired and an
  idle-timed-out session both 401;
- a session for candidate A cannot read candidate B (404, indistinguishable);
- an erased candidate's sessions die with them, and their `login_challenges` are
  gone (§8.1);
- a mutating session request with no CSRF token is refused, and one presenting
  **both** a session cookie and a header key is still CSRF-checked (§4.2);
- CORS rejects an unlisted origin;
- prod + insecure cookie, prod + `"*"` origin, and prod + `capture` email each
  **refuse to boot** (§4.3);
- the route-table guard (§2.4) and the three resolver suites (§2.3).

### 11.1 `scripts/smoke_s82.py` — key-less, uvicorn, exit 0

Runs with `email_provider=capture`, `session_cookie_secure=false`,
`session_cookie_samesite=lax` against `http://localhost`, and reads codes from
`email_capture_path`:

org signup → code from the capture file → verify → session cookie set →
authenticated org call succeeds with **no `X-Org-Key` at all** → the same call
with the cookie but no CSRF token is refused → candidate signs up against an
email already on an uploaded resume → **verify attaches to the existing
candidate, and `/portal/me` shows the resume that org uploaded** → `/auth/sessions`
lists one → second login from a "different device" → two sessions → revoke the
first → it 401s and the second still works → admin mints an operator with
`X-API-Key` → operator logs in by OTP → admin call succeeds by session →
`DELETE /portal/me` → every candidate session 401s → unknown-email login still
returns 202.

That last check is small and easy to skip; it is the one that proves no account
enumeration, which is the kind of thing that is only ever noticed by an attacker.

## 12. Non-goals for S8.2

- **Rate limiting** — S8.3 (decision 0.6).
- **Org user invites.** `org_users.role` ships so no migration is needed later,
  but `POST /org/users` does not. A design-partner org runs on one login for the
  demo phase, and the permission model an invite implies is not worth opening
  while three planes are being re-seamed.
- **Passwords, SSO, SAML, OAuth social login** — PI-8 decision 0.3 settles v0.
- **Any UI, HTML, template or JS toolchain in this repo** — PI-8 decision 0.1.
- **Pinning S8.4's contracts** — decision 0.2.
- **Phone/SMS login.** The email seam is the one being built; adding a second
  channel doubles the provider surface for no launch-blocking gain.
- **Granting identity assurance on signup** (§6.2).

## 13. Definition of done

1. An organization signs up, receives a code, logs in, and holds a session
   **without any operator touching the database**.
2. A candidate self-registers against an email already present on an
   org-uploaded resume and **attaches to that existing candidate record**.
3. An operator account is created through the admin plane and logs in by OTP;
   admin actions are attributable to a person.
4. Every existing header-key authorization test still passes, unmodified,
   through the new resolver.
5. The route-table guard passes and fails loudly for a route that establishes a
   principal any other way.
6. `DELETE /portal/me` kills every session and every login challenge of that
   candidate.
7. Prod refuses to boot with an insecure session cookie, a `"*"` CORS origin, or
   the capture email provider.
8. `pytest -q` green (1200 + new); `scripts/smoke_s82.py` exit 0, key-less; the
   S8.1 and earlier regression smokes still green.

## 14. Follow-ups this sprint deliberately leaves open

- Org user invites + the permission model behind them (§12).
- Rate limiting on the OTP surface — **S8.3, and it is the only thing standing
  between this sprint and a brute-forceable login** once the deploy happens
  (decision 0.6).
- Widening the ledger audit table so org-user and admin session events are
  auditable rather than merely logged (§8).
- Session-mode twins beyond the six in §2.5, if the resolver ever grows a
  plane-specific branch.
- `verification_challenges` and `login_challenges` are two tables running the
  same pure OTP mechanics for different purposes. Correct today; worth a look if
  a third appears.
