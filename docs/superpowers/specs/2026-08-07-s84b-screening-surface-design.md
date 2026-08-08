# S8.4 Phase B — the screening surface (design)

**Date:** 2026-08-07 · **Sprint:** S8.4 Phase B (PI-8) · **Branch:**
`s84b-screening-surface`

**Parent spec:** `docs/superpowers/specs/2026-08-05-s84-ui-integration-surface-design.md`
— §4 is Phase B's scope and every decision there still stands. This document is
the *delta*: the decisions §4 left to build time, the three Phase-A carry-overs
that now ride migration `0019`, and — the reason it exists at all — Phase B's
tenancy analysis written the way Phase A's failure says it must be.

**Read with:** `TENANCY.md` (the ownership model as shipped) · `UI.md` §4.A/§4.C
(the screens this feeds) · `FLOW.md` (the nine-node pipeline each item runs).

---

## 0. Why this document exists — the method change Phase A paid for

Phase A shipped a cross-tenant identity leak. It did not get in through a
missing rule; the rule was right and the facade enforced it. It got in because
spec §3.4 enumerated **the handlers that read people** and concluded there were
two, and the third reader — the *upload response* — returns a report without
reading one. `POST /screening/candidates` handed back real `candidate_id` /
`resume_id` values belonging to other customers' candidates, twice over (the
top-level `resume_farm` and the copy embedded in `report`).

Counting readers is what missed it. So Phase B's tenancy work is done the other
way round, and §2 is the artifact: **for every field of every new org-facing
response, where did this value come from, and can it name somebody who is not
this customer's?** Phase B adds two entirely new org-facing response shapes (the
queue read-model and the summary), which is exactly the surface where this
recurs.

---

## 1. Decisions

### 1.1 A queue row is built from `batch_items` alone — the report body is not on the read path

The queue read-model (`GET /screening/batches/{id}/queue`) returns **only**
columns of `batch_items` rows belonging to the caller's batch, plus scalars
stamped onto that item when it was processed. It does not open a `Report`.

Two independent reasons, and the second is the load-bearing one:

1. **It is the only shape that pages.** The UI must sort 500 rows by risk. The
   risk score lives inside `reports.body` as JSON; ordering by it in SQL is
   dialect-specific (`json_extract` vs `->>`), and ordering it in Python means
   parsing 500 report bodies per page request. A real `risk_score` column is
   sortable, indexable and dialect-neutral.
2. **It makes the leak structurally impossible rather than correctly handled.**
   A `Report` is a cross-corpus object — `resume_farm.matches[]` carries other
   customers' identities, which is why `redact_for_org` exists. If the queue
   read path never holds one, there is nothing on it to forget to redact. §2's
   table is short because of this decision.

**What gets stamped at process time**, on the item, once, when its evaluation
finishes: `risk_score` (a real nullable `Float` column — the sort key) and
`signals`, a JSON blob validated by a Pydantic `ItemSignals` model holding the
remaining scalars (risk band, confidence, depth band and score, the loudest
component id and its band, the resume-farm band/score/corpus size, and the three
ingest facts `matched_existing` / `matched_on` / `duplicate_resume`).

Storing these is consistent with the derived-status rule rather than an
exception to it. S7.3 argued the distinction already: **a closed fact about a
finished evaluation is safe to store; a fact that depends on the clock or on
later rows is not.** A batch's *progress* depends on later rows, so §4.4 keeps
it derived. A finished item's risk score does not change, and `matched_existing`
is not even recomputable — it is a fact about the moment of ingest, and by the
time anyone reads it the candidate certainly exists.

`signals` is JSON for the same reason `reports.body` and `extractions.profile`
are: schema evolution is Pydantic's job, not SQL's. A stored blob this code
cannot parse **degrades to "no signals" and logs** rather than raising — the
S7.3 `InterviewAssessment` finding, where one unparseable write bricked a
candidate's own portal on every later read.

