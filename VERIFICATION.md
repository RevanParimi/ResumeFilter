# VERIFICATION.md — the verification spine (PI-7, S7.1 + S7.2)

Peer of `LEDGER.md` (consent machinery) and `PORTAL.md` (candidate plane).
Design records:
`docs/superpowers/specs/2026-07-31-s71-identity-verification-design.md` (spine)
· `docs/superpowers/specs/2026-07-31-s72-document-forensics-design.md` (claims).

`app/verification/` answers **two** questions, and keeps them apart on purpose:

| Subject | Question | Ladder | Roll-up |
|---|---|---|---|
| `identity` (S7.1) | is the person attached to this `candidate_id` who they claim to be? | `AssuranceLevel` 0–4 | `IdentityAssurance` |
| `employment_claim` (S7.2) | is this job history real? | `ClaimStrength` 0–4 | `ClaimEvidence` |

Both are stored as `verifications` rows discriminated by a `subject` column, so
they share audit, consent, CASCADE and the adapter seam — and **fold into two
separate numbers**. §11 explains why that separation is load-bearing.

Everything here is **advisory**. Neither number gates matching, ranking, depth
scoring, or any rejection.

---

## 1. Why a spine and not just "identity verification"

Every signal Veritas collects — depth evaluations, coding rounds, cross-company
interview records, reputation — silently assumes the person evaluated is the
person on the record. Proxy interviewing is the single most common Indian
hiring fraud, so that assumption is exactly the one worth testing.

S7.1 does not close that gap on its own; no v0 can without a KYC vendor. What
it closes is the **structural** gap. Before this sprint there was nowhere to
put a verification outcome, no consent basis for obtaining one, and no seam for
a provider to plug into. Now:

- **S7.2** (document forensics + concurrent-employment advisory) **landed** as a
  *second producer* on this spine — the same way S6.2's LinkedIn adapter landed
  on S6.1's `profile_sources` spine. It added three methods, a `subject`
  discriminator and a second roll-up; it added **no** new table, **no** new
  consent purpose and **no** new erasure path. §11–§14.
- **S7.3** (AI interviews) reads `IdentityAssurance` for proxy-detection hooks.
- A real DigiLocker/Aadhaar/PAN integration is later **a new adapter**, not a
  schema migration and not a consent retrofit.

## 2. The DPDP posture is structural, not procedural

**Neither table has a column capable of holding a document, image, or
biometric.** The only evidence field is `evidence_digest` — a sha256 hex
string. A future government-ID adapter *physically cannot* persist an artifact
through this schema without a migration that a reviewer would see and question.

**S7.2 is where that rule earned its keep**, because a real document is now on
the wire. `POST /portal/documents` accepts base64, parses it in memory, computes
the digest, derives finding *codes*, and drops the bytes — and there is still
nowhere to put them. The models test caps every `String` column on both tables
at 64 chars with exactly one named exception (`claim_ref`, a 128-char employer +
interval **label**), so a column quietly grown to hold text would fail a test.

This is deliberate. A rule written in a docstring degrades under pressure; a
schema that cannot express the violation does not. The guard is enforced by
tests in both `tests/test_verification_schema.py` and
`tests/test_verification_models.py`, which assert the absence of any
artifact-shaped field.

Two further properties fall out of the design:

