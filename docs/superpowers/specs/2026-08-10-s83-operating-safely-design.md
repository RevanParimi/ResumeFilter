# S8.3 — Operating safely (design)

**Date:** 2026-08-10 · **Sprint:** S8.3 (PI-8) · **Status:** spec, approved by the
user 2026-08-10.
**Read order:** `docs/ROADMAP.md` "Current state" →
`2026-08-01-pi8-launch-readiness-design.md` §5.3 + §8 →
`2026-08-01-veritas-gtm-positioning.md` §8.1 → this.
**Builds as TWO branches from this one spec** (the S8.4 shape, which worked):
`s83a-limits-and-metrics`, then a review gate, then
`s83b-retention-and-rights`.

*Can this be run for paying customers?* — that is the whole sprint. It is the
last sprint before the deploy (S8.6), so everything here is a thing that must be
true **before** the service is publicly reachable, not a thing that would be
nice afterwards.

---

## 0. Decisions taken before the design (with the user, 2026-08-10)

**0.1 Two phases, one spec.** Phase A is the abuse and spend surface (rate
limits · in-place retry · metrics). Phase B is the statutory surface (retention
sweep · correction/rectification · grievance officer). Rejected: one branch for
all five subsystems — every branch review since S7.1 has found a defect that a
smaller diff would have surfaced sooner, and a single review covering five
subsystems is how the S8.4 Phase A identity leak got past a task review.
Rejected: Phase A only, deferring B past the deploy — the deploy would then go
live with `sweep_active=false` and no correction path, which are the two items
GTM §8.1 reclassifies from polish to **RFP blockers**.

**0.2 Rate-limit counters live in the database, in ONE table, behind ONE
limiter.** Rejected: in-process token buckets — they reset on every redeploy and
are per-worker, so two uvicorn workers silently double every limit. Both are
failures *of the exact surface the limiter exists for*, and both pass every unit
test. Rejected: a hybrid (DB for auth, memory for a blanket limit) — that is two
limiter implementations, which is the "one rule, two doors" shape this repo has
shipped as a real defect in S7.1, S7.2, S7.3 and S8.4 Phase B.

**0.3 DPDP correction is a REVIEWED REQUEST QUEUE, not a self-service edit.**
Rejected: direct `PATCH` of a field whitelist — on a fraud-screening platform,
giving the subject a write path onto the data the risk score is computed from is
giving them an edit box over the evidence. DPDP permits the fiduciary to verify
before correcting; §4.7 states the boundary precisely.

**0.4 Observability is hand-rolled counters at an admin-gated `GET /metrics`,
in Prometheus text format.** Rejected: OpenTelemetry — a dependency tree and an
exporter, with nothing to export to before the deploy. Rejected: a JSON admin
route — easier to assert, but nothing standard can scrape it. Rejected: log
lines only — there is then no way to answer "how often are we denying" without
grepping, and the pairing with the limiter is the whole point (§3.3).

**0.5 `rate_limit_default_per_minute` from the PI-8 config sketch is DROPPED,
not deferred.** A blanket per-IP limit on unauthenticated POSTs covers exactly
the `/auth/*` routes, which §3 already limits by name. Shipping it would add an
enforced-nowhere knob to a config file whose credibility depends on every knob
meaning something. Recorded here so a future reader does not "restore" it as an
oversight.

---

## 1. What is measured to be true today

Every claim below was read off the code on 2026-08-10, not remembered.

| Input | State |
|---|---|
| Rate limiting | **Nothing.** No middleware, no counter, no table, no knob in `config.yaml` or `Settings`. `login_challenges.attempts` bounds ONE challenge; `login_otp_cooldown_seconds` (60) bounds resends on ONE challenge. Neither bounds a caller. |
| Retention sweep | `build_retention_policy()` returns `RetentionPolicy(..., sweep_active=False)` — a hardcoded literal (`app/portal/retention.py:50`). Eight windows are declared posture-only via `RETENTION_KNOBS`. No sweeper exists anywhere. |
| In-place retry | No path re-queues a `failed` item. `_claimable` is pending + stale-processing only; `add_items` has no route. `SCREENING.md` §7 already admits the text is "kept on failure for a retry path that DOES NOT EXIST YET". |
| Observability | `configure_logging()` + one `access` log line with `request_id`, `method`, `path`, `status`, `duration_ms` (`app/main.py:106`). No counters, no metrics route, no `prometheus_client` dependency. |
| Correction / grievance | **Zero code.** No route, no table, no config contact. `CandidateStore` has no update path at all — `_refresh_identity` only runs inside `ingest`. |
| Worker / scheduler | **Still none**, re-confirmed. No `BackgroundTasks`, no scheduler, nothing async-detached in `app/`. So a "sweep job" is an invocable thing, never a daemon. |

