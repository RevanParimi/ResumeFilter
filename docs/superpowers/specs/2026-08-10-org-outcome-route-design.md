# S8.5 — an org-plane route for recording an outcome (design)

**Date:** 2026-08-10 · **Status:** spec · **Sprint:** S8.5 (closes the named gap)
**Parent:** `docs/superpowers/specs/2026-08-05-s84-ui-integration-surface-design.md`
**Touches `app/`.** Migration `0020`, two org-plane routes, one shared
constructor, three new columns on `outcomes`, one new config cap.

---

## 0. Why

`POST /report/{report_id}/outcome` is on the **admin** router
(`app/api/routes.py:2024`). A customer who screened 400 resumes, opened a
report and formed a judgment has **no way to record it** — an org session gets
401. The report screen currently states that in prose instead of showing four
buttons that would fail every time (UI.md §4.B).

That judgment is not a nice-to-have. It is **the** calibration input:

- PI-9 is the calibration harness, and the status board gates it on "real orgs
  submitting outcomes". Today no org *can*.
- Every band this product ships is a reasoned default, never validated against
  a hiring outcome (UI.md §7). The only thing that turns that into a measured
  claim is a customer telling us the resume really was fabricated.
- Without it the flywheel's `claim → probe → verdict → outcome` chain
  (`app/services/flywheel.py:1`) terminates at `verdict` for every row a
  customer ever produces.

## 1. The two routes

Both on `org_router`, both under `/screening/` beside the report read they
close the loop on:

```
POST /screening/reports/{report_id}/outcome   -> OutcomeRecordedResponse
GET  /screening/reports/{report_id}/outcomes  -> OutcomeListResponse
```

| Case | Answer |
|---|---|
| Report this org commissioned | 200 |
| Report another org commissioned | **404** |
| Report with `org_id IS NULL` (admin upload, pre-S8.4) | **404** |
| Unknown report id | 404 |
| `claim_id` not in the report's verdicts | 422 |
| `notes` over the cap | 422 naming the cap |

404-never-403 is TENANCY.md §6, unchanged: a 403 confirms the report exists.
An unowned report is nobody's, not everybody's (TENANCY.md §4), so it takes the
same 404 with no special case in the code — `NULL = 'org-a'` is false in SQL.

**The GET exists, and it is not optional.** Without it a recorded outcome is
invisible the moment the page reloads, the customer cannot tell whether their
click landed, and a second click silently appends a second row. The POST
response alone is a UI that only *looks* like it remembers.

**Append-only, like the admin route.** A reviewer changing their mind is a
fact, not a correction; the list is ordered oldest-first and the UI reads the
last one as current. Rejected: upsert-on-(report, claim, org). It would destroy
the sequence of judgments, which is exactly the thing a calibration harness
wants to look at (did they flip after the interview?).

## 2. The provenance columns — migration `0020_outcome_authorship`

`outcomes` records **what** was judged and **nothing about who judged it**.
That was tolerable while one operator was the only writer. It is not tolerable
the moment customers write to the same table.

Three columns, all on `outcomes`:

| Column | Type | Null | On delete | Why |
|---|---|---|---|---|
| `org_id` | String(36) FK `organizations.id` | yes | **SET NULL** | Which customer's judgment. NULL for an operator's. |
| `recorded_by` | String(16) | **no** | — | `operator` \| `organization`. |
| `recorded_by_org_user_id` | String(36) FK `org_users.id` | yes | **SET NULL** | Which human. NULL for a machine caller. |

**`org_id` is SET NULL, not CASCADE, and the contrast is the point.**
`screening_batches.org_id` CASCADEs because a batch is the org's own
operational work product with no meaning once they are gone. An outcome is a
**label about a person's record** that the platform learns from; destroying
labels on offboarding would silently degrade the model and leave the report
that *survives* (`reports.org_id` is SET NULL for the same reason) with a
judgment history full of holes. Same call as `reports.org_id`, same reasoning.

**`recorded_by` exists BECAUSE `org_id` is SET NULL.** With `org_id` alone,
`NULL` conflates two entirely different facts: "an operator recorded this" and
"the customer who recorded this has offboarded". PI-9 must never train on our
own operator's self-labels believing a customer produced them — that is
circular, and it is the difference between a calibrated model and one that
agrees with itself. One `String(16)` column keeps the fact after the FK is
nulled.

Rejected: deriving the source from `org_id IS NULL`. It is exactly the
conflation above, and it fails silently — the derived answer is always
*plausible*, which is the worst kind of wrong.

**Backfill:** every existing row was written through the admin route, so
`recorded_by = 'operator'` is a fact about them, not a guess. Added with a
`server_default` for the backfill which is then **dropped**, so the application
stays the source of truth for new rows — the 0004/0014 precedent, pinned by
`test_0014_leaves_no_server_default_behind_on_subject`'s sibling.

`recorded_by_org_user_id` is NULL for an `X-Org-Key` machine caller. Inventing
a human there would be a false audit trail — the same decision, and the same
words, as `screening_batches.created_by_org_user_id`.

## 3. One rule, two doors — `app/reports/outcomes.py`

This repo's signature defect, found by four consecutive branch reviews, is a
rule enforced at one entry point and forgotten at the second. Recording an
outcome is about to *have* a second entry point, and it carries three rules:
the claim must belong to the report, the notes must be bounded, and the record
must state its own provenance.

So the rules do not live in either route. One pure function, no I/O:

```python
class OutcomeRefused(ValueError):     # carries a stable reason code
    ...

def build_outcome(
    report, *, outcome, claim_id, notes, max_notes_chars,
    recorded_by, org_id=None, recorded_by_org_user_id=None,
) -> OutcomeRecord
```

