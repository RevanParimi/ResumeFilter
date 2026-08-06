# S8.4 — UI integration surface (design)

**Date:** 2026-08-05
**PI:** PI-8 (launch readiness)
**Position in the order:** S8.1 ✅ → S8.2 ✅ → **S8.4** → UI integration (S8.5) →
S8.3 → deploy (S8.6). Set by the user 2026-08-02; sprint IDs are stable
identifiers and only the order moved.
**Reads on:** `docs/superpowers/specs/2026-08-01-pi8-launch-readiness-design.md`
§5.4 · `UI.md` (the constraint, and the five open questions this spec closes) ·
`UI-Spec.md` items 9–17 · the 2026-08-03 wiring session's measured findings.

> **This is the last sprint before the UI is finished.** Anything the UI needs
> and does not get here becomes an integration rewrite, not a follow-up.

---

## 0. Decisions taken with the user for this sprint

All five of `UI.md` §9's open questions were settled on 2026-08-05, plus the
sprint's own shape. Rejected alternatives are recorded because the reasons are
the useful part.

### 0.1 An organisation sees only what it uploaded — and ownership belongs to the *upload*, not the person

Candidates remain **global and deduplicated by email hash**. That is S1.1
identity resolution, and it is the thing that makes cross-corpus near-duplicate
detection worth anything at all. What gains an owner is the *act of uploading*:
`resumes.org_id` and `reports.org_id`.

The three questions `UI.md` §2.1 posed, answered in order: Agency A does **not**
see the report Agency B commissioned; a candidate uploaded by both agencies
appears in **both** queues from **one** candidate row, because each agency owns
its own upload of her; and resume-farm detection **does** compare across the
whole corpus while disclosing only *that* a near-duplicate exists and how
similar it is — never whose (§0.4).

**Rejected — a shared candidate universe.** Cheapest to build and arguably the
honest description of one shared corpus. But "did the other agency see the
report I paid for?" is the first question a staffing buyer asks, and the answer
would be yes.

**Rejected — one deploy per customer.** Keeps multi-tenancy a non-goal (PI-8
§10) with no schema change, but it hard-codes a hosting posture that is still an
open question (GTM §11, PI-8 §12) and it kills the cross-customer resume-farm
signal, which is a genuine product advantage.

### 0.2 The wedge path gains org-plane routes; the admin routes stay

S8.4 **adds** org-plane endpoints beside the admin ones rather than moving them.
The admin routes keep working and keep their cross-tenant reach, because that is
the operator's support and debugging view and nothing else provides it.

**Rejected — moving the routes outright.** One canonical path per action is
tidier, but it removes the operator's cross-tenant view, breaks every existing
`X-Org-Key`/`X-API-Key` machine client (and `X-Org-Key` **is** the API product,
PI-8 decision 0.4), and churns the admin-plane tests plus all six regression
smokes for a cosmetic gain.

The two planes legitimately differ, and that difference is the design: **admin
sees everything, org sees what it owns.**

### 0.3 A batch is a real stored object; processing is client-driven

`screening_batches` + `batch_items`, so a queue can be named, resumed,
summarized and paginated.

The constraint forcing the shape: **there is no worker, no scheduler and no
`BackgroundTasks` anywhere in `app/`** — verified, not assumed — and
`POST /candidates` awaits the whole nine-node graph inline
(`app/api/routes.py:345-378`). Five hundred resumes in one request is not
physically possible. So upload only **registers** items (a row insert), and a
bounded `POST /screening/batches/{id}/process` does the slow work a few items at
a time while the UI polls progress.

**Rejected — in-process `BackgroundTasks`.** Nicer UX, but the work dies
silently on redeploy leaving items stuck `processing`, and it would introduce
the first background execution in the repo with no metrics to see it by until
S8.3.

**Rejected — client-side grouping with no stored batch.** Smallest change, but
`UI.md` screens A and C are both built on a batch that persists, and there would
be nothing server-side to name, resume or summarize.

### 0.4 The org sees the full report, counterparty-redacted

