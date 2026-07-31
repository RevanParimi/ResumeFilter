# S7.2 — Document Forensics + Concurrent-Employment Advisory — Design

**Sprint:** PI-7, S7.2 · **Date:** 2026-07-31 · **Status:** designed, not built
**Predecessor:** S7.1 (verification spine), merged to main `990274d`, 887 green
**Pattern:** second producer on the S7.1 spine — the S6.1 → S6.2 relationship

---

## 1. Why this sprint

Fake experience certificates are an industry in India; the gap analysis calls
them out as an "experience letter mill" market (§5B, row: *No experience-letter
/ payslip / certificate forensics*). Veritas can already reason about a resume's
internal coherence (S2.2 cross-field) and about who a candidate is (S7.1
identity assurance). It cannot yet reason about the **documents offered as proof
of an employment claim**.

S7.2 closes that, and does it as a *second producer on the S7.1 spine* rather
than a new subsystem: the spine already owns audited writes, candidate CASCADE,
a consent gate, an adapter seam, and a structural "never store an artifact"
posture. All of that is exactly what document evidence needs.

## 2. Scope decisions (taken with user, 2026-07-31)

All four on recommendation.

**(1) Spine producer with a SEPARATE roll-up.** Document checks write
`Verification` rows through `VerificationStore` — reusing audit, CASCADE,
digest-only evidence and the adapter seam — but carry their own method
vocabulary and fold into a **new** `ClaimEvidence` roll-up. `IdentityAssurance`
stays strictly about identity.
*Rejected:* generalizing `AssuranceLevel` to cover documents (an org reads that
number as "this is who they say they are"; "we saw a payslip" must not raise
it). *Rejected:* a fabrication-only module (loses the consent gate, the audit
trail and the CASCADE that uploaded evidence specifically needs).

**(2) Moonlighting = declare the inert adapter + promote the signal that
already exists.** `check_timeline_overlaps` in `app/fabrication/cross_field.py`
has computed concurrent primary-role overlap since S2.2. S7.2 surfaces it as a
first-class advisory and adds an `epfo_employment` method declared
`implemented=False`.
*Rejected:* dropping moonlighting (leaves the EPFO slot undesigned).
*Rejected:* building the vendor integration now — see §3.

**(3) Candidate-plane, first-party intake.** The candidate submits their own
letter under `X-Candidate-Key`. Acting on your own data is a data-principal
right, not a disclosure (the S6.4 principle, upheld by S7.1).
*Rejected:* admin-only (the candidate never initiates). *Rejected:* both planes
(org-supplied documents *about* a candidate are third-party data under DPDP and
need their own basis — out of scope).

**(4) The org read reuses `VERIFICATION_READ`, explicitly redefined.** S7.1
scoped that purpose to *identity assurance*; S7.2 widens it to *verification
disclosure* generally. This is acceptable **only because the purpose is days old
with zero real grants** — the same test S7.1 applied when it refused to reuse
`ledger_read` (candidates had already signed that one). The widening is dated
and recorded in `LEDGER.md`. **This window closes:** once real grants exist, a
further widening requires a new purpose.
*Rejected:* a fifth `CLAIM_READ` purpose (taxonomy growth plus a second grant
orgs must collect, for a distinction no candidate has yet relied on).

## 3. The EPFO/UAN question — ANSWERED (do not re-litigate)

Open since the 2026-07-26 gap analysis (§8) and carried as a blocker into this
spec. Resolved 2026-07-31.

**Finding.** EPFO/UAN-based dual-employment verification *is* lawful in India,
but access is mediated: it runs through **authorized BGV aggregators** holding
approved EPFO channels (AuthBridge and peers), not through any public EPFO API a
platform could call directly. Under the DPDP Rules 2025 the candidate's consent
must be explicit, itemized, unbundled, and name the source (EPFO), the purpose,
and the retention window; withdrawal must purge the data and log the event.
Re-checking an existing employee needs fresh consent for that instance.

**Consequence.** The blocker was never really the legality — it is the
**commercial vendor relationship**, which veritas does not have. That places an
EPFO pull in precisely the category S7.1 built for `government_id`: a
`third_party` adapter the seam declares and gates but cannot implement offline.

