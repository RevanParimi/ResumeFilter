# OPERATING.md — limits, metrics and the runbook

**Sprint:** S8.3 Phase A (2026-08-10) · **Spec:**
`docs/superpowers/specs/2026-08-10-s83-operating-safely-design.md`
**Audience:** whoever runs this service for a paying customer.

Phase B extends this document with the retention sweep and the data-principal
request queue. Everything below is live today.

---

## 1. What is limited, and where the check lives

| Rule | Scopes | Default | Enforced in |
|---|---|---|---|
| `login_request` | email **and** IP | 20/h, 100/h | `AuthService.request_code` |
| `login_verify` | email **and** IP | 30/h, 200/h | `AuthService.verify_code` |
| `screening_process` | org | 400/h | `ScreeningService.process` |
| `asr_transcribe` | candidate | 60/h | `InterviewService.answer`, audio only |

**The check lives in the SERVICE layer, never on a route.** The OTP surface is
eight routes across three planes and exactly **two** service methods. Limiting
at the routes would be eight chances to forget, plus one more for route nine,
and `AuthService`'s own docstring already states the rule this follows: *"Every
gate lives here rather than on a route … a rule applied at one entry point and
not the other has shipped as a real defect in S7.1, S7.2 and S7.3."*

**Signup and login share the `login_request` budget**, deliberately. Both mint
and send a code, so counting them separately would double the real bound on the
only thing being defended. `scripts/smoke_s83a.py` asserts this explicitly —
its first version assumed the opposite and was wrong.

**`screening_process` is the one that protects the bill.** `process` is capped
at `screening_max_items_per_call` (5), which bounds one request and says
nothing about a client in a loop — and every call bills a model. 400 calls × 5
items = 2000 items an hour per organisation, far above a human driving the UI
through a 500-resume batch and a hard ceiling on a runaway client.

The ASR rule fires **only when audio is present**: a typed interview answer
costs nothing and must not consume a transcription budget.

### Dual scoping: all scopes counted, any denial denies

Per-email alone lets an attacker spray one guess across ten thousand addresses.
Per-IP alone lets a botnet grind one address. Neither is a bound by itself, so
a rule carries a **list** of scopes, every one is evaluated, and any single
denial denies.

Every scope is counted **even after an earlier one has denied**. A limiter that
stops at the first denial under-reports the attacker who tripped it and leaves
the second scope's window looking clean to whoever reads §3.

### Counters live in the database, and that is not a matter of taste

`rate_limit_counters` (migration `0021`), keyed on a salted hash of
`rule | scope | identity` — never the email, never the IP. An in-process
limiter resets on every container start and is per-worker, so two uvicorn
workers would silently double every limit. Both are failures of the exact
surface a limiter exists for, and **both pass every unit test**;
`smoke_s83a.py` check 6 restarts the server against the same database and is
the check that tells them apart.

## 2. Fixed windows, stated honestly

Windows are fixed, not sliding. **A burst of up to 2× the limit is reachable
across a window edge** — 20 requests at 13:59 and 20 more at 14:01 are both
allowed. For a 20/hour OTP bound that is irrelevant, and a sliding window costs
a row per event rather than a row per window. If a rule ever needs precision at
the boundary, that is the trade to revisit.

## 3. `X-Forwarded-For` and `rate_limit_trusted_proxy_hops`

**Default is `0`, meaning the header is ignored entirely** and the socket peer
is used.

This is the setting that decides whether the per-IP scope is worth anything.
`X-Forwarded-For` is entirely attacker-controlled: trusting it by default would
hand every caller a free reset of their own scope on every request, and the
limiter would pass all its tests while bounding nothing.

- **Direct exposure (no proxy):** leave it `0`.
- **Behind Railway or one load balancer:** set it to `1`. The n-th entry *from
  the right* is taken — the rightmost entries are the ones our own
  infrastructure appended; everything left of them came from the client.
- **Set it too high** and the value falls back to the socket peer. **Set it too
  low behind a proxy** and every caller shares one bucket, so the per-IP scope
  will refuse legitimate traffic. Getting this wrong is visible in §4's deny
  counter before it is visible anywhere else.

Addresses are stored as `contact_hash(ip)` — the `email_hash`/`phone_hash`
precedent: store what identifies, never what re-identifies. The same helper
populates `auth_sessions.ip_hash`, which was a declared-but-never-written
column until this sprint.

## 4. The 429, and why it does not leak

A refusal is `429` with `{"detail": "rate_limited"}` and a `Retry-After`
header in whole seconds (never `0` — that invites a retry that is also
refused).

**One opaque detail.** Which rule and which scope refused is operator
information; it goes to the `rate_limited` log line, not to the caller. Telling
a brute-forcer which of their two axes tripped is telling them which one to
change.

**The 429 is byte-identical for a registered and an unregistered address**, and
this is load-bearing: `AUTH.md`'s anti-enumeration rule makes signup and login
answer `202` for everyone, and a 429 that appeared only for real accounts would
rebuild that oracle out of status codes. The counter therefore keys on the
**submitted** address and is incremented *before* the has-an-account branch.
Asserted in `tests/test_ratelimit_auth.py` and in the smoke.

**The 60-second resend cooldown keeps its silent `202`**, and the difference is
deliberate rather than an inconsistency: a cooldown can only be triggered by an
address that *has* a live challenge, so surfacing it would be an oracle. The
rate limit is account-independent, so it can be honest.

