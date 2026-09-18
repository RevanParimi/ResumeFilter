**Veritas codebase review — 7 September 2026**

This is the original audit snapshot. Subsequent implementation status is in
[PROGRESS.md](PROGRESS.md): the foundations batch addresses unsafe email/phone
fallback, shared provenance leakage, and feature snapshot pool selection.
Other findings remain open unless the handoff explicitly marks them complete.

Veritas has a substantial backend and a partially connected product UI. Its strongest foundations are explicit schemas, domain separation, offline testability, advisory outputs, and database-backed ownership and consent controls. Its largest weaknesses are at subsystem boundaries: identity resolution becomes authentication, shared evidence becomes candidate-specific evidence, historical consent becomes present authorization, and per-candidate snapshots become a searchable population.

This is a source review with local verification, not an assessment of a running production installation. No live LLM, email, GitHub, or verification-provider requests were made by the audit probes. No application source was changed. Existing modifications to `data/veritas.db` were present before the review.

**Scope and verification**

The repository contains 179 Python modules under `src/app`, approximately 28,300 Python lines including comments and blank lines, 253 test modules, 101 route decorators in `api/routes.py`, and a 3,213-line UI document. I traced ingestion, evaluation, provenance, authentication, candidate identity, screening, erasure, feature materialization, matching, interview scoring, verification, and UI integration. Smaller modules were assessed through their callers and tests; this is not a claim that every line or external integration was executed.

- Full suite in the project's `.resume` environment: **2,140 passed, 42 warnings, 340.90 seconds** on Python 3.13. The focused probes were also rerun in that environment.
- The initial system-Python run found missing Alembic. Continuing collection ran 1,647 tests successfully, with 3 failures and 51 collection errors all attributable to the same missing import. This was an interpreter/dependency mismatch, not evidence of 54 independent application bugs.
- `node scripts/check_ui_bindings.js`: all 402 distinct bindings resolved across nine states.
- JavaScript syntax checks passed for `frontend/api.js` and `frontend/support.js`.
- Focused probes reproduced the behaviors below using fake providers, synthetic identities, in-memory stores, and a local FastAPI TestClient.
- PostgreSQL, real browser rendering, live model quality, production load, and external delivery were not validated in this review.

The reproducibility artifacts are local ignored files: `.pytest_cache/review_probes.py`, `.pytest_cache/review-probe-results.json`, and `.pytest_cache/review-suite-venv.txt`.

**Current features and their actual maturity**

| Area | Implemented capability | Practical qualification |
|---|---|---|
| Resume evaluation | PDF/text ingestion; claims; rules plus optional LLM plausibility; GitHub grounding; probes; depth bands; explainable reports | Two domains: GenAI and Data Engineering. Offline behavior uses deterministic heuristics. |
| Candidate backbone | Structured extraction, confidence/source spans, email/phone deduplication, resume versions, India-focused normalization, extraction coverage | Identity matching has an authentication consequence described below. |
| Fabrication signals | Writing-style signals, timeline inconsistencies, near-duplicate fingerprints, fused risk bands | Advisory heuristics; implementation does not establish measured fraud-detection accuracy. |
| Employer screening | Tenant-owned uploads and reports, batches, processing, retries, queue sorting, summaries, outcome recording | Processing is driven by HTTP calls from the browser; no autonomous worker. |
| Authentication | Org signup, candidate signup/claim, operator login, OTPs, cookies, API keys, CSRF, session listing/revocation, rate limits | Substantial implementation; OTP consumption and identity binding need correction. |
| Evaluation ledger | Interview records, events, coding-round results, offers, purpose/org-scoped consent, access audit, reputation | A coding-result store, not an executable coding assessment platform. |
| Features and ranking | Versioned feature definitions, materialization, talent search, CSV/optional Parquet export, training-label joins | No trained ranking model. Default population snapshots are broken; cached consent needs rechecking. |
| Demand side | Jobs, skill/location/experience matching, compensation estimates, employer dashboard | Job matching uses profile-derived fit; it is not a learned technical-quality ranking. Compensation starts with explicitly illustrative seed bands. |
| Profile enrichment | GitHub signals, candidate-provided LinkedIn exports, taxonomy curation | LinkedIn export parsing is implemented; this is not a live LinkedIn integration. |
| Candidate portal | Data access, consent controls, access history, correction/grievance requests, sessions, erasure | Database erasure exists, but evaluation text survives elsewhere. |
| Verification | Self-attestation, contact challenges, manual review, payslip/experience-letter checks, employment-overlap signals | Contact delivery is unwired; government ID and EPFO adapters explicitly remain unimplemented. Document heuristics do not authenticate an issuer. |
| Interviews | Session lifecycle, report-derived questions, text/audio input, transcription, scoring, advisory proxy signals | Backend implemented; UI simulated; deterministic scoring is easily gamed. |
| Operations and quality | Migrations, boot checks, structured logs, counters, retention sweep, signal-quality analysis with sample/class refusal rules | Health is shallow; counters are process-local; empirical effectiveness still needs representative labeled data. |
| Browser UI | Connected auth, screening, reports, portal/consent/session flows, role and compensation views | `evaluate`, `interview`, `adminorgs`, `adminusers`, and `curation` are still mock screens, including when the correct account type is signed in. |

