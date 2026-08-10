# S8.5 — wiring the screening screens to the API (design)

**Date:** 2026-08-10 · **Sprint:** S8.5 (UI build + integration) · **Status:** design
**Predecessor:** `2026-08-03-ui-api-wiring-design.md` (auth · portal · devices ·
roles · comp). This session wires the five screens that were blocked on S8.4:
**queue · report · summary · upload · batches**.

**Peer documents read, not remembered:** `SCREENING.md` (what the seven routes
promise), `TENANCY.md` (404-never-403), `UI.md` §4.A/§4.B (what the screens must
say), `app/screening/schema.py` (the wire shapes).

**No `app/` code changes.** This is an integration session; anything found in the
API is written down and left for its own spec + TDD, exactly as the 2026-08-03
session did with the `org_name_taken` defect.

---

## 0. Decisions

### 0.1 One door: a batch of one is still a batch

`POST /screening/candidates` (Phase A, single resume) and `POST
/screening/batches` (Phase B, N resumes) both reach the same ingest core. The UI
uses **only the batch route**, including for a single file.

*Rejected:* a fast path for one resume. It is the repo's signature defect shape —
one rule, two doors — bought for an animation. A batch of one costs one extra
row.

### 0.2 The client drives the work, and the UI must say so

`POST /screening/batches/{id}/process` handles at most
`screening_max_items_per_call` (**5**) items per call, each a full nine-node
graph run. There is no worker anywhere in `app/`. So the browser loops until
`remaining` is 0.

Three consequences the UI is obliged to state rather than hide:

1. **Registration evaluates nothing.** The upload screen's current copy —
   *"Screening starts immediately and results appear as each one lands"* — is
   false against this API and is rewritten.
2. **Closing the tab pauses the batch.** It does not lose it: an item still
   `processing` after `screening_claim_timeout_seconds` reads `pending` again and
   is re-claimable (`SCREENING.md` §3), so the next `process` call resumes.
3. **Each call bills a model.** So the loop is **sequential**, never parallel
   (the claim protects against double-billing *the same item*, not against a
   client fanning out), and **any error stops it** — there is still no rate
   limiting server-side (S8.3), so a retry loop is caught nowhere.

### 0.3 Processing starts on upload, never on navigation

Registering 200 resumes is an unambiguous instruction to screen them, so the
upload flow registers → opens the queue → **starts the driver**, with a visible
Stop.

Merely *visiting* a batch that has pending items does **not** start it. A passive
read must never trigger billed work; the queue shows "N not screened yet" and a
Start button.

### 0.4 No polling timer, because nothing is happening server-side

The wired screens refresh **after each `process` call returns** — the call is the
tick. When the driver is not running, nothing polls, which is honest: with no
worker, an idle client means an idle batch. A manual Refresh covers the
second-tab case.

*Rejected:* a `setInterval` poll of `GET /screening/batches/{id}`. It would draw
a progress bar that cannot move.

### 0.5 The queue has no names, and that is the design

`QueueRow` is scalars only — no name, no email — because
`batch_items.candidate_id` is `ON DELETE SET NULL` and anything stored beside it
outlives the person (`SCREENING.md` §5). UI.md §4.A already specifies a row as
*band · score · confidence · reason · loudest signal*, with no name.

So rows are identified by a short id, the screen says **why** in one line, and
the name appears on drill-in from `Report.candidate_context.full_name`.

*Rejected:* fetching each row's report to get a name — N requests to defeat a
deliberate DPDP property.

### 0.6 The queue header's numbers come from `summary`, not from the page

`GET .../queue` returns one page (default 50). A header reading "11 elevated"
over a paged list would silently mean "11 on this page". The queue screen
therefore loads **both** `/queue` (rows) and `/summary` (header counts, which are
whole-batch and cheap — counts and enum members only).

### 0.7 Per-batch risk counts are not on the batches list, so the column goes

`BatchView.counts` holds **item statuses** (pending/processing/done/failed), not
risk bands. The mock batches screen shows "11 elevated" per row; that number does
not exist without a summary call per row.

Replaced with what the API actually serves: progress (done/total) and the derived
status. *Rejected:* fanning out one `summary` per listed batch.

### 0.8 The outcome buttons come off the report screen

`POST /report/{report_id}/outcome` is on the **admin** router (`routes.py:2024`).
An org user gets 401. The UI's own rule — an affordance that always fails is
worse than none — already governs this (it is why the current session cannot
revoke itself).

The heading stays with one honest sentence naming it as an operator action and a
PI-9 calibration input. *Rejected:* leaving four buttons that 401.

### 0.9 Wired screens drop their mock outright

Unchanged from spec 0.4 of the predecessor: no fallback-to-mock, because a
fallback makes a broken backend look like a working one. `CANDIDATES`, `ROWS`,
`REPORTS`, `JOBS`-style constants behind the five screens are **deleted**, not
left unreferenced.

