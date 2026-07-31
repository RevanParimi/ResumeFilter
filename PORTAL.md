# PORTAL.md — candidate auth + DPDP portal (PI-6, S6.4)

The portal gives a candidate a door they can walk through themselves. Every
DPDP data-principal right the platform already had the data for — access,
transparency, consent control, erasure — was previously reachable only through
the **admin** plane (an operator acting on the candidate's behalf). S6.4 adds a
**candidate auth plane** (mirroring the org plane from `LEDGER.md`) and a thin
`app/portal/` composition layer exposing those rights first-party. No new
evaluation, no LLM, no scoring: this is data access and consent self-service,
not a new signal. It changes no verdict, depth, or score.

## The candidate plane

A candidate authenticates with a minted key, exactly like an org authenticates
with `X-Org-Key`:

- **`X-Candidate-Key`** header → `require_candidate` (`app/api/routes.py`)
  resolves it to a `candidate_id` via `CandidateStore.authenticate_candidate`,
  or raises **401**. Unlike the admin `X-API-Key` (optional/shared-secret) and
  like the org plane, this is *always* enforced — the portal is the data
  principal's private surface, not an operator convenience.
- **`candidate_router`** (`app/api/routes.py`) — a dependency-free `APIRouter`,
  a peer of `router` (admin) and `org_router`, included in the app alongside
  them. No route on it accepts the admin key, and no route on it names another
  candidate — every handler takes only `candidate_id: str = Depends(require_candidate)`.

### Minting a key

There is no self-serve registration yet. Admin/system mints a key on the
candidate's behalf:

- **`POST /candidates/{candidate_id}/auth-key`** (admin plane, `X-API-Key`) →
  **200** `{candidate_id, access_key}` · **404** unknown candidate.
- `CandidateStore.issue_access_key(candidate_id)` (`app/candidates/store.py`)
  — mints a fresh `secrets.token_urlsafe(candidate_access_key_bytes)` token,
  stores only its **sha256 hash** (`_hash_access_key`, the same approach
  `LedgerStore` uses for org keys) on a `CandidateCredentialRow`, and returns
  the plaintext **once**. Calling it again **rotates**: the existing row's
  hash is overwritten and `rotated_at` is stamped — the old key stops
  authenticating immediately. Unknown candidate → `LookupError` (→ 404 at the
  route).
- `CandidateStore.authenticate_candidate(access_key)` — hashes the presented
  key and looks up the matching credential; empty/whitespace keys never
  match; unknown/rotated-away keys return `None` → 401.

**Why a minted key and not real registration:** a password/OTP/email flow has
no clean offline-determinism story and fights the no-external-dependency +
fully-offline-test constraints this repo holds everywhere else. A minted,
sha256-hashed, rotatable opaque token is deterministic, testable with no API
key, and adds zero external dependencies. Real self-serve registration
(password/OTP/session) is a **PI-8** productionization concern.

### `candidate_credentials` (migration `0012`)

A peer table (not a column on the PI-1 `candidates` row) — auth material
stays separable from the core identity/PII record and cascades cleanly on
erasure:

| column | type | notes |
|---|---|---|
| `id` | String(36) PK | UUID |
| `candidate_id` | FK `candidates.id` ON DELETE CASCADE, **unique**, indexed | one credential per candidate |
| `access_key_hash` | String(64), indexed | sha256 of the plaintext key |
| `created_at` | DateTime | |
| `rotated_at` | DateTime, nullable | set on re-mint |

The credential is not PII itself (a hash of an opaque token), but the row is
still candidate-linked with a CASCADE FK, so erasure removes it and the key
dies with the candidate. Drift/index/FK-ondelete/nullability guards were
extended to this table per repo convention.

## The DPDP rights map

Every right below is gated by **candidate authentication == identity of the
data subject**, not by a `ConsentPurpose`. See "No new `ConsentPurpose`" below
for why.

| Right | Endpoint | Notes |
|---|---|---|
| **Access** | `GET /portal/me` → `MyData` | profile, resumes, profile-source signals, interview records, coding rounds, reports (as refs), consents, identity assurance (S7.1), retention posture |
| **Transparency** | `GET /portal/access-log` → `list[AccessLogEntry]` | who accessed the candidate's data, newest-first, including platform-internal actions |
| **Consent control** | `GET /portal/consents` / `POST /portal/consents` / `POST /portal/consents/{id}/revoke` | first-party grant + revoke over the same `consent_grants` rows the admin plane and orgs already use |
| **Erasure** | `DELETE /portal/me` | hard delete, self-service, reuses the existing erasure path |
| **Identity verification** (S7.1) | `POST /portal/verifications` / `POST /portal/verifications/{id}/confirm` / `GET /portal/verifications` | candidate-initiated self-verification; see "Identity verification" below |

### Why no new `ConsentPurpose`

The existing `ConsentPurpose` members (`ledger_write`, `ledger_read`) govern
*org* access to a candidate's data — a third party asking permission. A
candidate reading or erasing **their own** data is not a consent-gated
disclosure to a third party; it is the DPDP data-principal right itself, and
its lawful basis is simply *"you are the subject, proven by your key."* Adding
a `self_access` purpose would be a category error — consent is something a
principal grants to *others*, not to themselves — and would dirty the
taxonomy for nothing. So every portal read/mutation is gated purely by
`require_candidate`; no consent row is checked or created for self-access.

Two things this does **not** change:
- **Self-access needs no org consent either.** `MyData.interview_records` /
  `coding_rounds` come from `LedgerStore.records_for_candidate` /
  `coding_rounds_for_candidate` — the same raw, ungated reads PI-4/internal
  code already used — not the `ledger_read`-gated org query path. A candidate
  does not need an org's consent to see what that org wrote about them.
- **First-party consent is additive, not a replacement.** `POST
  /portal/consents` writes to the *same* `consent_grants` rows the admin
  plane's `POST /ledger/candidates/{id}/consent` writes to
  (`actor_type="candidate"` either way). The admin path stays — it seeds
  tests and supports org-initiated consent-request flows; removing it would
  break existing flows for no benefit.

## Cross-candidate isolation

Isolation is **structural, not checked**:

- Every portal endpoint operates on the `candidate_id` **resolved from the
  key** by `require_candidate` — never on a path or body parameter. There is
  no portal URL that names another candidate, so candidate A has no reachable
  surface to read or mutate B's data by construction. (Tested explicitly: A's
  key against a B-shaped request only ever touches A.)
