# S3.3 — Coding-round results (schema + ingest) design

**Date:** 2026-07-25
**Sprint:** S3.3 (PI-3 Evaluation Ledger)
**Status:** Approved by user (2026-07-25) — data model boundary, consent reuse,
platform enum, field set all confirmed.
**Builds on:** S3.1 (ledger schema + DPDP consent), S3.2 (ledger HTTP APIs, org
API keys, query-time read enforcement + audit).

## What we are building

A new **coding-round results** record type in the evaluation ledger: rich,
structured results from automated coding assessments (HackerRank / Codility /
LeetCode / CodeSignal / HackerEarth / internal platforms) that a member org
submits about a consenting candidate, and that other member orgs can query
cross-org under read consent.

This is the user's declared **"far point"** for PI-3: **schema + ingest ONLY**.
The data model is made ready and the data flows through consent-gated, audited
APIs — but there is **no scoring logic, no cross-platform score normalization,
and no reputation aggregation**. Those are S3.4 (Bayesian cross-company
reputation). Like everything in this repo, the subsystem is advisory/data-only.

## Why a distinct record type (not `interview_records`)

`InterviewStage` already has a `coding` value, but an `interview_record` with
`stage=coding` is a *coarse pipeline-stage outcome* (advanced / rejected / …)
of a coding interview round. A coding-round **result** is a different
granularity: a structured automated-assessment result with a platform, a score
against a max, a percentile, and problem tags. Forcing it into
`interview_records` would either overload that table or bury the structured
fields in an untyped `evaluation_events` payload — either way defeating
"schema ready for PI-4 features and S3.4 reputation."

**Decision (approved):** a standalone `coding_round_results` table, a *peer* of
`interview_records`, sharing the same consent, audit, org-key, and DPDP
machinery. A coding assessment frequently arrives with no interview pipeline
attached, so it carries no required link to an interview record.

## Decisions taken (with user, 2026-07-25)

| Decision | Choice | Rationale |
|---|---|---|
| Data-model boundary | Standalone `coding_round_results` table (peer of `interview_records`) | Typed columns for PI-4/S3.4; no forced interview-pipeline parent |
| Consent purposes | **Reuse** `ledger_write` (submit) / `ledger_read` (query) | One consent object per candidate; no taxonomy fragmentation; an org with an active grant may submit/read both record kinds |
| `platform` representation | `CodingPlatform` StrEnum + `OTHER` escape + optional `platform_name` | Consistent with `InterviewStage`/`InterviewOutcome` code-constant taxonomies; controlled vocabulary for S3.4 grouping, long-tail still ingestable |
| Field richness | "Considered set": platform, assessment_name?, score, max_score?, percentile?, problem_tags[], taken_at, raw{} | `max_score` makes a raw score interpretable later; `raw` absorbs platform extras so S3.4/PI-4 need no follow-up migration |
| Events on coding rounds | **None** in S3.3 (no `append_event` analogue) | YAGNI — `raw` holds platform-specific detail; add later only if a real need appears |
| Config knobs | **None** | Nothing tunable; consent TTL + api-key bytes already cover the plane |

`?` = optional/nullable. `{}`/`[]` = JSON default.

## Data model — `coding_round_results`

New table on the shared candidates DB (`candidates_db_url`, same metadata root
and Alembic env as every other ledger table), Postgres-shaped on SQLite.

| Column | Type | Notes |
|---|---|---|
| `id` | String(36) PK (uuid) | |
| `org_id` | FK → `organizations.id` `ondelete=CASCADE`, indexed | submitting org |
| `candidate_id` | FK → `candidates.id` `ondelete=CASCADE`, indexed | DPDP erasure sweeps the row |
| `consent_id` | FK → `consent_grants.id` `ondelete=CASCADE`, indexed | the `ledger_write` grant this was submitted under (mirrors `interview_records`) |
| `platform` | String(32) | `CodingPlatform` value; `other` allowed |
| `platform_name` | Text, nullable | free platform name when `platform=other` |
| `assessment_name` | Text, nullable | e.g. "Backend SDE-2 Screen" |
| `score` | Float | primary metric, required |
| `max_score` | Float, nullable | denominator so a raw score is interpretable in S3.4 |
| `percentile` | Float, nullable | 0–100 platform rank |
| `problem_tags` | JSON | `list[str]`, default `[]` |
| `taken_at` | DateTime(timezone=True) | when the assessment was taken (parallel to `interviewed_at`) |
| `raw` | JSON | platform-specific extras, default `{}` — forward-compat, no future migration |
| `created_at` | DateTime(timezone=True) | server-set |

Indexes on `org_id`, `candidate_id`, `consent_id` (mirrors
`interview_records`). No `updated_at` — coding-round results are append-only
like interview records (never mutated in place).

### Contracts (`app/ledger/schema.py`)

Added alongside the existing ledger contracts (the module is the single home
for ledger data shapes and is still small):

- `CodingPlatform(StrEnum)`: `HACKERRANK`, `CODILITY`, `LEETCODE`,
  `CODESIGNAL`, `HACKEREARTH`, `INTERNAL`, `OTHER`. A code-constant taxonomy,
  never a config tunable — changing it is a reviewed schema decision.
- `CodingRoundResult(BaseModel)`: mirrors the row plus `id` / `created_at`.
  **Light data hygiene only** (this is *not* scoring): `percentile` is
  `Optional[float] = Field(default=None, ge=0, le=100)`; `score` and
  `max_score` are non-negative (`ge=0`). Deliberately **no** `max_score ≥ score`
  invariant — relating the two is normalization, which belongs to S3.4.
  `problem_tags: list[str] = []`, `raw: dict = {}`.

## Store (`app/ledger/store.py`)