Everything: `verdicts[]`, `missing_signals`, `probes[]` included. `UI.md` §4.B
argues these are what convert a score into an action — `missing_signals` is the
sentence a recruiter repeats to their client, and `probes[]` are ready-made
questions a fake cannot survive. A headline-only view would strip out both.

The single redaction is `resume_farm.matches[]` → similarity and count, never
identity, because those rows may belong to another customer.

**Rejected — headline and reasons only.** Safer to defend while calibration is
unvalidated (PI-9), but §7's honesty rules already handle that: a *fuller*
report is not a more *confident* one, and there is still no accuracy claim to
make either way. Withholding the useful fields would not make the numbers more
honest, only less useful.

### 0.5 The sprint ships as two branches from this one spec

**Phase A — ownership.** The `org_name_taken` fix, the ownership model, the
scoped facade and its guard, the org-plane wedge routes, the redacting
projection.

**Phase B — the screening surface.** Batch tables and processing, the
fraud-screen read-model, cursor pagination, the materialization route, the comp
reconciliation, OpenAPI.

The reason is §1's risk, not bookkeeping: a tenancy scoping rule spread across
~20 org-plane routes is precisely the bug shape the last four branch reviews
each caught, and it deserves a review of its own rather than a diff it shares
with pagination and OpenAPI polish. Nothing else can be built until "what does
this org own" has an answer, so the phases are genuinely ordered rather than
merely separable.

**Rejected — one branch.** Less ceremony and one merge, but a new
security-relevant invariant would land in the same review as six unrelated
changes.

---

## 1. What this sprint is, in one paragraph

An organisation that self-registers through S8.2 can log in and then do
**none** of the things it signed up to do: uploading a resume, reading a fraud
report, listing a candidate's reports and searching the talent pool are all on
the admin plane (`UI.md` §2). S8.4 makes the wedge reachable by the customer who
bought it — which requires first deciding what "the customer's data" even means,
because nothing in the schema has ever recorded which organisation uploaded a
resume. That decision (§0.1) is the sprint's centre of gravity; batch upload,
the fraud-screen read-model and cursor pagination are the surface built on top
of it, and the four defects the wiring session measured are fixed along the way.

**The highest-risk sentence in this document:** an ownership rule is only worth
what its weakest entry point enforces. §3.3 is how that is made structural
rather than remembered.

---

## 2. The defects this sprint closes

Four were measured against a running API during the 2026-08-03 wiring session,
not predicted. They are listed first because three of them are small and one of
them blocks self-onboarding entirely.

### 2.1 `org_name_taken` — org self-serve onboarding is broken (Phase A, blocker 5)

Signing up with an organisation name that already exists returns `202`, sends a
real code, and then rejects that **correct** code as `400 invalid_code`. The
user has a valid code in their inbox, types it correctly, is told it is wrong,
burns their attempts and cannot onboard. "Acme Staffing" is exactly the name two
customers pick.

**Mechanism.** Org creation happens inside `_establish`
(`app/auth/service.py:353-364`), which runs at **verify** time — after the code
was mailed. `OrgNameTaken` becomes `ChallengeRefused("org_name_taken")`, and the
route maps **every** `ChallengeRefused` to one `invalid_code`
(`app/api/routes.py:1703-1707`). `missing_organization_name` rides the same
path.

It is the house shape again: **one handler collapsing two unrelated failures.**
The single-message rule exists so a brute-forcer learns nothing about *codes*;
here it is swallowing a *registration* failure.

**Fix, in two parts.**

1. **Check the name at signup**, before a code is ever sent, and answer
   `409 organization_name_taken`. This leaks nothing: organisation names are not
   secret, and a uniqueness constraint already discloses the same fact to anyone
   who completes a signup. It is also the better product — the user learns at
   the moment they can still change the name.
2. **Keep the check at verify** as well, because the name can be taken in the
   window between the two calls, and separate *registration* refusals from
   *code* refusals there. `org_name_taken` and `missing_organization_name` get
   their own statuses; every genuine code failure — expired, wrong, exhausted —
   stays one indistinguishable `400 invalid_code`.