**Rejected — join to `reports` and project at read time.** Truthful and needs no
new columns, but it puts a cross-corpus object back on the hot read path (the
thing that just leaked), and it cannot sort or page without parsing every body.

### 1.2 `signals` holds scalars only — no free text — and that is a DPDP decision

`UI.md` §4.A asks each queue row for "a one-line reason". The obvious
implementation copies `fabrication_risk.reasoning` onto the item. **It is
refused.**

`batch_items.candidate_id` is `ON DELETE SET NULL` (parent spec §4.1) so that a
candidate erasing themselves does not silently rewrite the org's record of how
many resumes it screened. That is right — but it means anything *else* on the
item survives the erasure too. A reasoning string can quote claim text; a copy
of a person's claim text that outlives their erasure is precisely the orphan
S8.1's fold of the report store existed to make impossible, re-created one table
over.

So: **`ItemSignals` is bands, floats, booleans and enum members. No names, no
claim text, no free-form model output.** The one-line reason is **composed at
read time by a pure function** from those scalars ("elevated fabrication risk —
resume-farm is the loudest of 3 signals, confidence 0.42"). After an erasure the
row keeps a band and a score attached to a null candidate, which is not personal
data, and the full reasoning stays where it always was: in the `Report`, which
CASCADEs from the candidate and is reachable through
`GET /screening/reports/{id}` when the user opens the row.

**Rejected — copy the reasoning and clear it in the erasure handler.** It works
until the third erasure entry point forgets the line, which is this repo's
single most-repeated defect (S7.1, S7.2, S7.3, S8.2, S8.4A). A column that
cannot hold personal data needs nobody to remember anything.

### 1.3 One ingest core, not two

Batch processing runs the same pipeline as `POST /screening/candidates`:
extract → resolve identity → store → fingerprint → farm check → evaluate. That
logic lives in `_ingest_one` (`app/api/routes.py:312-408`), which takes a
FastAPI `Request` and raises `HTTPException` — neither of which a batch
processor can use.

**`app/screening/ingest.py::ingest_resume(...)`** takes the services bundle, the
engine and plain arguments, and raises `IngestRefused(reason)` for every
refusal. `_ingest_one` becomes a thin adapter that decodes the PDF, calls it and
maps `IngestRefused` → `422`; the batch processor calls it and maps
`IngestRefused` → `status='failed'`, `error=reason`.

The whole existing ingest suite (`test_ingest.py`, `test_candidates_api.py`,
`test_screening_api.py`, `test_resume_farm_api.py`, five smokes) passes
**unmodified** or the refactor is wrong. That is the acceptance test.

**Rejected — a second copy of the pipeline for batches.** It is the
one-rule-two-doors shape, committed on purpose, in the sprint whose entire
subject is that shape. **Rejected — the processor calling its own HTTP route
in-process.** A route is not an API for the process that hosts it: it re-runs
auth, re-parses a body, and turns every refusal into a status code the caller
has to reverse-engineer.

### 1.4 Cursor pagination lands only where the order is a stored key

Parent spec §4.5 asks for one opaque `(created_at, id)` keyset cursor over the
new screening lists **and** the three existing `limit`-only sites: curation
unmapped, job match, talent search.

Two of those three cannot honour it. `POST /jobs/{id}/match` and
`POST /talent/search` rank a pool that is **recomputed on every request** —
there is no stored order to key on, and a candidate's position can move between
page 1 and page 2 because a vector was materialized in between. An opaque cursor
is a promise that paging neither duplicates nor skips a row; over a re-ranked
pool that promise cannot be kept, and encoding an offset in base64 to look like
a cursor is a lie with a nicer wrapper.

**So:** the keyset cursor applies to `GET /screening/batches`,
`GET /screening/batches/{id}/queue` and `GET /curation/skills/unmapped` — three
lists whose order is stored. `POST /jobs/{id}/match` and `POST /talent/search`
keep `limit`, unchanged, and their OpenAPI descriptions say plainly that they
return a top-N ranking and are not paged. Nothing in `UI.md` pages either of
them; the 500-row problem §4.A names is the screening queue, which is keyset-
pageable.

**Rejected — a base64 offset for the ranked endpoints**, for the reason above.
**Rejected — snapshotting a ranking to make it pageable**: that is a stored
match result, a new table and a staleness question, for a screen nobody has
asked for.

### 1.5 The queue's sort key, and where unprocessed items go

Order is `COALESCE(risk_score, -1) DESC, id ASC`. Highest risk first (the screen
exists to put the riskiest resume at the top), unprocessed and failed items last
(they have no score), `id` breaking ties so the total order is stable and the
keyset predicate is exact. `COALESCE` rather than `NULLS LAST` because SQLite
sorts NULLs first under `DESC` and has no `NULLS LAST` before 3.30 — the
expression is the portable spelling of the same intent.

Pending items **are** in the queue. The UI shows partial results while a batch
processes (`UI.md` §4.A), and a row that says "not screened yet" is the honest
rendering of that.

### 1.6 Claiming is a conditional UPDATE, not a read-then-write

There is no worker, but there are two browser tabs. Two concurrent
`POST /process` calls must not run the same item twice — each item is a
full nine-node graph run, and on a live model that is money.

An item is claimed by `UPDATE batch_items SET status='processing',
claimed_at=:now WHERE id=:id AND status IN ('pending','processing-but-stale')`,
and the claim counts only if `rowcount == 1`. The read that *chose* the item may
be stale; the write that claims it cannot be.

"Stale" is `status='processing' AND claimed_at < now - screening_claim_timeout_seconds`,
which is parent spec §4.4's self-healing rule expressed as a predicate: an item
whose process died mid-run becomes claimable again on the next call, and a batch
interrupted by a redeploy heals instead of wedging.

### 1.7 Case-insensitive organisation names — a functional UNIQUE index (Phase-A carry-over 1)

Phase A left org names compared case-sensitively, and recorded why fixing it
there would have been worse than leaving it: a case-insensitive *check* without
a matching case-insensitive *constraint* creates a **new** lockout — the signup
409 refuses "acme", the insert at verify still succeeds beside "Acme", and now
two orgs share a name the UI treats as unique.

`0019` adds `uq_organizations_name_ci`, a UNIQUE index on `lower(name)`, and
`organization_name_exists` compares `lower(name)`. Both insert paths —
`LedgerStore.create_organization` and `AuthStore.create_org_with_owner` — already
map `IntegrityError` to their own refusal (`ValueError` / `OrgNameTaken`), so the
database becomes the single enforcement point and neither door needs a new check.

**Measured, and it changes a test:** SQLite *enforces* an expression index
(`INSERT 'acme'` after `'Acme'` raises `IntegrityError`) but **does not reflect
one** — `inspect(engine).get_indexes("organizations")` omits it entirely and
SQLAlchemy emits `SAWarning: Skipped unsupported reflection of expression-based
index`. `test_migrated_indexes_match_orm` compares ORM indexes against reflected
ones, so declaring the index in the ORM makes that guard fail on a schema that
is in fact correct. The guard therefore **skips expression indexes explicitly,
with the measurement in its docstring**, and a new behavioural test asserts the
constraint on the *migrated* engine by inserting the collision and requiring the
error. That trade is a strict improvement: a behavioural test proves the
constraint is enforced, which the metadata comparison never did.

**Rejected — a `name_key` column holding `lower(name)`.** Reflects normally and
keeps the guard untouched, but it is a second source of truth maintained by
application code at two insert sites: the two-doors shape again, for a cosmetic
gain. **Rejected — a generated column.** SQLite permits only `VIRTUAL` when
adding one to an existing table and Postgres permits only `STORED`, so the
migration would branch by dialect.

**Migration safety:** a database that already holds "Acme" and "acme" cannot
take the index. `0019` checks first and **raises with the colliding names**
rather than failing on an opaque `IntegrityError` or, worse, mangling a row. The
tracked dev database was measured — it has no `organizations` table at all
(reverted after the demo per the standing rule), so there is nothing local to
migrate.

### 1.8 Ownership stays on `resumes.org_id` — no `resume_uploads` join table (carry-over 3)

Phase A shipped `OrgScopedReads.owns_candidate` correct and unused, and flagged
that Phase B's queue would be its first real consumer and might want a join
table instead.

It does not. The queue reads `batch_items`, and an item already carries its
owner transitively through `batch_id → screening_batches.org_id NOT NULL`. A
`resume_uploads` table would be a *second* record of the same ownership fact —
the second source of truth parent spec §0.1 rejected `candidates.org_id` for.

`owns_candidate` is therefore **still unused after Phase B**, and that is stated
here rather than left to be rediscovered: it is either consumed by a future
org-plane candidate-detail route or deleted. Dead scoped code is not harmful,
but an unused method in a security-relevant facade invites a caller who assumes
it has been exercised. Listed in §7.

### 1.9 One `text_sha256` can now match several resume rows (carry-over 2)

Phase A made an upload by a *different* org create its own `resumes` row rather
than join somebody else's, so `text_sha256` is no longer close to unique.
Consequences Phase B honours: `batch_items.text_sha256` is **indexed, not
unique**; registering the same text twice in one batch is allowed (the org may
genuinely hold two copies, and refusing would fail a 500-file drop for a reason
the user cannot act on); each item is processed independently, and the second
one reports `duplicate_resume: true`, which is the fraud signal, not an error.

### 1.10 Materialization gets an admin route (parent §2.2)

`POST /features/materialize` on the **admin** plane, body
`{candidate_ids?: [...], as_of?: datetime, view_name?: str}`. Omitting
`candidate_ids` materializes every candidate, bounded by
`materialize_max_candidates`. Materialization is global across all candidates
and consent-masked per candidate (S4.2) — it is an operator action, and putting
it on the org plane would let one customer's call compute vectors over every
customer's people.

This needs the one store method it has never had: `CandidateStore.list_candidate_ids(limit)`.

### 1.11 The two 422 sites become 200 with a stated reason (parent §2.2)

`POST /jobs/{id}/match` and `GET /jobs/{id}/board` currently answer
`422 "no materialized candidates to match"` when the feature store is empty.
An empty feature store is a **server-side** state; 422 blames the client for it,
and for a self-registered org it is permanent rather than transient.

Both return **200** with `pool_size: 0`, an empty `ranked`, and a new
`MatchResult.reason: Optional[str]` reading `no_materialized_candidates`. This is
the 200-with-per-section-status pattern `GET /candidates/{id}/card` already
models and `UI.md` §6 asks to be mirrored everywhere. The field is additive;
`reason` is `None` on every successful match.

### 1.12 Comp returns one shape (parent §2.3)

`POST /comp/estimate` returns `CompBenchmark` with `requisition_band`,
`position` and `delta_pct` all `None` — honest, because there is no requisition
to position against. `GET /jobs/{id}/comp` is unchanged. The wired UI already
unwraps `CompBenchmark` centrally, so this makes that unwrap correct on both
paths (parent §4.7).

### 1.13 OpenAPI: explicit `operation_id`, declared `response_model`, enforced by a test

**Measured on `main` today, and the headline number is four times what this
section first claimed.** 82 operations · **0** duplicate `operationId`s
(FastAPI derives them from function name + path + method, so they are unique but
unusable — `list_candidate_reports_candidates__candidate_id__reports_get`) ·
**0** operations with a *missing* success schema · and **38 of 82 whose success
schema is `{"type":"object","additionalProperties":true}`** — the handler is
annotated `-> dict`, so a generated client types the response `Record<string,
any>` and the caller is back to guessing.

> **The first count of this was wrong and the error is worth recording**, since
> it is the same shape as the defect this whole sprint exists to prevent. The
> check looked for a `200`/`201` response and reported "5 missing schemas" — all
> five were the OTP routes, which answer **202**. The check was measuring its own
> assumption about status codes, not the API. Re-run across every `2xx`, the real
> answer is that nothing is *missing* and 38 are *untyped*, which is a bigger job
> and a different one.

The 38 are mostly trivial to close: many already have a model and merely annotate
`-> dict` (`GET /verification/candidates/{id}/assurance` → `IdentityAssurance`,
`GET /portal/verifications` → `list[Verification]`), and most of the rest are
one-field acknowledgements (`{deleted: true}`, `{revoked: true}`) that share a
handful of tiny models.

Every route gets an explicit `operation_id` — set **once, in a loop over the
route table** rather than 82 times by hand, so a route added next sprint
inherits it — and a typed `response_model`. A test asserts uniqueness, presence
**and** that no success schema is a bare untyped object, over the live schema.
Generated and enforced, never hand-maintained, because the hand-maintained list
is always the one that drifts (S8.2's `OPEN_PATHS` finding).

---

## 2. Tenancy: the FIELD table

Written per §0. Every field of every new org-facing response, its source, and
what stops it naming somebody who is not this customer's.

### 2.1 `GET /screening/batches` → `BatchView[]`

| Field | Source | Foreign identity possible? |
|---|---|---|
| `id`, `name`, `domain`, `created_at` | `screening_batches`, `WHERE org_id = caller` | No — the org's own row |
| `created_by_org_user_id` | same row | No — an `org_users.id` of this org |
| `counts.*` | aggregate over this batch's items | No — integers |

### 2.2 `GET /screening/batches/{id}` → `BatchDetail`

As above plus `status` (derived, §4.4) and `counts` by item status. All
integers and enum members over one org's own rows.

### 2.3 `GET /screening/batches/{id}/queue` → `QueueRow[]` — **the new surface**

Every row comes from one `batch_items` row reached through
`batch_id → screening_batches.org_id = caller`. There is no join to another
org's data anywhere on this path (§1.1).

| Field | Source | Foreign identity possible? |
|---|---|---|
| `item_id`, `status`, `created_at`, `processed_at` | the item | No |
| `candidate_id` | the item, written at process time | **Global id, deliberately disclosed.** This is the person *this org uploaded*; candidates are global and deduplicated (parent §0.1), so the id may pre-date this org. It names their own upload's subject and nobody else's. Same disclosure the Phase-A upload response already makes, decided in `TENANCY.md` §7 |
| `resume_id` | the item | No — the row this org's upload created (Phase A guarantees a distinct row per owning org) |
| `report_id` | the item | No — `reports.org_id = caller`, and `GET /screening/reports/{id}` re-checks ownership rather than trusting this |
| `risk_band`, `risk_score`, `risk_confidence`, `depth_band`, `depth_score` | `risk_score` column + `signals` | No — floats and enum members |
| `loudest_signal` | `signals` | No — one of three fixed component ids |
| `resume_farm_band`, `resume_farm_score`, `resume_farm_corpus_size` | `signals` | **No, by construction: `matches[]` is never stored on the item.** Similarity, band and a corpus count with no identity behind them — the §3.4 redaction obtained by never holding the identities in the first place |
| `matched_existing`, `matched_on`, `duplicate_resume` | `signals` | No — a boolean and a match-type. Cross-corpus *facts*, disclosed on purpose and already argued in `TENANCY.md` §7: a count and a match-type are not an identity, and this is the fraud signal the wedge sells |
| `reason` | composed at read time from the scalars above (§1.2) | No — generated text over numbers this org owns |
| `error` | the item, set by the processor from `IngestRefused` | No — a fixed reason code (`empty_resume`, `pdf_parse_failed`, …), never model output and never another row's content |

### 2.4 `GET /screening/batches/{id}/summary` → `BatchSummary`

Counts by risk band, counts by item status, `n_screened`, and the top-N
`loudest_signal` values with their counts. Aggregates over §2.3's rows, so
every entry is an integer or an enum member. **No exemplars, no names, no ids** —
a summary that quoted its riskiest row would re-introduce every question §2.3
answers, for a screen `UI.md` §4.C describes as a screenshot-able roll-up.

### 2.5 What Phase B does *not* change

`GET /screening/reports/{id}` and `GET /screening/candidates/{id}/reports` keep
Phase A's redaction through `redact_for_org`. Phase B adds no new reader of a
`Report` on the org plane — the one place a batch touches reports is
`OrgScopedReads.report(org_id, report_id)`, which redacts before returning.

### 2.6 The guard

`tests/test_org_scope_guard.py` gains `screening` to its sanctioned-door set
(the service, whose every method takes `org_id` first). The batch store is
built **inside** `ScreeningService` and is deliberately **not** an attribute of
`Services`, so there is no unscoped batch read for a handler to reach — the same
structural move as Phase A's facade, one table further along.

The guard's stated limits (its docstring, `TENANCY.md` §5) are unchanged and
still honest: two watched attributes, one hop, line-level not dataflow.

---

## 3. Data model — migration `0019_screening_batches`

```
screening_batches
  id                      varchar(36) pk
  org_id                  → organizations.id   NOT NULL, ON DELETE CASCADE, indexed
  name                    text
  domain                  varchar(32)
  created_by_org_user_id  → org_users.id       NULL, ON DELETE SET NULL
  created_at              timestamptz

batch_items
  id            varchar(36) pk
  batch_id      → screening_batches.id  NOT NULL, ON DELETE CASCADE, indexed
  status        varchar(16)    pending | processing | done | failed
  raw_text      text           CLEARED on success (parent §4.2)
  text_sha256   varchar(64)    indexed, NOT unique (§1.9)
  candidate_id  → candidates.id  NULL, ON DELETE SET NULL
  resume_id     → resumes.id     NULL, ON DELETE SET NULL
  report_id     → reports.id     NULL, ON DELETE SET NULL
  risk_score    float          NULL — the sort key (§1.1)
  signals       json           NULL — ItemSignals, scalars only (§1.2)
  error         varchar(64)    NULL — a reason code, never free text
  created_at / claimed_at / processed_at   timestamptz

organizations
  + uq_organizations_name_ci  UNIQUE INDEX on lower(name)   (§1.7)
```

`screening_batches.org_id` CASCADEs while `resumes.org_id` SET NULLs, and the
contrast is the parent spec's (§4.1): a batch is the organisation's own work
product with no meaning once the org is gone; a resume is a *person's* data that
merely happened to be uploaded by that org.

The metadata drift / index / FK-ondelete / nullability guards extend to both new
tables.

---

## 4. Config (new knobs)

```yaml
# --- Screening batches (PI-8, S8.4 Phase B) ----------------------------------
screening_max_batch_items: 500          # registration is cheap; a sanity bound
screening_max_items_per_call: 5         # each item is a full nine-node graph run
screening_claim_timeout_seconds: 900    # a 'processing' item older than this reads pending
ret_batch_item_days: 90                 # unprocessed item text; S8.3 sweep input
page_default_limit: 50
page_max_limit: 200
materialize_max_candidates: 1000        # bound on POST /features/materialize
```

No secrets. No knob weakens §2's scoping or re-opens parent §2.1's collapsed
`invalid_code` mapping.

---

## 5. DPDP posture

- **No new `ConsentPurpose`.** A batch is the org's own upload record.
- `batch_items.raw_text` is personal data with no candidate to cascade from
  (parent §4.2) — **cleared on success**, kept on failure so the org can retry,
  bounded by `ret_batch_item_days`, and deletable today through
  `DELETE /screening/batches/{id}`.
- **`signals` cannot hold personal data** (§1.2), so `SET NULL` on the three
  subject pointers is genuinely sufficient and no erasure handler gains a line.
- Candidate erasure is unchanged and still cascades everything that is theirs.
- An org-plane read of a report stays audited exactly as Phase A left it.

---

## 6. Testing and smoke

Fully offline, `NullLLM`, no network.

**Ownership and tenancy**
- Another org's batch is **404** on every one of the seven routes, and the body
  is byte-identical to a batch id that never existed.
- A queue row for an item never carries `matches[]` — asserted on a batch whose
  report genuinely *has* farm matches, which requires seeding a second org's
  near-duplicate resume first (the Phase-A smoke shape).
- The scope guard sees the new handlers and still fails on a planted unscoped
  read (non-vacuity re-proven, not assumed).

**Batch machinery**
- Registration creates **no** candidates, no resumes and no reports.
- `process` is bounded by `screening_max_items_per_call`, resumable across
  calls, and a repeated call after completion is a no-op reporting `remaining=0`.
- An item stranded in `processing` past the timeout is reclaimed and completes.
- Two concurrent claims of the same item: exactly one wins (`rowcount` check).
- `raw_text` is empty after success and present after failure.
- A failed item reports a reason code and does not stop the batch.
- `DELETE /screening/batches/{id}` removes items and their text.

**Pagination**
- Paging the queue across an insert neither duplicates nor skips a row.
- **A cursor carries no authority.** A cursor minted on batch A, replayed
  against batch B, returns only B's rows — the cursor is a sort *position*, and
  ownership is enforced by the query's `org_id` filter, never by the cursor.
  Stated this way rather than as "a foreign cursor is refused", because
  refusing one would imply the cursor is what protects the boundary.
- A malformed or truncated cursor is a **422**, not a 500.
- `limit` still works unchanged on curation, job match and talent search.

**The rest**
- Both former 422 sites return 200 with `reason='no_materialized_candidates'`.
- `POST /features/materialize` materializes and the board then returns a
  non-empty pool over HTTP.
- `POST /comp/estimate` returns `CompBenchmark` with three null positioning
  fields.
- Case-insensitive org names: signup 409s on `"acme"` when `"Acme"` exists, the
  *address* enumeration property is unchanged, and the migrated database refuses
  the collision at the constraint.
- OpenAPI: every operation has a unique explicit `operation_id` and a success
  schema.

**Mutation-test** the claim predicate (§1.6) and the queue's ownership filter.
S8.2 recorded two surviving mutants on `AuthService`, one of which proved a
load-bearing comment simply wrong; these two are where a silent mutant is a
cross-tenant disclosure or a double-billed evaluation.

**Smoke** `scripts/smoke_s84b.py` (uvicorn, key-less, `DEE_OPENROUTER_API_KEY=""`
pinned — five smokes were found making live billed calls in Phase A): two orgs ·
register a batch · bounded processing to completion · progress from the derived
counts · the queue ranked with the farm signal present and identity absent · the
summary · cursor paging · a cross-org 404 on every route · delete · and the
materialization route un-breaking the board.

All nine existing regression smokes stay green.

---

## 7. Follow-ups left open

- **`OrgScopedReads.owns_candidate` is still unused** (§1.8) — consume it from a
  future org-plane candidate-detail route or delete it.
- **The queue does not span batches** ("everything I have ever screened,
  ranked") — parent §10, unchanged. Cheap once this read-model exists.
- **`batch_items` retention is declared, not swept** — `ret_batch_item_days`
  needs S8.3's sweep, still the oldest outstanding compliance gap.
- **Org-plane `/evaluate` and `/talent/search`**, and the two cross-corpus
  marketplace routes `TENANCY.md` §8 names — one tenancy decision covering all
  four, deliberately not taken here.
- **Rate limiting on `POST /process`** — S8.3, and it must be on that list: it
  is the most expensive endpoint the platform has.
