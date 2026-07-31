# Veritas Roadmap — living plan (update every session)

> **New chat? Start here.** Read this file top to bottom, then open the spec:
> `docs/superpowers/specs/2026-07-06-veritas-talent-platform-design.md`.
> Work happens sprint by sprint: each sprint gets a spec/plan under
> `docs/superpowers/`, is built TDD-offline, and ends with `pytest -q` green
> plus a local smoke run. Update the status board + "Current state" section
> below before ending any session.

## ▶ Current state

- **Current sprint:** **PI-7 OPEN — S7.1 (Verification spine + consent-first
  identity) COMPLETE and MERGED to main — 784→887 green, smoke_s71 19/19 OK
  exit 0, key-less — no LLM, no network.** The whole-branch review (inline; the
  harness in these sessions forbids spawning agents unless asked) found **two
  Critical privilege escalations, both reproduced over HTTP with nothing but a
  candidate's own key, both now closed and covered by tests + smoke checks**:
  (1) `POST /portal/verifications` accepted **any** `VerificationMethod`, so a
  candidate could POST `manual_review` and self-award **L3 REVIEWED** — a level
  whose entire meaning is "an operator looked"; (2) worse, `government_id` was
  reachable for **L4**: the candidate self-grants `IDENTITY_VERIFY` from the
  portal (S6.4 first-party consent, working as designed), the spine's
  third-party gate passes, and because **the spine performs verifications itself
  and never calls into an adapter**, `GovernmentIdAdapter.start`'s
  `NotImplementedError` could never fire — the route's
  `except NotImplementedError → 422` was dead code and "declared but inert" was
  false as shipped. The root cause was shared and structural: `start()` treated
  **"not challenge_based" as "complete it now, VERIFIED"** — a fail-open default
  — and the tests proved the third-party gate only against a
  `_FakeThirdPartyAdapter` while the real, routable method went untested
  end-to-end. **Fix (in the spine, where the other gates live):** the adapter
  seam gained `self_service`/`implemented`/`instant`, **all defaulting to the
  REFUSING answer on `_Base`** so a new adapter is inert until it declares what
  it is; `start()` is now explicitly the candidate-initiated entry point and
  checks `self_service` → `implemented` → third-party consent → destination
  binding (**consent is necessary, never sufficient** — the candidate can grant
  it to themselves), and refuses to mark anything VERIFIED on request unless the
  adapter declares `instant` (only `self_attested` does). `manual_review` is
  `self_service=False` → **403**; `government_id` is `implemented=False` →
  **422**. Two further review fixes: the **OTP resend cooldown and challenge
  supersession were scoped to one verification row, which rate-limited nothing**
  (the plane mints a fresh verification per start, so a stolen key bought
  unlimited codes and unlimited guess-batches against a 6-digit code) — now
  scoped to **candidate + channel**, plus `hmac.compare_digest`; and an
  operator-recorded manual review audited as `actor_type="candidate"`, i.e. the
  candidate's own DPDP access log told them **they** did what an operator did —
  now `"system"`. 10 review tests added (877→887). Delivered a new pure package
  `app/verification/` (peer of `app/portal/`/`app/profile_sources/`): `schema.py`
  (`AssuranceLevel` **IntEnum** 0–4 so "highest level held" is a `max()`;
  `VerificationMethod`/`VerificationStatus`; `METHOD_LEVEL`; `Verification`;
  `IdentityAssurance`), `assurance.py` (pure clock-injected `is_expired`/
  `effective_status`/`compute_assurance` — **expiry is computed at read time**,
  never written by a job, because no scheduler exists and a stored `expired`
  would be a lie nobody corrects; lapsed methods are reported separately so the
  portal can prompt a re-verify instead of showing an unexplained downgrade),
  `otp.py` (pure code-gen/hash/TTL/attempt/cooldown arithmetic under an injected
  RNG + `Notifier` protocol with a `NullNotifier` that logs **neither** the code
  nor the destination), `methods.py` (adapter seam + registry), `models.py`,
  `store.py`, `service.py`. Migration `0013_identity_verification` — two tables,
  both candidate CASCADE: `verifications` (durable outcome) and
  `verification_challenges` (short-lived secret material, deliberately separate);
  drift/index/FK/nullability guards extended (the nullability guard **caught a
  real drift** during the build — `details` was `nullable=True` in the migration
  vs `Mapped[dict]` NOT NULL in the ORM; migration corrected). **Ladder shipped:**
  L1 `self_attested` · L2 `otp_email`/`otp_phone` (contact-control) · L3
  `manual_review` (**admin plane only** — `self_service=False`) · L4
  `government_id` **declared but inert** — inertness is `implemented=False`
  **enforced by the spine**; the adapter's `NotImplementedError` is only a
  backstop, since the spine never calls an adapter to do the work (precisely how
  the escalation above got in). **Two new `ConsentPurpose`
  members** (first taxonomy addition since S3.1): `IDENTITY_VERIFY` (gates any
  `third_party` adapter — enforced in the SPINE, not in adapters, and proven by a
  `_FakeThirdPartyAdapter` in tests) and `VERIFICATION_READ` (org disclosure,
  query-time enforced + **every attempt audited allowed or denied**, mirroring
  `query_records_for_org`). Six endpoints across three planes: candidate
  (`POST /portal/verifications`, `POST /portal/verifications/{id}/confirm`,
  `GET /portal/verifications`; `MyData` gained `identity`), org
  (`GET /verification/candidates/{id}/assurance`), admin
  (`POST /candidates/{id}/verifications/manual-review`). `verif_*` config knobs +
  `ret_verification_days`. `VERIFICATION.md` written. **Design invariants:**
  (a) **the "never store a document" rule is STRUCTURAL** — neither table has any
  column able to hold an artifact, the sole evidence field is a sha256
  `evidence_digest`, so a future govt-ID adapter cannot persist one without a
  migration a reviewer would see (asserted by tests in both schema and models);
  (b) **first-party self-service needs no grant** — the S6.4 principle holds,
  acting on your own data is a data-principal right, not a disclosure;
  (c) **destination binding** — the `candidates` table stores only
  `email_hash`/`phone_hash`, so the candidate supplies the OTP destination and
  the spine normalizes+hashes it and requires a match against the hash on file
  (proves they know the contact, works regardless of what extraction retained,
  and the raw value stays transient — only the hash is written);
  (d) **cross-candidate isolation is structural** — every candidate-plane handler
  resolves `candidate_id` from the key, never a path/body param; another
  candidate's verification is an indistinguishable 404. **Challenge hygiene is a
  deliberate exception to the deferred PI-8 sweep:** consumed/superseded OTP rows
  are actually DELETED on paths that already run — that is short-TTL secret
  material, not a retention policy (supersession + cooldown scoped **per
  candidate+channel**, post-review). 103 new tests (**784→887**, `pytest -q`
  green). Smoke `scripts/smoke_s71.py` (uvicorn, key-less) **19/19 OK** exit 0:
  candidate starts at level 0 → self-attest → L1 → OTP to a contact NOT on file
  400 → OTP to the real contact → wrong code 400 → correct code → L2 →
  **candidate self-awarding `manual_review` 403 → candidate self-grants
  `identity_verify` then `government_id` 422 → level still 2** → org read 403 →
  grant `verification_read` → 200 (and no evidence internals in the payload) →
  revoke → 403 → admin manual review → L3 → `DELETE /portal/me` → org read 404.
  **PI-6 (candidate side & intake) remains COMPLETE and is merged to main**
  (`814e845`, 784 green) — S6.1 GitHub · S6.2 LinkedIn export · S6.3
  normalization curation loop · S6.4 candidate auth + DPDP portal. Historical
  PI-6/PI-5 detail follows below.
- **Prior sprint detail:** **S6.4 (Candidate auth + DPDP portal)
  BUILT on branch `s64-candidate-auth-dpdp-portal` — 752→784 green, smoke_s64
  10/10 OK, key-less — no LLM, no network, no new `ConsentPurpose`; PENDING
  final whole-branch review + merge (not yet on main).** Delivered: migration
  `0012_candidate_credentials` (candidate CASCADE FK, unique on
  `candidate_id`; drift/index/FK/nullability guards extended);
  `CandidateStore.issue_access_key`/`authenticate_candidate` (mint/rotate a
  sha256-hashed opaque key, mirrors org API keys); `require_candidate`
  dependency + a new dependency-free `candidate_router` (peer of `router`/
  `org_router`); admin-plane `POST /candidates/{id}/auth-key` (mint, returned
  once, 200/404/401); a new pure package `app/portal/` (`schema.py` —
  `MyData`/`AccessLogEntry`/`ConsentView`/`ReportRef`/`RetentionWindow`+
  `RetentionPolicy`; `retention.py` — pure `retained_until` +
  `build_retention_policy`; `service.py` — `PortalService` composing
  `CandidateStore`+`LedgerStore`+`ProfileSourceService`+`ReportStore`, owns no
  tables); `Services.portal` wired cycle-safe; `LedgerStore.consents_for_candidate`
  + `get_grant` (small raw-read additions); config knobs
  `candidate_access_key_bytes` (32) + six `ret_*_days` (resumes 1095,
  interview records/coding rounds/observed offers 1825, profile sources 1095,
  audit log 2555). Six candidate-plane endpoints (`X-Candidate-Key`):
  `GET /portal/me` (access), `GET /portal/access-log` (transparency,
  newest-first, includes platform-internal actions),
  `GET /portal/consents` + `POST /portal/consents` +
  `POST /portal/consents/{id}/revoke` (consent control, ownership-enforced —
  unknown-or-not-owned both 404, no probing), `DELETE /portal/me` (erasure,
  reuses the existing hard-delete path; key 401s after). **Design invariant:
  no new `ConsentPurpose`** — self-access is the data-principal right itself,
  not an org-consent-gated disclosure, so `require_candidate` alone gates
  every route; cross-candidate isolation is structural (every handler
  resolves `candidate_id` from the key, never a path/body param). **Two
  deferred decisions (confirmed with user):** (a) `/portal/me` lists reports
  by existence + timestamp only (`ReportRef`) — depth `Report` internals
  (fabrication_risk, verdicts) are not disclosed to the subject in v0; (b)
  the access-log includes platform-internal actions (e.g.
  `feature.materialize`), not just org disclosures. Retention posture is
  surfaced (`RetentionPolicy.sweep_active=False` always) — the mechanical
  purge job is deferred to PI-8 (no scheduler exists yet). `PORTAL.md`
  written (peer of `LEDGER.md`/`DASHBOARD.md`). 32 new tests (752→784,
  `pytest -q` green). Smoke `scripts/smoke_s64.py` (uvicorn, key-less) 10/10
  OK exit 0 (the smoke commit's subject stales-reads "(12/12)" — the correct,
  verified count is **10/10**): create candidate → admin mints a key →
  `GET /portal/me` shows profile/resumes/retention → org submits + queries an
  interview record (consented) → `GET /portal/access-log` shows it with the
  org's name resolved → first-party `POST /portal/consents` grant →
  `GET /portal/consents` active → revoke → state `revoked` → wrong/absent key
  401 → a second candidate's key cannot see or revoke candidate 1's data
  (404, untouched) → `DELETE /portal/me` erases; key then 401s; admin
  `GET /candidates/{id}` 404. Executed subagent-driven (fresh implementer +
  review per task across 10 build tasks + this closeout); two plan-text
  inaccuracies self-corrected during the build (Task-8 route-existence test
  ordering; Task-9 a shared-email test helper collapsing two candidates via
  the S1.1 dedup path). Commits `f3646ca..4bdbdb6` (Tasks 1–10; spec
  `a0450d5`, plan `d2737f6` precede). Deferred minors carried (all DEFER,
  none merge-blocking): unused `datetime` imports in
  `tests/test_ledger_consents_for_candidate.py` (F401); two API test helpers
  use `client.__enter__()` without `__exit__()` (thread-leak, no correctness
  impact); the smoke commit subject's stale "(12/12)"; the `no_key_401` smoke
  check exercises absent-key only (wrong-key is covered by a unit test).
  **PI-8 follow-ups (spec §9):** mechanical retention sweep; real candidate
  registration (password/OTP/session); exposing depth-`Report` internals to
  the candidate; DPDP correction/rectification right; grievance/DPO contact
  endpoint; multi-credential/device sessions. **PI-6 status: COMPLETE** — S6.1
  GitHub [done] · S6.2 LinkedIn export [done] · S6.3 normalization curation
  loop [done] · **S6.4 candidate auth + DPDP portal [done, this sprint —
  pending final review + merge]**. S6.3 (normalization curation loop) remains
  COMPLETE — historical detail below and in the session log. S6.2 (LinkedIn
  export parsing) remains COMPLETE — historical detail below and in the
  session log. S6.1 (GitHub-as-signal) remains COMPLETE — historical detail
  below and in the session log.
  PI-5 (demand side) remains COMPLETE (S5.1–S5.3); historical S5.3 detail follows.
  S5.3 added a pure `app/dashboard/` composition layer (no tables/migration/LLM/new
  consent purpose) exposing three org-plane read-models: `GET /dashboard/overview`,
  `GET /jobs/{id}/board` (requisition + comp benchmark + top-N match), and
  `GET /candidates/{id}/card` (consent-gated per-section drill-in, 200 with per-section
  status, audit-by-reuse). API-first JSON only; no candidate PII, no depth-report
  exposure. Advisory.
