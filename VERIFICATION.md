# VERIFICATION.md — the verification spine (PI-7, S7.1)

Peer of `LEDGER.md` (consent machinery) and `PORTAL.md` (candidate plane).
Design record: `docs/superpowers/specs/2026-07-31-s71-identity-verification-design.md`.

`app/verification/` answers one question — **how confident are we that the
person attached to a `candidate_id` is who they claim to be?** — and provides
the place every later PI-7 producer writes its outcomes.

Everything here is **advisory**. Assurance never gates matching, ranking, depth
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

- **S7.2** (document forensics + moonlighting advisory) lands as a *second
  producer* on this spine — the same way S6.2's LinkedIn adapter landed on
  S6.1's `profile_sources` spine.
- **S7.3** (AI interviews) reads `IdentityAssurance` for proxy-detection hooks.
- A real DigiLocker/Aadhaar/PAN integration is later **a new adapter**, not a
  schema migration and not a consent retrofit.

## 2. The DPDP posture is structural, not procedural

**Neither table has a column capable of holding a document, image, or
biometric.** The only evidence field is `evidence_digest` — a sha256 hex
string. A future government-ID adapter *physically cannot* persist an artifact
through this schema without a migration that a reviewer would see and question.

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
| `GET /portal/verifications` | The candidate's own verifications + current `IdentityAssurance`. |
| `GET /portal/me` | Carries `identity: IdentityAssurance`. |

Isolation is **structural**: every handler resolves `candidate_id` from the
key, never from a path or body param. Another candidate's `verification_id` is
an indistinguishable **404** — no probing.

### Org plane (`X-Org-Key`)

| Route | Behaviour |
|---|---|
| `GET /verification/candidates/{id}/assurance` | `VERIFICATION_READ` enforced at query time, every attempt audited. 403 without a grant, 404 unknown candidate. Returns the advisory roll-up **only** — never `evidence_digest`, never `destination_hash`, never individual attempt rows. |

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
```

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

**Follow-ups:** S7.2 document forensics as a second producer · S7.3 proxy
-detection hooks reading assurance · PI-8 real OTP delivery, the mechanical
retention sweep, and assurance as a feature once its predictive value is
measurable. A real govt-ID adapter needs vendor selection **and** a legal
review of DigiLocker API terms (gap-analysis §8, still open).
