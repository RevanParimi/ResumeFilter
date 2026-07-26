# Veritas — Vision Gap Analysis & Forward Design (Mercor-for-India)

**Date:** 2026-07-26
**Status:** Planning reference — approved direction, no sprint commitment implied.
**Audience:** Any future session (human or agent). Read `docs/ROADMAP.md` first;
read this second when planning beyond the current sprint.
**Relationship to existing specs:** Extends (does not replace)
`2026-07-06-veritas-talent-platform-design.md`. That spec defined PI-1..PI-4 and
a PI-5 backlog; this document audits the whole product against the full
"Mercor-for-India" vision, names every capability gap, and shapes the backlog
into designed PIs so planning never restarts from scratch.

---

## 1. How to use this document (new-chat pickup)

- **Do not derail the current sprint.** The ROADMAP's "Current state" always
  wins for *what to do next*. As of this writing that is **S3.4 (cross-company
  reputation)** — unchanged by this document.
- When a PI completes and the next one needs shaping, come here: each gap below
  names its landing zone (existing sprint, new PI, or explicit non-goal).
- Every new capability inherits the standing conventions (§7). No exceptions
  without an explicit user decision recorded in the ROADMAP.

## 2. The vision, restated

**Veritas is the trust infrastructure for an Indian talent marketplace.**
A Mercor-style platform has two halves: (a) an *intelligence layer* that
ingests, verifies, evaluates, and ranks talent, and (b) a *marketplace layer*
that matches talent to demand and settles the transaction. Our strategy —
decided 2026-07-06 and still correct — is to build (a) first and deepest,
because in the Indian market **trust is the scarce commodity**: fabricated
resumes, proxy interviews, fake experience letters, and resume farms are
endemic, and no incumbent (Naukri, LinkedIn, Instahyre, Cutshort) solves
verification-at-depth. Mercor's moat is AI-vetting + outcome flywheel; ours is
that **plus** a consent-first cross-company evaluation ledger that DPDP makes
legally survivable — a network-effect asset none of the US-modeled clones can
copy-paste into India.

The end-state product (the "far vision"):

1. A candidate uploads a resume (or profile) once → extracted, normalized to
   Indian conventions, fabrication-screened, depth-evaluated.
2. Verified skill signals accumulate: coding-round results, AI-conducted
   interviews, cross-company interview outcomes — all consent-gated, all
   audited, all revocable.
3. A reputation + feature layer turns those signals into rankings and
   role-matches that employers query.
4. Employers pull from a pool that is *pre-trusted*, not merely pre-filtered;
   candidates own their data and see who touched it.

## 3. What exists today (asset inventory — honest)

| Subsystem | State | Notes |
|---|---|---|
| Depth-eval pipeline (`app/graph`, `app/domains`) | **Live** | Claim → probe → verdict; advisory-only; deterministic fallback; flywheel records. Single domain registered (genai). |
| Candidate backbone (`app/candidates`) | **Live** (PI-1) | Extraction w/ confidence + provenance spans; versioned store; identity resolution via hashed email/phone; DPDP hard-delete paths. |
| India normalization (`app/candidates/normalize`) | **Live** (S1.4) | ~85-skill taxonomy, degree/CGPA-out-of-10, IIT/IIM/NIT/IIIT tiers, ~60-employer aliases, metro/tier-2 gazetteer, notice-period parser. Static tables — no learning loop. |
| Fabrication defense (`app/fabrication`) | **Live** (PI-2) | AI-text signals, cross-field timeline forensics, MinHash resume-farm detection, fused advisory `fabrication_risk`. Text-only — no document/image/identity forensics. |
| Evaluation ledger (`app/ledger`) | **Live through S3.3** | Orgs + org API keys; purpose-scoped/expiring/revocable consent; interview records; coding-round results (ingest only); audit-of-every-touch; erasure cascades. |
| Reputation | **Next (S3.4)** | Bayesian aggregation, recency decay, per-org reliability. |
| ML feature store / ranking (PI-4) | **Designed, not built** | Registry → point-in-time materialization → search/ranking API → training export. |
| Infra | SQLite (PG-shaped), memory vectorstore, single-tenant, shared-secret admin key + org keys. No candidate-facing auth. |

