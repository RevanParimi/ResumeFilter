# Veritas Roadmap — living plan (update every session)

> **New chat? Start here.** Read this file top to bottom, then open the spec:
> `docs/superpowers/specs/2026-07-06-veritas-talent-platform-design.md`.
> Work happens sprint by sprint: each sprint gets a spec/plan under
> `docs/superpowers/`, is built TDD-offline, and ends with `pytest -q` green
> plus a local smoke run. Update the status board + "Current state" section
> below before ending any session.

## ▶ Current state

- **Current sprint:** PI-4 in progress — **S4.2 (materialization) COMPLETE**.
  Next is **S4.3 — talent search/ranking API** (filters + composite score over
  the materialized `ml_feature_vectors`; advisory, never an auto-reject gate).
- **Next action:** Write the S4.3 plan. S4.2 shipped the materialization layer:
  `build_context` is now a true point-in-time slicer (`CandidateStore.profile_as_of`
  + `as_of` on every axis), `LedgerStore.materialization_consent` (org-agnostic
  `has_any_active` ledger_read gate, audited `feature.materialize`),
  `app/features/materialize.py` (consent-masking materializer → `MaterializedVector`),
  the `ml_feature_vectors` table (migration `0007`, compact JSON row-per-cut,
  CASCADE erasure) + `FeatureStore` (idempotent upsert), and `app/features/export.py`
  (wide CSV always, guarded optional parquet). S4.3 ranks/searches over these rows;
  its seam is the JSON `feature_values` column (add a per-feature projection/index
  when the query shape is known — no change to how S4.2 writes). S4.4 then joins
  outcomes to the honest `as_of` cut for a leakage-free training set.
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
├── PI-4  ML FEATURE STORE & RANKING
│   ├── [x] S4.1  Feature registry (versioned definitions over candidate +
│   │            eval + ledger data)
│   ├── [x] S4.2  Materialization → wide ml_features table + CSV/parquet
│   │            export; point-in-time correct (no label leakage)
│   ├── [ ] S4.3  Talent search/ranking API (filters + composite score)
│   └── [ ] S4.4  Training-set export — features ⋈ outcomes (flywheel+ledger)
│
├── PI-5  DEMAND SIDE (shaped, not yet spec'd) — job/requisition schema +
│        role-conditioned matching · comp intelligence v0 · thin employer
│        dashboard  (see 2026-07-26 vision gap analysis, §6)
├── PI-6  CANDIDATE SIDE & INTAKE (shaped) — profile-source ingestion (GitHub/
│        LinkedIn) · normalization curation loop · candidate auth + DPDP portal
│        (my-data / who-accessed / revoke / retention TTLs)
│        [multilingual/Hinglish intake DEFERRED — English-first, 2026-07-26]
├── PI-7  VERIFICATION & ASSESSMENT DEPTH (shaped) — consent-first identity
│        verification · document forensics + moonlighting advisory · AI
│        interview delivery v0 (audio-first English w/ Indian accents,
│        advisory, proxy-detection hooks; model shortlist in MODELS.md)
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