The enumeration oracle is not re-opened, and this is worth stating precisely
because S8.2 closed two of them: the anti-enumeration property being protected
is about **whether an address has an account**, and neither new response varies
with that. `POST /auth/org/signup` for an unknown *address* still returns `202`
whether or not that address exists; only the *organisation name* — a value the
caller supplied and that is not a secret — changes the answer.

### 2.2 Feature materialization has no HTTP route (Phase B)

`app/features/materialize.py` is reachable only from Python, so for a
self-registered org the 422 below is **permanent, not transient**.

Two fixes, because there are two problems:

- **An admin-plane `POST /features/materialize`** route. Materialization is
  global across all candidates, so it is an operator action, not an org one.
- **The 422 goes away.** `"no materialized candidates to match"` appears at
  **two** call sites — `POST /jobs/{id}/match` (`app/api/routes.py:925`) and
  `GET /jobs/{id}/board` (`app/api/routes.py:1023`) — and an empty feature store
  is a *server-side* state. Returning 422 blames the client for it. Both become
  a `200` with an empty ranking and a stated reason, which is the same
  200-with-per-section-status pattern `GET /candidates/{id}/card` already models
  and `UI.md` §6 asks to be mirrored everywhere.

### 2.3 Two shapes for one set of numbers (Phase B)

`GET /jobs/{id}/comp` returns a `CompBenchmark` **wrapping** the estimate (plus
`position` / `delta_pct`); `POST /comp/estimate` returns a bare
`CompBandEstimate`. During wiring, assuming one shape rendered a band made
entirely of dashes.

**Fix:** both return `CompBenchmark`, with `position` and `delta_pct` **null**
when there is no requisition to compare against. One shape, one client-side
unwrap, and the null fields say honestly that there was nothing to position
against.

### 2.4 `POST /jobs` refuses a requisition with no skills (Phase B, minor)

A 422. Left as a validation rule but given a message that names the field, since
the current one sends a UI author looking in the wrong place.

---

## 3. Phase A — ownership

### 3.1 Data model — migration `0018_upload_ownership`

```
resumes.org_id   → organizations.id   NULL,  ON DELETE SET NULL,  indexed
reports.org_id   → organizations.id   NULL,  ON DELETE SET NULL,  indexed
```

**Nullable** because every existing row has no owner, and admin-plane uploads
legitimately have none. A null `org_id` means "unowned" — visible to operators,
invisible to every organisation. That is the correct reading for backfilled rows
and it needs no data migration inventing an owner that never existed.

**`ON DELETE SET NULL`, not `CASCADE`** — and this is the load-bearing choice.
An organisation offboarding must **not** destroy a candidate's resume. That
resume is the *person's* data; the only cascade permitted to delete it is the
candidate's own erasure, which already exists and already works. An org leaving
turns its uploads unowned; it does not erase people.

**No `candidates.org_id`.** A candidate is a person, not a customer record, and
two orgs can own uploads about the same person. "My candidates" is **derived** —
the candidates having at least one resume owned by my org — so there is no
second source of truth to drift. The cost is a join per query; the benefit is
that the ownership fact has exactly one home.

The metadata-wide drift / index / FK-ondelete / nullability guards extend to
both columns. That family of guards caught a real migration-vs-ORM drift during
S7.1 and is expected to earn its keep here, where the `SET NULL` semantics are
the whole point and a `CASCADE` typo would be silent until an org offboards.

### 3.2 Org-plane routes

| New (org plane) | Mirrors (admin, unchanged) | Notes |
|---|---|---|
| `POST /screening/candidates` | `POST /candidates` | Same request body (`resume_text \| resume_pdf_b64`, `domain`, `evaluate`) and the same `CandidateCreateResponse`. Stamps `org_id` on the resume, and on the report when `evaluate` is true. Synchronous, like its admin twin — this is the one-off upload, not the batch. |
| `GET /screening/reports/{id}` | `GET /report/{id}` | Redacted projection (§3.4); **404** if not owned |
| `GET /screening/candidates/{id}/reports` | `GET /candidates/{id}/reports` | Only reports this org owns; a candidate with none is an empty list, not a 404 |