Both routes call it and map `OutcomeRefused` to one 422. A test asserts the
admin route and the org route refuse the **same** inputs — because "both doors
call the helper" is a claim about today's source, and "both doors refuse the
same input" is a claim about behaviour.

`recorded_by` is a **required** argument with no default, and
`OutcomeRecord.recorded_by` is a required field. A default would be the
forget-me hazard this whole section exists to remove; a wrong provenance stamp
is invisible until PI-9 draws a conclusion from it.

## 4. The notes bound — `max_outcome_notes_chars`, both doors

`OutcomeRequest.notes` is an unbounded `str` into an unbounded `Text` column.
That is verbatim S7.2's `claim_ref` finding, which stored 5031 characters
including a salary and a UAN — and this field is about to be typed by
customers into a box beside a candidate's name.

`max_outcome_notes_chars: int = 2000` in `config.yaml`, enforced inside
`build_outcome`, so the admin door gains the bound in the same commit as the
org door. Fixing one and leaving the other is the defect shape, not a
smaller version of the fix.

2000 characters is a paragraph of reviewer reasoning and nowhere near a pasted
document. It is a cap against accident and abuse, not a UX constraint.

## 5. The flywheel record loses `notes`, at both doors

The flywheel is a JSONL training sink with **no erasure path** —
`app/services/flywheel.py` appends and never deletes. The admin route logs
`notes` into it today. Multiplying that by every customer would put free text a
human typed about a named candidate into an append-only file that no DPDP
delete can reach.

The label is the training signal; the prose never was. The logged record
becomes `{record_type, report_id, claim_id, outcome, org_id, recorded_by}` —
strictly more useful for calibration (it gains provenance) and strictly less
personal (it loses the only free text it carried). No test asserts `notes` in a
flywheel record; this was measured before deciding, not assumed.

The notes still live in `outcomes`, where erasure genuinely reaches them:
`outcomes.report_id → reports.id CASCADE`, and `reports.candidate_id →
candidates.id CASCADE`. A candidate erasing themselves destroys every judgment
ever written about them, in the database, without anybody remembering to.

## 6. Tenancy — the facade grows a write, and the class stops calling itself Reads

Two new methods on `app/screening/scope.py`, both taking `org_id` first (pinned
by `test_every_facade_read_takes_org_id_first`, which introspects rather than
hardcodes, so they are covered on arrival):

```python
def record_outcome(self, org_id, report_id, *, ...) -> Optional[OutcomeRecord]
def outcomes(self, org_id, report_id) -> Optional[list[OutcomeRecord]]
```

`None` means "not yours, or absent" and the route maps it to 404 — identical to
`.report`, so the two reads and the one write cannot disagree about what a
missing report looks like.

**The class is renamed `OrgScopedAccess`.** A class named `OrgScopedReads`
holding a write is a lie in the one file whose entire job is being trustworthy
about scope, and the next person adding a write will either put it somewhere
worse or believe the name. `screening_scope` — the attribute the guard watches
— **does not change**, so `tests/test_org_scope_guard.py` needs no edit and the
guard keeps covering routes nobody has written.

Rejected: a third sanctioned door (`OrgScopedWrites`). A second facade over the
same store means two places to forget the same rule, and the guard's
alternation would grow a third name to keep ordered — cost with no protection.

## 7. What is deliberately not here

- **No new consent purpose.** An outcome is the org's own judgment about a
  report the org commissioned. It reads nothing new about the candidate; the
  consent question was settled when they were allowed to read the report.
- **No calibration.** Recording labels is not analysing them. PI-9 reads this
  table; nothing in this change scores, weights or aggregates.
- **No auto-anything.** `advisory` and `human_review_required` are untouched.
  A `verified_fabricated` outcome changes no band, no score, no ranking, and
  nothing about that candidate anywhere else in the platform.
- **No cross-org visibility.** The GET filters to the caller's own `org_id`, so
  a customer never reads an operator's internal note about their own report —
  and an operator's cross-tenant view (`GET /report/{id}/outcomes`) still shows
  everything, which is what it is for.
- **No rate limit.** There is still none anywhere (S8.3). The notes cap bounds
  one call's damage; the number of calls is S8.3's problem, named not hidden.

## 8. Verification

1. **Unit/TDD** — a failing test before every change; `pytest -q` from 1553.
2. **The one-rule-two-doors test** — both routes refuse the same over-long
   notes and the same unknown claim id.
3. **Cross-tenant** — org B gets 404 on both routes for org A's report,
   byte-identical to an unknown id; an operator's outcome does not appear in
   the org's list; the org's outcome DOES appear in the operator's.
4. **Migration** — the existing guards (`test_migrated_fks_and_nullability_match_orm`,
   the index guard) cover the new columns for free; plus a backfill test that an
   existing outcome reads `operator`, and a no-server-default-left-behind test.
5. **Erasure** — deleting the candidate destroys the outcome, proven through
   the real FKs on the migrated schema.
6. **Smoke** — `scripts/smoke_s85_outcome.py`: sign up an org over HTTP, upload,
   read the report, record an outcome, read it back, prove a second org's 404,
   and prove the erasure. `DEE_OPENROUTER_API_KEY` pinned empty (three sprints
   running, this is the trap that bills money).
7. **UI** — the four buttons come back on the report screen, with the three
   layers a CI-less frontend needs: `check_ui_bindings.js`,
   `check_ui_screening_contract.py`, `check_ui_screening_browser.py`.
