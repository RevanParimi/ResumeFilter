# UI.md — what to build, and what it can actually call

**Date:** 2026-08-02 · **Audience:** whoever designs the veritas UI (externally,
via claude.ai/design — this repo ships no HTML, templates or JS toolchain).
**Read order:** `docs/superpowers/specs/2026-08-01-veritas-gtm-positioning.md`
(what we sell) → this → `AUTH.md` (how to log in) → the live `/openapi.json`.

**Measured against `main` at `a9b8e59`, 83 routes.** Every endpoint listed here
was enumerated from the running app, not remembered. Each is tagged:

| Tag | Meaning |
|---|---|
| ✅ | exists today, callable now |
| 🔜 | **does not exist** — lands in S8.4, the next sprint |
| 🚫 | exists but is **not for this UI** (see §8) |

---

## 1. The vision, in one paragraph

Veritas is being sold as **pre-screen fraud detection for Indian IT hiring** —
not as a talent platform. The buyer is a staffing/recruitment agency of 50–500
people. Their pain is that a meaningful share of the resumes they forward to
clients are embellished, AI-generated, farmed from a template shop, or belong to
someone who will send a proxy to the interview. Today they find that out *after*
their client does, which costs them the account.

**The product promise is one sentence: upload the resumes you already have, and
get back a ranked, reasoned list of who to look at harder.** Everything else in
this system — the evaluation ledger, comp intelligence, job matching, the
interview engine — is real, and is deliberately **off the pitch**.

So the UI has exactly one job to do well: **make that list legible to a
non-engineer in under a minute.** A staffing delivery head is the user. They are
not technical, they are busy, and they will judge the product on whether the
risk list tells them something they did not already know and can act on.

### The tone the product requires

Everything veritas emits is **advisory**, and every response literally carries
`advisory: true` and `human_review_required: true`. This is a legal and ethical
posture, not modesty:

- **Never auto-reject. Never rank someone as "fake".** The UI must never present
  a verdict as a decision. It presents a *reason to look closer*.
- **Show the reasoning, always.** Every assessment carries a `reasoning` string
  and component breakdown. A risk score with no visible basis is worse than no
  score — it is unchallengeable, and the candidate can never contest it.
- **Confidence is a first-class field, not a footnote.** Most assessments carry
  `confidence` alongside `score`. A high score at low confidence must not look
  like a high score at high confidence. If the UI collapses them, it lies.
- **"Insufficient signal" is a real, common, correct answer.** Bands include
  `insufficient_data` / `insufficient_signal`. Design a good empty state for it;
  it is not an error and it is not a low score.

## 2. THE constraint that shapes everything — read this before designing

**The entire fraud-screen path is on the ADMIN plane today. An org user cannot
reach any of it.**

An organization that self-registers through the new S8.2 flow can log in
successfully and then do *none* of the following:

| The wedge action | Endpoint | Plane today |
|---|---|---|
| Upload a resume | `POST /candidates` | **ADMIN** |
| Read the fraud/depth report | `GET /report/{id}` | **ADMIN** |
| List a candidate's reports | `GET /candidates/{id}/reports` | **ADMIN** |
| Search the talent pool | `POST /talent/search` | **ADMIN** |
| Evaluate ad-hoc resume text | `POST /evaluate` | **ADMIN** |

The org plane's *only* view onto a person is `GET /candidates/{id}/card`, which
is a consent-gated drill-in over ledger/reputation data — **not** the fraud
report.

**Consequence:** the demo the whole GTM rests on cannot be built against today's
API by an org user. S8.4's stated scope (batch upload, cursor pagination,
fraud-screen read-model, OpenAPI) therefore implies something not yet written
down: **the wedge path has to be exposed on the org plane.**

> **RESOLVED 2026-08-05 (§9 Q2) — S8.4 ADDS org-plane routes and LEAVES the
> admin routes alone.** The table above stays true: those admin paths keep
> working and keep their cross-tenant reach, because that is the operator's
> support and debugging view and nothing else provides it. What changes is that
> an org-plane equivalent appears beside each one, scoped to what the caller's
> organisation uploaded (§2.1). Rejected: moving the routes outright — one
> canonical path per action is tidier, but it takes the cross-tenant view away
> from operators, breaks every existing `X-API-Key` machine client, and churns
> the admin-plane tests and all six regression smokes for a cosmetic gain.
> Spec: `docs/superpowers/specs/2026-08-05-s84-ui-integration-surface-design.md`.