Paths sit under `/screening/*` rather than re-using the admin nouns, so the two
planes never collide in the route table and the OpenAPI document reads
unambiguously.

`POST /evaluate` and `POST /talent/search` stay admin-only this sprint —
`/evaluate` is candidate-less ad-hoc text (no owner to stamp, so it raises the
tenancy question in a form nothing in the UI needs yet) and talent search reads
the global feature store, which is a cross-corpus surface that wants its own
decision. Both are named in §8 as deliberate carry-overs rather than oversights.

### 3.3 The scoping rule, made structural

The lesson from four consecutive branch reviews — S7.1 `start()`, S7.2
`claim_ref`, S7.3 the audio path, S8.2 the two-challenge lockout — is that **a
rule enforced by remembering to enforce it will be forgotten at the second
door.** A tenancy rule spread across org-plane routes is that shape by
construction, so org handlers do not get the option:

1. **A scoped facade.** Org-plane reads of candidates, resumes and reports go
   through one object whose every method takes `org_id` as its first argument.
   There is no unscoped read reachable from an org handler.
2. **A guard test**, in the family of `tests/test_route_table_guard.py`: it walks
   the org-plane handlers and fails the build if one reaches an unscoped store
   method. Like the route-table guard, it covers routes **not yet written**,
   which is the property that makes it worth more than any number of individual
   tests.
3. **The guard must be proven non-vacuous.** S8.2 recorded the trap exactly:
   FastAPI 0.138 does not flatten `include_router` into `app.routes`, so a naive
   walk saw 9 routes instead of 63 and would have passed while inspecting almost
   nothing. This guard asserts a floor on what it inspected, and a deliberately
   unscoped handler in a test fixture must make it fail.
4. **404, never 403.** Another org's report is indistinguishable from one that
   does not exist — the S6.4 cross-candidate and S7.1 verification precedent. A
   403 would confirm the report exists, which is the fact being protected.

### 3.4 One projection, not two

`resume_farm.matches[]` may reference resumes belonging to another customer. The
org plane sees **similarity and count, never identity**.

That redaction lives in **one** function, called by both the single-report read
(§3.2) and Phase B's queue read-model (§4.3). Two copies would be a bound that
holds on one path and lapses on the other — verbatim the S7.2 `claim_ref`
finding and the S7.3 transcript finding, the same defect shape two sprints
running. A test asserts both callers go through it.

### 3.5 `TENANCY.md`

A root doc, peer of `AUTH.md` / `PORTAL.md` / `VERIFICATION.md`. It records the
model, why candidates stay global, what "unowned" means, the enforcement and the
four branch reviews that motivated it, the 404-not-403 rule, the single
redaction, and what is deliberately **not** scoped yet (§8). Written in Phase A,
because a tenancy rule nobody can look up is a tenancy rule the next sprint
reinvents differently.

---

## 4. Phase B — the screening surface

### 4.1 Data model — migration `0019_screening_batches`

```
screening_batches
  id            uuid pk
  org_id        → organizations.id   NOT NULL, ON DELETE CASCADE, indexed
  name          text
  domain        varchar(32)
  created_at    timestamptz
  created_by_org_user_id → org_users.id  NULL, ON DELETE SET NULL

batch_items
  id            uuid pk
  batch_id      → screening_batches.id  NOT NULL, ON DELETE CASCADE, indexed
  status        varchar(16)   pending | processing | done | failed
  raw_text      text          CLEARED on success (§4.2)
  text_sha256   varchar(64)
  candidate_id  → candidates.id  NULL, ON DELETE SET NULL
  resume_id     → resumes.id     NULL, ON DELETE SET NULL
  report_id     → reports.id     NULL, ON DELETE SET NULL
  error         text
  created_at / claimed_at / processed_at   timestamptz
```

`screening_batches.org_id` **CASCADE**, unlike §3.1's `SET NULL`, and the
distinction is deliberate: a batch is the *organisation's own* work product with
no meaning once the org is gone, whereas a resume is a *person's* data that
merely happened to be uploaded by that org.