- The one place a foreign id *is* named on the wire —
  `POST /portal/consents/{consent_id}/revoke` — is **ownership-enforced**:
  `PortalService.revoke` looks up the grant and requires
  `grant.candidate_id == candidate_id`, else raises `LookupError`. The route
  maps that to **404**, and it is the *same* 404 whether the `consent_id` is
  unknown or belongs to someone else — a candidate can never learn another
  candidate's grant ids by probing. (Unlike the *admin*-plane revoke, which
  accepts any `consent_id` — an operator is trusted with the whole ledger.)

## Reports — existence only (v0)

`MyData.reports` is `list[ReportRef]` (`report_id`, `domain`, `created_at`) —
existence and timestamp only. The depth `Report`'s advisory internals
(`fabrication_risk`, verdicts, per-claim scoring) are platform work-product,
not disclosed to the evaluated person in v0. Whether/how to surface those
internals (and any correction right over them) is a deferred policy call
(§9 non-goals below) — the candidate's *submitted* data and *org-submitted
records about them* are the v0 access surface, not the platform's own
assessment of that data.

## Identity verification (added by S7.1)

PI-7's verification spine is candidate-initiated, so its start/confirm surface
lives on this plane. Three routes were added to `candidate_router`; the
subsystem itself is documented in `VERIFICATION.md`.

- `POST /portal/verifications` — body `{method, destination?}`. Starts a
  verification. `self_attested` completes immediately; the OTP methods create a
  challenge.
- `POST /portal/verifications/{verification_id}/confirm` — body `{code}`.
- `GET /portal/verifications` — the candidate's own verifications plus their
  current `IdentityAssurance`.

Three properties matter for this document:

- **They follow the plane's rules exactly.** Each handler takes only
  `candidate_id: str = Depends(require_candidate)`; no route names another
  candidate. `confirm` is the one place a foreign id *could* be presented on
  the wire, and it is ownership-enforced the same way the consent revoke is:
  `VerificationService.confirm` requires the verification to belong to the
  calling candidate, else raises `LookupError` → **404**, identical whether the
  id is unknown or someone else's.
