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
  records) or `ledger_read` (org may query history; enforced in S3.2). Two
  further purposes were added later by the verification spine — see
  "S7.1 — two purposes added by the verification spine" at the end of this
  file.
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

## S3.4 — cross-company reputation (this sprint) — PI-3 COMPLETE

The payoff of the ledger: an **advisory** cross-company reputation band + score
aggregating a candidate's `interview_records` **and** `coding_round_results`.
A **derived read**, not a new record type — no graph node, no `Report` field,
no LLM. Standing guarantee holds: it never changes a verdict/depth score and is
**never a rejection signal**; nothing auto-rejects.

**Model** (`app/ledger/reputation.py`, pure — the `app/fabrication/risk.py`
pattern): each interview record and each *normalizable* coding round is one
fractional-success observation in `[0,1]`.
- Interview outcome → value (code constant, not config): `hired 1.0 · offer 0.9
  · advanced 0.65 · rejected 0.15 · no_show 0.10`; **`withdrawn` excluded**
  (candidate-initiated, not an evaluation of the candidate).
- Coding round → value: `percentile/100`; else `score/max_score`; else
  **excluded** (a bare score has no cross-platform meaning).
- Observation weight `= type_weight · recency · reliability`, where `recency =
  0.5 ** (age_days / rep_recency_halflife_days)` and `reliability` is the
  contributing org's `reliability_weight`.
- **Bayesian shrinkage** toward a neutral prior: `score = (α0 + Σ wᵢvᵢ) /
  (rep_prior_strength + Σ wᵢ)`, `α0 = rep_prior_mean · rep_prior_strength`. No
  evidence ⇒ score = prior (0.5). `confidence = min(cap, mass/(mass+k))`.

**Bands** (`ReputationBand`, corroboration-gated): `INSUFFICIENT_DATA` (below
the confidence floor) · `GUARDED` · `MIXED` · `FAVORABLE` · `STRONG`.
`STRONG` and `GUARDED` (**the only negative-leaning band**) each require
`≥ rep_corroboration_orgs` distinct orgs — **single-source high caps at
FAVORABLE, single-source low at MIXED**, so one company can never brand a
candidate (mirrors S2.4's "ELEVATED needs ≥2 flags"). The assessment carries no
per-org identities.

**Consent:** reuses `ledger_read` — a reputation query is a strictly-less-
granular read of the same records.

**Store** (`app/ledger/store.py`):
- `reputation_for_org` — query-time `ledger_read` enforcement; reads the
  candidate's interview records + coding rounds, builds the per-org reliability
  map, aggregates, and audits **every** attempt allowed/denied as
  `reputation.query` (actor `org`, band + counts in the allowed details) in the
  same txn. A reader with an active grant sees the aggregate across ALL member
  orgs.
- `set_org_reliability` — admin sets an org's `reliability_weight` (≥0; 0 mutes
  the org's evidence); audited `org.set_reliability` (actor `system`).

**Column:** `organizations.reliability_weight` (nullable, neutral default 1.0;
migration `0006_org_reliability_weight`). The mechanism ships now; calibrated
values are a PI-8 concern.

**Endpoints:**
- `GET /ledger/candidates/{id}/reputation` (org plane, `X-Org-Key`) — 403
  without read consent (audited), 404 unknown candidate / erased.
- `POST /ledger/orgs/{id}/reliability` (admin plane, `X-API-Key`) — 404 unknown
  org, 422 negative weight.

**Config:** `rep_*` knobs (`config.yaml` / `Settings`) — prior mean/strength,
recency half-life, confidence floor/k/cap, corroboration-orgs, strong/favorable/
guarded thresholds, interview/coding type weights. Outcome→value map is a code
constant.

**DPDP:** reputation reads only candidate-linked rows that already CASCADE on
erasure; an erased candidate ⇒ `LookupError` → 404. `reliability_weight` is
org-level, not candidate data. No new candidate-linked table ⇒ no new erasure
path.

**Not in S3.4:** learning per-org reliability from outcomes (PI-8); stage-
weighted or role-conditioned reputation (PI-4/PI-5); any use of reputation in
ranking/search or in the depth `Report`.

## S7.1 — two purposes added by the verification spine

`ConsentPurpose` (`app/ledger/schema.py`) is the platform-wide consent
taxonomy, so PI-7's verification spine extends it here rather than inventing a
parallel mechanism. The full current vocabulary:

| Purpose | Added | Authorizes |
|---|---|---|
| `ledger_write` | S3.1 | an org may submit records about the candidate |
| `ledger_read` | S3.1 | an org may query the candidate's ledger history |
| `identity_verify` | S7.1 | the platform may verify the candidate's identity or employment via an **external** source |
| `verification_read` | S7.1 | an org may see the candidate's verification disclosure — identity assurance **and** employment-claim evidence (**redefined 2026-07-31, S7.2** — see below) |

The S3.1 wire values are unchanged — stored grants reference them.

### ⚠ `verification_read` was REDEFINED on 2026-07-31 (S7.2)

**As of 2026-07-31 this purpose covers verification disclosure generally:**
identity assurance (S7.1, `GET /verification/candidates/{id}/assurance`) *and*
employment-claim evidence (S7.2, `GET /verification/candidates/{id}/claims`).
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

**Nothing in `app/ledger/` reads the two new purposes.** They are enforced in
`app/verification/store.py` and `app/verification/service.py`, which import the
ledger for consent checking and audit; the ledger never imports verification
(the same layering rule S5.2 established for comp). `VerificationStore` reuses
`LedgerStore._grants_for` / `_audit` and `consent.check_consent` /
`has_any_active` unchanged, and its audit rows (`verification.start`,
`verification.complete`, `verification.query`, and S7.2's `claim.query`) land in
the shared `audit_log`. Both org reads audit **every** attempt, allowed *and*
denied — the denied audit row is committed before the `ConsentError` is raised.

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