**⚠ And one finding this survey turned up, which shapes §3.2.**
`auth_sessions.ip_hash` exists (`app/auth/models.py:124`), is plumbed through
`AuthStore.create_session(ip_hash=...)` and `AuthService.verify_code(ip_hash=...)`
— and **is never populated**: `_verify` (`app/api/routes.py:2274`) does not pass
it. Every session row in the database has `ip_hash = NULL`, while PI-8 §7 states
"`ip_hash`, never a raw IP" as though the rule were implemented. It is a
declared-inert field, and S8.3 needs IP extraction for the limiter anyway. **One
helper, two consumers** — the limiter and the session row — so the rule becomes
true at the same moment it becomes enforceable.

---

# PHASE A — `s83a-limits-and-metrics`

## 2. The limiter's shape

New package `app/ratelimit/`, following the `app/screening/` split:

```
schema.py    pure types: RateRule, LimitScope, LimitDecision. No I/O.
models.py    RateLimitCounterRow  -> migration 0021
store.py     RateLimitStore: the atomic increment, and nothing else
service.py   RateLimiter.check(rule, keys, now) -> LimitDecision
```

### 2.1 The table

```
rate_limit_counters
  id            String(36)  pk
  bucket_key    String(128) -- sha256(rule name | scope | identity), hex
  window_start  DateTime(tz)
  count         Integer     default 0
  expires_at    DateTime(tz)
  UNIQUE (bucket_key, window_start)
  INDEX (expires_at)          -- the sweep's access path (§7)
```

`bucket_key` is a **hash**, never the identity itself: the row would otherwise
hold a raw email beside a raw IP for every login attempt on the platform, which
is a worse disclosure than the thing being defended. The identity is hashed with
`contact_hash_salt`, the same salt as `email_hash`/`phone_hash` — precedent, not
invention.

### 2.2 The increment must be atomic, and S8.4 Phase B says how

Two concurrent requests on one bucket must not both read `count = 19` and both
write `20`. The house solution already exists: `ScreeningStore._try_claim` is a
conditional `UPDATE` whose `rowcount` is the decision.

```
UPDATE rate_limit_counters SET count = count + 1
 WHERE bucket_key = :k AND window_start = :w AND count < :limit
```

`rowcount == 1` ⇒ allowed. `rowcount == 0` ⇒ either the row is at its limit or
it does not exist yet; the store then attempts an `INSERT` and treats an
`IntegrityError` on the unique constraint as "somebody else created it, re-run
the UPDATE once". The `count < :limit` clause is what makes the check and the
increment one statement.

**The S8.4 Phase B lesson applies verbatim and must be honoured in the tests:**
two mutants there (deleting a `WHERE` clause, relaxing a `rowcount` check)
**survived** because the race was unreachable through two sequential calls —
the second call's own SELECT filtered the row out before the UPDATE could
matter. So `RateLimitStore` gets the same treatment: the conditional UPDATE is
its own seam, and a test builds the interleaved state directly on the store
rather than hoping two sequential `check()` calls exercise it.

### 2.3 Dual scoping: ALL scopes evaluated, ANY denial denies

A `RateRule` carries a list of scopes. `check()` evaluates every one of them and
returns the **most restrictive** decision.

- Per-email alone: an attacker sprays one guess across ten thousand addresses
  and never trips a per-email counter.
- Per-IP alone: a botnet grinds one address from ten thousand addresses.

Neither is a bound. This is §3's "a bound on one path is no bound" carried into
the limiter itself, and it is why a rule is a *list* of scopes rather than a
scope.

**Order matters for the counter, not for the answer:** every scope is
incremented before the decision is returned, so a denial by the email scope does
not leave the IP scope under-counted and vice versa. A limiter that stops
counting at the first denial under-reports the attacker who tripped it.