- **Next action:** **S7.1 merged; S7.2 SPEC + PLAN WRITTEN** (spec
  `docs/superpowers/specs/2026-07-31-s72-document-forensics-design.md` `7465e4d`,
  plan `docs/superpowers/plans/2026-07-31-s72-document-forensics.md` `47737a4`,
  branch `s72-document-forensics`) — **next is the TDD build, Task 1 of 12.**
  Task order puts the isolation invariant first: contracts + subject
  discriminator (1–3), forensics (4–7), storage + migration `0014` (8–9),
  orchestration + routes (10–11), erasure/smoke/docs (12).
  Four scope decisions taken with user, all on recommendation: (1) spine
  producer with a **separate `ClaimEvidence` roll-up** — a payslip must never
  lift `IdentityAssurance` (same failure class as the S7.1 escalation);
  (2) moonlighting = declare the inert `epfo_employment` adapter + **promote the
  concurrent-employment overlap `check_timeline_overlaps` has computed since
  S2.2** (it was already built — S7.2 surfaces it, and the advisory is derived
  read-time, never stored); (3) candidate-plane first-party intake;
  (4) reuse `VERIFICATION_READ`, **explicitly redefined and dated** while it
  still has zero real grants — a window that closes once orgs hold grants.
  **The EPFO/UAN research item, open since the 2026-07-26 gap analysis, is
  ANSWERED in spec §3:** the checks are lawful in India but run only through
  **authorized BGV aggregators** with approved EPFO channels — no direct
  third-party API exists — so the blocker is the vendor relationship, not the
  law, which puts an EPFO pull in exactly the `government_id` category
  (declared, consent-gated, `implemented=False`). No LLM in S7.2. The original
  S7.2 framing follows.
  Shape/plan **S7.2 (document forensics + moonlighting advisory)** as the
  **second producer on the S7.1 spine** — the S6.1→S6.2 pattern: it writes
  `Verification` outcomes through `VerificationStore`, reusing the adapter seam,
  the audit trail, and the CASCADE, adding no new consent purpose unless a
  third-party pull (e.g. EPFO) is in scope. Per gap-analysis §5B, moonlighting
  must be advisory and derived from **first-party timeline evidence only**
  unless a candidate-consented pull is legally cleared (EPFO/UAN legality is an
  open §8 research item — resolve it in the S7.2 spec, and if murky, first-party
  forensics only). S7.3 (AI interview delivery v0) follows and reads
  `IdentityAssurance` for proxy-detection hooks. **S7.1 follow-ups (deferred, not
  merge-blocking):** real OTP delivery (no email/SMS provider in this repo —
  `NullNotifier` discards); the mechanical retention sweep (PI-8, unchanged);
  assurance as a feature-store feature once its predictive value is measurable;
  a real govt-ID adapter needs vendor selection **and** a legal review of
  DigiLocker API terms (when it lands, flip `implemented=True` — the seam's
  refusing defaults are what keep it inert until then). **Review minors carried
  (DEFER, none merge-blocking):** an abandoned OTP start leaves a `pending`
  verification row behind when its challenge is superseded (never contributes to
  assurance — folds into the PI-8 retention sweep); OTP codes are salted with
  `contact_hash_salt` rather than a dedicated secret; `Notifier.send` takes the
  raw destination (unused by `NullNotifier`, needed by any real provider). S6.3 follow-ups
  to fold in later: employers/institutions curation (needs an unmapped
  marker on `canonicalize_*`), resume-extraction capture (same `canonical=None`
  marker on `SkillClaim`), retroactive re-normalization of already-stored signals,
  a decision-history/audit table. S6.4 follow-ups (PI-8, spec §9): mechanical
  retention sweep; real candidate registration; exposing depth-`Report`
  internals to the candidate; DPDP correction/rectification right;
  grievance/DPO contact endpoint; multi-credential/device sessions. Deferred
  S6.1/S6.2 follow-ups still open:
  resume-claimed-vs-source corroboration (cross-adapter, both directions —
  narrower than LinkedIn's own within-export corroboration), feature-store
  consumption of the signal, flywheel wiring (all documented in
  `PROFILE_SOURCES.md`). **PI-5 (demand side) is COMPLETE
  (S5.1–S5.3).** Historical
  S5.2 detail follows. S5.2 is
  DONE (merged to main, 653 green; whole-branch self-review clean — no
  Critical/Important; one Minor closed: added a `comp_bands_path` override-loader
  test). S5.2 delivered (spec `2026-07-28-s52-comp-intelligence-design.md`, plan
  `2026-07-28-s52-comp-intelligence.md`, 10 TDD tasks): new pure `app/comp/` package
  (`schema.py` contracts + `SeniorityBand`/role-family vocab; `bands.py` illustrative
  license-clean static seed table + config-path override + deterministic
  role/seniority/tier resolvers; `estimate.py` reputation.py-style shrinkage blend on
  a **total-CTC basis** with k-anonymity floor + saturating confidence + benchmark;
  `service.py` `CompService` reading offers via `LedgerStore`), consent-gated
  `observed_offers` ledger table (peer of coding_round_results; `ObservedOffer`/
  `ObservedOfferPoint` contracts, `ObservedOfferRow`, migration `0009`
  candidate+org+consent CASCADE, drift/index/FK/nullability guards extended),
  `LedgerStore.submit_observed_offer` (`ledger_write`-gated, audited `offer.submit`)
  + `observed_offers_for_comp` (**de-identified**, revocation-respecting, audited
  `comp.aggregate` with `candidate_id=None`), `Services.comp` wiring (cycle-safe),
  org-plane endpoints `POST /ledger/offers` + `POST /comp/estimate` +
  `GET /jobs/{id}/comp` (403/404/400/401). **Design decisions (delegated to
  recommendation):** capture+blend (offers get a first-class CTC field) · estimate +
  requisition benchmark surface (no comp-fit match term — no candidate expected-CTC
  yet) · observed_offers lives in the ledger (layering: ledger never imports comp) ·
  cross-candidate aggregation consent basis = revocation-respecting stamped grant +
  k-anonymity floor + de-identified aggregate, **no new consent purpose** (documented
  DPDP residual). `comp_*` config knobs. No LLM. `COMP.md` written. 29 new tests
  (623→652, `pytest -q` green). Smoke `scripts/smoke_s52.py` (uvicorn + HTTP) 13/13
  OK exit 0: static-only floor → 6 offers → observed blend (p50 up, confidence up) →
  benchmark below/at → different role < k stays static → revoke drops one (6→5) →
  DPDP erase tips below k (static-only) → cross-org 404. **PENDING:** final
  whole-branch review + merge. S5.1 delivered (spec
  `2026-07-27-s51-job-requisition-matching-design.md`, plan
  `2026-07-27-s51-job-requisition-matching.md`, 10 TDD tasks): new `app/matching/`
  package — pure contracts `schema.py` (`JobRequisitionInput`/`JobRequisition`/
  `CompBand`/`MatchWeights`/`SkillMatchDetail`/`MatchedCandidate`/`MatchResult`),
  pure engine `match.py` (`skill_coverage`, `location_fit`, `compile_ranking`/
  `compile_filters`, and `match` — injects two synthetic values
  `match.skill_coverage`/`match.location_fit` into a copy of each FeatureVector and
  reuses `ranking.score()`), ORM `JobRequisitionRow` + migration `0008` (org-owned,
  CASCADE on org, **NOT candidate-linked** → survives candidate erasure), `JobStore`
  (org-scoped CRUD with canonical-skill normalization + audited
  `requisition.create`/`update`; `run_match` reads the pool + point-in-time profiles
  at one `as_of`, ranks, and audits every **returned** candidate as `match.surface`
  in the shared `audit_log` — candidate-linked + CASCADE), `Services.jobs` wiring,
  org-plane endpoints `POST/GET/PATCH /jobs` + `POST /jobs/{id}/match`
  (`MatchResult{advisory=True}`; cross-org 404, empty pool 422). **Design decisions
  (delegated to recommendation):** org plane · compile-to-ranking + skill-coverage ·
  comp band **metadata-only** (not matched; S5.2 consumes it, no follow-up
  migration) · **audit-every-match, no new consent gate** (pool already
  consent-masked at S4.2). `min_years/degree/notice` are **soft** (select the
  dimension, value is not a cutoff); the **only** hard gate is opt-in
  `min_skill_coverage`. `match_*` config knobs (skill weight dominant). No LLM.
  `MATCHING.md` written (peer of LEDGER/FEATURES). Whole-branch self-review: one
  hardening fix (skill canonicalization keeps punctuation asks like "C#"/"C++",
  and an all-blank skill set now raises → 400, never a reconstruct-time 500).
  39 new tests (584→623, `pytest -q` green). Smoke `scripts/smoke_s51.py`
  (uvicorn + HTTP) 11/11 OK exit 0:
  ranked strong→weak→other by skill coverage (advisory — zero-coverage still
  appears), `min_skill_coverage=0.75` gates to strong only, DPDP erase drops the
  candidate from the pool AND sweeps its `match.surface` audit rows.
- **Long-range planning:** the full Mercor-for-India vision audit lives in
  `docs/superpowers/specs/2026-07-26-veritas-vision-gap-analysis.md` — capability
  gap map (identity/KYC, document forensics, AI interviews, job/matching schema,
  candidate DPDP portal, comp intelligence) and the proposed PI-5..PI-8 shape
  that supersedes the old flat PI-5 backlog. Consult it whenever a PI completes
  and the next needs shaping; it never overrides the "Next action" above.
- **Open residuals (carried, all DEFER — none merge-blocking; see
  `.superpowers/sdd/progress.md`):** from S3.2 — `append_event` is ownership-only
  and intentionally inherits the submit-time `ledger_write` grant (documented in
  LEDGER.md — decide whether to re-gate on live consent); `create_organization`'s
  broad `except IntegrityError` maps any violation to "name exists" (only `name`
  is insert-reachable-unique today); `consent.py`/`store.py` module docstrings
  still carry "(S3.1)" framing; `revoke_consent` endpoint returns 200
  `{revoked:false}` for an unknown consent_id (no 404); 0004 downgrade (SQLite
  batch recreate) is untested. **S3.3 adds no new residuals.**
- **Last session (2026-07-25):** S3.3 executed inline TDD-offline on branch
  `s33-coding-round-results` (6 tasks). Delivered per plan: a standalone
  `coding_round_results` table (peer of `interview_records`, NOT an overload of
  it) with CASCADE FKs to candidates/organizations/consent_grants; contracts
  `CodingPlatform` StrEnum (hackerrank/codility/leetcode/codesignal/hackerearth/
  internal/other) + `CodingRoundResult` (platform, platform_name?, assessment_name?,
  score, max_score?, percentile? [0–100], problem_tags[], taken_at, raw{}) with
  pydantic bounds as data hygiene only — NO scoring; migration
  `0005_coding_round_results` (+ drift/index/FK-ondelete/nullability guards
  extended to the new table); store methods mirroring interview records —
  `submit_coding_round` (`ledger_write`-gated → ConsentError, stamps consent_id,
  audits `coding_round.submit` in-txn), `query_coding_rounds_for_org` (query-time
  `ledger_read` enforcement, audits every attempt allowed/denied as
  `coding_round.query`), `coding_rounds_for_candidate` (raw ungated read for
  PI-4); two org-plane endpoints (`POST /ledger/coding-rounds`,
  `GET /ledger/candidates/{id}/coding-rounds`) → 403/404/401/422; LEDGER.md S3.3
  section. **Consent reused** (`ledger_write`/`ledger_read`) — no new taxonomy.
  No new config knob, no LLM, no scoring. 20 new tests (422→442, `pytest -q`
  green). Smoke `scripts/smoke_s33.py` (uvicorn HTTP) 7/7 OK exit 0: submit-403
  → grant-write → submit → query-403 → grant-read → query-200 → DPDP-erase →
  query-404 (run happened to exercise the LIVE LLM extraction path too). Merged
  to main (fast-forward from 4f63cdc), 442 green on main, branch deleted. S3.3
  COMPLETE. Next: S3.4 plan (cross-company reputation).
- **Prior session (2026-07-22):** S3.2 executed subagent-driven, 11 tasks +
  whole-branch review, branch `s32-ledger-apis`. Delivered: two HTTP auth
  planes over `LedgerStore` — ADMIN plane (`X-API-Key` on `router`: org
  lifecycle + consent grant/revoke/status) and ORG plane (`X-Org-Key` → one
  org via `authenticate_org` on a dependency-free `org_router`: record submit
  [write-consent gated], event append [ownership-enforced], and
  `GET /ledger/candidates/{id}/records` with **query-time `ledger_read`
  enforcement + audit of every read attempt, allowed or denied, in-txn**).
  Org API keys (sha256-hashed, rotatable; migration `0004_org_api_keys` +
  unique index) with `ledger_api_key_bytes` knob (default 32, ge=16). All four
  S3.1 residuals closed: deterministic authorizing-grant selection
  (org-specific ▸ newest ▸ lowest id), `consent_status` 404-vs-403 shape,
  `create_organization` IntegrityError→ValueError (no TOCTOU), drift guard
  extended to indexes/FK-ondelete/nullability. `Services.ledger` injected
  (shares the candidate DB). 29 new tests (393→422). Smoke
  `scripts/smoke_s32.py` (uvicorn HTTP) 9/9 OK exit 0: admin gate → org+key →
  submit-403-without-consent → grant → submit → event → query-403-without-read
  → grant read → query 200 → revoke → query 403 → DPDP erase → query 404. Per
  task: fresh implementer + spec/quality review; final whole-branch review
  (opus) Ready-to-merge Yes, no Critical/Important code defects, all 13
  accumulated Minors DEFER; two recommended doc notes added (event-append
  grant inheritance, cross-org read blast radius). Merged to main
  (fast-forward 7a9fdcf→a948401), 422 green on main, branch deleted. S3.2
  COMPLETE. Next: S3.3 plan.
- **Prior session (2026-07-20):** S3.1 executed subagent-driven, 7 tasks,
  branch `s31-ledger-consent`. Delivered: `app/ledger/` package (Pydantic
  contracts + StrEnum taxonomies, pure clock-free consent logic in
  `consent.py`, ORM rows on the shared Base, migration
  `0003_evaluation_ledger` with CASCADE FKs), `LedgerStore` (organizations
  CRUD; grant/revoke/status consent; `submit_interview_record` gated by
  `ConsentError` and stamped with the authorizing grant; `append_event`;
  `records_for_candidate`/`events_for_record`/`audit_for_candidate`; every
  mutation audited in the same transaction), config knob
  `ledger_consent_default_ttl_days` (365), DPDP erasure cascades ledger rows
  via the migration's CASCADE FKs while organizations survive, `LEDGER.md`.
  42 new tests (350→392). Two deviations from plan: (a) migration 0003
  landed in Task 3 rather than later, because the metadata-wide drift guard
  requires it once ledger models are imported; (b) store converters
  normalize datetimes via `as_utc` because SQLite refetch returns naive
  datetimes and pydantic equality broke — the plan's converter code was
  fixed accordingly. Smoke `scripts/smoke_s31.py` 10/10 OK key-less
  (heuristic extraction), exit 0. Final whole-branch review: Ready to merge;
  its one Important finding fixed in 4dd09d0 (caller-supplied non-UTC
  datetimes now coerced via `as_utc` at write — SQLite drops tzinfo, so an
  IST revocation would otherwise land 5.5h late = fail-open window once
  S3.2 accepts API datetimes; + org-delete cascade documented, TTL knob
  ge=1). 393 tests. Merged to main (fast-forward to 4dd09d0), branch
  deleted. S3.1 COMPLETE. Next: S3.2 plan.
- **Prior session (2026-07-18):** S2.4 done on branch `s24-fabrication-risk`
  — PI-2 COMPLETE. Unified advisory fabrication_risk: pure fusion in
  `app/fabrication/risk.py` (band→risk code constants; 0.7·weighted-mean +
  0.3·max blend; coverage confidence so single-subsystem fusion never
  asserts; ELEVATED needs ≥2 flags, MODERATE needs a flag or ≥2 non-clean
  — the latter gate added mid-session after the live smoke caught a genuine
  resume banding moderate off one soft LLM signal), fused in the scoring
  node (depth/verdicts provably untouched), `Report.fabrication_risk` +
  moderate/elevated summary note + flywheel `record_type:
  "fabrication_risk"`, config `fr_*`. 350 tests green; smoke
  `scripts/smoke_s24.py` 10/10 key-less AND live.

## Status board

Legend: `[ ]` not started · `[~]` in progress · `[x]` done

```
VERITAS — TALENT INTELLIGENCE PLATFORM  (Indian-market Mercor, trust layer first)
│
├── PI-1  CANDIDATE DATA BACKBONE
│   ├── [x] S1.1  Prod-grade extraction schema + extractor
│   │            CandidateProfile: identity, contact(hashed), education[],
│   │            experience[], skills[], projects[], certifications[], links[];
│   │            per-field confidence + source-span provenance;
│   │            LLM extraction + deterministic fallback
│   ├── [x] S1.2  Candidate store — SQLAlchemy + Alembic on SQLite (PG-shaped);
│   │            candidates / resumes(versioned) / extractions;
│   │            identity resolution via email+phone hash dedup
│   ├── [x] S1.3  API + engine wiring — POST /candidates (upload → extract →
│   │            store → auto depth-eval); reports linked to candidate_id
│   └── [x] S1.4  India normalization — skill taxonomy, degree/CGPA normalizer,
│                institution + employer canonicalization, city/notice-period
│
├── PI-2  FABRICATION DEFENSE 2.0
│   ├── [x] S2.1  AI-generated-resume signals — ai_signals node after ingest
│   │            (deterministic stylometry ⊕ capped LLM), advisory band on Report
│   ├── [x] S2.2  Cross-field forensics — cross_field node (deterministic
│   │            timeline/coherence checks over the extracted profile),
│   │            advisory findings on Report
│   ├── [x] S2.3  Resume-farm detection — MinHash near-duplicates across
│   │            candidates (resume_fingerprints table, API-layer detection,
│   │            advisory Report.resume_farm)
│   └── [x] S2.4  Unified fabrication_risk score fused into calibration +
│                Report; still advisory, never auto-reject
│
├── PI-3  EVALUATION LEDGER (cross-company)                         [COMPLETE]
│   ├── [x] S3.1  Ledger schema + DPDP consent model — organizations,
│   │            interview_records, evaluation_events, consent_grants
│   │            (purpose-scoped, revocable, audited)
│   ├── [x] S3.2  Ledger APIs — submit/query with consent enforced at query
│   │            time; org-scoped API keys; audit trail
│   ├── [x] S3.3  Coding-round results — schema + ingest ONLY (far point):
│   │            platform, problem tags, score, percentile
│   └── [x] S3.4  Cross-company reputation — Bayesian aggregation with
│                recency decay + per-org reliability weight
│
├── PI-4  ML FEATURE STORE & RANKING                               [COMPLETE]
│   ├── [x] S4.1  Feature registry (versioned definitions over candidate +
│   │            eval + ledger data)
│   ├── [x] S4.2  Materialization → wide ml_features table + CSV/parquet
│   │            export; point-in-time correct (no label leakage)
│   ├── [x] S4.3  Talent search/ranking API (filters + composite score)
│   └── [x] S4.4  Training-set export — features ⋈ outcomes (flywheel+ledger)
│
├── PI-5  DEMAND SIDE                                         [COMPLETE]
│   ├── [x] S5.1  Job/requisition schema + role-conditioned match-ranking
│   │            (org-plane; compile-to-ranking + skill-coverage; comp band
│   │            metadata-only; audit-every-match, no new consent gate)
│   ├── [x] S5.2  Comp intelligence v0 (static bands + ledger-observed offers,
│   │            advisory) — consumes S5.1's stored comp_band
│   └── [x] S5.3  Thin employer dashboard (read-only over search/reports)
│            org-plane read-models: /dashboard/overview + /jobs/{id}/board +
│            /candidates/{id}/card; lean board + consent-gated drill-in card;
│            pure app/dashboard/ composition, no new state/consent/LLM
├── PI-6  CANDIDATE SIDE & INTAKE                                  [COMPLETE]
│   ├── [x] S6.1  GitHub-as-signal — pure app/profile_sources/ spine + GitHub
│   │            adapter (fetch → pure to_signal transform w/ S1.4 taxonomy
│   │            mapping + bounded confidence → append-only store, candidate
│   │            CASCADE); admin-plane POST/GET endpoints; advisory, no LLM,
│   │            no new consent purpose
│   ├── [x] S6.2  LinkedIn export parsing (2nd profile_sources adapter) — base64-
│   │            ZIP upload → pure parse_linkedin_export/to_signal, conservative
│   │            0.4/0.6 self-report-vs-corroborated confidence, de-identified
│   │            LinkedInActivity, discriminated activity union w/ back-compat
│   │            validator (no migration); admin-plane POST endpoint; advisory,
│   │            no LLM, no network, no new consent purpose
│   │            [multilingual/Hinglish intake DEFERRED — English-first, 2026-07-26]
│   ├── [x] S6.3  Normalization curation loop — human-in-the-loop taxonomy repair:
│   │            unmapped skill terms (canonical=None) from the GitHub + LinkedIn
│   │            adapters queue for admin review; map/create/ignore feeds a
│   │            deterministic normalize_skill overlay (static wins); candidate-
│   │            agnostic queue (no FK, survives erasure); no LLM, forward-only
│   └── [x] S6.4  Candidate auth + DPDP portal — candidate access-key auth
│                (X-Candidate-Key, mirrors org keys) + pure app/portal/
│                exposing access/transparency/consent-control/erasure; no new
│                consent purpose (self-access == identity of the subject)
├── PI-7  VERIFICATION & ASSESSMENT DEPTH                          [in progress]
│   ├── [x] S7.1  Verification spine + consent-first identity — pure
│   │            app/verification/ (assurance ladder behind a method-adapter
│   │            seam; outcomes stored, documents/biometrics structurally
│   │            impossible); ships self-attest / contact-control OTP /
│   │            operator manual review, government_id declared-but-inert;
│   │            two new ConsentPurpose (IDENTITY_VERIFY, VERIFICATION_READ);
│   │            three planes; no LLM, no network, advisory only
│   │            [MERGED 2026-07-31; branch review caught + closed two
│   │             candidate-side ladder escalations — seam now refuses by
│   │             default: self_service/implemented/instant]
│   ├── [~] S7.2  Document forensics (experience letters/payslips) +
│   │            moonlighting advisory — SECOND PRODUCER on the S7.1 spine
│   │            [spec written 2026-07-31; separate ClaimEvidence roll-up,
│   │             candidate-plane intake, EPFO declared-inert (vendor, not
│   │             legality, is the blocker); plan `47737a4` = 12 TDD tasks, build next]
│   └── [ ] S7.3  AI interview delivery v0 (audio-first English w/ Indian
│                accents, advisory, proxy-detection hooks reading
│                IdentityAssurance; model shortlist in MODELS.md)
└── PI-8  SCALE & LEARNING (shaped) — Postgres cutover + real embeddings ·
        calibration harness (predicted vs ledger outcomes) · observability +
        org self-serve.  STANDING NON-GOALS: payments/payroll/contracts,
        sourcing/outreach, native coding assessments (revisit post-PI-7)
```

## Standing conventions (do not relitigate)

- TDD, fully offline tests (NullLLM/fakes); `pytest -q` green before merge.
- Every LLM step degrades to a deterministic fallback (works with no API key).
- Advisory only — no auto-reject anywhere; conservative calibration gate stays.
- DPDP: first-party data only; consent objects + delete paths for new tables.
- Config: tunables in `config.yaml`, secrets in `.env` (`DEE_*`).
- DB: SQLAlchemy + Alembic on SQLite, Postgres-shaped (UUIDs, FKs, JSON columns).
- Each sprint ends with a local smoke: uvicorn + scripted HTTP calls on fixtures.
- LLM provider: OpenRouter + Qwen tiers (see `config.yaml`).

## Session log

- **2026-07-31 (2)** — **S7.1 whole-branch review → two Critical fixes →
  MERGED. S7.1 COMPLETE.** Review ran **inline** (the harness in these sessions
  forbids spawning agents unless the user asks), reading the full 14-commit
  branch surface rather than trusting the build's own account of it — which
  mattered, because the build's docs asserted a property the code did not have.
  **Both findings were reproduced over HTTP first** (throwaway pytest module
  against `create_app(make_services(...))`, deleted after), then fixed, then
  re-run to prove closure:
  **(1) `manual_review` self-award → L3.** The candidate-plane route accepted
  any `VerificationMethod`, and L3 asserts *an operator looked*.
  **(2) `government_id` self-award → L4.** The candidate grants themselves
  `IDENTITY_VERIFY` via S6.4 first-party consent (by design), the third-party
  gate passes, and the spine **never calls the adapter** — so the
  `NotImplementedError` inside `GovernmentIdAdapter.start` could not fire and
  the route's `except NotImplementedError → 422` was dead code. "Declared but
  inert / unreachable from any route" was false as shipped, in code *and* in
  `VERIFICATION.md`. The **shared root cause** was a fail-open default —
  `start()` read "not `challenge_based`" as "complete it now, VERIFIED" — and
  the **test blind spot** was `_FakeThirdPartyAdapter`: the gate was proven
  against a fake while the real, routable method was never driven end-to-end
  (`test_government_id_is_not_reachable_from_the_candidate_plane` asserted
  `status in (400, 403, 422)` and passed only because that test happened to have
  no grant — false comfort, now strengthened to grant-then-assert-422).
  **Fixes, all in the spine where the other gates live:** seam gains
  `self_service`/`implemented`/`instant`, **defaulting to REFUSE on `_Base`**
  (a new adapter is inert until it declares itself); `start()` documented as the
  candidate-initiated entry point, ordering `self_service` → `implemented` →
  third-party consent → destination binding (**consent necessary, never
  sufficient**); nothing is marked VERIFIED on request unless `instant`.
  `manual_review` → 403, `government_id` → 422. **Two more review fixes:** the
  OTP cooldown/supersession was scoped to one verification row and therefore
  rate-limited **nothing** (the plane mints a fresh verification per start, so a
  stolen key bought unlimited codes and unlimited 5-guess batches against a
  6-digit code) — rescoped to **candidate+channel**, plus `hmac.compare_digest`;
  and an operator manual review was audited `actor_type="candidate"`, so the
  candidate's own DPDP access log claimed **they** did it — now `"system"`.
  10 review tests added (**877→887** green, pyflakes clean); smoke_s71 extended
  with both escalations as checks — **19/19 OK exit 0**. Docs corrected
  (`VERIFICATION.md` §4/§5/§7/§8/§10, `PORTAL.md` route contract). Merged to
  main fast-forward; branch `s71-identity-verification` deleted. **Deferred
  minors (DEFER):** abandoned `pending` verification rows from superseded
  challenges (PI-8 sweep); OTP salt reuses `contact_hash_salt`; `Notifier.send`
  takes the raw destination. Next: shape/plan **S7.2** (document forensics +
  moonlighting advisory) as the second producer on this spine — resolve the
  EPFO/UAN legality question in its spec, and if murky, first-party timeline
  forensics only.
- **2026-07-31** — **PI-7 opened; S7.1 (verification spine + consent-first
  identity) built** (inline TDD-offline on branch `s71-identity-verification`,
  11 tasks; spec `2026-07-31-s71-identity-verification-design.md`, plan
  `2026-07-31-s71-identity-verification.md`). Confirmed S6.4 had already merged
  to main (`814e845`, 784 green) — PI-6 COMPLETE. Brainstormed PI-7 → **three
  scope decisions taken with user, all on recommendation:** **(1) S7.1 first** —
  build `app/verification/` as a reusable spine with identity as its first
  producer, so S7.2 lands as a second producer exactly as S6.2 did on S6.1's
  `profile_sources` spine (rejected: leading with S7.3, the largest build, which
  would strand identity hooks as stubs; and merging S7.1+S7.2 into one sprint).
  **(2) v0 = an assurance ladder behind an adapter seam** shipping only what is
  buildable with no vendor and no network — self-attest, contact-control OTP,
  operator manual review — with `government_id` **declared but unimplemented**,
  its consent gate and data posture designed now (rejected: OTP-only, which
  would force S7.2 to retrofit the spine; and an outcome-recording API, which
  skips the candidate-initiated consent flow that is the whole point of
  gap-analysis §5B). **(3) two new `ConsentPurpose` members** —
  `IDENTITY_VERIFY` + `VERIFICATION_READ` (rejected: one purpose, leaving a real
  govt-ID adapter with no grant to attach to; and reusing `LEDGER_READ`, which
  would silently widen what grants candidates have *already signed* disclose).
  Delivered `app/verification/` (`schema.py`/`assurance.py`/`otp.py`/
  `methods.py`/`models.py`/`store.py`/`service.py`), migration `0013` (two
  candidate-CASCADE tables), `Services.verification` wired cycle-safe (built
  **before** the portal, which now surfaces `identity` on `MyData`), six
  endpoints across the admin/org/candidate planes, `verif_*` + `ret_verification_days`
  config, and `VERIFICATION.md`. **No LLM, no network** — fully deterministic, so
  the deterministic-fallback convention is satisfied trivially. 93 new tests
  (**784→877**, `pytest -q` green — verified this session); pyflakes clean on
  every new + modified file. Smoke `scripts/smoke_s71.py` (uvicorn, key-less)
  **16/16 OK** exit 0. **Notable during the build:** the migration nullability
  guard caught a genuine drift (`details` `nullable=True` in the migration vs
  `Mapped[dict]` NOT NULL in the ORM) — migration corrected, models kept as the
  source of truth; and the first API-test fixture used the module-level `app`
  (whose lifespan builds real services against the dev DB) and was corrected to
  this repo's `create_app(services)` pattern. Executed **inline** rather than
  subagent-driven: the harness in this session forbids spawning agents unless the
  user asks. **PENDING:** final whole-branch review + merge. Next: merge, then
  shape/plan S7.2 (document forensics + moonlighting advisory) as the second
  producer on this spine.
- **2026-07-30 (2)** — **S6.4 (candidate auth + DPDP portal) built — PI-6
  COMPLETE** (subagent-driven on branch `s64-candidate-auth-dpdp-portal`, 10
  build tasks + this closeout; spec
  `2026-07-30-s64-candidate-auth-dpdp-portal-design.md`, plan
  `2026-07-30-s64-candidate-auth-dpdp-portal.md`). Three load-bearing scope
  decisions taken with user (all on recommendation): **retention TTLs surface
  posture now, sweep deferred to PI-8** (no scheduler exists yet; a sweep built
  now would strand an un-triggered function); **first-party consent is
  additive, not a hard replace** (the admin-plane consent endpoint stays — it
  seeds tests and supports org-initiated consent-request flows); **candidate
  auth = a minted, sha256-hashed, rotatable access key** (mirrors the org key —
  offline-deterministic, zero external deps; real password/OTP/session
  registration is a PI-8 productionization concern). Two smaller calls
  confirmed with user: (a) `/portal/me` lists reports by existence + timestamp
  only, not advisory internals; (b) the access-log includes platform-internal
  actions, not just org disclosures. Delivered: migration
  `0012_candidate_credentials` (candidate CASCADE, unique on `candidate_id`;
  drift/index/FK/nullability guards extended); `CandidateStore.issue_access_key`/
  `authenticate_candidate`; `require_candidate` dependency + new dependency-free
  `candidate_router`; admin-plane `POST /candidates/{id}/auth-key` (mint, once,
  200/404/401); new pure package `app/portal/` (`schema.py`/`retention.py`/
  `service.py` — `PortalService` composing `CandidateStore`+`LedgerStore`+
  `ProfileSourceService`+`ReportStore`, owns no tables); `Services.portal` wired
  cycle-safe; `LedgerStore.consents_for_candidate`/`get_grant` (small raw-read
  additions, nothing existing changed); config knobs
  `candidate_access_key_bytes` (32) + six `ret_*_days`; six candidate-plane
  endpoints (`GET /portal/me`, `GET /portal/access-log`,
  `GET/POST /portal/consents`, `POST /portal/consents/{id}/revoke`,
  `DELETE /portal/me`). **No new `ConsentPurpose`** — self-access is gated
  purely by identity (`require_candidate`), never a consent object;
  cross-candidate isolation is structural (every handler resolves
  `candidate_id` from the key, never a param) with ownership-enforced revoke
  (identical 404 whether a `consent_id` is unknown or belongs to someone else —
  no probing). `PORTAL.md` written (peer of `LEDGER.md`/`DASHBOARD.md`). 32 new
  tests (**752→784**, `pytest -q` green — verified this session). Smoke
  `scripts/smoke_s64.py` (uvicorn, key-less) **10/10 OK** exit 0 (the smoke
  commit's subject stale-reads "(12/12)" — the correct, verified count is
  10/10): create candidate → admin mints a key → `/portal/me` shows
  profile/resumes/retention → org submits + queries a consented interview
  record → `/portal/access-log` shows it with the org's name resolved →
  first-party grant via `/portal/consents` → `GET /portal/consents` active →
  revoke → state `revoked` → wrong/absent key 401 → a second candidate's key
  cannot see or revoke candidate 1's data (404, untouched) →
  `DELETE /portal/me` erases; key then 401s; admin `GET /candidates/{id}` 404.
  Executed subagent-driven: fresh implementer + review per task across the 10
  build tasks plus this closeout; per-task review came back clean; two
  plan-text inaccuracies were self-corrected during the build (Task-8's
  route-existence test ordering; Task-9's shared-email test helper
  unexpectedly collapsing two candidates via the S1.1 email/phone-hash dedup
  path). Deferred minors carried (all DEFER, none merge-blocking): unused
  `datetime` imports in `tests/test_ledger_consents_for_candidate.py` (F401);
  two API test helpers use `client.__enter__()` without `__exit__()`
  (thread-leak, no correctness impact); the smoke commit's stale "(12/12)"
  subject; the `no_key_401` smoke check exercises absent-key only (wrong-key is
  covered by a unit test). **PI-8 follow-ups (spec §9):** mechanical retention
  sweep; real candidate registration (password/OTP/session); exposing depth
  `Report` internals to the candidate; DPDP correction/rectification right;
  grievance/DPO contact endpoint; multi-credential/device sessions. Commits
  `f3646ca..4bdbdb6` (Tasks 1–10; spec `a0450d5`, plan `d2737f6` precede), this
  closeout on top. **PENDING:** final whole-branch review + merge. **PI-6
  (candidate side & intake) COMPLETE (S6.1–S6.4).** Next: merge, then shape/plan
  **PI-7** (verification & assessment depth) per the gap-analysis §6, when its
  turn comes.
- **2026-07-30** — **S6.3 (normalization curation loop) built** (subagent-driven
  on branch `s63-normalization-curation`, 9 tasks; spec
  `2026-07-30-s63-normalization-curation-loop-design.md`, plan
  `2026-07-30-s63-normalization-curation-loop.md`). Brainstormed → three design
  decisions taken with user (all on recommendation): **skills-only scope**
  (employers/institutions curation deferred — they lack a clean `canonical=None`
  unmapped marker); **system-wide overlay on `normalize_skill`** (curated aliases
  load into an in-memory `_CURATED_OVERLAY` merged with the static index — every
  consumer benefits, `normalize_skill` stays a pure dict lookup, **static taxonomy
  always wins**); **capture from profile sources only** (resume-extraction capture
  deferred). Two smaller calls: no decision-history table (re-resolve overwrites)
  and forward-only (resolving does not re-normalize already-stored signals).
  Delivered a new pure `app/curation/` package (`schema.py` — `CurationStatus`/
  `CurationAction`/`UnmappedTerm`; `models.py` — `UnmappedTermRow`; `store.py` —
  `CurationStore` upsert-queue/`resolve`/`load_overlay`; `service.py` —
  `CurationService` capture guards + resolve validation matrix + overlay refresh),
  the overlay hook + `set_/clear_curated_overlay`/`canonical_ids`/
  `category_for_canonical` on `app/candidates/normalize/skills.py`, best-effort
  capture wired into `ProfileSourceService` (both ingest paths, only
  `canonical is None`), `Services.curation` wired cycle-safe with the overlay
  loaded once at startup, migration `0011_skill_curation` (**candidate-agnostic**
  `unmapped_terms` — no candidate FK / no consent / no CASCADE; DPDP erasure
  deliberately leaves queued terms; drift/index/nullability guards extended), two
  admin-plane endpoints (`GET /curation/skills/unmapped` + `POST
  /curation/skills/resolve`, 200/404/422), and `cur_*` config knobs (200/2/64).
  **No LLM, no network, no new consent purpose.** `CURATION.md` written;
  `PROFILE_SOURCES.md` S6.3 note flipped to shipped. 27 new tests (725→752,
  `pytest -q` green). Smoke `scripts/smoke_s63.py` (uvicorn, key-less) 16/16 OK
  exit 0: create candidate → POST LinkedIn export with novel skills (COBOL,
  PyTorch Lightning, "Team Player") → queue pending → resolve create
  `cobol`/language + map "pytorch lightning"→`pytorch` (category `ml` derived) +
  ignore "team player" → re-POST → COBOL→`cobol`, PyTorch Lightning→`pytorch`
  (live per-process overlay), "Team Player" stays unmapped & not re-queued → bad
  resolve 422, unknown 404 → DPDP-erase candidate → queued term **survives**
  (candidate-agnostic). Executed subagent-driven: fresh implementer + two-stage
  spec/quality review per task (Tasks 1–4, 6–8 review-clean; Task 5 one fix round —
  two tests strengthened to genuinely discriminate existence-before-validation
  ordering and limit-cap enforcement). Task 9 (ROADMAP closeout) was finished
  in-controller after the account session limit terminated its subagent mid-edit —
  docs-only bookkeeping, matching the S5.3 precedent. Nine deferred minors carried
  (all DEFER, none merge-blocking — in the sprint ledger). Commits
  `078eab5..` this closeout (spec `6e9f514`, plan `3c9680b` precede). **PENDING:**
  final whole-branch review + merge. Next: merge, then shape/plan S6.4 (candidate
  auth + DPDP portal).
- **2026-07-29** — **S6.2 (LinkedIn export parsing / 2nd profile_sources
  adapter) built** (TDD-offline on branch `s62-linkedin-export`, 7 tasks; plan
  `docs/superpowers/plans/2026-07-28-s62-linkedin-export.md`). Second adapter on
  the S6.1 spine, no LLM, no network: config knobs
  `max_linkedin_b64_chars`/`ps_linkedin_skill_base_confidence`/
  `ps_linkedin_skill_corroborated_confidence`/`ps_linkedin_max_rows`;
  `ProfileSourceType.LINKEDIN_EXPORT` + `LinkedInActivity` (de-identified —
  canonical employers/institutions + counts only); `ProfileSourceSignal.activity`
  generalized to a discriminated union `GitHubActivity | LinkedInActivity`
  (discriminator `kind`) with a `source_type`-derived back-compat validator so
  pre-S6.2 GitHub rows keep validating — **no migration**; `method` gained
  `"export"`. `app/profile_sources/linkedin.py`: pure `parse_linkedin_export`
  (ZIP/CSV, per-row graceful degradation, column-name variants, nested export
  dirs, row cap) + pure `to_signal` (S1.4 taxonomy map; self-reported skills are
  claims at base confidence 0.4, bumped to 0.6 once whole-token-matched against
  that export's own positions/headline; de-identified `LinkedInActivity`;
  `method="export"`/`"unavailable"`). `ProfileSourceService.ingest_linkedin`
  (existence check → parse → transform → persist via the S6.1
  `ProfileSourceStore`; identifier fixed to `"linkedin_export"`). Admin-plane
  `POST /candidates/{id}/sources/linkedin` (200 export / 200 unavailable / 404 /
  422 bad-base64 / 422 oversize); `GET /candidates/{id}/sources?source_type=...`
  already worked unchanged. **No LLM, no network, no new consent purpose** — the
  export is the candidate's own first-party data; CASCADE erasure. 28 new tests
  (697→725, `pytest -q` green). `PROFILE_SOURCES.md` rewritten to cover both
  adapters (transport, pure parse→to_signal seams, confidence model, DPDP
  posture, endpoint contract, config knobs). Smoke `scripts/smoke_s62.py`
  (uvicorn, key-less) 12/12 OK exit 0: create candidate → POST linkedin export
  (canonical + corroborated Python 0.6, uncorroborated Leadership 0.4, canonical
  employers/institutions, current_positions) → GET filtered sources (1 row) →
  bad base64 422 → DPDP erase → sources 404. Six deferred minors carried from
  the sprint ledger, all DEFER / none merge-blocking (see "Current sprint" above
  for the list). Executed subagent-driven (fresh implementer + two-stage review
  per task; fix loops on Tasks 3/4/7 — ragged-CSV per-row degradation, trailing-dot
  corroboration, DPDP-retention doc accuracy). Task 5 was interrupted by a session
  limit mid-edit and resumed from its transcript; its erasure test was corrected
  from a broken brief assertion (`list_sources` after delete raises by design) to a
  store-level CASCADE check. **PI-6 reshaped:** S6.1 GitHub [done] · S6.2 LinkedIn
  export [done] · new **S6.3 Normalization curation loop** (the deferred curation
  thread, kept explicit on the board, its own sprint, not required now) · S6.4
  Candidate auth + DPDP portal (moved down from S6.3). Whole-branch final review
  (opus) = Ready to merge Yes, no Critical/Important. **Merged to main
  (fast-forward `23972d7`→`497eedb`), branch deleted, 725 green on main. S6.2
  COMPLETE.** Next: S6.3 plan (normalization curation loop).
- **2026-07-28 (3)** — **S6.1 (GitHub-as-signal / profile-source ingestion) built**
  (inline TDD-offline on branch `s61-github-profile-source`, 9 tasks; spec
  `2026-07-28-s61-github-profile-source-design.md`, plan
  `2026-07-28-s61-github-profile-source.md`). Brainstormed PI-6; two design
  decisions taken with user (both recommendations accepted): **(1) scope S6.1 to
  GitHub-as-signal only** — build the reusable `profile_sources` spine with GitHub
  as the first adapter (LinkedIn export reshapes into S6.2); **(2) ingest + store
  only** — resume-vs-source corroboration deferred. PI-6 reshaped: S6.1 GitHub ·
  S6.2 LinkedIn export + curation loop · S6.3 candidate auth + DPDP portal.
  Delivered a new pure `app/profile_sources/` package (`schema.py` contracts +
  `ProfileSourceType`; pure `github.py::to_signal` — non-fork language byte
  aggregation → S1.4 `normalize_skill` canonical skills [unknown kept,
  `canonical=None`] + bounded evidence-monotone confidence + primary-language
  nominal tail; `store.py::ProfileSourceStore` append-only on the candidates DB;
  `service.py::ProfileSourceService` handle resolution [explicit → profile GitHub
  link → 400; unknown candidate → 404] + fetch→transform→persist), extended
  `app/services/github.py` with `GitHubUserRaw`/`GitHubRepoRaw` +
  `gather_user_signal` (graceful degradation, `ps_github_*` limits), migration
  `0010_profile_sources` (candidate CASCADE; drift/index/FK/nullability guards
  extended), `Services.profile_sources` wired cycle-safe (shares the one GitHub
  client + candidate store; `build_default_services` hoists both), admin-plane
  endpoints `POST /candidates/{id}/sources/github` + `GET /candidates/{id}/sources`
  (200/400/404; degraded fetch → 200 `method="unavailable"`). `ps_github_repo_limit`
  /`ps_github_language_repos`/`ps_github_include_forks` config knobs. **No LLM, no
  new consent purpose, no candidate PII beyond the public handle, advisory only,
  depth scoring untouched.** `PROFILE_SOURCES.md` written. 25 new tests (672→697,
  `pytest -q` green). Smoke `scripts/smoke_s61.py` (uvicorn + LIVE GitHub) 7/7 OK
  exit 0: create candidate → POST github source (method=api, activity present) →
  GET sources (1 row) → no-handle 400 → DPDP erase → sources 404. Whole-branch
  self-review clean (no Critical/Important). Merged to main (fast-forward), branch
  deleted, 697 green on main. **S6.1 COMPLETE.** Next: S6.2 plan.
- **2026-07-28 (2)** — **S5.3 (thin employer dashboard) built + merged**
  (subagent-driven on branch `s53-employer-dashboard`, 7 TDD tasks; spec
  `2026-07-28-s53-employer-dashboard-design.md`, plan
  `2026-07-28-s53-employer-dashboard.md`). Two design decisions taken with user:
  **JSON read-models only** (no HTML/UI — API-first stays primary) and **lean board +
  drill-in card** (a board load fires no extra cross-org reads; consent-gated
  composition lives in the per-candidate card). Delivered a new pure `app/dashboard/`
  package (`schema.py` contracts + `SectionStatus`; `service.py` `DashboardService`
  composing JobStore + CompService + LedgerStore, owns no tables/state) exposing three
  org-plane read-models: `GET /dashboard/overview` (org's own reqs — counts by status +
  per-req flags; no consent, no audit), `GET /jobs/{id}/board` (requisition +
  `CompService.benchmark` + top-N `run_match`; 404 cross-org, 422 empty pool; reuses
  `run_match`'s `match.surface` + comp's `comp.aggregate` audit rows, adds none),
  `GET /candidates/{id}/card` (per-section consent-gated drill-in reusing
  `reputation_for_org`/`query_coding_rounds_for_org`/`query_records_for_org`; **200 with
  per-section `SectionStatus`** available/consent_required/no_data — never hard-403s;
  404 only for an unknown candidate [`LookupError` propagates]; audit-by-reuse).
  `Services.dashboard` wired cycle-safe (S4.3/S5.1/S5.2 pattern). `dash_board_top_n`
  config knob. **No LLM, no new consent purpose, no migration, no candidate PII, no
  depth-`Report` exposure.** `DASHBOARD.md` written. 29 new tests (653→672,
  `pytest -q` green). Smoke `scripts/smoke_s53.py` (uvicorn + HTTP) 18/18 OK exit 0:
  overview → board 422 (empty pool) → board 200 (materialized, comp advisory) → card
  consent_required (no grant) → grant ledger_read → no_data → revoke → consent_required
  (all 3 sections) → cross-org board 404 → unknown-candidate card 404. Executed
  subagent-driven: fresh implementer + reviewer per task (Tasks 1–6 review-clean; Task 5
  reviewer caught + fixed a wrong-enum bug the plan carried [`InterviewStage.TECHNICAL`/
  `InterviewOutcome.PASS` → real `TECH`/`ADVANCED`]; Task 7 one Important doc-accuracy
  finding [board audit inventory omitted the reused `comp.aggregate` row] fixed + a smoke
  revoke-symmetry minor). **NOTE:** the account session limit was hit near the end, so
  the Task-7 fix's scoped re-review and the independent whole-branch final review could
  not run as subagents — the fix was applied in-controller and self-verified (smoke
  18/18, suite 672), and a controller whole-branch self-review (pyflakes clean on all
  new + modified files; `service.py` logic re-read; deferred minors resolved) stood in,
  per the user's explicit decision to merge now rather than wait for the ~7pm reset.
  Merged to main (fast-forward), branch deleted. **S5.3 COMPLETE — PI-5 (demand side)
  COMPLETE.** Next: shape PI-6 (candidate side & intake).
- **2026-07-28** — **S5.2 (comp intelligence v0) built** (inline TDD-offline on
  branch `s52-comp-intelligence`, 10 tasks; spec
  `2026-07-28-s52-comp-intelligence-design.md`, plan `2026-07-28-s52-comp-
  intelligence.md`). Also closed out S5.1 bookkeeping first (reflog confirmed S5.1
  fast-forward merged to main at `2eb591c`; ROADMAP "merge pending" prose was stale).
  Two design decisions taken with user (both recommendations accepted, rest
  delegated): **(1) capture + blend** — observed offers get a first-class,
  consent-gated CTC field (not event-payload/defer); **(2) estimate + requisition
  benchmark** surface (no comp-fit match term — no candidate expected-CTC exists
  yet). Delivered a new pure `app/comp/` package (`schema.py` contracts +
  `SeniorityBand`/role-family vocab; `bands.py` illustrative license-clean static
  seed table [role x seniority x city-tier] + `comp_bands_path` override + title/
  skill/years/tier resolvers; `estimate.py` reputation.py-style shrinkage toward the
  static prior on a **total-CTC basis** + k-anonymity floor + saturating confidence
  + benchmark; `service.py` `CompService` reading offers via `LedgerStore`),
  consent-gated `observed_offers` ledger table (peer of coding_round_results;
  `ObservedOffer`/`ObservedOfferPoint` [de-identified projection], `ObservedOfferRow`,
  migration `0009` candidate+org+consent CASCADE, drift/index/FK/nullability guards
  extended), `LedgerStore.submit_observed_offer` (`ledger_write`-gated, `consent_id`-
  stamped, audited `offer.submit`) + `observed_offers_for_comp` (**de-identified**,
  revocation-respecting stamped-grant check, audited `comp.aggregate` with
  `candidate_id=None`), `Services.comp` wiring (TYPE_CHECKING + function-local build,
  the S4.3/S5.1 cycle-safe pattern; ledger never imports comp — comp vocab validated
  at the API boundary), org-plane endpoints `POST /ledger/offers` +
  `POST /comp/estimate` + `GET /jobs/{id}/comp` (403/404/400/401). `comp_*` config
  knobs (k-floor, halflife, prior strength, confidence, seniority thresholds,
  benchmark tolerance, bands-path). **No LLM, no new consent purpose.** DPDP posture:
  cross-candidate aggregation basis = revocation-respecting inclusion + k-anonymity +
  de-identified output + audit; **documented residual** — reusing `ledger_write` data
  for aggregation (vs a dedicated purpose that would stay empty) revisited later.
  `COMP.md` written. 29 new tests (623→652, `pytest -q` green). Smoke
  `scripts/smoke_s52.py` (uvicorn + HTTP) 13/13 OK exit 0: static-only floor → 6
  consented offers → observed blend (p50 above prior, confidence above floor) →
  benchmark 'at' (band brackets p50) + 'below' (low band) → different role < k stays
  static → revoke drops one offer (n_observed 6->5) → DPDP erase tips below k
  (static-only) → cross-org benchmark 404. Whole-branch self-review clean (no
  Critical/Important; one Minor closed — `comp_bands_path` override loader now
  tested, 652->653). Merged to main, branch deleted. **S5.2 COMPLETE.** Next: S5.3
  plan (thin employer dashboard).
- **2026-07-27 (5)** — S5.1 closed out (bookkeeping only, no new code). Confirmed
  via `git reflog` that branch `s51-job-requisition-matching` was **fast-forward
  merged to main** (`2eb591c`) with the whole-branch review's hardening fix
  (`ff2ecae`) already landed; branch deleted. `pytest -q` **623 green on main**.
  The ROADMAP "Current state"/"Next action" prose was stale (still framed the merge
  as "pending") — corrected here. **S5.1 COMPLETE.** Next: brainstorm → spec → plan
  → build **S5.2** (comp intelligence v0 — static bands + ledger-observed offers,
  advisory; consumes S5.1's stored `comp_band`), per gap-analysis §6.
- **2026-07-27 (4)** — **PI-5 shaped + S5.1 built** (inline TDD-offline on branch
  `s51-job-requisition-matching`). Confirmed PI-4 already merged to main (S4.4
  done); ROADMAP "Next action" prose was stale. Brainstormed PI-5 demand side →
  scoped this sprint to **S5.1** (spec `2026-07-27-s51-job-requisition-matching-
  design.md`, plan `…-matching.md`, 10 tasks). Four design decisions delegated to
  recommendation: **org plane** (X-Org-Key), **compile-to-ranking + job-relative
  skill-coverage**, **comp band metadata-only** (S5.2 consumes it, no follow-up
  migration), **audit-every-match with no new consent gate** (pool already
  consent-masked at S4.2). Delivered new `app/matching/` package: pure `schema.py`
  contracts; pure `match.py` (`skill_coverage`/`location_fit`/`compile_ranking`/
  `compile_filters`/`match` — injects synthetic `match.skill_coverage`/
  `match.location_fit` into a FeatureVector copy and reuses S4.3 `ranking.score()`,
  zero new scoring math); ORM `JobRequisitionRow` + migration `0008` (org-owned,
  CASCADE on org, **not candidate-linked** → survives candidate erasure; drift/
  index/FK/nullability guards extended); `JobStore` (org-scoped CRUD, canonical
  skill normalization, audited `requisition.create`/`update`; `run_match` reads
  pool + point-in-time profiles at one `as_of`, ranks, audits each returned
  candidate as `match.surface` — candidate-linked + CASCADE); `Services.jobs`
  wiring (TYPE_CHECKING + function-local build, the S4.3 cycle-safe pattern);
  org-plane endpoints `POST/GET/PATCH /jobs` + `POST /jobs/{id}/match`
  (`MatchResult{advisory=True}`; cross-org 404, empty/unmaterialized pool 422,
  malformed 400). `min_years/degree/notice` are **soft** (select the dimension,
  value is not a cutoff); the **only** hard gate is opt-in `min_skill_coverage`.
  `match_*` config knobs (skill weight 3.0 dominant). No LLM, no new consent
  purpose. `MATCHING.md` written. 39 new tests (584→623, `pytest -q` green). Three
  in-flight/review fixes: `run_match` `filtered_size` = post-filter-pre-limit count
  (S4.3 parity); `smoke_s51`/API tests use `with TestClient(...)` so the lifespan
  sets `app.state.services`; whole-branch review hardened skill canonicalization
  (keep punctuation asks; all-blank skills → 400 not a reconstruct 500). Smoke
  `scripts/smoke_s51.py` (uvicorn + HTTP) 11/11 OK exit
  0: ranked strong→weak→other by skill coverage (advisory — zero-coverage still
  appears), `min_skill_coverage=0.75` gates to strong only, DPDP erase drops the
  candidate + sweeps its `match.surface` audit rows. **PENDING:** final whole-branch
  review + merge to main. Next: merge, then S5.2 plan (comp intelligence v0).
- **2026-07-06** — Brainstormed + approved product design (Talent Intelligence
  Platform slice of a Mercor-style marketplace; SQLite-now/PG-shaped; modular
  monolith). Created spec, roadmap, CLAUDE.md, memory pointer. Next: S1.1 plan.
- **2026-07-06 (2)** — S1.1 done, TDD-offline on branch `s11-extraction-schema`:
  `app/candidates/{schema,hashing,dates,extractor}.py` — CandidateProfile with
  per-field confidence + SourceSpan provenance, salted contact-dedup hashing
  (`contact_hash_salt` in config.yaml), deterministic date parser, section-based
  heuristic extractor + LLM path (`parsing` tier) with fallback. 26 new tests
  (88 green). Smoke `scripts/smoke_s11.py` green with live OpenRouter key AND
  key-less (heuristic floor). Next: S1.2 plan (candidate store).
- **2026-07-06 (3)** — S1.2 done, TDD-offline on branch `s12-candidate-store`:
  shared SQLAlchemy core (`app/core/db.py`: Base, engine w/ SQLite FK pragma +
  StaticPool, session factory; `candidates_db_url` setting), PG-shaped ORM rows
  (`app/candidates/models.py`: candidates / resumes versioned-unique /
  extractions JSON), Alembic env + `0001_candidate_store` (+ drift-guard test),
  `CandidateStore` (`app/candidates/store.py`: ingest with email→phone hash
  identity resolution + backfill, sha256 resume dedup, latest_profile,
  DPDP hard deletes, `build_candidate_store`). 25 new tests (113 green).
  Smoke `scripts/smoke_s12.py` green live (llm) AND key-less (heuristic).
  Next: S1.3 plan (API + engine wiring).
- **2026-07-06 (4)** — S1.3 implementation plan written:
  `docs/superpowers/plans/2026-07-06-s13-api-engine-wiring.md` (7 TDD tasks,
  branch `s13-api-wiring`, 113→137 tests). Scope: `Report.candidate_id` +
  `for_candidate`/`delete_for_candidate` on both report stores (guarded ALTER
  for legacy reports.db), shared `app/core/pdf.py` helper, `Services.candidates`
  via `build_candidate_store`, POST /candidates (extract → ingest → auto
  depth-eval, graph untouched), GET candidate/resumes/reports, DPDP DELETE
  endpoints (candidate erasure also deletes linked reports), uvicorn smoke
  `scripts/smoke_s13.py`. Next: execute the plan.
- **2026-07-06 (5)** — S1.3 done, TDD-offline on branch `s13-api-wiring`:
  `Report.candidate_id` + `for_candidate`/`delete_for_candidate` on both report
  stores (guarded ALTER on legacy reports.db), shared `app/core/pdf.py`,
  `Services.candidates` via `build_candidate_store`, POST /candidates
  (extract → ingest → auto depth-eval; report stamped with candidate_id;
  graph/`/evaluate` untouched), GET candidate/resumes/reports, DPDP DELETE
  resume + candidate (erasure also deletes linked reports). 24 new tests
  (137 green). Smoke `scripts/smoke_s13.py` green live (llm) AND key-less
  (heuristic) — 11/11 checks OK both runs. Final review fix: POST /candidates
  re-checks the candidate after saving the report and drops the report if the
  candidate was erased mid-eval (25 new tests, 138 green). Accepted residual:
  a milliseconds-wide erasure race between that re-check and a concurrent
  delete's report sweep — mop up via a future orphaned-reports sweep (reports
  whose candidate_id no longer resolves). Next: S1.4 plan (India
  normalization).
- **2026-07-09** — S1.4 implementation plan written:
  `docs/superpowers/plans/2026-07-09-s14-india-normalization.md` (7 TDD tasks,
  branch `s14-india-normalization`, 138→190 tests). Scope: pure deterministic
  `app/candidates/normalize/` package (no LLM, no migration, no new tables),
  Optional canonical sibling fields on the S1.1 schema, extractor wiring.
- **2026-07-16** — S1.4 done, TDD-offline on branch `s14-india-normalization`:
  `app/candidates/normalize/{text,skills,degrees,orgs,location}.py` + the
  `normalize_profile` orchestrator — norm_key alias indexing, ~85-skill
  taxonomy, Indian degree families + canonical CGPA/10 (cgpa_4×2.5, %÷9.5
  clamped), institution alias table + IIT/IIM/NIT/IIIT campus patterns with
  tiers, ~60-employer alias table with legal-suffix stripping, city gazetteer
  (metro/tier_2) + notice-period parser (both offset-preserving for
  provenance). Schema grew all-Optional canonical fields (legacy JSON still
  validates); `heuristic_profile` lifts location + notice period with spans;
  `extract_profile` normalizes both paths; prompt asks for `notice_period`.
  52 new tests (190 green). Smoke `scripts/smoke_s14.py` 8/8 OK key-less
  (heuristic floor) AND live (llm) after the user refreshed the expired
  OpenRouter key. PI-1 complete. Next: S2.1 plan.
- **2026-07-17** — S2.1 implementation plan written:
  `docs/superpowers/plans/2026-07-17-s21-ai-signals.md` (7 TDD tasks, branch
  `s21-ai-signals`, 190→~223 tests). Scope: pure `app/fabrication/ai_text.py`
  (4 deterministic detectors: template phrases, uniform bullets, metric
  saturation, symmetric structure; fusion + conservative banding), new
  `ai_signals` graph node after ingest (deterministic first, LLM stylometry
  second with confidence capped at 0.75; LIKELY requires ≥2 deterministic
  tells — LLM alone can never flag), `AIGenerationAssessment` surfaced as an
  advisory `Report.ai_generation` field + flywheel record, adversarial
  fixture, smoke `scripts/smoke_s21.py`. No migration; depth scoring
  untouched (fusion into calibration is S2.4). Next: execute the plan.
- **2026-07-17 (2)** — S2.1 done, TDD-offline on branch `s21-ai-signals`:
  `app/schemas/fabrication.py` (AISignal / AILikelihoodBand /
  AIGenerationAssessment, advisory always true), `app/fabrication/ai_text.py`
  (template-phrase density, uniform-bullet shape, round-% metric saturation,
  symmetric entry structure; detectors gated on word/bullet minimums,
  confidence grows with evaluable detectors; fuse_pairs + band_for with the
  LIKELY ⇒ ≥2 deterministic tells gate), `ai_signals` node wired
  ingest → ai_signals → claim_extraction (LLM stylometry via the `parsing`
  FAST tier — non-decisive by design, so no flagship spend; confidence
  capped 0.75, degrades to deterministic on no key/garbage),
  `Report.ai_generation` + summary advisory note + flywheel
  `record_type: "ai_signals"`. Config knobs `ai_*` in config.yaml/Settings.
  35 new tests (225 green). Smoke `scripts/smoke_s21.py` 6/6 OK key-less
  (deterministic floor) AND live (llm; read timeout raised to 600s — the
  12-bullet fixture pays one reasoning call per claim). Next: S2.2 plan.
- **2026-07-17 (3)** — S2.2 implementation plan written:
  `docs/superpowers/plans/2026-07-17-s22-cross-field-forensics.md` (8 TDD
  tasks, branch `s22-cross-field`, 225→~268 tests). Scope: pure
  `app/fabrication/cross_field.py` (conservative interval math: year-only
  dates shrink inward for overlaps / expand outward for tenure; 4 checks),
  `cross_field` node after ai_signals (explicit profile from POST
  /candidates, else deterministic heuristic fallback; NO LLM in S2.2),
  advisory `Report.cross_field` + flywheel record. Gaps always minor.
- **2026-07-17 (4)** — S2.2 done, TDD-offline on branch `s22-cross-field`:
  `app/schemas/fabrication.py` grew FindingSeverity / ConsistencyBand /
  CrossFieldFinding / CrossFieldAssessment; `app/fabrication/cross_field.py`
  (narrow/wide/month-precise intervals, timeline_overlap ≥3mo (major ≥12),
  timeline_gap ≥12mo (always minor, neutral copy), education_employment_overlap
  ≥12mo bachelor-only (major ≥24), seniority_vs_tenure with 24/48-month
  floors (senior=minor, lead+=major) needing ≥2 dated entries;
  band_for_findings + assess_cross_field with the S2.1 confidence formula),
  `cross_field` node wired ai_signals → cross_field → claim_extraction
  (uses `state.candidate_profile` when POST /candidates supplies it, else
  `normalize_profile(heuristic_profile(text))`), `EvaluationEngine.evaluate`
  + POST /candidates pass the extracted profile through,
  `Report.cross_field` + major-only summary note + flywheel
  `record_type: "cross_field"`. Config knobs `xf_*` in config.yaml/Settings.
  45 new tests (270 green). Smoke `scripts/smoke_s22.py` 9/9 OK key-less
  (NullLLM + heuristic extraction) AND live (LLM extraction; both profile
  paths land major_issues on the inconsistent fixture, genuine stays clean).
  Next: S2.3 plan.
- **2026-07-17 (5)** — S2.3 done, TDD-offline on branch `s23-resume-farm`:
  `app/fabrication/similarity.py` (contact-masking before shingling so
  identity swaps don't dodge detection, word shingles + deterministic
  MinHash over 128 permutations, algo id "minhash-v1:128x3",
  `assess_resume_farm` bands unique/near_duplicate/insufficient_data with
  escalation once a cluster of matches appears), migration
  `0002_resume_fingerprints` with CASCADE FKs so DPDP deletes cascade
  cleanly, store `save_fingerprint`/`similar_resumes`. Detection lives at
  the API layer inside POST /candidates rather than as a graph node — the
  comparison must self-exclude by candidate_id (re-uploads and new versions
  are legitimate), and the graph is deliberately kept identity-blind.
  `Report.resume_farm` + near_duplicate-only advisory summary note +
  flywheel `record_type: "resume_farm"`. Config knobs `rf_*` in
  config.yaml/Settings. 42 new tests (312 green). One review fix
  (commit f0ba555) tightened advisory framing on all reasoning paths.
  Smoke `scripts/smoke_s23.py` 11/11 OK key-less (NullLLM + heuristic
  extraction) AND live (LLM extraction): first upload of a farm template is
  unique, an identity-swapped copy from a different candidate lands
  near_duplicate at a measured estimated similarity of 0.9375 (near_duplicate
  threshold 0.80) pointing back at the original, the uploader's own
  re-upload dedupes and self-excludes cleanly while still correctly
  matching the other farm member, a genuine resume stays unique, and
  POST /evaluate carries no farm assessment (no identity, no comparison).
  The smoke script's original re-upload check asserted the wrong property
  (expected `unique`, ignoring that a genuine near-duplicate was already in
  the corpus) and was corrected mid-session to assert self-exclusion
  directly — a script bug, not a product bug. Next: S2.4 plan.
- **2026-07-18** — S2.4 implementation plan written:
  `docs/superpowers/plans/2026-07-18-s24-fabrication-risk.md` (7 TDD tasks,
  branch `s24-fabrication-risk`, 312→~345 tests). Scope: pure deterministic
  `app/fabrication/risk.py` (band→risk mapping as code constants; fused score
  = 0.7·confidence-weighted mean + 0.3·max component risk; coverage
  confidence `min(0.9, 0.30 + 0.15·evaluated)` so single-subsystem fusion
  never asserts; ELEVATED requires ≥2 components at their top band —
  mirrors S2.1's ≥2-tells gate), computed in the scoring node (the
  calibration stage) with depth/verdicts provably untouched,
  `Report.fabrication_risk` + summary note on moderate/elevated + flywheel
  `record_type: "fabrication_risk"`, config knobs `fr_*`, smoke
  `scripts/smoke_s24.py`. No LLM, no migration. Next: execute the plan.
- **2026-07-18 (2)** — S2.4 done on branch `s24-fabrication-risk` (subagent-
  driven: 7 tasks, each spec+quality reviewed; final whole-branch review
  clean). Delivered per plan: contracts (FabricationRiskBand / RiskComponent
  / FabricationRiskAssessment), `app/fabrication/risk.py` (build_components
  excludes absent/insufficient signals; fuse = 0.7·weighted-mean + 0.3·max;
  confidence min(0.9, 0.30+0.15·evaluated) — one subsystem ⇒ 0.45 ⇒ never
  asserts), scoring-node fusion (depth/verdicts untouched, tested at node,
  pipeline, and both API entry paths), Report field + moderate/elevated
  advisory note + flywheel record, `fr_*` knobs, FABRICATION.md S2.4 docs.
  ONE DELIBERATE PLAN DEVIATION: the live smoke (first run 9/10) caught a
  genuine resume fusing to moderate off a single soft signal (ai=possible
  0.45 + rf=unique 0.10, cross_field dropped out ⇒ score 0.318 ≥ 0.30), so
  `band_for_risk` grew a MODERATE corroboration gate (flagged ≥1 OR
  non-clean ≥2; commit d7c23f5) mirroring the ELEVATED ≥2-flags gate —
  strictly more conservative, live re-run 10/10. Also: fr_weight=0 does not
  fully mute a subsystem (documented, not changed); smoke scratch-dir leak
  is a pre-existing pattern across all smoke scripts. 350 tests green.
  PI-2 complete. Next: S3.1 plan.
- **2026-07-19** — S3.1 implementation plan written:
  `docs/superpowers/plans/2026-07-19-s31-ledger-schema-consent.md` (7 TDD
  tasks, branch `s31-ledger-consent`, 350→~395 tests). Scope: new
  `app/ledger/` package — Pydantic contracts + StrEnum taxonomies
  (stage screen/tech/coding/hm, outcome, purpose ledger_write/ledger_read),
  pure clock-free consent logic (`consent.py`: purpose/org scope, always-
  expiring, revocation as point-in-time boundary, naive-UTC coercion for
  SQLite), ORM rows on the shared Base (organizations, consent_grants,
  interview_records, evaluation_events, audit_log), migration
  `0003_evaluation_ledger` (candidate-linked rows CASCADE ⇒ existing DPDP
  erasure sweeps the ledger; orgs survive), `LedgerStore` with write-time
  ConsentError gate on record submission + audit row in the same
  transaction, config knob `ledger_consent_default_ttl_days: 365`,
  direct-store smoke `scripts/smoke_s31.py` (key-less; S3.1 is LLM-free),
  `LEDGER.md`. No HTTP APIs (S3.2), no LLM. Next: execute the plan.
- **2026-07-20** — S3.1 done, subagent-driven on branch `s31-ledger-consent`
  (7 tasks). Delivered per plan: `app/ledger/` contracts + taxonomies, pure
  consent logic (`consent.py`: purpose/org scope, always-expiring,
  revocation as a point-in-time boundary, naive-UTC coercion), ORM rows +
  migration `0003_evaluation_ledger` (candidate-linked rows CASCADE, orgs
  survive), `LedgerStore` (organizations; grant/revoke/status consent;
  `submit_interview_record` raises `ConsentError` without an active
  `ledger_write` grant and stamps the authorizing consent_id;
  `append_event`; audit row written in the same transaction as every
  mutation), config `ledger_consent_default_ttl_days: 365`, direct-store
  smoke `scripts/smoke_s31.py`, `LEDGER.md`. 42 new tests (350→392). TWO
  DEVIATIONS FROM PLAN: (a) migration 0003 landed in Task 3 instead of
  later — the metadata-wide drift guard fires as soon as ledger models are
  imported, so the migration has to exist from that point on; (b) store
  converters normalize datetimes through `as_utc` because SQLite refetch
  returns naive datetimes and pydantic model equality broke on that — the
  plan's converter code was fixed accordingly, tested explicitly. Smoke
  `scripts/smoke_s31.py` run key-less: all 10 checks OK, extraction method
  `heuristic`, exit 0, `SMOKE OK`. One smoke-script bug found and fixed
  in-session (not a product bug): the "mutations audited in order" check
  compared a stale `audit_actions` snapshot taken before `revoke_consent`
  ran, so `consent.revoke` was never in it — fixed by re-fetching
  `audit_for_candidate` after the revoke call, matching the plan's own note
  that revoke is audited as the 4th action. Full suite: 392 passed
  (`pytest -q`). Status board left at `[~]` — final whole-branch review +
  merge is still pending. Next: final whole-branch review + merge.
- **2026-07-20 (2)** — S3.1 closed out. Final whole-branch review (most
  capable model): Ready to merge, one Important finding — caller-supplied
  aware non-UTC datetimes were stored wall-clock by SQLite (tzinfo dropped),
  so an IST-aware revocation would read back 5.5h late: a fail-open window
  once S3.2 accepts API datetimes. Fixed in 4dd09d0: `grant_consent` /
  `revoke_consent` / `submit_interview_record` route `now`/`expires_at`/
  `interviewed_at` through `as_utc` at write; failing-first IST test added
  (393 tests). Also documented `delete_organization`'s cascade semantics
  (org's grants→records→events go; candidate-linked audit rows survive) in
  LEDGER.md + docstring, and bounded `ledger_consent_default_ttl_days`
  (ge=1). Re-review verdict: Ready to merge, unconditional. Accepted
  residuals for S3.2 (logged in `.superpowers/sdd/progress.md`): drift
  guard blind to index/ondelete/nullability drift (cascade on migrated
  schema only proven by smoke), nondeterministic consent_id under
  overlapping grants, consent_status generic denial vs LookupError
  (404-vs-403 shape), org-create TOCTOU IntegrityError mapping, UUID
  tie-break ordering. Merged to main (fast-forward dc822e3→4dd09d0), 393
  green on main, branch deleted. S3.1 COMPLETE. Next: S3.2 plan.
- **2026-07-22** — S3.2 done, subagent-driven on branch `s32-ledger-apis`
  (11 tasks, each spec+quality reviewed; final whole-branch review opus).
  Plan: `docs/superpowers/plans/2026-07-22-s32-ledger-apis.md`. Delivered:
  two HTTP auth planes over `LedgerStore` — ADMIN (`X-API-Key` on `router`:
  `POST/GET /ledger/orgs`, rotate `/api-key`, `DELETE`, consent
  grant/revoke/status) and ORG (`X-Org-Key`→org via `authenticate_org` on a
  dependency-free `org_router`, each handler `Depends(require_org)`;
  `POST /ledger/records` write-consent gated → 403/404, `POST
  /ledger/records/{id}/events` ownership-enforced → 404, `GET
  /ledger/candidates/{id}/records` query-time `ledger_read` enforcement + audit
  of every read attempt allowed/denied in the same txn). Org API keys
  (`secrets.token_urlsafe`, sha256-hashed, rotatable; migration
  `0004_org_api_keys` col + unique index; suspended orgs never authenticate),
  `ledger_api_key_bytes` knob (32, ge=16). Four S3.1 residuals closed:
  deterministic authorizing-grant selection (`consent.py` `_selection_key`:
  org-specific ▸ newest ▸ lowest id), `consent_status` LookupError→404 vs
  denied-200, `create_organization` insert-then-map IntegrityError→ValueError
  (no TOCTOU), drift guard now checks indexes/FK-ondelete/nullability.
  `Services.ledger` injected sharing the candidate DB (conftest builds both on
  one session factory). 29 new tests (393→422). Smoke `scripts/smoke_s32.py`
  (uvicorn HTTP) 9/9 OK exit 0, key-less-capable. One authorized deviation
  across the HTTP test tasks: `asyncio.run(...)` replaced the brief's
  deprecated `asyncio.get_event_loop().run_until_complete(...)`. Final
  whole-branch review (opus): Ready to merge Yes, NO Critical/Important code
  defects; all 13 accumulated Minors triaged DEFER; two recommended doc notes
  added to LEDGER.md (event-append inherits submit-time grant + is swept on
  erasure; a single `ledger_read` grant exposes the candidate's cross-org
  history — reputation-network semantics). Merged to main (fast-forward
  7a9fdcf→a948401), 422 green on main, branch deleted. PI-3 now S3.1+S3.2
  complete. Next: S3.3 plan (coding-round results — schema + ingest only).
- **2026-07-25** — S3.3 done, inline TDD-offline on branch
  `s33-coding-round-results` (6 tasks; spec
  `docs/superpowers/specs/2026-07-25-s33-coding-round-results-design.md`, plan
  `docs/superpowers/plans/2026-07-25-s33-coding-round-results.md`). Design
  decisions taken with user (all recommendations accepted): standalone
  `coding_round_results` table (a peer of `interview_records`, NOT an overload —
  the `stage=coding` interview_record is a coarse pipeline outcome; a coding
  ROUND RESULT is a structured platform assessment); reuse `ledger_write`/
  `ledger_read` consent (no coding-specific purposes); `platform` as a
  `CodingPlatform` StrEnum + `OTHER`/`platform_name` escape; "considered" field
  set (platform, platform_name?, assessment_name?, score, max_score?,
  percentile?, problem_tags[], taken_at, raw{}) so S3.4/PI-4 need no follow-up
  migration. Delivered: contracts + StrEnum, `CodingRoundResultRow` +
  migration `0005_coding_round_results` (drift/index/FK-ondelete/nullability
  guards extended to it), store methods mirroring interview records
  (`submit_coding_round` write-gated + `consent_id`-stamped + `coding_round.submit`
  audit in-txn; `query_coding_rounds_for_org` query-time `ledger_read` + audit of
  every allowed/denied attempt as `coding_round.query`; `coding_rounds_for_candidate`
  raw read), two org-plane endpoints (`POST /ledger/coding-rounds`,
  `GET /ledger/candidates/{id}/coding-rounds`), LEDGER.md S3.3 section. Field
  bounds are data hygiene only — NO scoring/normalization (that's S3.4). No new
  config knob, no LLM. 20 new tests (422→442, `pytest -q` green). Smoke
  `scripts/smoke_s33.py` 7/7 OK exit 0 (submit-403 → grant-write → submit →
  query-403 → grant-read → query-200 [1 result] → DPDP-erase → query-404); the
  run also exercised the live LLM extraction path. Whole-branch self-review
  clean (no Critical/Important; migration↔ORM parity proven by the drift guard).
  Merged to main (fast-forward from 4f63cdc), 442 green on main, branch deleted.
  S3.3 COMPLETE — PI-3 now S3.1–S3.3 done. Next: S3.4 plan (cross-company
  reputation).
- **2026-07-26** — Vision gap analysis written (docs only, no code):
  `docs/superpowers/specs/2026-07-26-veritas-vision-gap-analysis.md`. Audited
  the whole product against the Mercor-for-India reference anatomy
  (ingest/verification/assessment/reputation/intelligence/flywheel/marketplace/
  platform). Key findings: biggest strategic gap is AI interview delivery;
  demand side (job schema, matching, comp bands) entirely absent; candidate-
  facing DPDP surface (auth, my-data portal, first-party consent, retention
  TTLs) needed before identity/KYC or AI interviews can land; identity
  verification + document forensics (experience-letter mills, proxy interviews,
  moonlighting) are the India-specific trust builds. Old flat PI-5 backlog
  superseded by shaped PI-5 (demand side) / PI-6 (candidate side & intake) /
  PI-7 (verification & assessment depth) / PI-8 (scale & learning); standing
  non-goals: payments/payroll, sourcing, native coding assessments. §8 lists
  research items to close at future spec time (DigiLocker/Consent Manager
  terms, Hinglish speech models on the Qwen-tier cost stance, EPFO legality,
  partner payload formats, license-clean comp data). Status board updated;
  S3.4 remains the next action — the vision doc changes nothing about it.
- **2026-07-26 (2)** — Model shortlist researched live (web) + two user
  decisions recorded. (1) **English-first**: launch vertical is IT jobs, so
  interviews/resumes are English (Indian-accented); Hinglish/regional intake
  DEFERRED to later verticals (media/entertainment) — gap-analysis §5/§6 and
  board updated accordingly. (2) `MODELS.md` created (root, beside FLOW/LEDGER
  docs): P1 ASR → Qwen3-ASR 1.7B (Jan 2026, Apache 2.0; Srota Hinglish
  fine-tune noted for the deferred phase), hosted alt Sarvam ASR ₹30/hr
  (DPDP-friendly India hosting); P2 TTS → Kokoro-82M (Indian-English voice),
  hosted alt Sarvam Bulbul; P3 text → Qwen tiers unchanged, Kimi K3
  (2026-07-16, OpenRouter $3/$15) flagged decisive-tier candidate — re-check
  pricing ~2 weeks after its 2026-07-27 open-weights drop; P4 embeddings →
  Qwen3-Embedding (0.6B/8B, top open MTEB v2); P5 reranker → Qwen3-Reranker.
  User actions: Sarvam account (free credits), bookmarks, no OpenRouter
  changes through PI-4. Docs only, no code; S3.4 still next.
- **2026-07-26 (3)** — Cost-first model config applied (config.yaml +
  `app/core/config.py`, all `DEE_*`-overridable knobs). Live OpenRouter pricing
  pulled from the API: swapped `model_reasoning` + `model_scoring` →
  `deepseek/deepseek-v3.2` ($0.269/$0.400 vs qwen3.7-max $1.475/$4.425, ~5–11x
  cheaper, equal quality for our decisive path); qwen3.7-max retained only as
  `model_reasoning_hard`; fast/bulk unchanged. Added inert future-slot knobs
  (`speech_provider`/`asr_model`/`tts_model`/`embedding_model`/`reranker_model`)
  — key finding: **OpenRouter serves audio models on the existing account**
  (voxtral-small-24b ASR $0.10/$0.30, live-pinged OK), so speech needs no new
  signup for v0; Sarvam demoted to prod India-residency option. Verified:
  deepseek-v3.2 + voxtral live-pinged through the project key; 442 offline green;
  full live pipeline smoke `scripts/smoke_s24.py` 10/10 exit 0 on deepseek-v3.2
  (depth solid, fabrication fusion clean). Decision record: `MODELS.md`. Windows
  gotcha logged: config.yaml comments must stay ASCII (cp1252 read). S3.4 still
  the next action.
- **2026-07-26 (4)** — S3.4 done, inline TDD-offline on branch
  `s34-cross-company-reputation` (6 tasks; spec
  `docs/superpowers/specs/2026-07-26-s34-cross-company-reputation-design.md`,
  plan `docs/superpowers/plans/2026-07-26-s34-cross-company-reputation.md`).
  **PI-3 COMPLETE.** One design decision taken with user: negative-signal stance
  = **one corroboration-gated band** (recommended); user delegated the rest.
  Delivered: cross-company reputation as a **derived, `ledger_read`-gated read**
  over `interview_records` + `coding_round_results` — NO new record type, NO
  graph node, NO `Report` field, NO LLM. Pure `app/ledger/reputation.py`
  (the `fabrication/risk.py` pattern): outcome→value code-constant map
  (`withdrawn` excluded), coding normalization (percentile ▸ score/max_score ▸
  excluded), per-obs weight = type·recency-halflife·per-org-reliability,
  **Beta-Binomial posterior** shrunk toward a neutral 0.5 prior, saturating
  confidence. Bands `INSUFFICIENT_DATA/GUARDED/MIXED/FAVORABLE/STRONG` —
  `STRONG` and `GUARDED` (the only negative band) each need ≥2 distinct orgs, so
  single-source high caps at FAVORABLE / single-source low at MIXED (mirrors
  S2.4's ≥2-flags gate). Contracts (`ReputationBand`/`ReputationComponent`/
  `ReputationAssessment`, `advisory=True`) + `Organization.reliability_weight`;
  migration `0006_org_reliability_weight` (nullable col, neutral default 1.0;
  drift guard extended). Store `reputation_for_org` (query-time `ledger_read`,
  audits every attempt allowed/denied as `reputation.query` in-txn, band+counts
  in details) + `set_org_reliability` (admin, `org.set_reliability` audit,
  weight ≥0). Endpoints `GET /ledger/candidates/{id}/reputation` (org plane,
  403/404) + `POST /ledger/orgs/{id}/reliability` (admin, 404/422). `rep_*`
  config knobs (prior, halflife, thresholds, corroboration-orgs, type weights).
  LEDGER.md S3.4 section. 26 new tests (442→468, `pytest -q` green). Smoke
  `scripts/smoke_s34.py` 9/9 OK exit 0 (also exercised live LLM extraction):
  2 orgs × 2 hired + 1 coding ⇒ `band=strong score=0.784 orgs=2 obs=6`;
  reputation-403 → grant read → 200 → set reliability → coherent shift → DPDP
  erase → 404. Whole-branch self-review clean (no Critical/Important; two DEFER
  minors: all-orgs-reliability-0 yields component mean_value 0.0 under a safe
  INSUFFICIENT_DATA band; `_settings()` helper duplicated per test file).
  Reputation is now available to PI-4 ranking as a consent-gated advisory
  feature (never an auto-reject gate). Next: S4.1 plan (feature registry).
- **2026-07-26 (5)** — S4.1 done, inline TDD-offline on branch
  `s41-feature-registry` (10 tasks; spec
  `docs/superpowers/specs/2026-07-26-s41-feature-registry-design.md`, plan
  `docs/superpowers/plans/2026-07-26-s41-feature-registry.md`). **PI-4 started.**
  Two design decisions taken with user (both recommendations accepted, user
  delegated the rest): (1) registry shape = **code-first `@register_feature`
  decorator** (mirrors `@register_domain`), not a DB table; (2) ledger/reputation
  features are **in the seed catalog, tagged `requires_consent`** (enforcement
  deferred to S4.2/S4.3). Delivered a new pure package `app/features/`:
  `schema.py` (FeatureSpec metadata + dtype/source StrEnums + FeatureContext
  point-in-time snapshot with cached `reputation` accessor + FeatureView +
  FeatureVector), `registry.py` (FeatureRegistry with collision guard /
  latest-version / `compute_one` output validation / `compute_view` / manifest,
  `@register_feature` + module-global default registry + `latest_view`),
  `context.py` (`build_context` store assembler — coarse `created_at <= as_of`
  cutoff; full historical slicer is S4.2), and `definitions/` seed catalog: **31
  features** across candidate (12), depth (7), fabrication (5), ledger (4,
  consent-tagged), reputation (3, consent-tagged). `core_v1` default view + one
  config knob `feat_default_view` (no numeric behavior knobs — feature logic is
  code-versioned like domains + the reputation outcome map). NO migration, NO
  HTTP, NO LLM, NO Report field, NO graph node (values/persistence = S4.2;
  serving/ranking = S4.3; labels = S4.4). DPDP: no new candidate-linked table ⇒
  no new erasure path; `build_context` returns None after erasure. `FEATURES.md`
  written (peer of LEDGER.md/FABRICATION.md). 39 new tests (468→507, `pytest -q`
  green). Smoke `scripts/smoke_s41.py` (uvicorn populate → direct feature
  compute) 10/10 OK exit 0 (also exercised the LIVE LLM extraction path):
  candidate → 31-feature vector (years_experience 8.08, depth_score 0.72,
  fabrication low, consent-gated interview_records 2, best_coding_percentile 92,
  reputation.score 0.70); a distinct no-ledger candidate → ledger counts 0,
  percentile missing, reputation insufficient_data. Two pre-exec plan-review
  fixes (report `created_at` cutoff; smoke 2nd candidate needs a distinct email
  or identity-resolution merges it) and two in-flight test fixes (InterviewRecord/
  CodingRoundResult require `id`+`created_at`; reputation unit test needed ≥6 obs
  to clear the confidence floor). No new residuals. Next: S4.2 plan
  (materialization → wide `ml_features` table + point-in-time slicer + export).
- **2026-07-27** — S4.2 done, inline TDD-offline on branch `s42-materialization`
  (9 tasks; spec `docs/superpowers/specs/2026-07-26-s42-materialization-design.md`,
  plan `docs/superpowers/plans/2026-07-26-s42-materialization.md`). Three design
  decisions taken with user (all recommendations accepted, user delegated the
  rest): (D1) consent enforcement = **per-candidate gate, one global platform
  table** — consent-tagged features materialize only under an active `ledger_read`
  grant at `as_of` (org-agnostic: any org / org=NULL), else nulled + reason;
  first-party features always materialize; every decision audited. (D2) storage =
  **compact row-per-vector** with a JSON `feature_values` column (migration-free as
  the catalog grows; wide shape is an export-time pivot). (D3) parquet =
  **CSV always (stdlib) + guarded optional `pyarrow`** (not a core dep). Delivered:
  point-in-time slicer — `CandidateStore.profile_as_of` (newest extraction ≤ as_of)
  and `build_context` now honors `as_of` on profile/report/ledger/consent/reputation
  (stays a raw assembler; consent policy lives in the materializer);
  `consent.has_any_active` (org-agnostic active-grant check) +
  `LedgerStore.materialization_consent` (audited `feature.materialize`, allowed &
  withheld, never raises on withheld); `app/features/materialize.py`
  (`MaterializedVector` + `materialize_candidate`/`materialize_all`, masks
  `requires_consent` features to null when withheld); `ml_feature_vectors` table
  (ORM `FeatureVectorRow` + migration `0007`, unique cut = idempotent upsert,
  CASCADE FK ⇒ DPDP erasure sweeps it, drift/index/FK/nullability guards extended)
  + `FeatureStore` (upsert/get/vectors_for_view, `as_of` keyed naive-UTC);
  `app/features/export.py` (wide `export_view_csv` stdlib pivot in `view.members`
  order; `export_view_parquet` typed per dtype, raises `ParquetUnavailable` when
  pyarrow absent). Reused `feat_default_view` — no new numeric knob, no LLM, no HTTP
  (materialization is a batch/script concern; serving = S4.3). `FEATURES.md` S4.2
  section. 22 new tests (507→529, `pytest -q` green). Smoke `scripts/smoke_s42.py`
  (uvicorn populate → direct materialize/persist/export) 11/11 OK exit 0 (also
  exercised the live LLM extraction path): candidate A (consented, FUTURE-dated
  ledger rows) → allowed, ledger count **0 at now** but **2 later** (point-in-time
  proof: rows that exist now are invisible at the earlier cut), percentile 92 later;
  candidate B (no consent) → consent features **null + masked**, first-party intact;
  wide CSV header in view order; parquet guarded (skipped, pyarrow absent); DPDP
  erase of A cascades its vector away. One smoke-script ordering bug fixed in-session
  (the "two persisted vectors" count was read AFTER the erase — captured pre-erase;
  a script bug, not a product bug). Whole-branch self-review clean (no
  Critical/Important; migration↔ORM parity proven by the drift guard). Merged to
  main (fast-forward), 529 green on main, branch deleted. S4.2 COMPLETE. Next: S4.3
  plan (talent search/ranking API over `ml_feature_vectors`).
- **2026-07-27 (2)** — S4.3 done, inline TDD-offline on branch `s43-talent-search`
  (8 tasks; spec `docs/superpowers/specs/2026-07-27-s43-talent-search-ranking-design.md`,
  plan `docs/superpowers/plans/2026-07-27-s43-talent-search-ranking.md`). Three
  design decisions taken with user (all delegated to the recommendation): (D1)
  **admin plane only** (`X-API-Key`) — reading the S4.2-masked vectors as-is means
  no new consent gate / no new disclosure surface; org-facing job-conditioned
  matching stays PI-5. (D2) **pool-independent normalization** via
  `FeatureSpec.valid_range`/category index (reproducible), pool-min-max fallback
  only for range-less count features. (D3) **drop-term + renormalize + report
  `coverage`** so consent-withheld/absent data never lowers rank. Delivered: pure
  `app/features/ranking_schema.py` (contracts) + `app/features/ranking.py`
  (`apply_filters`/`normalize_value`/`score`, the risk.py pattern — no I/O/clock),
  `FeatureStore.latest_as_of`, `Services.features` wiring (import-cycle-safe:
  TYPE_CHECKING annotation + function-local `build_feature_store`), admin endpoint
  `POST /talent/search` → `SearchResult{advisory=True}` (400 unknown-feature/
  malformed-filter, 422 empty-ranking, 401 no-key, empty-200 unmaterialized view),
  `search_default_limit` knob, FEATURES.md S4.3 section. No new table/migration/LLM;
  DPDP path unchanged (reads rows that already CASCADE on erasure). 35 new tests
  (529→564, `pytest -q` green). Smoke `scripts/smoke_s43.py` (uvicorn + HTTP) 8/8 OK
  exit 0 (also exercised the live LLM ingestion path): three unconsented candidates
  → materialize/persist → ranked senior→mid→junior with contributions, a filter
  narrowed the pool to 2, and consent-withheld candidates ranked with reduced
  `coverage` (reputation dropped) NOT pushed to the bottom. Whole-branch self-review:
  one Important fix (malformed filter value → 400 not 500; catch TypeError at the
  boundary + test) and one Minor cleanup (dropped unused `_ORDER_OPS`); no other
  Critical/Important. S4.3 COMPLETE — PI-4 now S4.1–S4.3 done. Next: S4.4 plan
  (training-set export — features ⋈ outcomes, leakage-free at the `as_of` cut).
- **2026-07-27 (3)** — S4.4 done, inline TDD-offline on branch
  `s44-training-set-export` (9 tasks; spec
  `docs/superpowers/specs/2026-07-27-s44-training-set-export-design.md`, plan
  `docs/superpowers/plans/2026-07-27-s44-training-set-export.md`). **PI-4 COMPLETE.**
  Four design decisions taken with user (all recommendations accepted, user
  delegated the rest): (D1) **ledger-only labels** — the flywheel `outcome` field
  is a permanent `None` placeholder (`report.py`), so interview outcomes + coding
  results are the only real point-in-time label source (flywheel report outcomes
  need a feedback API first — future); (D2) **compact censoring-aware label block**
  (`hired`/`outcome`/`coding_best_percentile`/`event_at`/`lag_days`/`observed`/
  `withheld`) — `observed=False` = right-censored, NOT a negative; (D3) **reuse the
  S4.2 consent decision + audit the join** — a withheld vector's label is withheld
  and its ledger is never read, consistent with masked `ledger.*` features; (D4)
  **library + script deliverable** (no HTTP/table), mirroring S4.2. Delivered: pure
  `app/features/training.py` `build_label` (post-cut-only via **strict `> as_of`** =
  no leakage; terminal-best `hired>offer>advanced>rejected>no_show`, `withdrawn`
  excluded; hire-positive `{hired,offer}`; `event_at`=earliest carrier, `lag_days`;
  `coding_best_percentile`=max post-cut) + orchestrator `build_training_set`
  (reads ledger only when consented, audits every join); contracts
  `training_schema.py` (`TrainingLabel`/`TrainingExample`);
  `LedgerStore.audit_training_label` (audits reused decision as `training.label`);
  `export.py` shared `feature_columns`/`vector_cells` helpers +
  `export_training_csv`/`export_training_parquet` (wide pivot + 7 `label_*` cols);
  FEATURES.md S4.4 section. No new table/migration/HTTP/LLM/config knob; DPDP path
  unchanged (labels recompute from CASCADE-swept ledger rows; `training.label`
  audit rows candidate-linked + CASCADE). 20 new tests (564→584, `pytest -q` green).
  Smoke `scripts/smoke_s44.py` (uvicorn + HTTP populate → direct materialize →
  build+export) 10/10 OK exit 0 (also exercised the live LLM ingestion path): A
  consented → post-cut HIRED label (`hired=True`, `lag~30d`) while its features stay
  point-in-time (pre-cut interview count 0 — the post-cut record drives the label
  but never leaks into features); B consented but only a PRE-cut hired → censored
  (`observed=False`, `hired=None` — pre-cut positive does NOT leak); C unconsented →
  `withheld=True` label + consent-masked features + `training.label` withheld audit;
  labeled CSV header ends with the 7 label columns; parquet guarded. One correctness
  fix over the plan draft (smoke `T=now` captured after ingest so the cut post-dates
  the extraction `created_at`, else `profile_as_of` returns None and materialize
  yields None). Next: whole-branch review + merge, then shape PI-5 (demand side).