**Carried residuals** (all DEFER, tracked in ROADMAP/`.superpowers/sdd/progress.md`):
event-append inherits submit-time grant; `create_organization` broad
IntegrityError mapping; stale "(S3.1)" docstrings; `revoke_consent` 200-on-unknown;
0004 downgrade untested.

## 4. Reference anatomy — what a Mercor-class platform contains

Capability map used for the audit (from public knowledge of Mercor-style
platforms, generalized):

```
A. INGEST & PROFILE      resume/profile parsing · enrichment (GitHub etc.) · normalization
B. VERIFICATION          document forensics · identity/KYC · fraud & farm detection
C. ASSESSMENT            coding assessments · AI interviews (voice/video) · work samples
D. REPUTATION & RECORDS  cross-company outcomes · verified history · consent/compliance
E. INTELLIGENCE          feature store · ranking · matching · salary/market intelligence
F. FLYWHEEL              outcome capture · model improvement · calibration against hires
G. MARKETPLACE           job requisitions · employer UX · payments/payroll · contracts
H. PLATFORM              auth/multi-tenancy · scale infra · observability · portability
```

## 5. Gap analysis

Legend: ✅ have · 🟡 partial · ❌ missing. Each gap names its **landing zone**.

### A. Ingest & profile — 🟡 strong core, narrow intake

| Gap | Why it matters | India angle | Landing zone |
|---|---|---|---|
| Only resume text/PDF intake; no LinkedIn/GitHub *profile* ingestion as first-class sources | Mercor ingests profiles, not just documents | Indian candidates under-maintain LinkedIn; GitHub + resume is the richer pair | **PI-6.1** |
| GitHub used only as probe evidence, not as a structured skill signal | Repo analysis is a verifiable skill source | Strong OSS signal among tier-2/3 candidates who lack brand-name employers | **PI-6.1** |
| Normalization tables are static | Taxonomies drift (new skills, new unicorns) | Indian startup employer churn is fast | **PI-6.2** (curation loop, still deterministic files — no auto-learning without review) |
| No regional-language / Hinglish resume handling | Widens the funnel beyond English-polished resumes | Tier-2/3 talent discovery is the underserved market — **but the launch vertical is IT jobs, which are English-resume territory** | **DEFERRED (user decision 2026-07-26):** English-first until the IT vertical matures; revisit with media/entertainment verticals. Falls out of PI-6.2 scope |

### B. Verification — 🟡 text forensics done, identity/document forensics absent

| Gap | Why it matters | India angle | Landing zone |
|---|---|---|---|
| No identity verification (liveness, doc-based KYC) | Proxy candidates defeat all downstream evaluation | **Proxy interviewing is the #1 Indian hiring fraud**; DigiLocker/Aadhaar-adjacent flows exist but are consent-radioactive — must be candidate-initiated, purpose-scoped, never stored raw | **PI-7.1** (design consent flow first; store only verification *outcomes*, never documents) |
| No experience-letter / payslip / certificate forensics | Fake experience certificates are an industry in India ("experience letter mills") | Detectable via template/metadata/issuer heuristics + issuer-domain checks | **PI-7.2** |
| No moonlighting / dual-employment signal | Employers care post-2022; ties to timeline forensics we already have | EPFO-based checks are third-party data — **only** consent-gated, candidate-pulled; otherwise out | **PI-7.2** (advisory flag from first-party timeline evidence only, unless candidate-consented pull) |
| Farm detection is single-DB MinHash | Fine now; breaks at scale / cross-tenant | — | **PI-8** (embeddings + ANN when real vectorstore lands) |

### C. Assessment — ❌ the biggest strategic gap vs Mercor

| Gap | Why it matters | India angle | Landing zone |
|---|---|---|---|
| **No AI interview delivery** (voice/video, structured scoring) | This is Mercor's signature capability and primary signal source | **English-first (Indian accents)** — IT-vertical interviews are English; Hindi/code-switching deferred to later verticals. Low-bandwidth (audio-first, not video-first); proxy-detection hooks (voice consistency vs later rounds) | **PI-7.3** (largest single build; text/audio first, video later; every score advisory + human-reviewed) |
| No native coding assessment | We only *ingest* third-party results (S3.3, deliberate) | Third-party ingest is the right wedge — build native only if partners don't cover | **Non-goal for now** — revisit after PI-7 |
| No work-sample / take-home evaluation | Secondary signal | — | Backlog (PI-9+) |