- **The raw OTP destination is never persisted.** Only `destination_hash`
  (S1.1's salted `contact_hash`) is stored.
- **The raw OTP code is never persisted.** Only a salted sha256 digest. The
  `NullNotifier` deliberately logs neither the code nor the destination — an
  OTP in a log file is an OTP leak.

## 3. The assurance ladder

A code constant (`app/verification/schema.py`), never a config tunable —
changing it is a reviewed schema decision, same stance as `InterviewStage` and
`ConsentPurpose`.

| Level | Method | v0 status |
|---|---|---|
| 0 `NONE` | — | no verification held |
| 1 `SELF_ATTESTED` | `self_attested` | ships — the candidate asserts their own identity |
| 2 `CONTACT_CONTROL` | `otp_email`, `otp_phone` | ships — proves control of the contact on file |
| 3 `REVIEWED` | `manual_review` | ships — an operator checked out of band; **admin plane only** |
| 4 `GOVERNMENT_ID` | `government_id` | **declared, not implemented** — the spine refuses it (422) |

`AssuranceLevel` is an `IntEnum` because ordering is genuinely semantic here:
"the highest level a candidate currently holds" is an ordinary `max()`.

**Expiry is computed at read time**, never written by a job. There is no
scheduler in this system, so a stored `expired` status would be a lie nobody
corrects. A stored `verified` past `verif_outcome_ttl_days` reads as `expired`
and stops contributing — but the lapsed method is still reported in
`IdentityAssurance.expired_methods`, so the portal can prompt a re-verify
rather than showing an unexplained downgrade.

## 4. The adapter seam

```python
class VerificationMethodAdapter(Protocol):
    method: VerificationMethod
    level: AssuranceLevel
    third_party: bool      # True => spine requires an IDENTITY_VERIFY grant
    challenge_based: bool  # True => two-step start/confirm
    self_service: bool     # True => a candidate may initiate it themselves
    implemented: bool      # False => the spine refuses; nothing stands behind it
    instant: bool          # True => assertion IS the evidence; completes on start
```

An adapter declares **what a method is**, not how the spine treats it. Every
gate lives in `VerificationService.start`, keyed off these flags — never inside
an adapter. *A gate an adapter could forget to apply is not a gate.* All three
booleans default to the **refusing** answer on `_Base`, so a new adapter is
inert until it says out loud what it is.

`VerificationService.start` is the **candidate-initiated** entry point and
applies them in order: `self_service` (may a candidate award themselves this at
all?), `implemented` (is there anything behind it?), the `third_party` consent
gate, then destination binding. Operator outcomes never pass through it — they
come in via `record_manual_review` on the admin plane.

`GovernmentIdAdapter` ships declared and inert, carrying its level, its
`third_party=True` flag, and therefore its consent requirement. **Its inertness
is `implemented = False`, enforced by the spine** — not the `NotImplementedError`
in the adapter, which is only a backstop: the spine performs verifications
itself and never calls an adapter to do the work, so an adapter-side raise
alone would never fire. A `_FakeThirdPartyAdapter` proves the spine's consent
gate fires, without shipping any external integration.

**Consent is necessary, never sufficient.** A candidate can grant themselves
`IDENTITY_VERIFY` from the portal (S6.4 first-party consent, by design), so the
`implemented` gate stands in front of the consent gate. Likewise
`manual_review` is `self_service = False`: it asserts a human at the platform
looked, and a candidate able to request it would simply award themselves L3.

## 5. Consent model

Two new `ConsentPurpose` members — the first taxonomy addition since S3.1.

| Action | Basis |
|---|---|
| Candidate self-attests, or OTPs their **own** contact | **No grant.** Identity of the subject *is* the authorization — the S6.4 principle: acting on your own data is a data-principal right, not a disclosure. |
| Platform verifies via an **external** source | Active **`IDENTITY_VERIFY`** grant. Enforced by the spine on any `third_party` adapter; the authorizing grant id is stamped on the row. |
| Org **reads** a candidate's assurance | Active **`VERIFICATION_READ`** grant. Query-time enforcement + audit of every attempt, allowed **or** denied. Mirrors `query_records_for_org`. |
| Operator records a manual review | Admin plane (`X-API-Key`) **only** — `manual_review` is not self-service, so the candidate plane refuses it with 403. Platform-internal, audited. |

`VERIFICATION_READ` is deliberately its own purpose rather than a reuse of
`ledger_read`: reusing it would silently widen what grants candidates have
*already signed* disclose — a retroactive scope expansion.

**Audit actions:** `verification.start`, `verification.complete`,
`verification.query` (both outcomes). These land in the shared `audit_log`, so
verifications appear in the candidate's own `/portal/access-log` for free.

## 6. Destination binding — a load-bearing detail

The `candidates` table stores **only** `email_hash` / `phone_hash`. There is no
raw address to send an OTP to.

Rather than reach into the extracted-profile JSON for a raw value, the
candidate **supplies the destination in the start request**. The spine
normalizes it (`normalize_email` / `normalize_phone`), hashes it
(`contact_hash`), and requires the result to equal the hash already on their
candidate row.

This is better than a lookup on three counts: it proves the candidate knows the
contact on file (a small verification in its own right), it works regardless of
whether extraction retained a raw value, and the raw destination stays
transient — only the hash is written. A mismatch is a 400; a candidate with no
hash of that type on file is a 400 with a distinct reason.

## 7. API

### Candidate plane (`X-Candidate-Key`)

| Route | Behaviour |
|---|---|
| `POST /portal/verifications` | Body `{method, destination?}`. Self-attest completes immediately → `verified` at L1. OTP methods bind the destination (§6), create a pending verification + challenge, and "send" via the notifier. 400 on destination problems · 403 for a method a candidate may not initiate (`manual_review`) or without `IDENTITY_VERIFY` for a third-party adapter · 422 unknown method **or a declared-but-unimplemented one (`government_id`)** · 429 resend inside the cooldown. |
| `POST /portal/verifications/{id}/confirm` | Body `{code}`. Correct + unexpired → `verified`. Wrong → 400, attempts incremented; at `verif_otp_max_attempts` the verification flips to `failed`. Expired challenge → 400. |
| `POST /portal/documents` | **(S7.2)** Body `{doc_type, content_b64, claim_ref?}`. Parses, assesses, writes ONE claim verification. 200 `{verification, findings, claims}` · 400 unparseable or bad base64 · 403 a method a candidate may not initiate · 404 unknown candidate · 422 oversize (`doc_max_b64_chars`), over `doc_max_pages`, or an unknown `doc_type`. |
| `GET /portal/verifications` | The candidate's own verifications + current `IdentityAssurance` **+ `claims: ClaimEvidence` (S7.2)** — two numbers, side by side, never merged. |
| `GET /portal/me` | Carries `identity: IdentityAssurance` **and `claims: ClaimEvidence` (S7.2)**. |

Isolation is **structural**: every handler resolves `candidate_id` from the
key, never from a path or body param. Another candidate's `verification_id` is
an indistinguishable **404** — no probing.

### Org plane (`X-Org-Key`)

| Route | Behaviour |
|---|---|
| `GET /verification/candidates/{id}/assurance` | `VERIFICATION_READ` enforced at query time, every attempt audited (`verification.query`). 403 without a grant, 404 unknown candidate. Returns the advisory roll-up **only** — never `evidence_digest`, never `destination_hash`, never individual attempt rows. |
| `GET /verification/candidates/{id}/claims` | **(S7.2)** Same purpose, same query-time gate, every attempt audited (`claim.query`) **allowed *and* denied**. Returns `ClaimEvidence` only — never `evidence_digest`, never `claim_ref`, never a finding carrying document content. |

### Admin plane (`X-API-Key`)

| Route | Behaviour |
|---|---|
| `POST /candidates/{id}/verifications/manual-review` | Body `{outcome, note?, evidence_digest?}`. Records an L3 `REVIEWED` outcome. 200 / 404 / 401. |

## 8. Retention and challenge hygiene

A `verifications` window joins the portal's `RetentionPolicy`
(`ret_verification_days`, default 1095). Consistent with S6.4, the *mechanical*
retention sweep stays deferred to PI-8 — posture is surfaced, not enforced.

**One deliberate exception:** expired or consumed `verification_challenges`
rows **are** actually deleted — at the point of consumption, and
opportunistically when a new challenge is issued for the same candidate and
channel. This is not a retention policy; it is short-TTL secret material.
Leaving live OTP code hashes lying around would be the defect, and no scheduler
is needed because the deletion happens on paths that already run.

Supersession and the resend cooldown are scoped to **candidate + channel**, not
to a single verification row. The candidate plane mints a fresh verification on
every start, so a per-row cooldown would rate-limit nothing: an attacker holding
a stolen candidate key could ask again for another code and another full set of
`verif_otp_max_attempts` guesses, and walk a 6-digit code down at will. Per
candidate+channel, exactly one code is ever live and a restart still waits out
the cooldown.

Both tables CASCADE from `candidates`: a DPDP delete removes every verification
and challenge, and the org-plane read then 404s.

## 9. Config (`config.yaml` / `Settings`)

```yaml
verif_otp_length: 6                    # digits in an OTP challenge
verif_otp_ttl_minutes: 10              # challenge lifetime
verif_otp_max_attempts: 5              # wrong codes before the verification fails
verif_otp_resend_cooldown_seconds: 60  # min gap between challenges per candidate+channel
verif_outcome_ttl_days: 365            # a verified outcome reads as expired after this
verif_otp_debug_echo: false            # local-only echo of the code
ret_verification_days: 1095            # retention window surfaced in the portal

# S7.2 — document forensics
doc_max_b64_chars: 8000000        # ~6MB decoded; refused BEFORE any decode
doc_max_pages: 20                 # parse cap
doc_metadata_skew_days: 1         # creation-vs-modification skew worth noting
moonlight_min_overlap_months: 12  # higher than xf_overlap_months_min on purpose
```

**Finding severities are NOT config.** The spec floated a
`doc_unknown_issuer_severity` knob; it ships as a code constant in
`documents.py` instead. A deploy-time switch that can silently reclassify a
finding from `soft` to `hard` is precisely what this file's "taxonomies are code
constants" stance exists to prevent.

`verif_otp_debug_echo` is **double-guarded**: the code is echoed only when
`env == "local"` *and* the knob is true. It exists so `scripts/smoke_s71.py`
can drive the two-step flow over plain HTTP; production cannot echo a code even
if the knob is flipped by accident.

## 10. Non-goals (S7.1)

- No DigiLocker / Aadhaar / PAN / any KYC vendor integration. The seam and its
  consent gate exist; the method is declared `implemented = False` and the spine
  refuses it (422).
- No liveness, face match, or any biometric capture.
- No feature-store consumption — assurance is not a ranking feature.
- No effect on matching, ranking, depth scoring, or `fabrication_risk`.
- No email/SMS delivery provider (`NullNotifier` discards).

**Follow-ups:** S7.3 proxy-detection hooks reading assurance · PI-8 real OTP
delivery, the mechanical retention sweep, and assurance as a feature once its
predictive value is measurable. A real govt-ID adapter needs vendor selection
**and** a legal review of DigiLocker API terms (gap-analysis §8, still open).

---

# S7.2 — employment-claim evidence

## 11. Two subjects, two ladders, one table

`VerificationSubject` (`identity` | `employment_claim`) discriminates every row.
`METHOD_SUBJECT` maps each method to exactly one subject, and the two per-ladder
maps are **disjoint by test**: a claim method has no `AssuranceLevel` entry and
an identity method has no `ClaimStrength` entry.

```
identity          →  METHOD_LEVEL           →  compute_assurance    →  IdentityAssurance
employment_claim  →  METHOD_CLAIM_STRENGTH  →  compute_claim_evidence →  ClaimEvidence
```

Both folds filter on `subject` first and both are pure, clock-injected and
read-time — a stored roll-up would go stale the moment an outcome lapsed.

**Why the separation is load-bearing.** An org reads an assurance level as *"we
have some confidence this is who they say they are."* A payslip is not evidence
of that. Letting one lift the other would be the same failure class as the S7.1
ladder escalation, so it is tested at the same weight: with verified claim rows
present, `IdentityAssurance.level` is still `0`
(`test_a_verified_claim_never_lifts_identity_assurance`, plus an over-HTTP
version and the `identity_level_still_zero` smoke check). The store reinforces
it — `create_verification` resolves the level with
`METHOD_LEVEL.get(method, NONE)`, so adding a claim method cannot mint one.

**The claim ladder:**

| Level | Meaning |
|---|---|
| 0 `NONE` | nothing held |
| 1 `SELF_REPORTED` | the resume says so, nothing backs it |
| 2 `DOCUMENTED` | a document backs it and forensics are clean |
| 3 `CORROBORATED` | document + an independent source agrees *(reserved; nothing emits it yet)* |
| 4 `THIRD_PARTY_VERIFIED` | EPFO et al — declared, inert |

Strength is a `max()` over rows that are `VERIFIED` and unexpired. **A `FAILED`
document contributes nothing and takes nothing away** — its findings are still
returned (the candidate is entitled to know why it failed) and it still appears
in the row list, but a bad submission leaves the candidate exactly where they
were. A failed document is never an accusation.

## 12. The forensics (`documents.py`) — deterministic, no LLM

No LLM and no network. The checks are structural and arithmetic, so the "every
LLM step needs a deterministic fallback" convention is satisfied by having no
LLM at all (the S6.2/S6.3 precedent).

`parse_document` decodes base64, reads a PDF via `app/core/pdf.py`
(`pdf_b64_to_document`, which unlike the text-only helper keeps metadata) or
falls back to a UTF-8 text body — a pasted letter is still assessable, and
refusing it would push candidates toward worse workarounds. It returns text,
page count, metadata and a sha256 digest. `ParsedDocument` has **no field able
to hold the bytes**, which go out of scope with the call.

**Only two findings are HARD**, and both mean *the document contradicts the
resume*, not *the document looks unusual*:

| Code | Severity | Check |
|---|---|---|
| `employer_not_claimed` | **hard** | the document's employer appears nowhere in the resume |
| `letter_dates_mismatch` | **hard** | letter dates do not overlap the claimed role |
| `payslip_arithmetic_mismatch` | **hard** | gross − deductions ≠ net (±₹1 rounding) |
| `payslip_period_outside_role` | **hard** | the pay period falls outside the claimed role |
| `issuer_domain_unknown` | soft | no issuer email domain on the letter |
| `no_employee_id` / `no_signatory` | soft | mill markers |
| `designation_mismatch` | soft | titles drift legitimately |
| `payslip_amounts_unreadable` | soft | amounts could not be read for the check |
| `metadata_modified_after_creation` | soft | PDF mtime ≫ ctime (`doc_metadata_skew_days`) |
| `metadata_producer_present` / `uan_present` / `no_profile_to_compare` | info | context only |

Conservative by construction: a small Indian employer legitimately has no mail
domain and no letterhead conventions in common with a multinational, so an
unknown issuer is `soft`, never `hard`. **A false "fake" costs far more than a
missed one.** Employer matching runs both sides through S1.4 normalization and
tolerates a differently written legal suffix ("Acme Technologies Pvt Ltd" on the
resume vs "ACME TECHNOLOGIES PRIVATE LIMITED" on the letterhead) precisely
because `employer_not_claimed` is one of the two HARD findings.

### `details` is codes, not content — the rule S7.2 lives by

A stored row's `details` carries finding **codes**, booleans and coarse buckets.
Forbidden, and asserted by tests at the pure, service and HTTP layers:

- raw document text or excerpts;
- **salary amounts** — comp intelligence has its own consented, k-anonymised
  path (S5.2, `COMP.md`) and a payslip must not become a back door into it.
  Amounts are read for one subtraction and discarded;
- **UAN / PF / PAN numbers** — presence is a boolean (`uan_present`), the
  identifier never is;
- any contact detail not already hashed on the candidate row.

## 13. Concurrent employment (`moonlighting.py`) — derived, never stored

`assess_concurrent_employment` reuses S2.2's interval machinery
(`narrow_interval`, `overlap_months`, `ym_label`, and the very same
`_NON_PRIMARY` set, imported rather than restated so the two modules cannot
drift on what "primary" means). It emits overlap windows, the longest overlap in
months, and a severity that **tops out at `soft`**.

It is computed at read time from the candidate's own resume and **stored
nowhere** — a stored overlap would go stale the moment the resume is updated,
exactly as a stored assurance would. The threshold
(`moonlight_min_overlap_months`, 12) is deliberately four times S2.2's
`xf_overlap_months_min` (3): a three-month overlap is a notice period.

**This is not an accusation.** Overlapping intervals are consulting, notice
periods and year-only date imprecision at least as often as dual employment. The
output names intervals only, never employers.

## 14. EPFO — answered, and the answer is "vendor, not law"

Open since the 2026-07-26 gap analysis (§8), resolved 2026-07-31.

EPFO/UAN dual-employment verification **is lawful in India**, but access is
mediated: it runs through **authorized BGV aggregators** holding approved EPFO
channels, not through any public API a platform could call. Under the DPDP Rules
2025 the candidate's consent must be explicit, itemized, unbundled, and name the
source, purpose and retention window; withdrawal must purge and log.

So the blocker was never the legality — it is the **commercial vendor
relationship**, which veritas does not have. That puts an EPFO pull in exactly
the category S7.1 built for `government_id`: `epfo_employment` is declared
`third_party=True`, `self_service=True`, `implemented=False`, at
`THIRD_PARTY_VERIFIED`. The spine refuses it with **422** and it lifts nothing —
even after the candidate self-grants `IDENTITY_VERIFY` from the portal, which
they can and by design may do. Consent is necessary, never sufficient. When a
vendor is contracted the work is one adapter and flipping one flag.

## 15. Non-goals (S7.2)

- No BGV vendor, no EPFO pull, no UAN lookup (§14).
- No certificate/degree forensics — a different issuer model, a later sprint.
- No LLM pass over letter phrasing (a deliberate follow-up).
- **No org-submitted documents.** A document an org holds *about* a candidate is
  third-party data under DPDP and needs its own lawful basis. Intake is
  first-party only, under `X-Candidate-Key`.
- No feature-store consumption; claim strength is not a ranking feature.
- No effect on depth scoring, `fabrication_risk` fusion, matching or ranking.
  Document findings stand *beside* `fabrication_risk`; wiring them into that
  fusion is a follow-up, not this sprint.
- Nothing emits `CORROBORATED` (3) yet — the rung is defined so that
  cross-source corroboration lands as a value, not a schema change.

## 16. What the S7.2 branch review found

Two Criticals, both reproduced over HTTP with nothing but a candidate's own key,
both fixed, both re-run to prove closure and kept as regression tests + smoke
checks. Recorded here because the *shape* of each recurs.

**(1) A claim method could be started through the IDENTITY route.**
`POST /portal/verifications {"method": "experience_letter"}` returned **200
`verified`** with `subject: identity` and no document anywhere. Two consequences:
a claim row landed inside `compute_assurance`'s fold, and — because
`compute_assurance` indexed `METHOD_LEVEL` directly — **every later read of that
candidate's own portal 500'd on a `KeyError`, permanently**. One request and a
candidate could destroy their own DPDP access rights.

The root cause is the S7.1 pattern exactly: *a gate applied at one entry point
and not the other*. `submit_document` checked `document_based`; `start` never
asked what subject a method belonged to. `_ClaimBase.instant = True` honestly
means "assessment IS the evidence" — true where forensics have run, false in
`start`, which read it as the older fail-open "complete it now, VERIFIED".

Fixed in three layers: the spine's `start` refuses a non-identity method
(**after** `implemented`, so `epfo_employment` still answers 422 like
`government_id`); `create_verification` refuses any method/subject disagreement
with `METHOD_SUBJECT`, making the bad row *unrepresentable* rather than merely
unreachable; and `compute_assurance` now uses `METHOD_LEVEL.get`, so a rogue row
contributes nothing instead of bricking a portal.

**(2) `claim_ref` was an unbounded text column.** SQLite does not enforce
`VARCHAR(128)`. 5031 characters — including a salary figure and a UAN — were
written straight into a `verifications` row. This defeated the subsystem's
central structural claim through the *one* field
`test_still_no_column_can_hold_a_document` excepts from its 64-char cap: the
exception was the hole. Now bounded by `CLAIM_REF_MAX_CHARS` at the route
(pydantic `max_length` → 422) **and** in the service, so a direct caller cannot
bypass it either.

**Also fixed: the suite was not time-independent.** Several S7.1 tests
(unchanged on `main`) granted consent at wall-clock time and then asserted at a
pinned `NOW` of 12:00 UTC on 2026-07-31 — so the grant did not yet exist at the
instant being checked, and the tests began failing the moment the clock passed
noon. S7.2 copied the pattern into its own store tests. Every `grant_consent` /
`revoke_consent` in these files now passes `now=NOW`, which is what the
clock-injection in `LedgerStore` was for.

**Clean:** `claim.query` is audited on the denied path as well as the allowed
one (the denied row is committed before the `ConsentError` is raised, and shows
up in the candidate's own access log with the org's name resolved); every
adapter that is startable declares how it reaches an outcome; the payslip path
stores no amount, no UAN and no document text at any layer.