### 2.1 The open question S8.4 must answer first — **RESOLVED 2026-08-05**

Candidates are **global and deduplicated by email hash across all organizations**
(S1.1 identity resolution). And:

```
reports    → id, domain, depth_band, candidate_id, body, created_at     ← no org column
candidates → id, email_hash, phone_hash, full_name, created_at, ...     ← no org column
resumes    → id, candidate_id, version, raw_text, text_sha256, ...      ← no org column
```

**Nothing in the schema records which organization uploaded a resume or
commissioned an evaluation.** That was fine while the wedge was operator-run. It
is not fine the moment two staffing agencies both screen the same candidate:

- Does Agency A see the report Agency B paid for?
- If Agency A uploads Priya and Agency B uploads Priya, they dedup to **one**
  candidate row. Whose screening queue does she appear in?
- Does "resume farm / near-duplicate detection" compare across *all* customers'
  corpora — which is a genuine product advantage — while not disclosing *whose*
  resume it matched?

PI-8 §10 lists multi-tenancy as a deliberate non-goal. The wedge forces at least
a partial answer. **This is a product decision, not an implementation detail, and
it should be settled before the UI's screening queue is designed** — because
"my queue" versus "the candidate universe" are different screens.

> **RESOLVED 2026-08-05 — an org sees only what it uploaded**, which is what the
> UI was already designed against and what a staffing buyer assumes is true.
>
> **Ownership is a property of the upload, not of the person.** Candidates stay
> global and deduplicated by email hash — that is S1.1 identity resolution, and
> it is what makes cross-corpus near-duplicate detection worth anything. What
> gains an owner is the *act*: `resumes.org_id` and `reports.org_id`, both
> nullable (every existing row and every admin-plane upload has no owner) and
> both **`ON DELETE SET NULL`**, because an organisation offboarding must not
> destroy a candidate's resume. That resume is the person's data; the only
> cascade permitted to delete it is the candidate's own erasure, which already
> exists.
>
> "My queue" is therefore **derived, not denormalized** — the candidates having
> at least one resume owned by my org — so there is no second source of truth to
> drift out of step with the first.
>
> Answering the three questions above in order: **no**, Agency A does not see
> Agency B's report; Priya appears in **both** queues off one shared candidate
> row, because each agency owns its own upload of her; and near-duplicate
> detection **does** compare across the whole corpus while disclosing only
> *that* a match exists and how similar, never whose (§4.B).
>
> Rejected: a shared candidate universe (cheapest, but "did the other agency see
> the report I paid for?" is the first question a buyer asks and the answer would
> be yes), and one deploy per customer (no schema change, but it hard-codes a
> hosting posture that is still open in GTM §11 and kills the cross-customer
> resume-farm signal outright).
>
> **The enforcement matters as much as the rule.** Four consecutive branch
> reviews (S7.1, S7.2, S7.3, S8.2) each found the same shape: a rule applied at
> one entry point and not the other. So org-plane handlers do not get the option
> — every org-plane read of a candidate, resume or report goes through a scoped
> facade whose methods all take `org_id` first, there is no unscoped read
> reachable from an org handler, and a guard test fails the build if one appears.
> Another org's report is **404, not 403** — indistinguishable, per the S6.4
> cross-candidate and S7.1 verification precedent, since a 403 confirms the
> report exists.

## 3. Auth — fully built, implement exactly this

This part is **done and shippable** (S8.2). `AUTH.md` is the reference; here is
the client contract.

### 3.1 Login

```
POST /auth/org/signup   {email, organization_name}  → 202   ✅
POST /auth/org/login    {email}                     → 202   ✅
POST /auth/org/verify   {email, code}               → 200   ✅
   ← Set-Cookie: dee_session (httpOnly)  +  dee_csrf (readable)
   ← body: {principal: "org", csrf_token: "...", organization_id: "..."}
```

Same three shapes for `/auth/candidate/*` (signup takes `{email}` only) and
`/auth/admin/login|verify` (**no admin signup — operators are created by an
operator**).

### 3.2 Rules the UI must follow

- **Every request needs `credentials: "include"`.** The session is a cookie, and
  the UI is on a different origin. Without this nothing authenticates.
