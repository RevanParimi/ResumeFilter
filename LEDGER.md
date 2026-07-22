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
    belongs to another org).
  - `GET /ledger/candidates/{id}/records` — **query-time `ledger_read`
    enforcement**: 403 without an active read grant. Every read attempt —
    allowed or denied — is written to `audit_log` (`record.query`, actor `org`)
    in the same transaction, so probing is itself observable.

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