### 2.4 The rules (config, §9)

| Rule | Scopes | Default | Call site |
|---|---|---|---|
| `login_request` | email, ip | 20/h, 100/h | `AuthService.request_code` |
| `login_verify` | email, ip | 30/h, 200/h | `AuthService.verify_code` |
| `screening_process` | org | 400/h | `ScreeningService.process` |
| `asr_transcribe` | candidate | 60/h | the S7.3 audio path |
| `grievance_submit` | candidate | 10/h | `POST /portal/grievances` (Phase B) |

`screening_process` at 400/h × `screening_max_items_per_call` (5) = 2000 items
an hour per organisation — comfortably above a human driving the UI through a
500-resume batch, and a hard ceiling on a runaway client loop. **Bounded per
call is not bounded per caller**, which is the gap the S8.5 wiring session named
when it made *any* error stop the browser's driver loop.

## 3. Where the limiter is called from, and why not the routes

### 3.1 The service layer, because that is where the gates already live

`AuthService`'s own docstring states the rule: *"Every gate lives here rather
than on a route. That is not style: a rule applied at one entry point and not
the other has shipped as a real defect in S7.1, S7.2 and S7.3."*

The OTP surface is **eight routes across three planes** and exactly **two
service methods**. Limiting at the routes is eight chances to forget and eight
places for a future ninth route to be added without one. Limiting inside
`request_code` and `verify_code` is two, and the header-key-versus-session twin
problem — the thing that made S8.2 collapse three resolvers into one — does not
arise at all, because a service method has no notion of how the caller
authenticated.

`ScreeningService.process` and the ASR path are single choke points already.

**Consequence for the HTTP layer:** the service raises `RateLimited(rule,
retry_after_seconds)`; routes translate it to `429` with a `Retry-After` header
and `{"detail": "rate_limited"}`. Services decide, routes translate — the S8.2
posture, unchanged.

### 3.2 Client IP: not trusted by default, and the same helper fills `ip_hash`

`app/api/routes.py` gains one helper:

```python
def _client_ip(request: Request, settings: Settings) -> Optional[str]
```

- With `rate_limit_trusted_proxy_hops == 0` (the default) it returns
  `request.client.host` and **ignores `X-Forwarded-For` entirely**.
- With `n > 0` it takes the `n`-th entry from the right of `X-Forwarded-For`,
  falling back to the socket peer when the header is absent or too short.

**This is the decision that determines whether the per-IP scope is worth
anything.** Trusting `X-Forwarded-For` by default hands an attacker a free reset
of their own IP scope through a header they fully control — the limiter would
look installed, pass every test, and bound nothing. The Railway deploy sets
`1`; the default assumes no proxy, because the wrong default here fails *open*.

When no IP can be determined (`request.client` is None, which happens under some
ASGI test transports) the **IP scope is skipped and the email scope still
applies** — a partial bound, never a bypass, and never a refusal of a legitimate
caller for a reason they cannot act on.

The same helper is passed to `verify_code(ip_hash=...)`, closing §1's inert
field. `ip_hash`, never a raw IP: the store gets `contact_hash(ip)`.

### 3.3 429 must not become an enumeration oracle

`AUTH.md`'s rule is that signup and login answer `202` identically for
registered and unregistered addresses. A limiter that answers `429` only for
addresses that *have* an account would reopen that hole from the side.

It does not, because **the counter keys on the submitted email hash regardless
of whether an account exists** — the limit is a property of the request, not of
the subject. A test pins that the 21st request for an unknown address and the
21st for a known one produce byte-identical responses.

The existing 60-second cooldown keeps its silent `202` (it can only be triggered
by an address that has an account, so surfacing it *would* be an oracle). The
rate limit is a coarser, account-independent bound and says so honestly. Both
behaviours are correct; they differ because their key differs, and the spec says
that out loud so a future reader does not "unify" them.

### 3.4 Prod refuses to boot with the limiter disabled

`verify_launch_config` today holds **five** refusals — two from S8.1 (no
`DEE_API_AUTH_KEY`, at any `env`; prod on SQLite) and three prod-only from S8.2
(insecure session cookie, `"*"` CORS origin, capture email provider). S8.3 adds
the **sixth**: `env == "prod"` and `rate_limit_enabled == False` ⇒
`LaunchConfigError`. It follows PI-8 §8's standing rule — *no knob restores
fail-open admin auth* — and an unthrottled OTP endpoint on a public host is the
same class of thing.

