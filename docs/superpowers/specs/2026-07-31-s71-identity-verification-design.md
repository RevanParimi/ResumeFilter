# S7.1 — Verification Spine + Consent-First Identity — Design

**Date:** 2026-07-31
**Sprint:** S7.1 — the first sprint of **PI-7 (verification & assessment depth)**.
**Status:** Approved design; implementation plan follows.
**Reads before this:** `docs/ROADMAP.md` → `docs/superpowers/specs/2026-07-26-veritas-vision-gap-analysis.md` §5B/§6/§7.
**Peers:** `LEDGER.md` (consent machinery reused), `PORTAL.md` (candidate plane
reused), `PROFILE_SOURCES.md` (the spine-plus-adapters pattern copied).

---

## 1. Why this sprint

Gap analysis §5B: *"No identity verification (liveness, doc-based KYC) — proxy
candidates defeat all downstream evaluation. Proxy interviewing is the #1 Indian
hiring fraud."* Every signal Veritas already collects — depth evaluations,
coding rounds, cross-company interview records, reputation — silently assumes
the person attached to the `candidate_id` is the person who was evaluated.
Nothing in the system tests that assumption today.

S7.1 does not close that gap by itself; no v0 can. What it closes is the
**structural** gap: there is currently no place to put a verification outcome,
no consent basis for obtaining one, and no seam for a real KYC provider to plug
into. This sprint builds that spine and populates it with the verification
methods that are genuinely implementable offline, so that:

- **S7.2** (document forensics + moonlighting advisory) lands as a *second
  producer* into the same spine — precisely the way S6.2's LinkedIn adapter
  landed on S6.1's `profile_sources` spine.
- **S7.3** (AI interview delivery) has an identity outcome to hang its
  proxy-detection hooks on.
- A real DigiLocker/Aadhaar/PAN integration is later a **new adapter**, not a
  schema migration and not a consent retrofit.

## 2. Scope decisions (taken with user, 2026-07-31)

All three were presented with alternatives; the recommendation was taken in each
case, with standing instruction to proceed autonomously thereafter.

1. **PI-7 order: S7.1 (verification spine + identity) first**, then S7.2 as a
   second producer on the spine, then S7.3. Rejected: leading with S7.3 (largest
   build, would strand identity hooks as stubs); merging S7.1+S7.2 into one
   sprint (more surface per merge).
