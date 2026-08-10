# SCREENING.md — the fraud-screen surface at volume (S8.4 Phase B)

Phase A made the wedge reachable by the customer who bought it: an organisation
could upload **one** resume and read its report. This is the surface the product
is actually sold on — drop in the resumes you have, watch them process, read a
ranked and reasoned risk queue.

Peer documents: `TENANCY.md` (who may read what), `AUTH.md` (how a principal is
established), `FABRICATION.md` (what the risk numbers mean).

A rule nobody can look up is a rule the next sprint reinvents differently, so
every section below states the decision **and the alternative it rejected**.

---

## 1. What a batch is, and why registration and processing are two calls

A batch is a real stored object: `screening_batches` plus its `batch_items`.
Registration inserts rows and **evaluates nothing**. Processing is a separate,
bounded call the client drives.

**Why not evaluate on upload?** Because it is not physically possible.
Measured, not assumed: there is **no worker, no scheduler and no
`BackgroundTasks` anywhere in `app/`**, and `POST /candidates` awaits the whole
nine-node graph inline. 500 resumes in one request is a request that times out.

**Rejected: a background worker.** It would need a queue, a supervisor and
somewhere to put failures — none of which exist, and all of which want S8.3's
observability underneath them first. Client-driven processing needs none of it,
survives a redeploy (§3), and adds no background execution to the repo ahead of
the tooling to watch it.

**Rejected: chunked upload that evaluates as it goes.** Same problem wearing a
different hat: the slow work still happens inside a request the client is
holding open.

---

## 2. The eight batch routes

All org-plane (`require_org`), all scoped by `org_id`, all answering **404 —
never 403 — for another organisation's batch** (§6 of `TENANCY.md`: a 403
confirms the thing exists).

| Method | Path | Answers | Notes |
|---|---|---|---|
| `POST` | `/screening/batches` | `BatchDetail` | `{name, domain, items:[{resume_text\|resume_pdf_b64}]}`. PDFs are decoded **here** |
| `GET` | `/screening/batches` | `BatchPage` | cursor-paged, newest first |
| `GET` | `/screening/batches/{id}` | `BatchDetail` | 404 if not yours |
| `POST` | `/screening/batches/{id}/process` | `ProcessResult` | bounded; call until `remaining` is 0. Rate-limited per ORG (S8.3) |
| `POST` | `/screening/batches/{id}/retry` | `RetryResult` | S8.3: re-queues `failed` items; does NOT process |
| `GET` | `/screening/batches/{id}/queue` | `QueuePage` | cursor-paged, riskiest first |
| `GET` | `/screening/batches/{id}/summary` | `BatchSummary` | counts only |
| `DELETE` | `/screening/batches/{id}` | `BatchDeleteResponse` | items CASCADE, text included |

**422 forks:** an empty batch, a batch over `screening_max_batch_items`, an
oversize item, a malformed cursor, and a PDF that will not parse.

**A corrupt PDF refuses the WHOLE registration**, naming the failing item's
index. Rejected: registering the good items and reporting the bad ones — a
half-registered batch leaves the org unable to say which files made it in, and
"which of my 400 files are missing?" is a worse question than "fix item 37 and
retry".

**PDF decoding happens at registration, not at processing**, because it is
cheap, deterministic and LLM-free. A corrupt file therefore fails immediately
rather than 400 items later.

**`created_by_org_user_id` is NULL for an `X-Org-Key` caller.** `X-Org-Key` is
an *organisation* credential with no human behind it, and inventing an actor
would be a false audit trail. The same decision, and the same words, apply to
`outcomes.recorded_by_org_user_id` below.

### 2.1 Closing the loop — two more org-plane routes (S8.5)

| Method | Path | Answers | Notes |
|---|---|---|---|
| `POST` | `/screening/reports/{id}/outcome` | `OutcomeRecordedResponse` | 404 if not yours; 422 on an unknown claim or over-long notes |
| `GET` | `/screening/reports/{id}/outcomes` | `OutcomeListResponse` | **this org's own** judgments, oldest first |

These sit beside `GET /screening/reports/{id}` (Phase A) rather than under
`/batches/`, because a judgment is about a report, not about the batch the
resume arrived in — an org may hold two reports about the same person from two
different batches, and each is judged separately.