It goes **after** the `if settings.env != "prod": return` at
`app/core/boot.py:50`, with the grievance refusal of §9 (the seventh). That
early return is the prod-only gate; a check placed above it applies everywhere
and would break every local run.

`rate_limit_enabled: false` remains available for local development and for the
test suite, where a shared counter across tests would be a flake generator.

## 4. In-place retry of failed items

`POST /screening/batches/{batch_id}/retry` (org plane) →
`{batch_id, requeued: int, skipped: int}`.

**It re-queues; it does not process.** The route flips `failed` items back to
`pending` and clears `error`, `claimed_at`, `processed_at`. The existing
`process` call then picks them up through the unchanged `_claimable` predicate.
There is exactly **one** processing door, and this route is not a second one —
which is the entire reason it is shaped as a status change rather than as a
"retry and evaluate" call.

**Batch-level, not per-item.** The realistic input is 3 failures in a 200-item
batch and a customer who wants them tried again; the wired UI has no per-item
action and inventing one is design work S8.5 deliberately did not do. One call,
one door.

**Items with an empty `raw_text` are counted as `skipped`, never re-queued.**
Either the text was cleared on success (so there is nothing to retry) or the
failure was `empty_resume` (so the retry would fail identically, and reporting
`requeued: 1` would be a promise the next `process` call breaks). The counts are
honest about which happened.

Ownership is checked through `OrgScopedAccess`; an unowned or unknown batch is
**404, never 403**, byte-identically — the same rule S8.5 asserted on both
outcome verbs.

**No retry counter column, deliberately.** A permanently-broken item fails
identically each time, at the organisation's own cost, and that cost is already
bounded by `screening_process`'s per-org rule (§2.4). A `retries` column would
be a second thing to keep true with no rule depending on it. Recorded so its
absence reads as a decision.

`SCREENING.md` §7's "kept on failure — for a retry path that DOES NOT EXIST
YET" is corrected in this phase, and gains its Phase B half (§7.3).

## 5. Metrics

### 5.1 Counters hang off `Services`, never off a module

New `app/metrics/registry.py`: a `Metrics` object holding counters and a
duration sum/count pair, constructed in `build_default_services()` and
therefore **injectable and per-app**. A module-level global would be shared
across every test in the suite, and the first ordering-dependent assertion would
be a flake nobody could reproduce. This is the same reason `Services` exists at
all.

### 5.2 Labels use the ROUTE TEMPLATE, never the raw path

`/screening/batches/{batch_id}` is one series. The raw path is one series per
batch id, and a scanner walking random URLs is an unbounded memory leak dressed
as observability. The middleware reads `request.scope.get("route")` **after**
`call_next` and uses `route.path`; anything unmatched gets the single literal
label `__unmatched__`.

This is the one cardinality trap that makes hand-rolled metrics dangerous, so it
is designed in rather than discovered.

### 5.3 What is counted

| Metric | Labels | Why it exists |
|---|---|---|
| `veritas_http_requests_total` | route, method, status | the baseline |
| `veritas_http_request_duration_ms_sum` / `_count` | route | an average; **no quantiles**, and the doc says so |
| `veritas_rate_limit_decisions_total` | rule, scope, decision | **the pairing that justifies the phase**: a limit you cannot observe is a guess |
| `veritas_llm_calls_total` | tier, outcome | spend |
| `veritas_asr_calls_total` | outcome | spend, the S7.3 path |
| `veritas_screening_items_total` | outcome | done vs failed, per item |
| `veritas_retention_deleted_total` | data_class | Phase B (§7) |

### 5.4 `GET /metrics`

Registered on `router` (the admin router), so it inherits `require_api_key` and
is **fail-closed by construction** — no new gate to forget, and the route-table
guard covers it with no edit. `PlainTextResponse`, content type
`text/plain; version=0.0.4`. It is not in `PUBLIC_PATHS`; an unauthenticated
scrape gets 401.

## 6. Phase A verification

- TDD throughout, `pytest -q` green before each commit.
- **Mutation probes on the limiter** (the house habit, and the S8.4 Phase B
  survivors are the reason): drop the `count < :limit` clause · drop the
  `rowcount` check · evaluate only the first scope · trust `X-Forwarded-For`
  when hops is 0 · skip the increment on the denying scope. Each must die
  naming a test.
