# PI-8 — Launch Readiness (PI-level design)

**Date:** 2026-08-01
**Status:** Design approved by the user. Each S8.x gets its own sprint spec
before it is built; this document fixes the decisions that span sprints.
**Amended 2026-08-02** — see the box below; §5 and §5.5 changed, §12 lost one
open question.
**Read order:** `docs/ROADMAP.md` "Next action" →
`2026-08-01-veritas-gtm-positioning.md` → `2026-08-01-veritas-gap-analysis-v2.md`
§9 → this.

> **AMENDMENT — 2026-08-02, by the user.** PI-8 is **re-sequenced**:
> **S8.2 → S8.4 → UI built externally → integrate → S8.3 → deploy.** Sprint IDs
> are stable identifiers and do not move; only the execution order does. Three
> consequences, all recorded where they bite:
> 1. **§5.5 is superseded.** S8.2 no longer pins S8.4's contracts, because the
>    UI is now built *after* S8.4 ships real endpoints rather than in parallel
>    against stubs.
> 2. **§12's `admin_users` question is CLOSED — it rides S8.2.**
> 3. **The deploy is the last act of the PI**, not part of S8.1. S8.1 shipped
>    deploy-*ready* (`railway.json` + a README `## Deploy` section) and the user
>    deleted the Railway project mid-sprint.
>
> Full reasoning, with rejected alternatives, in
> `2026-08-02-s82-identity-access-design.md` §0.

**PI-8's question:** *what stops a real company onboarding without the operator
hand-holding the database?*

---

## 0. The five decisions this PI rests on

Taken with the user on 2026-08-01, before any code. A wrong guess on any of
these is expensive to unwind, so they are recorded with their rejected
alternatives.

| # | Decision | Rejected | Why |
|---|---|---|---|
| 0.1 | **The UI is built externally** (claude.ai/design) and integrated later. This repo ships **no HTML, no templates, no JS toolchain.** | Jinja2+HTMX in-repo; a React SPA in-repo | User's explicit preference. It also keeps CI Python-only (3.11+3.12) and the `pytest`-plus-smoke discipline intact. The API must therefore be **browser-client-ready**, which is what §4 is about. |
| 0.2 | **Sessions are opaque server-side tokens, not JWT.** | stateless JWT access+refresh | The architecture's whole ethos is revocability + audit. A JWT stays valid after a candidate revokes consent or erases their account, until it expires. That is a **DPDP correctness bug**, not a preference. An opaque row dies with a `DELETE`. |
| 0.3 | **Login is email OTP. No passwords anywhere.** | password + bcrypt + reset flow | Removes the most scope of any call here: no password storage, no reset flow, no strength rules, no breach liability. Reuses `app/verification/otp.py`, already pure and tested. OTP login is the Indian consumer norm and needs no user education. |
| 0.4 | **Two auth modes per plane, permanently.** Browsers get cookie sessions; machines keep header API keys. | migrate everything to sessions | `X-Org-Key` is not legacy — the long-lived key **is** GTM option 3, the API product. Both are first-class and stay. |
| 0.5 | **The admin plane fails CLOSED and gains real operator accounts.** | keep the shared secret | §2. One shared secret cannot attribute an admin action to a person, and S7.1's review already caught one audit misattribution. Operator accounts are the most trimmable item in this PI if it runs long; **fail-closed is not trimmable.** |

## 1. The defect that reorders this PI