**Therefore:** S7.2 ships **first-party forensics only**. `epfo_employment` is
declared with `third_party=True`, `implemented=False`, `self_service=True`,
level `ClaimStrength.THIRD_PARTY_VERIFIED`, gated by `IDENTITY_VERIFY`. It is
refused with 422 and lifts nothing — asserted by a test mirroring
`test_government_id_stays_inert_in_the_spine_even_with_consent`. When a vendor
is contracted, the work is one adapter and flipping `implemented`, not a
migration and a consent retrofit.

Sources consulted: vendor/industry guidance on EPFO-UAN verification and DPDP
consent mechanics (digiverifier, AuthBridge, pietos, mploychek). These are
secondary sources; the conclusion S7.2 relies on — *no direct third-party EPFO
API, therefore not buildable offline* — does not depend on the finer legal
points.

## 4. Non-negotiables inherited (do not relitigate)

- TDD, fully offline; `pytest -q` green before merge.
- Advisory only. A document finding never auto-rejects and never touches depth
  scoring, ranking, or matching.
- DPDP first-party only; consent objects + delete paths on new state.
- Config in `config.yaml`, secrets in `.env` (`DEE_*`).
- SQLAlchemy + Alembic on SQLite, Postgres-shaped.
- **From the S7.1 review:** the adapter seam refuses by default
  (`self_service`/`implemented`/`instant` all default False on `_Base`), gates
  live in the spine and never in an adapter, and "not challenge-based" must
  never imply "believe it".

## 5. DPDP posture — the important one

S7.1's rule was *no column can hold an artifact*. S7.2 is where that rule earns
its keep, because for the first time a real document is on the wire.

**The document is never stored.** The route accepts base64, parses it in memory
via the existing `app/core/pdf.py` helper, computes a sha256 → `evidence_digest`,
derives findings, and discards the bytes. Nothing else survives the request.

**`details` is codes, not content.** Finding codes, booleans, and coarse buckets
only. Explicitly forbidden, and asserted by tests:

- raw document text or excerpts;
- **salary amounts** from a payslip — comp has its own consented, k-anonymised
  path (S5.2), and a payslip must not become a back door into it;
- **UAN / PF / PAN numbers** — presence may be recorded as a boolean, never the
  identifier itself;
- any contact detail not already hashed on the candidate row.

**Erasure.** Claim verifications are `verifications` rows, so the existing
candidate CASCADE sweeps them and the org read 404s afterward — no new erasure
path, asserted by a test.

## 6. Architecture

Three new pure modules beside `assurance.py`, no new package.

### 6.1 `schema.py` additions

```python
class VerificationSubject(StrEnum):
    IDENTITY = "identity"
    EMPLOYMENT_CLAIM = "employment_claim"

class ClaimStrength(IntEnum):          # claim ladder, NOT the identity ladder
    NONE = 0
    SELF_REPORTED = 1                  # the resume said so
    DOCUMENTED = 2                     # a document backs it, forensics clean
    CORROBORATED = 3                   # document + an independent source agrees
    THIRD_PARTY_VERIFIED = 4           # EPFO et al — declared, inert

class DocumentType(StrEnum):
    EXPERIENCE_LETTER = "experience_letter"
    PAYSLIP = "payslip"

class DocumentFinding(BaseModel):      # advisory, non-PII
    id: str                            # stable code, e.g. "issuer_domain_unknown"
    severity: str                       # info | soft | hard
    message: str                        # human-readable, no document content
    detail: dict = {}                   # coarse buckets only

class ConcurrentEmployment(BaseModel):  # advisory, derived, never stored
    periods: list[str]                  # "2023-04..2024-02" style labels
    max_overlap_months: int
    severity: str                       # info | soft
    advisory: bool = True

class ClaimEvidence(BaseModel):         # the roll-up, computed at read time
    candidate_id: str
    strength: ClaimStrength = ClaimStrength.NONE
    documents: list[DocumentType] = []
    findings: list[DocumentFinding] = []
    concurrent_employment: Optional[ConcurrentEmployment] = None
    advisory: bool = True
```

