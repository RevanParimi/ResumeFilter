# S6.4 — Candidate Auth + DPDP Portal — Design

**Date:** 2026-07-30
**PI / Sprint:** PI-6 (Candidate Side & Intake) · S6.4 — closes PI-6.
**Status:** Approved design — ready for implementation plan.
**Read first:** `docs/ROADMAP.md`, then
`docs/superpowers/specs/2026-07-26-veritas-vision-gap-analysis.md` §5.D / §6
(the "no candidate-facing auth or portal" gap → PI-6.3 landing zone), then
`LEDGER.md` (consent + audit substrate this sprint surfaces) and
`DASHBOARD.md` (the S5.3 composition-layer precedent this mirrors), then this
document.

---

## 1. Why this sprint

The vision-gap analysis (§5.D) names the last open candidate-side weakness:

> **No candidate-facing auth or portal ("who saw my data, revoke here").** DPDP
> grants rights the product must surface; trust is the brand. Landing zone:
> **PI-6.3 — candidate auth + transparency endpoints over the existing audit
> log — the data is already there.**

It is right that the *data* is already there. Everything a DPDP data principal is
entitled to see or control already exists in the store; what is missing is a
**door the candidate can walk through themselves**:

- **Access** — the candidate's profile, resumes, profile sources, and the
  interview/coding records orgs have submitted *about them* all live in the
  candidate + ledger stores.
- **Transparency ("who accessed my data")** — `LedgerStore.audit_for_candidate`
  already returns every disclosure event: each org read (`record.query` /
  `coding_round.query` / `reputation.query`, **allowed and denied**), each
  submission, each consent change.
- **Consent control** — `grant_consent` / `revoke_consent` already attribute
  `actor_type="candidate"`; today they are only reachable through the **admin**
  plane (`X-API-Key`), i.e. an operator acting *on behalf of* the candidate.
- **Erasure** — `DELETE /candidates/{id}` already hard-deletes the candidate and
  cascades every derived + ledger row.

S6.4 gives the candidate first-party keys to all of it: a **candidate auth
plane** (mirroring the org plane) and a thin **`app/portal/`** composition layer
exposing the DPDP rights. No new evaluation, no LLM, no scoring — this is data
access and consent self-service, not a new signal.

## 2. Scope decisions (taken with user, 2026-07-30)

Three load-bearing calls, all taken on recommendation:

1. **Retention TTLs: surface posture now, defer the sweep to PI-8.** The portal
   *shows* the retention policy (per-data-class window) and a computed
   `retained_until` — that transparency is the DPDP-facing value and the roadmap
   line. The **mechanical purge job is not built this sprint**: the platform has
   no scheduler yet, and cron/observability is explicitly PI-8's remit. A
   deterministic sweep is cheap in isolation but belongs where scheduling lives;
   building it now would strand an un-triggered function. (§8 follow-ups.)
2. **First-party consent is additive, not a hard replace.** The candidate plane
   gains grant + revoke against the *same* `consent_grants` rows
   (`actor_type="candidate"`). The existing admin-plane `POST
   /ledger/candidates/{id}/consent` **stays** — it seeds tests and supports
   org-initiated consent-request flows. "Replacing the admin plane" is satisfied
   in spirit (the candidate now controls their own consent); removing the admin
   path would break existing smoke flows for no benefit.
3. **Candidate auth = a minted access key (mirror the org key).** Admin/system
   mints an opaque, sha256-hashed, rotatable key returned **once**; the candidate
   authenticates with `X-Candidate-Key`. This is deterministic, offline-testable,
   and adds zero external dependencies. A real password/OTP/email registration
   flow has no clean offline-determinism story and fights the
   no-external-dep + fully-offline-test constraints; it is a productionization
   concern (PI-8), noted in §8.

Two smaller calls (confirmed with user):

- **(a) `/portal/me` lists reports by existence + timestamp only** — the depth
  `Report` internals (fabrication_risk, verdicts, per-claim advisory scoring) are
  platform work-product, not disclosed to the subject in v0. The candidate is
  told a report exists and when; exposing the advisory internals to the evaluated
  person is a policy question deferred (§8). Their *submitted* data and
  *org-submitted records about them* are the access surface.
- **(b) The access-log includes platform-internal actions**, labelled (e.g.
  `feature.materialize`), not just org disclosures — fuller transparency, and the
  candidate is entitled to see the platform's own use of their data too.

## 3. Non-negotiables inherited (do not relitigate)

- **First-party data only.** The portal exposes the candidate's *own* data and
  their *own* consent, plus records orgs submitted about them — all first-party
  to the data principal. No third-party data enters here.
