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
people. A `CASCADE` typo on either new FK would pass every test in this repo
except one: `test_deleting_an_org_leaves_the_resume_intact_and_unowned`
(`tests/test_upload_ownership.py`) and smoke check 12 in `smoke_s82`'s
family — it would be silent until the first organisation is ever deleted.

The pre-existing migration-drift / index / FK-ondelete / nullability guards
(`tests/test_migrations.py`) extend to both columns, so the migration and the
ORM models cannot silently disagree on either the nullability or the ondelete
verb.

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
   reachable from an org handler, and both report-returning methods
   (`.report`, `.reports_for_candidate`) redact (§6) before returning, so a
   handler cannot forget the redaction either.
2. **A structural guard — `tests/test_org_scope_guard.py`.** It walks the
   *live* FastAPI route table, matches per-statement (not per-function — a
   sanctioned call earlier in a handler must not blanket-exempt the rest of
   it), follows one hop into same-module helpers, and fails the build if any
   org-plane handler reaches a store read that did not go through the facade.
   Like `tests/test_route_table_guard.py` (`AUTH.md` §2), it covers routes
   **not yet written**, which is the property that makes it worth more than
   any number of individual tests. It carries a line-level allowlist with a
   written reason per entry — `similar_resumes` is cross-tenant *by design*
   (fraud detection has to scan the whole platform), and its output is
   redacted at the boundary instead of being blocked at the source.
3. **The guard is proven non-vacuous.** S8.2 recorded the exact trap: FastAPI
   0.138 does not flatten `include_router` into `app.routes`, so a naive walk
   saw 9 routes instead of 63 and would have passed while inspecting almost
   nothing. This guard asserts a floor (`>= 20` `@org_router` routes) on what
   it actually inspected, and has been watched going red on a deliberately
   unscoped handler planted in a fixture.

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
protect: that the report exists at all, just not for you. This is the same
precedent S6.4's cross-candidate isolation and S7.1's verification ownership
check already set — a foreign id on the wire gets one refusal, not a menu of
them.

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

Also out of scope, by the same spec section: a worker/queue/scheduler (no
background execution exists anywhere in `app/` yet — that is S8.3's), rate
limiting, row-level security or a tenant-per-schema database (this sprint is
application-level scoping with a structural guard; if the hosting posture ever
demands database-level isolation, this is the layer it replaces, not one it
fights), and org offboarding as a product *flow* — the `SET NULL` semantics
(§1) make offboarding *safe*, but there is no admin route to delete an
organisation today, which is why the smoke does not exercise it over HTTP (see
below).

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
that stays unowned and invisible to every org. The org-deletion `SET NULL`
behaviour is deliberately **not** repeated in the smoke — there is no HTTP
route to delete an organisation (§8), and
`test_deleting_an_org_leaves_the_resume_intact_and_unowned` already covers it
at the layer where it is reachable.