**404 — never 403 — on a WRITE as much as on a read.** The instinct on a
refused write is 403, and it would confirm the report exists to anyone who
guessed an id. Both verbs answer byte-identically to an unknown id, asserted.

**The GET returns THIS org's judgments, not every judgment on the report.** A
report has exactly one owning organisation, so nothing here can leak
*sideways* — but an operator's internal note about a customer's report lives on
that same report, and the customer is not its audience. The operator's own
`GET /report/{id}/outcomes` still returns everything; that is the cross-tenant
support view.

**Append-only.** A reviewer changing their mind is a fact, not a correction,
and the sequence of judgments is precisely what a calibration harness wants to
look at. Rejected: upsert on (report, claim, org).

**Both doors share one constructor** — `app/reports/outcomes.build_outcome` —
which owns all three rules: the claim must belong to the report, `notes` must
fit `max_outcome_notes_chars` (2000), and the record must state its own
provenance. A rule enforced at one entry point and forgotten at the second is
this repo's signature defect; a test asserts the two doors **refuse the same
inputs**, because "both call the helper" is a claim about today's source.

---

## 3. Item status is stored; batch status is derived

`batch_items.status` is a column (`pending | processing | done | failed`).
`BatchStatus` is **computed at read time** from the item counts and is never
stored.

**Why derived:** a stored batch status goes stale the moment a process dies, and
nothing afterwards corrects it. A count is always true.

**The stale-claim reinterpretation, which is what makes this self-healing:** an
item still `processing` after `screening_claim_timeout_seconds` **reads** as
`pending` again, and becomes claimable again. So a batch interrupted by a
redeploy resumes on the next `process` call instead of wedging with items nobody
will ever claim. The read *reinterprets*; it never rewrites the row — a stored
status corrected by a read would be a fact that depends on who looked at it
last.

**The claim is a conditional UPDATE**, not a select-then-write. Two browser tabs
can both `POST .../process`, and each item is a full nine-node graph run — on a
live model, a double claim is a double bill. The `UPDATE` re-asserts
claimability in its own `WHERE` clause and counts only if `rowcount == 1`.

That invariant is **unreachable through two sequential `claim` calls** — the
second call's own `SELECT` filters the row out long before the `UPDATE` would —
so mutation testing found that deleting the `WHERE` clause survived every
end-to-end test. `ScreeningStore._try_claim` exists as a seam so a test can
build the interleaved state directly, the same way S8.2's two-challenge lockout
test had to.

**One item's failure never abandons the rest of the claim.** A batch of 500 with
one corrupt file has to finish. An unexpected exception fails *its* item with
`error="internal_error"` — the alternative is a row stuck in `processing` until
the claim times out for a reason nobody recorded.

---

## 4. The queue reads `batch_items` and never a `Report`

**This is the load-bearing design decision of the sprint.**

A `Report` is a *cross-corpus* object: `resume_farm.matches[]` names other
candidates' resumes, which may belong to another customer. That field is exactly
what leaked in Phase A. The queue read-model is therefore built from
`batch_items` **alone** — a path that never holds a `Report` has nothing to
forget to redact.

That is a stronger guarantee than redaction. Redaction is a rule somebody has to
remember at every new reader; absence is a property of the type.

It is also the only shape that **pages**: `risk_score` is a real column, where
the same number inside `reports.body` JSON is dialect-specific and unindexable.

The full report is still reachable — `GET /screening/reports/{id}` (Phase A),
through `OrgScopedReads`, redacted. The queue row carries its `report_id` so the
UI can drill in.

---

## 5. `ItemSignals` holds scalars only — and that is DPDP, not style

`batch_items.candidate_id` is `ON DELETE SET NULL`, deliberately: a candidate
erasing themselves must not silently rewrite an organisation's record of how
many resumes it screened. **Which means anything stored beside it outlives the
person it describes.**

A band and a score attached to a null candidate are not personal data. A copied
`fabrication_risk.reasoning` can quote claim text, and would be exactly the
orphan S8.1's fold of the report store existed to make impossible.