2. **v0 = an assurance ladder behind an adapter seam**, shipping the three
   methods buildable with no vendor and no network, with government ID as a
   *declared but unimplemented* adapter whose consent gate and data posture are
   designed now. Rejected: OTP-only (S7.2 would have to retrofit the spine);
   an outcome-recording API only (skips the candidate-initiated consent flow
   that is the entire point of §5B's landing zone).
3. **Two new `ConsentPurpose` members** — `IDENTITY_VERIFY` (perform a
   verification via an external source) and `VERIFICATION_READ` (an org may see
   assurance). Rejected: one purpose (a real govt-ID adapter would then have no
   grant to attach to); reusing `LEDGER_READ` (silently widens what grants
   candidates have *already signed* disclose — a retroactive scope expansion).

## 3. Non-negotiables inherited (do not relitigate)

From `CLAUDE.md`, the ROADMAP's standing conventions, and gap-analysis §7:

1. **Advisory only.** `IdentityAssurance` never gates matching, ranking, depth
   scoring, or any rejection. No auto-reject, ever.
2. **Consent before signal.** Third-party/biometric-adjacent data is
   candidate-initiated and purpose-scoped through the *existing* consent
   machinery. New purposes join `ConsentPurpose`; they never bypass it.
3. **Store outcomes, never source documents or biometrics.**
4. **TDD, fully offline.** No network, no LLM anywhere in S7.1.
5. **Erasure sweeps everything** — every candidate-linked table CASCADEs.
6. Config tunables in `config.yaml`; taxonomies are code constants.

## 4. DPDP posture — the important one

**The "never store the document" rule is structural, not procedural.** Neither
new table has any column capable of holding an artifact. The single evidence
field is `evidence_digest`, a fixed-length sha256 hex string. A future govt-ID
adapter *physically cannot* persist a document, image, or biometric through this
schema without a migration that a reviewer would see and question. This is
deliberate: a rule written in a docstring degrades, a schema that cannot express
the violation does not.

**Consent basis by actor:**

| Action | Basis |
|---|---|
| Candidate self-attests, or OTPs their **own** contact | No grant. Identity of the subject *is* the authorization — the S6.4 principle: acting on your own data is a data-principal right, not a disclosure. |
| Platform verifies via an **external** source | Active `IDENTITY_VERIFY` grant required. Enforced by the spine on any adapter with `third_party = True`. |
| Org **reads** a candidate's assurance | Active `VERIFICATION_READ` grant required. Query-time enforcement + audit of every attempt, allowed **or** denied. Mirrors `query_records_for_org`. |
| Operator records a manual review | Admin plane (`X-API-Key`). Platform-internal, audited. |

**Erasure:** both tables CASCADE from `candidates`. A DPDP delete removes every
verification and challenge; the org-plane assurance read then 404s.

**Retention:** a `verifications` window joins `RetentionPolicy` in the portal
(`ret_verifications_days`, default 1095). Consistent with S6.4, the *mechanical*
retention sweep stays deferred to PI-8 — posture is surfaced, not enforced.

**One deliberate exception to that deferral:** expired or consumed
`verification_challenges` rows **are** actually deleted, at the point of
consumption and opportunistically when a candidate starts a new challenge on the
same verification. This is not a retention policy; it is short-TTL secret
material. Leaving live OTP code hashes lying around would be the defect, and no
scheduler is needed because the deletion happens on paths that already run.

**No new PII is introduced.** The OTP challenge stores a `destination_hash`
computed with S1.1's existing salted `contact_hash` over the candidate's own
already-stored contact — the raw email or phone is never re-persisted by this
subsystem.

## 5. Architecture

New pure package `app/verification/`, a peer of `app/profile_sources/`,
`app/portal/`, and `app/ledger/`. It owns its own tables and imports the ledger
for consent; **the ledger never imports verification** (same layering rule S5.2
established for comp).

### 5.1 `schema.py` — contracts and code-constant taxonomies

```python
class AssuranceLevel(IntEnum):     # ordered — "highest level held" is a max()
    NONE = 0
    SELF_ATTESTED = 1
    CONTACT_CONTROL = 2
    REVIEWED = 3
    GOVERNMENT_ID = 4

class VerificationMethod(StrEnum):
    SELF_ATTESTED = "self_attested"
    OTP_EMAIL = "otp_email"
    OTP_PHONE = "otp_phone"
    MANUAL_REVIEW = "manual_review"
    GOVERNMENT_ID = "government_id"   # declared; no v0 implementation

class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"
```

`METHOD_LEVEL: dict[VerificationMethod, AssuranceLevel]` is a module constant.
Levels are a reviewed schema decision, never a deploy-time tunable — the same
stance as `InterviewStage`/`ConsentPurpose`.

```python
class Verification(BaseModel):
    id: str
    candidate_id: str
    method: VerificationMethod
    assurance_level: AssuranceLevel
    status: VerificationStatus
    consent_id: Optional[str] = None       # set only for third-party adapters
    evidence_digest: Optional[str] = None  # sha256 hex; NEVER an artifact
    details: dict = Field(default_factory=dict)   # non-PII
    requested_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

class IdentityAssurance(BaseModel):
    """Advisory. Computed, never stored."""
    candidate_id: str
    level: AssuranceLevel = AssuranceLevel.NONE
    methods: list[VerificationMethod] = Field(default_factory=list)
    verified_at: Optional[datetime] = None   # most recent contributing outcome
    expired_methods: list[VerificationMethod] = Field(default_factory=list)
    advisory: bool = True
```

`AssuranceLevel` is an `IntEnum` specifically so "the highest level currently
held" is an ordinary `max()` and comparisons are total — the one place where
ordering is genuinely semantic rather than incidental.

### 5.2 `assurance.py` — pure, clock-injected

Mirrors `ledger/consent.py`: no I/O, no `utcnow()`, caller passes `at`.

- `is_expired(v: Verification, *, at: datetime) -> bool` — coerces via
  `as_utc` (reused from `app.ledger.consent`, because SQLite returns naive
  datetimes and S3.1 already solved this exact hazard).
- `effective_status(v, *, at) -> VerificationStatus` — a stored `verified` past
  `expires_at` reads as `expired`. Expiry is computed at read time, not written
  by a job; there is no scheduler and a stale stored status would lie.
- `compute_assurance(candidate_id, verifications, *, at) -> IdentityAssurance` —
  folds to the highest level among non-expired `verified` outcomes, lists
  contributing methods, and separately reports methods that *were* verified but
  have lapsed (so the portal can prompt a re-verify rather than silently
  showing a downgrade).

### 5.3 `methods.py` — the adapter seam

```python
class VerificationMethodAdapter(Protocol):
    method: VerificationMethod
    level: AssuranceLevel
    third_party: bool          # True => spine requires IDENTITY_VERIFY
    challenge_based: bool      # True => start/confirm two-step
```

Shipped adapters: `SelfAttestedAdapter` (L1, immediate), `OtpEmailAdapter` /
`OtpPhoneAdapter` (L2, challenge-based), `ManualReviewAdapter` (L3, admin-plane
completion). `GovernmentIdAdapter` is **declared with `third_party = True` and
raises `NotImplementedError`**; no route can reach it, and a registry lookup
test asserts exactly that.

The consent gate lives in the **spine**, keyed off `adapter.third_party` — not
in any individual adapter. Tests register a `_FakeThirdPartyAdapter` to prove
the gate fires without shipping a real external integration.

### 5.4 `otp.py` — pure OTP mechanics

`generate_code(length, *, rng)`, `hash_code(code, salt)` (sha256, reusing the
`contact_hash_salt` convention), and pure attempt/TTL arithmetic. Injected RNG
and clock make every path deterministic under test. No I/O.

Delivery sits behind a tiny `Notifier` protocol with a `NullNotifier` that logs
and discards — this repo has no email/SMS provider and S7.1 does not add one.

**Where the OTP destination comes from — a load-bearing detail.** The
`candidates` table stores *only* `email_hash` / `phone_hash`; there is no raw
contact value on the identity record to send to. Rather than reach into the
extracted-profile JSON for a raw address, the candidate **supplies the
destination in the start request**, and the spine normalizes it with S1.1's
`normalize_email` / `normalize_phone`, hashes it with `contact_hash`, and
**requires the result to equal the hash already on their candidate row**.

This is better than a lookup on three counts: it proves the candidate knows the
contact on file (a small verification in its own right), it works regardless of
whether extraction retained a raw value, and the raw destination is used
transiently for delivery and **never persisted** — only `destination_hash` is
stored. A mismatch is a 400; a candidate with no hash of that type on file is
likewise a 400 with a distinct reason.

### 5.5 `models.py` + migration `0013_identity_verification`

`verifications` — durable outcomes. `candidate_id` FK CASCADE; indexed on
`(candidate_id, status)`.

`verification_challenges` — short-lived secret material, deliberately a
*separate* table: `verification_id` FK CASCADE, `code_hash`, `channel`,
`destination_hash`, `attempts`, `max_attempts`, `expires_at`, `consumed_at`.
Separate because its lifecycle (create → consume → delete) and its sensitivity
are both categorically different from an outcome row, and because dropping the
whole table later costs nothing.

The existing metadata drift / index / FK-ondelete / nullability guards are
extended to both new tables, as every migration since 0004 has done.

### 5.6 `store.py` + `service.py`

`VerificationStore` — persistence, plus the two consent enforcement points
(third-party performs, org-plane reads) and audit writes in the same transaction
as the mutation, exactly as `LedgerStore` does. Audit actions:
`verification.start`, `verification.complete`, `verification.query`
(allowed *and* denied), `verification.manual_review`.

`VerificationService` — orchestration: resolve adapter → enforce consent when
`third_party` → create/complete → compute assurance. Composes `CandidateStore`
(existence + contact hashes) and `LedgerStore` (consent + audit). Wired as
`Services.verification` with the established cycle-safe pattern (`TYPE_CHECKING`
import + function-local build in `build_default_services`).

## 6. API

### 6.1 Candidate plane (`X-Candidate-Key`, existing `candidate_router`)

| Route | Behaviour |
|---|---|
| `POST /portal/verifications` | Body `{method, destination?}`. Self-attest completes immediately → `verified` at L1. OTP methods require `destination`, match its hash against the candidate's stored `email_hash`/`phone_hash` (§5.4), then create a pending verification + challenge and "send" via the notifier. Hash mismatch, missing `destination`, or no contact hash of that type on file → **400** (distinct reasons). A `third_party` adapter without an active `IDENTITY_VERIFY` grant → **403**. Unknown method → 422. Resend inside `verif_otp_resend_cooldown_seconds` → **429**. |
| `POST /portal/verifications/{id}/confirm` | Body `{code}`. Correct + unexpired → `verified`. Wrong code → 400, attempts incremented; at `verif_otp_max_attempts` the verification flips to `failed`. Expired challenge → 400. |
| `GET /portal/verifications` | The candidate's own verifications + current `IdentityAssurance`. |
| `GET /portal/me` | Gains `identity: IdentityAssurance` on `MyData`. |

Ownership isolation is **structural**, as in S6.4: every handler resolves
`candidate_id` from the key and never from a path or body param. Another
candidate's `verification_id` is an indistinguishable **404** — no probing.

### 6.2 Org plane (`X-Org-Key`, existing `org_router`)

| Route | Behaviour |
|---|---|
| `GET /verification/candidates/{id}/assurance` | `VERIFICATION_READ` enforced at query time; every attempt audited allowed or denied. 403 without a grant, 404 for an unknown candidate. Returns `IdentityAssurance` **only** — never `evidence_digest`, never `destination_hash`, never raw contacts. |

### 6.3 Admin plane (`X-API-Key`, existing `router`)

| Route | Behaviour |
|---|---|
| `POST /candidates/{id}/verifications/manual-review` | Body `{outcome: verified\|failed, note?, evidence_digest?}`. Records an L3 `REVIEWED` outcome. 200 / 404 unknown candidate / 401. |

## 7. Config (`config.yaml` / `Settings`)

```yaml
# --- Identity verification (PI-7) - S7.1 spine + consent-first identity -------
verif_otp_length: 6                  # digits in an OTP challenge
verif_otp_ttl_minutes: 10            # challenge lifetime
verif_otp_max_attempts: 5            # wrong codes before the verification fails
verif_otp_resend_cooldown_seconds: 60  # min gap between challenges on one verification
verif_outcome_ttl_days: 365          # a verified outcome reads as expired after this
verif_otp_debug_echo: false          # local-only: echo the code in the response
ret_verifications_days: 1095         # retention window surfaced in the portal
```

`verif_otp_debug_echo` is **double-guarded**: the code is echoed only when
`env == "local"` *and* the knob is true. The smoke script sets
`DEE_VERIF_OTP_DEBUG_ECHO=true` so it can drive the two-step flow over plain
HTTP; production cannot echo a code even if the knob is flipped by accident.

## 8. Testing (TDD-offline) + smoke

Fully offline: no network, no LLM, no clock reads in pure code. Coverage:

- **`assurance.py`** — level folding, `max()` across mixed methods, expiry at
  read time, lapsed-method reporting, naive-vs-aware datetime coercion.
- **`otp.py`** — code generation under an injected RNG, hash stability, TTL and
  attempt arithmetic at boundaries.
- **Adapter registry** — every `VerificationMethod` resolves; `government_id`
  raises `NotImplementedError` and is unreachable from any route.
- **Consent gate** — a `_FakeThirdPartyAdapter` is refused without
  `IDENTITY_VERIFY` and admitted with it; `consent_id` is stamped on the row.
- **Org read** — 403 without `VERIFICATION_READ`, 200 with, revocation flips it
  back, and *both* outcomes leave an audit row.
- **Isolation** — candidate B cannot see or confirm candidate A's verification
  (404, A's row untouched).
- **Destination binding** — an OTP start whose `destination` hashes to something
  other than the candidate's stored hash is refused; a candidate with no hash of
  that type on file is refused with a distinct reason; the raw destination
  appears in **no** persisted row (asserted by inspecting the challenge row).
- **Challenge hygiene** — a consumed challenge row is gone; a resend inside the
  cooldown is refused (429).
- **DPDP** — erasing the candidate cascades both tables; the org read then 404s.

**Smoke `scripts/smoke_s71.py`** (uvicorn + scripted HTTP, key-less): create
candidate from a fixture resume carrying an email → mint candidate key →
`GET /portal/me` shows `level: none` → self-attest → level `self_attested` →
start `otp_email` with a **wrong** destination → 400 → start with the resume's
real email → wrong code → 400 → correct code (read via the double-guarded
`verif_otp_debug_echo`) → level `contact_control` → org read 403 → grant
`VERIFICATION_READ` → org read 200 with the level → revoke → 403 again → admin
manual review → level `reviewed` → `DELETE /portal/me` → org read 404.

## 9. Non-goals / follow-ups

**Explicit non-goals for S7.1:**

- No DigiLocker / Aadhaar / PAN / any KYC vendor integration. The seam and its
  consent gate exist; the adapter raises.
- No liveness, face match, or any biometric capture.
- No feature-store consumption — assurance is not a ranking feature yet.
- No effect on matching, ranking, depth scoring, or `fabrication_risk`.
- No email/SMS delivery provider.

**Follow-ups (recorded, not built):**

- S7.2 lands document forensics as a second producer on this spine.
- S7.3 reads `IdentityAssurance` for proxy-detection hooks.
- PI-8: real OTP delivery; the mechanical retention sweep; assurance as a
  feature-store feature once its predictive value is measurable.
- A real govt-ID adapter needs vendor selection **and** a legal review of
  DigiLocker API terms — flagged in gap-analysis §8 and still open.

## 10. Definition of done

- `pytest -q` green (784 + new tests), fully offline.
- `alembic upgrade head` clean; drift/index/FK/nullability guards extended.
- `scripts/smoke_s71.py` exits 0, all checks OK, key-less.
- `VERIFICATION.md` written (peer of `LEDGER.md` / `PORTAL.md`).
- `docs/ROADMAP.md` status board + "Current state" + session log updated.
- Whole-branch review clean of Critical/Important before merge.