### D. Reputation & records — 🟡 best-in-class consent core, missing candidate face

| Gap | Why it matters | India angle | Landing zone |
|---|---|---|---|
| Reputation aggregation not built yet | The payoff of the whole ledger | — | **S3.4 (current)** |
| No candidate-facing auth or portal ("who saw my data, revoke here") | DPDP grants rights the product must surface; trust is the brand | DPDP data-principal rights: access, correction, erasure, grievance | **PI-6.3** (candidate auth + transparency endpoints over the existing audit log — the data is already there) |
| Platform records consent *on behalf of* candidates (admin-plane) | Fine for pilot; not for production DPDP posture | DPDP Consent Manager interop is emerging ecosystem | **PI-6.3** first-party consent UX; consent-manager integration backlog |
| Retention policies absent (data lives until erased) | DPDP purpose-limitation implies retention limits | — | **PI-6.3** (TTL sweep job, config-driven) |

### E. Intelligence — 🟡 designed (PI-4) but demand-side blind

| Gap | Why it matters | India angle | Landing zone |
|---|---|---|---|
| PI-4 as designed | Feature store, ranking, export | — | **PI-4 (next PI, as planned)** |
| **No job/requisition schema at all** — ranking without a target role | Matching needs demand-side objects: role, must-have skills, comp band, location/remote, notice tolerance | Notice-period economics (30–90 days, buyout math) is a *first-class matching feature* in India, not metadata | **PI-5.1** (job schema + role-conditioned ranking on top of PI-4's generic ranking) |
| No salary/market intelligence | Comp banding is core employer value | CTC structure (fixed/variable/ESOP), city-tier differentials | **PI-5.2** (starts as static bands + observed offers from ledger outcomes; advisory only) |
| Embeddings are fake (memory vectorstore) | Semantic skill match needs real vectors | — | **PI-8** |

### F. Flywheel — 🟡 capture exists, learning loop doesn't

| Gap | Why it matters | India angle | Landing zone |
|---|---|---|---|
| Flywheel records written, never consumed | Mercor's compounding advantage is models trained on outcomes | — | **PI-4 S4.4** exports the training set; actual model training/calibration loop = **PI-8** |
| No calibration measurement (predicted vs actual outcomes) | Needed to prove the product works | — | **PI-8** (offline eval harness over ledger outcomes) |

### G. Marketplace — ❌ deliberate, stays mostly out

| Gap | Landing zone |
|---|---|
| Employer dashboard/UX | **PI-5.3** (thin read-only dashboard over search + reports; API-first stays primary) |
| Payments/payroll/contracts (UPI, TDS/GST, contractor compliance) | **Explicit non-goal.** Partner/integrate; never build in this repo. |
| Sourcing/outreach tooling | **Explicit non-goal** for now. |

### H. Platform — 🟡 pilot-grade, known path

| Gap | Landing zone |
|---|---|
| Postgres migration (schema already PG-shaped) | **PI-8** (connection-string + CI matrix; low risk by design) |
| Real embeddings + vectorstore | **PI-8** |
| Candidate auth (see D) / org self-serve onboarding | **PI-6.3** / PI-8 |
| Observability beyond structlog (metrics, tracing) | **PI-8** |
| Multi-tenancy | Backlog — single-tenant until a real second tenant exists (YAGNI) |

## 6. Revised PI map (proposal — supersedes the old flat "PI-5 backlog")

Sequencing logic: **finish the trust spine (PI-3→PI-4), then monetizable
demand-side (PI-5), then candidate-side DPDP maturity + intake breadth (PI-6),
then the two big verification/assessment builds (PI-7), then scale/learning
(PI-8).** PI-5 before PI-6/7 because employer-visible value funds everything
else; PI-6 before PI-7 because AI interviews and KYC *require* the
candidate-facing consent/auth surface PI-6 builds.

```
PI-3  EVALUATION LEDGER                    [S3.1–S3.3 done · S3.4 next]
PI-4  ML FEATURE STORE & RANKING           [as designed: S4.1–S4.4]
PI-5  DEMAND SIDE (NEW)
 ├ S5.1 Job/requisition schema + role-conditioned match-ranking
 ├ S5.2 Comp intelligence v0 (static bands + ledger-observed offers, advisory)
 └ S5.3 Thin employer dashboard (read-only over search/reports)
PI-6  CANDIDATE SIDE & INTAKE (NEW)
 ├ S6.1 Profile-source ingestion (GitHub-as-signal; LinkedIn export parsing)
 ├ S6.2 Normalization curation loop  [multilingual/Hinglish intake DEFERRED —
 │      English-first for the IT vertical, user decision 2026-07-26]
 └ S6.3 Candidate auth + DPDP portal (my-data, who-accessed, revoke, retention TTLs,
        first-party consent capture replacing admin-plane consent)
PI-7  VERIFICATION & ASSESSMENT DEPTH (NEW — the Mercor-parity PI)
 ├ S7.1 Identity verification w/ consent-first design (outcomes stored, never docs)
 ├ S7.2 Document forensics (experience letters/payslips) + moonlighting advisory
 └ S7.3 AI interview delivery v0 (structured, audio-first, English w/ Indian
        accents [code-switch deferred], proxy-detection hooks; advisory scoring
        into ledger as a new record type)
PI-8  SCALE & LEARNING (NEW)
 ├ S8.1 Postgres cutover + real embeddings/vectorstore + ANN farm detection
 ├ S8.2 Calibration harness (predicted vs ledger outcomes) + model improvement loop
 └ S8.3 Observability + org self-serve onboarding
NON-GOALS (standing): payments/payroll/contracts · sourcing/outreach ·
native coding assessments (revisit post-PI-7) · multi-tenancy (until needed)
```

Each PI still gets its own brainstorm → spec → per-sprint plan when its turn
comes; the sprint bullets above are scoping stakes, not commitments.

## 7. Non-negotiables that extend to every new capability

Unchanged from the 2026-07-06 spec, restated because PI-6/7 will test them:

1. **Advisory only, forever.** AI interview scores, identity checks, moonlighting
   flags — all advisory, human-decided, never auto-reject. This is both ethics
   and (under DPDP + Indian employment practice) legal prudence.
2. **Consent before signal.** Any third-party or biometric-adjacent data
   (KYC, EPFO, voice) is candidate-initiated and purpose-scoped through the
   *existing* consent machinery — new purposes join `ConsentPurpose`, they don't
   bypass it. Store verification outcomes, never source documents/biometrics.
3. **Deterministic fallback for every LLM step** — an AI interview still needs a
   no-key degradation path (structured question bank + rubric scoring).
4. **TDD offline; smoke per sprint; Postgres-shaped SQLite until PI-8.**
5. **Erasure sweeps everything** — every new candidate-linked table CASCADEs.

## 8. Knowledge gaps to close during future planning (not now)

Flagged honestly so a future session budgets research time:

- DPDP Consent Manager ecosystem maturity + DigiLocker API terms (S7.1 spec).
- Speech models for Indian-accented **English** w/ economical inference (S7.3
  spec); must fit the OpenRouter/Qwen-tier cost stance. Shortlist researched
  2026-07-26 → see `MODELS.md` (Qwen3-ASR / Kokoro / Sarvam hosted; Kimi K3
  pricing re-check pending). Hinglish/code-switch models: deferred phase.
- EPFO/UAN data-access legality for consent-gated moonlighting checks (S7.2) —
  if legally murky, first-party timeline forensics only.
- Third-party assessment platforms' webhook/export formats (validates S3.3
  schema against real payloads when a partner appears).
- Comp-band data sources that are license-clean (S5.2).

## 9. Immediate next action (unchanged)

**S3.4 — cross-company reputation**, per ROADMAP. It now has two record types
to aggregate (interview records + coding rounds) and this document changes
nothing about it. After PI-4 completes, the next planning conversation starts
at §6 of this document.
