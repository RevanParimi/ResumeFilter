# LEDGER.md — organisations, consent and audit

The ledger holds member organisations and their API keys, candidates' consent
grants and the shared audit log. DPDP consent is a first-class schema object,
not a patch: grants are purpose-scoped, org-scoped, always expire and can be
revoked; every mutation is audited; candidate erasure removes every
candidate-linked row.

## Tables

Same database and metadata root as candidates (`candidates_db_url`):

| Table | What | DPDP linkage |
|---|---|---|
| `organizations` | member companies (`active`/`suspended`), API-key hash, `reliability_weight` (retained metadata) | none — survives erasure |
| `consent_grants` | purpose-scoped, org-scoped, expiring, revocable consent | CASCADE from `candidates.id` |
| `audit_log` | append-only audit of every mutation and consent-gated read | candidate-linked rows CASCADE; org-only rows survive |

Migration `0031_cut_unused_tables` drops the nine tables left behind by retired
features. Its downgrade recreates their schema empty; it does not restore data.

## Consent model (`src/app/ledger/consent.py`, pure)

- Purpose-scoped: one purpose per grant (see the purpose table below).
- Org-scoped: a specific org, or `org_id=NULL` = any member org.
- Always expires: grants without explicit expiry get
  `ledger_consent_default_ttl_days` (config, default 365). No perpetual consent.
- Revocable: revocation is an UPDATE (`revoked_at`), never a DELETE — the
  audit trail keeps the fact of having consented. Point-in-time checks before
  the revocation instant still see the grant as active.
- Deterministic authorizing-grant selection (org-specific ▸ newest ▸ lowest id),
  so a stamped `consent_id` and an audited read are reproducible.
- Erasure trumps everything: `CandidateStore.delete_candidate` cascades away
  grants and candidate-linked audit rows.

Every mutation in `src/app/ledger/store.py` writes its `audit_log` row in the
same transaction. Consent actions are attributed to the candidate and
org management to `system`.

**Org deletion is a hard cascade, deliberately.** `delete_organization`
cascades through that org's consent grants and the rows stamped with them. This
is org-offboarding semantics, not a DPDP requirement — candidate-linked
`audit_log` rows survive the org's departure.

## Admin routes

Admin plane (`X-API-Key` or an admin session):

- `POST /ledger/orgs` → creates an org and returns a one-time `api_key` (only
  its sha256 hash is stored); duplicate name → 409.
- `GET /ledger/orgs` · `POST /ledger/orgs/{id}/api-key` (rotate) ·
  `DELETE /ledger/orgs/{id}` (hard-cascade offboarding).
- `POST /ledger/candidates/{id}/consent` (grant) ·
  `POST /ledger/consent/{id}/revoke` · `GET /ledger/candidates/{id}/consent`
  (status; 404 for an unknown candidate or org, 200 with `allowed:false` when
  known but ungranted).

**Org API keys:** `secrets.token_urlsafe(ledger_api_key_bytes)` (default 32),
stored as sha256 hex in `organizations.api_key_hash` (unique index). An
`X-Org-Key` resolves to one org via `authenticate_org`; suspended orgs never
authenticate. Rotation overwrites the hash, invalidating the old key.

## Consent purposes

`ConsentPurpose` (`src/app/ledger/schema.py`) is the platform-wide consent
taxonomy. Stored grants reference these wire values, so none is removed:

| Purpose | Added | Authorizes |
|---|---|---|
| `ledger_write` | S3.1 | an org may submit ledger evidence about the candidate (retained purpose; submission routes have been removed) |
| `ledger_read` | S3.1 | consent-gated ledger reads; also the basis for including consent-tagged features in materialisation and serving ([FEATURES.md](FEATURES.md)) |
| `identity_verify` | S7.1 | the platform may verify the candidate's identity or employment via an **external** source |
| `verification_read` | S7.1 | an org may see the candidate's verification disclosure — identity assurance **and** employment-claim evidence (**redefined 2026-07-31, S7.2** — see below) |
| `interview_read` | S7.3 | an org may see the candidate's AI-interview assessments (bands, dimensions, proxy band — **never a transcript**) |

### ⚠ `verification_read` was REDEFINED on 2026-07-31 (S7.2)

**As of 2026-07-31 this purpose covers verification disclosure generally:**
identity assurance (S7.1, `GET /verification/candidates/{id}/assurance`) *and*
employment-claim evidence (S7.2; that route and the document intake behind it
have since been removed).
As originally written in S7.1 it named identity assurance only.

**Why the widening was permissible, and why the window is now shut.** S7.2
landed four days after S7.1, while the purpose held **zero real grants** — no
candidate had consented to anything under it, so no one's understanding of what
they had signed was changed retroactively. That is exactly the test S7.1 itself
applied when it *refused* to widen `ledger_read`: candidates had already signed
that one. **Once real grants exist, this argument is unavailable.** Any further
widening of `verification_read` — a third verification subject, an outcome
detail beyond the advisory roll-up — requires a **new** `ConsentPurpose`, not
another redefinition.

`identity_verify` was widened in the same breath and on the same basis: it now
gates any third-party verification pull, whether about identity
(`government_id`) or employment (`epfo_employment`). Both remain declared and
inert (`implemented = False`).

**S7.3 honoured that closure.** AI-interview disclosure is a *third* thing an org
might read about a candidate, and the tempting move was one more redefinition.
Instead it got its own purpose, `interview_read` — the window shut on 2026-07-31
and it stays shut. A test pins the distinction: an org holding
`verification_read` and nothing else is still refused the interview endpoint
(`test_a_verification_read_grant_does_not_unlock_interviews`).

**Nothing in `src/app/ledger/` reads the three purposes added by PI-7.** They are
enforced in `src/app/verification/` and (for `interview_read`)
`src/app/interview/store.py`, which import the ledger for consent checking and
audit; the ledger never imports either . `VerificationStore` reuses
`LedgerStore._grants_for` / `_audit` and `consent.check_consent` /
`has_any_active` unchanged, and its audit rows (`verification.start`,
`verification.complete`, `verification.query`) land in the shared `audit_log`. Both org reads audit **every** attempt, allowed *and*
denied — the denied audit row is committed before the `ConsentError` is raised.
S7.3's `InterviewStore.assessments_for_org` follows the identical shape, auditing
`interview.query` allowed *and* denied; its `interview.start` /
`interview.complete` rows land in the same log.

**`verification_read` is deliberately not a reuse of `ledger_read`.** Widening
`ledger_read` to also disclose identity assurance would retroactively change
the scope of grants candidates have *already* signed. (The S7.2 redefinition
above is the same test applied to `verification_read` itself, and it passed only
because that purpose had no grants yet.)

**`identity_verify` gates only third-party verification.** First-party methods
a candidate runs on themselves (self-attestation, an OTP to their own contact)
need no grant at all — the S6.4 principle in `PORTAL.md`: acting on your own
data is a data-principal right, not a disclosure. Today no shipped adapter is
third-party (`government_id` is declared but raises `NotImplementedError`), so
`identity_verify` gates a seam rather than live traffic; the gate is exercised
in tests via a fake third-party adapter. Full detail: `VERIFICATION.md`.