- **Every mutating request** (`POST`/`PUT`/`PATCH`/`DELETE`) must send
  `X-CSRF-Token` equal to the `dee_csrf` cookie value. Miss it and you get
  **403**, not 401 — a distinct failure worth its own error state.
- **`GET /auth/me` on app load** ✅ tells you who you are
  (`{kind, organization_id, session_id}`). A `401` means "show login".
- **`401` anywhere means the session died** — expired (12h), idle (2h), revoked,
  or the account was erased. Redirect to login; do not retry.
- **Signup and login always return `202`, even for unknown addresses.** This is
  deliberate anti-enumeration. **Never render "no account found"** — the UI must
  say "if that address is registered, a code is on its way." Getting this wrong
  re-opens a hole the backend deliberately closed.
- **All verify failures return one `400 {"detail": "invalid_code"}`** — expired,
  wrong and too-many-attempts are indistinguishable on purpose. Show one message.
- **`503 {"detail": "email_unavailable"}`** means no email provider is
  configured. It is a real state in dev/demo and deserves a clear message rather
  than a generic failure.

### 3.3 Sessions / devices ✅

```
GET  /auth/sessions                    → the caller's own live sessions
POST /auth/sessions/{id}/revoke        → 404 if not yours (indistinguishable)
POST /auth/logout
```

`SessionView` = `{id, issued_at, expires_at, last_seen_at, status, user_agent,
current}`. Never a token. Good "signed-in devices" screen on both planes.

### 3.4 One thing the operator must do for you

CORS is **fail-closed and server-side**: the API refuses all cross-origin calls
until the UI's exact origin is added to `cors_allowed_origins`. Wildcards are
refused at boot in prod. Tell whoever deploys the API the UI's origin, or every
call fails in the browser while working fine in Postman.

## 4. The screens

Ordered by what the demo needs. **A → B → C is the entire pitch.**

### A. Screening queue — *the product* ✅ (S8.4 Phase B — `SCREENING.md`)

The one screen that matters. "Here are the resumes you dropped in, ranked by how
much they need a human."

All three prerequisites now exist, on the **org plane** (`X-Org-Key` or an org
session):
- **Batch upload** ✅ — `POST /screening/batches` with
  `{name, domain, items:[{resume_text|resume_pdf_b64}]}`. Registration only
  inserts rows; it evaluates nothing (see the resolved note below).
- **Bounded processing** ✅ — `POST /screening/batches/{id}/process` until
  `remaining` is 0. Poll `GET /screening/batches/{id}` for derived progress.
- **A fraud-screen read-model** ✅ — `GET /screening/batches/{id}/queue`
  returns ranked rows, riskiest first, each already carrying its reason.
- **Cursor pagination** ✅ — `cursor` + `limit` on the batch list and the
  queue; pass `next_cursor` back as `cursor`.

**Two fields a designer would otherwise invent, so they are stated here:**

1. **`reason` is GENERATED, not stored.** It is composed at read time from the
   row's own scalar signals. Render it as the row's one-line explanation — but
   never treat it as an editable or model-authored sentence, and never expect it
   to quote the resume. It cannot: the item stores no free text, because a
   candidate's erasure sets `candidate_id` to NULL and anything stored beside it
   would outlive the person (`SCREENING.md` §5).
2. **An unprocessed row is a NORMAL state, not an error.** `status: "pending"`
   with `risk_score: null` and `reason: "not screened yet"` means exactly that.
   Show it greyed and sorted last. A `failed` row carries a reason **code**
   (`empty_resume`, …) and is retryable — it is not a verdict about the person.

Design it as: batch header (name, count, uploaded-at, progress) → rows sorted by
risk band, each row showing **band · score · confidence · a one-line reason ·
the loudest signal**. Rows must be scannable without opening anything.

> **Ingest is slow and asynchronous in nature.** Each resume is extracted,
> claim-checked, scored across four fabrication subsystems, and (with a live
> model) LLM-assisted. Design for a progress state and partial results, not a
> spinner that blocks until 500 finish.