- **Advisory / no auto-anything.** N/A to evaluation — the portal changes no
  verdict, depth, or score. It is read + consent-control + erasure only.
- **DPDP.** The one new table (`candidate_credentials`) is candidate-linked with a
  CASCADE FK and is swept by the existing erasure path. **No new `ConsentPurpose`**
  (§4). Erasure remains a hard delete.
- **Deterministic, no LLM.** Auth, portal composition, and retention math are pure
  Python + DB reads. No API key ever required to run.
- **TDD offline; smoke per sprint; Postgres-shaped SQLite; Alembic migration with
  drift/index/FK/nullability guards extended.**
- **Config in `config.yaml` (`ret_*`, `candidate_access_key_bytes`); no new
  secrets.**

## 4. DPDP posture — the important one

**No new `ConsentPurpose`.** The existing `ConsentPurpose` members
(`ledger_write`, `ledger_read`) govern *org* access to a candidate's data. A data
principal accessing or erasing **their own** data is not a consent-gated org
disclosure — it is the DPDP data-principal right itself, and its lawful basis is
*"you are the subject, proven by your key."* So every portal read/mutation is
gated by **candidate authentication == identity of the data subject**, full stop.
Adding a `self_access` purpose would be a category error (consent is something a
principal grants to *others*, not to themselves) and would leave the taxonomy —
"reviewed schema decisions, not tunables" — dirtied for nothing.

**Consequences / guardrails:**

- **Cross-candidate isolation is structural, not checked.** Every portal endpoint
  operates on the `candidate_id` resolved from the key by `require_candidate` —
  **never on a path/body parameter.** There is no portal URL that names another
  candidate, so candidate A has no reachable surface to read or mutate B's data.
  (Tested explicitly: A's key against a B-shaped request still only ever touches
  A.) The one place an id is named — `POST /portal/consents/{consent_id}/revoke` —
  is **ownership-enforced**: the grant must belong to the authenticated candidate
  or it is a 404 (unlike the admin revoke, which accepts any `consent_id`).
- **The credential is not PII but still cascades.** `access_key_hash` is a hash of
  an opaque token, not personal data; nonetheless the row is candidate-linked with
  a CASCADE FK, so erasure removes it and the key dies with the candidate.
- **Self-access needs no org consent.** The candidate reading their own
  org-submitted interview/coding records uses the raw `records_for_candidate` /
  `coding_rounds_for_candidate` store reads (which exist precisely for
  non-org-gated internal reads), *not* the `ledger_read`-gated org query path. A
  candidate does not need an org's consent to see what that org wrote about them.
- **Erasure is unchanged and complete.** `DELETE /portal/me` reuses the existing
  erasure path (candidate + resumes + extractions + reports + cascaded ledger rows
  + the new credential row). After it, the key no longer authenticates (401).

## 5. Architecture

### 5.1 Candidate authentication (mirror the org plane)

**New table `candidate_credentials`** (migration `0012`, §5.5): a peer table, not a
column on the PI-1 `candidates` row — auth material stays separable from the core
identity/PII record and cascades cleanly on erasure. One credential per candidate
(unique on `candidate_id`); minting again rotates it.

**Model — `app/candidates/models.py`** (`CandidateCredentialRow`):

| column | type | notes |
|---|---|---|
| `id` | String(36) PK | UUID, repo convention |
| `candidate_id` | FK `candidates.id` ON DELETE CASCADE, **unique**, indexed | one credential per candidate |
| `access_key_hash` | String(64), not null, indexed | sha256 of the plaintext key |
| `created_at` | DateTime, not null | |
| `rotated_at` | DateTime, nullable | set on re-mint |

**Store — `app/candidates/store.py`** (auth lives with the store that owns the
candidates table + the DPDP deletes, exactly as org auth lives in the ledger store
that owns orgs). Reuse the same `_hash_api_key` sha256 approach the ledger uses:

- `issue_access_key(candidate_id) -> str` — mint a fresh `secrets.token_urlsafe`
  key, upsert its hash onto the candidate's credential row (insert if none, else
  overwrite + set `rotated_at`), return the plaintext **once**. `LookupError` if
  the candidate is unknown.
- `authenticate_candidate(access_key) -> Optional[str]` — `candidate_id` for the
  credential whose hash matches an active (existing) candidate, else `None`.
  Empty/whitespace keys never match.

**Routes — `app/api/routes.py`:**

- `require_candidate(request, x_candidate_key) -> str` dependency —
  `services.candidates.authenticate_candidate(key)` → `candidate_id` or **401**.