**Highest-priority confirmed findings**

1. **High — unverified resume contact data can bind a new login email to another candidate.**

   `CandidateStore._resolve_candidate` falls back to matching a phone hash. `_refresh_identity` then fills an empty email hash from the new upload. Candidate login treats that email hash as the account-to-person link. For an existing phone-only candidate, a later upload containing the same phone and an attacker-controlled email joins the existing identity. A valid OTP for the attacker's own email then resolves to that candidate, giving access to candidate portal data and actions.

   The probe reproduced both the merge and a resulting candidate session pointing at the original record. This requires an upload path and a matching phone-only record; it is not a demonstrated takeover of every already-email-bound account. Separate asserted resume contacts from verified login identities. Contact changes and identity merges need a verified binding or explicit review.

   Evidence: `src/app/candidates/store.py:171`, `:198`; `src/app/auth/service.py:486`.

2. **High — provenance crosses evaluation boundaries.**

   The provenance node adds GitHub evidence to a shared vector store and queries the entire collection without an evaluation/candidate/repository filter. The probe evaluated Alice and then Bob using the same service bundle; Bob received both `BOB_ONLY` and `ALICE_ONLY` evidence. The query also runs for every claim when any documents were gathered, including claims without their own anchor. This can create false corroboration and disclose another evaluation's evidence association.

   Retrieval should be limited to evidence authorized for the current evaluation, with provenance metadata and an explicit relevance threshold. A per-evaluation in-memory index is sufficient for the present workload. The no-link path currently skips retrieval; contamination was reproduced when Bob supplied his own link.

   Fetch status also needs a separate representation: the GitHub client returns error messages as evidence strings, and plausibility marks every string without "does not exist" as supporting evidence. A 429 or transport failure therefore receives the wrong polarity.

   Evidence: `src/app/graph/nodes/provenance.py:48`; `src/app/services/vectorstore.py:74`, `:108`; `src/app/graph/nodes/plausibility.py:124`.

3. **High — default materialization makes most candidates disappear from search.**

   The materialization route passes `as_of=None` separately for each candidate. `build_context` resolves that to a fresh timestamp each time. Search and job matching subsequently choose the globally latest timestamp and require exact timestamp equality. Two materialized candidates produced two timestamps and a default search pool of one. The HTTP route still reported `materialized: 2` and `as_of: null`.

   Resolve one timestamp before the batch loop and return it. Also define what partial refreshes mean: updating one candidate should not accidentally replace the discoverable population. Either publish complete snapshots or query each candidate's latest eligible vector.

   Evidence: `src/app/api/routes.py:2249`; `src/app/features/context.py:39`; `src/app/features/store.py:95`; `src/app/matching/store.py:185`.