> **WIRED 2026-08-10 (S8.5).** Screens A, B and C now run against these routes.
> Four things the API's shapes forced, recorded here so a redesign does not
> re-litigate them:
>
> 1. **A queue row carries NO NAME.** `QueueRow` is scalars only, because
>    `batch_items.candidate_id` is `ON DELETE SET NULL` and anything stored
>    beside it outlives the person (`SCREENING.md` §5). Rows are identified by a
>    short id and the screen **says so in a line of prose**; the extracted name
>    appears on drill-in, from the report's `candidate_context`. Do not design a
>    name column here — there is nothing to put in it, and fetching one report
>    per row to find one would defeat a deliberate DPDP property.
> 2. **Screening runs in the browser.** Registration evaluates nothing; the
>    client calls `process` five items at a time until `remaining` is 0. So the
>    UI starts the loop **on upload and never on navigation** (opening a batch
>    is not an instruction to spend money), stops it on any error (there is no
>    rate limiter yet — S8.3), and states plainly that closing the tab pauses
>    the batch and reopening it resumes.
> 3. **No polling timer.** The `process` call is the tick. With no worker, an
>    idle client means an idle batch, and a timer would animate a bar that
>    cannot move.
> 4. **Paging is hidden while screening runs.** The queue's sort key is
>    `COALESCE(risk_score, -1)` and screening an item moves it from null to a
>    score, so mid-run the key is *mutable* — keyset paging is stable against
>    inserts, not against re-observation (`SCREENING.md` §6, the same caveat as
>    the curation queue).
>
> The batches list shows **progress, not risk**: `BatchView.counts` holds item
> statuses only, and there is no per-band count without one `summary` call per
> row.

