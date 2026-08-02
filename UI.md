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
down: **the wedge path has to be exposed on the org plane.** Design against that
intent, and expect the endpoint paths in §5 to be the S8.4 shapes rather than
today's admin paths.

### 2.1 The open question S8.4 must answer first

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

The UI can be designed against the assumption **"an org sees only the batches it
uploaded"**, which is the answer most buyers will assume is true. Flagging it
here so nobody discovers it during integration.

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

### A. Screening queue — *the product* 🔜

The one screen that matters. "Here are the resumes you dropped in, ranked by how
much they need a human."

Needs, none of which exist yet:
- **Batch upload** (drag 500 PDFs/text files) 🔜 — today `POST /candidates` ✅
  takes **one** `{resume_text | resume_pdf_b64, domain}` at a time, admin-only.
- **A fraud-screen read-model** 🔜 — one call returning a ranked, reasoned risk
  list over a batch. Today you would have to fan out to `GET /report/{id}` per
  candidate.
- **Cursor pagination** 🔜 — today only `limit` exists, on 3 endpoints, with no
  cursor. A 500-resume queue cannot page.

Design it as: batch header (name, count, uploaded-at, progress) → rows sorted by
risk band, each row showing **band · score · confidence · a one-line reason ·
the loudest signal**. Rows must be scannable without opening anything.

> **Ingest is slow and asynchronous in nature.** Each resume is extracted,
> claim-checked, scored across four fabrication subsystems, and (with a live
> model) LLM-assisted. Design for a progress state and partial results, not a
> spinner that blocks until 500 finish.

### B. Candidate risk detail — *where trust is won or lost* ✅ (admin-plane today)

`GET /report/{report_id}` returns the full `Report`. This is the richest object
in the system and the UI's central rendering problem:

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

### C. Batch summary / "what did we find" 🔜

A short, screenshot-able roll-up per batch: N screened, distribution across risk
bands, top reasons. This is what gets pasted into a WhatsApp group and sells the
next seat. Composed from the same read-model as A.

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

## 9. Open questions — for the user, before or during S8.4

1. **Tenancy (§2.1).** Does an org see only its own uploads? This changes the
   screening queue's shape and is the biggest one.
2. **Does the wedge path move to the org plane, or does S8.4 add org-plane
   equivalents** and leave the admin routes alone? Affects every path in §4.A/B.
3. **Batch identity.** Is a "batch" a real stored object with a name and a
   status, or just a client-side grouping of uploads? A screening queue really
   wants the former; nothing in the schema has it today.
4. **How much of the depth report does the org see?** The full `Report` includes
   claim-level verdicts and evidence. That is the most valuable view and the most
   sensitive one.
5. **Ingest feedback.** Batch upload of 500 needs progress. Poll, or does S8.4
   add a status endpoint?