4. **High — erasure does not erase the evaluation flywheel's claim text.**

   Every report writes verbatim claim text and report IDs to the flywheel. Production uses an append-only JSONL writer with no erase operation. Portal erasure deletes candidate-linked SQL records and login state but cannot reach this file. The probe deleted the candidate and report successfully while four matching claim records remained. Removing a database ID does not anonymize free-form text.

   Store this material in a deletable, candidate-linked system with an explicit retention/purpose policy, or stop retaining verbatim claims. Include derived stores and deletion during an in-flight evaluation in the erasure tests.

   Evidence: `src/app/graph/nodes/report.py:100`; `src/app/services/flywheel.py:43`; `src/app/portal/service.py:195`.

5. **Medium — one login OTP can create two sessions under an interleaving.**

   Challenge lookup, validation, deletion, and session creation use separate transactions. Deletion neither compares the exact challenge version nor reports whether this caller consumed it. A controlled interleaving let both verification calls validate the same challenge and establish distinct sessions. Concurrent attempt increments are also read/modify/write operations.

   Consume a specific challenge atomically using a conditional write/lock, then establish the session only for the successful consumer. Preserve the existing rate limiter. The probe simulated the interleaving directly; no production race or PostgreSQL load test was performed.

   Evidence: `src/app/auth/service.py:361`, `:402`; `src/app/auth/store.py:320`, `:326`, `:336`.

6. **Medium — malformed LLM output can crash the supposedly resilient evaluation.**

   `_llm_assessment` catches failures during the provider call, but float conversion and collection parsing occur outside the protected block. A returned object containing `coherence: "not-a-number"` raised `ValueError` rather than falling back. Null arrays and wrong top-level JSON shapes expose related unvalidated boundaries. `_extract_json` can return non-dict JSON despite its dict annotation.

   Validate every provider response into a constrained schema, including finite numeric values, before use. Handle invalid output as a model failure and preserve deterministic scoring. Tests should cover syntactically valid but structurally wrong JSON, not only transport failures.

   Evidence: `src/app/graph/nodes/plausibility.py:58`, `:66`; `src/app/services/llm.py:34`.

7. **High product-quality gap — the interview rubric rewards keyword repetition.**

   Specificity counts numeric/skill tokens, ownership counts pronouns, depth searches for literal expected phrases, and consistency gives full credit for any matching profile term. Repeating `I Python 123 retrieval` twenty times produced `1.0` on all four dimensions for a Python profile and a retrieval signal. This is a rubric stress test, not a claim about every interview configuration, but it demonstrates that scores can be detached from technical substance. Confidence also rewards answer length and coverage.

   Add repetition and relevance checks, count distinct concrete details, and evaluate reasoning against an anchored human rubric. Calibrate with good paraphrases and fluent nonsense. Keep the current results clearly experimental until those comparisons pass.

   Evidence: `src/app/interview/scoring.py:55`, `:65`, `:74`, `:97`, `:181`.

8. **Medium — invalid PDFs are reported as successful evaluations.**

   The ingest graph node records PDF parsing errors in internal state and continues. The report omits that error state. Sending a malformed PDF to `/evaluate` returned HTTP 200, a saved report, zero verdicts, and `insufficient_signal`, with no parsing diagnostic in the report. The candidate-ingest route instead rejects malformed PDFs. Whitespace-only text follows a similar empty-input path.

   Validate input before starting evaluation and return an explicit parse failure. Keep genuinely sparse resumes distinguishable from unreadable inputs. Apply text-size limits after PDF extraction too; `/evaluate` currently checks encoded input size but does not recheck extracted text length.

   Evidence: `src/app/graph/nodes/ingest.py:20`; `src/app/api/routes.py:503`, `:609`; `src/app/graph/nodes/report.py:79`.