- **`smoke_s83a.py`, and it reaches one thing no unit test can.** After
  hammering the OTP endpoint to a `429`, it builds a **second app instance
  against the same database** and confirms the counter did not reset. That is
  the entire argument for decision 0.2, and an in-process limiter would pass
  every unit test in this phase and fail exactly this check. It also proves
  dual scoping in both directions (two emails from one IP; one email from two
  IPs), retries a genuinely failed item and watches `process` pick it up, and
  reads the deny counter back out of `/metrics`.
- Every prior smoke re-run; `DEE_OPENROUTER_API_KEY` pinned in the new ones too,
  per the trap S8.4 Phase A recorded for the third sprint running (and which
  `smoke_s63` proved was still live one sprint later).

---

# PHASE B — `s83b-retention-and-rights`

## 7. The retention sweep

### 7.1 One table drives both the promise and the deletion

`app/portal/retention.py` already holds `RETENTION_KNOBS` — eight data classes
mapped to eight config knobs — and it is what the candidate is **told** in
`/portal/me`. If the sweeper carries its own list of targets, the two drift, and
the drift is silent in the worst direction: the portal keeps promising a window
that nothing enforces.

So `app/retention/plan.py` defines `SweepTarget(data_class, knob, table,
timestamp_column, mode)` and the knob mapping is **derived from the same
source**. A guard test asserts set equality in both directions — every declared
window has a target, every target has a declared window — in the
metadata-drift-guard family that has already caught a real migration-vs-ORM
drift in S7.1.

### 7.2 `sweep_active` stops being a literal

```python
return RetentionPolicy(windows=windows, sweep_active=False)   # today
return RetentionPolicy(windows=windows,
                       sweep_active=settings.retention_sweep_enabled)
```

**This is the point of Phase B.** Right now the portal tells every data
principal that no mechanical purge runs. After this phase that sentence has to
become true in the other direction — and it has to be *derived*, because a
second hardcoded literal is a promise that goes stale the day the operator
flips the config.

`retention_sweep_enabled` flips to `true` in `config.yaml` in this phase,
because the job it was waiting for now exists.

### 7.3 Eleven classes, and three of them sweep differently

The eight declared classes delete rows older than their window:
`resumes` · `profile_sources` · `verifications` · `interview_sessions` ·
`interview_records` · `coding_round_results` · `observed_offers` · `audit_log`
(all keyed on `created_at`, which every one of those tables has — measured).

Three more join them, and each behaves differently for a reason already
established elsewhere:

1. **`batch_items` CLEARS `raw_text` and KEEPS THE ROW** under
   `ret_batch_item_days`. The organisation's record of what it screened must
   survive — identical reasoning to `batch_items.candidate_id` being
   `SET NULL`, and to the S8.5 argument that an outcome outlives the org that
   recorded it. **And this is where Phase A and Phase B meet: retention bounds
   the retry window.** After 90 days a failed item is no longer retryable
   because its input is gone. Stated in `SCREENING.md` §7 and in
   `OPERATING.md`, one sentence each, because a capability that silently
   expires is worse than one that never existed.
2. **`rate_limit_counters`** get their own short window,
   `ret_rate_limit_days: 7`. An `ip_hash` stored beside an `email_hash` is
   pseudonymous personal data, not bookkeeping, and the row has no value once
   its window has closed.
3. **Expired `login_challenges` and `auth_sessions`.** S8.2 deletes a challenge
   on consume — but an **abandoned** challenge is never consumed and lives
   forever today. Same for a session that expired without a logout.

### 7.4 Delivery: a route and a CLI, because there is no scheduler

- `run_sweep(session_factory, settings, *, now, dry_run) -> SweepReport` — pure
  orchestration over the target table, no HTTP vocabulary.
- `POST /admin/retention/sweep` (admin plane) → `SweepReport{by_class, dry_run,
  truncated, at}`. **`dry_run` defaults to `true`**: the most destructive
  operation in the repo must not delete because somebody posted an empty body.
  A cron passes `{"dry_run": false}` explicitly.