New `VerificationMethod` members: `EXPERIENCE_LETTER`, `PAYSLIP`,
`EPFO_EMPLOYMENT`. `METHOD_LEVEL` keeps mapping identity methods to
`AssuranceLevel`; a parallel `METHOD_CLAIM_STRENGTH` maps the claim methods.
`METHOD_SUBJECT` maps every method to its subject — one table, so a method
cannot be ambiguous about which ladder it feeds.

### 6.2 `documents.py` — pure forensics, no LLM

`parse_document(data: bytes, doc_type) -> ParsedDocument` (text + PDF metadata,
via `app/core/pdf.py`) and
`assess(parsed, profile, *, at) -> tuple[ClaimStrength, list[DocumentFinding]]`.

**No LLM in this sprint.** These checks are structural and arithmetic, so the
"every LLM step needs a deterministic fallback" convention is satisfied by
having no LLM at all — the S6.2/S6.3 precedent. An optional capped LLM pass over
letter phrasing is a follow-up, not this sprint.

Experience-letter checks: issuer domain / employer canonicalization against
S1.4; letter dates vs the profile's `ExperienceEntry` intervals, reusing
`cross_field`'s interval helpers so one notion of "when" exists; designation
agreement; mill markers (no signatory, no employee ID, generic phrasing).
Payslip checks: employer agreement; gross − deductions = net arithmetic; month
sequencing across several payslips; PF/UAN **presence** only.
Both: PDF metadata skew (producer tool, creation-vs-modification dates).

Findings are conservative by construction: an unknown issuer domain is `soft`,
never `hard`, because small Indian employers legitimately lack a mail domain.

### 6.3 `claims.py` — the roll-up

`compute_claim_evidence(candidate_id, verifications, *, at, concurrent=None)`,
mirroring `assurance.py`: pure, clock-injected, read-time, filters to
`subject == EMPLOYMENT_CLAIM`, strength is a `max()` over contributing rows,
expiry reuses `effective_status`.

**The invariant:** `compute_assurance` filters to `subject == IDENTITY`. A
payslip can never lift `IdentityAssurance`. This is the same failure class as
the escalation the S7.1 review closed, so it is tested at the same weight: with
a verified claim row present, identity level is still 0.

### 6.4 `moonlighting.py` — thin, read-time

`assess_concurrent_employment(profile, *, at) -> Optional[ConcurrentEmployment]`
— reuses `cross_field`'s overlap machinery, emits periods, months, and a
severity. **No new state and nothing stored**: it is derived from the profile,
so storing it would go stale exactly as a stored assurance would. Advisory, and
explicitly *not* an accusation: overlapping intervals are consulting, notice
periods, and year-only date imprecision at least as often as dual employment.

### 6.5 `models.py` + migration `0014_verification_subject`

`verifications` gains:

- `subject` — `String(24)`, NOT NULL, indexed. Existing rows backfill to
  `identity` (server_default applied then dropped, SQLite batch recreate,
  matching the 0004 precedent).
- `claim_ref` — `String(128)`, nullable: which experience claim the document
  backs (employer label + interval), so two letters for two employers do not
  collapse.

No new table. Findings live in the existing `details` JSON — advisory finding
lists are JSON elsewhere in this codebase (S2.x on `Report`), and a second table
would buy nothing. Drift / index / FK / nullability guards extended, as every
migration in this repo does.

### 6.6 `store.py` / `service.py`

`VerificationStore.create_verification` takes `subject` and `claim_ref`;
`claims_for_candidate` mirrors `assurance_for_candidate`; `claims_for_org`
mirrors `assurance_for_org` exactly — same query-time `VERIFICATION_READ`
enforcement, same audit of **every** attempt allowed or denied, action
`claim.query`.

`VerificationService.submit_document(candidate_id, doc_type, data, claim_ref)`
runs the adapter gates (the claim methods are `self_service=True`,
`implemented=True`, `instant=True` — the outcome is known the moment the
document is assessed), parses, assesses, and writes one verification. Its
strength comes from the assessment: hard findings → `FAILED`, otherwise
`VERIFIED` at `DOCUMENTED`, lifted to `CORROBORATED` when an independent source
already on file agrees (a ledger interview record or a profile-source signal for
the same employer).