So `ItemSignals` holds numbers, booleans and closed-vocabulary enum members —
nothing else. `tests/test_screening_schema.py` asserts the field set **by name**,
so adding a prose field fails a test until somebody justifies it in writing.

**The one-line reason the queue shows is composed at read time**
(`compose_reason`), never stored. A column that cannot hold personal data needs
nobody to remember anything.

`farm_corpus_size` is a **count** of fingerprinted resumes compared against —
never their ids.

---

## 6. The cursor

Keyset, opaque, and **carrying no authority**.

* **Keyset, not offset:** a cursor is the sort-key tuple of the last row on the
  page, so a row inserted while a client is paging can be neither skipped nor
  served twice.
* **Opaque (base64):** not a promise about the encoding — a promise that clients
  cannot hand-build one and then depend on a shape we mean to change.
* **Not a capability.** Ownership is enforced by each query's own `org_id`
  filter. A cursor minted by one organisation and replayed by another merely
  positions inside the *second* organisation's own list; it reaches none of the
  first's rows (`smoke_s84b` check 11). Nothing here should ever grow an
  ownership claim — that would make a client-supplied string load-bearing for
  tenancy, the opposite of Phase A's whole argument.

**`POST /jobs/{id}/match` and `POST /talent/search` deliberately get no cursor.**
Both re-rank their pool on every request, so there is no stored key to page on
and a cursor would promise a stability they cannot keep. They keep `limit`, and
their OpenAPI descriptions say so — a client author cannot see a decision the
document does not state.

`GET /curation/skills/unmapped` **is** cursor-paged, with a stated limitation:
its sort key (`occurrences`, `last_seen`) is *mutable*, so paging there is stable
against inserts and not against re-observation. Acceptable because it is an
internal operator queue, not a customer surface — and written down rather than
discovered.

---

## 7. DPDP

`batch_items.raw_text` holds personal data with **no candidate to cascade
from** — a resume cannot be written to `resumes` before extraction, because a
resume row needs a candidate and identity resolution needs the extraction.

* **Cleared on success.** The text then lives in `resumes`, where candidate
  erasure already cascades. Deleted on a path that already runs (the S7.1
  challenge-hygiene pattern).
* **Kept on failure — and since S8.3 Phase A there is a path that uses it.**
  `POST /screening/batches/{batch_id}/retry` flips this batch's `failed` items
  back to `pending`, clearing `error`, `claimed_at` and `processed_at`; the
  existing `process` call then picks them up, so there is still exactly **one**
  door that evaluates an item. An item whose `raw_text` is already empty is
  reported as `skipped`, never re-queued — it either succeeded (text cleared)
  or failed as `empty_resume` and would fail identically, and a `requeued`
  count the next `process` call cannot honour would be a lie.
  *(This paragraph used to read "for a retry path that DOES NOT EXIST YET",
  which the S8.4 Phase B review wrote after catching the original overclaim.
  The capability has now shipped; the honest correction is this, not a
  deletion of the history.)*
* **`DELETE /screening/batches/{id}` ships in the sprint that creates the
  table** — a real delete path, not a promise of one.
* **`ret_batch_item_days` (90) is declared and NOT yet swept.** It is S8.3
  **Phase B** sweep input; Phase A shipped the limiter, the retry and the
  metrics, and the sweep is the phase after. The honest statement is still that
  nothing deletes on this window today — a retention window nobody enforces is
  a posture, and calling it anything else would be the overclaim `TENANCY.md`
  had six of.
* **Retention will bound the retry, and that coupling is the point.** Once the
  Phase B sweep clears `raw_text` past `ret_batch_item_days`, an item older
  than the window stops being retryable — its input is gone. Retaining the text
  is justified *by* the retry capability, and the retry is bounded *by* the
  retention window; neither half stands alone. Stated here and in
  `OPERATING.md` §6 rather than discovered by a customer whose retry silently
  reports `skipped: 1`.

No new `ConsentPurpose`. Screening an uploaded resume is the organisation's own
first-party processing of a document it holds.

**Outcome notes (S8.5) are the only free text a customer can write about a
person, and erasure reaches them without anybody remembering to:**
`outcomes.report_id → reports.id` CASCADE, `reports.candidate_id →
candidates.id` CASCADE. A candidate erasing themselves destroys every judgment
ever written about them, in the database.

