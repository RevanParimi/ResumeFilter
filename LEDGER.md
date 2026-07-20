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