- **No `ConsentPurpose` gates them.** Self-verification is first-party, so the
  "Why no new `ConsentPurpose`" reasoning below applies unchanged. S7.1 *did*
  add two purposes to the taxonomy (`identity_verify`, `verification_read`) —
  but neither gates any portal route: `verification_read` gates the **org**
  plane's read of assurance, and `identity_verify` gates verification via an
  external source (no shipped adapter is third-party today). See `LEDGER.md`.
- **`MyData.identity`** carries the same advisory `IdentityAssurance`
  (`level`, contributing `methods`, `verified_at`, `expired_methods`) that
  `GET /portal/verifications` returns. It is `Optional` — `PortalService` takes
  the verification service as an optional collaborator, so the portal stays
  constructible without the spine, in which case `identity` is simply omitted.

Assurance is **advisory** and affects no verdict, depth, score, ranking, or
match — the same posture as everything else in this document.

## Retention posture

`GET /portal/me` surfaces `MyData.retention: RetentionPolicy`
(`app/portal/schema.py`, `app/portal/retention.py` — pure, no I/O):

- **Every** data class always appears as a `RetentionWindow`, with its
  `ttl_days` (the policy) shown regardless of whether the candidate has data
  in that class.
- `oldest_item_at` / `retained_until` (`= oldest + ttl_days`) are populated
  only for the classes `my_data` already materializes in full this sprint —
  `resumes`, `profile_sources`, `interview_records`, `coding_rounds` (the
  oldest timestamp is free from those reads). `observed_offers`, `audit_log`
  and `verifications` are **policy-only** rows (`retained_until=None`) — the
  portal does not materialize per-candidate reads for those classes, and this
  keeps the retention view honest rather than fabricating a timestamp it
  didn't compute. (`verifications` joined the policy in S7.1; `my_data` reads
  assurance, not the underlying rows' timestamps, so it has no oldest-item
  timestamp to report.)
- **`RetentionPolicy.sweep_active = False`, always.** The portal *shows* the
  policy; it does not enforce it. There is no scheduler in this platform yet,
  and cron/observability is explicitly **PI-8**'s remit — a deterministic
  sweep is cheap in isolation but would strand an un-triggered function if
  built now. The mechanical purge job lands with PI-8's scheduler work.

Config knobs (`config.yaml` / `app/core/config.py`), all illustrative
retention windows — **not enforced deletion** (no sweep this sprint; they
parametrize the surfaced `retained_until` only):

| knob | default | data class |
|---|---|---|
| `candidate_access_key_bytes` | 32 (`ge=16`) | entropy of a minted candidate key — mirrors `ledger_api_key_bytes` |
| `ret_resume_days` | 1095 (3y) | resumes |
| `ret_profile_source_days` | 1095 (3y) | profile-source signals |
| `ret_interview_record_days` | 1825 (5y) | interview records |
| `ret_coding_round_days` | 1825 (5y) | coding rounds |
| `ret_observed_offer_days` | 1825 (5y) | observed offers (policy-only) |
| `ret_audit_log_days` | 2555 (7y) | audit trail — deliberately longest; accountability outlives content |
| `ret_verification_days` | 1095 (3y) | identity verifications (policy-only; added S7.1) |

## DPDP erasure completeness

`DELETE /portal/me` reuses the existing erasure path exactly as the admin
`DELETE /candidates/{id}` does: it deletes the candidate's reports
(`report_store.delete_for_candidate`) then hard-deletes the candidate
(`CandidateStore.delete_candidate`), which cascades resumes, extractions, and
every candidate-linked ledger row via the migration's CASCADE FKs — including
the new `candidate_credentials` row, and (since S7.1) the candidate's
`verifications` rows and their `verification_challenges`. After erasure the
same key **401s** on
any subsequent call: the credential is gone, so `authenticate_candidate` finds
nothing to match. Response: **200** `{candidate_id, deleted: true,
reports_deleted: N}`.

## Endpoint contract

### Admin plane (`X-API-Key`, existing `router`)

- `POST /candidates/{candidate_id}/auth-key` → **200** `{candidate_id,
  access_key}` (once) · **404** unknown candidate · **401** without the admin
  key.

### Candidate plane (`X-Candidate-Key`, new `candidate_router`)

All resolve the acting candidate from the key; **401** on a
missing/invalid/empty key, always.

- `GET /portal/me` → **200** `MyData`.
- `GET /portal/access-log` → **200** `list[AccessLogEntry]` (newest-first;
  includes platform-internal actions, labelled by `actor_type`/`action` —
  e.g. `feature.materialize` — not only org disclosures).