> **S8.3 Phase A changed two things this screen must handle (2026-08-10).**
>
> 1. **A failed row is now genuinely retryable, and there is a route for it.**
>    `POST /screening/batches/{id}/retry` re-queues *every* `failed` item in the
>    batch and answers `{requeued, skipped}`. It does **not** process them — the
>    client still drives `process` afterwards, exactly as it does after upload.
>    So the sentence this section already carries ("a `failed` row … is not a
>    verdict about the person") is now backed by an action rather than by good
>    intentions. `skipped` counts items whose input text is gone; surface it,
>    because "3 requeued, 1 skipped" is the honest sentence and "4 requeued" is
>    not.
> 2. **The driver loop can now receive a `429`.** `POST .../process` is limited
>    per organisation (400/hour by default), and `POST /auth/*` is limited per
>    email and per IP. The existing rule — *any* error stops the loop — remains
>    correct and now has a named case: on a 429 the UI must **stop and show the
>    wait**, reading the `Retry-After` header rather than retrying. A client
>    that retries into a limiter is the thing the limiter exists to stop.
>    `OPERATING.md` §4 has the response shape; the body is one opaque
>    `rate_limited` on purpose and carries nothing worth branching on.

> **RESOLVED 2026-08-05 (§9 Q3 + Q5) — a batch is a REAL stored object, and
> processing is CLIENT-DRIVEN.** `screening_batches` + `batch_items` (S8.4
> Phase B), so a queue can be named, resumed, summarized and paginated.
>
> There is no worker, no scheduler and no `BackgroundTasks` anywhere in `app/` —
> `POST /candidates` awaits the whole nine-node graph inline — so 500 resumes in
> one request is not physically possible. Upload therefore only *registers*
> items (a row insert, fast), and a bounded `POST /screening/batches/{id}/process`
> does the slow work a few items at a time while the UI polls for progress.
> Nothing is lost on redeploy, and no background execution enters the repo ahead
> of S8.3's observability.
>
> **Batch status is derived at read time, never stored** — progress is a count
> over item statuses (the S7.1 assurance / S7.3 `effective_status` rule). A
> stored status is a fact that goes stale when a process dies and that nothing
> corrects; an item stuck `processing` past a timeout simply reads as `pending`
> again, so a batch interrupted mid-run heals itself instead of wedging.
>
> Rejected: in-process `BackgroundTasks` (nicer UX, but work dies silently on
> redeploy leaving items stuck `processing`), and client-side grouping with no
> stored batch (smallest change, but screens A and C are both built on a batch
> that persists, and there would be nothing server-side to name or resume).

### B. Candidate risk detail — *where trust is won or lost* ✅ (org plane)

`GET /screening/reports/{report_id}` (S8.4 Phase A, org plane, redacted) returns
the full `Report`; `GET /report/{report_id}` is the operator's cross-tenant
equivalent. This is the richest object in the system and the UI's central
rendering problem:

```
Report
 ├ depth_score, depth_band, overall_confidence, summary
 ├ advisory: true, human_review_required: true      ← must be visible, not fine print
 ├ fabrication_risk  {score, confidence, band, components[], reasoning}   ← THE headline
 ├ ai_generation     {likelihood, confidence, band, signals[], reasoning}
 ├ cross_field       {score, confidence, band, findings[], reasoning}
 ├ resume_farm       {score, confidence, band, matches[], corpus_size, reasoning}
 ├ verdicts[]        CoherenceVerdict per claim:
 │                    {claim_text, claim_type, status, coherence_score,
 │                     confidence, reasoning, expected_signals[],
 │                     missing_signals[], evidence[], probes[]}
 └ flagged_claim_ids[], deferred_claim_ids[]
```

Design guidance:

- **`fabrication_risk` is the headline**, and it is a *fusion* of the three
  subsystems below it with a coverage-confidence term. Show the band, then let
  `components[]` explain which subsystem drove it. Never show the four scores as
  four equal peers — one is the conclusion, three are inputs.
- **`missing_signals` is the most useful field in the whole object** and the
  least obvious. It says *what a real version of this claim would have looked
  like and didn't*. That is the sentence a recruiter repeats to their client.
- **`probes[]` are ready-made questions a fake cannot survive.** Surface them as
  copyable text next to each flagged claim — it converts a score into an action,
  which is what makes the tool feel worth paying for.
- **`resume_farm.matches[]` needs care under §2.1** — it may reference resumes
  belonging to another customer. Show *that* a near-duplicate exists and its
  similarity, not whose it is, until the tenancy question is settled.

> **RESOLVED 2026-08-05 (§9 Q4) — the org sees the FULL report,
> counterparty-redacted.** Everything above, including `verdicts[]`,
> `missing_signals` and `probes[]`: those are the fields that convert a score
> into an action, and a headline-only view would strip out both the sentence a
> recruiter repeats to their client and the questions that make the demo land.
>
> The single redaction is `resume_farm.matches[]` → similarity and count, never
> identity, exactly as this section already required — now permanent rather than
> pending, since tenancy resolved the way it did.
>
> **The redaction lives in ONE projection function**, called by both the
> single-report read and the batch queue read-model. Two copies would be a bound
> that holds on one path and not the other — which is verbatim the S7.2
> `claim_ref` finding and the S7.3 transcript finding, the same defect shape two
> sprints running.
>
> §7's rule is unaffected and still binds: a fuller report is not a more
> confident one, and there is still no accuracy claim to make.

> **WIRED 2026-08-10. The outcome section shipped in a second pass the same
> day, once the route it needs existed.** The first pass dropped the four
> verdict buttons and said why in a sentence, because
> `POST /report/{report_id}/outcome` is on the **admin** router and an org
> session gets 401 — four buttons that fail every time would be worse than
> none. That was recorded as a real product gap rather than a UI omission, and
> S8.5 closed it: `POST /screening/reports/{id}/outcome` and
> `GET /screening/reports/{id}/outcomes` are org-plane, so the buttons are back
> and the apologetic paragraph is gone.
>
> **The section states what recording does and does not do**, because a verdict
> button on a fraud screen invites the assumption that it acts: nothing here
> changes the score above it, the candidate's standing, or anything anyone else
> sees. It is written down so the bands can eventually be measured against what
> really happened. Judgements are **kept in order, never overwritten** — a
> reviewer changing their mind after an interview is exactly what a calibration
> harness wants to see — and the history list says, in one line, that none of
> it is visible to the candidate.
>
> Two decisions worth keeping: **the notes box clears on success and is kept on
> failure** (carrying one person's sentence onto the next candidate is how it
> gets filed against the wrong person; retyping after our own 422 is the user
> paying for our error), and **the busy state is per-button** — a spinner on
> all four would be lying about which judgment is in flight.
>
> The three component cards are composed from `fabrication_risk.components[]`
> joined to each subsystem's own assessment — the components carry the weights,
> and the subsystems carry the only prose (`reasoning`) the API produces.
> `resume_farm.matches[]` renders as a **count and top similarity**; the wired
> screen never reads `candidate_id`/`resume_id` at all, so a regression in the
> projection could not surface through it.

### C. Batch summary / "what did we find" ✅ (S8.4 Phase B)

`GET /screening/batches/{id}/summary` → `{batch_id, name, domain, status,
counts, n_screened, by_risk_band, top_signals[], advisory,
human_review_required}`.

A short, screenshot-able roll-up per batch: N screened, distribution across risk
bands, top signals. This is what gets pasted into a WhatsApp group and sells the
next seat. Composed from the same read-model as A.

**It is counts and enum members only — no names, no ids, no prose.** That is
deliberate: a roll-up that quoted its riskiest row would re-open every tenancy
question the read-model exists to close. If the design needs a name on this
screen, it has to come from a drill-in the viewer is entitled to, not from the
summary.

> **WIRED 2026-08-10.** Band shares are computed against **`n_screened`, never
> the upload count**: at 20% processed the remaining 80% is unknown, not
> "insufficient signal", and a percentage over the wrong denominator is the
> quietest way for this screen to lie. `top_signals[]` arrives as the three
> component ids (`ai_generation` · `cross_field` · `resume_farm`) and the UI
> owns the labels.

### D. Candidate DPDP portal ✅ — *compliance is a differentiator, not overhead*

Fully built and callable today. GTM §8 makes the point: in an Indian enterprise
RFP, a working consent architecture is a **selling point**, and correction +
grievance rights are RFP blockers. A demo that shows the candidate's own view is
a real advantage over incumbent BGV vendors.

```
GET    /portal/me            ✅  profile, resumes, sources, interview records,
                                 coding rounds, report refs, consents, identity
                                 assurance, claim evidence, interviews, sessions,
                                 retention policy
GET    /portal/access-log    ✅  every access, org name resolved — the transparency screen
GET    /portal/consents      ✅
POST   /portal/consents      ✅  grant (first-party)
POST   /portal/consents/{id}/revoke  ✅
DELETE /portal/me            ✅  erasure. Everything cascades.
```

Plus identity verification (`/portal/verifications*` ✅), document upload
(`POST /portal/documents` ✅) and AI interviews (`/portal/interviews*` ✅).

**Note:** `/portal/me` deliberately exposes reports as **refs only**
(`{report_id, domain, created_at}`) — the depth-report internals are not
disclosed to the subject in v0. Don't design a candidate-facing risk score.

### E. Roles / requisitions ✅ (org plane, already reachable)

```
GET  /jobs · POST /jobs · GET|PATCH /jobs/{id}   ✅
GET  /jobs/{id}/board    ✅  requisition + comp benchmark + top-N ranked match
POST /jobs/{id}/match    ✅
GET  /dashboard/overview ✅  requisition counts by status
GET  /jobs/{id}/comp · POST /comp/estimate       ✅
```

Genuinely useful and org-authenticated **today** — the only substantial thing the
UI can build against right now without S8.4. But it is **not the wedge**. Treat
it as phase 2 unless a demo needs filler.

### F. Operator/admin console ✅ — build the minimum

`POST|GET|DELETE /admin/users` ✅, `POST /ledger/orgs` ✅, curation queue
(`GET /curation/skills/unmapped` ✅). An internal tool. Do not spend design time
here.

## 5. Endpoint inventory

**Public (14)** — `/`, `/healthz`, `/docs`, `/redoc`, `/openapi.json`,
`/docs/oauth2-redirect`, and the 8 `/auth/*` login routes. ✅

**Candidate plane (15)** ✅ — portal, consents, access log, verifications,
documents, interviews, erasure. All session- or `X-Candidate-Key`-authenticated.

**Org plane (20)** ✅ — jobs/requisitions/matching, comp, dashboard overview,
candidate card, and consent-gated reads of ledger records, coding rounds,
reputation, verification assurance, claim evidence, interview assessments.

**Admin plane (30)** — includes the whole wedge path (§2) plus org lifecycle,
candidate CRUD, profile sources, curation, reports and outcomes.

> **These five counts are the `a9b8e59` measurement and have NOT been
> re-measured since.** S8.4 Phase B added the seven batch routes plus
> `POST /features/materialize`, and S8.5 added two more to the org plane
> (`POST`/`GET /screening/reports/{id}/outcome(s)`). The counts are therefore
> low; the plane *assignments* above are still right. Do not cite the numbers —
> `GET /openapi.json` is the authority, as the next paragraph already says, and
> the two documentation defects this section's own review found were both a
> route's plane being assumed rather than read off the router it is registered
> on.

**Any-session (4)** ✅ — `/auth/me`, `/auth/sessions`,
`/auth/sessions/{id}/revoke`, `/auth/logout`.

**Live contract:** `GET /openapi.json` ✅ is the authority and is generated from
the code. Prefer it over this document wherever they disagree — S8.4 polishes it
specifically so a typed client can be generated from it.

## 6. Consent is query-time and will 403 you

Several org-plane reads are gated on a live consent grant and **return 403 when
it is absent or revoked** — and every attempt is audited either way:

```
GET /ledger/candidates/{id}/records         → needs ledger_read
GET /ledger/candidates/{id}/coding-rounds   → needs ledger_read
GET /verification/candidates/{id}/assurance → needs verification_read
GET /interview/candidates/{id}/assessments  → needs interview_read
```

**403 here is a normal state, not an error.** Design it as "the candidate has not
shared this with you" with a request-access affordance — not a red failure toast.
`GET /candidates/{id}/card` ✅ already models this well: it returns **200 with
per-section status**, so some sections populate and others say "not shared".
Mirror that pattern everywhere.

## 7. Numbers the UI must not overstate

Stated plainly because a confident-looking UI can make an honest backend lie:

- The thresholds and weights behind every band are **calibrated conservatively
  and have not been validated against real hiring outcomes.** The calibration
  harness is PI-9, gated on real orgs submitting outcomes. Until then these are
  reasoned defaults, not measured accuracy.
- There is **no accuracy claim** to put in the UI. Do not design a "97%
  accurate" badge, and do not design anything that implies a benchmark exists.
- `insufficient_data` / `insufficient_signal` will be common on thin resumes.
  That is the system being honest.

## 8. Do not build

- 🚫 **The evaluation ledger as a feature.** Cross-company reputation is the most
  impressive subsystem here and is deliberately **off the pitch** (GTM §2) — it
  is worth zero to customer #1 and it raises questions a first meeting should not
  spend time on. The endpoints stay; the screens do not get built.
- 🚫 **Anything that auto-rejects, auto-shortlists, or hides a candidate.**
- 🚫 **A candidate-facing risk score** (§4.D).
- 🚫 Payments, payroll, contracts, sourcing/outreach, native coding assessments —
  standing non-goals.
- 🚫 Passwords, SSO, social login — login is email OTP only, by decision.

## 9. Open questions — **ALL FIVE CLOSED 2026-08-05**

Settled with the user while shaping S8.4. Full reasoning and the rejected
alternatives are in
`docs/superpowers/specs/2026-08-05-s84-ui-integration-surface-design.md`; each
answer is also recorded inline in the section it governs.

| # | Question | Answer | Where |
|---|---|---|---|
| 1 | Tenancy — does an org see only its own uploads? | **Yes.** Ownership is a property of the upload (`resumes.org_id`, `reports.org_id`, nullable, `SET NULL`); candidates stay global and deduplicated. Enforced by a scoped facade + a guard test, and another org's report is **404**. | §2.1 |
| 2 | Move the wedge path to the org plane, or add equivalents? | **Add** org-plane routes; the admin routes stay as the operator's cross-tenant view. | §2 |
| 3 | Is a batch a real stored object? | **Yes** — `screening_batches` + `batch_items`. Status is **derived at read time**, never stored. | §4.A |
| 4 | How much of the depth report does the org see? | **All of it**, including `verdicts[]`, `missing_signals` and `probes[]`. One redaction: `resume_farm.matches[]` loses identity, keeps similarity — applied in a single shared projection. | §4.B |
| 5 | Ingest feedback — poll, or a status endpoint? | **Both, and the client drives the work.** Upload registers items; a bounded `process` call does a few at a time; the UI polls batch progress. There is no worker anywhere in `app/`. | §4.A |

**One consequence worth carrying into design:** Q1 and Q3 together mean the
screening queue is "my batches", not "the candidate universe" — so an org that
has uploaded nothing sees an **empty queue, not an error**. That is the correct
resting state for a newly self-registered organisation and it is the first
screen every new customer will ever see.