A `FAILED` claim row **contributes nothing to strength** — `claims.py` folds
only `VERIFIED`, unexpired rows, reusing `effective_status`. Its findings are
still returned to the candidate (they are the reason it failed, and the
candidate is entitled to that) and it still appears in the row list. A failed
document is never an accusation and never lowers anything: strength is a
`max()` over what *is* held, so a bad submission leaves the candidate exactly
where they were.

## 7. API

### 7.1 Candidate plane (`X-Candidate-Key`)

| Route | Behaviour |
|---|---|
| `POST /portal/documents` | Body `{doc_type, content_b64, claim_ref?}`. Parses, assesses, writes one claim verification. 200 with `{verification, findings, claims}` · 400 unparseable or bad base64 · **422** oversize (`doc_max_b64_chars`) or unknown `doc_type` — matching the S6.2 LinkedIn-upload contract exactly. |
| `GET /portal/verifications` | Grows a `claims` key alongside `verifications` and `assurance`. |

`MyData` grows `claims`, as it grew `identity` in S7.1.

### 7.2 Org plane (`X-Org-Key`)

| Route | Behaviour |
|---|---|
| `GET /verification/candidates/{id}/claims` | `VERIFICATION_READ` enforced at query time, every attempt audited both ways. Returns the advisory roll-up only — never `evidence_digest`, never a finding carrying content. 403 without a grant, 404 unknown candidate. |

### 7.3 Admin plane

None. `manual_review` already covers "an operator checked something".

## 8. Config

```yaml
doc_max_b64_chars: 8000000      # ~6MB decoded, matches the resume-PDF ceiling
doc_max_pages: 20               # parse cap
doc_unknown_issuer_severity: soft
doc_metadata_skew_days: 1       # creation-vs-modification skew that is notable
moonlight_min_overlap_months: 12  # reuses the S2.2 threshold, now a knob
```

## 9. Testing (TDD-offline) + smoke

~40 new tests across `test_verification_documents.py` (pure forensics, fixture
letters/payslips built in-test), `test_verification_claims.py` (roll-up, expiry,
**the identity-isolation invariant**), `test_verification_moonlighting.py`,
`test_verification_claim_api.py`, `test_verification_claim_org_api.py`, plus
migration-guard and erasure additions.

Tests that must exist, because they encode what this sprint could get wrong:

1. A verified claim row leaves `IdentityAssurance.level` at 0.
2. `epfo_employment` with an active `IDENTITY_VERIFY` grant → 422, strength
   unchanged.
3. No stored row, in any column, contains document text, a salary amount, or a
   UAN.
4. Another candidate's document submission cannot reference or lift this
   candidate's claims (subject resolved from the key, never a body param).
5. DPDP erasure sweeps claim rows; the org read then 404s.

`scripts/smoke_s72.py` (uvicorn, key-less, no network): create candidate →
claims empty → submit a clean experience letter → `DOCUMENTED` → submit a
mismatched-dates letter → findings, strength not lifted → submit a payslip whose
arithmetic is inconsistent → hard finding → identity level **still 0** →
`epfo_employment` after self-granting `identity_verify` → 422 → org claims read
403 → grant `verification_read` → 200 (no evidence internals) → revoke → 403 →
concurrent-employment advisory visible on overlapping resume intervals →
`DELETE /portal/me` → org read 404.

## 10. Non-goals / follow-ups

- No BGV vendor, no EPFO pull, no UAN lookup (§3).
- No certificate/degree forensics (a different issuer model — later sprint).
- No LLM pass over document phrasing (follow-up).
- No org-submitted documents (third-party data, needs its own basis).
- No feature-store consumption; claim strength is not a ranking feature.
- No effect on depth scoring, `fabrication_risk` fusion, matching, or ranking.
  Document findings are advisory and stand beside `fabrication_risk`; wiring
  them into that fusion is a deliberate follow-up, not this sprint.

## 11. Definition of done

`pytest -q` green (887 → ~927); pyflakes clean on every new and modified file;
`scripts/smoke_s72.py` exit 0 with every check OK; migration `0014` with guards
extended; `VERIFICATION.md` extended with a claims section and `LEDGER.md`
carrying the dated `VERIFICATION_READ` redefinition; `docs/ROADMAP.md` updated;
whole-branch review before merge — reading the code, not the branch's own
account of it.