9. **Medium — consent revocation does not invalidate materialized consent decisions.**

   The probe revoked an active read grant, but the stored vector retained `consent_state.allowed=True` and a non-null consent-tagged feature. Talent search consumes stored values, export writes them directly, and training joins decide whether to read outcomes from the cached flag. Revocation updates the grant only. This concerns platform search/export/training; the probe did not demonstrate an unauthorized employer reading a ledger record through its consent-gated route.

   Recheck current authorization at the serving/export/training boundary, separately from historical feature timestamps. Invalidate or mask derived data as required by the declared revocation policy. A historical consent decision is not itself current authorization.

   Evidence: `src/app/ledger/store.py:394`; `src/app/features/training.py:109`; `src/app/features/export.py:35`; `src/app/api/routes.py:2153`.

**Incomplete capabilities and additional technical risks**

- **Verification OTP delivery is missing.** `VerificationService` defaults to `NullNotifier`, and its production builder never injects a working notifier. Both contact methods declare themselves implemented. The route exposes the code only behind local debug settings, so a production candidate receives a pending challenge whose code is discarded. Login's SMTP client does not fix this separate path. Wire delivery or explicitly refuse unavailable methods. See `src/app/verification/service.py:88`, `:169`, and its builder; `src/app/verification/otp.py:66`.
- **Five UI screens simulate work.** `runEvaluate` advances a timer; interview handlers manipulate local state; operator and curation screens use constants. The mock explanation says the endpoints are on another account plane even for users on the correct plane. Wiring those workflows is a feature completion task. See `frontend/Veritas.dc.html:2131`, `:2749`; `frontend/api.js:224`.
- **Concurrent ingest is not fully protected.** Candidate contact hashes are indexed but not unique, and ingest uses lookup-then-create. Resume versions use `max(version)+1` under a unique constraint without conflict recovery. Multiple workers can create duplicate identities or fail a valid upload. This is a source-identified race, not a reproduced PostgreSQL result. See `src/app/candidates/models.py:43`; `src/app/candidates/store.py:96`, `:136`.
- **Processing has no durable executor.** A request claims several items at one timestamp and evaluates them sequentially. Browser closure stops future processing calls; retries or expired leases can repeat model work. The service ignores the boolean result of `complete`/`fail`, so reported counts can include results whose lease was lost. Add one managed worker and renewal/idempotency rules when uninterrupted batches become a product requirement. See `src/app/screening/service.py:187`; `src/app/screening/store.py:256`.
- **Blocking work occurs inside async handlers.** SQLAlchemy sessions, SMTP, PDF extraction, file writes, and vector-store operations are synchronous. A slow SMTP send or large PDF can block the worker's event loop. Start by moving blocking boundaries off-loop and measuring concurrent request latency; a full async database rewrite is not a prerequisite.
- **Payload and computation bounds are incomplete.** Input models deserialize before most route size checks. Batch uploads have per-item bounds but no explicit aggregate body-byte bound; PDFs are fully decoded and extracted without OCR, page-count, or extraction-time limits. Add an early body limit and bounded document processing. See `src/app/api/routes.py:1115`; `src/app/core/pdf.py:15`.
- **Cross-worker state can diverge.** Taxonomy edits refresh a process-global overlay only in the editing worker; other workers load it at startup. Metrics are likewise process-local, so a scrape behind worker load balancing is not a process-wide aggregate. See `src/app/curation/service.py:73`, `:104`; `src/app/metrics/registry.py:57`.
- **Runtime data is tracked.** `git ls-files data` includes `data/veritas.db`, and it was already modified when the review began. I did not inspect its records. Use deterministic seed fixtures instead of committing a working database; removing tracking would not remove copies already in history. `.env` files are ignored and were not printed.
- **Readiness and diagnostic limits remain.** `/healthz` reports configuration rather than exercising storage availability. Provider usage/cost and latency-percentile metrics are absent. Several exception logs serialize raw exception messages; for example SMTP recipient errors can include addresses despite comments promising not to log them. Structured log fields need allowlisting at these boundaries.

**Where the code is over-engineered**

The problem is not simply the number of modules. Several boundaries are useful and should stay: typed request/report contracts, separate candidate/org/admin authorization, purpose-scoped consent, isolated domain rules, migration discipline, and explicit insufficient-signal states.

