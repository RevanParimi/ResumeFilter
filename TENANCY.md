# TENANCY.md — org-plane data ownership (S8.4 Phase A)

Peer of `AUTH.md` / `PORTAL.md` / `VERIFICATION.md`.
Design record: `docs/superpowers/specs/2026-08-05-s84-ui-integration-surface-design.md`
§0.1, §0.4, §3.

Before S8.4 an organisation that self-registered through S8.2 could log in and
do **none** of the things it signed up to do: uploading a resume, reading a
fraud report, and listing a candidate's reports were all admin-only. Making the
wedge reachable by the customer who bought it required first deciding what
"the customer's data" even means — nothing in the schema had ever recorded
which organisation uploaded a resume. That decision is this document.

---

## 1. The model — ownership is a property of the upload

`resumes.org_id` and `reports.org_id` (migration `0018_upload_ownership`):
nullable, FK to `organizations.id`, indexed, **`ON DELETE SET NULL`**.

**Nullable** because every pre-S8.4 row has no owner, and every admin-plane
upload legitimately has none too. A null `org_id` means *unowned* — visible to
operators, invisible to every organisation. No data migration invents an owner
that never existed.

**`SET NULL`, not `CASCADE` — the load-bearing choice.** An organisation
offboarding must not destroy a candidate's resume. That resume is the
*person's* data; the only cascade permitted to delete it is the candidate's own
erasure (`resumes.candidate_id → candidates.id ON DELETE CASCADE`, pre-existing
and unchanged). An org leaving turns its uploads unowned; it does not erase
people.

**What catches a `CASCADE` typo, precisely.** A typo in the *migration* is
caught by `test_migrated_fks_and_nullability_match_orm`
(`tests/test_migrations.py`), which compares the migrated schema against the ORM
metadata for every table in `CANDIDATE_TABLES` + `REPORT_TABLES` — `resumes` was
added to that tuple during this sprint precisely because it was **not** covered
before, and the guard was proven red on a deliberate `CASCADE` before being
trusted. A typo in *both* the migration and the ORM model agrees with itself and
slips past that guard; only
`test_deleting_an_org_leaves_the_resume_intact_and_unowned`
(`tests/test_upload_ownership.py`) catches it, by actually deleting an
organisation and asserting the resume survives unowned.

**There IS an HTTP route that triggers this**, and an earlier draft of this
document said there was not — twice, in §8 and §9, which is why the smoke
originally skipped it. `DELETE /ledger/orgs/{org_id}`
(`app/api/routes.py:671`) calls `LedgerStore.delete_organization`, which does
`session.delete(OrganizationRow)`: exactly the deletion the `SET NULL` contract
is about, reachable today with an admin key. `smoke_s84a` now exercises it end
to end. Without these the mistake would be silent until the first offboarding.

## 2. Why candidates stay global

**There is deliberately no `candidates.org_id`.** Candidates remain global and
deduplicated by email hash — that is S1.1 identity resolution, and it is the
thing that makes cross-corpus near-duplicate ("resume farm") detection worth
anything at all. Two agencies who both screen the same person are comparing
notes on one candidate row, whether they know it or not; collapsing that into
per-org candidate copies would blind the fraud check to exactly the pattern it
exists to catch — the same resume, reused across customers.

What gains an owner is the *act of uploading*, not the person. A candidate
uploaded by two different agencies appears in both agencies' queues, from one
candidate row, because each agency owns its own *upload* of her.

**Including when the bytes are identical**, which is the case worth stating
because it is the likeliest real input: two agencies are routinely handed the
*same* PDF for the same person. One `org_id` column cannot hold two owners, so
identical text arriving from a *different* organisation gets **its own resume
row** (next version, same `text_sha256`) owned by that organisation, rather than
silently joining somebody else's row. The consequences, all deliberate:

- `duplicate_resume` stays `True` — it is a fact about the *text* ("these exact
  bytes were uploaded before"), which is the fraud signal, and it is unaffected
  by which row the upload lands on.
- The **same** org re-uploading its **own** identical text reuses its existing
  row: no version bump, no duplicate row. Idempotent, and pinned by a test.
- The **admin plane never diverges.** An upload with no owner (`org_id is None`)
  reuses whatever row is already there, exactly as it did pre-S8.4 — which is
  why every pre-existing dedup test and smoke passes unmodified.
- Lookup prefers *this caller's own* row. Once two orgs hold rows for one text,
  taking the first match would hand org B org A's row and spawn a third row on
  every re-upload.
- **An offboarded org leaves one orphan row per (candidate, text) it held.**
  `SET NULL` (§1) turns its rows unowned rather than deleting them, and the
  admin fallback only ever adopts the lowest-version match, so a churned org's
  row is never re-adopted by an organisation. Bounded by org churn, invisible to
  every org, and the alternative — deleting it — is the `CASCADE` this document
  exists to refuse.
- **Farm detection now sees N matches where one person's resume is held by N
  orgs.** The banding is unaffected: `distinct` counts `candidate_id`s and the
  duplicate rows share one, and `similar_resumes` excludes the uploader's own
  candidate, so a row is invisible to its own re-upload. What does shift
  slightly is the reviewer-facing `reasoning` string and the `rf_max_matches`
  truncation budget, which can now spend slots on duplicates of one person. It
  is a sensitivity change to a fraud detector, so it is recorded rather than
  left to be rediscovered.

**Rejected — a shared candidate universe** (no per-upload ownership at all).
Cheapest to build, and arguably the honest description of one shared corpus.
But "did the other agency see the report I paid for?" is the first question a
staffing buyer asks, and the honest answer under that design is yes.

**Rejected — one deploy per customer.** Keeps multi-tenancy a schema non-issue,
but it hard-codes a hosting posture that is still an open question and it kills
the cross-customer resume-farm signal — a genuine product advantage — outright.

## 3. "My candidates" is derived

There is exactly one home for the ownership fact: the upload row. "The
candidates my org has ever screened" is not stored anywhere — it is derived by
joining through `resumes` (`org_owns_candidate`, `for_candidate_and_org` in
`app/candidates/store.py` / `app/reports/store.py`). The cost is a join per
query; the benefit is that there is no second copy of "who owns this" that can
drift from the first. A `candidates.org_id` column would have been exactly that
second copy, and it would have been wrong the moment two orgs uploaded the same
person.

## 4. What "unowned" means

A null `org_id` — every pre-S8.4 row, and every row an operator uploads through
the admin plane today — belongs to **nobody, not everybody**. It is readable on
the admin plane (operators see everything, by design — see §7) and invisible on
every org's screening surface. The alternative reading, "unowned means every
org can see it," would make the admin plane's own upload history a silent
cross-tenant leak the day org-plane routes existed at all.

This is why `OrgScopedReads.report` and `.reports_for_candidate` (§5) never
special-case a null `org_id` as a match: an org-scoped store read only ever
matches rows whose `org_id` equals the caller's own id, and `NULL = 'org-a-id'`
is false in SQL, not true. The admin plane's own upload of `OTHER` in the smoke
below is exactly this case, proven over HTTP.

## 5. The enforcement — the facade and the guard

The lesson from four consecutive branch reviews — S7.1's `start()`, S7.2's
`claim_ref`, S7.3's audio path, S8.2's two-challenge lockout — is that **a rule
enforced by remembering to enforce it will be forgotten at the second door.** A
tenancy rule spread across org-plane routes is exactly that shape by
construction, so org handlers get no option to forget it:

1. **A scoped facade — `app/screening/scope.py`, `OrgScopedReads`.** Every
   method takes `org_id` as its *first* argument, there is no unscoped read
   **on this object**, and both report-returning methods (`.report`,
   `.reports_for_candidate`) redact (§6) before returning, so a handler cannot
   forget the redaction either.

   Note the precise claim: no unscoped read *on the facade*, not "no unscoped
   read reachable from an org handler". The latter would be false.
   `POST /screening/candidates` reaches `_ingest_one`, which calls
   `similar_resumes()` (cross-tenant by design) and `get_candidate()` — five
   such lines, each carrying a written justification in the guard's
   `ALLOWLISTED_LINES`. The defense for those is redaction at the boundary
   (§7), not absence of the read.
2. **A structural guard — `tests/test_org_scope_guard.py`.** It walks the
   *live* FastAPI route table, matches one **physical line** at a time (not
   per-function — a sanctioned call earlier in a handler must not
   blanket-exempt the rest of it), follows one hop into same-module helpers,
   and fails the build if an org-plane handler reads `services.report_store`
   or `services.candidates` without going through the facade. Like
   `tests/test_route_table_guard.py` (`AUTH.md` §2), it covers routes **not yet
   written**, which is the property that makes it worth more than any number
   of individual tests. It carries a line-level allowlist with a written reason
   per entry — `similar_resumes` is cross-tenant *by design* (fraud detection
   has to scan the whole platform), and its output is redacted at the boundary
   instead of being blocked at the source.

   **What it does not cover, stated plainly, because a guard's worth is its
   honesty about its own reach.** It watches exactly two attributes —
   `report_store` and `candidates`. `services.features`, `.jobs`, `.ledger`,
   `.portal`, `.verification`, `.interview`, `.dashboard` and `.comp` are
   invisible to it (see §8 for two org-plane surfaces that matters for).
   Helpers in *other* modules are skipped entirely, so the "one hop" is one hop
   *within `routes.py`*. The receiver is resolved by AST for the three
   plain-name binding forms (`=`, annotated `:`, walrus `:=`), so a renamed
   local counts — but **not** tuple unpacking, not the container passed into a
   helper as an argument, not `getattr(services, "report_store")`, not a
   backslash continuation, and not the inline `_services(<name>)` spelling when
   the parameter is called anything but `request`. A read two hops of delegation
   deep also passes unseen. The guard's own module docstring carries this same
   list, and it is deliberately explicit: an overstated reach is worse than a
   narrow one, because it is what stops somebody adding the check that would
   have caught the next bug.
3. **The guard is proven non-vacuous.** S8.2 recorded the exact trap: FastAPI
   0.138 does not flatten `include_router` into `app.routes`, so a naive walk
   saw 9 routes instead of 63 and would have passed while inspecting almost
   nothing. This guard asserts a floor (`>= 20` `@org_router` routes) on what
   it actually inspected, and its **detector** is pinned red against unscoped
   handler *sources* — a direct read, a read hidden one hop inside a helper, a
   violation sharing a function with a sanctioned call, and three receiver
   spellings including a renamed local. The walker was additionally watched
   going red against the **live** route table during the build, by temporarily
   pointing `screening_get_report` at the store; that step is a manual
   verification, not a committed fixture.

**This is not a hypothetical defect.** Building this guard *found* one: Task
6's `POST /screening/candidates` computed `resume_farm` by scanning the whole
platform's fingerprints (fraud detection has to), and the upload response
returned it — with real `candidate_id`/`resume_id` of other customers'
candidates — unredacted, in both the top-level `resume_farm` field and the
embedded `report.resume_farm`. The read routes were redacted from the start;
the *ingest* response never was, because the spec had counted two org-facing
readers and missed the third. The guard went red on it before a customer could
have found it. §6 and the sprint's smoke are both built around this leak.

## 6. 404, never 403

Another org's report is **indistinguishable from one that does not exist** —
same status code, same response body, byte for byte. `OrgScopedReads.report`
returns `None` for "not found" and "found but not yours" alike, and the route
maps `None` to one `404`. A `403` would leak the one fact this design exists to
protect: that the report exists at all, just not for you. This follows S6.4's
cross-candidate isolation, where an unknown candidate id and one belonging to
somebody else both answer `404` so neither can be probed for.

**The precedent is S6.4's, not S7.1's** — worth naming exactly, because the
org-plane verification route does the opposite:
`GET /verification/candidates/{id}/assurance` answers `403` on a consent failure
and `404` on a lookup failure (`app/api/routes.py:1284-1287`), which does
distinguish "exists but you may not" from "does not exist". That is defensible
there — consent is a fact the org already knows it lacks — but it is not the
rule this document is stating, and citing it as though it were would tell a
future reader the opposite of §6.

## 7. The one redaction

`resume_farm.matches[]` may name resumes belonging to another customer. An
organisation is allowed to learn *that* a near-duplicate exists and *how
similar* it is — that is the fraud signal — never *whose* it is.

`app/screening/projection.py` holds the **one** place that stripping happens:
`_stripped_matches`, which nulls `candidate_id`/`resume_id` on every match and
leaves everything else (`similarity`, the band, the count) untouched. Every
org-facing reader goes through it, directly or via one of two callers:

- `redact_for_org(report)` — the single-report read and Phase B's queue
  read-model.
- `redact_ingest_response_for_org(resp)` — the upload response itself, which
  carries the *same* assessment twice (top-level `resume_farm`, and again
  inside the embedded `report`). Both copies are stripped, or the second one
  re-leaks what the first just redacted.

Two copies of the strip would be a bound that holds on one path and lapses on
another — the exact shape of §5's leak, and the same defect shape S7.2's
`claim_ref` and S7.3's transcript findings were. One function, two thin
callers, is the whole defense.

**`None` and empty round-trip untouched.** A report with no `resume_farm` at
all stays `None`; a present-but-empty assessment stays present and empty. A
null and an `insufficient_data` conclusion are different facts (no assessment
ever ran, vs. one ran and could not say), and this function's one job is
stripping counterparty identity, not inventing or erasing signal.

The org still sees the **full** report otherwise — `verdicts[]`,
`missing_signals`, `probes[]` included. Those are what convert a score into an
action; withholding them would make the numbers less useful without making
them more honest (spec §0.4, §7).

**What is deliberately *not* redacted, decided rather than overlooked.** The
upload response (`CandidateCreateResponse`) also carries `resume_version`,
`matched_existing`, `matched_on` and `duplicate_resume`, and these are
**cross-corpus by nature**:
`resume_version` is a per-candidate counter spanning every organisation, so an
org uploading a person for the first time can see a version above 1 and infer
that other uploads of that person exist. `matched_existing` / `matched_on` say
the same thing more directly, and `duplicate_resume` says the sharpest version
of it: *these exact bytes* have been uploaded for this person before — possibly
by a different customer.

These stay, and the reasoning is the same principle as the `matches[]` strip
rather than an exception to it: **a count and a match-type are not an
identity.** An org learns *that* this person is already known to the platform
and *what* identified her — never to whom, never how many organisations, never
which. That is precisely the fraud signal the wedge is sold on (`UI-Spec.md`
item 9 asks for these ingest-time signals to be surfaced, not hidden), and
suppressing it would blind the product to "this candidate is being shopped
around" while protecting nothing that §7's strip does not already protect.

It is written down here because the original spec called the `matches[]` strip
"the one redaction" and never mentioned these fields — the same
counted-the-readers-not-the-fields omission that let the ingest-response leak
through (§5). Naming the disclosure makes it a decision instead of an oversight.

## 8. What is deliberately not scoped yet

`POST /evaluate` and `POST /talent/search` remain **admin-only** this sprint.
Both are named non-goals in the spec (§8), not oversights:

- **`POST /evaluate` is candidate-less** — it scores ad-hoc resume text with no
  candidate or resume row behind it, so there is no upload to stamp an owner
  on. Org-scoping it raises the tenancy question in a form nothing in the UI
  needs yet.
- **`POST /talent/search` reads the global feature store** — a genuinely
  cross-corpus surface, which wants its own scoping decision rather than
  inheriting this sprint's per-upload model by default.

**Two org-plane routes are in the same category and are already reachable by a
customer**, which is why they are named here rather than left to be
rediscovered: `POST /jobs/{req_id}/match` and `GET /jobs/{req_id}/board` are
both `@org_router`, and the ranking underneath them reads
`features.vectors_for_view(...)` with **no org filter**
(`app/matching/store.py:188`), returning `candidate_id`s drawn from the whole
platform. This is pre-existing S5.1 marketplace design, not an S8.4 regression,
and it does not leak anything §7 redacts — but it means the org plane has more
than one cross-corpus data surface, and only the screening one is scoped by this
sprint. The guard in §5 cannot see it either, since it watches `report_store`
and `candidates` and this reads `features`. Scoping the marketplace surfaces is
the same open decision as `/talent/search`, and it should be taken once, for all
three.

Also out of scope, by the same spec section: a worker/queue/scheduler (no
background execution exists anywhere in `app/` yet — that is S8.3's), rate
limiting, row-level security or a tenant-per-schema database (this sprint is
application-level scoping with a structural guard; if the hosting posture ever
demands database-level isolation, this is the layer it replaces, not one it
fights), and org offboarding as a product *flow* — the `SET NULL` semantics
(§1) make offboarding *safe*, and `DELETE /ledger/orgs/{org_id}` already
performs it on the **admin** plane; what does not exist is an org-plane
self-service flow, and that is the part deferred (`UI-Spec.md` item 17).

## 9. Proof

`tests/test_upload_ownership.py`, `test_screening_projection.py`,
`test_screening_scope.py`, `test_screening_api.py`, `test_org_scope_guard.py`,
`test_auth_org_name_taken.py` cover this at the unit/integration level.

`scripts/smoke_s84a.py` proves it end to end over real HTTP, with two
organisations racing over the same person: a taken organisation name refused
before any code is sent; two orgs unable to read each other's reports, the
refusal a byte-identical 404; the same person deduplicating to one candidate
row while each org sees only its own report; the resume-farm redaction on a
report that genuinely has matches, both from a same-org `GET` and — the
sprint's headline guarantee, run the way a real customer would trigger
it — from the **upload response of a second, different org**, on both the
top-level and the embedded copy of the assessment; and an admin-plane upload
that stays unowned and invisible to every org; and finally **the `SET NULL`
contract itself, over HTTP** — an organisation is deleted through
`DELETE /ledger/orgs/{org_id}` and its uploaded resume is shown to survive,
readable by the admin plane and now reading as unowned. That last pair exists
because the sprint originally skipped it on a false premise: the plan, this
document and the smoke all asserted there was no HTTP route to delete an
organisation. There is. `SET NULL` is the load-bearing choice of the whole
sprint, and it is the one thing a `CASCADE` typo would destroy silently, so it
is worth proving at the layer a real operator would trigger it rather than only
in a unit test.
