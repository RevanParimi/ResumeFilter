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


## Follow-up 2026-09-26 — Repository clutter review

Scope: user-requested review of file/document accumulation and unnecessary logic
at `4c83cad`. Inventoried all 760 tracked files: 156 Markdown (26 root, 44 delivery,
74 historical specs/plans, 12 other). No byte-identical nonempty files were found.
Read both UI specs, agent/workflow instructions, active parent/PI records and
architecture notes; traced source references for service composition, vector
retrieval, graph orchestration, routes/UI and smoke harnesses. This is a targeted
source review, not an exhaustive line-by-line correctness or performance audit.
No live providers, working-data edits or runtime refactor were performed.

| Severity | Finding, trigger and consequence | Resolution / evidence |
|---|---|---|
| Medium | [historical design in Git](https://github.com/RevanParimi/ResumeFilter/blob/54804988f3ead83d727754e4361266a4322655c4/UI-Spec.md) and `docs/ui/UI-SPEC.md` diverged: root retained later tenancy decisions but advertised admin signup/fixed question count; nested copy carried auth/interview corrections. Both presented old mock-only claims as current. | Merged unique tenancy and auth/interview material into root UI-Spec; removed nested copy. Marked UI.md, UI-Spec and docs/ui/PLAN as historical and linked current contracts. This does not certify every historical UI statement as current. |
| Medium | `CLAUDE.md` still required the old spec-to-plan workflow alongside the remediation workflow, inviting another plan tree for the same work. | Reduced it to AGENTS/workflow references plus unique repository conventions. No extra task/review file created. |
| Medium | PI-R1 and seven open ancestors copied leaf test counts and obsolete initial traces. Each small fix required synchronized edits across ancestors and could leave stale completion claims. | Parents now own direct-child scope/status and acceptance; leaf evidence retains exact counts/commands. Shortened the handoff and feature validation section; added explicit documentation ownership rules. No leaf evidence or task ID removed; no gate closed. |
| Medium | [Service composition](../src/app/services/__init__.py) still calls `build_vectorstore`; [provenance](../src/app/graph/nodes/provenance.py) now uses evaluation-local evidence and has no vector query/add consumer. Default config selects Chroma and its builder can wait up to the configured 15-second initialization deadline. | Reconfirmed R4-S1-T2. Keep removal/config/dependency compatibility and startup tests together in that task. The potential wait is a configured bound, not a measured startup delay. Corrected FLOW's stale vector/JSONL diagrams now. |
| Medium | [Job](../src/app/matching/store.py), [comp](../src/app/comp/service.py) and [dashboard](../src/app/dashboard/service.py) builders recursively construct stores/engines for the same URL; [app lifespan](../src/app/main.py) logs shutdown without explicit resource disposal. | Reconfirmed R4-S1-T1; preserve injection, separate URL semantics and lifecycle tests before implementation. No engines removed in this documentation task. |
| Medium | `data/veritas.db` remains tracked. Deleting or untracking it casually would risk working data and would not erase historical copies. | Preserve bytes; retain the fixture/untracking work under R4-S3-T3. No records inspected or database cleanup run. |
| Low | FLOW linked a removed report store and described old persistence/provenance wiring; three historical designs had 12 obsolete pre-src-layout links. | Updated FLOW to the current nine-node/source map and SQL report store. Rebased historical links to current files and removed obsolete line anchors, with historical notices. |
| Low | `routes.py` (2880 lines) and `frontend/support.js` (1911 lines) mix many live flows; LangGraph is a fixed nine-node chain. Large size or linearity alone does not prove dead code. | Keep R4-S1-T3/T4 extraction and T2 graph evaluation; do not delete live handlers or replace orchestration just to lower file count. |

Retained deliberately: distinct feature contracts, active task briefs, completed
regression evidence, 74 historical design/plan files, migration history, and
scenario-specific smoke/tests. Archived UI/design-system assets are historical,
and static mount tests enforce that the served UI is allowlisted. Similar smoke
setup does not make its distinct race/interruption scenarios redundant. No broad
file deletion, new abstraction, dependency change or runtime behavior change.

Acceptance for this review: consolidate proven documentation duplication without
losing unique decisions/evidence, correct actionable stale pointers/instructions,
keep all task statuses and the next development task unchanged, preserve working
DB bytes, and map runtime findings to existing tasks.

Validation: inline `.resume/Scripts/python.exe -` checks resolved local links in
all **155 remaining tracked Markdown files**, preserved all **34 task statuses**
and PI task headings/statuses, compared every detailed leaf/archive record with
HEAD (unchanged), and asserted the merged UI corrections/tenancy decisions plus
the unchanged D3d2c2 next-task pointer. `git diff --check` passed. Only Markdown
changed: one redundant file removed, no new file, more than 700 net lines removed.
The working DB SHA256 is unchanged from the handoff. No application tests were
rerun because source, tests, migrations and frontend assets are unchanged.

Same-agent diff review covered `4c83cad` plus the 24-file documentation delta:
acceptance/evidence preservation, direct-child status maps, unique UI decisions,
source-link corrections, historical/current labeling and instruction ownership.
Review retained the original first-party-data requirement in the short CLAUDE
entry point and corrected text encoding during consolidation. No documentation
acceptance blocker remains. Runtime findings above remain open under PI-R4; no
independent review, application execution or full-codebase correctness claim.

## Follow-up 2026-10-19 — Retire obsolete repository material

R4-M2 versioned-file retirement and cleanup-only main publication complete (2026-10-19); local ignored-artifact deletion remains blocked. User explicitly authorized removal of the
previously identified obsolete files and a push to `main`, with commit email
`revan.datta132@gmail.com`. Publication is scoped to the cleanup-only candidate; earlier application/test
work, working data, secrets and local editor settings are excluded.

Acceptance: remove superseded historical implementation plans, prototype UI
documents and unreferenced design assets; retain current feature contracts,
meaningful regression/journey tooling, task IDs/statuses and validation evidence.
Rebase references to current owners or the exact historical Git revision. Remove
only verified generated local review/Windows-cache artifacts, after resolving
their paths inside this workspace. Prevent their accidental addition/build use.
Preserve unrelated prior edits, the working database and running demo. Record
the exact reviewed/tested commit and verify the remote main SHA after pushing.

Required evidence: source/asset-reference and API-contract preservation, focused
and full offline pytest, UI bindings/JS syntax, actual scratch Chrome journeys,
documentation links/status checks and a separate diff self-review. No SQL,
migration, provider-quality or additional feature work is authorized by this
cleanup. R4-S1-T3E remains the next feature task, not started here. Historical
records can be recovered from Git; no published evidence will silently disappear.

Implementation: 93 versioned files removed: 74 historical implementation
plans/specifications, two files under docs/ui, UI.md/UI-Spec.md, and 15 design
assets. Current HTML/API/support files do not reference the retired design
bundles. Historical references now resolve to exact blobs at
`54804988f3ead83d727754e4361266a4322655c4`; current feature guides remain.
The only application behavior change is that restored `_ds` files return 404;
the UI entry, api.js and support.js remain served. No useful test or journey
script is removed. Ignore/build rules exclude local retired review/cache paths.

Regression: `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3d.py retire-red -m pytest -q --tb=short tests/test_ui_mount.py::test_retired_design_assets_are_not_served_if_restored`
failed as intended (**1 failed**, 8.00s): a real file in the retired directory
was still served with 200. The new allowlist refuses it while api.js returns 200.
Initial focused checks found one unrelated contract mismatch from a documentation
rewrite in schema descriptions (**1 failed, 57 passed**); those three source
files were restored byte-for-byte. The existing API fixture was not regenerated.

Current workspace validation:

- `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3d.py retire-focused-final -m pytest -q --tb=short tests/test_ui_mount.py tests/test_image_contents.py tests/test_deploy_doc.py tests/test_api_route_extraction.py tests/test_route_table_guard.py tests/test_org_scope_guard.py tests/test_ui_handlers.py`:
  **58 passed, 1 warning, 17.65s**, exit 0; full API/dependency contract unchanged.
- `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3d.py retire-browsers .pytest_cache/retire_browsers.py`:
  actual Chrome screening/reload/error journey **24/24**, evaluation/feedback/
  contact **31/31**, embedded contract **1/1**, exit 0. Scratch migrated SQL and
  fake/capture providers; requires existing CDN internet. No live-provider,
  scoring-quality or PostgreSQL validation claim.
- `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**; JS syntax
  checks for frontend/api.js and frontend/support.js pass.
- `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3d.py retire-full`:
  **3,511 passed, 505 skipped, 127 warnings, 1024.42s (17:04)**, exit 0;
  wrapper elapsed 1037.65s. Optional/environment skips are not passes; existing
  SQLite reflection/autogenerate and dependency warnings remain.

Cleanup-only publication candidate, checked out separately from committed
main (the earlier local application backlog is not copied): focused **44 passed,
1 warning, 14.64s**, exit 0. Actual candidate Chrome screening **19/19**, exit 0.
Candidate full regression: **2,518 passed, 188 skipped, 44 warnings,
568.89s (9:28)**, exit 0; wrapper elapsed 582.77s. Candidate bindings: **402 /
9 states** and both JS syntax checks passed. `.pytest_cache/run_retire_candidate.py`
selects its own src/working directory and clears DEE configuration/credentials;
all Python children use the existing project environment.

Separate self-review covers old main plus the explicit 112-path candidate diff:
93 removals and 19 related files. API route/function ASTs and all old UI mount
regressions are preserved; main.py changes only the retired static allowlist
apart from comments/docstrings. Current task IDs/statuses, relative links and
historical blobs pass verification; working DB and unrelated prior edits are
unchanged. Byte/EOL checks distinguish binary data from text. Candidate reviewed
hashes are retained in ignored local artifacts. No independent review claimed.

Automatic approval review rejected recursive local-artifact deletion as
"blocked by policy", including a narrower attempt for .superpowers. Those
ignored review/Windows-cache directories remain on disk; no alternate deletion
method will bypass that rejection. The owned archive helper was stopped. These
local artifacts are excluded from the cleanup commit and build context.

Publication: [commit 57a68ec](https://github.com/RevanParimi/ResumeFilter/commit/57a68ecc65603951922657658e14b6567364db26)
was pushed normally to origin/main and verified with git ls-remote. Author and
committer are Revan Parimi <revan.datta132@gmail.com>. Local main was advanced
to the same commit, refreshing only its 112 index paths; all 714 remaining
project files were unchanged during synchronization. The cleanup-only commit
contains no earlier local application/test work, working data, secrets or local
editor settings. Earlier work remains uncommitted and preserved. No deployment
or next feature task was started. Exact next development task remains T3E.

Final post-publication checks: all 858 current local links resolve, historical
blobs and PI IDs/statuses are retained, 698 unrelated pre-cleanup files are
unchanged, and the existing demo /healthz returns 200 without a restart. No staged
changes remain. The owned temporary checkout is unregistered; Windows denied
removing its residual ignored directory, which remains as local scratch.

The tracked-file cleanup/publication is complete. Recursive removal of the
ignored local review/Windows-cache directories remains explicitly blocked by
automatic approval review; those directories were not silently counted as removed.

### Publication follow-up: previously completed local work

On 2026-10-19 the user explicitly requested committing/pushing the remaining
completed work as well as its unnecessary-file removals. This expands the
previous cleanup-only publication scope; it does not start another backlog task.
The reviewed base is `57a68ecc65603951922657658e14b6567364db26`.

Acceptance: publish the existing completed remediation, migrations, API modules,
UI flows, regression/journey tooling and R4-M1 test/delivery consolidation as one
consistent tree. Include the 58 pending tracked deletions (35 delivery records,
22 test modules and the retired vector-store implementation), retaining their
replacement evidence/tests. Preserve working data, secrets, editor settings and
the running demo. Add local editor exclusions to Git/build rules. Verify the
explicit staged manifest, full offline regression, relevant scratch HTTP/Chrome
journeys, documentation links/record preservation, whitespace and remote main.

The manifest contains 342 paths; runtime data, secrets, scratch/cache directories
and local editor settings are excluded. No additional application behavior is
introduced in this publication step. Staged diff review found one surplus EOF
blank line in the new candidate router; trimming it preserves the exact AST.
The remaining source/tests/migrations match the pre-publication snapshot.

Final publication validation (2026-10-19):

- `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3d.py publish-full`:
  **3,511 passed, 505 skipped, 127 warnings, 1210.98s (20:10)**; exit 0,
  wrapper elapsed 1231.45s. Existing optional/environment skips are not passes.
- `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3d.py publish-journeys .pytest_cache/publish_journeys.py`:
  exit 0, 258.04s. Migrated scratch screening HTTP/restart **16/16**, reused HTTP
  contract **31/31**; actual Chrome screening **24/24**, evaluation **31/31** plus
  embedded contract **1/1**, interview text/audio/reload/restart **40/40** plus
  embedded contract **1/1**. Fake/capture providers and synthetic media; Chrome
  still requires the existing CDN internet. The working demo was not restarted.
- `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**; both
  `node --check frontend/api.js` and `node --check frontend/support.js` passed.
- Existing consolidation verifier preserves all **4,015** original collected
  cases and **295** moved function/class ASTs; the retirement regression adds
  one case. All **86** record bodies/IDs survive link rebasing. Current local
  links, immutable historical Git blobs and unchanged PI status maps pass.
- Explicit staged scope is **342 paths**, including **58 deletions**. Reviewed
  credential-pattern/path checks and `git diff --cached --check` pass. Source,
  tests and migrations match the pre-publication snapshot apart from the
  AST-identical EOF cleanup; protected DB/credential/editor bytes are unchanged.

Separate same-agent publication review covered the full path manifest and
recorded acceptance contracts, plus the authentication/CSRF/router composition,
login proof/erasure, current-consent export/search, provider refusal/fallback,
bounded PDF parsing, shared resource ownership and interview/UI changes in the
aggregate diff. The only new finding was the surplus EOF blank line above,
resolved without behavior change. No publication acceptance blocker remains.
This is self-review; no independent reviewer or new live-provider, PostgreSQL,
Docker runtime or empirical-quality validation is claimed. Earlier bounded
migration/database evidence remains in the linked task records.

Publication candidate is ready for the explicitly authorized main push using
Revan Parimi <revan.datta132@gmail.com>. The exact commit/remote verification is
recorded after publication. Remaining development status is unchanged: 29 parent
tasks done, one in progress and 20 pending. R4-S1-T3E remains next, not started.

## Follow-up 2026-10-18 — Test and delivery consolidation

R4-M1 maintenance, done (2026-10-18). User authorized a bounded consolidation before
the next route extraction. Baseline: 314 pytest modules and 97 delivery Markdown
files (9,883 lines). Reuse this audit for the contract and evidence; no new task
tree. R4-S1-T3E remains the next development task and is not started here.

Acceptance: consolidate related unit/API contract tests and seven repeated Node
launchers without losing collected cases, assertions, fixture isolation or
offline behavior. Consolidate completed delivery records by PI, preserving task
IDs, statuses, decisions, validation results and limitations; rewrite inbound
links to stable anchors. Keep the active task separate and prefer inline child
contracts/evidence for future work. Preserve all unrelated edits and working DB.

Validation required: before/after collection mapping and AST comparison of moved
tests/helpers, focused and full offline pytest, Node bindings, local links and
task-status/evidence preservation checks, separate diff self-review and file
hash preservation. Application/frontend/schema code is outside scope, so no
new HTTP/browser/PostgreSQL execution claim or migration gate is applicable.
The consolidated API tests still execute their actual TestClient workflows;
Node handler tests execute the shipped JS harnesses, not Chrome.

Implementation: 47 related modules now use 15 product-area/contract modules;
pytest module count is **314 -> 282**. Seven repeated Node launchers are one
parametrized test with the same scripts, skip condition, timeout and failure
output. Identical screening helpers are shared; colliding report/schema names
are made explicit. All 295 moved function/class ASTs match the snapshots after
recorded symbol renames, and collection maps one-for-one across **4,015 cases**.
No regression assertion, concurrency/erasure scenario or fixture scope removed.

Delivery Markdown is **97 -> 14 files**. All 86 completed task bodies/statuses
are retained in four PI evidence files, with rebased links and stable task/section
anchors. Historical commands/next pointers are explicitly dated history. The
active T3 record remains separate. Repeated sprint instructions now have one
workflow owner; future child contracts/evidence stay inline and maintenance
reviews reuse this audit. This reduces file fragmentation; historical evidence
text is retained, rather than claiming a large reduction in its total length.

Validation run with the existing sanitized offline wrapper:

- Collection before/after: `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3d.py consolidation-before -m pytest --collect-only -q`
  and the same command with `consolidation-after`: **4,015 collected** each.
- Focused command (the 15 consolidated modules):

```powershell
.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3d.py consolidation-focused -m pytest -q --tb=short `
  tests/test_api_route_extraction.py `
  tests/test_auth_schema.py `
  tests/test_candidate_schema.py `
  tests/test_candidate_store.py `
  tests/test_candidates_api.py `
  tests/test_verification_schema.py `
  tests/test_verification_concurrency.py `
  tests/test_report.py `
  tests/test_fabrication_schema.py `
  tests/test_feature_schema.py `
  tests/test_verification_assurance.py `
  tests/test_screening_batches_api.py `
  tests/test_screening_service.py `
  tests/test_screening_schema.py `
  tests/test_ui_handlers.py
```

Focused result: **279 passed, 16 skipped, 1 warning, 81.79s**, exit 0.
The warning is Starlette/httpx deprecation; environment/PG skips are not passes.
Actual TestClient API workflows and all seven Node handler harnesses ran. No
application, UI contract, script, schema or migration change requires a new
HTTP/subprocess/browser/PG journey here; no Chrome/live-provider claim is made.

- Full pytest: `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3d.py consolidation-full`
  (default `-m pytest -q --tb=short`): **3,510 passed, 505 skipped, 127 warnings,
  891.56s (14:51)**, exit 0; wrapper elapsed 902.07s. Warnings retain existing
  SQLite expression-index reflection/autogenerate and Starlette/httpx limits.
  Skipped optional/environment cases are not validation of those environments.
- `.resume/Scripts/python.exe .pytest_cache/verify_consolidation_tests.py` and
  `verify_consolidation_docs.py`: collection/AST/body/status preservation, **893
  local links with no missing file/anchor**, and **765 unrelated baseline files**
  unchanged, including runtime source/scripts/frontend and working DB. Only five
  new durable files exist: the four evidence collections and Node launcher.
- `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**, passed.
- Windows-aware `git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --check`: passed.
  Five new files also have no whitespace diagnostics/trailing whitespace.

Separate self-review: HEAD `5480498` plus this session's snapshot-relative diff,
15 consolidated modules and documentation rebasing. Checked import origins,
constant/helper collisions, fixture/async scope, parameter IDs, subprocess failure
reporting, task/status preservation, links and future documentation ownership.
Code hashes are recorded in `.pytest_cache/consolidation-reviewed-code.json`;
logs/maps/snapshots are ignored local artifacts, not portable setup guarantees.
No acceptance-blocking finding remains; this is not independent review. Earlier
raw-CRLF whitespace output and a regex inside a historical code fence were
checker issues; corrected checks above pass. No working-data cleanup, demo
restart, commit, deployment or next route extraction was performed.

Post-suite preservation/links passed again; all 15 reviewed test-module hashes
match the full-suite state. The existing demo's `/healthz` returned 200 without
a restart. Durable additions remain exactly the five consolidated files.

Done: acceptance, focused/full regression, static/preservation checks and review
are complete. Exact next development task remains **R4-S1-T3E**, not started;
write its contract/evidence inline in the active T3 record.

## Follow-up 2026-10-11 — local demo readiness

User requested a working URL and a short nontechnical demo. Acceptance: verify
hosting evidence, demonstrate actual browser operations, preserve working data
and distinguish simulated UI/model quality from functional execution.

`DEPLOY.md` records no public deployment; `railway.cmd status --json` reports no
linked project. No Veritas listener existed initially. Started the real app at
`http://127.0.0.1:8000/ui/` with a newly migrated scratch SQLite database, four
fictional resumes, memory vectors, NullLLM and local captured/auto-filled login.
No provider/mail delivery, cloud resource or working migration. Organization
demo login: `demo@veritas.example`; no credentials retained in documentation.
Ignored `.pytest_cache/demo-runtime-2026-10-11.json` records the owned PID/storage;
the URL is local to this machine and valid while that process runs.

Present three flows: upload/process a batch into the review queue; open a report
with reasons, similarity signals and follow-up questions; record a reviewer
decision and reload its saved history. Instant check/interview UI remain
simulations (`runEvaluate` timer/local interview state), excluded from the demo.
Style/factual-risk remediation and representative scoring quality remain open.

Validation using `.resume/Scripts/python.exe`: existing
`scripts/check_ui_screening_browser.py` passes **19/19**, exit 0 (captured through
`subprocess.run` to disambiguate PowerShell's first redirected stderr result), and ignored
`.pytest_cache/check_local_demo_20261011.py` passes **9/9** actual Chrome checks
against the running demo, including login, four reports, questions, similarity,
saved outcome/reload and no console errors. `node scripts/check_ui_bindings.js`
passes 425 bindings across 10 states. Final `/healthz` and `/ui/` both return 200;
health reports `llm_mode=null`. `git diff --check` passes. Full pytest was not
rerun: tracked changes are documentation only. Working DB SHA256 remains the
handoff value.

Same-agent review scope: HEAD `5480498` plus this three-document delta and the
ignored session launch/browser helpers; checked isolation, secret handling,
claimed behavior versus browser evidence, and unchanged task/status pointers.
No independent/provider/accuracy or deployment claim. No remediation ID closed;
PI/task evidence is unchanged, and **R2-S1-T2B** remains awaiting Linux validation.
