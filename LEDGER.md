# Organisations, consent and audit

Reviewed on 2026-11-17. `src/app/ledger/` holds organisations, API keys,
purpose-scoped consent grants and the shared audit log.

## Storage and erasure

| Table | Purpose | Erasure |
|---|---|---|
| `organizations` | Member companies, status, API-key hash and retained `reliability_weight` metadata | Org offboarding; survives candidate erasure |
| `consent_grants` | Candidate/org/purpose, grant and expiry times, optional revocation | Cascades with candidate or org |
| `audit_log` | Mutation and consent-gated read history | Candidate-linked rows cascade with candidate; org-only rows survive |

These tables share `candidates_db_url` and the common metadata root. Migration
`0031_cut_unused_tables` drops nine tables left by retired features; downgrade
recreates their schema empty. It cannot recover removed records.

`audit_log` is append-only by store convention. Consent revocation updates
`revoked_at`, retaining the fact of the grant. Candidate erasure overrides that
retention and removes every candidate-linked row. Hard org offboarding removes
the org and its grants; candidate-linked audit rows survive org departure.

## Organisation administration

The operator plane accepts `X-API-Key` or an admin session; cookie writes require
CSRF protection. Routes are:

- `POST /ledger/orgs`: create, returning a one-time API key; duplicate name is 409.
- `GET /ledger/orgs`: list organisations.
- `POST /ledger/orgs/{id}/api-key`: rotate the key.
- `DELETE /ledger/orgs/{id}`: offboard the organisation.

Keys use `secrets.token_urlsafe(ledger_api_key_bytes)` (default 32) and are stored
only as SHA-256 hashes. Rotation invalidates the previous key. `X-Org-Key`
resolves one active org; a suspended org cannot authenticate. The
`reliability_weight` column and response field remain, with no update control.

## Consent

Grants cover one purpose and either a specific organisation or any member org
(`org_id=NULL`). They always expire; omitted expiry uses
`ledger_consent_default_ttl_days` (365). Revocation stops current use while
historical checks before revocation can still see an active grant. Grant
selection is deterministic: org-specific, then newest, then lowest ID.

Operator consent routes are `POST /ledger/candidates/{id}/consent`,
`POST /ledger/consent/{id}/revoke` and
`GET /ledger/candidates/{id}/consent`. Unknown candidate/org is 404; a known
subject without a grant returns `allowed:false`. Candidates can inspect and
revoke their own grants through the [portal](PORTAL.md).

Every existing wire value remains valid because stored grants may use it:

| Purpose | Current role |
|---|---|
| `ledger_write` | Historical evidence-submission purpose; submission routes removed |
| `ledger_read` | Consent-tagged feature materialization/serving; dormant in the shipped catalog |
| `identity_verify` | Third-party verification adapter gate; shipped external adapters are unimplemented |
| `verification_read` | Employer assurance disclosure; historical scope also included the removed employment-evidence route |
| `interview_read` | Employer interview assessment summary; never a transcript |

First-party self-attestation and contact control need no consent grant. They
operate on the candidate's own data. Verification and interview disclosures
retain separate purposes: `verification_read` cannot unlock interviews.
Purpose scopes must not be widened for existing grants; use a new purpose for
a new disclosure subject.

Ledger mutations audit in the same transaction. Verification and interview
services reuse ledger consent checks and the shared audit log, recording both
allowed and denied disclosure attempts. A denied read commits its audit before
raising `ConsentError`. See [verification](VERIFICATION.md),
[interviews](INTERVIEWS.md) and [features](FEATURES.md).