Mirrors the interview-record methods exactly, including the same-transaction
audit-row rule (an action that committed is an action that was audited) and the
`consent.as_utc` datetime coercion (SQLite drops tzinfo on write).

- `submit_coding_round(*, org_id, candidate_id, platform, score, taken_at, assessment_name=None, platform_name=None, max_score=None, percentile=None, problem_tags=None, raw=None, now=None) -> CodingRoundResult`
  - Validates org + candidate exist → `LookupError` (API 404).
  - Checks an active `ledger_write` grant via `app.ledger.consent`; on denial
    raises `ConsentError` (API 403).
  - Stamps the authorizing `consent_id`; coerces `taken_at`/`now` via `as_utc`.
  - Writes the row **and** an audit row (`action="coding_round.submit"`,
    `actor_type="org"`, `entity_type="coding_round_result"`, candidate-linked)
    in one transaction.
- `query_coding_rounds_for_org(*, org_id, candidate_id, at=None) -> list[CodingRoundResult]`
  - Query-time `ledger_read` enforcement (mirrors `query_records_for_org`).
  - Audits **every** attempt — allowed *and* denied — as
    `action="coding_round.query"` in the same transaction (probing is itself
    observable). Denied → `ConsentError` (API 403). An org with an active
    `ledger_read` grant sees the candidate's coding rounds across **all** member
    orgs (reputation-network semantics), consistent with record reads.
- `coding_rounds_for_candidate(candidate_id) -> list[CodingRoundResult]`
  - Raw, ungated store read for internal / PI-4 materialization (mirrors
    `records_for_candidate`; query-time enforcement lives at the API layer).
- Row→contract converter `_coding_round(row)` normalizing every datetime
  through `consent.as_utc`.

## API (`app/api/routes.py`, `org_router`)

Org data plane (`X-Org-Key` → org via `authenticate_org`, each handler
`Depends(require_org)`); an org never needs the platform's admin secret to
touch its own data. No admin-plane changes (org lifecycle + consent already
exist from S3.2).

- `POST /ledger/coding-rounds` — body `CodingRoundSubmitRequest`
  (`candidate_id`, `platform`, `score`, `taken_at`, + optional
  `assessment_name`, `platform_name`, `max_score`, `percentile`,
  `problem_tags`, `raw`). Maps `ConsentError` → **403**, `LookupError` → **404**.
- `GET /ledger/candidates/{candidate_id}/coding-rounds` — query-time
  `ledger_read` enforcement; the store audits every attempt. `ConsentError` →
  **403**, `LookupError` → **404**.
- Missing/invalid `X-Org-Key` → **401** (via `require_org`, unchanged).
- **No** events endpoint on coding rounds (YAGNI).

## Migration `0005_coding_round_results`

- Down-revision `0004_org_api_keys`. `upgrade()` creates the table + the three
  indexes with CASCADE FKs; `downgrade()` drops the table.
- No changes to existing tables. The metadata-wide drift-guard test (extended
  in S3.2 to check indexes / FK `ondelete` / nullability) picks up the new
  table automatically.

## DPDP

- `coding_round_results` CASCADEs from `candidates.id`, so
  `CandidateStore.delete_candidate` (existing erasure path) sweeps a candidate's
  coding rounds with everything else. Audit rows are candidate-linked and swept
  too.
- `delete_organization` cascades the org's `consent_grants` → the
  `interview_records` **and** `coding_round_results` submitted under them, plus
  the org-scoped rows via the `org_id` CASCADE FK — identical offboarding
  semantics to interview records.
- First-party data only; consent object + delete path exist before any write —
  the non-negotiable convention holds.

## Testing strategy (TDD, fully offline)

- **Contracts:** `CodingPlatform` values; `CodingRoundResult` validation
  (percentile bounds, non-negative score/max_score, JSON defaults).
- **Model + migration:** the metadata-wide drift guard stays green with the new
  table (no bespoke assertion needed beyond its existing coverage); a targeted
  test that the table + CASCADE FKs exist.
- **Store:** submit refused without `ledger_write` (`ConsentError`); submit
  stamps `consent_id` + writes the audit row; unknown org/candidate →
  `LookupError`; query refused without `ledger_read` and the denied attempt is
  audited; query allowed under read consent returns cross-org rows and is
  audited; `coding_rounds_for_candidate` is ungated; DPDP candidate erasure
  cascades the rows; `delete_organization` cascades them.
- **API:** `POST` 403 without write consent, 200 with; `GET` 403 without read
  consent (audited) + 200 with; 401 without `X-Org-Key`; 404 unknown candidate.
- **Smoke** `scripts/smoke_s33.py` (uvicorn + scripted HTTP, key-less-capable):
  admin creates org + issues key + ingests a candidate → submit **403** without
  write consent → grant `ledger_write` → submit coding round → query **403**
  without read consent → grant `ledger_read` → query **200** (sees the round) →
  DPDP-erase the candidate → query **404**. Mirrors `scripts/smoke_s32.py`.

Estimated ~30–40 new tests (422 → ~455).

## Explicitly out of scope (S3.4 / later)

- Score normalization across platforms; any interpretation of `score` vs
  `max_score`; any use of `percentile` beyond storage.
- Reputation aggregation, recency decay, per-org reliability weighting.
- Coding-specific consent purposes (reusing `ledger_write`/`ledger_read`).
- Events / annotations attached to a coding-round result.
- Correlating a coding round to a specific `interview_records` row.
- Any config knob, any LLM call.

## Sprint workflow

spec (this doc) → implementation plan (`docs/superpowers/plans/`) → TDD-offline
build → `pytest -q` green → local smoke → update `LEDGER.md` (S3.3 section) and
`docs/ROADMAP.md` (status board `[x]`, Current state, session log).