The less justified complexity is:

| Area | Why it costs more than it currently delivers | Proportionate simplification |
|---|---|---|
| Service construction | Builders recursively create stores and engines for the same database. Dashboard builds jobs/comp/ledger again; jobs build candidate/features again. Tests typically share one session factory, so their topology differs from production. | Create one engine and session factory per app, inject them into stores, reuse service instances, and dispose resources at shutdown. |
| Routing | All 101 route declarations, many DTOs, auth helpers, and response mappings share a roughly 2,870-line module. | Split routers by product area while preserving centralized authentication and existing route-contract guards. |
| Frontend | A single large document and a custom runtime bind logic by string names. Syntax/binding checks pass even when actions are simulated. | First wire the missing flows and add browser workflow checks to CI; then extract cohesive components and type API models. Avoid a wholesale rewrite solely for fashion. |
| Evaluation orchestration | LangGraph currently runs nine nodes in a fixed chain, with no checkpointing or conditional workflow. | Keep it if graph capabilities are planned soon; otherwise a typed sequential runner would suffice. Replacing it now is lower priority than correctness. |
| Provenance storage | Persistent Chroma plus a custom 256-dimensional token-hashing embedder manages a small set of short GitHub facts, while missing the necessary isolation boundary. | Begin with scoped evidence lists/local retrieval; introduce persistent retrieval only with a measured need and explicit lifecycle. |
| Product breadth | Feature registries, training export, cross-company reputation, compensation priors, and verification adapters have accumulated before core browser workflows and score validity are complete. | Freeze expansion and complete one trustworthy upload → review → follow-up → outcome loop. |
| Comments and guard tests | Long historical narratives obscure short implementations. Many guards check source shape or documentation rather than multi-user behavioral outcomes. | Put history in design records; retain concise invariants in code. Keep useful guard tests, but add cross-request and cross-subsystem scenarios. |

Dependencies are directly pinned in `requirements.txt`, but transitive packages still float and normal project installation uses broad ranges from `pyproject.toml`. A reproducible environment should have a complete generated lock and a documented interpreter/installation command. This would also reduce the system-Python versus `.resume` confusion encountered during the review.

**Test gaps that explain why these defects survived**

The test suite is valuable, but large counts do not establish safety or model effectiveness. The most useful additions are behavioral sequences:

- Evaluate two different candidates with the same service bundle and assert evidence isolation.
- Materialize several candidates without an explicit timestamp, then assert that all appear in default search.
- Upload a phone-only candidate and then a conflicting email/phone identity; verify account binding stays protected.
- Interleave two verifications of one OTP; exactly one may consume the challenge.
- Delete a candidate and check every derived persistence mechanism, including evaluation still in progress.
- Revoke consent after materialization and attempt search/export/training afterward.
- Feed valid JSON with invalid types to each LLM-assisted node.
- Compare semantically correct paraphrases, copied expected phrases, repetition, and unrelated fluent interview answers.
- Run real browser workflows for the five incomplete screens, and exercise production service wiring rather than only the shared-factory fixture container.

The signal-quality harness is a useful foundation and correctly refuses insufficient samples. The repository does not, by itself, demonstrate that the current fabrication probabilities, confidence values, compensation estimates, or interview bands are calibrated on representative candidates. Treat those claims as hypotheses to measure.

**Recommended order of work**

1. Correct identity binding, evidence isolation, erasure coverage, and feature snapshot selection. Add the reproductions as regression tests.
2. Make OTP consumption atomic; validate LLM responses and unreadable inputs; define current-consent enforcement for derived data.
3. Wire the five UI screens and verification delivery. Rework and evaluate the interview rubric before relying on its bands.
4. Unify database/service construction, move blocking work off the event loop, bound uploads, and add worker execution only where batch continuity requires it.
5. Gather representative, human-reviewed outcomes and use the existing signal-quality tools before expanding the platform's breadth.

The most valuable next release would make the existing core reliable and explainable across real workflows. Additional scoring systems or abstraction layers would currently compound the unresolved boundaries.