- A new **`candidate_router` = APIRouter()** (no admin-key dependency, exactly
  like `org_router`), included in the app alongside `router` / `org_router`.
- Admin mint endpoint on the existing `router` (admin plane):
  `POST /candidates/{candidate_id}/auth-key` → `{candidate_id, access_key}`
  (returned once), **404** unknown candidate. Mirrors `rotate_org_key`.

### 5.2 New package `app/portal/` (the DPDP portal)

Mirrors `app/dashboard/`: pure `schema.py` contracts + `service.py` `PortalService`
that **owns no tables/state** — it composes `CandidateStore` + `LedgerStore` +
`ReportStore`. Every endpoint below is on `candidate_router`, gated by
`require_candidate`, and operates on the resolved `candidate_id`.

**`schema.py`** — Pydantic contracts (no scoring; all read-shapes):

- `RetentionWindow(BaseModel)`: `data_class: str`, `ttl_days: int`,
  `oldest_item_at: Optional[datetime]`, `retained_until: Optional[datetime]`
  (oldest + ttl; `None` when the class has no items).
- `RetentionPolicy(BaseModel)`: `windows: list[RetentionWindow]`, `sweep_active:
  bool = False` (honest: posture is surfaced, purge is deferred — the portal is
  self-describing about this). **Every** data class appears as a window (its
  `ttl_days` is always shown = the policy). `oldest_item_at` / `retained_until` are
  populated for the classes `my_data` already materializes in full — resumes,
  profile_sources, interview_records, coding_rounds (oldest is free from those
  reads); observed_offers and audit_log are **policy-only** rows
  (`retained_until=None`) because the portal does not materialize them in v0. This
  keeps the retention view honest without adding candidate-scoped reads the portal
  otherwise wouldn't do.
- `ReportRef(BaseModel)`: `report_id: str`, `domain: str`, `created_at: datetime`
  — existence + timestamp only, no advisory internals (decision (a)).
- `MyData(BaseModel)` — the access view: `candidate_id`, `profile:
  Optional[CandidateProfile]`, `resumes: list[ResumeSummary]`, `sources:
  list[ProfileSourceSignal]`, `interview_records: list[InterviewRecord]`,
  `coding_rounds: list[CodingRoundResult]`, `reports: list[ReportRef]`,
  `consents: list[ConsentGrant]`, `retention: RetentionPolicy`.
- `AccessLogEntry(BaseModel)` — a candidate-friendly projection of `AuditEntry`:
  `at: datetime`, `actor_type: str` (`org`/`candidate`/`system`), `actor_id:
  Optional[str]`, `actor_name: Optional[str]` (org name resolved from `actor_id`,
  else `None`), `action: str`, `allowed: Optional[bool]` (from
  `details["allowed"]` when present), `entity_type: str`.
- `ConsentView(BaseModel)` — a grant plus a derived `state` label so the candidate
  sees status without re-deriving from three timestamps: `revoked` if `revoked_at`
  is set, else `expired` if `expires_at <= now`, else `active`. (Derived directly
  from the grant's own timestamps — no org/purpose scope, unlike `is_grant_active`
  which answers a *disclosure* question.)

**`retention.py`** (pure) — `retained_until(oldest_at, ttl_days) -> datetime` and
`build_retention_policy(counts_and_oldest, settings) -> RetentionPolicy` mapping
each data class to its `ret_*_days` knob. No I/O; the service passes in the
per-class oldest timestamps it already reads.

**`service.py`** — `PortalService`:

- `my_data(candidate_id) -> MyData` — compose: `latest_profile`, `list_resumes`,
  `profile_sources.list_sources`, `records_for_candidate`,
  `coding_rounds_for_candidate`, `report_store.for_candidate` → `ReportRef`s,
  `consents_for_candidate` (new tiny raw read, §5.3), and `build_retention_policy`
  from the oldest timestamps across those reads. `LookupError` → 404 for an
  unknown candidate (shouldn't happen post-auth, but symmetric with the store).
- `access_log(candidate_id) -> list[AccessLogEntry]` — `audit_for_candidate`,
  resolve org names via `LedgerStore.get_organization(actor_id)` (cache within the
  call), project to `AccessLogEntry`, newest-first.
- `consents(candidate_id) -> list[ConsentView]` — `consents_for_candidate` + state
  labelling.
- `grant(candidate_id, purpose, org_id, expires_at) -> ConsentGrant` — delegates
  to `LedgerStore.grant_consent` (first-party; same row, `actor_type="candidate"`).
- `revoke(candidate_id, consent_id) -> bool` — **ownership-enforced**: look up the
  grant; if it is missing or its `candidate_id != candidate_id` → `LookupError`
  (404); else `LedgerStore.revoke_consent`.
- `build_portal_service(settings, *, candidates=None, ledger=None,
  report_store=None) -> PortalService` (cycle-safe builder pattern).

### 5.3 Small store additions — `app/ledger/store.py`

The portal needs two thin, candidate-scoped reads the ledger doesn't expose yet:

- `consents_for_candidate(candidate_id) -> list[ConsentGrant]` — all grants for a
  candidate (active + revoked + expired), ordered by `granted_at`. A raw read like
  `records_for_candidate`; no consent gate (it is the candidate's own consent
  ledger).
- `get_grant(consent_id) -> Optional[ConsentGrant]` — needed for the
  ownership check in `PortalService.revoke`. (Trivial `session.get` + `_grant`.)

Both are pure additions; nothing existing changes.

### 5.4 Wiring — `app/services/…`

- `Services.portal: PortalService` added (function-local build + `TYPE_CHECKING`
  import — the cycle-safe pattern S4.3/S5.1/S5.2/S5.3/S6.3 established).
- `build_default_services` constructs `PortalService`, sharing the already-built
  `candidates`, `ledger`, `report_store`, and `profile_sources` instances (no new
  DB connections; the portal owns no store of its own).

### 5.5 Migration `0012_candidate_credentials`

One table `candidate_credentials` (columns per §5.1). Surrogate `id` PK + a
**unique index on `candidate_id`** (one credential per candidate) + an index on
`access_key_hash` (the auth lookup). **Candidate FK ON DELETE CASCADE** — erasure
sweeps the credential. Extend the drift-guard / index / FK-ondelete / nullability
tests to the new table per repo convention. SQLite-now / Postgres-shaped: fine on
both.

## 6. API

### 6.1 Admin plane (`X-API-Key`, existing `router`)

- `POST /candidates/{candidate_id}/auth-key` → **200** `{candidate_id,
  access_key}` (once) · **404** unknown candidate · **401** without the admin key.

### 6.2 Candidate plane (`X-Candidate-Key`, new `candidate_router`)

All resolve the acting candidate from the key; **401** on a missing/invalid key.

- `GET /portal/me` → **200** `MyData`.
- `GET /portal/access-log` → **200** `list[AccessLogEntry]` (newest-first).
- `GET /portal/consents` → **200** `list[ConsentView]`.
- `POST /portal/consents` — body `{purpose, org_id?, expires_at?}` → **200**
  `ConsentGrant` · **404** unknown `org_id` (propagated from `grant_consent`) ·
  **422** bad purpose (enum validation at the boundary).
- `POST /portal/consents/{consent_id}/revoke` → **200** `{consent_id, revoked:
  bool}` · **404** when the grant is unknown **or not owned by the caller**
  (ownership-enforced — a candidate can never learn another's grant ids by
  probing: same 404 either way).
- `DELETE /portal/me` → **200** `{candidate_id, deleted: true, reports_deleted:
  N}` (reuses the erasure path). Subsequent calls with the same key → **401**.

## 7. Config (`config.yaml` / `Settings`)

| knob | default | purpose |
|---|---|---|
| `candidate_access_key_bytes` | 32 | entropy of a minted candidate key (`ge=16`, mirrors `ledger_api_key_bytes`) |
| `ret_resume_days` | 1095 | retention window surfaced for resumes (3y, illustrative) |
| `ret_interview_record_days` | 1825 | interview records (5y) |
| `ret_coding_round_days` | 1825 | coding rounds (5y) |
| `ret_observed_offer_days` | 1825 | observed offers (5y) |
| `ret_profile_source_days` | 1095 | profile-source signals (3y) |
| `ret_audit_log_days` | 2555 | audit trail — deliberately longest (7y); accountability outlives content |

Defaults are illustrative retention windows, **not** enforced deletion (no sweep
this sprint); they parametrize the surfaced `retained_until` only.

## 8. Testing (TDD-offline) + smoke

**Unit / integration (offline, no key):**

- **Auth:** `issue_access_key` mint + rotate (new hash, `rotated_at` set, old key
  stops authenticating); `authenticate_candidate` match / unknown / empty; unknown
  candidate on mint → `LookupError`; credential row CASCADEs on
  `delete_candidate`.
- **`require_candidate`:** 401 on missing/invalid/empty key; resolves to the right
  candidate on a valid key.
- **Store additions:** `consents_for_candidate` returns active+revoked+expired
  ordered; `get_grant` hit/miss.
- **Retention (pure):** `retained_until` math; `build_retention_policy` maps each
  class to its knob and computes oldest→retained_until; empty class → `None`s.
- **`PortalService`:** `my_data` composition shape (profile/resumes/sources/records/
  coding/reports-as-refs/consents/retention); `access_log` projection + org-name
  resolution + newest-first + `allowed` surfaced; `consents` state labelling;
  `grant` writes an `actor_type="candidate"` row; `revoke` ownership — owner
  succeeds, non-owner → `LookupError` (and does **not** revoke B's grant).
- **Cross-candidate isolation:** A's key never surfaces B's data on any endpoint;
  A revoking B's `consent_id` → 404 and B's grant stays active.
- **Reports:** `my_data` exposes `ReportRef` (id/domain/created_at) only — no
  verdicts/fabrication fields present in the response.
- **Erasure:** `DELETE /portal/me` removes candidate + credential + reports +
  cascaded ledger rows; the key then 401s.
- **API:** each endpoint's status matrix (200/401/404/422); admin mint 200/404/401.
- **Migration `0012`** drift/index/FK/nullability guards.

**Smoke `scripts/smoke_s64.py`** (uvicorn, key-less):

1. create candidate → admin `POST /candidates/{id}/auth-key` → get key K.
2. `GET /portal/me` with K → profile + resumes + retention posture present;
   `reports` are refs (no internals).
3. create org + key; admin-grant `ledger_write` + `ledger_read`; org submits an
   interview record; org queries records (allowed).
4. `GET /portal/access-log` with K → shows the org's `record.submit` and
   `record.query` (allowed=true), org **name** resolved.
5. `POST /portal/consents` with K (first-party grant) → 200; `GET /portal/consents`
   shows it active.
6. `POST /portal/consents/{id}/revoke` with K → 200 revoked; state now `revoked`.
7. wrong/absent key → 401; a second candidate's key cannot see candidate 1's data
   and cannot revoke candidate 1's grant (404, grant untouched).
8. `DELETE /portal/me` with K → deleted; K now 401s; `GET /candidates/{id}` (admin)
   → 404.

Target: `pytest -q` green (752 → ~785), smoke exit 0.

## 9. Non-goals / follow-ups

- **Retention sweep (mechanical purge).** Surfaced as posture this sprint; the
  deterministic, `now`-injected purge job lands in **PI-8** with the scheduler /
  observability work. (Scope decision 1.)
- **Real candidate registration (password/OTP/email/session).** The minted access
  key is the offline-deterministic stand-in; a productionized self-serve
  registration + session flow is a **PI-8** concern. (Scope decision 3.)
- **Exposing depth `Report` internals to the candidate.** v0 lists reports by
  existence only (decision (a)); whether/how to surface advisory internals (and
  correction rights over them) to the evaluated person is a deferred policy call.
- **Correction / rectification right.** DPDP includes correction; v0 covers
  access / transparency / consent-control / erasure. Candidate-initiated profile
  correction is a natural follow-up.
- **Grievance / DPO contact endpoint.** A statutory DPDP touchpoint; deferred to
  the org-self-serve / productionization work (PI-8).
- **Multi-credential / device sessions.** One key per candidate today; multiple
  named credentials or revocable sessions are YAGNI until needed.

## 10. Definition of done

- `candidate_credentials` model + migration `0012` (candidate CASCADE, unique on
  `candidate_id`); drift/index/FK/nullability guards extended.
- `CandidateStore.issue_access_key` / `authenticate_candidate`; `require_candidate`
  dependency + `candidate_router`; admin `POST /candidates/{id}/auth-key`.
- `app/portal/` (schema, retention, service) + `Services.portal` wiring.
- `LedgerStore.consents_for_candidate` + `get_grant`.
- Six candidate-plane endpoints (`GET /portal/me`, `GET /portal/access-log`,
  `GET /portal/consents`, `POST /portal/consents`,
  `POST /portal/consents/{id}/revoke`, `DELETE /portal/me`).
- `ret_*` + `candidate_access_key_bytes` config knobs.
- `PORTAL.md` written (peer of `LEDGER.md` / `DASHBOARD.md`): the candidate plane,
  the auth model, the DPDP rights map (access / transparency / consent / erasure),
  the retention posture + what's deferred, the endpoint contract, config.
- All tests green offline; `scripts/smoke_s64.py` exit 0.
- ROADMAP status board + Current state + session log updated; **S6.4 marked done →
  PI-6 complete.**
