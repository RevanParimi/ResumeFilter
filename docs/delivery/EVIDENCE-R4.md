# PI-R4 completed evidence

Reference history, consolidated 2026-10-18. Start with [the handoff](../PROGRESS.md)
and [PI-R4](PI-R4.md) for current status. Each task's original contract,
decisions, validation and limits are retained below; historical next-task pointers
and commands describe their recorded date, not today's execution order or paths.
Moved pytest cases now live in their product-area modules. No old result is a new
execution, independent review, live-provider check or broader quality claim.

- [R4-S1-T1](#r4-s1-t1)
- [R4-S1-T1A](#r4-s1-t1a)
- [R4-S1-T1B](#r4-s1-t1b)
- [R4-S1-T2](#r4-s1-t2)
- [R4-S1-T3A](#r4-s1-t3a)
- [R4-S1-T3B](#r4-s1-t3b)
- [R4-S1-T3C](#r4-s1-t3c)
- [R4-S1-T3D](#r4-s1-t3d)

## <a id="r4-s1-t1"></a>R4-S1-T1 — Share database and service resources

Status: done (2026-10-16). Parent: [PI-R4](PI-R4.md), F12.
Prerequisite: [R3-S3-Q](EVIDENCE-R3.md#r3-s3-q), done.

Split before implementation into SQL topology/engine ownership and provider
transport cleanup. Both bounded contracts passed; child records own exact
acceptance criteria, red regressions, final checks, review and preservation.

- [T1A](#r4-s1-t1a), done: default composition shares one runtime SQL factory
  and stores/services, disposes owned engines on failure/shutdown and preserves
  explicit borrowed factories/bundles and separate app databases.
- [T1B](#r4-s1-t1b), done: lazy owned GitHub/LLM/speech transports, asynchronous
  cleanup across normal/error/canceled exits, borrowed clients preserved and
  accessible/late Chroma results closed through the public per-client API.
  EvaluationEngine requires an explicit bundle; callers own manual bundle cleanup.

Actual migrated SQLite/PostgreSQL HTTP with graceful restarts exercised shared
SQL and provider transport closure plus evaluation/search/portal/audio, tenant
denials, current consent and erasure/survivor behavior. Final focused/full pytest,
real Chrome/contracts/static checks and separate same-agent self-review passed.
T1A owns SQL lock/migration gates; B changes no SQL/schema/transaction behavior.

This proves bounded ownership/cleanup, not forced recovery from drivers/closers
that never return or raise. Chroma's indefinitely blocked SDK constructor remains
T2's unused-path removal. No zero-leak, live-provider, quality, performance or
independent-review claim. Prior work/data/demo preserved; owned validation
processes stopped. Detailed children archived at group closure.

F12 stays open for R4-S1-Q; R4-S1/PI-R4 remain open. Exact next **R4-S1-T2 — Remove
unused provenance infrastructure**, not started. Stop after T1B this session.

## <a id="r4-s1-t1a"></a>R4-S1-T1A — Shared SQL topology and engine ownership

Status: done (2026-10-16). Parent: [T1](#r4-s1-t1), F12.

### <a id="r4-s1-t1a--contract"></a>Contract

Production currently builds independent engines and duplicate candidate/feature/
ledger/job/comp stores behind its services. Tests hide the topology difference.
Use explicit factory/dependency parameters in existing builders and one per-app
factory; preserve each store's settings and all consent/erasure/tenant gates.
No global URL cache or new injection framework. Standalone builders remain usable.

- AC1: Production and fake-provider test containers share the same SQL topology:
  candidate/report/ledger/feature/job/source/curation/auth/interview/verification/
  screening/rights stores and limiters use one factory; dashboard/jobs/comp reuse
  the container's store/service instances. Spy construction and exercise writes.
- AC2: An explicit external factory is borrowed, and two separately configured
  app databases remain isolated. No hidden global settings redirect dependencies.
- AC3: The SQL engine created by default composition is disposed once on app
  shutdown, exceptional lifespan exit, and failed composition; borrowed factories
  survive. Repeated fresh startup/shutdown constructs and disposes matching pools.
- AC4: Actual production composition on migrated scratch storage supports
  evaluation, search and portal flows across child-app restart, including tenant/
  current-consent/erasure denials. Run meaningful red/final regressions, full
  project pytest, affected HTTP/browser contracts, static checks and a separate
  recorded same-agent diff review. PostgreSQL gates revalidate shared-pool
  transactions/locks and relevant existing migrations; no working migration.

T1B owns provider-client cleanup and complete startup resource ownership. No UI,
SQL/schema/scoring change, Chroma removal, background-worker rewrite, deployment,
live-provider or independent-review claim. Preserve prior edits/data and demo.

### <a id="r4-s1-t1a--evidence-and-review"></a>Evidence and review

Initial snapshot preserves 899 prior files/status/HEAD under
`.pytest_cache/r4-s1-t1a-before/`. Safe project runner:
`.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t1a.py <tag> <Python arguments>`;
omitted arguments run `-m pytest -q --tb=short`. It clears inherited DEE config
and disables live providers. No working DB/demo restart or migration.

Reproduction: confirmed original-source run `red-baseline-confirmed -m pytest -q
--tb=short -o pythonpath=.pytest_cache/r4-s1-t1a-before/src
tests/test_services_features.py::test_real_and_fake_composition_share_sql_and_service_instances[True]
tests/test_services_features.py::test_default_composition_constructs_one_runtime_pool`
through the baseline runner: **2 intended failures**, 5.24s. Production allocated
**16 runtime engines**, and store identities differed. The first broad red run
also included a fixture wrapper signature error; it is not counted as the
reproducer. The first baseline helper selected current code through pytest's
configured pythonpath; the explicit override above proves original-source failure.

Existing builders now accept a borrowed factory/dependencies, default composition
owns one engine and shares stores/services, and lifespan passes its exact boot
settings. `ExitStack` disposes an owned engine on composition failure; transfer
to the bundle occurs only after construction. `dispose_sql()` is idempotent;
app-owned SQL is disposed on normal/exceptional exit and app references clear.
Explicit factories and injected bundles remain caller-owned; standalone store
builders still leave their engine lifecycle to the caller. No global URL cache.

Separate same-agent specification/correctness review: 18 executable/test/journey
hashes plus bounded diff in `.pytest_cache/r4-s1-t1a-reviewed.json` /
`r4-s1-t1a-session.diff`, captured with project `review_r4_s1_t1a.py`. Review maps
AC1-4 to real/default and fake topology, actual engine/connection events, separate
databases/borrowed resources and migrated restart/data denials. Checked builder
callers/default compatibility, preserved key/TTL/settings values, factory identity
through all SQL consumers/limiters, candidate/tenant/consent/erasure boundaries,
exception ownership transfer and shutdown ordering. SQL statements/schema/scoring
and provider construction are unchanged. No unresolved acceptance-blocking finding
within T1A. Provider-client closure/partial-startup leaks and Chroma's late startup
remain T1B/T2; this is self-review, not independent review or full F12 closure.

Initial focused topology/rate wiring: 21 passed; affected services: 75 passed,
1 warning; extended topology/lifespan: 13 passed. Initial migrated SQLite HTTP
`scripts/smoke_r4_s1_t1a.py`: **12/12**, including actual graceful uvicorn shutdown
and two pool-disposal events. Final reviewed gates passed below.

Final focused arguments: `-m pytest -q --tb=short tests/test_services_features.py
tests/test_ratelimit_wiring.py tests/test_job_store_match.py
tests/test_dashboard_service.py tests/test_comp_service.py
tests/test_profile_sources_service.py tests/test_screening_service.py
tests/test_ui_mount.py tests/test_verification_delivery.py`.

| Layer | Actual final command/result | Artifact |
|---|---|---|
| Focused | Safe runner `focused` with arguments above: **83 passed, 1 warning, 52.09s**, exit 0 | `.pytest_cache/r4-s1-t1a-focused.txt` |
| Migrated SQLite HTTP/graceful restart | Safe runner `http scripts/smoke_r4_s1_t1a.py`: **12/12**, exit 0, 31.13s; actual default SQL composition with fake providers, evaluation/search/portal/report ownership, revoked consent, erasure/survivor, two graceful uvicorn shutdowns with DBAPI-close/pool-dispose events | `.pytest_cache/r4-s1-t1a-http.txt` |
| Evaluation Chrome | Safe runner `evaluate-browser scripts/check_ui_evaluate_browser.py`: **31/31**, exit 0, 63.49s | `.pytest_cache/r4-s1-t1a-evaluate-browser.txt` |
| Combined interview Chrome | Safe runner `interview-browser scripts/check_ui_interview_integration_browser.py`: **40/40**, exit 0, 118.35s; actual text/synthetic microphone, saved version/evidence, employer consent, process restart, uncertain-write recovery and actor cleanup | `.pytest_cache/r4-s1-t1a-interview-browser.txt` |
| Cookie/CSRF contracts | Safe runner `contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 53.14s | `.pytest_cache/r4-s1-t1a-contract.txt` |
| PostgreSQL locks/migrations | Project Python `.pytest_cache/run_r4_s1_t1a_postgres.py`, selecting services/features, jobs, current consent, interview lifecycle/erasure, screening erasure, candidate-login and curation migrations: **208 passed, 59 skipped, 21 warnings, 482.86s**, exit 0; PG 18.6 / READ COMMITTED / Asia/Calcutta; actual competing connections and existing up/down/up | `.pytest_cache/r4-s1-t1a-pg-focused.txt` |
| Migrated PostgreSQL HTTP/graceful restart | Same owned runner invokes `scripts/smoke_r4_s1_t1a.py --postgres`: **12/12**, exit 0, 51.68s | `.pytest_cache/r4-s1-t1a-pg-http.txt` |
| Full pytest | Safe runner `full`, project `-m pytest -q --tb=short`: **3471 passed, 505 skipped, 127 warnings, 1343.86s**, exit 0, on reviewed source | `.pytest_cache/r4-s1-t1a-full.txt` |
| Static | `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**; `node --check frontend/api.js`, `frontend/support.js`; project `-m compileall -q src/app/services/__init__.py src/app/main.py scripts/smoke_r4_s1_t1a.py`; `git -c core.safecrlf=false diff --check`: passed | No frontend changes; bindings are separate from Chrome |

Owned PG's initial `pg_ctl stop` timed out (exit 1, 66.88s) during checkpoint;
the server subsequently completed shutdown. Project Python
`.pytest_cache/recheck_r4_s1_t1a_postgres.py` confirmed status exit 3 (no server),
no postmaster PID file and refused connection on the owned port. Runtime metadata
retains the original timeout and records `shutdown_confirmed`; server log records
completed shutdown. No forced kill, application change or test rerun was needed.

Chrome needs
internet for its existing CDN assets; provider/media fixtures do not establish
live-provider compatibility or measured quality. No schema migration was added.

### <a id="r4-s1-t1a--handoff"></a>Handoff

AC1-4 and final gates passed. Default app composition now builds **one runtime SQL
engine instead of 16**, with shared stores/services and explicit borrowed-resource
ownership. Actual warmed DBAPI connections close on graceful shutdown; failed
composition/lifespan and repeated app cycles have regression coverage. No HTTP contract,
SQL/schema/scoring, dependency or working-data migration change. Warning summaries
are existing Starlette/httpx and SQLite expression-index warnings; optional
Parquet and environment/lock-inspection skips do not prove omitted cases.

Final project Python `.pytest_cache/verify_r4_s1_t1a.py --closed`: **878 unrelated
prior files**, working DB/HEAD/unrelated status and **18 reviewed hashes** preserved;
demo health 200, owned PG shutdown confirmed. **6 documents / 206 local links**,
added-line whitespace and current/parent/next-task status checks passed. Final
`git -c core.safecrlf=false diff --check` passed; changed executable-line whitespace
was checked by the review capture. Owned app/Chrome/PG stopped; synthetic evidence
retained. No user-data cleanup, deployment or live-provider claim.

**T1A is done; parent T1/F12, R4-S1 and PI-R4 remain open.** Provider-client
closure/partial startup and the Chroma timeout path remain T1B/T2. Exact next:
**R4-S1-T1B — Provider-client ownership and cleanup**, not started. Read the parent,
write B's contract before implementation, preserve T1A's SQL ownership/injection,
and validate complete shutdown/failure paths. Stop after T1A this session.

## <a id="r4-s1-t1b"></a>R4-S1-T1B — Provider-client ownership and cleanup

Status: done (2026-10-16). Parent: [T1](#r4-s1-t1), F12.
Prerequisite: [T1A](#r4-s1-t1a), done.

### <a id="r4-s1-t1b--contract"></a>Contract

Keep synchronous service composition compatible while making transport creation
lazy: startup performs no provider requests and needs no opened HTTP transports.
The app closes its constructed clients asynchronously; explicitly injected
clients/factories/bundles remain borrowed. Preserve T1A's SQL topology and disposal.
Use direct ownership fields and existing seams, without a new injection framework.
`EvaluationEngine` now requires explicit Services (all repository callers already
inject them); remove its unused no-op close stub. Manual bundle owners await
`Services.aclose()`. An indefinitely hanging closer cannot be forcibly settled;
other available closers and SQL are attempted independently.

- AC1: Owned GitHub HTTP and LLM/speech SDK transports open on first use and close
  exactly once; unused providers create no transport. Failure during composition
  opens no HTTP transports and disposes owned SQL. Provider settings and fallback
  behavior remain intact. Borrowed resources survive normal/error exits.
- AC2: Normal shutdown, startup after composition failure, exceptional serving,
  concurrent/repeated close and cancellation settle all available owned cleanup
  operations. One failing closer cannot prevent other clients or SQL disposal;
  report failures with fixed diagnostics, without provider payloads or secrets.
- AC3: An accessible Chroma client closes through its public close API, including
  collection-construction failure and results arriving after fallback. Use a
  synchronized timeout handoff; preserve per-client SDK ownership rather than
  stopping shared systems globally. An indefinitely stuck SDK constructor remains
  uninterruptible; T2 removes the unused startup path. No new worker framework.
- AC4: Meaningful offline regressions, separate recorded diff self-review, final
  full pytest and actual default-composition HTTP/graceful restart on migrated
  scratch storage prove transport and SQL cleanup plus evaluation/portal/consent/
  tenant/erasure behavior. Relevant browser/contracts/static checks revalidate
  consumers. No SQL/schema/transaction change means no new migration/lock gate;
  run existing PostgreSQL HTTP compatibility without a working-data migration.

Inspect installed SDK source for close contracts; use local fake SDKs and HTTP
transports, not paid/live providers. No accuracy, deployment, no-resource-leak or
independent-review claim. Preserve prior changes, working DB and running demo.
Complete only B; T2 is not started in this session.

### <a id="r4-s1-t1b--evidence-and-review"></a>Evidence and review

Snapshot: 902 prior files/status/HEAD, `.pytest_cache/r4-s1-t1b-before/`.
Runner: `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t1b.py <tag> <Python
arguments>` clears DEE config/secrets, forces memory vectors and disables live
providers; no arguments runs `-m pytest -q --tb=short`. Logs use the matching
`.pytest_cache/r4-s1-t1b-<tag>.txt`. Final full gates passed; final handoff preservation is recorded below.

GitHub/LLM/speech allocate HTTP/SDK transports lazily and expose idempotent close.
Default composition records owned clients; `Services.aclose()` shares one shielded
cleanup task, disposes SQL and attempts independent provider closers concurrently.
Repeated cancellation waits for available cleanup, then propagates cancellation.
Cleanup errors use fixed messages/type-only logs; primary app/build failures win.
Injected clients/factories/bundles remain borrowed. Synchronous partial build
opens no HTTP transport; ExitStack closes available vectors/SQL on failure.
Chroma uses public per-client close on collection failure, shutdown and late
construction results; a lock coordinates timeout ownership. No global SDK stop.

Red: initial `red -m pytest -q --tb=short tests/test_service_lifecycle.py` had 14
failures (40.67s): 13 intended lifecycle defects, plus a masked-backend fixture
failure excluded from reproduction. Corrected `late-red-confirmed` against the
saved source, with `-o pythonpath=.pytest_cache/r4-s1-t1b-before/src`, failed at
the missing late-result close (7.34s). `graph-red` failed the forbidden implicit
builder assertion (5.47s), with a stub protecting working data. Initial focused
run: 95 passed/one masked late-result fixture failure; corrected run: 97 passed.

Separate same-agent specification/correctness review: HEAD plus the 12-file
session diff and SHA256 inventory captured by `review_r4_s1_t1b.py`; no independent
review. Checked ownership transfer, every repository graph constructor, lazy SDK
settings, cancellation/error precedence, Chroma timeout handoff and diagnostics.
Installed OpenAI 2.43.0 async `close()` closes its HTTP transport; Chroma 1.5.9's
public `close()` releases this client's shared-system reference. No global stop.
No schema, scoring, auth, consent or UI behavior changes. No acceptance-blocking
application finding remains in this reviewed scope; final regressions below passed.
Review also added partial vector-build failure/error-precedence and
borrowed-vector checks. The preliminary full run was stopped after 184.91s and
restarted to include these final tests and EOF whitespace cleanup; it supplies no
completion evidence. Final hashes were captured before that restart.
Validation review corrected the old vector timeout/error fixtures:
the sanitized runner's memory backend had bypassed their patched Chroma branches;
explicit Chroma settings now exercise those fakes. The corrected late-result test
also fails against the saved pre-change source. The implicit graph constructor
was a second ownership entry point; requiring explicit Services closes it without
changing any repository caller, and removes the unused no-op cleanup method.

Final focused arguments: `-m pytest -q --tb=short tests/test_service_lifecycle.py
tests/test_services_features.py tests/test_vectorstore_build.py
tests/test_llm_config.py tests/test_speech_seam.py tests/test_github_repo_evidence.py
tests/test_github_user_signal.py tests/test_ratelimit_wiring.py`.

| Layer | Actual command/result |
|---|---|
| Focused | Runner `focused-final` with arguments above: **111 passed, 67.71s**, exit 0; final added tests/borrowed vector rechecked by `lifecycle-final -m pytest -q --tb=short tests/test_service_lifecycle.py tests/test_llm_config.py tests/test_vectorstore_build.py`: **42 passed, 37.21s**, exit 0 |
| Migrated SQLite HTTP/graceful restart | Runner `http scripts/smoke_r4_s1_t1b.py`: **15/15**, exit 0, 57.77s; default composition, real wrappers/local SDK and httpx fakes, two opened/closed transport sets and disposed SQL pools; saved report/portal/search, org denial, current consent and erasure/survivor |
| Evaluation Chrome | Runner `browser-evaluate scripts/check_ui_evaluate_browser.py`: **31/31**, exit 0, 54.80s |
| Combined interview Chrome | Runner `browser-interview scripts/check_ui_interview_integration_browser.py`: **40/40**, exit 0, 117.51s; text/synthetic microphone, saved assessment/version, restart, permitted employer summaries and actor/device cleanup |
| Cookie/CSRF contracts | Runner `contracts scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 36.47s |
| PostgreSQL HTTP compatibility | Owned project-Python `.pytest_cache/run_r4_s1_t1b_postgres.py` invokes `scripts/smoke_r4_s1_t1b.py --postgres`: **15/15**, exit 0, 62.29s; PG 18.6 / READ COMMITTED / Asia/Calcutta, migrated isolated schema and two graceful lifespans. Auxiliary topology/lifecycle tests: **33 passed, 53.71s** (their production fixtures select scratch SQLite; not PG lock proof). No new SQL/schema/transaction changes; T1A owns lock/migration evidence |
| Full pytest | Runner `full-final`, project `-m pytest -q --tb=short`: **3493 passed, 505 skipped, 127 warnings in 1795.09s (0:29:55)**, exit 0; final 12-file reviewed code state |
| Static | Node bindings **589 / 18 states**, frontend api/support JS syntax; project compileall for changed services/main/graph/tests/journey scripts; `git -c core.safecrlf=false diff --check`: passed. Review capture checks added-line whitespace, including untracked files |

Chrome uses internet for existing CDN assets. Synthetic SDK/ASR/httpx fixtures
prove lifecycle mechanics, not live-provider/codec compatibility or quality.
Warnings are existing Starlette/httpx deprecation and SQLite expression-index
reflection notices; optional/environment skips do not prove omitted cases.
Chroma constructors/closers that never return cannot be forcibly interrupted;
T2 removes the unused startup path. A driver/closer that raises is reported, not
proof of successful release. No blanket leak-free/performance/independent claim.

### <a id="r4-s1-t1b--handoff"></a>Handoff

AC1-4 and required gates passed within the available-client/transport scope.
Owned PG stopped successfully (5.51s); no postmaster PID/owned port remains.
Final project Python `.pytest_cache/verify_r4_s1_t1b.py --closed` passed: **885
unrelated prior files**, working DB/HEAD/unrelated status and all **12 reviewed
hashes** preserved; demo health 200, owned PG stopped/PID absent/port closed.
**8 documents / 241 local links**, added-line whitespace, archived IDs/counts,
A's original evidence apart from its repaired parent link, and current/parent/
next-task statuses passed. T1's two leaves are archived; the handoff was condensed
to current scope/setup/risks with historical evidence linked.
Owned app/Chrome/PG stopped; synthetic artifacts retained. Final diff check passed.

**T1B and parent T1 are done. F12 remains open for R4-S1-Q; sprint/PI remain
open.** Exact next: **R4-S1-T2 — Remove unused provenance infrastructure**,
not started. T2 must address the uninterruptible unused Chroma startup path.
No SQL/schema/scoring/UI/dependency or working-data migration; no data cleanup,
demo restart, deployment, live-provider or independent-review claim. Stop after B.

## <a id="r4-s1-t2"></a>R4-S1-T2 — Remove unused provenance infrastructure

Status: done (2026-10-16). PI/sprint: PI-R4 / R4-S1. Audit: F13; F02 cleanup.
Prerequisite: [T1](#r4-s1-t1) done; F13/sprint/PI remain open.

### <a id="r4-s1-t2--contract"></a>Contract

Before T2, default composition built Chroma (or a hashing-based memory fallback)
although provenance used only evaluation-local GitHub observations. Remove that
unused service, embedding code and direct dependency after checking callers.
Retire `vectorstore_backend`, `vectorstore_init_timeout_seconds`,
`chroma_persist_dir`, `chroma_collection`: old constructor/YAML/.env/DEE_ entries
are accepted and ignored through existing extra-setting compatibility; no vector
storage is opened, read, migrated or deleted. Remove shipped defaults/docs that
advertise retrieval. Internal Python vector-store imports/injection are removed;
retain the historical report evidence enum so saved reports still deserialize.

Keep the current typed nine-node graph: its async invocation/state merging and
existing pipeline contracts work, and replacing them offers no required behavior
for this cleanup. No checkpoint/branch/performance claim. No scorer, SQL/schema,
auth/consent/erasure, UI or provider-transport changes. Preserve working data and
all prior edits; do not restart the existing demo.

### <a id="r4-s1-t2--acceptance-and-validation"></a>Acceptance and validation

| ID | Observable criterion | Evidence |
|---|---|---|
| AC1 | Production build/evaluation/cleanup succeeds without any Chroma import or init, including old backend settings | New runtime regression and migrated subprocess HTTP journey |
| AC2 | Retired settings from constructor, YAML, dotenv and environment cannot restore storage; other settings keep their precedence | Config regressions |
| AC3 | Candidate/repo evidence remains scoped; provider refusal and historical `vectorstore` report values still work | Existing provenance/GitHub/pipeline tests; historical report regression |
| AC4 | No unused vector/hash service or dependency; graph choice documented; resource effect measured | Caller/dependency/import checks and controlled before/after construction probe |

Required: focused and full offline pytest, real migrated scratch-app HTTP with
restart/shutdown, dependency/import and diff checks, separate recorded self-review.
Browser execution is not required (no visible handler/contract changes); run UI
bindings as a guard. PostgreSQL competing-transaction/migration gates do not apply
(no SQL, constraints, transactions or migrations change). This does not prove
live providers, fresh dependency resolution, Docker execution or scoring quality.

### <a id="r4-s1-t2--evidence"></a>Evidence

Caller inventory before removal: only production builder and test container
constructed vectors; provenance has no add/query consumer.
`embedding_model` is a separate future model slot and numeric feature vectors are
live SQL-backed product data; neither belongs to this removal. Historical smoke
backend overrides may remain as ignored compatibility inputs, not live settings.

Red: project Python `.pytest_cache/run_r4_s1_t2.py red -m pytest -q --tb=short
tests/test_provenance_runtime.py`: **10 failed, 2 passed, 9.56s**. Default/legacy
Chroma attempts and still-active settings failed their intended assertions;
evaluation/report setup succeeded. Removed the obsolete vector builder tests
and three late-client lifecycle tests with the implementation; retained failed
composition SQL cleanup and borrowed GitHub/LLM/speech coverage.

All runners use `.resume/Scripts/python.exe`; sanitized runner clears inherited
DEE settings/keys, selects absent YAML and no vector override. Logs use
`.pytest_cache/r4-s1-t2-<tag>.txt`. Final focused arguments (`focused-final`):
`-m pytest -q --tb=short tests/test_provenance_runtime.py tests/test_provenance.py
tests/test_github_repo_evidence.py tests/test_service_lifecycle.py
tests/test_services_features.py tests/test_integration.py tests/test_plausibility.py
tests/test_scoring.py tests/test_requirements_pinned.py tests/test_image_contents.py
tests/test_config.py tests/test_smoke_harness.py`: **224 passed, 65.93s**, exit 0.
Initial focused selection named nonexistent `tests/test_domains.py` (exit 4, no
tests); corrected selection passed 106 tests before final preservation/harness
checks. No invalid selection is counted as a successful gate.

| Final gate | Actual result |
|---|---|
| Migrated HTTP | Runner `journey-final scripts/smoke_r4_s1_t2.py`: **12/12**, exit 0, 32.39s. Default then legacy Chroma settings; blocked imports, zero vector threads/directory creation. Revision 0029, two graceful SQL shutdowns; evaluation, two employers/subjects, report/job ownership, portal/search/restart, consent revocation and erasure |
| Packaging | `.resume/Scripts/python.exe .pytest_cache/build_r4_s1_t2.py` builds wheel with isolated scratch Hatchling tools; `pip wheel --no-deps --no-build-isolation --no-index --wheel-dir .pytest_cache/r4-s1-t2-wheel .`. `wheel-import -I .pytest_cache/verify_wheel_r4_s1_t2.py`: metadata excludes Chroma, archive excludes vector module, app/services/graph import from wheel under blocked Chroma imports; exit 0 |
| Static | Project `-m compileall -q` on changed service/config/logging/schema, harness/journey and test files; `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**; `git -c core.safecrlf=false diff --check`: exit 0 |
| Documentation fix | `docs-final -m pytest -q --tb=short tests/test_deploy_doc.py tests/test_provenance_runtime.py`: **18 passed, 1 warning, 10.64s**, exit 0 |
| Full pytest | Runner `full-repeat-final` (no extra args): project `-m pytest -q --tb=short`: **3499 passed, 505 skipped, 127 warnings, 1454.36s (0:24:14)**, exit 0. Warnings: Starlette/httpx deprecation and SQLite expression-index reflection/autogenerate limitations. Skips do not validate omitted environments |
| Preservation | `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t2.py`: **880 unrelated baseline files unchanged**, including working DB; **16 reviewed code hashes match**. Existing demo health **200**, never restarted. Scratch HTTP processes exited gracefully; no owned app/PG/Chrome left running |

Controlled resource probe (`before-probe` / `after-probe
.pytest_cache/probe_r4_s1_t2.py`): same scratch production builder, three builds,
synthetic Chroma constructor sleeps 0.05s. Before: **3 constructions on 3
`chroma-init` threads**, build seconds **[0.1838, 0.0619, 0.0621]**. After:
**0 constructions/threads**, **[0.1849, 0.0138, 0.0141]**. This measures eliminated
synthetic work; cold import noise is visible. No measured live-Chroma latency,
memory reduction, universal speedup or clean-install claim.

### <a id="r4-s1-t2--review-and-handoff"></a>Review and handoff

Separate same-agent review on HEAD `5480498` plus this session's service/config,
dependency/Docker/CI, smoke harness, tests and current documentation edits. Read
the removed path and its callers before deletion; prior T1 lifecycle/SQL and
earlier remediation edits remain outside this session's change. AC1–4 map to the
runtime/config/evidence tests, packaging and migrated HTTP. Checked default and
legacy sources, saved enum values, borrowed-provider cleanup, failure paths and
legacy-directory preservation. No SQL/schema/API/scorer/visible UI changes.
No remaining acceptance-blocking source finding; this is self-review, not an
independent review. Final full pytest and preservation gates passed on the same
reviewed code; only documentation changed after the initial full run.

Final regression exposed one low-severity documentation finding at `DEPLOY.md`
Expected variables: listing retired settings there conflicted with the active
configuration contract/guard. Moved the compatibility note to separate prose
linked to FLOW's canonical keys. No guard weakened or runtime change introduced;
affected documentation/config checks and full suite passed after correction.
Initial `full-final`: **1 failed, 3498 passed, 505 skipped, 127 warnings,
1199.38s**; only failure was this documentation guard, now resolved.

An optional initial wheel command could not import `hatchling.build` from the
project environment. Installed build tools only into ignored scratch storage;
the same no-deps/no-index wheel build then succeeded without changing `.resume`.
This is packaging evidence, not a clean transitive dependency resolution.

AC1–4 and required gates complete. No schema/data migration or cleanup; existing
legacy directories and installed environments are preserved. Graph retained for
the rationale above. No browser/PG/live-provider/quality or Docker execution
claim; dependency resolution/reproducibility remains R4-S3-T3.

Stop after T2. Exact next task: R4-S1-T3, split routes by product area (partition
the first cohesive router into a bounded contract before implementing).

Final handoff checks: **122 local links** resolve across the changed handoff,
PI/delivery/task/feature/deployment/requirements records; T1/T2 done, T3 pending,
PI in progress. New-file whitespace and final diff checks passed. Preservation
was repeated after these updates with the same 880/16 hashes and demo HTTP 200.

## <a id="r4-s1-t3a"></a>R4-S1-T3A — Extract authentication/session routes

Status: done (2026-10-17). Parent: [T3](tasks/R4-S1-T3.md). PI-R4 / R4-S1; F13.
Prerequisite: [T2](#r4-s1-t2), done. Only child authorized for this session.

### <a id="r4-s1-t3a--contract"></a>Contract

Move the 12 `/auth/*` operations, their request/response DTOs and OTP/cookie
helpers into `app.api.auth`. Move existing principal resolution, CSRF enforcement,
request-service lookup, client-IP hashing and 429 translation into
`app.api.dependencies`, imported by remaining handlers. No behavior redesign.
Keep the resolvers/allowlist imported from `routes` as identity-preserving aliases
for existing guards/callers; the app explicitly imports the extracted auth router.
Preserve OpenAPI schema names, operation IDs, router ordering, statuses, generic
OTP/anti-enumeration responses, cookie flags, session-first CSRF and revocation.
No admin-account/product routes, SQL/migrations, service logic, UI or dependencies
changed. Never read/migrate working storage or restart the running demo.

This is a pure extraction, with no runtime defect claimed. Characterize the
current behavior before moving it, rather than labeling an absent module/import
as a behavioral reproduction. Compare the same wire contracts after extraction.

### <a id="r4-s1-t3a--acceptance-and-tests"></a>Acceptance and tests

| ID | Observable criterion | Evidence planned |
|---|---|---|
| AC1 | Full OpenAPI and ordered method/path/ID/auth-dependency contracts unchanged | Captured pre-move runtime contract, repository digest fixture and comparison regression |
| AC2 | Candidate, org and admin login/session flows preserve cookies, CSRF and ownership | Auth/session/CSRF/rate-limit pytest and migrated real HTTP restart journey |
| AC3 | Extracted auth router can register independently with the same dependency identities and no duplicate app routes | Standalone router HTTP test; existing all-route/auth-plane guards |
| AC4 | Existing candidate/employer/admin product handlers keep shared resolver behavior | Route/OpenAPI/auth guards; two-actor cross-plane API journey and actual Chrome login/reload/logout |

Required: focused/full offline pytest, migrated scratch subprocess HTTP, actual
Chrome for affected auth navigation, UI bindings, import/compile/diff checks and
separate self-review. PostgreSQL lock/migration gates do not apply: no SQL,
constraints, transaction semantics or migrations change. Fakes prove mechanics,
not provider delivery or assessment quality. No independent review claimed.

### <a id="r4-s1-t3a--evidence-and-review"></a>Evidence and review

Pre-move runtime snapshot: **102 operations**, full OpenAPI and ordered recursive
dependency contract. Baseline `baseline-final` passed **66 tests, 1 warning,
34.48s**. Two early baseline attempts failed only because capture had not written
the fixture yet (65 passed/one missing-fixture failure each); a capture runner
import-path error and a shell Unicode marker error were corrected before moving
source. These are setup failures, not a behavioral defect reproduction.

Moved handlers/DTOs into `api/auth.py` and shared helpers into `api/dependencies.py`;
main imports auth explicitly; existing route aliases retain identity. Existing
product handlers remain in place. `routes.py` shrinks to 2,370 lines (from 2,871).
The capture's full document stays in ignored scratch; its digest/operation count
is in `tests/fixtures/api_contract_r4_s1_t3.json`. Final tests compare
the same full wire contract, not just bindings or source text.

Separate same-agent review: HEAD `5480498` plus this session's API modules/main,
new contract/standalone test, fixture and migrated smoke. Compared **185 original
function/class ASTs**, all unchanged; reviewed imports and the actual moved bodies,
CSRF/session-before-header ordering, model names, auth registration, denial paths,
ownership, and deferred `CandidateCreateResponse` import. No circular imports or
duplicate registration; no remaining acceptance-blocking source finding. A quoted
read-only search briefly escaped its intended folders; stopped it and repeated
with literal, bounded paths. No files changed from that search. Self-review is
not independent review; no SQL/scorer/provider/visible UI implementation changed.

Seven reviewed code/contract files have recorded hashes. Logs use
`.pytest_cache/r4-s1-t3a-<tag>.txt`; runner is
`.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3a.py <tag> <Python args>`
(no extra arguments runs `-m pytest -q --tb=short`). It clears inherited DEE
settings/keys, selects absent YAML, and uses scratch/fake-provider setups.

Final focused arguments (`focused-final`): `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_auth_api.py
tests/test_route_table_guard.py tests/test_openapi_contract.py
tests/test_api_auth_gate.py tests/test_org_scope_guard.py tests/test_ratelimit_auth.py
tests/test_cookie_posture.py tests/test_auth_debug_echo.py
tests/test_auth_org_name_taken.py tests/test_portal_sessions.py
tests/test_candidate_login_binding.py tests/test_login_redemption_validity.py
tests/test_error_logging.py`.

| Final gate | Actual evidence |
|---|---|
| Focused | **144 passed, 12 skipped, 1 warning, 86.19s**, exit 0. Starlette/httpx deprecation; skipped environment cases are not proof of those environments |
| Migrated HTTP | `journey-final scripts/smoke_r4_s1_t3a.py`: **20/20**, exit 0, 55.06s. All three planes, second employer/device, cookie posture, CSRF/header precedence, ownership, anti-enumeration, generic invalid code, revocation/logout and restart; two revision-0029 graceful SQL lifespans |
| Actual Chrome | `browser-final scripts/check_ui_evaluate_browser.py`: **31/31** plus **1/1** startup, exit 0, 48.68s. Org/admin/candidate login, report/feedback/reload, expiry/old-session handling, contact path and no console exceptions. Migrated scratch app with captured mail/fake providers; existing CDN internet required |
| Imports | `import-final -I .pytest_cache/check_import_r4_s1_t3a.py`: exit 0, 14.74s. Auth imports without product routes loaded, registers 12 standalone operations; legacy resolver/allowlist/router identities preserved |
| Static | Project `-m compileall -q src/app/api/routes.py src/app/api/auth.py src/app/api/dependencies.py src/app/main.py tests/test_api_route_extraction.py scripts/smoke_r4_s1_t3a.py`; Node UI bindings **589/18 states**; `git -c core.safecrlf=false diff --check`: passed |
| Full pytest | `full-final`, no extra arguments: **3502 passed, 505 skipped, 127 warnings, 1096.23s (0:18:16)**, exit 0. Warnings: Starlette/httpx deprecation and SQLite expression-index reflection/autogenerate limits. Skips do not prove omitted environments |
| Preservation | `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3a.py`: **897 unrelated baseline files unchanged**, including working DB; **7 reviewed code hashes match**; existing demo health **200**. Scratch HTTP processes exited gracefully; owned browser/app processes stopped |

OpenAPI/ordered dependency contract remains the captured 102-operation digest
`cbdd461be76f67469f960cc56e6349e90ed99003db24b0acc7c4f45f2817e2b5`.
AST comparison is supporting move-review evidence; runtime/HTTP/Chrome checks
above supply separate behavior evidence. Final full pytest passed on the reviewed
code hashes; no application code changed afterward. Preserve this fixture through
the remaining pure extractions; intentional wire changes require explicit review.

### <a id="r4-s1-t3a--handoff"></a>Handoff

AC1–4 and required gates passed. No database/schema/API/scorer/UI behavior change,
working-data migration, new live-provider/PG/quality or independent-review claim.
No deployment/commit/push. Parent T3/F13/sprint/PI remain open; remaining product
handlers are still in `routes.py`. Stop after T3A. Exact next child: T3B,
evaluation and operator reports/outcomes; write its bounded contract first.

Final handoff verification: **96 local links** resolve across the current
handoff/PI/parent/child/feature/auth records; A done, twelve children pending,
parent/PI open and next B are consistent. New-file whitespace and final diff
checks passed. Preservation repeated after documentation updates: same 897
unrelated files, seven reviewed hashes and existing demo HTTP 200.

## <a id="r4-s1-t3b"></a>R4-S1-T3B — Extract evaluation and operator report/outcome routes

Status: done (2026-10-18). Parent: [T3](tasks/R4-S1-T3.md). PI-R4 / R4-S1; F13.
Prerequisite: [T3A](#r4-s1-t3a), done. Only current-session child.

### <a id="r4-s1-t3b--contract"></a>Contract

Move `POST /evaluate`, `GET /report/{report_id}`, and the operator outcome
write/list handlers into `app.api.reports`, with their request/response DTOs and
shared outcome helpers. Remaining employer handlers import those same models and
helpers, preserving one validation/provenance path. Candidate ingest, screening,
services/stores, scorer, SQL/migrations, UI and dependencies remain out of scope.

Preserve the 102-operation full OpenAPI and ordered dependency digest from A,
including schema text, route order and one admin resolver per moved operation.
The four operations occupy two positions in the existing admin sequence: use
two small registration groups in this one cohesive report-workflow module.
Compose their already-guarded APIRoute lists at the original positions in the
existing aggregate router. This retains the exact route/dependency structure,
without nested include contexts, duplicate gates, route copies or slice indexes.
Each group also registers independently through normal FastAPI inclusion.

No runtime defect is claimed for this pure extraction. Add/execute behavioral
characterization before moving definitions; import/setup failures are not a red
defect reproduction. Keep original handler/model bodies and supported aliases.
Preserve advisory/human review, domain independence, malformed-input refusals,
saved-report rechecks, outcome bounds/provenance and erasure races. Never migrate
working storage, discard prior edits, or restart the existing demo.

### <a id="r4-s1-t3b--acceptance-and-evidence-mapping"></a>Acceptance and evidence mapping

| ID | Observable criterion | Validation |
|---|---|---|
| AC1 | Full OpenAPI and ordered route/auth dependency contract unchanged | Existing digest/route/OpenAPI guards; exact move comparison |
| AC2 | Four report-workflow operations run independently and keep admin/CSRF boundaries, persistence and failure behavior | New standalone workflow regression; API/auth/input/outcome/erasure tests |
| AC3 | Employer report/outcome ownership and shared DTO/helper behavior stay intact | Two-employer outcomes/provenance tests and migrated HTTP/restart |
| AC4 | Real operator/employer evaluation, feedback and reload/error journeys remain usable | Actual Chrome evaluation journey, migrated scratch HTTP, import/static checks |

Required: focused/full offline pytest; real migrated scratch HTTP/restart; actual
Chrome; UI bindings; import/compile/diff checks; separate self-review and final
preservation. No PostgreSQL lock/migration gate (no SQL, constraint, transaction
or migration change). Fakes do not establish live delivery/provider quality.
Same-agent review is not independent review; parent/sprint/PI remain open.

### <a id="r4-s1-t3b--evidence-and-review"></a>Evidence and review

Pre-move characterization (`baseline`) passed **53 tests, 1 warning, 22.49s**,
including the new workflow test and existing full-contract/ownership guards.
This is green characterization, not a defect reproduction. Extracted the four
operations plus four DTOs/two shared helpers into `api/reports.py`. Remaining
employer handlers import the shared contracts/helpers. `routes.py` shrinks from
2,370 to **2,223 lines**; registration positions stay unchanged.

Separate same-agent review on HEAD `5480498` plus this session's route/report
module, standalone test and current source-map/task docs. Compared **152 original
class/function bodies and function signatures**, unchanged; reviewed the moved
code and actual callers, guarded route-list composition, parent router options,
deferred candidate projection import, CSRF/identity, error/erasure snapshots,
notes bounds and operator/employer provenance. Full 102-operation contract passes
without regenerating its fixture. No blocking source finding remains; this is
self-review, not independent review. Four reviewed code/contract hashes recorded.
No SQL/service/scorer/UI implementation, deployment, commit or push change.

Initial post-move focus: **285 passed, 2 skipped, 1 warning, 36.92s**.
Runners use `.resume/Scripts/python.exe
.pytest_cache/run_r4_s1_t3b.py <tag> <Python args>`; no extra args run
`-m pytest -q --tb=short`. Runner clears inherited DEE keys/config and selects
absent YAML; journeys use isolated stores and fake/capture providers. Logs:
`.pytest_cache/r4-s1-t3b-<tag>.txt`.

Reuse `scripts/smoke_r3_s1_q.py` for migrated three-plane evaluation, operator/
employer outcomes, ownership and restart. Its Windows stop uses process terminate;
that proves restart/persistence, not graceful lifespan cleanup. No SQL/provider
lifecycle code changes here; prior T1 evidence owns that separate contract.

Final focused arguments (`focused-final`): `-m pytest -q --tb=short
tests/test_operator_report_extraction.py tests/test_api_route_extraction.py
tests/test_api.py tests/test_screening_outcome_api.py tests/test_api_auth_gate.py
tests/test_route_table_guard.py tests/test_openapi_contract.py
tests/test_report_outcomes.py tests/test_report_response_erasure.py
tests/test_report_review_context.py tests/test_model_output_boundaries.py
tests/test_error_logging.py`.

| Final gate | Actual evidence |
|---|---|
| Focused | **285 passed, 2 skipped, 1 warning, 55.07s**, exit 0. Starlette/httpx deprecation; environment skips do not prove omitted cases |
| Migrated HTTP | `journey-final scripts/smoke_r3_s1_q.py`: **20/20**, exit 0, 53.70s. Revision 0029; all three cookie planes, operator report/outcomes and exact restart persistence, two-employer ownership/provenance, invalid/PDF input, CSRF, contact/erasure and safe logs. Windows termination qualifier above applies |
| Actual Chrome | `browser-final scripts/check_ui_evaluate_browser.py`: **31/31** plus **1/1** startup, exit 0, 48.22s. Actual operator/employer report/feedback/reload, candidate/auth/contact and timeout/error/expiry flows; no console exceptions. Scratch app, fake/capture providers; existing CDN internet required |
| Imports | `import-final -I .pytest_cache/check_import_r4_s1_t3b.py`: exit 0, 8.73s. Report workflow imports without remaining product routes, groups contain 1+3 operations with one admin dependency each; shared object identities and single composition preserved |
| Static | Project `-m compileall -q src/app/api/routes.py src/app/api/reports.py tests/test_operator_report_extraction.py`; `node scripts/check_ui_bindings.js`: **589/18 states**; `git -c core.safecrlf=false diff --check`: passed |
| Full pytest | `full-final`, no extra arguments: **3503 passed, 505 skipped, 127 warnings, 926.85s (0:15:26)**, exit 0. Warnings: Starlette/httpx deprecation and SQLite expression-index reflection/autogenerate limits. Skips do not prove omitted environments |
| Preservation | `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3b.py`: **903 unrelated baseline files unchanged**, including working DB; **4 reviewed code/contract hashes match**; existing demo health **200**. Scratch app/browser processes stopped; existing demo never restarted |

Captured contract remains **102 operations**, digest
`cbdd461be76f67469f960cc56e6349e90ed99003db24b0acc7c4f45f2817e2b5`.
AST comparison supports the move review; separate runtime/HTTP/Chrome checks
above provide behavior evidence. No guard weakened or fixture regenerated. Full
pytest passed on the reviewed hashes; only documentation changed afterward.

### <a id="r4-s1-t3b--handoff"></a>Handoff

AC1–4 and required gates passed. No schema/data migration or cleanup, SQL/service/
scorer/UI behavior change, live-provider/quality/PG or independent-review claim.
No deployment, commit or push. Parent T3/F13/sprint/PI remain open; other product
handlers remain in `routes.py`. Stop after B. Exact next child: R4-S1-T3C,
candidate intake/resume management and profile sources. Write C's bounded contract
before implementation.

Final handoff checks: **218 local links** resolve across the changed operational
records/source maps; A/B done, eleven children pending, parent/PI open and next C
are consistent. New-file whitespace and final diff checks passed. Preservation
repeated after documentation updates: same 903 unrelated files, four reviewed
code/contract hashes and existing demo HTTP 200.

## <a id="r4-s1-t3c"></a>R4-S1-T3C — Extract candidate intake, resumes and profile-source routes

Status: done (2026-10-18). Parent: [T3](tasks/R4-S1-T3.md). PI-R4 / R4-S1;
F13. Prerequisite: [T3B](#r4-s1-t3b), done. Only this child this session.

### <a id="r4-s1-t3c--contract"></a>Contract

Move the ten contiguous admin candidate operations (intake, detail, resumes,
reports, candidate/resume erasure, key issuance and GitHub/LinkedIn source
ingestion/listing) and their DTOs/shared intake adapter into `app.api.candidates`.
Keep employer screening handlers and portal erasure in the aggregate module;
they import the same intake and erasure contracts. Update projection's deferred
type import to the new owner without adding a runtime import cycle.

Compose the guarded candidate router's existing APIRoutes at their original
position. Preserve the captured full 102-operation OpenAPI/ordered dependency
contract, one admin resolver per operation, central CSRF, ownership/error
responses and supported aliases. No service/store/SQL/migration/scorer/frontend
change, routing framework or new DTO layer. Working storage, prior edits and
the running demo remain preserved.

This is a pure extraction, with green pre-move behavioral characterization;
no runtime defect or red defect reproducer is claimed. Test the workflow using
the aggregate router before the move and the standalone area router afterward.

### <a id="r4-s1-t3c--acceptance-and-evidence-mapping"></a>Acceptance and evidence mapping

| ID | Observable criterion | Validation |
|---|---|---|
| AC1 | Full API schemas, ordered routes/dependencies and shared DTO identity unchanged | Existing full contract/route/OpenAPI guards; move comparison and isolated import |
| AC2 | Candidate lifecycle works independently with admin/header/session CSRF gates, dedup/versioning and resume ownership | New standalone workflow; candidate/auth/input/erasure regressions |
| AC3 | Source advisory behavior, malformed transport, filtered reads and erasure preserved | Source API/service/erasure regressions and migrated HTTP/restart |
| AC4 | Employer intake uses the same adapter with tenant isolation/redaction; visible intake still works | Screening/projection regressions, two-employer HTTP and actual Chrome evaluation/reload/error journey |

Required: final focused/full offline pytest, migrated scratch HTTP/restart,
actual Chrome, UI bindings, import/compile/diff checks, separate self-review and
preservation. PostgreSQL lock/migration gate does not apply: no SQL, constraint,
transaction or migration changes. Synthetic providers prove mechanics; no live
provider/quality or independent-review claim. Parent/sprint/PI stay open.

### <a id="r4-s1-t3c--evidence-and-review"></a>Evidence and review

Pre-move characterization (`pre-move`) passed **39 tests, 1 warning, 26.08s**.
It used the aggregate router; afterward the new workflow uses the standalone
candidate router. Initial draft assertions were corrected to the existing admin
profile/contact schema; those failures are test corrections, not defect evidence.
The move extracts ten operations, ten DTOs and the shared `_ingest_one` adapter.
`routes.py` shrinks from 2,223 to **1,929 lines**; `api/candidates.py` is 325 lines.
Employer intake and portal erasure retain shared object identity. Projection's
type import remains deferred, with its pointer updated to the new DTO owner.

Separate same-agent review: HEAD `5480498` plus the candidate/aggregate/projection
diff, standalone tests, HTTP runner and source maps. Specification review covers
AC1–4, unchanged full contract and original registration position. Correctness
review covers import callers/cycles, admin/CSRF versus candidate/employer gates,
dedup/versioning, cross-candidate resume refusal, source transport/unavailability,
report/key/source erasure, tenant redaction, snapshots and restart persistence.
All **142 original class/function definitions, signatures and decorators** compare
unchanged across the aggregate and area module. Follow-up import/reference review
confirms no removed aggregate import is still referenced by its handlers.
Six reviewed code/contract hashes
are recorded; this supports move review, not runtime/browser evidence.

Resolved review/validation findings:

- **Medium, `routes.py:portal_me`:** removing the source-store import also removed
  `SourceSubjectErasedError`, still used in the portal's exception tuple. Erasure
  during an aggregate read returned 500 instead of 404. Existing controlled
  `tests/test_aggregate_erasure.py` reproduced it in `full-diagnostic -m pytest
  -q -x --tb=short`: **1 failed, 4 passed, 1 warning, 27.65s**; restore that remaining import. Superseded focused/full runs
  were stopped after diagnosis; they are not passing runs.
- **Test harness, `smoke_r4_s1_t3c.py`:** the long fixture has a GitHub link, so
  no explicit handle resolves successfully. Use an invalid explicit handle for
  the 400 case. Check the full recorded revision `0029_candidate_login_binding`,
  rather than the abbreviated `0029`. Prior journey ran 20/21 behavior checks;
  the lifecycle assertion was false despite both actual graceful shutdowns.
- **Low, `CANDIDATES.md`:** its existing T2B evidence link still pointed at
  `tasks/` after archival. Link validation found it while updating the source
  map; point it at the existing archived record. No application change.

No blocking finding remains in the reviewed scope. Final validation below passed
on the reviewed fix; no independent review, SQL/service/scorer/UI implementation,
live-provider/quality/PG, deployment, commit or push claim.

Runners use `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3c.py <tag>
<Python args>`; omitted args run `-m pytest -q --tb=short`. Inherited DEE settings/
keys are cleared and an absent YAML is selected. Logs are
`.pytest_cache/r4-s1-t3c-<tag>.txt`. All journeys use isolated migrated storage and
fake/capture providers; Chrome uses the existing CDN runtime internet.

Post-move contract focus: **75 passed, 1 warning, 32.11s** (`post-move`), before
the broader suite exposed the portal import finding above. Final validation
uses the corrected import and the following focused arguments (`focused-reviewed`):
`-m pytest -q --tb=short tests/test_candidate_route_extraction.py
tests/test_api_route_extraction.py tests/test_candidates_api.py
tests/test_profile_sources_api.py tests/test_screening_api.py
tests/test_screening_projection.py tests/test_screening_ingest.py
tests/test_ingest_response_erasure.py tests/test_ingest_erasure_concurrency.py
tests/test_profile_source_erasure.py tests/test_aggregate_erasure.py
tests/test_resume_input_boundary.py tests/test_candidate_auth_api.py
tests/test_candidate_auth.py tests/test_portal_api.py tests/test_api_auth_gate.py
tests/test_route_table_guard.py tests/test_org_scope_guard.py
tests/test_openapi_contract.py tests/test_model_output_boundaries.py`.

| Final gate | Actual evidence |
|---|---|
| Focused | `focused-reviewed`: **469 passed, 49 skipped, 1 warning, 230.65s (0:03:50)**, exit 0. Includes controlled aggregate/source/ingest erasure and standalone candidate lifecycle/CSRF. Starlette/httpx deprecation; PostgreSQL skips do not validate those cases |
| Migrated HTTP | `journey-reviewed scripts/smoke_r4_s1_t3c.py`: **21/21**, exit 0, 46.31s. Production SQL composition, revision 0029, admin cookie/CSRF and candidate key, dedup/versioning, resume ownership, source ingestion/history, two-employer isolation/redaction, exact restart state, erasure and graceful cleanup |
| Actual Chrome | `browser-reviewed scripts/check_ui_evaluate_browser.py`: **31/31** plus **1/1** startup, exit 0, 39.15s. Employer shared intake/report/feedback/reload and timeout/error/expiry, operator evaluation, candidate/auth/contact flow; no console exceptions. Profile sources are API-only; no source-management UI claim |
| Imports | `import-reviewed -I .pytest_cache/check_import_r4_s1_t3c.py`: exit 0, 4.50s. Standalone candidate import without remaining product routes, ten operations with one admin dependency each, shared DTO/adapter identity, single ordered composition |
| Static | Project `-m compileall -q src/app/api/routes.py src/app/api/candidates.py src/app/screening/projection.py tests/test_candidate_route_extraction.py scripts/smoke_r4_s1_t3c.py`; `node scripts/check_ui_bindings.js`: **589/18 states**; `git -c core.safecrlf=false diff --check`: passed |
| Full pytest | `full-reviewed`, no extra arguments: **3506 passed, 505 skipped, 127 warnings, 1494.16s (0:24:54)**, exit 0. Starlette/httpx deprecation and SQLite expression-index reflection/autogenerate warnings; omitted environments are not validated |
| Preservation | `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3c.py`: **903 unrelated baseline files unchanged**, including working DB; six reviewed code/contract hashes match; existing demo health **200**. Scratch HTTP/browser processes stopped; final handoff checks recorded below |

The full captured contract stays **102 operations**, digest
`cbdd461be76f67469f960cc56e6349e90ed99003db24b0acc7c4f45f2817e2b5`;
its fixture was not regenerated. Two successful final HTTP starts/shutdowns were
graceful; Chrome's Windows process stop is forced. Earlier browser run also passed
31/31; final browser reran after restoring the portal exception import. No broader
provider-cleanup, live compatibility or assessment-quality claim.

### <a id="r4-s1-t3c--handoff"></a>Handoff

AC1–4 and all required gates passed. The full suite ran on the reviewed code;
only documentation changed afterward. No SQL/schema/scorer/UI behavior or working
data change. Synthetic providers and environment skips retain the limits above.
No deployment, commit or push. Parent T3/F13/sprint/PI remain open. Stop after C.

Exact next child: R4-S1-T3D, employer screening/batches/queue and scoped
reports/outcomes, not started. Write its bounded contract first; trace the shared
candidate adapter, report/outcome helpers, batch DTOs and org-scope guard before
moving handlers. Retain the full contract and central auth/CSRF. T4 remains
unstarted.

Final handoff checks: **324 local links** resolve across the changed operational
records/source maps; A/B/C done, ten children pending, parent/PI open and next D
are consistent. New-file trailing-space and final diff checks passed. Preservation
repeated after documentation updates: the same 903 unrelated files, six reviewed
code/contract hashes and existing demo HTTP 200. No scratch HTTP/CDP processes
remain. The existing demo was never restarted.

## <a id="r4-s1-t3d"></a>R4-S1-T3D — Extract employer screening, batches, queue and scoped reports

Status: done (2026-10-18). Parent: [T3](tasks/R4-S1-T3.md). PI-R4 / R4-S1;
F13. Prerequisite: [T3C](#r4-s1-t3c), done. Only this child this session.

### <a id="r4-s1-t3d--contract"></a>Contract

Move the thirteen contiguous employer screening operations (single intake,
scoped report/candidate-report reads, outcome write/list, batch registration,
list/detail/process/retry/queue/summary/delete), three batch DTOs and two helpers
into `app.api.screening`. Preserve each handler's explicit `require_org` and
central principal/CSRF resolution. Compose that router's existing APIRoutes at
their original position in the aggregate org router, without another dependency
context. Reuse candidate intake DTOs/adapter and report/outcome DTOs/helpers.
Retain aliases used by existing callers and the captured full 102-operation
OpenAPI/ordered dependency contract. Do not regenerate its fixture.

No runtime defect is claimed for the extraction. Add and run green workflow
characterization using the aggregate org router before moving definitions, then
run it using the standalone screening router. Trace actual imports and remaining
global references before removing imports. The org-scope guard still inspects
each endpoint and its same-module helpers; preserve its existing limits and
non-vacuity assertions. No new dependency/routing abstraction or SQL, migration,
service, scorer, auth policy or frontend implementation change. Preserve prior
edits, working storage and the existing demo.

### <a id="r4-s1-t3d--acceptance-and-validation"></a>Acceptance and validation

| ID | Observable criterion | Evidence |
|---|---|---|
| AC1 | Full API schemas, operation order and dependency/auth contract unchanged; no duplicate/unguarded routes or import cycles | Full contract/route/OpenAPI guards, move/import review and isolated import |
| AC2 | Standalone screening preserves intake/redaction, scoped report/outcome reads/writes and two-employer non-disclosure | New complete workflow, screening/outcome/projection/auth regressions; migrated HTTP/restart |
| AC3 | Batches retain atomic input refusal, bounded processing, cursor/error/retry behavior, safe queue summaries and deletion | Standalone batch workflow, batch/retry/rate/erasure tests; migrated HTTP |
| AC4 | Cookie CSRF and human/machine provenance remain correct; actual screening screens and reload/error journeys work | Standalone cookie workflow, actual Chrome batch journey and UI HTTP contract |

Required: focused/full offline pytest; migrated scratch HTTP/restart; actual
Chrome; UI bindings; import/compile/diff checks; separate same-agent review and
preservation. No PostgreSQL lock/migration gate: no SQL/constraint/transaction/
migration changes. Environment skips are not evidence for omitted cases; fake
providers and browser CDN access do not establish live-provider quality. No
independent review, deployment, commit/push or parent/sprint/PI closure implied.

### <a id="r4-s1-t3d--evidence-and-review"></a>Evidence and review

Green pre-move characterization (`characterization`) passed **50 tests,
1 warning, 13.16s** using the aggregate org router. Initial draft assertions
returned **2 failed, 48 passed, 1 warning, 15.04s** (`pre-move`): malformed PDF
transport uses `item 1: pdf_parse_failed`, and `/auth/me` intentionally omits
the human ID. Corrected those assertions and read the verified signup account
from the isolated auth store for provenance. These were test corrections, not
runtime defect reproductions. After extraction, the same workflow runs with
the standalone router. Post-move API/auth/guard focus: **72 passed, 1 warning,
14.76s** (`post-move`).

Extracted thirteen operations, three DTOs and `_batch_texts`/`_org_user_id` into
the 332-line `api/screening.py`. The aggregate shrinks from 1,929 to **1,626
lines**. Candidate/report shared contracts and legacy aliases retain identity;
the new module has no remaining-product-route import. Org-scope guard changes
only clarify its actual endpoint-module scope; no detector/allowlist/floor change.

Separate same-agent review: HEAD `5480498` plus the aggregate/screening diff,
workflow/guard tests, HTTP/browser runners and source maps. Specification review
maps AC1–4 to contract, standalone API, real HTTP and actual Chrome evidence.
Correctness review checked principal/CSRF order, imported globals/cycles, source
caps and atomic refusal, human/machine attribution, tenant 404 behavior, private
operator judgments, report/farm projection, cursors, retry/erasure snapshots,
restart and cleanup. **121 original class/function definitions, signatures and
decorators are unchanged** across the two modules. No removed import remains
referenced by aggregate handlers. Seven reviewed code/contract hashes recorded;
this supports move review and does not replace behavior/journey evidence.

Review finding (low, browser harness): `Page.reload` acknowledgement can arrive
before the old document disappears, so visible authenticated text alone can
match the old page. Add a pre-reload window marker and wait for its removal
plus authenticated text in the new document before continuing. Final actual
Chrome rerun passed. No blocking source finding remains in this reviewed scope;
this is self-review, not independent review. No SQL/service/scorer/UI behavior,
live-provider/quality/PG, deployment, commit or push claim.

Commands use `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3d.py <tag>
<Python args>`; omitted args run `-m pytest -q --tb=short`. Inherited DEE config/
keys are cleared and an absent YAML selected. Logs are
`.pytest_cache/r4-s1-t3d-<tag>.txt`. Journeys use migrated disposable stores and
fake/capture providers. Chrome requires the existing CDN runtime internet.

Final focus (`focused-reviewed`): `-m pytest -q --tb=short
tests/test_screening_route_extraction.py tests/test_api_route_extraction.py
tests/test_screening_api.py tests/test_screening_batches_api.py
tests/test_screening_outcome_api.py tests/test_screening_tenancy.py
tests/test_screening_scope.py tests/test_screening_retry.py
tests/test_screening_refusal_retention.py tests/test_screening_unresolved_input.py
tests/test_screening_erasure_concurrency.py tests/test_screening_durable_input.py
tests/test_screening_report_input.py tests/test_asserted_contact_api.py
tests/test_asserted_contact_batch.py tests/test_ingest_response_erasure.py
tests/test_ingest_erasure_concurrency.py tests/test_org_scope_guard.py
tests/test_api_auth_gate.py tests/test_route_table_guard.py
tests/test_openapi_contract.py tests/test_ratelimit_wiring.py`.

| Final gate | Actual evidence |
|---|---|
| Focused | `focused-reviewed`: **247 passed, 83 skipped, 3 warnings, 110.01s (0:01:50)**, exit 0. Starlette/httpx deprecation and SQLite expression-index reflection warnings; PostgreSQL skips do not validate those cases |
| Migrated HTTP | `journey scripts/smoke_r4_s1_t3d.py`: **31/31** reused UI HTTP contract plus **16/16** screening/restart checks, exit 0, 26.24s. Revision 0029; real cookie/CSRF and human attribution, two-tenant privacy, operator-note exclusion, configured one-item processing bound, exact batch/queue/summary/report/outcome restart state and graceful SQL disposal. HTTP contract simulation is not Chrome |
| Actual Chrome | `browser-reviewed scripts/check_ui_screening_extraction_browser.py`: **24/24**, exit 0, 26.42s. File picker/text/PDF, bounded driver, queue privacy, report feedback/history, summary, actual batch deletion, second file intake, authenticated new-document reload and injected 503 read/recovery; no console exceptions |
| Imports | `import-reviewed -I .pytest_cache/check_import_r4_s1_t3d.py`: exit 0, 3.76s. Standalone screening import without aggregate routes, thirteen explicit single-org dependencies, shared/legacy object identities and single ordered composition |
| Static | Project `-m compileall -q` on the two API modules, workflow/guard tests and HTTP/browser runners; `node scripts/check_ui_bindings.js`: **589/18 states**; tracked `git -c core.safecrlf=false diff --check` and no-index whitespace checks on all five new files passed |
| Full pytest | `full-reviewed`, no extra arguments: **3510 passed, 505 skipped, 127 warnings, 783.67s (0:13:03)**, exit 0. Starlette/httpx deprecation and SQLite expression-index reflection/autogenerate warnings; omitted environments are not validated |
| Preservation | `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3d.py`: **908 unrelated baseline files unchanged**, including working DB; seven reviewed code/contract hashes match; existing demo health **200**. Final documentation/process checks recorded below |

The full contract remains **102 operations**, digest
`cbdd461be76f67469f960cc56e6349e90ed99003db24b0acc7c4f45f2817e2b5`;
the fixture was not regenerated. Actual Chrome's Windows process stop is forced;
HTTP's two application lifespans shut down gracefully. Neither proves general
live-provider cleanup or assessment quality.

### <a id="r4-s1-t3d--handoff"></a>Handoff

AC1–4 and required gates passed. Full pytest ran on the reviewed code; only
documentation changed afterward. No SQL/schema/scorer/UI behavior or working
data change. Environment skips, synthetic-provider limits and same-agent review
qualifications above remain. No deployment, commit or push. Parent
T3/F13/sprint/PI remain open. Stop after D.

Exact next child: R4-S1-T3E, ledger organizations, consent, records, coding and
reputation, not started. Write its bounded contract first; trace the admin/org
plane split, shared ledger schemas/helpers and remaining request/response DTOs.
Retain the full contract and central auth/CSRF. T4 remains unstarted.

Final handoff checks: **323 local links** resolve across changed operational
records/source maps; A/B/C/D done, nine children pending, parent/PI open and next E
are consistent. Tracked diff and all five new-file whitespace checks passed.
Preservation repeated after documentation updates: the same 908 unrelated files,
seven reviewed code/contract hashes and existing demo HTTP 200. Scratch HTTP/CDP
processes are absent; the existing demo was never restarted.

## <a id="r4-s1-t3e"></a>R4-S1-T3E - Extract ledger administration and employer evidence routes

Status: done (2026-10-20). Parent: [T3](tasks/R4-S1-T3.md). PI-R4 / R4-S1;
F13. Prerequisite: [T3D](#r4-s1-t3d), done. Only E completed this session.

### <a id="r4-s1-t3e--contract"></a>Contract

Trigger: production composition or standalone ledger-router mounting. Move the
eight admin organization/consent operations and six organization record/event,
coding and reputation operations into `app/api/ledger.py`, with their ten DTOs.
Keep admin `require_api_key` and explicit per-operation `require_org` dependencies,
their order, endpoint names and the complete 102-operation OpenAPI contract.
Compose the extracted routes at their existing positions without adding inherited
dependencies. The portal reuses `ConsentRevokedResponse` from its new owner;
consent schemas/errors still used by other areas retain their current owners.
No dependency framework or new service layer is needed.

Preserve one-time key output, rotation/offboarding invalidation, duplicate-org
409, missing-resource 404, invalid-input 422, cookie CSRF (including session
precedence over keys), event ownership, purpose/org/expiry/revocation consent
gates, allowed/denied read audits and advisory reputation. Consent-gated ledger
reads are intentionally cross-company; possession of another org's key alone
does not authorize them. Offers/compensation remain T3F. No store, transaction,
migration, scoring, frontend or working-demo change is in scope.

### <a id="r4-s1-t3e--acceptance-and-validation"></a>Acceptance and validation

- Extend `tests/test_api_route_extraction.py` with the ledger workflow and
  admin/org cookie tests; establish behavior on assembled routes before the move,
  then run the same assertions against standalone extracted routers.
  This is a pure extraction, with no pre-existing behavioral defect claimed.
- Retain the full OpenAPI/ordered dependency fixture unchanged; run ledger API,
  auth/CSRF/route/ownership guards, shared portal-consent regressions and full
  offline pytest using the project interpreter and isolated fake-provider stores.
- Run migrated scratch HTTP with two organizations, captured admin/org login,
  records/events/coding/reputation, revocation, key lifecycle and graceful restart.
  Reuse the actual org-admin Chrome journey for its existing affected UI contract;
  run UI bindings/syntax checks. Browser actions and HTTP checks are separate.
- Review the final diff for specification compliance, dependency identity/order,
  shared schemas, import cycles and ownership/error preservation; record a separate
  self-review. PostgreSQL/migration concurrency gates do not apply to unchanged
  store/schema/transaction code. Missing required evidence leaves E open.

### <a id="r4-s1-t3e--evidence-and-review"></a>Evidence and review

Extracted fourteen operations and ten DTOs into the 276-line `api/ledger.py`;
the aggregate shrinks from 1,626 to 1,374 lines. `ConsentRevokedResponse` retains
object identity through the aggregate for portal use. The other retained ledger
schemas/errors support portal/verification/interview/compensation handlers.
The original full contract fixture is unchanged: 102 operations, digest
`cbdd461be76f67469f960cc56e6349e90ed99003db24b0acc7c4f45f2817e2b5`.

Pre-move characterization on assembled routers: initial draft **1 failed,
32 passed, 1 warning, 30.32s** (`characterization`); the new test expected a
short consent reason instead of the existing grant/purpose-specific text.
Corrected that assertion; **33 passed, 1 warning, 14.89s**
(`characterization-corrected`). This was a test correction, not a runtime defect
reproducer. The same ledger assertions now run on standalone ledger/auth routers.

Validation uses `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3e.py <tag>
<Python args>`; omitted args run `-m pytest -q --tb=short`. The sanitized runner
clears inherited DEE settings/keys, selects absent config and fake/null providers.
Logs: `.pytest_cache/r4-s1-t3e-<tag>.txt`; local artifacts are not portable setup.

Focused command (`focused`): `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_ledger_api.py tests/test_auth_api.py
tests/test_api_auth_gate.py tests/test_route_table_guard.py
tests/test_org_scope_guard.py tests/test_openapi_contract.py
tests/test_portal_api.py tests/test_portal_sessions.py tests/test_ledger_consent.py
tests/test_ledger_store_records.py tests/test_ledger_store_coding.py
tests/test_ledger_store_reputation.py`.
**149 passed, 1 warning, 39.58s**, exit 0. Starlette/httpx deprecation warning.

Migrated HTTP (`journey-fresh scripts/smoke_r4_s1_t3a.py`): **35/35**, exit 0,
21.85s. Extended the existing captured-login/auth/graceful restart journey with
two employers' ledger consent/records/events/coding/reputation, tenant precedence
over another valid key, wrong-plane/CSRF/ownership refusals, exact persisted
record/coding bodies, revocation after restart, subject-visible allowed/denied
query audits and rotation/offboarding invalidation. Both actual application
lifespans use revision 0029 and dispose/detach SQL. Initial `journey` stopped on
a harness-only `candidate_id` lookup: `/auth/me` deliberately omits that field;
read it from `/portal/me` instead. `journey-corrected` stalled for hours around
restart and then lost valid session behavior; it is failed evidence, not a
successful restart. The fresh scratch run passed without application changes.

Actual Chrome (`browser scripts/check_ui_admin_orgs_browser.py`): **28/28**
org-admin checks plus the shared runner's **1/1**, exit 0, 32.02s. Captured operator
login; actual create/list/filter/page/inspect/reliability/rotate/offboard actions;
one-time key disposal, pending/timeout/503/denial recovery, new-document reload,
backend restart, credential invalidation, session expiry and no console exceptions
or generated keys in logs. Failure injection uses synthetic transport; ordinary
actions use real HTTP. Browser reload verifies changed `performance.timeOrigin`.
Windows browser harness shutdown is forced; graceful lifecycle evidence is HTTP.
Chrome uses existing CDN internet; neither journey calls live model/mail vendors.

Separate same-agent review: HEAD `756caad` plus the aggregate/new ledger source,
standalone tests, existing HTTP extension and reused browser source. Specification
review maps the fourteen operations, auth planes, shared portal response and
full contract to focused/API/browser assertions. Correctness review traced key
rotation/offboarding, cookie-first resolution and CSRF ordering, event ownership,
purpose/org/expiry/revocation checks, audited cross-company reads, deterministic
advisory reputation, errors and restart. No SQL/transaction/service/scorer/UI
implementation changed. All **103** original class/function definitions,
decorators, signatures and bodies remain identical across the two API modules.
Isolated ledger import without aggregate routes passes; eight admin/six org
operations each have exactly one original resolver; composition includes each
APIRoute once. Review command: `review -I .pytest_cache/review_r4_s1_t3e.py`,
exit 0, 3.52s; six code/contract hashes recorded locally. No blocking source
finding remains. This is self-review, not independent review.

Static: project `-m compileall -q` on both API modules, changed tests and HTTP
runner; `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**;
`node --check frontend/api.js`, `node --check frontend/support.js` and tracked
`git -c core.safecrlf=false diff --check` passed.

Full pytest (`full-reviewed`, no extra arguments): **3513 passed, 505 skipped, 127 warnings in 793.57s (0:13:13)**,
exit 0. Starlette/httpx deprecation and SQLite expression-index reflection/
autogenerate warnings; environment/optional skips do not validate omitted cases.
All code checks ran on the reviewed code; only documentation changed afterward.

Final preservation: `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3e.py`
confirms **705 unrelated tracked baseline files unchanged**, including working DB,
and **six reviewed code/contract hashes match**. Handoff/PI/task/evidence local
links and anchors resolve; tracked and new-source whitespace checks pass. Existing
demo health is **200**; it was not restarted. Scratch HTTP/browser processes are
stopped. No deployment, commit or push.

### <a id="r4-s1-t3e--handoff"></a>Handoff

E acceptance and required gates are complete. No application behavior, schema,
SQL transaction, service, scoring or frontend change is claimed. Synthetic
providers, Chrome CDN access, omitted environments and same-agent review retain
the limits above. Parent T3/F13/sprint/PI stay open. Exact next child:
**R4-S1-T3F - Extract employer jobs, compensation (including ledger offers) and
dashboard routes**, not started. Add its contract/evidence inline in the existing
T3 record; reuse the consolidated extraction tests. Stop after E; no T4.


Subsequent completion workflow/final-review/publication follow-up (2026-10-20):
[the existing audit](../CODEBASE_REVIEW_2026-09-07.md#task-completion-publication-2026-10-20)
owns that later evidence; the no-publication statements above describe E/F's
original completion sessions.

## <a id="r4-s1-t3f"></a>R4-S1-T3F - Extract employer jobs, compensation and dashboard routes

Status: done (2026-10-20). Parent: [T3](tasks/R4-S1-T3.md). PI-R4 / R4-S1;
F13. Prerequisite: [T3E](#r4-s1-t3e), done. Only F completed this continuation.

### <a id="r4-s1-t3f--contract"></a>Contract

Move eleven contiguous org-plane operations (job create/list/get/update/match,
ledger offer submission, ad-hoc/job compensation, overview/board/candidate card)
and four request DTOs into `app/api/employer.py`. Keep every handler's explicit
shared `require_org`, names, signatures, error translations and original ordered
composition. Retain the unchanged 102-operation OpenAPI/dependency fixture.
Shared matching, compensation, dashboard and ledger schemas keep their owners;
no aggregate import or new routing/service abstraction is needed.

Preserve tenant-owned jobs and uniform missing/other-tenant 404s, normalized
skills, 200 empty-pool match/board explanations, materialized advisory ranking,
consent-degraded card sections, consent-gated offers, invalid-input 400/422s,
advisory compensation wrappers with null ad-hoc positioning, and cookie-first
principal/CSRF behavior. The Python extraction is a pure move. No store,
SQL/migration/transaction, scorer, live-provider or working-demo changes.
Preserve the existing uncommitted E work and all working data.

Scope refinement from actual Chrome (before UI implementation): existing Roles
bindings still expect `match.matches`, top-level `skill_coverage` and empty-pool
HTTP 422, although the preserved API returns `ranked`, `skill.coverage` and 200
with a reason. This leaves both empty and populated boards blank. Correct only
these API consumers and stale empty-state copy/comments as F acceptance blockers;
add actual browser regressions. No component extraction or other T4 work starts.
Reload restores the authenticated landing screen by existing design; the browser
must reopen compensation after confirming a new document, not invent deep links.

### <a id="r4-s1-t3f--acceptance-and-validation"></a>Acceptance and validation

- Extend `tests/test_api_route_extraction.py`: characterize the assembled routes
  before extraction, then use the standalone employer/auth routers. Exercise all
  eleven operations with two employers, key/cookie auth, CSRF, malformed inputs,
  empty/materialized ranking, compensation and consent grant/revoke behavior.
- Run jobs/comp/dashboard API/service regressions, shared auth/ownership/OpenAPI
  guards and full offline pytest using isolated stores/fakes/project Python.
- Extend the existing migrated auth/ledger HTTP/graceful-restart journey for
  employer workflows. Exercise the actual affected Roles/compensation/board UI
  in Chrome with reload/error recovery and console checks; use the existing
  Chrome/CDP harness. Run bindings/syntax/import/compile/diff checks.
- Separately self-review the final source/test/journey diff, dependency identity,
  shared DTO globals and import cycles. Record all evidence and limits. No PG
  migration/concurrency gate applies to unchanged SQL/schema/transaction code.
  Missing required evidence leaves F awaiting validation; T3/F13/sprint/PI stay open.

### <a id="r4-s1-t3f--evidence-and-review"></a>Evidence and review

The Python move extracts eleven operations/four request DTOs into the 231-line
`api/employer.py`; aggregate `routes.py` shrinks from 1,374 to 1,163 lines.
The full 102-operation contract fixture remains unchanged (digest
`cbdd461be76f67469f960cc56e6349e90ed99003db24b0acc7c4f45f2817e2b5`).
Roles now reads `ranked` and `skill.coverage`, and renders a successful empty pool
from its reason. Genuine 422 errors remain errors; consent refusals stay separate.

Commands use `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3f.py <tag>
<Python args>`; omitted args run `-m pytest -q --tb=short`. Sanitized inherited
DEE config/keys, absent YAML, fake/null/capture providers and isolated stores.
Logs: `.pytest_cache/r4-s1-t3f-<tag>.txt`; local artifacts are not portable setup.

Pre-move (`characterization`): `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_jobs_api.py tests/test_comp_api.py
tests/test_dashboard_api.py`: **26 passed, 1 warning, 18.53s**, exit 0. Same
behavioral assertions now mount only employer/auth routers. Initial post-move
focus (`focused`): **108 passed, 1 warning, 47.32s**, exit 0.

Final focus (`focused-reviewed`): `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_jobs_api.py tests/test_comp_api.py
tests/test_dashboard_api.py tests/test_dashboard_service.py tests/test_comp_service.py
tests/test_api_auth_gate.py tests/test_auth_api.py tests/test_route_table_guard.py
tests/test_org_scope_guard.py tests/test_openapi_contract.py
tests/test_ledger_store_offers.py tests/test_ui_handlers.py`:
**115 passed, 1 warning, 51.54s**, exit 0. Starlette/httpx deprecation warning.

Migrated HTTP (`journey-corrected scripts/smoke_r4_s1_t3a.py`): **44/44**, exit 0,
40.29s. Existing captured-login/auth/ledger journey now includes tenant-owned
jobs, 404s across all job doors, empty/populated match/board, advisory compensation
and null ad-hoc positioning, consented offers/cards and revocation after restart.
Exact job/overview/as-of-match/compensation bodies survive graceful restart.
Two revision-0029 lifespans dispose/detach owned SQL. Initial `journey` refused
to run the new block before `job` was assigned; corrected harness ordering.
The first extraction command failed its Unicode-comment lookup before changing
source; ASCII boundaries fixed that local command. Neither is a runtime defect.

Actual Chrome (`browser-reviewed scripts/check_ui_review_context_browser.py`):
**28/28**, exit 0, 34.85s. Reused captured org login and report review journey;
new empty board, actual ranked candidate ID from HTTP, compensation wrapper,
new-document reload/reopening, injected 503 without stale rows and recovery pass.
Report version/style/ownership/erasure checks remain green; no console exceptions.
Requires existing Chrome/CDN internet; vendors are fake/capture. Browser process
shutdown is forced on Windows; HTTP owns graceful lifecycle evidence.

Pre-fix `browser`/`browser-corrected` failed empty/populated Roles assertions,
reproducing existing API/UI drift. Draft harness also used a broad parent-div
click and incorrectly expected reload to restore the comp screen. Exact role-row
selection and reopening after an authenticated landing correct those harness
expectations. `browser-ui-fix` then passed 28/28; final reviewed rerun above adds
an actual ranked-ID assertion. No browser failure is counted as successful proof.

Offline UI regressions extend `scripts/test_ui_evaluate.js`'s existing shared
component/API harness: ranked/nested coverage, zero coverage, empty/error/consent
separation and recovery. `node --test scripts/test_ui_evaluate.js`: **24 passed**.
The same new tests loaded against the original `HEAD` frontend via the isolated
local loader (`node --test .pytest_cache/check_ui_before_r4_s1_t3f.js`) produce
**2 failed, 22 passed**: missing ranked rows and successful empty state. No working
frontend file was overwritten for that expected pre-fix reproducer.
Initial bindings failed seven shortlist mappings because its fixture also used
the retired `matches` shape. Updated that fixture to the actual response shape;
`node scripts/check_ui_bindings.js`: **589 bindings / 18 states**, passed.
JS syntax (`frontend/api.js`, `frontend/support.js`, changed Node tests), project
`-m compileall -q` on changed Python and tracked diff whitespace passed.

Separate same-agent review: HEAD `756caad` plus preserved uncommitted E work and
the F aggregate/employer, tests, frontend consumer and existing journey changes.
Specification review maps eleven unchanged operations, four DTOs and bounded UI
scope refinement to API/browser/handler assertions. Correctness review traced
tenant/CSRF precedence, job ownership/404s, offer grants/revocation, card read
degradation/audits, advisory ranking/compensation, shared schemas/imports, empty
versus failed reads, reload and resource shutdown. All **79** pre-F Python
class/function definitions (including decorators/signatures/bodies) are unchanged
across the two modules. Isolated employer import succeeds without aggregate
routes; eleven explicit original org resolvers compose once. Review command:
`review-final -I .pytest_cache/review_r4_s1_t3f.py`, exit 0, 6.17s; ten reviewed
code/contract hashes recorded. No SQL/transaction/service/scorer changes.

Review findings resolved: **medium**, `Veritas.dc.html` Roles projection expected
obsolete API fields/status, leaving real empty/populated boards blank; corrected
those bindings/copy, with pre-fix Chrome and passing browser/offline regressions.
**Low**, `check_ui_bindings.js`'s matching obsolete fixture concealed that drift;
actual API-shaped data restores non-vacuous shortlist coverage. Harness ordering,
row selection and reload assumptions corrected as above. No blocking finding
remains; this is self-review, not independent review or empirical quality proof.

Full pytest (`full-reviewed`, no extra arguments): **3515 passed, 505 skipped, 127 warnings in 826.93s (0:13:46)**,
exit 0. Starlette/httpx deprecation and SQLite expression-index reflection/
autogenerate warnings; environment/optional skips do not prove omitted cases.
Checks ran on the reviewed code; only documentation changed afterward.

Final preservation: `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3f.py`
confirms **702 unrelated baseline files unchanged**, including the working DB
and prior uncommitted `api/ledger.py`, plus **ten reviewed code/contract hashes**.
Handoff/PI/task/evidence links and anchors and tracked/new-source whitespace pass.
Existing demo health is **200**; no restart. Scratch HTTP/browser processes have
stopped. No deployment, commit or push; E work is preserved.

### <a id="r4-s1-t3f--handoff"></a>Handoff

F acceptance and required gates are complete, including the explicitly recorded
Roles binding correction. Python HTTP behavior, SQL/services/scorers are unchanged.
No live-provider, PG/concurrency, independent-review or empirical-quality claim.
T3/F13/sprint/PI remain open. Exact next child: **R4-S1-T3G - Extract feature
materialization and talent search routes**, not started. Add its contract/evidence
inline in the existing T3 record and reuse the consolidated route tests. Stop
after F; no G or T4 implementation this continuation.

Subsequent completion workflow/final-review/publication follow-up (2026-10-20):
[the existing audit](../CODEBASE_REVIEW_2026-09-07.md#task-completion-publication-2026-10-20)
owns that later evidence; the no-publication statements above describe E/F's
original completion sessions.

## <a id="r4-s1-t3g"></a>R4-S1-T3G - Extract feature materialization and talent search routes

Status: done and published (2026-10-20); remote commit verified.
Parent: [T3](tasks/R4-S1-T3.md). Prerequisite: [F](#r4-s1-t3f), done.
Only G is authorized for this continuation; T3/F13/sprint/PI remain open.

### <a id="r4-s1-t3g--contract"></a>Contract

Move `POST /talent/search`, `POST /features/materialize` and their three DTOs
into `app/api/features.py`, using the existing shared admin dependency and
service resolver. Compose the existing APIRoutes at the original admin position.
Keep handler names, signatures, bodies, ordered dependencies, all 102 operations
and the full OpenAPI fixture unchanged. No service/store/schema/SQL, scorer,
frontend, provider or running-demo change. Keep shared feature/ranking schemas
with their current owners; preserve aggregate aliases only where callers need them.

Acceptance preserves key/cookie admin-only access, cookie-first principal and
CSRF handling, empty advisory search, known/unknown feature and filter errors,
limits, default/explicit view and historical cuts, partial materialization and
unknown/erased subject skips. Current platform ledger_read consent must mask
historical values before filtering/scoring without altering stored cuts or
first-party values; consent storage failure must refuse the response.

### <a id="r4-s1-t3g--validation"></a>Required validation

- Characterize both operations before the move in the existing
  `tests/test_api_route_extraction.py`, then run the same behavior through the
  standalone feature/auth routers. Include two subjects, scoped consent,
  revocation, erasure, cookie/key/CSRF boundaries and input errors.
- Run focused route/materialization/search/consent/ownership/auth regressions and
  the complete offline pytest suite with isolated stores and project Python.
  This is a pure refactor, so passing pre-move characterization is expected;
  no existing functional defect or expected red regression is invented.
- Extend the existing migrated auth/ledger HTTP/graceful-restart journey for
  actual search/materialization, historical persistence and consent revocation.
  Reuse the actual Roles Chrome journey, which consumes materialized features;
  no direct search/materialization screen exists. Include reload/error recovery
  and console checks. Run UI bindings, Python import/compile and diff checks.
- Record an implementation self-review of the diff, original AST/DTO/dependency
  identity and independent module imports. No PG migration/concurrency gate
  applies to unchanged stores/transactions/schema. After completion records,
  perform a distinct final self-review, commit/push scoped changes and verify
  the remote SHA under the user's standing instruction.

### <a id="r4-s1-t3g--evidence-and-review"></a>Evidence and review

The pure move places two operations/three DTOs in the 175-line `api/features.py`;
aggregate `routes.py` is 1,009 lines (formerly 1,163). Their unchanged APIRoutes
compose in the original position with exactly one shared admin resolver each.
Caller search found no aggregate DTO/helper consumers requiring aliases.
The complete 102-operation OpenAPI/ordered dependency fixture remains unchanged
(`cbdd461be76f67469f960cc56e6349e90ed99003db24b0acc7c4f45f2817e2b5`).

Commands use `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3g.py <tag>
<Python args>`; omitted arguments run `-m pytest -q --tb=short`. The local runner
clears inherited DEE settings/keys, points at absent YAML and uses null/fake/capture
providers and isolated stores. Logs: `.pytest_cache/r4-s1-t3g-<tag>.txt`. These
ignored artifacts are evidence aids, not portable setup guarantees.

Pre-move `characterization`: `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_features_materialize_api.py
tests/test_talent_search_api.py`: **34 passed, 1 warning, 18.81s**, exit 0.
Three new behavioral tests first ran through the assembled application and now
mount only feature/auth routers. No behavioral defect is claimed for this refactor.

Post-move `focused`: `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_features_materialize_api.py
tests/test_talent_search_api.py tests/test_features_materialize.py
tests/test_features_current_consent.py tests/test_feature_serving_consent.py
tests/test_ledger_store_materialize_consent.py tests/test_ranking.py
tests/test_ranking_filters.py tests/test_ranking_score.py tests/test_ranking_config.py
tests/test_api_auth_gate.py tests/test_auth_api.py tests/test_route_table_guard.py
tests/test_org_scope_guard.py tests/test_openapi_contract.py`:
**177 passed, 101 skipped, 1 warning, 141.13s**, exit 0. Environment/optional skips
do not prove omitted cases; Starlette/httpx deprecation warning.

After the review's non-vacuity assertion, `focused-reviewed`: `-m pytest -q
--tb=short tests/test_api_route_extraction.py -k feature_`: **3 passed,
11 deselected, 1 warning, 2.58s**, exit 0. Full pytest ran on that final code.

Migrated HTTP (`journey-corrected scripts/smoke_r4_s1_t3a.py`): **51/51**, exit 0,
37.14s. Two revision-0029 lifespans, captured admin/org/candidate cookies,
wrong-plane refusals, admin cookie plus valid key CSRF refusal, partial refresh
with unknown-ID skips, malformed-view/feature/ranking errors, consented advisory
historical contributions, exact search body across graceful restart, then
revocation masking before filtering while first-party values remain available.
Existing ledger/employer ownership/consent/shutdown checks remain green.
Initial `journey`: **50/51**, exit 1; its bare portal subject had no resume and
therefore no first-party skill count to preserve. Added a synthetic SQL resume
to that exact verified subject (identity asserted). This corrects the fixture;
no production logic changed to satisfy a test assumption.

Actual Chrome (`browser scripts/check_ui_review_context_browser.py`): **28/28**,
exit 0, 40.26s. The existing Roles journey consumes the new materialization
composition and renders actual ranked candidate IDs, with successful empty state,
new-document reload, injected 503/recovery and no console exceptions. Existing
report review/ownership/erasure checks remain green. There is no direct feature
or talent-search UI. Chrome/CDN internet is required; external providers are
fake/capture. Browser cleanup is forced on Windows; HTTP proves graceful shutdown.

Static checks: `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**,
passed. `node --check frontend/api.js`, `node --check frontend/support.js`, project
`-m compileall -q` for the two API files, extended route tests and HTTP script,
and `git diff --check` pass. No frontend source change.

Implementation self-review: HEAD `ea2ee86` plus aggregate/features, consolidated
route tests and extended existing HTTP journey. Specification review maps both
unchanged operations and three DTOs to full-contract and behavioral checks.
Correctness review traces current-consent masking before filters/normalization,
historical/partial refresh reads, unknown/erased subject skips, consent read
failure, auth-plane isolation and cookie/CSRF precedence. All **64** original
aggregate class/function definitions (decorators/signatures/bodies included)
are AST-identical across aggregate/features. `review-corrected -I
.pytest_cache/review_r4_s1_t3g.py`: exit 0, 5.22s; isolated import needs no aggregate,
shared dependency/service identity is retained and five code/contract hashes
are recorded. No schema/store/SQL/scorer/provider changes or import cycle.
Low review finding: make the initial consented ranking assertion non-vacuous
with both exact candidate IDs before checking coverage; resolved in the existing
test. HTTP fixture gap resolved as above. No blocking implementation finding
remains; this is self-review, not independent review or measured ranking quality.

Preservation check (`.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3g.py`):
**707 unrelated tracked files**, including working `data/veritas.db`, and the
five reviewed code/contract hashes unchanged. After completion consolidation,
all **157 local links/anchors in five scoped Markdown files**, source whitespace
and `git diff --check` pass. Scratch HTTP/Chrome processes exited.
The existing demo health read refused its connection and no listener was found
on port 8000. No demo was started/restarted; no deployment or working migration.
No live-provider, PG concurrency/migration, independent-review or empirical
quality claim. Current consent checks remain snapshots, not delivery locks.

Full pytest (`full-reviewed`, no extra runner arguments): **3518 passed, 505 skipped, 127 warnings in 833.54s (0:13:53)**,
exit 0. Starlette/httpx deprecation and SQLite expression-index reflection/
autogenerate warnings remain; skipped environment/optional cases are not proof
of those cases. Full pytest ran on the reviewed code; only documentation changed
afterward. Acceptance and required runtime/static gates are complete.

### <a id="r4-s1-t3g--completion-review-and-publication"></a>Completion review and publication

After full pytest and the completion/evidence/handoff updates, a distinct final
same-agent self-review examined HEAD `ea2ee86` plus the exact nine staged files:
`api/routes.py`, new `api/features.py`, the existing route-test/HTTP-journey
modules, and `PROGRESS`, `ROADMAP`, `PI-R4`, `EVIDENCE-R4`, active T3 records.
Specification review confirmed G's two-operation/three-DTO scope, required
evidence, unchanged 102-operation contract and H-only next pointer. Correctness
review rechecked dependency order/identity, current-consent historical serving,
erasure/refusals, fixture realism, resource cleanup and retained limitations.
`completion-review -I .pytest_cache/review_r4_s1_t3g.py` again confirmed all 64
original definitions, standalone import and single shared admin gates. Final
code/contract hashes match the validated state. Scoped staging contains no
working DB, secrets, generated artifacts or unrelated changes. No blocking
finding remains. This later review is distinct from implementation self-review;
no independent review is claimed. Documentation tense/pending-check wording was
updated to match completed evidence; only documentation changed after full pytest.

The reviewed nine-file task scope is committed as **`dc4b871`** on local `main`.
Publication to configured tracking branch `origin/main` was initially **blocked
by GitHub authentication/account selection**. Initial `git push` stalled in its
owned Credential Manager process tree; after verifying the process identity,
that attempt was terminated.
Retry with `GIT_TERMINAL_PROMPT=0` and `GCM_INTERACTIVE=never` exits 1:
`Cannot prompt because user interactivity has been disabled` / `could not read
Username for 'https://github.com': terminal prompts disabled`. GitHub CLI is
not installed. Read-only `git ls-remote origin refs/heads/main` succeeded and
confirmed remote **`ea2ee86a7a1eb3b192e40a29a400c3b035df83bb`**, not the task commit,
at that point. Those attempts did not publish the task.

The user was asked to sign in while the blocker record was prepared. Local
Credential Manager help confirms `git credential-manager github login --device
--no-ui` as an available interactive-terminal recovery command. The recovery plan
was to retry `git push` after sign-in, then compare `git rev-parse HEAD` with
`git ls-remote origin refs/heads/main`. Standing publication authorization was
sufficient; authentication/account selection was needed. The task stayed local
pending publication, with H unstarted and no deployment.

Publication-blocker documentation follow-up: separately self-reviewed the five
changed handoff/evidence/status/roadmap files after the failed push. Their status
then distinguished local completion from remote publication and directed the next
session to finish publication first. No blocking documentation finding remained.
Final local links/anchors: **158**, all valid; whitespace, **707** unrelated-file
hashes and all five reviewed code/contract hashes still pass. This prose-only
follow-up does not require another application test run or change validated code.

Publication resumed after the user's explicit sign-in confirmation. The first
noninteractive retry still refused an account prompt; `git credential-manager
github list` showed two accounts. The repository owner has an authenticated
account, so per-command selection avoided that prompt without changing Git
configuration: `git -c credential.https://github.com.username=RevanParimi push`
(with `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0 and advanced
remote main from `ea2ee86` to **`41d0342`**. The task commit **`dc4b871`** is included.
Read-only remote verification compared `git rev-parse HEAD` with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`41d0342986b4a0d29f61d3ae9c498d8c47f69346`**. Authentication/publication
is resolved. No deployment or H implementation occurred.

This five-file documentation-only confirmation updates status/next pointers and
preserves the failed-attempt history. No application code changed after the
recorded full pytest/API/Chrome validation. Separate final same-agent self-review
against `41d0342` checked the five-file diff, verified-publication evidence,
consistent completion/next pointers and retained limits; no blocking finding
remains. Local links/anchors, whitespace and reviewed/unrelated-file preservation
checks pass. No application tests were rerun for prose-only changes. The session's
final response reports the resulting verified remote confirmation commit.

### <a id="r4-s1-t3g--handoff"></a>Handoff

Only G completed in this continuation. T3/F13/sprint/PI stay open. Exact next
child: **R4-S1-T3H - Extract candidate portal, consent/access and data-principal
request routes**, not started. Add its bounded contract/evidence inline in the
existing T3 record and reuse consolidated route tests. T4 has not started.
No next-backlog implementation or deployment during publication.

## <a id="r4-s1-t3h"></a>R4-S1-T3H - Extract candidate portal and data-principal request routes

Status: done and published (2026-10-20). Parent: [T3](tasks/R4-S1-T3.md).
Prerequisite: [G](#r4-s1-t3g), done/published.
Only H is in scope for this continuation; T3/F13/sprint/PI remain open.

### <a id="r4-s1-t3h--contract"></a>Contract

Extract nine candidate portal operations (access view/log, consent list/grant/
revoke, corrections, grievances, request list and self-erasure), two operator
request list/resolve operations and their four DTOs into `app/api/portal.py`.
Keep explicit shared candidate resolvers and one shared admin gate per operator
route. Compose APIRoutes at their original candidate/admin positions without
changing any handler body/decorator/signature or the full 102-operation ordered
auth/OpenAPI fixture. Keep shared erasure/revocation DTOs with candidates/ledger;
public grievance contact stays in the aggregate for M. No service/store/SQL,
migration, scoring, provider, frontend or working-demo changes are implied.

Preserve first-party ownership from credentials, mixed cookie/key precedence and
CSRF; uniform absent/foreign consent 404s; allowed/denied access audit and current
consent; reviewed corrections with default `apply=false`, explicit name-only
application and unchanged extraction evidence; private human/machine resolution
provenance; queue limits/status validation and 400/404/409/422/429 translations
where applicable; request rate budgets, and erasure of own data/credentials while
another subject remains accessible. Retain concurrent-erasure refusals.

### <a id="r4-s1-t3h--validation"></a>Required validation

- Extend existing `tests/test_api_route_extraction.py` before the move to
  characterize two-subject portal/rights/erasure and cookie/admin workflows;
  rerun the same assertions with standalone portal/auth routers. Pure refactoring
  expects passing characterization, not an invented functional red regression.
- Run focused portal/rights/auth/ownership/full-contract pytest and full offline
  pytest with project Python, isolated stores and fake/capture providers.
- Extend the existing migrated auth/ledger HTTP/graceful-restart journey for
  candidate requests, operator review and erasure. Extend the existing evaluation
  Chrome journey's candidate session for rendered portal, consent revocation,
  allowed/denied access log, reload, injected read failure/recovery and erasure.
  Rights list/resolve have no existing UI; real HTTP owns those operations.
- Run bindings, relevant JS syntax, Python compile/import and diff checks.
  Review definition/DTO/dependency identity, import cycles and preservation.
  No PG migration/concurrency gate applies to unchanged stores/transactions.
- Record implementation self-review and a distinct final review after completion
  records; commit/push reviewed scoped changes and verify the tracking remote.
  Use per-command authenticated repository-owner selection for GitHub's two
  Credential Manager accounts (G publication evidence). Do not start I or T4.

### <a id="r4-s1-t3h--evidence-and-review"></a>Evidence and review

The pure extraction moves eleven operations/four DTOs into the 266-line
`api/portal.py`; aggregate `routes.py` shrinks from 1,009 to 772 lines. Candidate
and operator routes compose at their original positions, preserving one shared
candidate/admin resolver per operation. Shared response DTO identity stays with
`api/candidates.py` and `api/ledger.py`; caller search found no moved aggregate
DTO/handler consumers requiring aliases. Public grievance contact remains for M.
The full 102-operation OpenAPI/ordered dependency fixture is unchanged (digest
`cbdd461be76f67469f960cc56e6349e90ed99003db24b0acc7c4f45f2817e2b5`).

Commands use `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3h.py <tag>
<Python args>`; omitted arguments run `-m pytest -q --tb=short`. The local runner
clears inherited DEE config/keys, points to absent YAML and uses isolated stores
and fake/null/capture providers. Logs: `.pytest_cache/r4-s1-t3h-<tag>.txt`; ignored
local artifacts are not portable setup guarantees.

Pre-move `characterization`: `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_portal_api.py tests/test_rights_api.py
tests/test_rights_admin_api.py`: **47 passed, 1 warning, 15.86s**, exit 0.
Three new behavioral tests first mounted the aggregate, then switched to just
portal/auth routers. Pure refactoring expects passing characterization; no
functional defect or expected-red result is claimed.

Post-move `focused`: `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_portal_api.py tests/test_portal_sessions.py
tests/test_portal_service.py tests/test_portal_identity.py tests/test_rights_api.py
tests/test_rights_admin_api.py tests/test_rights_service.py tests/test_rights_store.py
tests/test_api_auth_gate.py tests/test_auth_api.py tests/test_route_table_guard.py
tests/test_org_scope_guard.py tests/test_openapi_contract.py`:
**171 passed, 1 warning, 39.50s**, exit 0 (Starlette/httpx deprecation).
New standalone workflows cover exact two-subject ownership/credential semantics,
absent/foreign consent 404 equality, allowed/refused audit, correction review and
explicit application without extraction rewrites, machine/human provenance,
queue bounds/status, 404/409/422/429 responses, budget charging before validation,
cookie/foreign-key precedence, CSRF and erasure with a surviving second subject.
Controlled service erasure exceptions prove 404 translations; they are not new
database concurrency evidence.

Migrated HTTP (`journey scripts/smoke_r4_s1_t3a.py`): **58/58**, exit 0, 37.59s.
The captured admin/candidate/org composition verifies owned portal requests,
cookie plus foreign-key precedence and CSRF refusal, operator queue bounds/auth,
persisted request body/grant ID over graceful restart, named reviewed application,
repeat-decision 409, revocation, request/credential erasure and another subject's
survival. Prior ledger/employer/feature contracts remain green. Two revision-0029
lifespans dispose/detach owned SQL; no working migration or demo restart.

Actual Chrome (`browser scripts/check_ui_evaluate_browser.py`): **38/38**, plus
**1/1** startup/UI-host harness, exit 0, 38.64s. The existing real candidate
session now grants consent through browser API plumbing, renders/revokes it
through the actual Consents screen, sees allowed/refused employer accesses with
actor name, reloads a new document preserving revocation, renders an injected
503 on Overview and recovers by navigation, then performs visible confirmed
erasure, loses its credential/session and preserves a second subject. No console
exceptions. Existing evaluation/report/outcome/OTP journeys stay green. Rights
submission/review have no current UI; HTTP owns those operations. Chrome needs
existing CDN internet; providers/mail are fake/capture, not live validation.
Browser cleanup is forced on Windows; HTTP owns graceful lifecycle evidence.

Static checks: `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**,
passed. `node --check frontend/api.js`, `node --check frontend/support.js`, project
`-m compileall -q` for aggregate/portal, extended route tests and both existing
journeys, and `git diff --check` passed. No frontend source change.

Implementation self-review: HEAD `fd668e9` plus aggregate/portal, consolidated
route tests and the two extended existing journeys. Specification review maps
all eleven operations/four DTOs to full-contract, standalone, HTTP and actual
browser assertions. Correctness review traces subject isolation, shared response/
dependency identities, CSRF order, uniform foreign/missing refusals, current
consent/audit, reviewed identity-only changes without rewriting extraction,
rate/queue bounds, resolution provenance/error ordering, erasure and lifecycle.
All **59** original aggregate class/function definitions, including decorators,
signatures and bodies, are AST-identical across aggregate/portal. `review -I
.pytest_cache/review_r4_s1_t3h.py`: exit 0, 5.78s; isolated module import succeeds
without aggregate, both shared response identities and single appropriate gates
pass; six code/contract hashes recorded. No blocking implementation finding
remains. This is self-review, not independent review or scoring-quality proof.

Preservation (`.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3h.py`):
**707 unrelated tracked files**, working DB and **six reviewed code/contract
hashes** unchanged; **162 local links/anchors across five scoped Markdown files**
and whitespace pass after completion consolidation. No SQL/
transaction/schema/provider changes, so no PG migration/concurrency gate applies.
Existing final-read snapshot/concurrent-erasure and advisory limitations remain.

Full pytest (`full-reviewed`, no extra runner arguments): **3521 passed, 505 skipped, 127 warnings in 742.32s (0:12:22)**,
exit 0. Starlette/httpx deprecation and SQLite expression-index reflection/
autogenerate warnings remain; environment/optional skips do not prove omitted
cases. The full suite ran on the reviewed code, with only documentation changed
afterward. Acceptance and required runtime/static gates are complete.

### <a id="r4-s1-t3h--completion-review-and-publication"></a>Completion review and publication

After full pytest and completion/evidence/handoff updates, a distinct final
same-agent self-review examined HEAD `fd668e9` plus the exact ten staged files:
aggregate/new portal, consolidated route tests, existing migrated HTTP and
evaluation Chrome journeys, and the five handoff/PI/task/evidence/roadmap records.
Specification review confirmed eleven operations/four DTOs, all required
validation, unchanged ordered API/auth contract and the I-only next pointer.
Correctness review rechecked subject/tenant and auth-plane boundaries, cookie/
CSRF precedence, shared DTO/dependency identity, reviewed correction/provenance,
rate/error order, erasure and audit visibility, test fixtures and lifecycle.
`completion-review -I .pytest_cache/review_r4_s1_t3h.py`: exit 0, 3.58s, reconfirms
all 59 original definitions, independent import, both shared responses and one
appropriate gate per operation. Six code/contract hashes match the validated
state. No blocking finding remains; this later self-review is separate from
implementation review, and no independent review is claimed. Only documentation
changed after full pytest. Scoped staging excludes working data, secrets,
generated artifacts and unrelated files. Final scoped whitespace/link and
preservation checks pass. Commit/push uses configured tracking branch
`origin/main` and per-command authenticated account selection as recorded in G.
Scoped task commit **`4b516f3`** was created and `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`fd668e9` to `4b516f3`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`4b516f3960e9b43dbde39c4d414f270230ba727f`**. Working tree was clean.
No I work or deployment occurred.

The following two-file documentation-only confirmation records that verified
publication in the handoff and this existing evidence section. A separate final
self-review against `4b516f3` checked the exact documentation diff, successful
remote evidence, unchanged task limits and I-only next pointer; no blocking
finding remains. Scoped links/whitespace and preservation checks pass. Application
code is unchanged from the full pytest/API/Chrome validated state, so no application
tests were rerun for prose. The final response reports the verified remote SHA
after this confirmation's commit/push.

### <a id="r4-s1-t3h--handoff"></a>Handoff

Only H completed in this continuation. T3/F13/sprint/PI remain open. Exact next
child: **R4-S1-T3I - Extract verification, documents and employer assurance
routes**, not started. Add I's bounded contract/evidence inline in the existing
T3 record and reuse consolidated route tests. Trace verification/OTP/document
schemas and manual-review/assurance consumers before refining the boundary.
T4 has not started. No next backlog task or deployment during publication.

## <a id="r4-s1-t3i"></a>R4-S1-T3I - Verification, documents and employer assurance

Status: done and published (2026-10-21). Parent: [T3](tasks/R4-S1-T3.md).
Prerequisite: [H](#r4-s1-t3h), done/published.
Only I is in scope; T3/F13/sprint/PI remain open.

### <a id="r4-s1-t3i--contract"></a>Contract

Extract seven operations and seven request/response DTOs into `api/verification.py`:
candidate start/confirm/list verification and document submission, employer
assurance/claim reads and operator manual review. Compose separate candidate,
org and admin routers at their original positions with identical handler bodies,
decorators, signatures and shared auth dependencies. Preserve the complete
102-operation ordered auth/OpenAPI fixture; no service/store/SQL, migration,
scorer/provider/frontend or working-demo changes are included.

Acceptance: standalone routers preserve two-subject OTP ownership and one-use
confirmation, unavailable/failed delivery and debug-echo policy, first-party
document ownership, parse/size/label bounds, separate identity/claim ladders,
manual-review auth and cookie/CSRF precedence. Two organizations retain current
consent, allowed/denied audit and redacted assurance/claim summaries; revocation
and erasure refuse access without affecting another subject. Keep unsupported
method and 400/403/404/422/429/503 translations.

Validation: extend consolidated route tests before extraction for passing
characterization, then mount only verification/auth routers. Pure extraction
does not imply a functional defect or expected-red reproduction. Run focused
verification/auth/contract tests and full offline pytest with project Python;
extend the existing migrated HTTP/graceful restart journey for documents, manual
review, employer reads, revocation and erasure. Run actual verification Chrome
for contact/assurance, reload and failure recovery, plus bindings, JS syntax,
compile/import, AST identity and preservation/diff checks. Unchanged SQL does
not require new PostgreSQL concurrency/migration evidence. Record implementation
self-review and a distinct completion review before scoped commit/push and remote
verification. Complete only I; next is J, interviews/assessment summaries.

### <a id="r4-s1-t3i--evidence-and-review"></a>Evidence and review

Pure extraction moves seven operations/seven DTOs into the 256-line
`api/verification.py`; aggregate `routes.py` shrinks from 772 to 547 lines.
The complete 102-operation ordered auth/OpenAPI fixture is unchanged (digest
`cbdd461be76f67469f960cc56e6349e90ed99003db24b0acc7c4f45f2817e2b5`).
Caller search found no moved handler/DTO imports requiring compatibility aliases.
Candidate/org/admin routers compose at their original positions and keep one
appropriate shared principal/CSRF gate each. No service/store/SQL/scorer/provider
or frontend behavior changes.

Commands use `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3i.py <tag>
<Python args>`; omitted arguments run `-m pytest -q --tb=short`. This local runner
clears inherited DEE config/keys, points at absent YAML and uses fake/null/capture
providers and isolated stores. Logs are `.pytest_cache/r4-s1-t3i-<tag>.txt`;
ignored artifacts are not portable setup guarantees.

Pre-move `characterization`: `-m pytest -q --tb=short
tests/test_api_route_extraction.py -k 'verification or full_openapi'`:
**4 passed, 16 deselected, 1 warning, 3.46s**, exit 0. The three new workflows
first mounted the aggregate and then switched to verification/auth routers only.
Initial test setup assumptions were corrected: the reused candidate has no phone,
and a cooldown refusal may retain an additional pending attempt. These were
characterization adjustments, not application defects or expected-red evidence.

Post-move `focused`: `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_verification_api.py
tests/test_verification_org_api.py tests/test_verification_claim_api.py
tests/test_verification_service.py tests/test_verification_claim_service.py
tests/test_verification_delivery.py tests/test_verification_consent.py
tests/test_verification_erasure.py tests/test_verification_documents_parse.py
tests/test_verification_documents_letter.py tests/test_verification_documents_payslip.py
tests/test_api_auth_gate.py tests/test_auth_api.py tests/test_route_table_guard.py
tests/test_org_scope_guard.py tests/test_openapi_contract.py`:
**209 passed, 1 warning, 32.55s**, exit 0 (Starlette/httpx deprecation).
Standalone workflows prove owned single-use OTP, indistinguishable foreign/absent
404s, method refusals/cooldown, separate identity/claim ladders, document parse/
label bounds and no raw document echo, operator-only review, two-employer consent,
redacted summaries and allowed/denied audit, revocation/erasure, and mixed cookie/
foreign-key precedence and CSRF on start/confirm/document/manual writes. Existing
delivery/claim tests preserve production debug policy, unavailable/failed dispatch,
size bounds, consent and erasure. Fakes prove mechanics, not live delivery or
document-forensics accuracy.

Migrated HTTP (`journey scripts/smoke_r4_s1_t3a.py`): **70/70**, exit 0, 16.54s.
The existing captured-login/auth/ledger journey adds document parse refusal and
owned intake, manual-review auth/CSRF, distinct ladders, scoped employer summaries
and redaction, exact saved attempts/summaries across graceful restart, revocation,
allowed/denied audit and erased-subject refusals with another subject surviving.
Both revision-0029 lifespans dispose/detach owned SQL. No working migration or
demo restart.

Contact HTTP (`contact scripts/smoke_r3_s1_t2.py`): **20/20**, exit 0, 23.72s.
Captured delivery covers wrong contact, phone unavailability, cooldown, provider
failure/rollback/retry, foreign confirmation, one-use/expired/exhausted challenges,
no plaintext echo, persisted contact assurance after restart and erasure/privacy.
Its Windows process cleanup is forced; the separate journey owns graceful
lifecycle evidence.

Actual Chrome (`browser scripts/check_ui_verification_browser.py`): **19/19**,
plus **1/1** startup/UI-host harness, exit 0, 23.56s. Real candidate signup,
contact/assurance rendering, empty/contact/provider/CSRF failures and recovery,
duplicate clicks, captured code, incorrect/foreign/expired/exhausted confirmation,
new-document reload, held/expired assurance, logout/session loss and no console
exceptions all pass. App logs omit addresses/codes. Chrome needs existing CDN
internet; delivery is synthetic/capture. Documents, manual review and employer
summaries have no dedicated current UI; HTTP owns their runtime evidence.

Static checks: `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**,
passed. `node --check frontend/api.js`, `node --check frontend/support.js`, project
`-m compileall -q src/app/api/routes.py src/app/api/verification.py
tests/test_api_route_extraction.py scripts/smoke_r4_s1_t3a.py`, and
`git diff --check` pass. No frontend source change.

Implementation self-review: HEAD `5b3c6c4` plus aggregate/new verification,
consolidated route tests and the existing extended migrated HTTP journey.
Specification review maps all seven operations/DTOs to full-contract, standalone,
HTTP and actual Chrome checks. Correctness review traces shared schema/dependency
identity, auth-plane order, candidate/tenant ownership, cookie precedence/CSRF,
destination binding, delivery/confirmation errors, current consent/audit,
document privacy, distinct ladders, operator review, erasure and lifecycle.
`review -I .pytest_cache/review_r4_s1_t3i.py`: exit 0, 2.21s. All **44** original
aggregate class/function definitions, including decorators, signatures and bodies,
are AST-identical across aggregate/verification. Independent module import, three
shared domain schemas and exactly one appropriate gate per operation pass; five
code/contract hashes recorded. No blocking finding remains. Same-agent self-review
is not independent review or an accuracy claim. No SQL/transaction/migration
change, so no new PostgreSQL concurrency/migration gate applies.

Full pytest (`full-reviewed`, no extra runner arguments): **3524 passed, 505 skipped, 127 warnings in 867.60s (0:14:27)**,
exit 0. Existing Starlette/httpx deprecation and SQLite expression-index reflection/
autogenerate warnings remain; optional/environment skips do not prove omitted
cases. It ran on the reviewed code; only documentation changed afterward.

Preservation (`.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3i.py`):
709 unrelated tracked files, working DB and five reviewed code/contract hashes
are unchanged. Scoped Markdown links/anchors and tracked/staged whitespace pass.
Existing final-read snapshot, concurrent-erasure and advisory limitations remain.
Acceptance and required validation are complete.

### <a id="r4-s1-t3i--completion-review-and-publication"></a>Completion review and publication

After required checks and completion/evidence/PI/handoff updates, a distinct final
same-agent self-review examined HEAD `5b3c6c4` plus the exact nine staged files:
aggregate/new verification, consolidated route tests, the existing extended
migrated HTTP journey and five handoff/roadmap/PI/task/evidence records.
Specification review confirms all seven operations/seven DTOs, unchanged full
API/auth contract, completed validation and the J-only next pointer. Correctness
review rechecks principal/schema identity and gate order, first-party ownership,
cookie/CSRF precedence, destination binding/one-use confirmation, delivery/error
policy, document privacy and bounds, distinct advisory ladders, operator review,
current scoped consent/audit, revocation/erasure and graceful lifecycle.
`completion-review -I .pytest_cache/review_r4_s1_t3i.py`: exit 0, 1.82s; all 44
original definitions, independent import, three shared schemas, single appropriate
gates and five reviewed hashes match. No blocking finding remains. This later
self-review is separate from implementation review; no independent review is
claimed. Only documentation changed after full pytest. Final scoped preservation,
163 local links/anchors across five Markdown files and staged whitespace pass.
Staging excludes secrets, working data, generated artifacts and unrelated files.
Configured tracking branch is `origin/main`; its remote still matched the starting
HEAD before publication. Commit/push will use per-command account selection from
G's existing two-account Credential Manager evidence. Scoped task commit
**`bd4e556`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`5b3c6c4` to `bd4e556`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`bd4e556cd4f5d8ea9d301c99cb0421e18c9618ab`**. Working tree was clean.
No J work, demo restart or deployment occurred.

This two-file documentation-only confirmation records that verified
publication in the handoff and this existing evidence section. Its separate final
self-review against `bd4e556` checks the exact prose diff, actual remote evidence,
unchanged task limits and J-only next pointer; no blocking finding remains.
Scoped link/whitespace and preservation checks pass. Application code remains at
the full pytest/API/Chrome validated state, so no tests were rerun for prose.
The final response reports the verified remote SHA after this confirmation's
commit/push.

### <a id="r4-s1-t3i--handoff"></a>Handoff

Only I completed in this continuation. T3/F13/sprint/PI remain open. Exact next:
**R4-S1-T3J - Extract candidate interviews and employer assessment summaries**,
not started. Add J's bounded contract/evidence inline in the existing T3 record;
reuse consolidated route tests and existing interview HTTP/Chrome journeys.
Preserve content-only advisory scoring, transcript privacy, ownership/current
consent, scorer-version fields, ASR bounds/fallbacks and conflict/error contracts.
T4 has not started. No next task or deployment during publication.

## <a id="r4-s1-t3j"></a>R4-S1-T3J - Candidate interviews and employer assessment summaries

Status: done and published (2026-10-22). Parent: [T3](tasks/R4-S1-T3.md).
Prerequisite: [I](#r4-s1-t3i), done/published.
Only J is in scope; T3/F13/sprint/PI remain open.

### <a id="r4-s1-t3j--contract"></a>Contract

Extract six operations, five DTOs and `_interview_body` into `api/interviews.py`:
candidate start/list/detail/answer/finish and employer assessment summaries.
Compose the candidate/org routers at their original positions; keep every
decorator, signature, body, response schema and ordered auth dependency unchanged.
Retain the full 102-operation ordered auth/OpenAPI fixture. Shared dependencies
remain in `api/dependencies.py`; no moved aggregate imports require aliases in
current callers. No service/store/SQL/migration, rubric/scorer/provider/frontend
or working-demo changes are included.

Acceptance: standalone routers preserve credential-derived candidate ownership,
foreign/absent 404 equality, cookie/key precedence and CSRF on all candidate
writes; start/answer/finish conflicts and invalid-domain/no-question refusals;
text/audio exclusivity, bounds, safe ASR failures, transcription budgets and typed
fallback; persisted versioned content-only advisory scores and candidate-only
transcripts. Employer reads require current employer-scoped `interview_read`
consent, retain allowed/denied audit, expose summaries without transcripts/media,
and refuse on revocation/erasure while another subject remains authorized.

Validation: extend `tests/test_api_route_extraction.py` before extraction for
passing characterization, then mount only interview/auth routers. Pure extraction
does not imply a functional defect or an expected-red result. Run focused
interview/auth/rate/contract pytest and full offline pytest with project Python,
fake providers and isolated stores. Reuse/extend the migrated mixed text/audio HTTP
journey with graceful restart and run actual combined interview Chrome for input,
failure/recovery, persisted rendering/reload and employer summary privacy. Run
bindings, JS syntax, compile/import, AST identity, preservation and diff checks.
Unchanged SQL needs no new PostgreSQL migration/concurrency gate. Record an
implementation self-review and a distinct completion review, then commit/push
scoped changes and verify the tracking remote. Complete only J; K is next.

### <a id="r4-s1-t3j--evidence-and-review"></a>Evidence and review

Pure extraction moves six operations, five DTOs and one response helper into the
182-line `api/interviews.py`; aggregate `routes.py` shrinks from 547 to 387 lines.
The complete 102-operation ordered auth/OpenAPI fixture remains unchanged (digest
`cbdd461be76f67469f960cc56e6349e90ed99003db24b0acc7c4f45f2817e2b5`).
Candidate/org routers compose at their original positions, sharing one appropriate
principal/CSRF gate per operation. Caller search found no moved DTO/handler/helper
imports requiring aggregate aliases. Existing auth aliases used by route guards
remain. No service/store/SQL/rubric/provider/frontend behavior changed.

Commands use `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3j.py <tag>
<Python args>`; omitted arguments run `-m pytest -q --tb=short`. This local runner
clears inherited DEE config/keys, points at absent YAML and uses fake/null/capture
providers and isolated stores. Logs are `.pytest_cache/r4-s1-t3j-<tag>.txt`;
ignored artifacts are not portable setup guarantees.

Pre-move `characterization`: `-m pytest -q --tb=short
tests/test_api_route_extraction.py -k 'interview or full_openapi'`:
**5 passed, 19 deselected, 1 warning, 4.46s**, exit 0. Four new cases first mounted
the aggregate, then switched to only interview/auth routers. An initial test budget
assumption was corrected: malformed audio consumes transcription budget before
parsing even when no provider is called. This is passing characterization of
existing behavior, not an application defect or expected-red reproduction.

Post-move `focused`: `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_interview_api.py
tests/test_interview_org_api.py tests/test_interview_service.py
tests/test_interview_org.py tests/test_interview_review.py tests/test_interview_erasure.py
tests/test_interview_erasure_concurrency.py tests/test_interview_lifecycle_concurrency.py
tests/test_interview_scoring.py tests/test_interview_scoring_llm.py
tests/test_interview_schema.py tests/test_ratelimit_spend.py
tests/test_api_auth_gate.py tests/test_auth_api.py tests/test_route_table_guard.py
tests/test_org_scope_guard.py tests/test_openapi_contract.py`:
**248 passed, 16 skipped, 1 warning, 88.01s**, exit 0 (Starlette/httpx deprecation).
Standalone workflows exercise credential-derived ownership/foreign-absent 404s,
unknown-domain and start/duplicate/finish conflicts, malformed/exclusive audio,
pre-provider rate refusal with Retry-After, typed fallback, saved mixed channels
and scorer-version/advisory fields. They retain candidate-only transcripts and
summary projections, exact-purpose/two-employer current consent, audit,
revocation/erasure, cookie plus foreign candidate/org key precedence and CSRF on
all candidate writes. Controlled unavailable/failed ASR keeps the same question
and allows typed recovery without leaking provider detail. Existing focused tests
cover no-question/bounds, historical score semantics and concurrent lifecycle/
erasure behavior; they do not establish measured assessment quality.

Migrated HTTP (`journey scripts/smoke_r3_s3_t3.py --combined`): **25/25**, exit 0,
42.73s. The existing synthetic mixed-channel journey now reuses the stop-file
uvicorn loop from `smoke_r4_s1_t1a.py` and checks both normal shutdown exits.
It verifies revision-0029 startup, candidate isolation, invalid media and provider
refusals without saved turns, typed/audio continuation and duplicate refusal,
transcript truncation, saved advisory versioned content scoring, repeated-keyword
insufficiency, consent-gated transcript-free employer summaries, exact turns/
assessment across graceful restart, revocation and erasure with a surviving
subject. Logs omit raw media, transcript and private provider error. No working
migration/demo restart; normal exits are not new SQL-disposal instrumentation.

Actual Chrome (`browser scripts/check_ui_interview_integration_browser.py`):
**40/40**, plus **1/1** startup/UI-host harness, exit 0, 87.13s. Browser actions
exercise denied/late microphone permission, typed fallback, unsupported format,
oversize recording, visible ASR failures and recovery, duplicate/stale requests,
saved transcript/truncation and advisory assessment, mixed channels and repeated
keywords, reload and actual process restart, exact employer summary fields/privacy,
scoped consent and revocation, navigation/logout during recording, new-account
isolation and no console errors. App logs omit transcript/private provider error.
Chrome needs existing CDN internet and uses a synthetic microphone
and fake ASR/capture mail; no live-provider or representative scoring-quality claim.
Employer summary assertions use actual HTTP, not a dedicated employer interview UI.
Browser process cleanup/restart is forced on Windows; HTTP owns graceful evidence.

Static checks: `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**,
passed. `node --check frontend/api.js`, `node --check frontend/support.js`, project
`-m compileall -q src/app/api/routes.py src/app/api/interviews.py
tests/test_api_route_extraction.py scripts/smoke_r3_s3_t3.py`, and
`git diff --check` pass. No frontend source change.

Implementation self-review: HEAD `4b59ac9` plus aggregate/new interviews,
consolidated route tests and the existing modified interview HTTP harness.
Specification review maps six operations/five DTOs/helper to full-contract,
standalone, HTTP and actual Chrome validation. Correctness review traces shared
schema/dependency and rate-translation identity, auth-plane order, subject/tenant
ownership, cookie precedence/CSRF, method/error/budget ordering, typed fallback,
transcript/media privacy, content-only advisory/versioned scoring, exact current
consent/audit, revocation/erasure and owned child-process shutdown/restart.
`review -I .pytest_cache/review_r4_s1_t3j.py`: exit 0, 7.15s. All **30** original
aggregate class/function definitions, including decorators, signatures and bodies,
are AST-identical across aggregate/interviews. Independent module import, shared
three domain schemas/rate translator and exactly one appropriate gate per route
pass; five reviewed code/contract hashes recorded. No blocking finding remains.
Same-agent self-review is not independent review or empirical quality evidence.
No SQL/transaction/migration change, so no new PostgreSQL concurrency/migration
gate applies.

Preservation (`.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3j.py`):
710 unrelated tracked files, working DB and five reviewed code/contract hashes
unchanged; scoped links/anchors and tracked/staged whitespace pass.

Full pytest (`full-reviewed`, no extra runner arguments): **3528 passed, 505 skipped, 127 warnings in 768.08s (0:12:48)**,
exit 0. Existing Starlette/httpx deprecation and SQLite expression-index reflection/
autogenerate warnings remain; environment/optional skips do not prove omitted
cases. The full suite ran on the reviewed code; only documentation changed later.
Acceptance and required validation are complete. Existing final-read snapshots,
concurrent-erasure and bounded/uncalibrated assessment limitations remain.

### <a id="r4-s1-t3j--completion-review-and-publication"></a>Completion review and publication

After required checks and completion/evidence/PI/handoff updates, a distinct final
same-agent self-review examined HEAD `4b59ac9` plus the exact nine staged files:
aggregate/new interviews, consolidated route tests, the existing modified
interview HTTP harness and five handoff/roadmap/PI/task/evidence records.
Specification review confirms six operations/five DTOs/helper, unchanged full
ordered API/auth contract, required validation and the K-only next pointer.
Correctness review rechecks shared schemas/principal and rate-translation identity,
candidate/tenant ownership, cookie/CSRF precedence, conflict/error/budget ordering,
typed recovery, candidate-only transcripts, employer summary projection and scoped
current consent/audit, revocation/erasure, versioned advisory content scoring,
owned subprocess shutdown/restart and retained limitations. No blocking finding
remains. `completion-review -I .pytest_cache/review_r4_s1_t3j.py`: exit 0, 2.38s;
all 30 original definitions, independent import, shared schemas/translator,
single appropriate gates and five reviewed hashes match. This later self-review
is separate from implementation review; no independent review is claimed.
Only documentation changed after full pytest. Final preservation, 167 local
links/anchors across five Markdown files and staged whitespace pass. Staging
excludes secrets, working data, generated artifacts and unrelated files.
Configured tracking branch is `origin/main`; remote matched the starting HEAD
before publication. Commit/push will use per-command account selection from G's
existing two-account Credential Manager evidence. Scoped task commit **`7a2f7be`**
was created; `git -c credential.https://github.com.username=RevanParimi push`
(with `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main
from `4b59ac9` to `7a2f7be`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`7a2f7be4b5869cf94d2e53d4faa490ee0471a623`**. Working tree was clean.
No K work, demo restart or deployment occurred.

This two-file documentation-only confirmation records that verified publication
in the handoff and this existing evidence section. Its separate final self-review
against `7a2f7be` checks the exact prose diff, actual remote evidence, unchanged
task limits and K-only next pointer; no blocking finding remains. Scoped links/
whitespace and preservation checks pass. Application code remains at the full
pytest/API/Chrome validated state, so no application tests were rerun for prose.
The final response reports the verified remote SHA after this confirmation's
commit/push.

### <a id="r4-s1-t3j--handoff"></a>Handoff

Only J completed in this continuation. T3/F13/sprint/PI remain open. Exact next:
**R4-S1-T3K - Extract curation routes**, not started. Add K's bounded contract/
evidence inline in the existing T3 record; reuse consolidated route tests and
existing curation HTTP/Chrome journeys. Preserve operator auth/CSRF, paginated
queue/status/cursor contracts, revision conflicts, alias decisions and curated
overlay behavior. T4 has not started. No next task or deployment during publication.