The three subject pointers are **`SET NULL`**, so a candidate erasing themselves
leaves the item reading "subject erased" rather than silently rewriting the
org's record of how many resumes it screened.

### 4.2 The uncomfortable part, stated rather than hidden

**`batch_items.raw_text` holds personal data with no candidate to cascade
from.** A resume cannot be written to `resumes` before extraction, because a
resume row requires a candidate and identity resolution requires the extraction
to produce the email/phone hashes. The text genuinely must live somewhere
unowned for a while. Three things make that safe:

1. **On success the item's `raw_text` is cleared.** The text now lives in
   `resumes`, where candidate erasure already cascades. This is S7.1's challenge
   hygiene: short-lived material actually deleted on a path that already runs,
   not a retention policy waiting for a sweep that does not exist.
2. **`DELETE /screening/batches/{id}` ships in this sprint** — a real delete path
   on a new table, per the standing DPDP convention, rather than deferring the
   only means of deletion to S8.3.
3. **Unprocessed items get a declared retention window** (`ret_batch_item_days`)
   and are named as input to S8.3's sweep. An org that uploads 500 and abandons
   them is the case this covers.

A failed item keeps its text, because the org must be able to retry it; failure
is not a reason to destroy the input. Failed items are inside the retention
window like any other unprocessed row.

### 4.3 Endpoints

| Route | Plane | Purpose |
|---|---|---|
| `POST /screening/batches` | org | Create a batch and **register** items — a row insert per resume, no evaluation. Body: `{name, domain, items: [{resume_text \| resume_pdf_b64}]}`. PDFs are decoded to text at registration (cheap, deterministic, no LLM) so a corrupt file fails immediately rather than 400 items later. Bounded by `screening_max_batch_items`. |
| `GET /screening/batches` | org | The org's batches, cursor-paginated |
| `GET /screening/batches/{id}` | org | Batch + **derived** progress counts (§4.4) |
| `POST /screening/batches/{id}/process` | org | Claim and process up to `screening_max_items_per_call` pending items; returns processed / failed / remaining |
| `GET /screening/batches/{id}/queue` | org | **The fraud-screen read-model** — ranked, reasoned, cursor-paginated |
| `GET /screening/batches/{id}/summary` | org | The screenshot-able roll-up (`UI.md` screen C) |
| `DELETE /screening/batches/{id}` | org | Delete the batch, its items and their text |

The two read-models are **pure composition** in the `app/dashboard/` style — no
new state, no new `ConsentPurpose`, no LLM. Each queue row carries band · score ·
confidence · a one-line reason · the loudest signal, plus the ingest-time fraud
signals `UI-Spec.md` item 9 found were being computed and thrown away:
`matched_existing`, `matched_on`, `duplicate_resume`, `resume_farm`. Both go
through §3.4's redacting projection.

### 4.4 Status is derived, never stored

Batch progress is a **count over item statuses computed at read time** — the
S7.1 assurance / S7.3 `effective_status` rule. A stored batch status is a fact
that goes stale the moment a process dies and that nothing afterwards corrects.

The same rule makes processing restart-safe: an item in `processing` whose
`claimed_at` is older than `screening_claim_timeout_seconds` **reads as
`pending`** again. A batch interrupted by a redeploy heals itself on the next
`process` call instead of wedging forever with items nobody will ever claim.

S7.3's stored `InterviewAssessment` was a deliberate exception to this rule,
argued on the grounds that it is a closed fact about a finished session and
recomputing it would re-hit a paid model. Neither applies to a count of rows.

### 4.5 Cursor pagination

One shared implementation: an opaque base64 cursor over `(created_at, id)` —
the tuple, not a bare offset, so inserts during paging cannot duplicate or skip
a row. Applied to the new screening lists and to the three existing
`limit`-only sites: curation unmapped (`routes.py:596`), job match
(`routes.py:870`) and talent search (`routes.py:1471`).

`limit` keeps working on all three. The cursor is additive, because those three
have callers.

