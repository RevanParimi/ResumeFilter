# LEDGER.md — cross-company evaluation ledger (PI-3)

The ledger lets member companies share interview outcomes about consenting
candidates. DPDP consent is a first-class schema object, not a patch: no
write happens without an active grant, every mutation is audited, and
candidate erasure sweeps every ledger trace.

## S3.1 — schema + consent model (this sprint)

**Tables** (migration `0003_evaluation_ledger`, same DB/metadata root as
candidates — `candidates_db_url`):

| Table | What | DPDP linkage |
|---|---|---|
| `organizations` | member companies (`active`/`suspended`) | none — survives erasure |
| `consent_grants` | purpose-scoped, org-scoped, expiring, revocable consent | CASCADE from `candidates.id` |
| `interview_records` | one outcome one org submitted (stage: screen/tech/coding/hm) | CASCADE |
| `evaluation_events` | append-only detail per record (scores, notes) | CASCADE |
| `audit_log` | append-only audit of every mutation | candidate-linked rows CASCADE; org-only rows survive |

**Consent model** (`app/ledger/consent.py`, pure):
- Purpose-scoped: one purpose per grant — `ledger_write` (org may submit
  records) or `ledger_read` (org may query history; enforced in S3.2).
- Org-scoped: a specific org, or `org_id=NULL` = any member org.
- Always expires: grants without explicit expiry get
  `ledger_consent_default_ttl_days` (config, default 365). No perpetual consent.
- Revocable: revocation is an UPDATE (`revoked_at`), never a DELETE — the
  audit trail keeps the fact of having consented. Point-in-time checks before
  the revocation instant still see the grant as active (PI-4 needs this).
- Erasure trumps everything: `CandidateStore.delete_candidate` cascades away
  grants, records, events, and candidate-linked audit rows.

**Write-time gate** (`app/ledger/store.py`): `submit_interview_record` raises
`ConsentError` without an active `ledger_write` grant and stamps the record
with the authorizing `consent_id`. Every mutation writes its `audit_log` row
in the same transaction. Actor model pre-auth (S3.2 adds org API keys):
consent actions → `candidate`, record/event writes → `org`, org management
→ `system`.

**Org deletion is a hard cascade, deliberately.** `delete_organization`
CASCADEs through that org's `consent_grants` → their `interview_records` →
`evaluation_events`, hard-deleting all of it (unlike candidate erasure, this
is not soft-revoke-then-audit). This is intentional org-offboarding
semantics, not a DPDP requirement — candidate-linked `audit_log` rows are
unaffected and survive the org's departure.

**Not in S3.1:** HTTP APIs, query-time `ledger_read` enforcement, org API
keys, audit of reads (all S3.2); coding-round ingest (S3.3); reputation
aggregation (S3.4).

## S3.2 — ledger APIs (this sprint)

Two auth planes over `LedgerStore`:

- **Admin plane** (existing `X-API-Key` shared secret, `router`): org lifecycle
  and consent recording — platform operations.
  - `POST /ledger/orgs` → creates an org, returns a one-time `api_key`
    (only its sha256 hash is stored); duplicate name → 409.
  - `GET /ledger/orgs` · `POST /ledger/orgs/{id}/api-key` (rotate) ·
    `DELETE /ledger/orgs/{id}` (hard cascade offboarding).
  - `POST /ledger/candidates/{id}/consent` (grant) ·
    `POST /ledger/consent/{id}/revoke` · `GET /ledger/candidates/{id}/consent`
    (status; 404 for unknown candidate/org, 200 with `allowed:false` when known
    but ungranted).