- `GET /portal/consents` → **200** `list[ConsentView]` (grant + derived
  `active`/`revoked`/`expired` state).
- `POST /portal/consents` — body `{purpose, org_id?, expires_at?}` → **200**
  `ConsentGrant` · **404** unknown `org_id` · **422** bad purpose (enum
  validation at the boundary).
- `POST /portal/consents/{consent_id}/revoke` → **200** `{consent_id,
  revoked: bool}` · **404** grant unknown **or not owned by the caller**
  (identical either way — no probing).
- `DELETE /portal/me` → **200** `{candidate_id, deleted: true,
  reports_deleted: N}`. Subsequent calls with the same key → **401**.

Added by S7.1 (contracts in `VERIFICATION.md`):

- `POST /portal/verifications` — body `{method, destination?}` → **200**
  `{verification, debug_code?}` · **400** destination missing / malformed /
  not matching the contact hash on file · **403** a method the candidate may
  not initiate (`manual_review` — operator-recorded, admin plane only) or a
  third-party method without an `identity_verify` grant · **422** unknown
  method, or a declared-but-unimplemented one (`government_id`) · **429**
  resend inside the cooldown (scoped per candidate + channel, so restarting a
  verification does not reset it). (`debug_code` appears only when
  `env == "local"` **and**
  `verif_otp_debug_echo` is true — it exists so the sprint smoke can drive the
  two-step flow over plain HTTP.)
- `POST /portal/verifications/{verification_id}/confirm` — body `{code}` →
  **200** `Verification` · **400** wrong or expired code · **404** unknown
  **or not owned by the caller** (identical either way — no probing).
- `GET /portal/verifications` → **200** `{verifications, assurance}`.

## Architecture (for reference)

Mirrors `app/dashboard/` (`DASHBOARD.md`): a pure `app/portal/` package that
owns no tables/state, composing `CandidateStore` + `LedgerStore` +
`ProfileSourceService` + `ReportStore`:

- **`schema.py`** — Pydantic contracts: `MyData`, `AccessLogEntry`,
  `ConsentView`/`ConsentState`, `ReportRef`, `RetentionWindow`/
  `RetentionPolicy`. No scoring; all read-shapes.
- **`retention.py`** — pure `retained_until` + `build_retention_policy`
  (`RETENTION_KNOBS` mapping each data class to its `ret_*` setting). No I/O.
- **`service.py`** — `PortalService`: `my_data`, `access_log`, `consents`,
  `grant`, `revoke`; `build_portal_service` (cycle-safe builder, the
  S4.3/S5.1/S5.2/S5.3/S6.3 pattern).
- **`Services.portal`** wired in `app/services/…` (function-local build +
  `TYPE_CHECKING` import), sharing the already-built `candidates`, `ledger`,
  `report_store`, and `profile_sources` instances — no new DB connections.
  Since S7.1 it also receives the `verification` service (built **before** the
  portal in `build_default_services` for that reason) as an **optional**
  collaborator, used only to populate `MyData.identity`.

Small store additions this sprint (`app/ledger/store.py`, nothing existing
changed): `consents_for_candidate(candidate_id)` — all grants for a candidate
(active + revoked + expired), ordered by `granted_at`, a raw read like
`records_for_candidate` with no consent gate (it is the candidate's own
consent ledger); `get_grant(consent_id)` — needed for the ownership check in
`PortalService.revoke`.

## What's deferred (non-goals, v0)

- **Retention sweep (mechanical purge).** Posture is surfaced this sprint;
  the deterministic, `now`-injected purge job lands in **PI-8** with the
  scheduler / observability work.
- **Real candidate registration** (password/OTP/email/session). The minted
  access key is the offline-deterministic stand-in; a productionized
  self-serve registration + session flow is a **PI-8** concern.
- **Exposing depth `Report` internals to the candidate.** v0 lists reports
  by existence only; whether/how to surface advisory internals (and
  correction rights over them) to the evaluated person is a deferred policy
  call.
- **Correction / rectification right.** DPDP includes correction; v0 covers
  access / transparency / consent-control / erasure only. Candidate-initiated
  profile correction is a natural follow-up.
- **Grievance / DPO contact endpoint.** A statutory DPDP touchpoint,
  deferred to the org-self-serve / productionization work (PI-8).
- **Multi-credential / device sessions.** One key per candidate today;
  multiple named credentials or revocable sessions are YAGNI until needed.