### 4.6 OpenAPI

Sufficient to generate a typed client, which means specifics rather than
polish: a unique `operation_id` and a declared `response_model` on **every**
route, plane tags, and error responses documented where a client must branch on
them (the 401/403/404/409 forks the wiring session had to discover by
measurement). A test asserts uniqueness and presence — generated and enforced,
never hand-maintained, because a hand-maintained list is the one that drifts
(S8.2's `OPEN_PATHS`/`PUBLIC_PATHS` finding).

---

### 4.7 What this breaks in the already-wired UI

The UI was wired on 2026-08-03 against the API as it stood. Two changes here are
visible to it, and both are cheap **now** and an integration bug **later**, so
they are named rather than discovered:

- **`POST /auth/org/signup` gains a `409`** (§2.1). `frontend/api.js` currently
  treats org signup as "202 always" — the wiring session's contract suite asserts
  exactly that, and it will fail on purpose. The signup screen needs a
  name-already-taken state, which is a better experience than the lockout it
  replaces.
- **`POST /comp/estimate` changes shape** (§2.3). The UI already unwraps
  `CompBenchmark` centrally because `GET /jobs/{id}/comp` returns one, so this
  makes the two paths agree and the central unwrap becomes correct for both. The
  wired comp screen is expected to keep working; a CDP click-through confirms it
  rather than assuming.

Nothing else the UI calls changes. The org-plane routes in §3.2 and §4.3 are
additive, which is what unblocks screens 2, 4, 5 and 6 in S8.5 without touching
what already works.

## 5. Config (new knobs)

```yaml
# --- Screening batches (PI-8, S8.4) ------------------------------------------
screening_max_batch_items: 500          # registration is cheap; this is a sanity bound
screening_max_items_per_call: 5         # each item is a full nine-node graph run
screening_claim_timeout_seconds: 900    # a 'processing' item older than this reads pending
ret_batch_item_days: 90                 # unprocessed item text; S8.3 sweep input
page_default_limit: 50
page_max_limit: 200
```

No secrets. No knob weakens the §3.3 scoping rule or restores the collapsed
`invalid_code` mapping of §2.1.

---

## 6. DPDP posture

- **No new `ConsentPurpose`.** Ownership is not a disclosure — it is the
  narrowing of one, and it strictly *reduces* what an org can see. Consent-gated
  org reads (`ledger_read`, `verification_read`, `interview_read`) are unchanged
  and still enforced at query time.
- **New tables get real delete paths** (§4.2), not deferred ones.
- **Erasure still cascades correctly and gains nothing to remember.** The three
  subject pointers on `batch_items` are `SET NULL` and the text is already gone
  by then, so no erasure handler needs a new line — which is the property S8.1's
  fold and S7.3's cascading tables both aimed at.
- **Access to a report through the org plane is audited**, as every org-plane
  read of a person already is.
- **The cross-corpus signal stays de-identified.** §3.4 is a DPDP control, not
  only a commercial one: it is the difference between telling an org "this
  resume resembles another in the corpus" and telling them about a person who
  never consented to that disclosure.

---

## 7. Testing and smoke

Fully offline, `NullLLM`, no network — as always.

**Phase A must prove ownership, adversarially:**

- An org reading another org's report gets **404**, and the response is byte-for-byte
  what a genuinely absent report returns.
- Two orgs upload the same person; both see her in their own queue, exactly one
  candidate row exists, and neither can read the other's report.
- An org offboarding leaves the resume and the candidate **intact and unowned**
  (this is the `SET NULL` semantics, and a `CASCADE` typo must fail this test).
- The candidate's own erasure still removes everything, unchanged.
- **The scoping guard is proven non-vacuous** — it asserts a floor on how many
  handlers it inspected, and a deliberately unscoped handler makes it fail.
- **`resume_farm.matches[]` is redacted on both paths**, single-report and queue,
  through the one shared projection.

**Phase A must prove the §2.1 fix does not re-open enumeration:** signup for an
unknown *address* still answers `202` regardless of whether an account exists;
only a taken *organisation name* changes the response; and every genuine code
failure — expired, wrong, exhausted — remains one indistinguishable
`400 invalid_code`.

**Phase B must prove the batch machinery:**

- Registration is evaluation-free — a registered batch creates no candidates.
- Processing is bounded, resumable, and idempotent under a repeated call.
- An item stranded in `processing` past the timeout is reclaimed and completes.
- `raw_text` is empty after success and retained after failure.
- `DELETE /screening/batches/{id}` removes the text.
- Cursor paging across an insert neither duplicates nor skips a row.
- Both former 422 sites return 200 with an empty ranking and a reason.

**Mutation-test the scoping facade and the projection.** S8.2 recorded two
surviving mutants on `AuthService`, one of which proved a load-bearing comment
was simply wrong. These two functions are where a silent mutant would be a
cross-tenant disclosure.

**Smokes** (uvicorn, key-less, per the convention): `scripts/smoke_s84a.py` —
two orgs, one candidate, ownership proven over HTTP end to end, plus the
`org_name_taken` path from signup to a successful second attempt.
`scripts/smoke_s84b.py` — register a batch, process it in bounded calls, watch
progress, read the queue and the summary, page with a cursor, delete the batch.
All six existing regression smokes stay green.

---

## 8. Non-goals for S8.4

- **`POST /evaluate` and `POST /talent/search` on the org plane** (§3.2) —
  deliberate carry-overs. `/evaluate` is candidate-less, so there is no owner to
  stamp; talent search is a cross-corpus read wanting its own decision. Both are
  the next tenancy question, not this one.
- **A worker, a queue or a scheduler** (§0.3). The retention sweep in S8.3 is
  the first thing that genuinely needs one, and it should choose the mechanism.
- **Rate limiting** — S8.3, and `POST .../process` is a new expensive endpoint
  that must be on its list.
- **Row-level security or a tenant-per-schema database.** §3.1 is application-level
  scoping with a structural guard. If the hosting posture (GTM §11) later demands
  database-level isolation, this is the layer it replaces, not a layer it fights.
- **Org offboarding as a product flow.** The `SET NULL` semantics make it *safe*;
  a UI for it is not in scope (`UI-Spec.md` item 17).
- **Everything in PI-8 §10** — standing, unchanged.

---

## 9. Definition of done

1. An organisation that self-registers can upload a resume, read its fraud
   report, and see it in a ranked queue — **without an operator touching
   anything**.
2. Two organisations screening the same person cannot read each other's reports,
   and a test proves the failure is a 404 indistinguishable from absence.
3. The scoping guard fails the build when a handler reaches an unscoped read,
   and is proven non-vacuous.
4. Signing up with a taken organisation name is refused at signup with its own
   status, and every code failure remains one `invalid_code`.
5. A 500-item batch registers, processes in bounded calls, survives a restart
   mid-run, and reports honest progress throughout.
6. `GET /jobs/{id}/board` and `POST /jobs/{id}/match` no longer 422 on an empty
   feature store; materialization has an admin route.
7. Comp returns one shape from both endpoints.
8. `GET /openapi.json` has a unique `operation_id` and a `response_model` on
   every route, asserted by a test.
9. `pytest -q` green; `smoke_s84a` and `smoke_s84b` green; all six regression
   smokes green.

---

## 10. Follow-ups this sprint deliberately leaves open

- **Org-plane `/evaluate` and talent search** (§8) — the next tenancy decision.
- **Whether unowned rows should ever be adoptable.** Today a null `org_id` is
  permanent. Backfilling ownership for pre-S8.4 uploads is possible but there is
  no evidence about who uploaded them, and inventing one would be a lie in a
  column other code will trust.
- **`batch_items` retention actually sweeping** — the window is declared here,
  the job is S8.3's, and `sweep_active=False` has been the oldest outstanding
  compliance gap since S6.4.
- **Whether the queue should span batches** ("everything I have ever screened,
  ranked"). Cheap once the read-model exists; not needed for the demo, and it
  changes what a cursor is paging over.
