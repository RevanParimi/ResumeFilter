# OPERATING.md — limits, metrics, retention and the runbook

**Sprint:** S8.3, Phase A (2026-08-10) + Phase B (2026-08-11) · **Spec:**
[historical design in Git](https://github.com/RevanParimi/ResumeFilter/blob/54804988f3ead83d727754e4361266a4322655c4/docs/superpowers/specs/2026-08-10-s83-operating-safely-design.md)
**Audience:** whoever runs this service for a paying customer.

§§1–7 are Phase A: what is limited, how it is counted, the 429 and the runbook.
§§8–10 are Phase B: the retention sweep, the DPDP request queue and the
published grievance officer. §11 is what was deliberately left out of both.

**Everything in this document is live.** Where a section describes something
that has to be *invoked* rather than something that runs on its own, it says so
in those words — §8 is the one that does, because there is no scheduler.

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

**It counts calls, not items,** and the check runs *before* the ownership read
and *before* the claim. So a call that screens nothing — the UI's terminating
poll, a `process` on a finished batch, a guessed batch id — costs exactly what
a five-item call costs. That is the price of two properties worth more than the
accounting: counting after the ownership read would make a refusal on somebody
else's batch id distinguishable from a refusal on your own, and counting after
the claim would let a refused call strand the items it had already claimed in
`processing` until the claim timeout expired. The overhead in practice is one
no-op call per batch — 101 calls for a 500-resume batch — so 400/hour still
leaves room for four full 500-resume batches an hour. Both consequences are
pinned by tests in `tests/test_ratelimit_spend.py`; move the check and they
fail.

The ASR rule fires **only when audio is present**: a typed interview answer
costs nothing and must not consume a transcription budget.

### Raw HTTP body budget

`max_request_body_bytes` defaults to **32,000,000 bytes** for the entire HTTP
body, including all batch items, JSON syntax, ignored fields and whitespace.
Set it in `config.yaml` or override with `DEE_MAX_REQUEST_BODY_BYTES`; it must be
positive. Restart the application to apply a changed budget. Existing per-item
text/base64/PDF limits still apply.

The ASGI ingress gate runs before JSON/model validation, authentication and route
work. A declared over-budget Content-Length refuses without reading a body;
missing/underreported lengths still count actual received bytes. Equality is
accepted. Over-budget requests return HTTP **413**, with detail
`request body exceeds max_request_body_bytes=<limit>`, before PDF/provider/store
work. Split a large batch into smaller registrations or choose an appropriate
deployment budget. Refusal never silently truncates or partially registers a batch.

Request IDs and configured CORS apply to refusals. CORS preflights can finish
without consuming a body. Disconnect during ingress stops before routing and
attempts HTTP 400 with `request_body_incomplete`; the disconnected client may
never receive it. Cancellation propagates. Transport read timeouts are unchanged.

This bounds raw bytes per request. Server-owned ASGI event buffers, temporary
copies, JSON/decoded objects and simultaneous requests have separate memory
costs; this is not an RSS or global concurrent-upload bound. Remaining SQL/SMTP
work belongs to
[R4-S2-T3](docs/delivery/PI-R4.md#r4-s2-t3--bound-requests-and-move-blocking-work-off-loop).

### PDF execution budget

`pdf_max_concurrent_parses` defaults to **2** per service/application process.
Set it in YAML or with `DEE_PDF_MAX_CONCURRENT_PARSES` (positive; restart to
apply). Resume uploads, batch registration, evaluation and candidate document
parsing share this admission budget. Batch files parse sequentially before any
registration writes. Text resumes retain their normal path during saturation.

There is no waiting queue: full capacity returns HTTP **503** with detail
`pdf_capacity_exhausted` and `Retry-After: 1`. Shutdown closes admission with
`pdf_executor_closed`. Retry after capacity returns; a refused registration has
saved no partial batch. Parser timeout/invalid-file errors keep the existing
422 resume / 400 verification-document behavior and safe details.

Parsing runs in bounded supervisor threads, each retaining the disposable child
and its existing per-parse input/page/work/decoded/output/memory/deadline limits.
Task cancellation signals the supervisor and propagates immediately; admission
stays occupied until its child is killed/reaped and pipes close. The child wait
checks cancellation at intervals of at most 50 ms, apart from process launch,
decoding and cleanup. Service cleanup stops admission, signals active work and
joins these threads before owned SQL disposal. Normal server shutdown first
drains in-flight HTTP requests; there is no new whole-batch deadline. A transport
disconnect alone does not
guarantee application-task cancellation; accepted work can finish within its
existing deadline. No database sessions cross threads.

The budget is per process, not a global RSS or concurrent-body bound. Each
supervisor also uses two bounded pipe-I/O threads. Direct synchronous parser
and verification-service callers retain caller-owned scheduling and the same
per-parse limits; use the service's async entry points for shared admission.

### Authentication code execution budget

`auth_code_max_concurrent_requests` is positive and defaults to **2** per
service/application process. Its queue-free workers handle the entire signup/
login-code operation, including organization-name checks and store-owned SQL
sessions. No live SQL session, HTTP Request or Response crosses threads.
Full capacity returns **503** `auth_code_capacity_exhausted`; closed admission
uses `auth_code_executor_closed`. Both include `Retry-After: 1`, before account
lookup, rate-counter or email work. The browser explains capacity refusal.

`auth_code_wait_seconds` defaults to **20**, must be finite/positive, and bounds
the caller's asynchronous wait. Configure these settings in YAML or with
`DEE_AUTH_CODE_MAX_CONCURRENT_REQUESTS` / `DEE_AUTH_CODE_WAIT_SECONDS`, then
restart. The wait budget does not kill a SQL/mail operation or promise rollback.
Timeout returns the existing generic **202** accepted body, without claiming
delivery. A different status after slow mail would disclose which addresses
have an account. Local-only echo remains guarded and is absent after timeout.

Do not automatically replay an uncertain code request. An email may arrive
later; enter that code if it does. The browser says this for every ordinary
acceptance. Cancellation propagates to the caller; cancellation and timeout
retain the admission slot until the original operation actually finishes.
Service cleanup closes admission and joins accepted operations before owned SQL
disposal. It cannot safely kill Python threads; existing driver/SMTP socket
timeouts apply, and normal server shutdown first drains HTTP requests. This is
not a whole-operation/drain deadline, a global RSS budget or a durable mail queue.

Code redemption has its separate budget below; session-management handlers and
remaining SQL boundaries stay under [T3C](docs/delivery/PI-R4.md#r4-s2-t3c). Direct synchronous auth
service callers retain caller-owned scheduling. This does not configure or send
live email.

### Contact code execution budget

`contact_code_max_concurrent_requests` defaults to **2** per Services/application
process and must be positive. `POST /portal/verifications` uses this dedicated
queue-free pool for the entire start/resend operation, including its owning SQL
sessions and configured mail. Self-attestation shares that same entry point.
The auth-code pool remains separate; both use the same execution mechanics.
No live Session, HTTP Request or Response crosses threads. After the existing
principal/CSRF gate, saturation returns **503** `contact_code_capacity_exhausted`
and closed admission returns `contact_code_executor_closed`, with `Retry-After: 1`,
before verification-service SQL or mail.

`contact_code_wait_seconds` defaults to **20** and must be finite/positive.
Configure YAML or `DEE_CONTACT_CODE_MAX_CONCURRENT_REQUESTS` /
`DEE_CONTACT_CODE_WAIT_SECONDS`, then restart. A caller wait timeout returns
**504** `contact_code_pending`, without a code or success DTO. The operation may
still send/commit. Refresh the candidate's contact status, choose the saved
pending record and enter any delivered code before requesting another. The UI
explains this uncertainty and never automatically replays the start/resend.
Confirmation still proves contact control only; ownership, consent, erasure,
cooldown and guarded local echo remain.

Cancellation propagates to the caller; cancellation and timeout retain capacity
until actual completion. Cleanup closes both pools and joins accepted work before
SQL disposal. Threads cannot safely be killed, SMTP cannot be recalled, and an
HTTP failure does not promise rollback. Existing SQL/SMTP driver/socket limits
apply; no whole-operation, server-drain deadline or durable queue is added.

SMTP retains the existing candidate-locked transaction (SQLite's writer lock).
Competing writes, including erasure, may wait for it; an erasure that follows
activation removes its challenge. Principal resolution/session touches now use
the separate budget below; confirm/list/other handler SQL remain C3. This does
not make every authenticated write nonblocking. Direct
synchronous verification callers still own scheduling. Validation uses capture
providers and scratch stores, not live delivery.

### Request principal resolution budget

`auth_resolution_max_concurrent_requests` defaults to **8** per Services/app
process. This separate queue-free pool runs complete `AuthService.resolve` and
`resolve_any` calls for all four request gates, including session/key lookups and
periodic last-seen writes. Eight accommodates the current UI's concurrent
batch/summary/queue/driver requests; it is not a production throughput guarantee.
Only raw credentials and detached principals cross the boundary. Each SQL session
opens, runs and closes on its owning worker; request state and CSRF remain on the
caller. Session precedence over header keys and all existing access rules remain.

`auth_resolution_wait_seconds` defaults to **20**. Capacity must be positive,
wait finite/positive. Set YAML or `DEE_AUTH_RESOLUTION_MAX_CONCURRENT_REQUESTS` /
`DEE_AUTH_RESOLUTION_WAIT_SECONDS`, then restart. Full admission returns **503**
`auth_resolution_capacity_exhausted`; closed admission returns **503**
`auth_resolution_executor_closed`. Wait expiry returns **503**
`auth_resolution_pending`. All include `Retry-After: 1`, without cookies or a
principal reaching the route handler. Refused work does not run the resolver;
timed-out/cancelled work retains its slot until actual completion and may commit
its last-seen touch. The original HTTP action never resumes or replays afterwards.
The browser explains temporary unavailability and manual refresh, including on
session bootstrap; its existing cookie can recover without signing in again.

Full admission can refuse any protected request, including anonymous/header-only
calls. Public liveness/UI remain available. An unrelated protected read needs a
free slot and can still encounter later synchronous route SQL. Actual SQLite/PG
lock tests establish resolver responsiveness, not complete SQL coverage. A
candidate/contact transaction can still hold SQLite's writer lock; a stale
session's worker waits without blocking the event loop, subject to driver limits.

Cleanup joins accepted resolver and code work before disposing owned SQL. Caller
timeout is not a thread kill, rollback promise or hard whole-operation/drain
deadline. Budgets multiply across Services/processes and do not globally cap
memory or DB connections. Resolved principals remain authorization snapshots;
there is no new transaction lock across later revoke/erasure and route execution.
Direct synchronous auth callers own scheduling. Session-management handlers and
other SQL have their own budgets below or remain in [C3C-F/Q](docs/delivery/PI-R4.md#r4-s2-t3c3c).

### Code redemption execution budget

`auth_redemption_max_concurrent_requests` defaults to **2** per Services/app
process, with a separate queue-free pool for all three
`/auth/{candidate,org,admin}/verify` routes. Each worker owns the complete
`AuthService.verify_code` operation: limiter, challenge lookup, address lock,
atomic consume/subject/session commit and SQL session cleanup. Raw credential
values and detached results cross the boundary; cookies are set on the caller
only after confirmed completion. Existing OTP, ownership and erasure rules apply.

`auth_redemption_wait_seconds` defaults to **20**. Capacity must be positive,
wait finite/positive. Configure YAML or `DEE_AUTH_REDEMPTION_MAX_CONCURRENT_REQUESTS`
and `DEE_AUTH_REDEMPTION_WAIT_SECONDS`, then restart. Full/closed admission gives
**503** `auth_redemption_capacity_exhausted` / `auth_redemption_executor_closed`
before limiter or OTP work. Caller wait expiry gives **503**
`auth_redemption_pending`. All include `Retry-After: 1` and set no cookies.

Timeout/cancellation keeps the slot until actual completion; it cannot kill a
thread or promise rollback. A late commit can consume the code and create a
session whose token never reaches the browser. That session keeps its ordinary
TTL and appears in the subject's device list after a fresh successful sign-in.
The browser explains uncertainty and permits a deliberate fresh code request;
it does not retry redemption or send another code automatically. Normal
cooldown/attempt/rate limits still apply. A refused admission has not used the
code; an uncertain response cannot establish that the code is still usable.

Cleanup joins accepted work before disposing owned SQL. Public health/UI and
unrelated admitted reads remain responsive to a held redemption worker; SQLite
writer locks can still delay competing writes. These are per-process admission
and caller wait budgets, not global memory/connection limits or a hard database/
shutdown deadline. Direct synchronous service callers own scheduling. Logout,
session list/revoke have their separate budget below; other SQL remains C3C-F.
This does not close [combined T3 acceptance](docs/delivery/PI-R4.md#r4-s2-t3c3q).

### Session management execution budget

`auth_session_max_concurrent_requests` defaults to **2** per Services/app process.
This separate queue-free pool runs complete logout, own-session list and revoke
operations. Detached principal/id/results cross the boundary; SQL sessions open,
run and close on their owning worker. Authentication/CSRF remain on the caller.
Existing subject/plane isolation and account policy remain. Conditional SQL
updates permit one revocation winner; candidate revoke audit commits with it.

`auth_session_wait_seconds` defaults to **20**. Capacity must be positive and
wait finite/positive. Configure YAML or `DEE_AUTH_SESSION_MAX_CONCURRENT_REQUESTS`
and `DEE_AUTH_SESSION_WAIT_SECONDS`, then restart. Full/closed admission returns
**503** `auth_session_capacity_exhausted` / `auth_session_executor_closed` before
handler SQL. Wait expiry returns **503** `auth_session_pending`. Each includes
`Retry-After: 1`, with no success body or cookie deletion. Confirmed logout clears
both cookies; pending or cancelled operations can still commit later.

Timeout/cancellation keeps admission until actual completion; there is no replay,
thread kill or rollback guarantee. Device errors offer **Refresh devices**;
an uncertain revocation disables another revoke until a saved read succeeds.
Sign-out immediately clears sensitive UI state, waits for its server result
before allowing another sign-in, and reports unconfirmed outcomes. Manual reload
checks whether the retained cookie still represents an active session. A busy
logout has not revoked it; a late committed logout can make it invalid. Do not
infer confirmed revocation from an uncertain response or automatically retry it.

Cleanup joins accepted work before owned SQL disposal. Budgets are per process,
not global memory/connection/request limits or a hard driver/shutdown deadline.
Public liveness/UI and unrelated admitted reads can stay responsive while a
worker waits; SQLite writer locks can still delay competing writes. Principals
remain authorization snapshots, with no new lock against later revoke/erasure.
Direct synchronous callers own scheduling. Other handler/graph/store SQL remains
under C3C-F, and combined bounded-work acceptance remains C3Q. No schema change,
external delivery, live-data cleanup or demo restart is part of this change.

### Operator candidate record execution budget

`candidate_record_max_concurrent_requests` defaults to **2** per Services/app
process. Its separate queue-free pool runs the complete operator candidate
detail/resume-list/report-list GET operations and POST `/candidates/{id}/auth-key`.
Workers own summary/payload/final existence checks and every SQL session; only
store/bound-reader/id arguments and detached results cross the boundary. Operator
authentication and session-CSRF stay on the caller. Other intake/source/rights
SQL is separate work; this pool does not cover all candidate operations.

`candidate_record_wait_seconds` defaults to **20**, finite/positive; capacity
must be positive. Configure YAML or `DEE_CANDIDATE_RECORD_MAX_CONCURRENT_REQUESTS`
and `DEE_CANDIDATE_RECORD_WAIT_SECONDS`, then restart. Full/closed admission gives
**503** `candidate_record_capacity_exhausted` / `candidate_record_executor_closed`
before the owning operation. Wait expiry gives **503** `candidate_record_pending`.
Each includes `Retry-After: 1`, without partial records, a replacement key or
cookies. Missing or observed-erased candidates give the existing generic 404.

Timeout/cancellation retains admission until actual completion. A late auth-key
POST can rotate the credential and invalidate the old key without delivering its
replacement. Do not replay automatically or infer rollback. An authorized operator
can deliberately issue a fresh key after the original work finishes; that fresh
rotation invalidates any late undisclosed key. No saved read can recover plaintext
because only its hash is stored. These are API-only operator routes today; no new
record/key screen or automatic client recovery is provided by this change.

Candidate-row locking serializes first issuance, rotation and erasure. SQLite
uses a write-locking self-assignment preserving the profile update timestamp;
PG uses `FOR UPDATE`. Erasure leaves no orphan/valid erased credential. Final
existence checks refuse observed erasure but remain snapshots, without locking
later deletion, another rotation or HTTP delivery. Independent rotations can
invalidate an earlier delivered key as before.

Cleanup joins accepted workers before owned SQL disposal. This is per-process
admission and caller wait, not a thread kill, rollback guarantee, durable queue,
global memory/connection/request cap or hard DB/shutdown deadline. Health and
unrelated admitted reads can stay responsive while worker SQL waits; SQLite
writer locks still delay competing writes. Direct synchronous callers own
scheduling. No migration, working-data rotation or demo restart is included.

### Candidate intake persistence budget

`candidate_ingest_max_concurrent_requests` defaults to **2** per Services/app
process and `candidate_ingest_wait_seconds` to **20**, finite/positive. Configure
YAML or `DEE_CANDIDATE_INGEST_MAX_CONCURRENT_REQUESTS` /
`DEE_CANDIDATE_INGEST_WAIT_SECONDS`, then restart. One separate queue-free pool
serves admin/employer single uploads and batch processing. After async extraction,
it runs the entire initial candidate/resume/extraction transaction and any batch
generation/retain callbacks. It then acquires admission separately for complete
fingerprint computation, idempotent save, corpus comparison and advisory assessment.
Each worker owns its SQL sessions. Async extraction and evaluation remain on the
caller; this budget does not cover providers.

Full/closed admission gives **503** `candidate_ingest_capacity_exhausted` /
`candidate_ingest_executor_closed`; caller wait expiry gives **503**
`candidate_ingest_pending`. Each includes `Retry-After: 1` without partial IDs,
success or cookies. Timeout/cancellation retains admission until actual completion,
consumes late failure and never replays. A late initial transaction may commit
candidate/resume/extraction and a batch input checkpoint; fingerprinting/evaluation/
report creation does not resume for that abandoned call. Late fingerprint work
may save a signature and finish comparison without resuming evaluation. A full/
closed refusal at the fingerprint boundary can follow a committed resume, so
even an admission refusal does not promise that the upload saved nothing. Do not
infer rollback.

For a batch, uncertainty stops the current process call without marking its item
failed or racing a failure write against the still-running transaction. Earlier
items may already be complete. Read saved batch/queue state after work settles;
deliberately resume processing after the existing claim expires. The checkpoint
pins a retry to the committed resume, including inputs without contact hints.
The existing browser driver stops on the error, explains that saving may continue
and asks for refresh, then Start screening when the row says "not screened yet".
For single uploads, read known saved state and make any fresh upload deliberately:
dedupe requires compatible identity hints and bytes; absent stable identity hints,
another upload can create a second subject. No new idempotency key is provided.

Shutdown joins accepted ingest workers before owned SQL disposal; threads cannot
be killed and driver waits/drain have no new hard deadline. Report/subject SQL
and batch claim/failure/terminal SQL remain outside this budget. Competing SQLite
writers can still block those later synchronous operations; admission is not a
global lock/deadline. Direct
low-level ingest/process callers must supply the shared executor or own scheduling.
No schema change, live-data rotation or demo restart belongs to this change.

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

**The 429 does not distinguish a registered address from an unregistered one**,
and this is load-bearing: `AUTH.md`'s anti-enumeration rule makes signup and
login answer `202` for everyone, and a 429 that appeared only for real accounts
would rebuild that oracle out of status codes. The counter therefore keys on the
**submitted** address and is incremented *before* the has-an-account branch.

Precisely: same status, same body, same header **names**, no `Set-Cookie` on
either. Two things legitimately differ and neither is a function of the address
— `X-Request-ID` is unique per request by design, and `Retry-After` counts down
within the shared window, so two refusals a second apart differ by a second.
Asserted in `tests/test_ratelimit_auth.py` (body *and* headers, added by the
S8.3 review) and in the smoke.

**All three planes share one budget per address.** `bucket_key` is
`salt | rule | scope | identity`; the plane is not in it, so an address gets one
`login_request` allowance across the org, candidate and admin routes. That is
the conservative direction — nobody buys 3× the guesses by rotating planes —
and the cost is that a person who is both a candidate and an org user shares a
single 20/hour allowance, which at 20/hour is not a real constraint. Adding a
per-plane limit later would silently triple the real bound, so the coupling is
pinned by a test.

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
- Another organisation's batch answers **404, never 403**, and is
  indistinguishable from an unknown id: same status, same body. (`X-Request-ID`
  differs on every response by design and carries nothing about the batch.
  Asserted by `smoke_s83a` check 10 and
  `tests/test_screening_batches_api.py::test_another_org_gets_404_never_403`.)
- It is not itself rate-limited: it is one `UPDATE`, and the spend it unlocks
  is bounded by `screening_process` on the call that does the work.

> **The retry window IS bounded by `ret_batch_item_days` (90), since S8.3 Phase
> B.** The sweep clears `batch_items.raw_text` past that window, so a failed
> item older than 90 days is no longer retryable and reports as `skipped`
> rather than `requeued`. That coupling is the whole justification for
> retaining the text in the first place, and it is stated here and in
> `SCREENING.md` §7 rather than discovered. **A capability that silently
> expires is worse than one that never existed**, which is why it is written in
> both directions: the retry justifies keeping the text, and the sweep bounds
> the retry.

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
public host is the same class of thing as a fail-open admin plane. **S8.3 Phase
B adds a seventh**: an empty `grievance_officer_email` (§10).

**Clearing counters** (an operator locking themselves out during a demo):
delete the rows for that bucket from `rate_limit_counters`, or wait out the
window — `Retry-After` on the refusal says exactly how long. Since Phase B the
sweep retires those rows under `ret_rate_limit_days` (7); a new window for the
same key also purges the previous one on write.

## 8. The retention sweep

Eight retention windows were **posture only** until S8.3 Phase B: `/portal/me`
printed them and nothing enforced them. Now they are enforced, and three more
classes joined them.

**The targets are DERIVED from `src/app/portal/retention.py`'s `RETENTION_KNOBS`** —
the same table the candidate portal prints. A sweeper carrying its own list
would let the two drift, and the drift is silent in the worst direction: the
portal keeps promising a window that nothing enforces.
`tests/test_retention_plan.py` asserts set equality in both directions.

| data class | knob (default) | table(s) | keyed on | mode |
|---|---|---|---|---|
| `resumes` | `ret_resume_days` (1095) | `resumes` | `created_at` | delete |
| `profile_sources` | `ret_profile_source_days` (1095) | `profile_sources` | `created_at` | delete |
| `verifications` | `ret_verification_days` (1095) | `verifications` | `created_at` | delete |
| `interviews` | `ret_interview_session_days` (1095) | `interview_sessions` | `created_at` | delete |
| `interview_records` | `ret_interview_record_days` (1825) | `interview_records` | `created_at` | delete |
| `coding_rounds` | `ret_coding_round_days` (1825) | `coding_round_results` | `created_at` | delete |
| `observed_offers` | `ret_observed_offer_days` (1825) | `observed_offers` | `created_at` | delete |
| `audit_log` | `ret_audit_log_days` (2555) | `audit_log` | `created_at` | delete |
| `batch_item_text` | `ret_batch_item_days` (90) | `batch_items` + `screening_item_inputs` | original item `created_at` | **clear** unlinked `raw_text`; **delete** private retry reference |
| `rate_limit_counters` | `ret_rate_limit_days` (7) | `rate_limit_counters` | `expires_at` | delete |
| `login_state` | `ret_login_state_days` (7) | `login_challenges` + `login_issuances` + `auth_sessions` | `expires_at` | delete |

**Eleven classes, fourteen targets.** `login_state` covers expired challenges,
abandoned send reservations and expired sessions. Migration 0027 adds reservations
containing only an opaque ID, hashed address, scope and expiry; normal completion,
failure or erasure deletes them, and later requests purge expired reservations
for that address. The existing retention window also clears abandoned rows.
`batch_item_text` covers the unlinked
copy before ingest and the private resume reference used for retry after ingest.
New batch report saves also bind that reference to report erasure atomically.
Report-only deletion ends unfinished retry even after a worker exit, while
preserving the resume and completed anonymous counts/scalars. Migration 0025
adds this nullable link without inferring historical report associations.

Migration 0026 adds a non-personal erasure counter and an item registration
generation. Candidate/resume/report deletes, including bulk retention, advance
the counter in their transaction. Older unlinked items then require a fresh
upload, including unrelated queued items across organizations. The queue shows
`fresh_upload_required` and a re-upload instruction; retry skips these items.
Their original retention window is unchanged. Already-bound surviving resume
retries and completed counts/scalars remain intact. This limits automatic
recreation; it does not identify or immediately delete unknown personal text.

Upgrade pauses historical raw input and unfinished private references without
report links, preserving their contents. **Downgrade refuses while retained
quarantined input exists** (`screening_input_requires_review_before_downgrade`),
because old code could make it retryable again. Review that data under the normal
batch deletion/retention policy before attempting downgrade; the migration does
not silently remove it. SQLite uses native column removal to preserve child
references. These changes require the migration before running the new code.

**`batch_item_text` keeps the screening item.** The sweep clears unlinked text
and deletes private retry references; it does not delete the referenced resume.
An organisation's record of what
it screened must outlive the text it screened — the same reasoning as
`batch_items.candidate_id` being `SET NULL`. Its eligibility predicate has a
second half (`raw_text != ''`), because the column is already empty on every
successful item and an age-only predicate would report the same rows as
"cleared" every day forever.

**Deleting cascades at the database.** The sweep issues bulk statements, which
bypass SQLAlchemy's ORM-level cascade; what carries it is each FK's
`ON DELETE CASCADE` plus `PRAGMA foreign_keys=ON`. Measured, not assumed —
sweeping a `resumes` row takes its `extractions` row with it, asserted in
`tests/test_retention_sweep.py`.

### Running it — there is no scheduler

**Nothing in `src/app/` runs this on a timer.** If nobody invokes it, nothing is
deleted. Two doors, one implementation (`run_sweep`):

> **Deploying? `DEPLOY.md` §5 is the cron.** Shipping this service without
> wiring one means the portal keeps telling every data principal that eleven
> classes of their data are purged on a schedule while nothing ever invokes the
> purge. S8.6 made that a named step in the go-live checklist rather than
> something an operator has to infer from this section.

```bash
# PREVIEW (the default). Counts, deletes nothing.
curl -XPOST -H "X-API-Key: $KEY" $HOST/admin/retention/sweep -d '{}'

# DELETE. The explicit flag is the point.
curl -XPOST -H "X-API-Key: $KEY" $HOST/admin/retention/sweep -d '{"dry_run": false}'

# The cron's / operator shell's door. Same refusals, same report.
python -m app.retention.sweep            # preview
python -m app.retention.sweep --apply    # delete
```

- **`dry_run` defaults to `true`.** This is the most destructive call in the
  repo, and an empty body is the easiest thing to send by accident.
- **Dry-run parity is guaranteed by construction**: `affected` is the same COUNT
  in both modes and only the write is skipped. A preview that disagrees with the
  action is worse than no preview.
- **`retention_sweep_enabled: false` refuses a real run** — `409
  retention_sweep_disabled` at the route, exit code `2` at the CLI. A *dry run*
  still works, because a count is safe and is how an operator sees what would go
  before turning the knob on.
- **`sweep_max_rows_per_class` (10000) bounds one invocation.** The report says
  `truncated: true` rather than pretending it finished; run it again. Precisely:
  it bounds each **target**; `login_state` has three and `batch_item_text` has two,
  so a single run can move up to 3× and 2× the cap respectively. The cap bounds how long
  one statement holds locks, which is a per-table property.
- **The CLI's report is the LAST line of stdout**, and it is JSON. This process
  shares stdout with the structured log, so the stream is a sequence of JSON
  documents — fine for `jq`, and `json.loads` of the whole buffer will raise.
- `veritas_retention_deleted_total{data_class=...}` counts real runs only. A dry
  run moves nothing, because counting intentions would make "how much have we
  deleted" unanswerable.

**`/portal/me`'s `sweep_active` is derived from `retention_sweep_enabled`.** It
is no longer a literal, and it must never become one again: the portal would
keep telling every data principal that no mechanical purge runs while the cron
ran one.

## 9. The DPDP request queue

`data_principal_requests` holds two kinds — `correction` and `grievance` — with
one lifecycle: filed by the subject, reviewed by an operator, decided with a
written reason, disclosed back.

| Route | Plane |
|---|---|
| `POST /portal/corrections` | candidate |
| `POST /portal/grievances` | candidate |
| `GET /portal/requests` | candidate (their own, both kinds) |
| `GET /admin/requests?status=open` | admin |
| `POST /admin/requests/{id}/resolve` | admin |

**`status` and `applied` are two facts.** `status` is what the operator decided
(`resolved` | `rejected`); `applied` is whether that decision changed stored
data — false for every grievance, false for an `email` correction handled out of
band, true only when a value moved.

**A CORRECTION NEVER REWRITES AN EXTRACTION.** An `extractions` row records what
a document said, and the subject of a correction request is exactly the person
with an incentive to edit a claim that got flagged. A resolved correction may
touch the candidate's own identity columns and nothing else.

**Only `full_name` is auto-appliable.** `email` and `phone` are refused for
auto-apply, and the refusal names the consequence: both are hashed into the
candidate dedup keys, and `email_hash` is additionally the portal login
credential, so changing either can merge two people's records or move an
account's login address. `other` names no single stored field. All four can
still be **resolved** with a written explanation — the mechanism is complete for
every field; auto-apply is a convenience for the one where it is safe.

**Every decision needs a reason.** A blank `resolution` is a 422, including on a
rejection: DPDP's mechanism is request-review-decide-**record**-disclose, and a
refusal the subject cannot act on is the one thing a grievance process must
never be.

**Resolving twice is a 409, not a 422.** The store's conditional `UPDATE` on
`status = 'open'` is the guard, so two operators clicking Resolve at the same
moment produce one decision.

Both the submission and the decision are audited onto the **subject's own**
`GET /portal/access-log`, with `entity_type="data_principal_request"`. The
subject is told the *kind* of decider (`operator_key` / `admin_user`), never a
person's identity.

Submissions are rate-limited by `request_submit` (10/hour per candidate),
covering **both** candidate writes on one budget. The limit is charged *before*
validation: a typo costs one of ten complaints an hour, which is the smaller
harm than an endpoint a stuck client can hammer forever with a body that never
validates.

## 10. The grievance officer

```yaml
grievance_officer_name: ""
grievance_officer_email: ""     # PROD REFUSES TO BOOT when empty
grievance_officer_phone: ""
grievance_response_days: 30
```

**`GET /grievance` is PUBLIC** — it is in `PUBLIC_PATHS`, which is the reviewable
act that widening that set is meant to be. DPDP requires the mechanism to be
*published*, and a contact reachable only after login is not reachable by
someone whose complaint is that they cannot log in. It discloses four
operator-chosen config fields and reads nothing about any data principal. It is
also echoed in `MyData.grievance` so the portal shows it in context.

**Prod refuses to boot with an empty officer email** — the seventh refusal. An
unpublished contact would make `GET /grievance` a 200 that says nothing, which
is worse than a 404 because it looks answered.

`grievance_response_days` is the promise on that page. Nothing enforces it
mechanically; it is what an operator has committed to, and `GET
/admin/requests?status=open` ordered oldest-first is how they keep it.

## 10a. The signal-quality harness (PI-9, S9.1)

Does any advisory number predict what a human concluded? Full treatment in
`SIGNALS.md`; the operational surface is:

```bash
# the route -- admin plane, no org variant (cross-tenant by construction)
curl -H "X-API-Key: $KEY" "$HOST/admin/signal-quality?source=outcomes"

# the CLI -- same shape as the retention sweep, and for the same reason:
# there is no scheduler anywhere in app/, so this is invocable, never a daemon
python -m app.signal_quality.report --source outcomes
```

**Exit codes**, because a cron is the caller nobody is watching when it goes
wrong: `0` ran and printed the report as the LAST line of stdout as JSON; `3`
the database is not migrated -- one sentence on stderr, no traceback, and
nothing was read. Same treatment the retention sweep got in S8.6, applied here
from the start rather than after an operator found it.

**Expect refusals, and read them as the tool working.** Below
`min_signal_quality_samples` (default 30), on a one-class sample, or for a
signal this label source cannot score, the signal reports why and carries no
numbers at all. Every `depth.*` signal refuses against the default `outcomes`
source today and will until real organisations submit ledger interview records
-- that is the honest state, not a fault.

**It changes nothing.** No score, no band, no threshold, no decision. Advisory
analysis only.

## 10b. Dependencies: the lock, and the refresh ritual

`requirements.txt` is the **lock** — every direct dependency pinned with `==`.
`pyproject.toml` declares the **ranges the app supports**. CI
(`.github/workflows/ci.yml`) and the production image (`Dockerfile`) both
install the lock, so CI, a developer machine and a shipped container are the
same three things.

**Why it is pinned.** Every entry was an unbounded `>=` until 2026-08-24, when
FastAPI 0.141 deleted `fastapi.dependencies.utils.get_flat_dependant`. CI
resolved 0.141.1 while the development machine had 0.138.0, and five test
modules failed at **collection** time in CI while 2086 tests were green
locally. Local green proved nothing about CI. The same unbounded resolution
reached the `Dockerfile`, which meant two image builds a week apart could ship
different frameworks into production.

**An unrefreshed pin is its own risk.** A frozen dependency stops receiving
security patches, so this is a ritual with a cadence, not a one-time act:

```bash
# 1. relax the pin(s) you want to move -- one, or all of them
# 2. resolve
pip install -U -r requirements.txt
# 3. the suite must be green
pytest -q
# 4. plus the smokes covering whatever the upgrade touches
python scripts/smoke_s92.py
# 5. re-pin to exactly what step 2 resolved, in a commit that changes
#    NOTHING else -- so `git log` shows the upgrade as its own reviewable act
```

`tests/test_requirements_pinned.py` fails the build if a pin goes unbounded,
drifts outside pyproject's range, loses an extra (`uvicorn[standard]`,
`psycopg[binary]` — both change what is installed), or if the two files stop
describing the same dependency set. It found a real defect on its first run:
`sqlalchemy`, `alembic` and `psycopg` were in `requirements.txt` and **missing
from `pyproject.toml`**, so `pip install -e .` built an app that could not
import — sqlalchemy alone is imported by 31 modules under `src/app`.

**Known limit.** Only the 18 **direct** dependencies are pinned; transitive
packages still float. A full `pip freeze` lock would close that too, at the
cost of a file nobody can hand-edit. This is the deliberate middle.

**Already proven, not yet taken:** the full suite is green under
`fastapi==0.141.1` (measured before the pin landed), so that bump is low-risk
whenever someone wants to run the ritual above.

## 10c. The local sign-in echo (`login_otp_debug_echo`)

Signing in locally means a six-digit code, and the only local mail provider is
`capture`, which writes it to a file. Reading that file is where the friction
lives — and worse, it invites an ORDERING mistake with no visible symptom:
every press of **Send code** mints a new code and kills the previous one, so a
code copied out of the file *before* the click is already dead when it is
typed. `invalid_code` is deliberately identical for expired, wrong and
too-many-attempts (§4 makes the same argument for the 429), so the screen
cannot tell you which of those just happened. Three sessions were lost to that
exact loop before this knob existed.

With `DEE_LOGIN_OTP_DEBUG_ECHO=true` **and** `env=local`, the 202 from every
signup/login carries `debug_code`, and the UI fills the six boxes and submits.
Typing an address is the whole flow; no file is opened.

Both halves of the guard are load-bearing, and the knob is refused three ways:

| Guard | What it stops |
|---|---|
| `env == "local"` **and** the knob, at `_request_code` | The one helper all five code-issuing routes share, so the echo cannot be live on one plane and missing on another. |
| Boot refusal 9 (`src/app/core/boot.py`) | A prod config that *intends* to leak OTPs dies at boot instead of sitting armed behind an `env` check nobody rereads. |
| `scripts/_smoke.py`'s third pin | `.env` is read by `Settings` itself, so a developer's local knob would otherwise change what every smoke measures. |

**It is an enumeration oracle, by construction.** A code comes back only when
one was really sent, so the body distinguishes a registered address from an
unregistered one — precisely what the uniform 202 exists to hide. That is
acceptable only because it cannot leave a laptop.

Inside `login_otp_cooldown_seconds` no code is minted (the previous one is
still live), so the 202 carries no `debug_code` and the UI leaves the boxes
alone rather than blanking digits already typed.

### The fixed test code (`login_otp_static_code`)

The echo above removes the *lookup*; this removes the *rotation*. With it set,
every minted login code is the same known string, on every plane — so local UI
testing types the same six digits all session, and a scripted click-through
needs no capture-file read at all.

```bash
# local only; never in config.yaml
DEE_LOGIN_OTP_STATIC_CODE=000000 uvicorn app.main:app
```

**IT IS A CREDENTIAL BYPASS, NOT A DEBUG AID.** The echo reveals a code that
was genuinely sent to a real address. This *replaces* the code with one the
operator already knows, so anyone holding it signs in as **any account on any
plane**. It is the most dangerous setting in this file, and it is guarded
accordingly — three ways, because one check is a check nobody rereads:

1. **`env=local` or it does nothing.** `mint_code_for` ignores it otherwise
   and mints a real random code (`app/auth/challenges.py`).
2. **Prod refuses to BOOT with it set** — the 10th launch refusal, alongside
   the missing admin key, prod-on-SQLite, an insecure session cookie, wildcard
   CORS, a capture email provider, an empty grievance officer, and the debug
   echo. A config that intends to disable authentication must die loudly
   rather than sit armed.
3. **`config.yaml` never ships it armed**, asserted by
   `tests/test_static_test_otp.py::test_the_shipped_config_does_not_arm_it`.

**One mint door, pinned by a test.** `mint_code_for` is the only production
caller that mints a login code, and a test fails if a second appears or if any
production code calls the raw `mint_code`. Without that, the `env=local` rule
would be applied at one entry point and not the other — the defect shape this
repo has found in every PI review.

**It must be exactly `login_otp_length` digits** (6 by default) or the app
refuses to construct. A five-digit static code would mint something the verify
path rejects, and the developer would read `invalid_code` and go hunting
through the auth flow instead of looking at their own config.

**The cooldown and TTL still apply.** The digits stop rotating; the challenge
does not become immortal. A re-request inside `login_otp_cooldown_seconds` is
still refused, and the row still expires on `login_otp_ttl_seconds` — you
simply get the same digits back next time. If you want long-lived sessions
rather than a long-lived code, raise `session_ttl_minutes` instead.

## 10d. Reading the logs (PI-9, S9.3)

Until S9.3 this runbook could only count. Every entry above says `GET /metrics`,
and a counter answers "how many 403s" — it cannot answer **"why did *this*
customer get one"**, which is the question a staffing agency actually asks.

The reason was structural, not neglect: `api/routes.py` raises `HTTPException`
138 times and binds no logger, and Starlette answers `HTTPException` itself, so
none of those refusals ever reached the 500 handler. Every 4xx veritas issued
left exactly one artifact — a status integer in the `access` line. Two boundary
handlers in `app/main.py` now log all of them, and `routes.py` is still not
edited: a refusal is logged **because it happened**, not because whoever wrote
it remembered to.

**The vocabulary.** One refusal line per failed request, *alongside* the
`access` line that has always been emitted — two lines, correlated by
`request_id`. The refusal line carries the *why*; the access line the *timing*.

| event | level | when |
|---|---|---|
| `access` | info | every request, with `status` and `duration_ms` |
| `request_refused` | warning | a 4xx on a route that matched |
| `request_refused` | info | a 404/405 that matched nothing (scanner noise) |
| `request_refused` | error | a 5xx HTTPException, e.g. `503 email_unavailable` |
| `request_invalid` | warning | a body Pydantic rejected; `fields` says where |
| `unhandled_error` | error | a bug — carries the full traceback |
| `integrity_race` | info | a store lost an insert race and took the winner's row |

**"A customer says they got a 403."**

1. Ask for the `X-Request-ID` from the response — every response carries it, so
   a customer quoting it is handing you an exact grep key:
   ```bash
   grep '"request_id": "req_de37c5ef75db"' server.log
   ```
2. The `request_refused` line carries `reason` — the same detail string the
   caller received — plus `route` (the template) and `method`.
3. **No `request_refused` line at that id means it was not a refusal.** Look for
   `unhandled_error` at the same id: that is a bug, and the traceback is on it.

**"Is anything failing that nobody has reported?"**

```bash
grep '"event": "request_refused"' server.log | grep '"level": "error"'
```

5xx refusals only. `503 email_unavailable` here means the email provider is
down and **logins are failing for everyone** — §10c and the email seam notes
say why that refuses rather than degrades.

**A sudden flood of `integrity_race`** is the one to watch by rate, not by
event. Each one is handled correctly and individually harmless; a thousand a
minute where there was one a day means real contention, most likely two clients
signing up the same org name or a retry loop.

**What is deliberately NOT logged: the `input` of a rejected body.**
`RequestValidationError.errors()` carries the caller's raw submitted value, and
for this product that is resume text, candidate addresses and login codes. The
`request_invalid` line logs `fields` (the locations) and never the values. If
you are ever tempted to add `errors=exc.errors()` to that handler, run
`tests/test_error_logging.py::test_a_validation_failure_never_logs_the_submitted_value`
first — it exists to stop exactly that, and it was checked against the leaking
version rather than assumed to work.

**Log labels are bounded on purpose.** `route` is the route TEMPLATE, never the
raw path, and anything unmatched collapses to `__unmatched__` — the same rule as
§5's metric labels, for the same reason: a scanner walking random URLs must not
become unbounded log volume. Unmatched paths also log at `info` rather than
`warning`, so bot noise does not train you to ignore the channel that carries
real refusals.

**Asserting on logs in tests.** There are two seams and they are NOT
interchangeable (`tests/conftest.py`): `log_events` shows what a call site
*passed*; `log_output` renders through the real processor chain and shows what
*leaves the process*. Egress claims ("no OTP was written") are only valid on
`log_output` — `capture_logs` bypasses the processors, which is how the OTP-leak
guard read as green for eight PIs while asserting a string was absent from an
empty string.

## 11. Deliberately not here

- **Sliding windows / token buckets** (§2).
- **Distributed limiting, Redis.** One database is the coordination point until
  there is a second service.
- **A blanket per-request limit.** `rate_limit_default_per_minute` from the
  PI-8 sketch was dropped rather than deferred: it would have covered exactly
  the `/auth/*` routes that §1 already limits by name, and an enforced-nowhere
  knob costs more than it buys.
- **Alerting.** `/metrics` is scrapeable; wiring a scraper and thresholds is a
  deploy-time concern. **S8.6 did not deploy** — it made the system correct to
  deploy and stopped there, so this is still open and now belongs to the
  user-gated go-live in `DEPLOY.md`, not to a sprint.
- **A per-item retry counter.** A permanently-broken item fails identically
  each time at the organisation's own cost, and that cost is already bounded.
- **Any action taken on a signal-quality measurement.** The harness measures;
  acting on what it measures is a human decision, and calibration stays
  conservative and advisory (§10a, `SIGNALS.md`).