- **Org plane** (`X-Org-Key` → one org via `authenticate_org`, `org_router` — an
  org never needs the platform secret to touch its own data):
  - `POST /ledger/records` — write-consent gated at the store (403 without an
    active `ledger_write` grant; 404 unknown candidate).
  - `POST /ledger/records/{id}/events` — ownership enforced (404 if the record
    belongs to another org). Event append is gated on record ownership only and
    intentionally inherits the record's submit-time `ledger_write` grant — it is
    NOT re-checked against current consent, and these events are candidate-linked
    so DPDP erasure sweeps them.
  - `GET /ledger/candidates/{id}/records` — **query-time `ledger_read`
    enforcement**: 403 without an active read grant. Every read attempt —
    allowed or denied — is written to `audit_log` (`record.query`, actor `org`)
    in the same transaction, so probing is itself observable. An org holding an
    active `ledger_read` grant sees the candidate's interview records across ALL
    member orgs (the reputation-network semantics), not only its own.

**Org API keys:** `secrets.token_urlsafe(ledger_api_key_bytes)` (default 32),
stored as sha256 hex in `organizations.api_key_hash` (migration
`0004_org_api_keys`, unique index). Suspended orgs never authenticate. Rotation
overwrites the hash, invalidating the old key.

**S3.1 residuals closed this sprint:** deterministic authorizing-grant selection
(org-specific ▸ newest ▸ lowest id) so stamped `consent_id` and audited reads are
reproducible; `consent_status` raises `LookupError` (→ 404) for unknown
candidate/org vs a denied decision (→ 200) when known; `create_organization`
maps the unique-name `IntegrityError` to `ValueError` (→ 409), no TOCTOU; the
migration drift guard now also checks indexes, FK `ondelete`, and nullability.

**Not in S3.2:** coding-round ingest (S3.3); reputation aggregation (S3.4);
candidate-facing consent auth (platform records consent on the principal's
behalf, audited as actor `candidate`).

## S3.3 — coding-round results (this sprint)

A new **coding-round result** record type: structured automated-assessment
results (HackerRank / Codility / LeetCode / CodeSignal / HackerEarth / internal),
a standalone peer of `interview_records`. **Schema + ingest only — no scoring,
no cross-platform normalization, no reputation** (S3.4).

**Table** `coding_round_results` (migration `0005_coding_round_results`, same
DB/metadata root; CASCADE FKs to `candidates`, `organizations`, `consent_grants`):
`platform` (`CodingPlatform` enum; `other` + `platform_name` for the long tail),
`assessment_name?`, `score`, `max_score?`, `percentile?` (0–100), `problem_tags[]`
(JSON), `taken_at`, `raw{}` (JSON — platform extras, forward-compat), plus
`org_id`/`candidate_id`/`consent_id`. Field bounds are data hygiene, not scoring:
`score`/`max_score` are related only in S3.4.

**Consent:** reuses `ledger_write` (submit) / `ledger_read` (query) — one consent
object per candidate, no coding-specific purposes.

**Store** (`app/ledger/store.py`), mirroring interview records:
- `submit_coding_round` — write-consent gated (`ConsentError` → 403), stamps the
  authorizing `consent_id`, audits `coding_round.submit` (actor `org`) in-txn.
- `query_coding_rounds_for_org` — query-time `ledger_read` enforcement; audits
  **every** attempt allowed/denied as `coding_round.query` in the same txn. A
  reader with an active grant sees the candidate's coding rounds across ALL member
  orgs (reputation-network semantics).
- `coding_rounds_for_candidate` — raw ungated read for PI-4/internal use.

**Endpoints** (org plane, `X-Org-Key`):
- `POST /ledger/coding-rounds` — 403 without write consent, 404 unknown candidate.
- `GET /ledger/candidates/{id}/coding-rounds` — 403 without read consent (audited).

**DPDP:** `coding_round_results` + its audit rows CASCADE from `candidates.id`, so
candidate erasure sweeps them; `delete_organization` cascades them via the org's
grants and the `org_id` FK, identical to interview records.

**Not in S3.3:** any interpretation of `score`/`percentile`; reputation
aggregation, recency decay, per-org reliability weight (all S3.4); events on a
coding-round result; correlating a coding round to a specific interview record.