[`app/api/routes.py:76-82`](../../../app/api/routes.py#L76-L82):

```python
"""Shared-secret gate (FR-15). No key configured → open (local/dev)."""
expected = _services(request).settings.api_auth_key.get_secret_value()
if expected and x_api_key != expected:
    raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
```

**If `DEE_API_AUTH_KEY` is unset, all 27 admin endpoints are public.** That
includes `POST /candidates/{id}/auth-key` (mints *any* candidate's access key,
which is full impersonation of a data principal) and `POST /ledger/orgs`.

Correct for local dev. **Catastrophic the moment PI-8 does its job and deploys
this**, because the trigger is a forgotten environment variable, not an attack.

It is also the **house bug shape for the fourth time running** — a fail-open
default (v2 §6: S7.1's `start()` treating "not challenge_based" as "complete it
now, VERIFIED"; S7.2's identity route; S7.3's audio path).

**Fix, in S8.1, non-negotiable:** the app **refuses to start** when no admin
credential is configured and the environment is not explicitly declared local.
A missing secret is a boot failure with a loud message, never an open door.
There is no config knob to restore the old behaviour — see §0.5.

### 1.1 The fix is suite-wide, not three lines — measured

Do not plan this as a small change. Measured at `47b5fc3`:

- `api_auth_key` defaults to `SecretStr("")` (`app/core/config.py:361`), so
  **fail-open is the default posture**, not an edge case.
- **`tests/conftest.py` never sets it.** The entire 1175-test suite therefore
  runs in fail-open mode today.
- **7 test files call admin routes with no key at all** and pass *because* of
  the defect.
- 26 smoke scripts likewise assume the open door.

So closing it means: the gate, plus a conftest-level test credential, plus a
shared header helper, plus touching those 7 files and the smokes. Mechanical,
but wide.

**Two planning consequences:**

1. **Do it as the very first task in S8.1**, before Postgres and before the
   report-store rewrite. Any other order means re-touching every file the other
   changes already moved.
2. **The suite passing today is not evidence the gate works.** A test that never
   sends a credential cannot distinguish "authorized" from "unguarded" — which
   is exactly how this survived eight PIs and four branch reviews. The new tests
   must assert the **refusal**, not just the success path.

## 2. Seven gaps the technical audit did not have

Gap-analysis v2 §9 audited the API **as an API**. Nothing had yet audited it as
a *backend for a browser client*, which is what decision 0.1 makes it. The six
in the table below were measured against the tree at `2f0d616`; the seventh
(§2.1) is different in kind — a latent DPDP fragility rather than a UI-backend
gap — and it decided the fold question §12 had left open.

| # | Gap | Evidence | Consequence |
|---|---|---|---|
| 1 | **Admin plane fails open** | §1 | launch-blocking; 27 endpoints |
| 2 | **No CORS anywhere** | the only middleware in `app/main.py:60` is request-ID logging | a separately-hosted UI **cannot call this API at all** |
| 3 | **No batch resume upload** | `POST /candidates` takes one `CandidateCreateRequest` | the wedge demo is "upload 500 resumes" |
| 4 | **No real pagination** | `limit` only, 3 sites, no offset or cursor | a UI listing candidates cannot page |
| 5 | **No email infrastructure** | only `Notifier` Protocol + `NullNotifier` in `app/verification/otp.py` | blocks OTP login **and** — see below |
| 6 | **No password hashing anywhere** | zero `bcrypt`/`argon2`/`passlib` in the tree | moot under decision 0.3, recorded so nobody re-derives it |

**Gap 5 has a consequence worth stating on its own:** S7.1's L2 contact-control
assurance ships, is tested, and **has never delivered an OTP to a human being**,
because `NullNotifier` deliberately logs neither the code nor the destination.
The ladder's second rung has been theoretical since 2026-07-31. S8.2's email
sender closes that at the same time as it enables login.

### 2.1 Cross-database erasure is a convention, not a guarantee — and it decides §12's fold question

Measured at `cd4e660`. **DPDP erasure is currently complete, and nothing
structural makes it so.**

`ReportStore.delete_for_candidate` has exactly **two callers**, both in the route
layer — `app/api/routes.py:354-355` (admin plane) and
`app/api/routes.py:988-989` (candidate portal). Each calls the report store and
*then* `candidates.delete_candidate`. Both remember. Nothing enforces it.

That is verbatim the shape v2 §6 instructs every sprint to hunt: **a rule
enforced at the route rather than the service, duplicated across entry points.**
It shipped as a real defect in S7.1, S7.2 and S7.3. Here the consequence of a
third entry point forgetting one line is that reports — holding the full depth
evaluation, claim verdicts and fabrication analysis of an **erased person** —
are orphaned permanently, with no FK to catch it, no cascade to sweep it, and no
error to notice it.

Two further consequences of the split, both structural:

- **Erasure is non-atomic.** No transaction spans two databases. A failure
  between lines 354 and 355 destroys the reports while keeping the candidate.
- **`report_store.py:76` runs `ALTER TABLE ... ADD COLUMN` inside a `try/except`
  at construction** — a migration system reimplemented badly, three directories
  away from fifteen real Alembic migrations.

**Decision: FOLD `reports` + `outcomes` into the main database.** Five reasons,
in order of weight:

1. **It converts the convention into a structural guarantee.**
   `reports.candidate_id → candidates.id ON DELETE CASCADE` makes an orphaned
   report *unrepresentable* rather than merely unlikely — the same move S7.1
   made for "no column can hold a document" and S7.2 for `METHOD_SUBJECT`. This
   is the last place in the repo not following the house pattern.
2. **Porting keeps every defect and does the work anyway.** `INSERT OR REPLACE`
   is invalid on Postgres, so the SQL is rewritten either way. Porting buys a
   second hand-written raw-SQL store, a second connection pool and a second
   migration path — and still no FK, no cascade, no atomicity.
3. **PI-9 needs a join that cannot exist in SQL across two databases.**
   `outcomes` is the human ground truth; S4.4's features and leakage-free labels
   live in the main DB. v2 §3.3 calls the calibration harness the cheapest
   high-value sprint — which holds only if its central query is an ordinary
   join. **PI-9 is next.**
4. **The timing will never be better.** Folding needs a data migration; today
   that is one local dev database. PI-8 exists specifically to put real data
   behind it, so this gets monotonically more expensive from here.
5. **It is already de-risked.** A 7-method Protocol, `InMemoryReportStore`
   backing every test, 6 consuming modules.

**Honest cost:** roughly half a day more than porting, and `body` remains a
serialized-JSON column either way — which is fine, the main DB uses JSON columns
throughout. In exchange, a 212-line subsystem and a bespoke self-migrating schema
are deleted.

**Consequence for the route layer:** once the cascade is real, the two call sites
collapse to a single `delete_candidate`, and `delete_for_candidate` survives on
the Protocol only for as long as something still needs it explicitly.

## 3. Inherited non-negotiables (do not relitigate)

From `CLAUDE.md` and v2 §6. PI-8 changes none of them:

- TDD, fully offline tests (`NullLLM`/fakes); `pytest -q` green before merge.
- Every LLM/network step degrades to a deterministic fallback.
- Advisory only — no auto-reject anywhere.
- DPDP: first-party data only; consent objects + delete paths on new tables.
- Config in `config.yaml`, secrets in `.env` (`DEE_*`).
- Each sprint ends with a key-less scripted-HTTP smoke.
- **Hunt the one-entry-point gate** (v2 §6). Gates live on the **service**, not
  the route. This PI adds a second entry point to *every* plane (sessions
  alongside keys), so this rule is the single highest-risk thing in PI-8.
  Every authorization check must be proven against **both** modes.

## 4. Auth architecture

### 4.1 Principals

Three exist today, all key-authenticated:

| Plane | Header | Principal | Today |
|---|---|---|---|
| admin | `X-API-Key` | *none* — a shared secret | fails open (§1) |
| org | `X-Org-Key` | one organization | `authenticate_org`, sha256-hashed, rotatable |
| candidate | `X-Candidate-Key` | one candidate | `authenticate_candidate`, sha256-hashed |

A UI needs **people**, not organizations. An org today has one API key and no
concept of a human member. PI-8 adds:

- **`org_users`** — humans who log into an org (CASCADE from `organizations`).
- **`admin_users`** — operators (decision 0.5).
- Candidates are already principals; they gain sessions, not a new table.

### 4.2 Sessions — one table, exclusive arc

**`auth_sessions`**, with three nullable FK columns — `candidate_id`,
`org_user_id`, `admin_user_id` — **each with its own `ON DELETE CASCADE`**, plus
a CHECK constraint that **exactly one is non-null**.

**Why the exclusive arc and not a polymorphic `subject_type`+`subject_id`:** a
polymorphic id column **cannot carry a foreign key**, so erasure would stop
cascading — silently breaking the "erasure cascades everything" non-negotiable
that has held for eight PIs. Three nullable FKs keep the cascade in the database
where it belongs. `DELETE /portal/me` then kills every session of that candidate
for free, exactly as S7.3's interview tables did.

**Why not three separate session tables:** same guarantee, three times the
surface, three places for a gate to be forgotten — which is precisely the bug
shape §3 says to hunt.

Columns: `id`, the three nullable FKs, `token_hash` (sha256 — plaintext returned
once, never stored, mirroring `issue_access_key`), `issued_at`, `expires_at`,
`last_seen_at`, `revoked_at` (nullable), `user_agent`, `ip_hash`.

**Expiry is computed at read time**, never written by a job — the S7.1
`effective_status` precedent, and for the same reason: no scheduler exists, and
a stored `expired` that nothing corrects is a lie.

### 4.3 Transport — cookie, not bearer

**Session travels as an httpOnly, `Secure`, `SameSite=None` cookie, with
double-submit CSRF tokens on mutating requests.**

`SameSite=None` is **required, not chosen**: the UI is separately hosted
(decision 0.1), so every request is cross-site and `Lax` would drop the cookie
entirely. `None` mandates `Secure`, which mandates HTTPS — so **the API cannot
be served over plain HTTP in any environment the UI talks to**, and S8.1's
deploy must reflect that. `SameSite=None` is also precisely why the CSRF layer
below is non-optional rather than belt-and-braces.

Considered and rejected: `Authorization: Bearer <opaque>`. It avoids CSRF
entirely and is trivially cross-origin, but the token then lives in
`localStorage`, where **any XSS reads it** — the more common real-world
compromise. This product holds real candidates' PII under DPDP; httpOnly closes
the larger hole, and the CSRF machinery it costs is small and well-trodden.

Machine-to-machine is unaffected: `X-Org-Key` continues to be a header, has no
cookie, and needs no CSRF token. **Browsers get cookies, machines get keys**
(decision 0.4).

### 4.4 Login and signup — OTP, no passwords

**`login_challenges`**: `email_hash`, `purpose` (`signup` | `login`),
`code_hash`, `expires_at`, `attempts`, `cooldown_until`. **No FK** — at signup
time no principal exists yet.

Rows are **DELETED on consume or supersession**, not retained. This is the
explicit S7.1 precedent: short-TTL secret material is hygiene, not a retention
policy, and it is a deliberate exception to §6's sweep.

The pure mechanics — code generation, hashing, TTL, attempt counting, cooldown —
are **reused from `app/verification/otp.py`**, which is already pure,
clock-injected and tested. Login reuses the *functions*, not the *table*:
`verification_challenges` is candidate-scoped identity verification and stays
that way.

Cooldown and attempt limits are scoped to **email_hash + purpose**, applying
S7.1's own review finding — a limit scoped to a row that the flow re-mints
limits nothing.

### 4.5 Email seam

New `app/services/email.py`, shaped exactly like `llm.py` and `speech.py`:
`EmailClient` protocol / `SMTPEmail` / `NullEmail` / `CaptureEmail` /
`build_email`.

- **`NullEmail` refuses** and logs neither code nor destination (S7.1's
  `NullNotifier` posture). With no provider configured, signup and login return
  a clear `503 email_unavailable` rather than silently appearing to succeed.
  This is the `NullSpeech` pattern from S7.3, and it is why the key-less smoke
  can still assert something honest.
- **`CaptureEmail` is selected only by explicit config**, never by fallback.
  It is how the smoke drives a real login end-to-end without a provider.
  **There is no silent degradation into it** — that would be §1's bug again.

### 4.6 CORS

Config-driven allowlist `cors_allowed_origins`, **defaulting to empty** (no
cross-origin — fail-closed). Never `*`; with credentials enabled browsers forbid
`*` anyway, and relying on that as the guard would be an accident waiting to be
"fixed" by someone silencing the error.

### 4.7 What this does NOT change

Every existing authorization rule stays exactly as written: consent is still
enforced at query time, every access is still audited allowed-or-denied,
cross-candidate isolation is still structural (handlers resolve the principal
from the credential, **never** from a path or body param). Sessions are a new way
to *establish* the principal; they change nothing about what a principal may do.

**This is the highest-risk sentence in the document.** §3's rule applies with
full force: every gate must be proven against both modes, and the tests must say
so explicitly.

## 5. Sprint boundaries

**Execution order (amended 2026-08-02):** S8.1 ✅ → **S8.2 → S8.4 → UI (external)
→ integration + composite smoke → S8.3 → deploy.** The sprint definitions below
are unchanged; they are simply built in that order. S8.3 still lands before the
deploy — which is now the last act of the PI, so nothing is publicly reachable
while its rate limits and retention sweep are outstanding.

### S8.1 — Deployable spine

*What stops a container from booting into a working system?*

- `alembic upgrade head` in the boot path (v2 §9 blocker 1).
- **Fail-closed admin auth + boot refusal** (§1). Ships first because every
  later sprint is deployed with it.
- Postgres cutover for the main DB — connection string, CI matrix, the six
  `batch_alter_table` migrations verified on PG (blocker 2).
- **`reports` + `outcomes` are FOLDED into the main database** — decided
  2026-08-01, see §2.1. Not ported. Two ORM models, one Alembic migration, the
  seven `ReportStore` Protocol methods reimplemented against SQLAlchemy, and a
  data migration for existing rows. `app/services/report_store.py` and its
  bespoke self-migrating schema are **deleted**.
  Bounded and already de-risked: `InMemoryReportStore` backs every test and only
  6 modules consume the Protocol.
  **Task ordering inside the rewrite:** the cascade regression test (§2.1) is
  written *first* and must pass with **no route-layer orchestration at all** —
  it is the whole point of folding, and writing it last would let the old
  convention quietly survive the migration.
- Railway deploy; secrets via environment.

### S8.2 — Identity & access

*Can a real org and a real candidate get in without an operator?*

- `org_users`, `admin_users`, `auth_sessions`, `login_challenges` (§4).
- `app/services/email.py` (§4.5) — which also gives S7.1's L2 OTP its first
  real delivery path (§2).
- Email-OTP signup + login + logout + session listing/revocation, on all three
  planes.
- Org self-onboard (blocker 5) and candidate self-registration (blocker 4).
- CORS (§4.6) and CSRF (§4.3).
- **`admin_users` rides here** — §12's open question, closed 2026-08-02.
- ~~Pins the S8.4 API contract — see §5.5.~~ **Dropped by the 2026-08-02
  amendment**; see §5.5.

### S8.3 — Operating safely

*Can this be run for paying customers?*

- Rate limiting (blocker 7). **Login and OTP endpoints first** — they are the
  brute-force surface this PI creates. Then the ASR spend path the S7.3 review
  flagged. **Limits are dual-scoped — per email AND per IP** (§8): per-email
  alone lets an attacker spray one guess across ten thousand accounts, per-IP
  alone lets a botnet grind one account. Neither scope is sufficient by itself,
  which is the same "a bound on one path is no bound" lesson §3 carries forward.
- Metrics, tracing, error aggregation (blocker 8). Paired with the limiter
  because a limit you cannot observe is a guess.
- Retention sweep (blocker 6) — `sweep_active=False` since S6.4, and the oldest
  outstanding compliance gap.
- **DPDP correction/rectification + grievance-officer contact** — promoted from
  S6.4 follow-ups to RFP blockers by GTM §8.1.

### S8.4 — UI integration surface

*Can the external UI actually be built against this?*

- Batch resume upload (§2 gap 3) — the wedge demo's central action.
- Cursor pagination on every list endpoint (§2 gap 4).
- The fraud-screen read-model: one call returning a ranked, reasoned risk list
  over a batch, composed from existing subsystems in the pure `app/dashboard/`
  style — **no new state, no new consent purpose**.
- OpenAPI polish sufficient to generate a typed client.

### 5.5 Sequencing note — SUPERSEDED 2026-08-02

~~The UI is being designed **in parallel and externally** (decision 0.1). If
S8.4's endpoint shapes are not settled until S8.4, the design work targets a
moving target and integration is a rewrite. **Therefore: S8.2 pins the S8.4
request/response contracts** — as committed Pydantic schemas and a published
OpenAPI document, with the handlers returning `501` until S8.4 fills them in.~~

**Superseded by the 2026-08-02 re-sequencing.** Pinning existed only to protect
*parallel* design work from a moving target. Under S8.2 → S8.4 → UI, the UI is
built against endpoints that already work, so committing schemas and `501`
handlers one sprint before their implementation buys nothing and costs a sync
burden for exactly one sprint. **S8.2 publishes OpenAPI for what it ships; S8.4
publishes its own.**

The concern §5.5 was protecting against has not vanished — it has moved. It is
now the *ordering* itself that protects integration: nothing is designed against
a contract that does not exist yet.

## 6. Data model summary

Four new tables plus two folded in from the second database — all in the main
DB, all Alembic, all Postgres-shaped:

| Table | Sprint | FKs | Erasure |
|---|---|---|---|
| `reports` | S8.1 | `candidate_id` → `candidates` **CASCADE** (§2.1) | dies with the candidate, **structurally** |
| `outcomes` | S8.1 | `report_id` → `reports` **CASCADE** | dies with its report, so with the candidate |
| `org_users` | S8.2 | `organization_id` CASCADE | dies with the org |
| `admin_users` | S8.2 | none | operators are not data principals in the DPDP sense |
| `auth_sessions` | S8.2 | `candidate_id` / `org_user_id` / `admin_user_id`, **all CASCADE**, CHECK exactly-one | dies with any of its three possible principals |
| `login_challenges` | S8.2 | none (§4.4) | **deleted on consume**, not swept |

`reports.candidate_id` is **nullable** — `POST /evaluate` produces a report with
no candidate attached, and that path predates the candidate backbone. Nullable
plus CASCADE is correct here: an attached report dies with its subject, an
unattached one was never personal data.

The metadata-wide drift / index / FK-ondelete / nullability guards extend to all
four. That guard caught a real migration-vs-ORM drift during S7.1 and is
expected to earn its keep again here.

## 7. DPDP posture

- **No new `ConsentPurpose`.** Authentication is not a disclosure — it is how a
  data principal proves they are the subject. This is exactly S6.4's argument
  for the portal needing no purpose, applied to sessions.
- **Sessions are erasable and cascade** (§4.2).
- `MyData` gains a session list so a candidate can see and revoke their own
  devices — a transparency right, consistent with the access log.
- Session creation, refusal and revocation are **audited**, like every other
  touch.
- `ip_hash`, never a raw IP. The precedent is `email_hash`/`phone_hash` in
  `candidates`: store what identifies, not what re-identifies.
- Correction/rectification + grievance contact land in S8.3 (§5.3).

## 8. Config (new knobs)

```yaml
# --- Auth sessions + login (PI-8) --------------------------------------------
session_ttl_minutes: 720
session_idle_timeout_minutes: 120
session_token_bytes: 32
login_otp_length: 6
login_otp_ttl_seconds: 600
login_otp_max_attempts: 5
login_otp_cooldown_seconds: 60
cors_allowed_origins: []          # fail-closed; never "*"
email_provider: "null"            # null | smtp | capture — capture NEVER by fallback
email_from: ""
rate_limit_login_per_hour_per_email: 20    # brute-forcing ONE account
rate_limit_login_per_hour_per_ip: 100      # spraying MANY accounts
rate_limit_default_per_minute: 120
retention_sweep_enabled: false    # flips true in S8.3 with the job
```

Secrets stay in `.env` under `DEE_*` (SMTP credentials, admin bootstrap, the
Postgres URL). **No knob restores fail-open admin auth** (§0.5).

## 9. Testing and smoke

- Fully offline, as always. `CaptureEmail` and a fake clock make the whole OTP
  path deterministic; no network, no provider.
- **Every authorization gate must be proven against both modes** (§3, §4.7) —
  the PI's main regression risk. **Amended 2026-08-02:** this was written as
  "every authorization test gains a session-mode twin", which S8.2 §2 replaces
  with a stronger and much smaller construction — **one resolver per plane**
  (so existing header-key tests already execute the shared path), **three
  resolver suites** (where cookie-vs-header actually differs), and **a
  structural guard over the FastAPI route table** asserting every non-public
  route establishes its principal through one of those three. Twins are
  hand-written only for the six cases where authorization means something beyond
  identity resolution. The guard is the metadata-drift-guard pattern applied to
  authorization, and unlike twins it covers routes that do not exist yet.
- **Adversarial cases that must be tests, not hopes:** admin plane with no
  configured secret **refuses to boot**; a session for candidate A cannot read
  candidate B (404, indistinguishable); a revoked session 401s immediately; an
  erased candidate's session dies with them; an expired OTP, a reused OTP and an
  over-attempted OTP all refuse; cooldown is scoped to email+purpose, not to a
  row; CORS rejects an unlisted origin; a mutating request without a CSRF token
  is refused.
- **Per-sprint key-less smoke** as always (`scripts/smoke_s81.py`..`s84.py`),
  plus — new for this PI — **one composite smoke** walking the full launch path:
  fresh DB → migrate on boot → org signs up → OTP login → session → batch resume
  upload → fraud-screen read-model → candidate self-registers → portal → erase.
  v2 §4 called this optional; the wedge demo makes it the thing that proves the
  PI is done.

## 10. Non-goals for PI-8

- **Any UI, HTML, template or JS toolchain in this repo** (decision 0.1).
- **Calibration harness** — PI-9, gated on real orgs (v2 §5, RESOLVED note).
- **Real embeddings / ANN** — deferred; `HashingEmbedding` stands.
- **Multi-tenancy** — still deliberately YAGNI; revisit if hosting posture
  demands it (GTM §11).
- **Payments, payroll, contracts, sourcing, native coding assessments** —
  standing non-goals, unchanged.
- **Passwords, SSO, SAML, OAuth social login** — 0.3 settles v0. SSO becomes a
  real question when a segment-2 buyer asks; it is not launch-blocking.
- **The flywheel delete-or-repurpose call** — v2 §3.2, still open, still not
  urgent.

## 11. Definition of done for PI-8

1. A fresh container against an empty Postgres boots, migrates, and serves.
2. It **refuses to boot** with no admin credential configured.
3. An organization signs up, logs in by email OTP, and receives a session
   without any operator touching the database.
4. A candidate self-registers, logs in, exercises `/portal/me`, and erases
   themselves — and every session dies with them.
5. A batch of resumes uploads and returns a ranked, reasoned fraud-risk list.
6. Rate limits, metrics and the retention sweep are live; correction and
   grievance endpoints exist.
7. `pytest -q` green; every sprint smoke green; the composite smoke green.
8. The OpenAPI document is sufficient to build the external UI against.

## 12. Open questions — for the sprint specs, not for this document

- ~~Fold `reports`/`outcomes` into the main DB, or port the raw-`sqlite3` store
  as-is?~~ **CLOSED 2026-08-01 — FOLD. See §2.1**, which also records the
  cross-database erasure finding that decided it.
- **Hosting posture — shared instance vs per-customer.** Interacts with the
  deferred multi-tenancy call. GTM §11.
- **Session TTL and idle timeout defaults** — the values in §8 are placeholders
  pending one real usage pattern.
- ~~**Whether `admin_users` earns its own sprint slice or rides S8.2** — the most
  trimmable item in the PI (§0.5).~~ **CLOSED 2026-08-02 — it rides S8.2.** S8.1
  made admin fail closed on a *shared secret*, which still cannot attribute an
  action to a person; since S8.2 builds `auth_sessions` + OTP login anyway,
  operator accounts are a third principal on machinery already being written.
  Deferring would have meant doing §4.7's regression work twice.