Two decisions that follow from that:

* **The flywheel record carries the label, never the note.**
  `app/services/flywheel.py` is an append-only JSONL with **no erasure path**,
  so free text a human typed beside a candidate's name has no business in it.
  The label is the training signal; the prose never was. Changed at BOTH doors
  in one commit, because fixing the customer's and leaving the operator's is
  the defect shape rather than a smaller version of the fix.
* **`outcomes.org_id` is `SET NULL`, not `CASCADE`** — the contrast with
  `screening_batches.org_id` two rows up is the reasoning. A batch is the
  organisation's own operational work product with no meaning once they are
  gone; an outcome is a **label about a person's record** that the platform
  learns from, and the report it judges survives offboarding too
  (`reports.org_id`, same call). `recorded_by` exists *because* of that: with
  `org_id` alone, NULL would conflate "an operator recorded this" with "the
  customer who did has offboarded".

---

## 8. What is deliberately not here

* **A worker.** §1.
* **Rate limiting.** Still absent platform-wide (S8.2 decision 0.6, S8.3's job).
  `POST .../process` is bounded per call but nothing bounds the *call rate*.
* **A cross-batch queue.** "Everyone I have ever screened, ranked" is a
  different read-model over a different index, and inventing it before anyone
  has asked would be a second source of truth to keep correct.
* **Auto-reject, auto-shortlist, or hiding a candidate.** Advisory only, like
  everything else in this platform. Every scored response carries
  `advisory: true` and `human_review_required: true`.
* **Re-processing a finished item.** `process` on a completed batch is a no-op
  (0/0/0), not a re-run — re-screening the same text on a paid model because
  somebody clicked twice is not a behaviour to ship by accident.

---

## 9. Proof

* `tests/test_screening_schema.py` — the scalars-only rule, by field name.
* `tests/test_screening_models.py` — the three `SET NULL` subject pointers,
  asserted structurally *and* end to end through a real erasure.
* `tests/test_screening_store.py` — the claim cannot double-claim (including the
  interleaved race the public API cannot reach), stale claims heal, `raw_text`
  is cleared on success and kept on failure, unreadable signals degrade to
  `None` rather than bricking the batch.
* `tests/test_screening_service.py` — registration evaluates nothing, processing
  is bounded and resumable, a bad item fails alone, and a queue row cannot carry
  farm-match identities *on a batch whose report genuinely has them*.
* `tests/test_screening_tenancy.py` — every batch route 404s for another org,
  byte-identical to absence.
* `tests/test_screening_batches_api.py` — the surface over HTTP.
* `tests/test_org_scope_guard.py` — `screening` is a sanctioned door; the
  allowlist is **empty**; re-proven non-vacuous against a planted unscoped read.
* `tests/test_openapi_contract.py` — every route has an explicit unique
  `operation_id` and a typed success schema.
* `scripts/smoke_s84b.py` — 16/16 over real HTTP, key-less.

The outcome loop (§2.1):

* `tests/test_report_outcomes.py` — the shared constructor's three rules, and
  that `recorded_by` has no default in either the function or the model.
* `tests/test_report_store.py` — provenance survives the roundtrip against
  REAL organisation/org_user rows; `outcomes_for_org` separates "not yours"
  (`None`) from "nothing recorded" (`[]`).
* `tests/test_screening_outcome_api.py` — the loop over HTTP: 404 on both
  verbs byte-identical to absence, an operator's note invisible to the
  customer, both doors refusing the same inputs, and erasure destroying the
  judgment.
* `tests/test_migrations.py` — `0020`'s backfill to `operator`, no
  server_default left behind, and `org_id` SET NULL proven by deleting a real
  organisation.
* `scripts/smoke_s85_outcome.py` — 21/21 over real HTTP, key-less. The only
  place a real `org_user` id is attributed, because every unit test uses
  `X-Org-Key`, which has no human behind it.
* `scripts/check_ui_screening_contract.py` / `_browser.py` — the screen's own
  claims: the maxlength it advertises is the cap the API enforces, and clicking
  a button really records a judgment.