## 5. Metrics

`GET /metrics` — **admin-gated** (it is on the admin router, so the credential
check is inherited rather than remembered), Prometheus text exposition,
`text/plain; version=0.0.4`. No scraper is wired yet; the format is standard so
one can be pointed at it whenever the deploy lands.

| Metric | Labels |
|---|---|
| `veritas_http_requests_total` | route, method, status |
| `veritas_http_request_duration_ms_sum` / `_count` | route |
| `veritas_rate_limit_decisions_total` | rule, scope, decision |

**Durations are a sum and a count — an average. There are no buckets and no
quantiles**, and that is said out loud so nobody reads a p99 into a mean.

**Labels use the route TEMPLATE, never the raw path.**
`/screening/batches/{batch_id}` is one series; the raw path would be one series
per batch id, and a scanner walking random URLs would be an unbounded memory
leak dressed as observability. Anything unmatched collapses to a single
`__unmatched__` label.

Counters are **per-app**, held on the injected `Services` bundle. A module-level
registry would be shared by every test in the suite and the first
ordering-dependent assertion would be an unreproducible flake.

**The table above is the whole list.** `llm_calls`, `asr_calls`,
`screening_items` and `retention_deleted` were declared in the registry's help
table with nothing incrementing them; the S8.3 review removed them rather than
wiring them, because producing those numbers means threading a metrics handle
through the `LLMClient` and `SpeechClient` ABCs, three subclasses each, both
builders and every fixture that constructs one — to emit series no scraper
reads yet. Phase B adds each name in the same commit as the code that
increments it, and `tests/test_metrics.py::test_every_declared_metric_has_a_call_site`
now makes that ordering mandatory rather than remembered.

A declared-inert metric is worse than a missing one: the series is simply
absent from a scrape, an operator reads absent as "nothing happened", and §7's
runbook step quietly cannot answer. This is the same shape as
`auth_sessions.ip_hash` — declared, plumbed, never populated — which is this
branch's own headline finding.

## 6. Retry

`POST /screening/batches/{batch_id}/retry` → `{batch_id, requeued, skipped}`.

**It re-queues; it does not process.** Failed items go back to `pending` with
their error cleared, and the existing `process` call does the work — there is
exactly one door that evaluates an item, and this is not a second one.

- **Batch-level, not per-item.** The real input is three failures in a
  200-item batch.
- **`skipped` counts items whose `raw_text` is gone** — either they succeeded
  (text is cleared on success) or they failed as `empty_resume` and would fail
  identically. Reporting those as `requeued` would be a promise the next
  `process` call breaks.
- Another organisation's batch answers **404, never 403**, byte-identically to
  an unknown id.
- It is not itself rate-limited: it is one `UPDATE`, and the spend it unlocks
  is bounded by `screening_process` on the call that does the work.

> **The retry window will be bounded by `ret_batch_item_days` (90) once Phase
> B's retention sweep lands.** After that window an item's input text is gone
> and it is no longer retryable. That coupling is the whole justification for
> retaining the text in the first place, and it is stated here and in
> `SCREENING.md` §7 rather than discovered.

## 7. Runbook

**"A customer says they are getting 429s."**
1. `GET /metrics` with the admin key; look at
   `veritas_rate_limit_decisions_total{decision="denied"}` and read the `rule`
   and `scope` labels. That tells you *which* bound they hit — the response
   body deliberately will not.
2. `scope="ip"` denials across many different emails usually mean
   `rate_limit_trusted_proxy_hops` is wrong for the deployment (§3), not that
   anybody is attacking. Every caller sharing one bucket looks exactly like a
   spray.
3. `scope="org"` on `screening_process` means a client loop. The wired UI
   stops its driver on any error, so a customer seeing this repeatedly is
   probably running their own integration.

**Raising a limit** is a config change (`DEE_RATE_LIMIT_*` or `config.yaml`)
plus a restart. Counters are keyed by window, not by limit, so a raise takes
effect on the next request within the current window.

**Turning the limiter off is not an option in production.** `rate_limit_enabled:
false` is refused at boot when `env=prod` — the sixth such refusal, alongside
the missing admin key, prod-on-SQLite, an insecure session cookie, a wildcard
CORS origin and a capture email provider. An unthrottled OTP endpoint on a
public host is the same class of thing as a fail-open admin plane.

**Clearing counters** (an operator locking themselves out during a demo):
delete the rows for that bucket from `rate_limit_counters`, or wait out the
window — `Retry-After` on the refusal says exactly how long. Phase B's sweep
will retire rows automatically under `ret_rate_limit_days`; until then a new
window for the same key purges the previous one on write.

## 8. Deliberately not here

- **Sliding windows / token buckets** (§2).
- **Distributed limiting, Redis.** One database is the coordination point until
  there is a second service.
- **A blanket per-request limit.** `rate_limit_default_per_minute` from the
  PI-8 sketch was dropped rather than deferred: it would have covered exactly
  the `/auth/*` routes that §1 already limits by name, and an enforced-nowhere
  knob costs more than it buys.
- **Alerting.** `/metrics` is scrapeable; wiring a scraper and thresholds is a
  deploy-time concern (S8.6).
- **A per-item retry counter.** A permanently-broken item fails identically
  each time at the organisation's own cost, and that cost is already bounded.