- `python -m app.retention.sweep` for a Railway cron or an operator shell.
- When `retention_sweep_enabled` is false, a `dry_run=true` call still works (a
  count is safe and is the operator's way to see what *would* go) and a
  `dry_run=false` call is refused **409 `retention_sweep_disabled`**.
- `sweep_max_rows_per_class` (10000) bounds one invocation so it cannot hold
  locks for minutes on a large table; the report carries `truncated: true`
  rather than pretending it finished.

The smoke asserts **dry-run parity**: the counts a dry run reports are the
counts the real run then deletes. That is the cheapest guard against a sweeper
whose preview and whose action disagree, which is the failure mode that makes
dry-run worse than useless.

## 8. Correction / rectification

### 8.1 One table, two kinds

`data_principal_requests` (migration `0022`):

```
id                       String(36) pk
candidate_id             FK candidates ON DELETE CASCADE
kind                     String(16)  correction | grievance
status                   String(16)  open | resolved | rejected
applied                  Boolean     default False
field                    String(32)  nullable; a CorrectionField member
current_value            Text        bounded
requested_value          Text        bounded
note                     Text        bounded by max_request_note_chars
created_at               DateTime(tz)
resolved_at              DateTime(tz) nullable
resolution               Text
resolved_by_admin_user_id FK admin_users ON DELETE SET NULL
```

**`status` and `applied` are two facts, not one**, and collapsing them is the
ambiguity worth spending a column on. `status` is what the operator decided:
`resolved` (handled) or `rejected` (refused), with the reason in `resolution`.
`applied` is whether that decision actually **changed stored data** — which is
false for every grievance, false for a resolved `email` correction the operator
handled out of band (§8.3), and true only when a value was written. A single
four-member enum would leave "is an applied correction also resolved?"
answerable two ways, and the subject's own view of their request is the last
place to be vague about whether anything changed.

`candidate_id` **CASCADEs**: an erased subject's requests die with them, because
erasure is the stronger right and a correction request about a person who no
longer exists is personal data with no subject. This is the opposite call from
S8.5's `outcomes.org_id` SET NULL, and the contrast is the reasoning — an
outcome is a label the *platform* learns from, while a correction request is
wholly the subject's own.

`resolved_by_admin_user_id` exists for the same reason S8.5 added
`recorded_by`: a decision about a person's record must record who made it.

### 8.2 A correction NEVER rewrites an extraction

**The load-bearing rule of this phase.** An `extractions` row is a record of
what a document said. Rewriting it destroys the evidence the fraud screen is
computed from, and on *this* product that is not a hypothetical: the subject of
a correction request is exactly the person with an incentive to edit a claim
that got flagged.

So the extraction is immutable, and a resolved correction may only touch the
candidate's own identity columns.

### 8.3 Only `full_name` is auto-appliable, and the other two are refused BY NAME

`CorrectionField` = `full_name` · `email` · `phone` · `other`.

- **`full_name`** is a plain column on `candidates` with no identity semantics.
  Resolving with `apply: true` writes it through a new
  `CandidateStore.apply_correction`, audited.
- **`email` and `phone` are refused for auto-apply, with the reason in the
  refusal.** Both are hashed into the dedup keys `_resolve_candidate` matches
  on, and `email_hash` is additionally the portal login credential. Changing
  either is an *identity* operation that can collide two candidate rows or move
  an account's login address — not a data correction. They are recorded,
  reviewed, and resolved with a written explanation by an operator who
  understands the consequence.
- **`other`** requires a note and can never be auto-applied.

The mechanism DPDP requires — request, review, decide, record, disclose — is
complete for all four. Auto-apply is a convenience for the one field where it is
safe, and the refusal names its own reason so nobody has to remember it.

### 8.4 Routes

| Route | Plane |
|---|---|
| `POST /portal/corrections` | candidate |
| `POST /portal/grievances` | candidate |
| `GET /portal/requests` | candidate (their own, both kinds) |
| `GET /admin/requests` | admin (filter by status) |
| `POST /admin/requests/{id}/resolve` | admin |

Every transition is audited through the existing `LedgerStore._audit` (actor,
action, `entity_type="data_principal_request"`), so it surfaces in the
candidate's own `/portal/access-log`. That is the S3.1 rule — *surveillance is
itself observable* — applied to the handling of the subject's own complaint,
which is the case where it matters most.

`MyData` gains `requests: list[RequestView]`.

## 9. The grievance officer

Config, published, and refused at boot:

```yaml
grievance_officer_name: ""
grievance_officer_email: ""
grievance_officer_phone: ""
grievance_response_days: 30
```

- **`GET /grievance` is PUBLIC** — added to `PUBLIC_PATHS`, which is the
  reviewable act that widening that set is meant to be. DPDP requires the
  mechanism to be *published*; a contact reachable only after login is not
  reachable by someone whose complaint is that they cannot log in.
- Echoed in `MyData.grievance` so the portal shows it in context.
- **Prod refuses to boot with an empty officer email.** Shipping to production
  with no published grievance contact is precisely the RFP blocker GTM §8.1
  names, and a boot failure is the only form of "remember this" that works.

`POST /portal/grievances` is rate-limited per candidate (§2.4) — it is the one
new authenticated write that a stuck client could loop on.

## 10. Config (new knobs)

```yaml
# --- Rate limiting (PI-8, S8.3 Phase A) --------------------------------------
rate_limit_enabled: true                    # prod REFUSES to boot with false
rate_limit_trusted_proxy_hops: 0            # 0 = ignore X-Forwarded-For entirely
rate_limit_login_per_hour_per_email: 20
rate_limit_login_per_hour_per_ip: 100
rate_limit_verify_per_hour_per_email: 30
rate_limit_verify_per_hour_per_ip: 200
rate_limit_process_per_hour_per_org: 400    # x5 items = 2000 items/hour
rate_limit_asr_per_hour_per_candidate: 60
rate_limit_grievance_per_hour_per_candidate: 10   # lands in PHASE B, with its
                                                  # call site -- a knob whose
                                                  # rule has no call site is
                                                  # exactly what 0.5 refuses

# --- Retention sweep (PI-8, S8.3 Phase B) ------------------------------------
retention_sweep_enabled: true               # the job now exists
sweep_max_rows_per_class: 10000
ret_rate_limit_days: 7

# --- DPDP rights (PI-8, S8.3 Phase B) ----------------------------------------
max_request_note_chars: 2000                # same bound, same reason, as outcome notes
grievance_officer_name: ""
grievance_officer_email: ""                 # prod REFUSES to boot when empty
grievance_officer_phone: ""
grievance_response_days: 30
```

## 11. Testing and smoke

Fully offline, as always: `NullLLM`, a fake clock for every window, no network.

- Phase A: §6.
- Phase B: `smoke_s83b.py` — a candidate files a correction; it appears in
  `/portal/requests` **and** in `/portal/access-log`; an operator lists it,
  resolves it with `apply: true`, and `/portal/me` shows the corrected name;
  an `email` correction is refused for auto-apply naming its reason; the
  grievance contact is readable **without a session**; rows seeded with old
  timestamps are counted by a dry run and then deleted by a real run **with the
  counts matching**; `sweep_active` reads `true` in `/portal/me` afterwards.
- Regression: all eighteen prior smokes, `DEE_OPENROUTER_API_KEY` pinned.

## 12. Documentation

New root doc **`OPERATING.md`** — the limits and their scopes, the metrics and
their cardinality rule, the sweep runbook (route, CLI, dry-run discipline), and
the request queue's lifecycle. Written in Phase A, extended in Phase B.

Corrected in place: `SCREENING.md` §7 (retry exists; retention bounds it),
`UI.md` §4.A (a retry affordance is now callable) and §4.D (correction,
grievance and the live sweep are new portal surfaces), `TENANCY.md` §5 if the
scope guard's reach changes.

## 13. Explicitly not in this sprint

- **Sliding-window or token-bucket limiting.** Fixed windows admit a 2× burst
  across a window edge. For a 20/hour OTP bound that is irrelevant, and the
  honest statement is worth more than the precision. `OPERATING.md` says it.
- **Distributed rate limiting / Redis.** One database is the coordination point
  until there is a second service.
- **Per-item retry, a retry counter** (§4).
- **Alerting.** `/metrics` is scrapeable; wiring a scraper and thresholds is a
  deploy-time concern (S8.6), not an application one.
- **Correcting an extraction, or any self-service profile edit** (§8.2).
- **A candidate-facing view of a report** — unchanged since S6.4, and a
  correction request does not become one.