`MOCK_NOTE`'s text ("no endpoint until S8.4") is now false and is rewritten: the
five remaining mock screens are mock for three different reasons (admin plane,
candidate plane, or not built).

---

## 1. The mapping, field by field

Enumerated from `app/screening/schema.py` and `app/schemas/report.py`, not from
memory.

### 1.A Batches — `GET /screening/batches`

| Screen | Source |
|---|---|
| name | `batches[].name` (may be `""` → "Untitled batch") |
| meta line | `created_at` · `counts.total` resumes · `domain` |
| progress | `counts.done + counts.failed` / `counts.total` |
| status | `status` — `empty\|pending\|processing\|complete\|partial` |
| delete | `DELETE /screening/batches/{id}` (real DPDP path, `SCREENING.md` §7) |
| load more | `next_cursor` → `?cursor=` |

`partial` is "nothing left to do, but something failed" — it must not render as
`complete`.

### 1.B Queue — `GET /screening/batches/{id}/queue` + `/summary` + `/{id}`

| Screen | Source |
|---|---|
| row identity | `candidate_id` (short) else `item_id` (short) |
| band chip | `signals.risk_band` → elevated/moderate/low/insufficient_data |
| score | `risk_score` (null for unscreened — renders "—", never 0) |
| confidence | `signals.risk_confidence` |
| reason | `reason` — **generated server-side**, rendered verbatim |
| loudest signal | `signals.loudest_signal` + `loudest_band`, via a label map |
| drill-in | `report_id` → report screen (absent → row is not clickable) |
| header counts | `summary.by_risk_band` |
| progress | `batch.counts` + `batch.status` |

`status: "pending"` with `risk_score: null` is a normal state (UI.md §4.A):
greyed, sorted last by the API's own `COALESCE(risk_score, -1)` ordering.
`failed` carries a reason **code**, not a verdict about a person.

### 1.C Summary — `GET /screening/batches/{id}/summary`

`by_risk_band` → the four big stats, as a share of `n_screened` (**not** of
`counts.total`: a 20%-processed batch must not report 80% "insufficient").
`top_signals[]` → the bar list, ids mapped to labels
(`ai_generation` / `cross_field` / `resume_farm`).

### 1.D Report — `GET /screening/reports/{report_id}` (Phase A, org plane)

| Screen | Source |
|---|---|
| name | `candidate_context.full_name` (null → "Name not extracted") |
| role line | `candidate_context.role_title` · `seniority` · `domain` |
| summary | `summary` |
| depth | `depth_band` · `depth_score` |
| headline gauge | `fabrication_risk.score` / `.band` / `.confidence` |
| the three cards | `fabrication_risk.components[]` joined to `ai_generation` / `cross_field` / `resume_farm` for each one's own band, numbers and **`reasoning`** |
| verdicts | `verdicts[]` → claim_text, claim_type, status, coherence_score, confidence, reasoning, `missing_signals`, `evidence[]{source,polarity,detail}`, `probes[]` |
| near-duplicates | `resume_farm.matches[]` → **count + top similarity only** |

`matches[]` arrives with `candidate_id`/`resume_id` **already null** on the org
plane (Phase A's projection). The UI reads neither field — a screen that never
touches them cannot leak them if the projection ever regresses.

### 1.E Upload — `POST /screening/batches`

Browser-side: `.pdf` → base64 via `FileReader.readAsDataURL` (prefix stripped) →
`resume_pdf_b64`; `.txt`/`.md` → `readAsText` → `resume_text`; anything else is
refused **client-side, naming the file**, because the API has no route that would
accept it.

**The index→filename translation is load-bearing.** A corrupt PDF refuses the
**whole** registration with `item 37: pdf_parse_failed: …`. "Item 37" is
meaningless to someone looking at 400 filenames, so the UI rewrites the leading
`item N:` with that file's name and says plainly that **nothing was registered**.

The item cap (`screening_max_batch_items`, 500) is **not** hardcoded client-side:
the server's 422 already names it (`a batch holds at most 500 items`) and a second
copy is a second thing to drift. The UI renders the server's sentence.

---

## 2. What this session must not do

- No `app/` change. Findings get written down.
- No new consent purpose, no new endpoint, no schema change.
- No accuracy claim, no auto-reject affordance, no candidate-facing risk score
  (UI.md §7/§8).
- No mock left behind a wired screen (0.9).

## 3. Verification (there is no CI for `frontend/`)

1. **A contract script over real HTTP** driving the seven routes exactly as the
   UI does: org signup → register a batch (text + a real PDF) → the bounded
   `process` loop to `remaining == 0` → queue page + cursor → summary → report
   drill-in → delete. Plus the refusals the UI renders: a corrupt PDF's
   `item N:` prefix, an over-cap batch, another org's batch (404), a forged
   cursor (422).
2. **A browser click-through at the real origin** over CDP: every wired screen,
   the driver running to completion, and the empty state a brand-new org sees.
3. `pytest -q` re-run to prove no `app/` code moved.
