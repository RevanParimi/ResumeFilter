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
- [R4-S1-T3](#r4-s1-t3)
- [R4-S1-T3M](#r4-s1-t3m)
- [R4-S1-T4A](#r4-s1-t4a)
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

Status: done (2026-10-17). Parent: [T3](#r4-s1-t3). PI-R4 / R4-S1; F13.
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

Status: done (2026-10-18). Parent: [T3](#r4-s1-t3). PI-R4 / R4-S1; F13.
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

Status: done (2026-10-18). Parent: [T3](#r4-s1-t3). PI-R4 / R4-S1;
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

Status: done (2026-10-18). Parent: [T3](#r4-s1-t3). PI-R4 / R4-S1;
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

Status: done (2026-10-20). Parent: [T3](#r4-s1-t3). PI-R4 / R4-S1;
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

Status: done (2026-10-20). Parent: [T3](#r4-s1-t3). PI-R4 / R4-S1;
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
Parent: [T3](#r4-s1-t3). Prerequisite: [F](#r4-s1-t3f), done.
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

Status: done and published (2026-10-20). Parent: [T3](#r4-s1-t3).
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

Status: done and published (2026-10-21). Parent: [T3](#r4-s1-t3).
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

Status: done and published (2026-10-22). Parent: [T3](#r4-s1-t3).
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

## <a id="r4-s1-t3k"></a>R4-S1-T3K - Extract curation routes

Status: done (2026-10-22). Only K completed in this session.
Trigger/result: curation requests currently execute in the aggregate route module;
move its two operations and `CurationResolveRequest` into `api/curation.py`.
Compose the already guarded routes at the same aggregate position. Preserve the
shared dependency and domain response types; caller search found no request DTO
or handler imports requiring aggregate compatibility aliases.

Acceptance: full 102-operation ordered auth/OpenAPI contract is unchanged;
standalone curation/auth routers preserve operator key/session gating, cookie
precedence and CSRF, authenticated decision identity, raw-free receipts,
status/limit/cursor behavior, 404/409/422 translations, required revisions,
stale snapshot/alias-conflict rollback, map/create/ignore and immediate overlay
refresh. Source ownership, erasure and reload/restart behavior stay intact.
No service/store/SQL/migration/scorer/frontend change; process-local overlay and
mutable pagination limitations remain. L/M/T4 do not start.

Validation: characterize curation workflows in the existing consolidated route
test module before moving, then mount just curation/auth for those workflows.
Run focused curation/auth/route tests and full offline pytest; reuse
`smoke_curation_activation.py` for migrated HTTP/restart and
`check_ui_curation_browser.py` through its `--browser` option for actual Chrome.
Reuse the existing stop-file uvicorn loop for graceful HTTP shutdown; preserve
the demo and working DB. Run bindings/JS syntax, compile/diff checks and record
implementation self-review, then completion review and scoped commit/push with
remote verification. Pure extraction expects passing characterization, not a
functional defect or an expected-red test. No new PostgreSQL concurrency gate
applies without SQL/transaction/schema changes.

### <a id="r4-s1-t3k--evidence-and-review"></a>Evidence and review

Two operations and one DTO now live in `api/curation.py` (73 lines); aggregate
`routes.py` is 328 lines. The full 102-operation contract fixture is unchanged.
The shared admin dependency and domain response/error classes retain identity.

Commands use `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3k.py <tag>
<Python args>`; omitted arguments run `-m pytest -q --tb=short`. The local runner
clears inherited DEE config/keys, points to absent YAML and uses isolated stores
and fake/null/capture providers. Logs: `.pytest_cache/r4-s1-t3k-<tag>.txt`;
ignored local artifacts are not portable setup guarantees.

Pre-move `characterization`: `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_curation_api.py
tests/test_curation_activation.py`: initial test-setup error (nonexistent store
helper), 1 failed/46 passed; corrected setup uses the existing durable-source
fixture and access-key method. `characterization-corrected`: **47 passed,
1 warning, 19.16s**, exit 0, 24.92s runner. All three new workflows first mounted
the original aggregate, then switched to curation/auth only. This pure extraction
expects passing characterization; the fixture error is not a product regression.

Post-move `focused`: `-m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_curation_api.py
tests/test_curation_activation.py tests/test_curation_service.py
tests/test_curation_store.py tests/test_curation_overlay.py
tests/test_curation_review_revisions.py tests/test_curation_owned_store.py
tests/test_curation_capture.py tests/test_curation_input_boundary.py
tests/test_curation_schema.py tests/test_api_auth_gate.py tests/test_auth_api.py
tests/test_route_table_guard.py tests/test_org_scope_guard.py
tests/test_openapi_contract.py`: **190 passed, 64 skipped, 52 warnings, 119.43s**,
exit 0 (125.16s runner). Three standalone workflows assert capped/cursor/status
queues, two surviving contributors and erasure revisions, malformed/refused
requests without mutation, exact raw-free receipts, immediate overlay changes,
stale replacement and alias rollback, key/plane isolation, cookie/key CSRF,
authenticated decision identity and reviewer revocation. Existing fixtures also
exercise owned storage and revision lifecycle. PostgreSQL skips do not prove
controlled lock behavior; Starlette/httpx and expression-index reflection warnings
remain.

Migrated HTTP (`journey scripts/smoke_curation_activation.py`): **20/20**, exit 0,
20.81s. Reuses the existing stop-file uvicorn loop and checks both normal shutdown
exits; revision 0029, two source contributors, surviving ownership after erasure,
refused capture, raw-free map/ignore receipts, auth and cookie/key CSRF,
authenticated operator identity, exact queue revision across graceful restart,
legacy/new overlay loading, expiry/maintenance and sanitized capture failure pass.
No working migration/demo restart; normal exits are not new SQL-disposal probes.

Actual Chrome (`browser scripts/smoke_curation_activation.py --browser`):
**53/53 combined HTTP/browser checks**, exit 0, 58.48s. Real operator sign-in,
map/create/ignore and normalization, revision transmission, reload, alias and
two-operator stale-review conflicts, uncertain network/timeout/503 recovery,
failed refresh, navigation and late writes, actual 20/25-row paging, denied/invalid
read cache clearing, expiry/erasure, reviewer revocation and denied org/candidate
sessions all pass. No console exceptions. Three graceful app lifespans preserve
browser-approved vocabulary over restart; Chrome cleanup is forced on Windows.
Chrome needs existing CDN internet; providers/mail are fake/capture. No live
provider, measured quality or cross-worker overlay claim.

Static: `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**, passed;
`node --check frontend/api.js`, `node --check frontend/support.js`, project
`-m compileall -q src/app/api/routes.py src/app/api/curation.py
tests/test_api_route_extraction.py scripts/smoke_curation_activation.py` and
`git diff --check` pass. No frontend source change.

Implementation self-review: HEAD `36b92d9` plus aggregate/new curation,
consolidated route tests and the existing modified curation HTTP harness.
Specification review maps both operations/DTO to full-contract, standalone, HTTP
and actual Chrome evidence. Correctness review traces principal/dependency order,
cookie/key CSRF and operator identity, source ownership/privacy, queue bounds,
cursor/status/error translations, revision/alias rollback, overlay/erasure and
owned subprocess shutdown/restart. `review -I .pytest_cache/review_r4_s1_t3k.py`:
exit 0, 3.03s. All **18** original aggregate class/function definitions, including
decorators/signatures/bodies, are AST-identical across aggregate/curation;
independent import, shared schemas/errors and exactly one admin gate per operation
pass. Five reviewed code/contract hashes recorded. No blocking finding remains.
Same-agent self-review is not independent review. No SQL/transaction/migration
change, so no new PostgreSQL concurrency/migration gate applies.

Initial preservation (`.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3k.py`):
711 unrelated tracked files, working DB and five reviewed code/contract hashes
unchanged; scoped Markdown links/anchors and whitespace pass. Remote `origin/main`
matches starting HEAD `36b92d9b3df513e5954a7bd27b0b6eb7fcaf8289`.
Full pytest (`full-reviewed`, no extra runner arguments): **3531 passed,
505 skipped, 127 warnings in 7058.15s (1:57:38)**, exit 0 (7074.35s runner).
Existing Starlette/httpx deprecation and SQLite expression-index reflection/
autogenerate warnings remain. Environment/optional skips do not establish omitted
cases. The full suite ran on the reviewed code; only documentation changed later.
Acceptance and required validation are complete. Mutable queue ordering,
process-local overlay and retention scheduling limitations remain unchanged.

### <a id="r4-s1-t3k--completion-review-and-publication"></a>Completion review and publication

After required checks and completion/evidence/PI/handoff updates, a distinct final
same-agent self-review examined HEAD `36b92d9` plus the exact nine staged files:
aggregate/new curation, consolidated route tests, existing curation HTTP harness
and five handoff/roadmap/PI/task/evidence records. Specification review confirms
two operations/one DTO, unchanged full ordered API/auth contract, required runtime
validation, evidence ownership and the L-only next pointer. Correctness review
rechecks shared schemas/errors/principal identity and dependency order, cookie/key
CSRF and authenticated decision actor, source privacy/erasure, queue bounds and
status/cursor/error behavior, revision/alias rollback, overlay refresh and graceful
subprocess restart. No blocking finding remains. `completion-review -I
.pytest_cache/review_r4_s1_t3k.py`: exit 0, 5.10s; all 18 original definitions,
independent import, shared schemas/errors, single admin gates and five reviewed
hashes match. This later self-review is separate from implementation review;
no independent review is claimed. Only documentation changed after full pytest.
Final preservation confirms 711 unrelated tracked files, working DB and reviewed
code/contract hashes unchanged; 169 local links/anchors across five scoped Markdown
files and tracked/staged whitespace pass. Staging excludes secrets, working data,
generated artifacts and unrelated files. Configured tracking branch is
`origin/main`; publication uses G's per-command account selection for the existing
two-account Credential Manager setup. Commit/push and remote verification follow
this recorded final review; actual publication is recorded below.

Scoped task commit **`f4e41dc`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`36b92d9` to `f4e41dc`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`f4e41dc1df27da646b66ad6ed9a8032b873e6b81`**. Working tree was clean.
No L work, demo restart or deployment occurred.

This two-file documentation-only confirmation records that verified publication
in the handoff and this existing evidence section. Its separate final self-review
against `f4e41dc` checks the exact prose diff, actual remote evidence, unchanged
task limits and L-only next pointer; no blocking finding remains. Scoped links/
whitespace and preservation checks pass. Application code remains at the full
pytest/API/Chrome validated state, so no application tests were rerun for prose.
The final response reports the verified remote SHA after this confirmation's
commit/push.

### <a id="r4-s1-t3k--handoff"></a>Handoff

Only K completed. T3/F13/sprint/PI remain open. Exact next: **R4-S1-T3L - Extract
operator accounts, retention, metrics and signal-quality routes**, not started.
Write L's contract/evidence inline in the existing T3 record; reuse consolidated
route tests and existing operator HTTP/Chrome journeys. Preserve admin auth/CSRF,
account/session revocation, dry-run retention defaults and refusal, metrics media
type and advisory label/report behavior. T4 has not started. No next task or
deployment during publication.

## <a id="r4-s1-t3l"></a>R4-S1-T3L - Extract operator routes

Status: done and published (2026-10-22). Only L completed this session.

### Contract and acceptance

Move six operations and three DTOs from `api/routes.py` into `api/operator.py`:
`GET /metrics`, `POST /admin/retention/sweep`, `POST/GET /admin/users`,
`DELETE /admin/users/{admin_user_id}` and `GET /admin/signal-quality`.
Keep existing method/path, operation IDs, schemas, descriptions, status/error
bodies and ordered dependency/OpenAPI contract. The module uses three guarded
router segments (metrics, retention, accounts/report), because the existing
portal/domain routes interleave them. Compose their existing APIRoutes at their
original positions without another inherited dependency context or route slices.

Acceptance: machine credentials and operator cookies retain shared admin auth,
session precedence/CSRF and other-plane refusals. Account creation retains hashed
email, duplicate 409, missing-delete 404 and deletion revokes every target session
without revoking another operator. Retention keeps the empty-body dry-run default,
disabled-apply 409 without mutation, bounded preview/apply parity and recent-row
preservation. Metrics keep Prometheus media type/text and bounded private labels.
Signal quality keeps outcomes/ledger selection, configured sample floor,
operator-label opt-in and explicit refusal shapes without exposing source rows.

Extend consolidated route characterizations before moving code; first run against
the aggregate, then standalone operator/auth routers. Reuse existing focused
auth/retention/metrics/signal tests and full 102-operation contract fixture.
Run full offline pytest, migrated scratch HTTP with actual process restart and
real operator-account Chrome actions using `smoke_r3_s2_q.py --browser`.
Extend that existing HTTP harness for retention/metrics/signal behavior and reuse
the shared graceful stop-file server pattern. Run bindings, syntax/import,
whitespace, documentation/preservation checks and implementation self-review,
then record completion and a distinct final self-review before scoped commit/push.
No SQL/schema/transaction/provider/frontend changes; no new PostgreSQL migration
or concurrency gate applies. Working storage/demo and unrelated files stay intact.

### Evidence

Starting HEAD `f981714`; initial worktree clean. Sanitized local runner
`.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3l.py <tag> <Python args>`
clears inherited DEE settings/secrets, ignores `.env`, uses isolated test stores
and blocks external GitHub; no arguments after the tag means full pytest.
Baseline hashes cover 720 tracked files including working storage.

Pre-move `characterization -m pytest -q --tb=short
tests/test_api_route_extraction.py -k 'operator_accounts_preserve or
operator_retention_preserves or operator_signal_quality_preserves or
product_extraction'`: **4 passed, 26 deselected, 1 warning, 7.66s**, exit 0
(15.87s runner). Characterizations ran against the original aggregate, then
switched to standalone auth/operator routers. Pure extraction expects passing
characterization; no reproduced product defect is claimed.

Post-move `focused -m pytest -q --tb=short tests/test_api_route_extraction.py
tests/test_auth_api.py tests/test_api_auth_gate.py tests/test_route_table_guard.py
tests/test_org_scope_guard.py tests/test_openapi_contract.py
tests/test_retention_api.py tests/test_retention_sweep.py tests/test_retention_plan.py
tests/test_retention_cli_contract.py tests/test_metrics.py
tests/test_signal_quality_route.py tests/test_signal_quality_labels.py
tests/test_signal_quality_service.py tests/test_signal_quality_metrics.py
tests/test_signal_quality_schema.py tests/test_signal_quality_signals.py
tests/test_signal_quality_cli.py`: **240 passed, 14 warnings, 76.78s**, exit 0
(81.45s runner). Full 102-operation ordered auth/OpenAPI fixture is unchanged.
New standalone workflows verify all six operations' plane refusals, cookie/key
CSRF, hashed account identity, duplicate/missing refusals, both target sessions'
revocation and another operator's survival; retention defaults/refusal/cap/parity,
recent-row survival and private Prometheus text; actual saved human labels,
opt-in/configured floor, outcomes/ledger refusal shapes and input validation.

Initial migrated scratch HTTP `journey scripts/smoke_r3_s2_q.py`: **44/44**,
exit 0, 17.66s. Existing harness now uses the shared stop-file uvicorn loop;
normal exit 0 is required at shutdown/restart. Added expired/recent-resume preview,
disabled apply/CSRF refusals without mutation, enabled apply after restart,
operator-label persistence/opt-in, ledger mismatch, malformed queries, metrics
media type/privacy and revoked-operator access. Final expanded plane-denial
checks also pass in the combined Chrome invocation. No working migration
or demo restart; normal exits do not add SQL disposal probes.

Actual Chrome `browser scripts/smoke_r3_s2_q.py --browser`: **62/62 combined
HTTP/browser checks**, exit 0, 42.51s. Real operator sign-in, create/list/delete,
another session's revocation, account persistence across restart, navigation/cache
clearing, revoked-operator recovery, denied org/candidate cookies, backend
org/curation integration and no console exceptions pass. All three app lifespans
require graceful exit 0; browser process cleanup is forced on Windows. Chrome
uses existing CDN internet and fake/capture providers/mail. No live-provider,
measured-quality or cross-worker claims.

Static: `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**, pass;
`node --check frontend/api.js`, `node --check frontend/support.js`, project
`-m compileall -q src/app/api/routes.py src/app/api/operator.py
tests/test_api_route_extraction.py scripts/smoke_r3_s2_q.py` and `git diff --check`
pass. No frontend source change.

Implementation self-review: HEAD `f981714` plus aggregate/new operator,
consolidated route tests and existing operator HTTP harness. Specification review
maps six operations/three DTOs to characterization, standalone/full-contract and
migrated HTTP assertions; recorded full/Chrome evidence completes the runtime gates.
Correctness review traces principal/dependency order and CSRF, account identity
and multi-session revocation, retention defaults/configuration/bounds/mutation,
metric privacy/media type, report label provenance/refusals and graceful restart.
`review -I .pytest_cache/review_r4_s1_t3l.py`: exit 0, 2.49s. All **15** original
aggregate class/function definitions are AST-identical across aggregate/operator,
normalizing only two decorator router variable names. Independent import, shared
contracts/services and exactly one admin dependency per operation pass; five
reviewed code/contract hashes recorded. No blocking finding remains. Same-agent
self-review is not independent review. No SQL/transaction/migration change;
no new PostgreSQL concurrency/migration gate applies.

Initial preservation `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3l.py`:
712 unrelated tracked files, working DB and five reviewed code/contract hashes
unchanged; 169 local Markdown links/anchors and tracked/staged whitespace pass.
Remote `origin/main` matches starting HEAD
`f9817141dee48da2c8fad0c40444db44843eb516`.

Full pytest `full-reviewed` (no extra runner arguments; project
`-m pytest -q --tb=short`): **3534 passed, 505 skipped, 127 warnings in 973.25s
(0:16:13)**, exit 0 (983.51s runner). Existing Starlette/httpx deprecation and
SQLite expression-index reflection/autogenerate warnings remain. Environment/
optional skips do not prove omitted cases. Five reviewed code/contract hashes
remain unchanged; only documentation changed after full pytest started.
Acceptance and required validation are complete. Aggregate `routes.py` is now
200 lines (328 before L); `operator.py` contains six operations and three DTOs.
Metrics remain process-local, retention still needs an external schedule and
synthetic fixtures do not establish measured signal quality.

### Completion review and publication

After required validation and completion/evidence/PI/handoff updates, a distinct
final same-agent self-review examined HEAD `f981714` plus the exact nine staged
files: aggregate/new operator, consolidated route tests, existing operator HTTP
harness and five handoff/roadmap/PI/task/evidence records. Specification review
confirms six operations/three DTOs, unchanged 102-operation ordered API/auth
contract, all required validation layers, single evidence ownership and M-only
next pointer. Correctness review rechecks principal/dependency order and cookie/
key CSRF, hashed identity and target/other-operator session lifecycles, retention
preview/configuration/cap/parity/recent-row survival, metrics privacy/media type,
advisory label provenance/refusals and graceful process restart. No blocking
finding remains. Two documentation phrases were clarified to describe shared
server-loop reuse and recorded runtime evidence accurately; code is unchanged.
`completion-review -I .pytest_cache/review_r4_s1_t3l.py`: exit 0, 6.17s. All
15 original definitions (normalizing two decorator router variable names),
independent import, shared contracts/services, single admin gates and five
reviewed code/contract hashes match. This later self-review is separate from
implementation review; no independent review is claimed. Only documentation
changed after the full regression run began. Final preservation confirms 712
unrelated tracked files, working DB and five reviewed code/contract hashes
unchanged; 171 local Markdown links/anchors and tracked/staged whitespace pass.
All changes are staged in the named nine-file scope; secrets, working data and
generated artifacts are excluded. Tracking branch is `origin/main`; publication
uses G's existing per-command account selection. Scoped commit/push and remote
verification follow; actual publication will be recorded here.
No M/T4 work, demo restart or deployment started.

Scoped task commit **`26d9515`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`f981714` to `26d9515`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`26d9515bf122b73be549ce9ad1eafd05539fe1b8`**. Working tree was clean.
No M work, demo restart or deployment occurred.

This two-file documentation-only confirmation records verified publication in
the handoff and this evidence section. Its separate final self-review against
`26d9515` checks the exact prose diff, actual remote evidence, unchanged task
limits and M-only next pointer; no blocking finding remains. Scoped links,
whitespace and preservation pass. Application code remains at the full
pytest/HTTP/Chrome validated state, so no application tests are rerun for prose.
The final response reports the verified remote SHA after this confirmation's
commit/push.

### Handoff

Only L completed. T3/F13/sprint/PI remain open. Exact next development task:
**R4-S1-T3M - Extract public health/domain/grievance/service surface and finalize
composition**, not started. Write M's bounded contract/evidence inline in the
existing T3 record; preserve the full ordered API/auth contract, named public
allowlist, `/domains` admin guard, liveness mode and advisory/human-review service
response. T4 has not started. No next task starts during L publication.

## <a id="r4-s1-t3"></a>R4-S1-T3 - Split routes by product area

Status: done (2026-10-22); split before implementation, 2026-10-17. PI-R4 / R4-S1;
F13. Prerequisite: [T2](#r4-s1-t2), done.

Original contract: the 2,871-line route module mixed 102 operations across auth
planes and product areas. Extract cohesive modules without changing HTTP behavior or adding
a routing/dependency framework. Shared principal resolution and CSRF remain in
one dependency module; preserve import aliases actually used by current callers.
Each child evidence section owns its bounded contract, focused/full pytest,
affected migrated HTTP and relevant browser journey, OpenAPI/route comparison and separate self-review.
No SQL/service/scorer/frontend changes are implied. Missing evidence keeps the
child open; this parent required every child to pass. A-M are now complete.

| Child | Bounded area | Status |
|---|---|---|
| [T3A](#r4-s1-t3a) | Authentication/session router and shared request/auth dependencies | Done (2026-10-17); child owns evidence |
| [T3B](#r4-s1-t3b) | Evaluation and operator reports/outcomes | Done (2026-10-18); child owns evidence |
| [T3C](#r4-s1-t3c) | Candidate intake, resume management and profile sources | Done (2026-10-18); child owns evidence |
| [T3D](#r4-s1-t3d) | Employer screening, batches, queue and scoped reports/outcomes | Done (2026-10-18); child owns evidence |
| [T3E](#r4-s1-t3e) | Ledger organizations, consent, records, coding and reputation | Done (2026-10-20); child owns evidence |
| [T3F](#r4-s1-t3f) | Employer jobs, compensation and dashboard | Done (2026-10-20); child owns evidence |
| [T3G](#r4-s1-t3g) | Feature materialization and talent search | Done/published (2026-10-20); child owns evidence |
| [T3H](#r4-s1-t3h) | Candidate portal, consent/access and data-principal requests | Done (2026-10-20); child owns evidence |
| [T3I](#r4-s1-t3i) | Verification, documents and employer assurance reads | Done (2026-10-21); child owns evidence |
| [T3J](#r4-s1-t3j) | Candidate interviews and employer assessment summaries | Done (2026-10-22); child owns evidence |
| [T3K](#r4-s1-t3k) | Curation | Done (2026-10-22); child owns evidence |
| [T3L](#r4-s1-t3l) | Operator accounts, retention, metrics and signal quality | Done (2026-10-22); child owns evidence |
| [T3M](#r4-s1-t3m) | Public health/domain/grievance/service surface and final composition | Done (2026-10-22); child owns evidence |

Common acceptance: every method/path, operation ID, success/error response,
response schema, dependency order, ownership/auth plane and cookie/CSRF behavior
is preserved; no duplicate/unguarded registration or circular imports. Child
boundaries may be refined from actual callers before starting each child; do not
create placeholder evidence files for unstarted children. Reuse existing guards,
fakes and journeys, and compare the full contract at every extraction.

A-M are complete; their linked sections own the bounded contracts, exact
validation, review and publication records. Final composition keeps all 102
operations in their original order with the same OpenAPI/auth digest. `routes.py`
is now 69 lines of assembly, with no handlers or DTOs; all handlers live in
product modules. This closes T3 only. F13, R4-S1 and PI-R4 remain open for T4
and their integration gate. Exact next: **R4-S1-T4 - Extract frontend components
and remove dead handlers**, not started. Define its first bounded child in the
next session before implementation. No T4 work starts during M publication.

2026-10-18 R4-M1 maintenance consolidated completed records and related tests;
[the audit](../CODEBASE_REVIEW_2026-09-07.md#follow-up-2026-10-18--test-and-delivery-consolidation)
owns its acceptance and validation. No additional route extraction in that task.

## <a id="r4-s1-t3m"></a>R4-S1-T3M - Public surface and final composition

Status: done and published (2026-10-22). Prerequisite: [L](#r4-s1-t3l), done/published.

### Contract and acceptance

Extract `GET /domains`, `/grievance`, `/healthz` and `/` with their three DTOs
into `api/public.py`. The domain router retains the shared admin dependency;
the other three operations retain their named public exemptions. Keep the
existing ordered 102-operation OpenAPI/auth fixture unchanged, including route
names, descriptions, schemas and dependencies. Separate the service-description
router so `/` remains last, after auth and the UI mount. Move live endpoint
discovery with that handler; retain helper/guard aliases used by current callers.
Reduce `routes.py` to ordered assembly, without route slicing, extra inherited
dependencies or a new framework. No service, SQL, transaction, schema, frontend,
provider, readiness or scoring changes.

Acceptance: anonymous/invalid credentials can read health, the configured public
four-field grievance contact and the advisory/human-review service description.
Health retains version, environment, ordered registered domains and effective
null/live mode without invoking providers or storage. `/domains` returns the
same registered metadata only for an admin key/session, refusing anonymous,
org and candidate callers. Endpoint discovery follows each requesting app's
current routes, including later additions, excluding docs/root/mounts and
HEAD/OPTIONS. Preserve cookie precedence/CSRF across the composed API.

Extend `tests/test_api_route_extraction.py` with pre-move characterizations,
then run them against standalone public/domain/auth routers. Run focused API,
root/contact/boot/auth/route/schema tests and full offline pytest. Extend the
existing `scripts/smoke_r4_s1_t3a.py` migrated scratch HTTP/graceful-restart
journey with these public/guarded behaviors, plus an actual Chrome evaluation/
auth journey to check final composition. Run bindings/syntax/import, diff,
documentation/preservation checks, implementation self-review and a distinct
final completion self-review before scoped commit/push/remote verification.
No new PostgreSQL migration/concurrency gate applies. Preserve working storage,
unrelated files and the existing demo. Finish only M; T4 stays unstarted.

### Evidence

Starting HEAD `172c8b2c325c51ddffa52d0f18a206b6dc21db78`; initial tree clean.
Sanitized runner `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t3m.py
<tag> <Python args>` clears inherited DEE config/keys, ignores `.env`, blocks
external GitHub and uses fake providers/isolated stores. Omitted Python args
run `-m pytest -q --tb=short`. Logs use `.pytest_cache/r4-s1-t3m-<tag>.txt`.
Baseline hashes cover 721 tracked files, including working storage; the task
contract had already been written when this preservation snapshot was taken.

Pre-move `characterization -m pytest -q --tb=short
tests/test_api_route_extraction.py -k 'public_surface or public_domains or
public_service or product_extraction'`: **5 passed, 29 deselected, 1 warning,
3.57s**, exit 0 (6.46s runner). The first attempt had two fixture failures
because the composed app's access middleware also needs the metrics recorder;
supplying that existing recorder fixed the fixture before extraction. Those
failures are not a product-defect reproduction. Characterizations first ran
against the aggregate and then switched to standalone public/domain/auth routers.

Final focused `final-focused -m pytest -q --tb=short
tests/test_api_route_extraction.py tests/test_api.py tests/test_root_endpoints.py
tests/test_grievance_contact.py tests/test_boot_config.py
tests/test_api_auth_gate.py tests/test_route_table_guard.py
tests/test_org_scope_guard.py tests/test_openapi_contract.py
tests/test_ui_mount.py tests/test_auth_api.py`: **170 passed, 1 warning, 49.88s**,
exit 0 (55.80s runner). An earlier focused run passed 170/170 before the final
explicit model-call refusal assertion was added. The final run includes that
assertion. Full ordered API/auth/OpenAPI digest remains
`cbdd461be76f67469f960cc56e6349e90ed99003db24b0acc7c4f45f2817e2b5` (102 operations).

New standalone tests verify public reads with no auth/store services, both
effective model modes with model invocation forbidden, exact configured contact,
advisory/human-review response, admin-key/session domain metadata and other-plane
refusals, logout refusal and requesting-app/later-route discovery without docs,
mounts, root, HEAD/OPTIONS or duplicates. Existing root tests also exercise
discovery through actual `create_app` composition.

Migrated scratch HTTP `journey scripts/smoke_r4_s1_t3a.py`: **83/83**, exit 0,
27.87s runner. Added anonymous/invalid-key public reads, configured four-field
contact, effective live mode (fake model), exact 101-other-operation service
listing against HTTP OpenAPI, domain key/operator-cookie access and candidate/org
cookie refusals before/after restart. Existing auth/ledger/employer/features/
portal/verification flows, consent/revocation, ownership and SQL disposal still
pass. Both scratch lifespans exit gracefully with revision 0029. No working
migration, demo restart or live provider calls.

Static: `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**, pass;
`node --check frontend/api.js`, `node --check frontend/support.js`, project
`-m compileall -q src/app/api/routes.py src/app/api/public.py src/app/main.py
tests/test_api_route_extraction.py scripts/smoke_r4_s1_t3a.py` and
`git diff --check` pass. No frontend source change.

Implementation self-review: HEAD `172c8b2` plus aggregate/new public module,
main composition, consolidated route tests and existing HTTP harness. Specification
review maps all four routes/three DTOs to standalone/full-contract and HTTP
assertions. Correctness review traces domain admin dependency, named exemptions,
cookie precedence/CSRF across unchanged planes, light health behavior, contact
privacy, current requesting-app discovery, operation IDs/order and restart.
`review -I .pytest_cache/review_r4_s1_t3m.py`: exit 0, 9.37s runner. All ten moved
definitions are AST-identical, normalizing only domain/root decorator router names
and root's explicit Request/`request.app` access in place of its closure. Standalone
import needs no aggregate/main import; single domain guard, public exemptions,
helper identity, full contract and absence of aggregate/main-owned handlers pass.
Six reviewed code/contract hashes recorded. No blocking finding remains. This
same-agent self-review is not independent review. No SQL/transaction/migration
change; no new PostgreSQL concurrency/migration gate applies.

Actual Chrome `browser scripts/check_ui_evaluate_browser.py`: **38/38**, exit 0,
39.68s runner. Real sign-in/evaluation/report/advisory output, feedback recovery,
reload, selected-domain PDF retry, auth expiry/ownership, candidate portal,
consent/access, error recovery and erasure pass with no console exceptions.
The shared browser harness also reports its **1/1** app-contract check. Chrome
uses existing CDN internet, fake model/GitHub/speech and captured mail; injected
transport faults test browser recovery, not real provider outages. Browser/app
process cleanup is forced on Windows; the separate HTTP journey owns graceful
restart evidence. No live-provider or measured-quality claim.

Preservation `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t3m.py`:
712 unrelated tracked files, working DB and six reviewed hashes unchanged;
172 local Markdown links/anchors and tracked/staged whitespace pass. Read-only
remote check confirms `origin/main` still matches starting HEAD `172c8b2`.

Full pytest `full-reviewed` (no extra runner args; project
`-m pytest -q --tb=short`): **3538 passed, 505 skipped, 127 warnings in
1166.90s (0:19:26)**, exit 0 (1180.56s runner).
Existing Starlette/httpx deprecation and SQLite expression-index reflection/
autogenerate warnings remain; optional/environment skips do not prove omitted
cases. The reviewed code stayed unchanged through this full run. Final review
then removed one terminal blank line in the new public module; its Python AST
is identical. The affected static/contract checks were rerun below. No other
application/test/harness source changed after full pytest started.

All acceptance and required validation gates are complete. Four operations,
three DTOs and three discovery helpers now live in `api/public.py`; `routes.py`
is 69 lines (200 before M). Its ordered assembly has no handlers/models.
The public allowlist, `/domains` admin guard and effective liveness behavior
remain unchanged. Liveness is not storage readiness; readiness remains R4-S3-T2.
Synthetic providers prove mechanics, not live integration or measured quality.
Only M completed this session; A-M now close T3, while F13/sprint/PI remain open.
No T4 work, working-data migration, demo restart or deployment occurred.

### Completion review and publication

After required validation and completion records, a distinct final same-agent
self-review examined HEAD `172c8b2` plus the exact eleven staged files: aggregate,
new public module, main composition, consolidated route tests, existing HTTP
harness, feature overview, handoff, roadmap, PI/evidence and retired active T3
record. Specification review confirms four operations/three DTOs, unchanged
ordered 102-operation API/auth contract, all validation layers, A-M parent
closure, single evidence ownership, updated inbound links and T4-only next pointer.
Correctness review rechecks domain admin dependency and cookie precedence,
public exemptions/contact privacy, health without storage/model calls, requesting
app discovery, operation-ID assignment, dependency order, graceful restart and
the unchanged consent/erasure/advisory boundaries. No blocking finding remains.
This later self-review is separate from implementation review; no independent
review is claimed.

The staged whitespace check caught an extra terminal blank line in the new
public module (untracked files were absent from the earlier `git diff --check`)
and consolidation initially added a terminal blank line in the evidence file.
Both are removed. The public module's before/after AST is identical; its reviewed
hash was refreshed only for that whitespace change. `final-format-contract -m
pytest -q --tb=short tests/test_api_route_extraction.py -k 'public_surface or
public_domains or public_service or product_extraction'`: **5 passed,
29 deselected, 1 warning, 7.62s**, exit 0 (12.74s runner). Project
`-m compileall -q src/app/api/public.py` and tracked/staged whitespace pass.
`completion-review-final -I .pytest_cache/review_r4_s1_t3m.py`: exit 0, 5.98s
runner; rechecks all ten
AST definitions, standalone import, shared guards/helpers, original route order,
full contract and six final reviewed hashes. Final preservation confirms **711**
unrelated tracked files, working DB and six reviewed hashes unchanged; scoped
links/anchors and whitespace pass. Secrets, working data and local artifacts are
excluded. Tracking branch is `origin/main`; publication used G's existing
per-command account selection. No T4 work or deployment started.

Scoped task commit **`73a9870`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`172c8b2` to `73a9870`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`73a98701fbe83abdc8eee4a7d555ced9edfd924a`**. Working tree was clean.

This two-file documentation-only confirmation records verified publication in
the handoff and this evidence section. Separate final same-agent self-review
against `73a9870` checks the exact prose diff, actual remote evidence, completed
T3 status and T4-only next pointer; no blocking finding remains. Scoped links,
whitespace and preservation pass. Application/test/harness code remains at the
validated state, so no application tests are rerun for prose. The final response
reports the verified remote SHA after this confirmation's commit/push.

### Handoff

Exact next development task: **R4-S1-T4 - Extract frontend components and remove
dead handlers**, not started. Read its PI section and workflow and define a
bounded first child before implementation in the next session. Stop after M.

## <a id="r4-s1-t4a"></a>R4-S1-T4A - Extract operator-account UI logic

Status: done and published (2026-10-22). Parent: [T4](#r4-s1-t4).

### Contract and acceptance

Move the operator-account handlers and their view-value mapping out of the
4,209-line `frontend/Veritas.dc.html` logic class into the plain script
`frontend/operator-accounts.js`. Expose a single factory that extends the supplied
DCLogic base; pass existing API/date/error/timeout helpers explicitly. The
component retains its shared state, navigation, session-loss/unmount cleanup,
template and stable bound handler names. This small inheritance seam preserves
the existing class-field semantics without a controller/dependency framework.
Compose its values into `liveVals()` at the original precedence. Load the script
before logic evaluation and add only this named asset to the static allowlist;
keep generated `support.js` unchanged. Update the two existing offline execution
entry points so they load the actual extracted script.

Acceptance: operator list/status/filter/pagination, create/confirmation/delete,
server refresh and self-deletion/session revocation behave unchanged. No user
email/hash/sample rows render as account data. Non-admin planes refuse both
handlers and privileged values. Duplicate clicks send one mutation; malformed
responses, CSRF/4xx/5xx/timeouts and uncertain writes retain existing recovery
copy and drafts. Navigation/session change/unmount invalidate late results.
Detached template callbacks retain their component receiver, and two component
instances share no handlers, requests or state. All shipped bindings still
resolve. Anonymous `/ui/` can fetch the declared module, while unrelated files
remain refused. Full ordered API/auth contract remains unchanged.

No duplicate mock/live source or dead operator-account handler was found in this
bounded area; do not remove other screens' fixtures/handlers in A. Inspect the
original/moved bodies during review and preserve current lifecycle behavior.

### Required validation

Extend `scripts/test_ui_admin_users.js` with pre-move detached-callback and
two-instance characterizations, then run the existing account/evaluation suites
against extracted composition. Extend `tests/test_ui_mount.py` for anonymous
module delivery. Run focused UI/mount/image/auth/API-contract pytest, full
offline pytest, bindings and JS syntax (including extracted inline logic).
Use `scripts/check_ui_admin_users_browser.py` for the real migrated-scratch
account journey with reload/errors/CSRF/plane denial/session revocation and
restart; its Windows process restart is forced, not graceful-lifecycle evidence.
Reuse `scripts/smoke_r3_s2_q.py` for migrated HTTP/graceful restart and static
asset delivery. Record implementation self-review, preservation/docs/diff checks,
completion and a distinct final self-review before scoped commit/push/remote
verification. No SQL/transaction/schema changes; no new PostgreSQL gate applies.
Preserve working storage, unrelated edits and the existing demo.

### Evidence

Starting HEAD `0a21b2bff199a6b1a2deda8957f843aac98498a7`; initial worktree clean.
Pure extraction uses passing before/after characterizations, not a product-defect
reproduction. Sanitized runner `.resume/Scripts/python.exe
.pytest_cache/run_r4_s1_t4a.py <tag> <Python args>` clears inherited DEE config/
keys, ignores `.env`, blocks external GitHub and uses existing fake providers
and isolated stores. No arguments after the tag runs project `-m pytest -q
--tb=short`. Python logs use `.pytest_cache/r4-s1-t4a-<tag>.txt`; Node logs use
the same prefix. Baseline hashes cover 721 tracked files including working DB.

Pre-move `node --test scripts/test_ui_admin_users.js`: **40 passed, 0 failed,
0 skipped, 481.95ms**; post-move same command: **40 passed, 0 failed, 0 skipped,
451.93ms**, both exit 0. This includes the imported evaluation/API suite. New
characterizations verify detached callbacks retain their original receiver and
stable identity, separate component instances never share changes/handlers, and
a stale read after session loss cannot replace another instance's current rows.
Existing tests cover actual-row mapping, paging/filtering, double-submit,
confirmation/cancel, encoded IDs, response validation, draft preservation,
CSRF/policy/timeout/network/5xx errors, plane refusals and late-result guards.

Focused `focused -m pytest -q --tb=short tests/test_ui_handlers.py
tests/test_ui_mount.py tests/test_image_contents.py
tests/test_api_route_extraction.py tests/test_auth_api.py
tests/test_api_auth_gate.py tests/test_route_table_guard.py
tests/test_openapi_contract.py`: **110 passed, 1 warning, 59.86s**, exit 0
(65.94s runner). Includes all seven offline handler subprocesses, anonymous
delivery of every declared local script with exact bytes/JavaScript media type,
static confinement, image COPY/ignore contracts and the unchanged full ordered
102-operation API/auth/OpenAPI digest. Image contract tests are not an image build.

Actual Chrome `browser scripts/check_ui_admin_users_browser.py`: **29/29**,
exit 0, 39.83s runner, plus the shared harness's **1/1** app-contract check.
Migrated scratch composition (0029), captured sign-in, enabled/disabled actual
rows, empty/filter/page, input validation, double-click/create/persistence,
new-operator login, duplicate/CSRF/refusal/timeout/503 recovery, stale deletion,
cancel/confirm/session revocation, navigation/document reload, backend restart,
plane denials, expiry/self-deletion and no console exceptions pass. Fault
transports are synthetic; ordinary mutations/auth use real HTTP. Existing CDN
internet is required. Windows app/browser stop/restart is forced here; no
graceful-lifecycle claim from that script. No live provider or quality claim.

Migrated HTTP `journey scripts/smoke_r3_s2_q.py`: **46/46**, exit 0, 26.79s runner.
The existing journey now also checks anonymous declared-module delivery with
exact source bytes/media type and an unrelated-path refusal before and after
restart. Existing account/session, retention, metrics, signal, org/curation,
consent/ownership, restart/revocation and log privacy checks pass. Both scratch
server lifespans require graceful exit 0. Working DB/demo are untouched.

Static: `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**, pass;
`node --check frontend/api.js`, `frontend/support.js` and
`frontend/operator-accounts.js` pass. Review also runs `node --check` over both
changed Node behavior scripts, the binding checker and extracted inline logic
(`.pytest_cache/r4-s1-t4a-inline.js`). Tracked diff and new source/task whitespace
pass. Generated runtime, API client and Dockerfile are unchanged.

Project `-m compileall -q src/app/main.py tests/test_ui_mount.py
scripts/smoke_r3_s2_q.py` also passes. Docker COPY/ignore inspection includes the
new module; no Docker image build is claimed.

Implementation self-review: HEAD `0a21b2b` plus the HTML/new account module,
named static allowlist, existing Node/checker/HTTP entry points and mount test.
Specification review maps the bounded account behavior to pre/post Node,
focused/API, real Chrome and migrated HTTP checks. Correctness review traces
field initialization and receiver identity through the supplied-base subclass,
explicit helper capture, value precedence, shared lifecycle invalidation,
per-instance tokens, non-admin masking, request recovery and static confinement.
`review -I .pytest_cache/review_r4_s1_t4a.py`: exit 0, 0.90s runner. All 14
handler bodies and complete view inputs/mapping are text-identical; the rest of
the template/state/lifecycle/logic is identical after normalizing only the three
script/base/value composition edits. Main's AST changes only the named asset
allowlist. All shipped/test/inline JS parses and eleven reviewed source/contract
hashes are recorded. No blocking finding remains. This same-agent self-review
is not independent review. No SQL/transaction/migration changes or new PostgreSQL
gate apply. No dead operator-account handler or sample/live duplicate was found;
other screens' prototype material remains for their bounded children.

Preservation `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t4a.py`:
**709** unrelated tracked files, working DB and eleven reviewed hashes unchanged;
251 scoped local Markdown links/anchors and tracked/staged whitespace pass.
Full pytest `full-reviewed` (no extra runner args; project
`-m pytest -q --tb=short`): **3539 passed, 505 skipped, 127 warnings in
1066.39s (0:17:46)**, exit 0 (1077.03s runner).
Existing Starlette/httpx deprecation and SQLite expression-index reflection/
autogenerate warnings remain; optional/environment skips do not prove omitted
cases. Eleven reviewed source/contract hashes remain unchanged. Only documents
changed after the reviewed full run started.

All bounded A acceptance and required validation gates are complete. The
operator-account handlers and values have one live implementation in the new
plain script. Shared state/lifecycle, all other screen logic and API behavior
are preserved. No dead account handler/sample duplicate was removed because
none was found in this area. Only A completed; T4/F13/sprint/PI remain open.
Working storage/demo preserved. No B work or deployment started.

### Completion review and publication

After required validation and completion records, a distinct final same-agent
self-review examined HEAD `0a21b2b` plus the exact fourteen staged files: HTML/new
account module, static allowlist, existing Node/checker/HTTP entry points, mount
test, feature overview, handoff, roadmap, PI/evidence and active T4 parent record.
Specification review confirms the bounded extraction and all required validation,
unchanged ordered API/auth contract, one account implementation, child evidence
ownership and the B-only next pointer with T4/F13/sprint/PI still open.
Correctness review rechecks subclass field initialization (handlers capture the
receiver before shared state initializes, but read it only when called), explicit
helper capture, callback identity, value precedence, per-instance load/action
tokens, navigation/session/unmount invalidation, plane masking, no optimistic
mutation success, ambiguous-write recovery, static allowlisting and packaging.
The generated runtime/API client and all other screen logic remain unchanged.
No blocking finding remains. This final self-review is separate from the earlier
implementation review; no independent review is claimed.

`completion-review -I .pytest_cache/review_r4_s1_t4a.py`: exit 0, 0.69s runner;
all fourteen original handler bodies and complete view inputs/mapping match,
template/state/lifecycle and main AST comparisons pass, and all shipped/test/
inline JS syntax plus eleven source/contract hashes match. Final preservation
confirms **709** unrelated tracked files, working DB and eleven reviewed hashes
unchanged; **259** scoped local links/anchors and tracked/staged whitespace pass.
Only documentation changed after full pytest started. The exact staged scope
excludes secrets, working data and local artifacts. Tracking branch is
`origin/main`; its pre-publication remote matches starting HEAD. Publication
used G's existing per-command account selection. No B work or deployment.

Scoped task commit **`439ee10`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`0a21b2b` to `439ee10`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`439ee10695dcabbd984531d51196eb2be3488e33`**. Working tree was clean.

This two-file documentation-only confirmation records verified publication in
the handoff and this evidence section. Separate final same-agent self-review
against `439ee10` checks the exact prose diff, actual remote evidence, open T4
parent and B-only next pointer; no blocking finding remains. Scoped links,
whitespace and preservation pass. Application/test/harness code remains at the
full pytest/HTTP/Chrome validated state; no application tests are rerun for prose.
The final response reports the verified remote SHA after this confirmation's
commit/push. No B work, working-data change, demo restart or deployment occurred.

### Handoff

Exact next: **R4-S1-T4B - Extract organization-administration UI handlers and
view values**, not started. Define its contract in the existing T4 record before
implementation in the next session. Stop after A publication.

## <a id="r4-s1-t4b"></a>R4-S1-T4B - Extract organization-administration UI logic

Status: done and published (2026-10-22). Parent:
[T4](#r4-s1-t4). Prerequisite: [T4A](#r4-s1-t4a), done/published.

### Contract and acceptance

Move the organization-administration handlers and view-value mapping from
`frontend/Veritas.dc.html` into `frontend/organization-admin.js`, using A's plain
script factory/subclass seam and explicit API/date/error/timeout/chip helpers.
Compose its values at their existing precedence. Keep shared state, navigation,
session-loss/unmount invalidation, template, API client and generated runtime
unchanged. Add only the named module to public static delivery and load it in
the existing offline component and binding entry points.

Acceptance: actual organization rows, loading/empty/error, inspection, local
filter/page, create and saved reliability behave unchanged. Names and finite
nonnegative weights are validated; wrong planes refuse reads/mutations and
privileged values. Rotation/offboarding require target-scoped confirmation and
block duplicate mutations. One-time keys start concealed and clear on selection,
refresh, navigation, session loss and reload. Malformed responses and CSRF,
policy, timeout/network/5xx failures preserve recovery advice and drafts without
automatic replay or optimistic success. Late reads/mutations cannot alter a new
screen/account or unmounted component. Detached callbacks retain their receiver;
separate component instances share no mutable state, pending requests or keys.
Separate factory compositions retain their supplied helpers. No duplicate
sample/live organization implementation remains. All UI bindings and
the ordered API/auth contract remain intact.

### Required validation

Extend `scripts/test_ui_admin_orgs.js` with before/after detached-callback and
instance-isolation characterizations, preserving its existing error/lifecycle
coverage. Extend `tests/test_ui_mount.py` and the existing
`scripts/smoke_r3_s2_q.py` module-delivery checks. Run focused UI/mount/image,
organization/auth and ordered API-contract pytest, full offline pytest,
bindings and JS syntax including extracted inline logic. Run actual Chrome via
`scripts/check_ui_admin_orgs_browser.py` for persisted org/key/reliability,
confirmation, errors, reload/restart and session loss. Its Windows stop/restart
is forced; use `scripts/smoke_r3_s2_q.py` for migrated HTTP and graceful restart.
Record implementation self-review, preservation/docs checks, completion and a
distinct final self-review before scoped commit/push/remote verification.
No schema/transaction/concurrency changes; no new PostgreSQL gate applies.
Preserve working storage, unrelated work and the existing demo. Stop after B;
next child C will extract curation handlers/view values with a contract defined
in its own session. T4/F13/sprint/PI remain open.

### Evidence

Starting HEAD `b3ccfd15392dd8fd57e5c64b5392cd5529db71ac`; initial worktree clean.
Pure extraction uses passing before/after characterizations, not a product-defect
reproduction. Sanitized runner `.resume/Scripts/python.exe
.pytest_cache/run_r4_s1_t4b.py <tag> <Python args>` clears inherited DEE config/
keys, ignores `.env`, blocks external GitHub and uses existing fake providers
and isolated stores. No arguments after the tag runs project `-m pytest -q
--tb=short`. Python logs use `.pytest_cache/r4-s1-t4b-<tag>.txt`. Baseline hashes
cover 723 tracked files including working DB; these local artifacts stay ignored.

Pre-move `node --test scripts/test_ui_admin_orgs.js`: **39 passed, 0 failed,
0 skipped, 516.00ms**; post-move same command: **39 passed, 0 failed,
0 skipped, 568.71ms**, exit 0. Final expanded suite adds network-recovery and
same-composed-class instance checks: **41 passed, 0 failed, 0 skipped, 865.71ms**.
Replay against original HEAD HTML using a process-only read override,
`node --require ./.pytest_cache/baseline_r4_s1_t4b.cjs --test
scripts/test_ui_admin_orgs.js`: **41 passed, 0 failed, 0 skipped, 1729.32ms**,
exit 0. No working source is replaced for that comparison. Each count includes
the imported evaluation/API suite. New checks cover detached callback receiver
and stable identity, saved zero reliability, distinct factories and same-class
instances, per-instance requests/keys, stale read/create after account loss,
privileged-value masking and uncertain network recovery. Existing tests cover
actual list/page/filter/selection, create, concealed key/reveal/clearing,
confirmation/cancel/target changes, duplicate mutation, input validation,
CSRF/policy/conflict/timeout/503, malformed success and navigation/unmount guards.

Focused `focused -m pytest -q --tb=short tests/test_ui_handlers.py
tests/test_ui_mount.py tests/test_image_contents.py
tests/test_api_route_extraction.py tests/test_ledger_api.py tests/test_auth_api.py
tests/test_api_auth_gate.py tests/test_route_table_guard.py
tests/test_openapi_contract.py`: **134 passed, 1 warning, 67.35s**, exit 0
(78.86s runner). All seven offline handler subprocesses, anonymous declared
module delivery with exact source bytes/media type, static confinement, image
COPY/ignore contracts and unchanged ordered 102-operation API/auth/OpenAPI
contract pass. Final expanded Node checks also run separately above and in the
full suite. Image contract checks are not an image build.

Actual Chrome `browser scripts/check_ui_admin_orgs_browser.py`: **28/28**,
exit 0, 45.25s runner, plus the shared harness's **1/1** app-contract check.
Migrated scratch SQLite (0029), captured sign-in, actual empty/saved rows,
double-click/create, concealed/revealed one-time key without URL/storage
retention, duplicate-name/CSRF/refusal/timeout/503 recovery, reliability,
rotation/cancel/key revocation, paging/filter, offboarding and other-tenant
preservation, plane denials, document/backend reload, session expiry and no
console exceptions pass. Ordinary mutations/auth use real HTTP; injected faults
are synthetic. Existing CDN internet is required. Windows app/browser stop and
restart here are forced; this is not graceful-lifecycle evidence. No live
provider or measured-quality claim.

Migrated HTTP `journey scripts/smoke_r3_s2_q.py`: **48/48**, exit 0, 39.14s runner.
Anonymous module delivery now covers both account and organization modules,
exact bytes/media type and unrelated-path refusal before/after restart.
Existing account/session, retention, metrics, signal, organization/curation,
consent/ownership, restart/revocation and log-privacy checks pass. Both scratch
server lifespans require graceful exit 0. Working DB/demo are untouched.

Static: `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**, pass;
`node --check frontend/api.js`, `frontend/support.js` and
`frontend/organization-admin.js` pass. Review also checks account module, both
changed Node behavior scripts, binding checker and extracted inline logic
(`.pytest_cache/r4-s1-t4b-inline.js`). Tracked diff whitespace passes. Generated
runtime, API client and Dockerfile are unchanged; COPY/ignore includes the new
module. No Docker image build is claimed.

Implementation self-review: HEAD `b3ccfd1` plus HTML/new organization module,
named static allowlist, Node/checker/HTTP entry points and mount test.
Specification review maps the bounded organization behavior to baseline/final
Node, focused API/contract, actual Chrome and migrated HTTP checks. Correctness
review traces composed-class field initialization and receiver identity,
explicit helper capture, value precedence, per-instance read/action tokens,
navigation/session/unmount cleanup, non-admin row/key masking, one-time key
clearing, target-scoped confirmation, no automatic mutation replay and static
confinement. `review -I .pytest_cache/review_r4_s1_t4b.py`: exit 0, 2.66s runner.
All **20** handler bodies and complete view inputs/mapping are text-identical;
template/state/lifecycle and other logic are identical after normalizing the
three script/base/value composition edits. Main's AST changes only the named
asset allowlist. All shipped/test/inline JS parses and twelve reviewed source/
contract hashes are recorded. The first local comparison attempt had an
incorrect expected handler count (21); corrected to the actual 20, with all
source comparisons unchanged. No blocking finding remains. This same-agent
self-review is not independent review. No SQL/transaction/schema changes or new
PostgreSQL gate apply. No dead organization handler or sample/live duplicate was
found in this bounded area; other screens remain for later children.

Low-severity documentation finding, this contract's instance-isolation wording:
it initially implied helper references differ for every instance, although
instances of the same composed class intentionally use the supplied helpers.
That overstates the contract. Wording now distinguishes mutable state/pending
requests/keys from separate factory helper capture; the passing same-class and
separate-composition Node checks demonstrate those actual boundaries. No
application behavior changed for this clarification.

Project `compile -m compileall -q src/app/main.py tests/test_ui_mount.py
scripts/smoke_r3_s2_q.py`: exit 0, 0.46s runner. Preservation
`.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t4b.py`: **710** unrelated
tracked files, working DB and **12** reviewed hashes unchanged; **259** scoped
local Markdown links/anchors and tracked/staged/source whitespace pass.

Full pytest `full-reviewed` (no extra runner arguments; project `-m pytest -q
--tb=short`): **3539 passed, 505 skipped, 127 warnings in 1309.65s (0:21:49)**,
exit 0 (1325.16s runner). Existing Starlette/httpx deprecation
and SQLite expression-index reflection/autogenerate warnings remain. Optional
and environment skips do not prove omitted cases. Reviewed source/contract
hashes remain unchanged; only documentation changed during the full run.

All bounded B acceptance and required validation gates are complete. Organization
handlers and values have one implementation in the new plain script; existing
shared state/lifecycle/template and API/auth behavior are preserved. No dead org
handler/sample duplicate was found to remove in this area. B alone completed
this session; T4/F13/sprint/PI remain open. Working storage/demo are preserved.
No C implementation or deployment started.

### Completion review and publication

After required validation and completion records, a distinct final same-agent
self-review examined HEAD `b3ccfd1` plus the exact fourteen staged files: HTML/new
organization module, named static allowlist, existing Node/checker/HTTP entry
points, mount test, feature overview, handoff, roadmap, PI/evidence and active T4
parent record. Specification review confirms the bounded extraction, required
validation, unchanged ordered API/auth contract, single organization
implementation, child evidence ownership and C-only next pointer, with
T4/F13/sprint/PI still open.

Correctness review rechecks composed-class field initialization (bound handlers
capture their receiver before shared state initializes but read it only when
called), supplied helper capture, view precedence, per-instance read/action
tokens, navigation/session/unmount invalidation, non-admin masking, concealed
one-time keys and clearing, deliberate target-scoped confirmation, uncertain
write recovery without replay, static confinement and packaging. Generated
runtime/API client and other screen logic remain unchanged. No blocking finding
remains. This final self-review is separate from implementation review; no
independent review is claimed.

`completion-review -I .pytest_cache/review_r4_s1_t4b.py`: exit 0, 1.24s runner;
all twenty original handler bodies and complete view inputs/mapping match,
template/state/lifecycle and main AST comparisons pass, and shipped/test/inline
JS syntax plus twelve reviewed source/contract hashes match. Final preservation
confirms **710** unrelated tracked files, working DB and **12** reviewed hashes
unchanged; **265** scoped local links/anchors and tracked/staged whitespace pass.
Only documentation changed during/after full pytest. Exact staged scope excludes
secrets, working data and local artifacts. Tracking branch is `origin/main`;
its pre-publication remote matches starting HEAD. Publication uses G's existing
per-command account selection. No C work, demo restart or deployment started.

Scoped task commit **`d7e7500`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`b3ccfd1` to `d7e7500`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`d7e7500a12a3c62fb0f38187de24771eab12c805`**. Working tree was clean.

This two-file documentation-only confirmation records verified publication in
the handoff and this evidence section. Separate final same-agent self-review
against `d7e7500` checks the exact prose diff, actual remote evidence, open T4
parent and C-only next pointer; no blocking finding remains. Scoped links,
whitespace and preservation pass. Application/test/harness code remains at the
full pytest/HTTP/Chrome validated state; no application tests are rerun for prose.
The final response reports the verified remote SHA after this confirmation's
commit/push. No C work, working-data change, demo restart or deployment occurred.

### Handoff

Exact next: **R4-S1-T4C - Extract curation UI handlers and view values**, not
started. Define its bounded contract in the existing T4 record before
implementation in the next session. Stop after B publication.

## <a id="r4-s1-t4c"></a>R4-S1-T4C - Extract curation UI logic

Status: done and published (2026-10-22). Parent:
[T4](#r4-s1-t4). Prerequisite: [T4B](#r4-s1-t4b), done/published.

### Contract and acceptance

Move curation handlers and the curation-only view mapping from
`frontend/Veritas.dc.html` into `frontend/curation.js` using the existing
plain-script factory/subclass seam. Pass API, timeout, error and idle-resource
helpers explicitly and compose values at their existing precedence. Keep shared
state, navigation, session-loss/unmount invalidation, template, API client,
generated runtime and backend behavior unchanged. Add only this named module to
public static delivery and load it in the existing offline execution entry points.

Acceptance: the operator sees actual pending terms/counts/source types and
cursor pages, with correct loading/empty/error states. Review starts with a blank
alias, and map/create/ignore sends the exact loaded revision only after an
explicit action. Stale/missing snapshots clear drafts and require selection of
the refreshed term. Ambiguous writes and malformed receipts require a successful
read before another explicit decision; never replay automatically or advertise
optimistic success. Known CSRF/policy/conflict/validation refusals retain drafts
where appropriate. Wrong planes and other screens cannot fetch/mutate or render
raw terms, private errors or editor drafts. Navigation, session loss and unmount
invalidate late reads/decisions. Detached callbacks keep their receiver and
identity; component instances have separate mutable state and pending tokens,
and separate factory compositions retain supplied helpers. All shipped bindings
and the ordered API/auth contract remain intact. Remove only proven dead or
duplicate curation code in this bounded area.

### Required validation

Extend `scripts/test_ui_curation.js` with before/after detached-callback and
instance-isolation characterizations. Retain its revision/receipt/error/lifecycle
coverage. Extend existing mount and migrated HTTP module-delivery checks. Run
focused UI/mount/image, curation/revision/auth and ordered API-contract pytest;
full offline pytest; bindings and JS syntax including extracted inline logic.
Reuse `scripts/smoke_curation_activation.py --browser` for migrated scratch HTTP,
real Chrome review/reload/error/auth recovery and graceful app restart. Existing
`scripts/smoke_r3_s2_q.py` covers module delivery and combined operator restart.
Record implementation self-review, preservation/docs checks, completion and a
distinct final self-review before scoped commit/push/remote verification. No
schema/transaction/concurrency changes; no new PostgreSQL gate applies. Preserve
working storage, unrelated work and the existing demo. Stop after C; next child
D will extract evaluation/report UI logic under a contract defined next session.
T4/F13/sprint/PI remain open.

### Evidence

Starting HEAD `036e1e1f4030e630a69b2b1f7ec1f8f654a6e300`; initial worktree clean.
This pure extraction uses passing before/after characterizations, not a
product-defect reproduction. Sanitized runner `.resume/Scripts/python.exe
.pytest_cache/run_r4_s1_t4c.py <tag> <Python args>` clears inherited DEE config/
keys, ignores `.env`, blocks external GitHub and uses existing fake providers
and isolated stores. No arguments after the tag runs project `-m pytest -q
--tb=short`; logs use `.pytest_cache/r4-s1-t4c-<tag>.txt`. Baseline hashes cover
724 tracked files including the working DB; local artifacts stay ignored.

Pre-move `node --test scripts/test_ui_curation.js`: **45 passed, 0 failed,
0 skipped, 627.11ms**; post-move same command: **45 passed, 0 failed,
0 skipped, 388.92ms**, both exit 0. Counts include the imported evaluation/API
suite. New characterizations exercise detached callback receivers and stable
identity, separate factory helpers/drafts/decisions, and same-class instances
with concurrent decisions, account-loss invalidation and another instance's
pending editor. Existing checks cover map/create/ignore with exact revisions
and blank aliases, cursor encoding and overlap/revision changes, malformed pages
and receipts, known/ambiguous refusals, successful read before explicit retry,
no automatic replay, duplicate-submit/racing edits, stale/missing snapshots,
wrong-plane masking and navigation/session/unmount guards.

Focused `focused -m pytest -q --tb=short tests/test_ui_handlers.py
tests/test_ui_mount.py tests/test_image_contents.py
tests/test_api_route_extraction.py tests/test_curation_api.py
tests/test_curation_review_revisions.py tests/test_auth_api.py
tests/test_api_auth_gate.py tests/test_route_table_guard.py
tests/test_openapi_contract.py`: **131 passed, 17 skipped, 15 warnings in
75.17s (0:01:15)**, exit 0 (82.39s runner). Includes all seven offline handler
subprocesses, anonymous module delivery with exact bytes/media type, static
confinement, image COPY/ignore contracts and unchanged ordered 102-operation
API/auth/OpenAPI contract. Curation revision coverage retains its isolated
stores and ownership/expiry/erasure boundaries; optional environment skips do
not prove PostgreSQL or omitted cases. Image contract checks are not a build.

Migrated HTTP plus actual Chrome `browser-journey
scripts/smoke_curation_activation.py --browser`: **53/53 combined checks**,
exit 0, 57.75s runner. Scratch SQLite migrates to 0029; real captured sign-in,
actual queue, explicit map/create/ignore, revision binding, persisted approved
alias/operator and subsequent normalization pass. Actual Chrome covers blank
alias, validation/conflict, reload, synthetic network/timeout/503 and failed
read recovery, navigation/late success, 20/25-row pagination, refused/malformed
reads, actual stale expiry/erasure/reviewer revocation, org/candidate denials,
raw-state clearing and no console exceptions. HTTP covers capture/ownership,
erasure, raw-free receipts, CSRF, legacy/expired-state handling and
maintenance. Three scratch app lifespans exit gracefully; subsequent restart
preserves Chrome-approved decisions and normalization. Browser transport faults
and GitHub evidence are synthetic; ordinary auth/decisions use real HTTP.
Chrome requires existing CDN internet. No live-provider or measured-quality
claim. Working storage and the existing demo are untouched.

Combined operator HTTP `operator-journey scripts/smoke_r3_s2_q.py`: **50/50**,
exit 0, 30.79s runner. Anonymous module delivery now includes curation alongside
the account/organization modules, exact bytes/media type and unrelated-path
refusal before/after restart. Existing account/session, retention, metrics,
signal, organization/curation, consent/ownership, restart/revocation and
log-privacy checks pass. Both scratch app lifespans require graceful exit 0.

Static: `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**, pass.
`review -I .pytest_cache/review_r4_s1_t4c.py`: exit 0, 2.80s runner; `node
--check` covers API client, generated runtime, account/organization/curation
modules, changed Node behavior scripts, binding checker and extracted inline
logic (`.pytest_cache/r4-s1-t4c-inline.js`). Project `compile -m compileall -q
src/app/main.py tests/test_ui_mount.py scripts/smoke_r3_s2_q.py`: exit 0,
0.32s runner. Existing frontend COPY/ignore includes the named module;
Dockerfile, generated runtime and API client are unchanged. No image build is
claimed. Tracked/source whitespace passes.

Implementation self-review: HEAD `036e1e1` plus HTML/new curation module, named
static allowlist, Node/checker/HTTP entry points and mount test. Specification
review maps the bounded curation contract to baseline/final Node, focused API/
revision/route checks, actual Chrome and migrated HTTP. Correctness review
traces composed-class initialization, receiver identity, supplied helper/IDLE
capture, view precedence, review-revision binding and raw-free receipts,
per-instance read/review tokens, draft recovery, stale/missing snapshots,
navigation/session/unmount cleanup, non-admin/off-screen masking, no optimistic
decision success or automatic replay, static confinement and packaging.
All **16** handler bodies and complete view inputs/mapping are text-identical;
template/state/lifecycle and other logic are identical after normalizing the
script/base/value composition edits. Main's AST changes only the named static
allowlist entry. Thirteen reviewed source/contract hashes are recorded. No
blocking finding remains. This same-agent self-review is not independent
review. No schema/transaction/concurrency changes or new PostgreSQL gate apply.
No dead handler or sample/live curation duplicate was found to remove in this
bounded area; other screens remain for later children.

Preservation `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t4c.py`:
**711** unrelated tracked files, working DB and **13** reviewed hashes unchanged;
**265** scoped local Markdown links/anchors and tracked/staged/source whitespace
pass. Tracking branch is `origin/main`; its pre-publication remote matches
starting HEAD.

Full pytest `full-reviewed` (no extra runner arguments; project `-m pytest -q
--tb=short`): **3539 passed, 505 skipped, 127 warnings in 953.17s (0:15:53)**,
exit 0 (966.32s runner). Existing Starlette/httpx deprecation
and SQLite expression-index reflection/autogenerate warnings remain. Optional
and environment skips do not prove omitted cases. Thirteen reviewed source/
contract hashes remain unchanged; only documentation changed during the run.

All bounded C acceptance and required validation gates are complete. Curation
handlers/view values have one implementation in the new plain script. Shared
state/lifecycle/template and API/auth behavior remain unchanged. No dead curation
handler or sample/live duplicate was found to remove. C alone completed this
session; T4/F13/sprint/PI remain open. Working storage/demo are preserved.
No D implementation or deployment started.

### Completion review and publication

After required validation and completion records, a distinct final same-agent
self-review examined HEAD `036e1e1` plus the exact fourteen staged files: HTML/new
curation module, named static allowlist, existing Node/checker/HTTP entry points,
mount test, feature overview, handoff, roadmap, PI/evidence and active T4 parent
record. Specification review confirms the bounded extraction, required
validation, unchanged ordered API/auth contract, single curation implementation,
child evidence ownership and D-only next pointer, with T4/F13/sprint/PI open.

Correctness review rechecks composed-class field initialization (bound handlers
capture their receiver before shared state initializes but read it only when
called), supplied API/error/timeout/IDLE capture, view precedence, exact revision
binding, receipt allowlisting, explicit blank-alias review, per-instance load/
decision tokens, stale/missing snapshots, uncertain writes without replay,
read recovery before explicit retry, navigation/session/unmount cleanup,
non-admin/off-screen masking, static confinement and packaging. Generated
runtime/API client and other screen logic remain unchanged. No blocking finding
remains. This final self-review is separate from implementation review; no
independent review is claimed.

`completion-review -I .pytest_cache/review_r4_s1_t4c.py`: exit 0, 1.28s runner;
all sixteen original handler bodies and complete view inputs/mapping match,
template/state/lifecycle and main AST comparisons pass, and shipped/test/inline
JS syntax plus thirteen reviewed source/contract hashes match. Final preservation
confirms **711** unrelated tracked files, working DB and **13** reviewed hashes
unchanged; **271** scoped local links/anchors and tracked/staged whitespace pass.
Only documentation changed during/after full pytest. Exact staged scope excludes
secrets, working data and local artifacts. Tracking branch is `origin/main`;
its pre-publication remote matches starting HEAD. Publication uses G's existing
per-command account selection. No D work, demo restart or deployment started.

Scoped task commit **`5221f9f`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`036e1e1` to `5221f9f`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`5221f9f8f215933d9af7bd3bad07c2e795631e3a`**. Working tree was clean.

This two-file documentation-only confirmation records verified publication in
the handoff and this evidence section. Separate final same-agent self-review
against `5221f9f` checks the exact prose diff, actual remote evidence, open T4
parent and D-only next pointer; no blocking finding remains. Scoped links,
whitespace and preservation pass. Application/test/harness code remains at the
full pytest/HTTP/Chrome validated state; no application tests are rerun for prose.
The final response reports the verified remote SHA after this confirmation's
commit/push. No D work, working-data change, demo restart or deployment occurred.

### Handoff

Exact next: **R4-S1-T4D - Extract evaluation/report UI handlers and view values**,
not started. Define its bounded contract in the existing T4 record before
implementation in the next session. Stop after C publication.

## <a id="r4-s1-t4d"></a>R4-S1-T4D - Extract evaluation/report UI logic

Status: done and published (2026-10-22). Parent:
[T4](#r4-s1-t4). Prerequisite: [T4C](#r4-s1-t4c), done/published.

### Contract and acceptance

Move Instant check inputs/submission, report loading/navigation, feedback and
probe-copy handlers plus evaluation/report/feedback view mappings from
`frontend/Veritas.dc.html` to `frontend/evaluation-report.js`. Reuse the plain
script factory/subclass seam, passing existing API, resource, display, browser
and timer helpers explicitly. Keep shared state, navigation/session/unmount
invalidation, PDF reading, template, generated runtime, API client and backend
behavior unchanged. Compose evaluation values before live overrides and report
values at their existing screening-map position. Add only the named module to
public static delivery and existing offline execution entry points. The moved
probe cache remains per-instance; shared unmount still clears its timer.

Acceptance: organization text/PDF evaluation uses its existing owned route;
operator evaluation uses the ad-hoc route. Invalid/candidate input refuses;
duplicate clicks produce one request. Saved report IDs, reload/hash restoration,
report read retries and feedback reads/writes retain route/ownership/CSRF
boundaries. Errors preserve drafts and existing uncertain-write advice without
automatic replay or fabricated success. Navigation keeps completed evaluations
available without changing the new screen; session loss/unmount invalidate late
results, and feedback cannot clear another report/account's notes or token.
Detached callbacks retain receiver/identity; same-class instances have separate
mutable state, pending requests and report/probe/feedback caches. Report mapping
preserves factual/style separation, historical v1 labels/scores, missing and
unsupported assessment states, withheld match identities, candidate clarification
and advisory/human-review wording. Probe-copy state and feedback history retain
their existing behavior. All bindings and the ordered API/auth contract remain
intact. Remove only proven dead/duplicate code in this bounded area.

### Required validation

Extend `scripts/test_ui_evaluate.js` with before/after callback, same-class
isolation and report-semantics characterizations. Keep its input/PDF/error/
session/retry tests and run all existing offline handlers. Extend existing
mount and migrated HTTP module-delivery checks. Run focused UI/image/mount,
evaluation/report/outcome/auth and ordered API-contract pytest; full offline
pytest; bindings and JS syntax including extracted inline logic. Actual Chrome:
`scripts/check_ui_evaluate_browser.py` and
`scripts/check_ui_review_context_browser.py` cover evaluation/feedback and
advisory/style/historical report rendering. Reuse `scripts/smoke_r3_s1_q.py`
for migrated evaluation/report/outcome/restart (Windows stop is forced), and
`scripts/smoke_r4_s1_t3d.py` for module serving, scoped report/feedback persistence
and graceful restart. Browser fixtures/transport faults prove mechanics, not
live providers or accuracy. Record implementation self-review, preservation,
completion and distinct final self-review before scoped commit/push/remote
verification. No schema/transaction/concurrency changes; no new PostgreSQL gate
applies. Preserve working storage, unrelated work and the existing demo. Stop
after D; next E will extract screening handlers/view values with its contract
defined next session. T4/F13/sprint/PI remain open.

### Evidence

Starting HEAD `890efc9700c38470caa082cc5f0bcc096bdc293f`; initial worktree clean.
This pure extraction uses passing before/after characterizations, not a
product-defect reproduction. Sanitized runner `.resume/Scripts/python.exe
.pytest_cache/run_r4_s1_t4d.py <tag> <Python args>` clears inherited DEE config/
keys, ignores `.env`, blocks external GitHub and uses existing fake providers
and isolated stores. Omitted args after the tag run project `-m pytest -q
--tb=short`; logs use `.pytest_cache/r4-s1-t4d-<tag>.txt`. Baseline hashes cover
725 tracked files including the working DB; local artifacts stay ignored.

Pre-move `node --test scripts/test_ui_evaluate.js`: **27 passed, 0 failed,
0 skipped, 396.55ms**; post-move same command: **27 passed, 0 failed,
0 skipped, 399.16ms**, both exit 0. New characterizations exercise detached
evaluation/input/feedback callbacks and stable identity, separate factory state,
same-class pending evaluations and feedback, account-loss invalidation,
per-instance probe/feedback caches, report v2/v1/unknown/missing semantics,
withheld match identities and probe-copy notice state/timer cleanup. This is
not OS clipboard-delivery evidence. Existing tests retain organization/operator
routes, PDF/text replacement, malformed success, input/CSRF/policy/timeout/
network/503 recovery, report read retry, hash reload, navigation, session loss,
unmount and late feedback/401 guards. All seven offline handler subprocesses
reuse this actual extracted composition.

Focused `focused -m pytest -q --tb=short tests/test_ui_handlers.py
tests/test_ui_mount.py tests/test_image_contents.py
tests/test_api_route_extraction.py tests/test_screening_outcome_api.py
tests/test_report_outcomes.py tests/test_report_response_erasure.py
tests/test_auth_api.py tests/test_api_auth_gate.py tests/test_route_table_guard.py
tests/test_openapi_contract.py`: **144 passed, 2 skipped, 1 warning in 39.47s**,
exit 0 (47.18s runner). Includes actual offline handlers, anonymous module bytes/
JavaScript media type, static confinement, image COPY/ignore, report/outcome/
erasure boundaries and unchanged ordered 102-operation API/auth/OpenAPI contract.
Environment skips do not prove PostgreSQL or omitted cases; image contract
checks are not an image build.

Actual Chrome `evaluation-browser scripts/check_ui_evaluate_browser.py`:
**38/38**, exit 0, 33.06s runner, plus shared harness **1/1** app-contract check.
Migrated scratch SQLite (0029) and captured sign-in prove organization text/PDF,
duplicate clicks, real report summary/ID, factual/style advisory context,
cross-tenant refusal, saved feedback and lost acknowledgement followed by
read-only recovery, document reload without resubmission, unreadable PDF retry,
domain selection, navigation/late results, erasure/404, session expiry and stale
401 after operator login. Operator ad-hoc/candidate-free report and feedback,
candidate refusal, captured contact, portal consent/access/erasure and no console
exceptions also pass. Transport timeout/network/503/lost acknowledgements are
synthetic; ordinary auth/mutations use real HTTP. Existing CDN internet is
required. Windows process stop is forced, not graceful-lifecycle evidence.

Actual Chrome `review-browser scripts/check_ui_review_context_browser.py`:
**28/28**, exit 0, 28.30s runner. Real reports with fake providers prove paired
plain/polished factual context, separate unverified style observations, timeline
clarification, content matches without identities, insufficient/missing/unknown
assessment refusal, original historical v1 score/summary without JSON rewrite,
authorized report reload, real missing-report error/recovery and no console
exceptions. Existing employer board/role/compensation empty/saved/error flows
also pass. Windows stop is forced. Neither browser run validates live providers
or measured accuracy; working storage/demo are untouched.

Migrated HTTP `evaluation-journey scripts/smoke_r3_s1_q.py`: **20/20**, exit 0,
25.05s runner. Organization and operator evaluation/report/outcomes, CSRF/plane/
ownership refusals, named human provenance, captured contact and exact saved
report/judgement restart checks pass. Windows shutdown here is forced.

Migrated HTTP `graceful-journey scripts/smoke_r4_s1_t3d.py`: **18/18**, exit 0,
27.33s runner, plus reused screening HTTP contract **31/31** (HTTP simulation,
not Chrome). Anonymous named-module delivery checks declaration, exact bytes,
JavaScript media type and unrelated-path refusal before/after restart. Existing
scoped report/feedback, private operator notes, named reviewer, ownership/CSRF,
batch/queue/summary/advisory and exact persisted report/outcomes pass. Both
migrated scratch app lifespans require graceful exit 0 with shared SQL disposal.

Static: `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**, pass.
`review -I .pytest_cache/review_r4_s1_t4d.py`: exit 0, 1.86s runner; `node
--check` covers API client, generated runtime, account/organization/curation/
evaluation-report modules, existing changed Node behavior/checker scripts and
extracted inline logic (`.pytest_cache/r4-s1-t4d-inline.js`). Project `compile
-m compileall -q src/app/main.py tests/test_ui_mount.py
scripts/smoke_r4_s1_t3d.py`: exit 0, 0.21s runner. Existing frontend COPY/ignore
includes the named module; Dockerfile, generated runtime and API client are
unchanged. No image build is claimed. Tracked/source whitespace passes.

Implementation self-review: HEAD `890efc9` plus HTML/new evaluation-report
module, named static allowlist, existing Node/checker/HTTP entry points and mount
test. Specification review maps the bounded contract to before/after Node,
focused API/route/erasure checks, both actual Chrome journeys and migrated HTTP.
Correctness review traces composed-class field initialization, receiver identity,
explicit API/resource/display/browser/timer capture, evaluation/live/report-map
precedence, per-instance probe/feedback caches and request tokens, route/URL
encoding, draft recovery, no automatic replay, navigation/session/unmount
invalidation, factual/style and scorer-version handling, identity withholding,
static confinement and packaging. All **16** handler bodies, probe-cache field,
evaluation view mapping and report inputs/mapping are text-identical. Shared
state/lifecycle/PDF reader and other logic are identical after normalizing only
the script/base/view composition edits. Main's AST changes only the named static
allowlist entry. **16** reviewed source/harness/contract hashes are recorded.
No blocking finding remains. This same-agent self-review is not independent
review. No schema/transaction/concurrency changes or new PostgreSQL gate apply.
No dead handler or duplicate sample/live evaluation/report source was found to
remove in this bounded area; unrelated prototype screens remain for later work.

Preservation `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t4d.py`:
**713** unrelated tracked files, working DB and **16** reviewed hashes unchanged;
scoped local Markdown links/anchors and tracked/staged/source whitespace pass.
Tracking branch is `origin/main`; its pre-publication remote matches starting
HEAD.

Full pytest `full-reviewed` (no extra runner arguments; project `-m pytest -q
--tb=short`): **3539 passed, 505 skipped, 127 warnings in 741.75s (0:12:21)**,
exit 0 (750.79s runner). Existing Starlette/httpx deprecation
and SQLite expression-index reflection/autogenerate warnings remain. Optional
and environment skips do not prove omitted cases. Sixteen reviewed source/
harness/contract hashes remain unchanged; only documentation changed during
the run.

All bounded D acceptance and required validation gates are complete. Evaluation,
report, feedback and probe-copy handlers plus their mappings have one
implementation in the new plain script. Shared state/lifecycle/PDF reader,
template and API/auth behavior remain unchanged. No dead handler or sample/live
duplicate was found to remove. D alone completed this session; T4/F13/sprint/PI
remain open. Working storage/demo are preserved. No E implementation or
deployment started.

### Completion review and publication

After required validation and completion records, a distinct final same-agent
self-review examined HEAD `890efc9` plus the exact thirteen staged files:
HTML/new evaluation-report module, named static allowlist, existing Node/checker/
HTTP entry points, mount test, feature overview, handoff, roadmap, PI/evidence
and active T4 parent record. Specification review confirms the bounded
extraction, required validation, unchanged ordered API/auth contract, single
evaluation/report implementation, child evidence ownership and E-only next
pointer, with T4/F13/sprint/PI still open.

Correctness review rechecks composed-class initialization (bound handlers and
the probe cache initialize before shared state, but handlers read state only
when called), explicit API/resource/display/navigator/timer capture, evaluation
values before live overrides, report values at the original screening position,
per-instance caches and request tokens, report URL/route encoding, PDF helper
reuse, feedback draft recovery, uncertain writes without automatic replay,
navigation/session/unmount invalidation, advisory/style separation, preserved
historical scores, missing/unsupported assessment refusal, withheld match
identities, static confinement and packaging. Generated runtime/API client and
other screen logic remain unchanged. No blocking finding remains. This final
self-review is separate from implementation review; no independent review is
claimed.

`completion-review -I .pytest_cache/review_r4_s1_t4d.py`: exit 0, 1.76s runner;
all sixteen original handler bodies, probe-cache field and complete evaluation/
report inputs/mappings match. Shared template/state/lifecycle/PDF reader and
main AST comparisons pass; shipped/test/inline JS syntax and sixteen reviewed
source/harness/contract hashes match. Final preservation confirms **713**
unrelated tracked files, working DB and **16** reviewed hashes unchanged;
**277** scoped local links/anchors and tracked/staged whitespace pass. Only
documentation changed during/after full pytest. Exact staged scope excludes
secrets, working data and local artifacts. Tracking branch is `origin/main`;
its pre-publication remote matches starting HEAD. Publication uses G's existing
per-command account selection. No E work, demo restart or deployment started.

Scoped task commit **`06b45c5`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`890efc9` to `06b45c5`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`06b45c50afa67d590cb6ab82428fb6d54d21cb0e`**. Working tree was clean.

This two-file documentation-only confirmation records verified publication in
the handoff and this evidence section. Separate final same-agent self-review
against `06b45c5` checks the exact prose diff, actual remote evidence, open T4
parent and E-only next pointer; no blocking finding remains. Scoped links,
whitespace and preservation pass. Application/test/harness code remains at the
full pytest/HTTP/Chrome validated state; no application tests are rerun for prose.
The final response reports the verified remote SHA after this confirmation's
commit/push. No E work, working-data change, demo restart or deployment occurred.

### Handoff

Exact next: **R4-S1-T4E - Extract screening UI handlers and view values**, not
started. Define its bounded contract in the existing T4 record before
implementation in the next session. Stop after D publication.

## <a id="r4-s1-t4e"></a>R4-S1-T4E - Extract screening UI handlers and view values

Status: done and published (2026-10-23). Parent:
[T4](#r4-s1-t4). Prerequisite: [D](#r4-s1-t4d), done/published.

### Contract and acceptance

Move batch/queue/summary loading, pagination, sequential processing, two-step
deletion, file intake/registration and `screeningVals()` into
`frontend/screening.js`, using the existing plain-script factory/subclass seam.
Pass API/resource/display helpers explicitly. Keep shared state, resource loader,
navigation/session/unmount lifecycle, row callback cache, `_readFile()` (also
used by Instant check), report handlers/template, generated runtime and backend
unchanged. Retain the current screening/report mapping precedence. No database,
schema, API/auth, visual or processing-policy change is in scope.

Acceptance: text/PDF intake keeps filename/type/error recovery and registration
payloads; unsupported/empty/unreadable files refuse without invented success.
Only registration or an explicit start drives processing. Calls stay sequential,
duplicate starts do not add a concurrent call, any process error stops without
automatic retry, stop/batch-switch/unmount/session loss retain existing pending
successful process-result invalidation. In-app summary navigation retains the
current driver without switching screens on completion. Switching/deleting a
selected batch prevents an older detail/queue/summary read from restoring its
view. Paging appends server
cursors and preserves existing error/retry behavior. Delete propagation and
two-step UI remain intact. Queue callbacks still open owned reports/feedback;
rows without reports remain inert. Whole-batch summaries, screened denominators,
unassessed/pending rows and advisory/human-review wording remain unchanged.
Detached callbacks retain their receiver/identity; instances isolate mutable
state, row caches, pending processing and batch-view guards. Preserve existing
API plane/tenant/CSRF/consent/erasure contracts and exact static delivery.
Remove only code proven dead in this area; no unrelated hardening or new worker.

### Required validation

Add screening characterizations beside the existing offline handler suites,
reusing their composed-component fixture; run before and after extraction.
Cover intake, sequential/error/late processing, batch read switching/deletion,
paging, callback/instance isolation and rendered mapping semantics. Extend the
existing handler pytest parametrization, anonymous module delivery/mount and
migrated HTTP checks. Run focused UI/mount/image/screening/API-route/auth tests,
full offline pytest, bindings, shipped/extracted JS syntax and diff checks.
Run actual Chrome `scripts/check_ui_screening_extraction_browser.py` plus
`scripts/check_ui_evaluate_browser.py` for shared file/report/session callers;
reuse `scripts/smoke_r4_s1_t3d.py` for migrated scratch HTTP and graceful restart.
Fake providers prove mechanics, not live-provider quality. No SQL transaction,
concurrency or migration change means no new PostgreSQL gate. Record
implementation self-review, preservation, completion and distinct final
self-review before scoped commit/push/remote verification. Preserve working
storage, unrelated work and the existing demo. Stop after E. Next child:
**R4-S1-T4F - Extract candidate portal and authentication UI logic**, with its
bounded contract defined next session. T4/F13/sprint/PI remain open.

### Evidence

Starting HEAD `a8dd784`; initial worktree clean. Sanitized runner
`.resume/Scripts/python.exe .pytest_cache/run_r4_s1_t4e.py <tag> <Python args>`
clears inherited DEE config/keys, ignores `.env`, blocks external GitHub and
uses existing fake providers/isolated stores. Omitted Python args run project
`-m pytest -q --tb=short`; logs use `.pytest_cache/r4-s1-t4e-<tag>.txt`.
Baseline hashes cover 726 tracked files including the working DB. This pure
extraction uses before/after characterizations, not a product-defect reproducer.

`node --test scripts/test_ui_screening.js`: before **45 passed, 0 failed,
0 skipped, 334.59ms**; after **45 passed, 0 failed, 0 skipped, 463.79ms**, exit 0.
The screening suite reuses the existing component fixture and includes its 27
evaluation/report cases plus 18 screening cases. Tests cover actual fake-reader
text/PDF payloads, unsupported/empty/disk/indexed failures, explicit start,
sequential/duplicate starts, counters, failure/manual restart, late successful
process suppression after stop/batch switch/session/unmount, in-app summary
navigation, all three batch read guards on switch/delete, paging/encoded
cursors/refusal recovery, deletion propagation/errors, whole-batch denominators,
inert/insufficient queue rows, report callbacks and same-class isolation.
These are offline handler checks, not actual browser rendering.
An initial draft run had one fixture-timing failure (42/43): the snapshot was
taken before the newly selected batch's own reads settled. Waiting for those
reads corrected the characterization; it was not a product-defect reproducer.

Focused `focused -m pytest -q --tb=short tests/test_ui_handlers.py
tests/test_ui_mount.py tests/test_image_contents.py tests/test_screening_api.py
tests/test_screening_batches_api.py tests/test_screening_outcome_api.py
tests/test_screening_unresolved_input.py tests/test_api_route_extraction.py
tests/test_auth_api.py tests/test_api_auth_gate.py tests/test_route_table_guard.py
tests/test_openapi_contract.py`: **168 passed, 11 skipped, 1 warning in 51.49s**,
exit 0. Covers eight offline handler subprocesses, anonymous exact module bytes/
JavaScript media type, static confinement/packaging, tenant/CSRF/report/erasure
boundaries and unchanged ordered 102-operation API/auth/OpenAPI contract.
Environment skips do not prove PostgreSQL/omitted cases; no image build claimed.

Actual Chrome `screening-browser scripts/check_ui_screening_extraction_browser.py`:
**24/24**, exit 0, 22.65s runner. Migrated scratch SQLite (0029), captured sign-in,
actual file picker/reading, browser-driven processing, private queue identities,
summary counts, owned report/feedback/history, duplicate feedback clicks,
two-step deletion, second intake, authenticated document reload, persisted batch
list and injected 503 read/recovery all pass with no console exceptions. Requires
existing CDN internet; Windows process stop is forced. Synthetic providers and
transport faults prove mechanics, not live-provider behavior/quality.

Migrated HTTP `http-journey scripts/smoke_r4_s1_t3d.py`: **20/20** plus reused
screening HTTP contract **31/31**, exit 0, 27.78s runner. Both named modules
are anonymously declared/delivered byte-for-byte with JavaScript media type
before/after restart; unrelated static paths refuse. Named reviewer, private
operator notes, tenant/CSRF/cursor/error/advisory boundaries, one-item processing
bound, retry without replaying successful items and exact saved batch/queue/
summary/report/outcomes survive restart. Both migrated scratch SQL app starts
exit gracefully with disposal; the HTTP contract is not Chrome evidence.

Implementation self-review: HEAD `a8dd784` plus HTML/new screening module,
named static allowlist and offline/mount/HTTP entry points. Specification review
maps the bounded extraction to before/after Node, focused API/auth/erasure,
actual screening Chrome and migrated HTTP/restart. Correctness review traces
subclass field initialization (`loadMore` exists before `moreBatches`, state is
read only on invocation), explicit helper capture, unchanged mapping precedence
and report callbacks, per-instance row cache/driver/view guards, filename/index
errors, no automatic process retry, delete propagation, paging and existing
navigation/session/unmount behavior. No dead handler or duplicate sample/live
screening implementation was found to remove. No blocking finding remains;
same-agent self-review is not independent review. Existing cancellation/paging
semantics are preserved; this extraction adds no broader race-safety guarantee.

`review -I .pytest_cache/review_r4_s1_t4e.py`: exit 0, 2.36s runner. All **22**
handler fields and full screening/report view composition are text-identical;
template/shared state/lifecycle/row cache/file reader/other screens are identical
after normalizing only script/base composition. Main's AST changes only the
named static allowlist entry. Shipped/test/checker/inline JS syntax passes;
**18** reviewed source/harness/contract hashes recorded. Bindings:
`node scripts/check_ui_bindings.js`, **589 bindings / 18 states**, pass.

Actual Chrome `evaluation-browser scripts/check_ui_evaluate_browser.py`:
**38/38**, plus shared harness **1/1**, exit 0, 33.34s runner. Organization
text/PDF/duplicate/error recovery, saved report/feedback/hash reload, lost-write
acknowledgement/read-only recovery, domain selection, navigation/late results,
erasure/404/session expiry/stale 401, operator ad-hoc routes, candidate refusal,
captured contact and portal consent/access/erasure pass with no console exceptions.
Transport faults are synthetic; ordinary auth/mutations use real migrated
scratch HTTP. CDN internet and forced Windows stop limitations remain.

`compile -m compileall -q src/app/main.py tests/test_ui_mount.py
tests/test_ui_handlers.py scripts/smoke_r4_s1_t3d.py`: exit 0, 0.17s runner.
Full pytest `full-reviewed` (no extra runner arguments; project `-m pytest -q
--tb=short`): **3540 passed, 505 skipped, 127 warnings in 753.45s (0:12:33)**,
exit 0 (763.87s runner). Existing
Starlette/httpx deprecation and SQLite expression-index reflection/autogenerate
warnings remain; optional/environment skips do not prove omitted cases. The
eighteen reviewed source/harness/contract hashes are unchanged; only task
documentation changed during the full run.

Preservation `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t4e.py`:
**713** unrelated tracked files, working DB and **18** reviewed hashes unchanged;
scoped local Markdown links/anchors and tracked/staged/source whitespace pass.
Tracking branch is `origin/main`; its pre-publication remote matched starting
HEAD `a8dd784286e7ff04a42ec0c9f615a06afb6bcf6d`.

All bounded E acceptance and required validation gates are complete. The 22
handler fields and screening/report view composition now have one implementation
in the new plain script. Shared state/lifecycle/row cache/file reader, template,
API/auth and other screen logic remain unchanged. No dead handler or duplicate
sample/live screening source was found to remove. No SQL transaction, concurrency
or migration changes and no new PostgreSQL gate apply. Existing cancellation/
paging semantics and browser-driven processing remain; durable continuation is
R4-S2-T4. No broader race-safety, live-provider or accuracy claim is made.
Working storage/demo are preserved. Only E completed this session;
T4/F13/sprint/PI remain open. No F implementation or deployment started.

### Completion review and publication

After required checks and completion records, a distinct final same-agent
self-review examined HEAD `a8dd784` plus the exact fifteen staged files:
HTML/new screening module, named static allowlist, existing Node/checker/HTTP
entry points, mount/handler tests, feature overview, handoff, roadmap,
PI/evidence and active T4 parent. Specification review confirms the bounded
extraction, required validation, unchanged ordered API/auth contract, one
screening implementation, child evidence ownership and F-only next pointer,
with T4/F13/sprint/PI still open.

Correctness review rechecks base/derived field ordering and deferred state
reads, explicit helper capture, stable detached callbacks, per-instance file/
row-cache/driver/view state, report-map precedence, shared file-reader reuse,
filename/index error recovery, sequential processing/no automatic retry,
stop/batch-switch/session/unmount successful-result guards, in-app navigation,
delete propagation and stale-read invalidation, paging/cursor/error recovery,
whole-batch summary denominators, insufficient rows, advisory/human review,
static confinement and packaging. Existing cancellation/paging limitations are
preserved and disclosed; no new worker or backend semantics entered the diff.
No blocking finding remains. This final self-review is separate from the
implementation review; no independent review is claimed.

`completion-review -I .pytest_cache/review_r4_s1_t4e.py --staged`: exit 0,
2.18s runner. All 22 original handler fields and full screening/report mapping
match; template/state/lifecycle/row cache/file reader and main AST comparisons
pass. Shipped/test/checker/inline JS syntax and all 18 reviewed hashes match.
The exact 15-file staged scope matches the reviewed files, excluding working
data, secrets and local artifacts. Final preservation confirms 713 unrelated
tracked files, working DB and 18 reviewed hashes unchanged; 283 scoped local
links/anchors and tracked/staged/source whitespace pass. Only documentation
changed during/after full pytest. The review-record prose is checked separately
for scope/evidence/status accuracy before publication; application tests do not
need rerunning for prose.

Scoped task commit **`6677a8d`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`a8dd784` to `6677a8d`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`6677a8da2d73d0a68b395c01985142199903b5e5`**. Working tree was clean.

This two-file documentation-only confirmation records verified publication in
the handoff and this evidence section. Separate final same-agent self-review
against `6677a8d` checks the exact prose diff, actual remote evidence, open T4
parent and F-only next pointer; no blocking finding remains. Scoped links,
whitespace and preservation pass. Application/test/harness code remains at the
full pytest/HTTP/Chrome validated state; no application tests are rerun for prose.
The final response reports the verified remote SHA after this confirmation's
commit/push. No F work, working-data change, demo restart or deployment occurred.

### Handoff

Exact next: **R4-S1-T4F - Extract candidate portal and authentication UI logic**,
not started. Define its bounded contract in the existing T4 record next session.
Stop after E publication.

## <a id="r4-s1-t4f"></a>R4-S1-T4F - Extract candidate portal and authentication UI logic

Status: done and published (2026-10-23). Parent:
[T4](#r4-s1-t4). Prerequisite: [E](#r4-s1-t4e), done/published.

### Contract and acceptance

Move login/signup/resend/verification/sign-out, OTP box handlers, auth plane/
mode selection, candidate contact verification, consent/session revocation and
erasure handlers plus auth/portal/device view mappings into
`frontend/portal-auth.js` using the existing plain-script factory/subclass seam.
Pass existing API, OTP/plane/resource/display helpers explicitly. Keep shared
state, resource loader, boot/session/unmount cleanup, navigation, row cache,
template, generated runtime, API client and backend unchanged. Keep live auth
action precedence and account identity mapping. Remove the six portal/device
sample arrays and their always-overwritten render mappings after proving no
other callers; keep other areas out of scope. No database/schema/API/auth-policy,
visual or broader race-safety change is implied.

Acceptance: all three auth planes retain signup/login/verify routes, payloads,
landing screens and uniform acceptance copy; operator has no self-signup.
Blank email/org name/incomplete code refuse locally. OTP paste, backspace and
Enter, local-only server debug echo, resend-without-echo preserving typed digits,
failed verify clearing digits, logout and shared session cleanup retain their
behavior. Portal/access/consent/device navigation requests the same resources;
consent and other-device revocation reread saved server state; errors preserve
existing data and never invent success. Erasure requires typed DELETE, ends the
session only on success and preserves other subjects. Contact checks retain
candidate-only/duplicate guards, encoded IDs, strict returned-state checks,
uncertain-write recovery and existing account/unmount invalidation. Detached
callbacks retain their receiver/identity; instances isolate OTP handlers, contact
tokens and row caches. Portal mappings preserve identity/retention/assurance,
report metadata without report contents, access actors/outcomes and current
device's inert action; empty/loading/error states never fall back to samples.
Tenant/subject/CSRF/consent/erasure and ordered API contracts remain intact.

### Required validation

Extend the existing `scripts/test_ui_verification.js` suite with before/after
auth/OTP/portal/device/erasure/instance characterizations, reusing its component
fixture and existing contact regressions. Extend mount and migrated HTTP module
delivery checks; run all offline handlers, focused UI/mount/image/auth/portal/
verification/API-route pytest, full offline pytest, bindings and shipped/inline
JS syntax/diff checks. Extend actual Chrome `scripts/check_ui_evaluate_browser.py`
with real candidate resend/invalid-code recovery and sibling-device revocation,
retaining its contact/consent/access/reload/error/erasure journeys. Also run
`scripts/check_ui_screening_extraction_browser.py` for organization signup and
screen/report callers, and `scripts/smoke_r4_s1_t3a.py` for migrated scratch
auth/portal/ownership/CSRF/graceful restart plus exact module delivery. Fake
providers/captured mail prove mechanics, not live delivery/provider quality.
No SQL transaction/concurrency/migration change means no new PostgreSQL gate.
Record implementation self-review, preservation, completion and separate final
self-review before scoped commit/push/remote verification. Preserve working
storage, unrelated work and the existing demo. Stop after F. Exact next:
**R4-S1-T4G - Extract interview UI handlers and view values**; define its bounded
contract next session. T4/F13/sprint/PI remain open.

### Evidence

Starting HEAD `0b23ebe75feeef2988c45a6bee1d82bdce5b9983`; initial worktree
clean. Sanitized runner `.resume/Scripts/python.exe
.pytest_cache/run_r4_s1_t4f.py <tag> <Python args>` clears inherited DEE config/
keys, ignores `.env`, blocks external GitHub and uses fake providers/isolated
stores. Omitted Python args run project `-m pytest -q --tb=short`; logs use
`.pytest_cache/r4-s1-t4f-<tag>.txt`. Baseline hashes cover 728 tracked files
including working DB. This extraction uses passing before/after
characterizations, not a product-defect reproducer.

`node --test scripts/test_ui_verification.js`: before **54 passed, 0 failed,
0 skipped, 1206.80ms**; after **54 passed, 0 failed, 0 skipped, 853.43ms**, exit 0.
The existing suite reuses 27 evaluation/client cases and 12 contact cases;
15 added auth/portal cases cover all plane/mode routes, local validation,
OTP paste/backspace/Enter/identity/instance isolation, local server echo,
resend-without-echo preserving digits, verify/send/resend refusal and recovery,
busy-action precedence, resource-specific navigation, redacted report/contact
metadata, assurance/retention/access actors, no sample fallback, consent/device
saved-state rereads/errors, typed erasure/success cleanup and separate pending
contact tokens. Existing contact tests retain strict returned-state checks,
duplicate suppression, delivery/code refusal, uncertain writes and account-loss
invalidation. Initial draft failures (52/54 then 53/54) were fixture mistakes:
mutating the shared idle resource and expecting verification to be the last
call despite its landing-screen read. Corrected assertions/setup are not
product-defect reproductions. Offline handlers are not Chrome rendering.

Focused `focused -m pytest -q --tb=short tests/test_ui_handlers.py
tests/test_ui_mount.py tests/test_image_contents.py tests/test_auth_api.py
tests/test_auth_debug_echo.py tests/test_auth_session_twins.py
tests/test_portal_api.py tests/test_portal_sessions.py tests/test_portal_identity.py
tests/test_verification_api.py tests/test_verification_delivery.py
tests/test_api_route_extraction.py tests/test_api_auth_gate.py
tests/test_route_table_guard.py tests/test_openapi_contract.py`:
**164 passed, 0 skipped, 1 warning in 150.29s (0:02:30)**, exit 0
(165.42s runner). Covers all eight offline handler subprocesses, anonymous
module bytes/JavaScript media type, static confinement/packaging, auth/subject/
tenant/CSRF/contact/erasure and unchanged ordered 102-operation API/auth/OpenAPI
contracts. Image contract checks are not an image build.

Actual Chrome `screening-browser scripts/check_ui_screening_extraction_browser.py`:
**24/24**, exit 0, 46.34s runner. Migrated scratch SQLite (0029), captured org
signup/OTP, actual text/PDF picker/reading/processing, private queue identities,
summary, owned report/feedback/history, duplicate judgement clicks, two-step
delete, new intake/reload, injected 503 read/recovery and no console exceptions
pass. CDN internet is required; Windows stop is forced. Fakes prove mechanics,
not live provider/delivery quality.

Migrated HTTP `http-journey scripts/smoke_r4_s1_t3a.py`: **85/85**, exit 0,
66.65s runner. Both migrated starts anonymously declare/deliver exact portal/
auth module bytes and JavaScript media type; unrelated static paths refuse.
Three-plane sign-in/cookies/CSRF, owned devices and sibling survival, uniform
unknown login and invalid verify, subject/tenant ownership, portal requests/
consent/contact documents/manual review, exact saved state across restart,
revocation/erasure and other-subject survival pass. Both lifespans shut down
gracefully with shared SQL disposal. Other existing employer/ledger/features/
public-surface checks remain green; HTTP is not browser evidence.

After the source-comment correction, `http-journey-final
scripts/smoke_r4_s1_t3a.py` repeats **85/85**, exit 0, 29.08s runner, including
exact final module bytes before/after restart and both graceful SQL lifespans.

Implementation self-review: HEAD `0b23ebe` plus HTML/new portal-auth module,
named static allowlist, Node/checker/browser/HTTP entry points and mount test.
Specification review maps the bounded extraction to before/after Node,
focused API/auth/portal/erasure checks, actual org Chrome and migrated HTTP.
Correctness review traces base field initialization (OTP array creates callbacks,
state is read on invocation), explicit helpers, auth busy/live precedence,
portal/account map placement, per-instance OTP/contact/row-cache state, strict
contact state/encoded IDs, existing navigation/boot/session/unmount cleanup,
uniform auth responses, no automatic write replay, revocation/erasure recovery,
report metadata/redacted contacts, assurance/retention and static packaging.
Six sample arrays and their mappings each had only a definition and a render
reference always overwritten by live values; the duplicate initial auth action
was also always overwritten. Their removal changes no rendered values. No
blocking finding remains. This same-agent self-review is not independent review.
Existing non-contact callback/cancellation semantics remain; no broader
race-safety guarantee or backend policy change is made.

Low finding, resolved: the transferred current-device comment in
`frontend/portal-auth.js` incorrectly claimed the API refuses self-revocation;
the existing HTTP journey proves it succeeds while the sibling survives. The
UI deliberately keeps the current device's row action inert. Replaced only
that source comment with the UI rule (use Sign out for this device), avoiding a
misleading maintenance instruction. `node --test scripts/test_ui_verification.js`
after correction: **54 passed, 0 failed, 0 skipped, 716.08ms**, exit 0; shipped/
test/checker/inline syntax also passes. Browser behavior/runtime expressions are
unchanged, so no browser rerun is needed for the comment. The correction was
made during full pytest before its UI handler subprocesses execute.

`review-final-comment -I .pytest_cache/review_r4_s1_t4f.py`: exit 0, 2.20s runner
(supersedes the 3.36s `review-final` snapshot after that comment correction).
All **29** original fields (28 handlers plus per-instance OTP callback array),
portal setup/account/live mappings and effective auth mapping are preserved.
Shared state/boot/session cleanup/unmount/navigation/template/row cache and
other screen logic are identical after normalizing script/base/map composition
and only the proven dead data/default and reviewed source comment. Main's AST
changes only the named static allowlist entry. Shipped/test/checker/extracted inline JS syntax passes;
**20** reviewed source/harness/contract hashes recorded. Bindings
`node scripts/check_ui_bindings.js`: **589 bindings / 18 states**, pass.

`compile -m compileall -q src/app/main.py tests/test_ui_mount.py
scripts/smoke_r4_s1_t3a.py scripts/check_ui_evaluate_browser.py`: exit 0,
0.43s runner.

Actual Chrome `evaluation-browser-final scripts/check_ui_evaluate_browser.py`:
**42/42**, plus shared harness **1/1**, exit 0, 48.26s runner. Real candidate
resend/wrong-code refusal/cleared digits/correct-code recovery and saved sibling
device listing/revocation/current-session survival extend the existing org/
operator/candidate sign-in, evaluation/report/feedback, uncertain-write reads,
contact delivery failure/confirmation, consent revocation/access actors,
authenticated document reload/error recovery and erasure/other-subject survival.
All pass with no console exceptions on migrated scratch SQLite/captured mail.
Cooldown is disabled only in the synthetic browser server; production settings
are unchanged. Existing transport fault cases are injected; auth/mutations use
real HTTP. CDN internet is required; Windows stop is forced. The initial extended
run was **41/42**, exit 1 (84.49s): its new device check expected a revoked row,
but the existing API deliberately lists live sessions only. Corrected the test
to require sibling disappearance, actual sibling 401 and current-session
survival. No product code changed for that harness correction; the affected
browser rerun passes and its final hash is recorded.

Full pytest `full-reviewed` (no extra runner arguments; project `-m pytest -q
--tb=short`): **3540 passed, 505 skipped, 127 warnings in 1842.46s (0:30:42)**,
exit 0 (1853.15s runner). Existing
Starlette/httpx deprecation and SQLite expression-index reflection/autogenerate
warnings remain. Optional/environment skips do not prove omitted cases. All
twenty final reviewed source/harness/contract hashes match. During the full run,
one source comment was corrected before the UI handler subprocesses executed;
runtime expressions remained identical and affected Node/syntax checks were
rerun. Other changes during the run were task documentation only.

Preservation `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t4f.py`:
**714** unrelated tracked files, working DB and **20** reviewed hashes unchanged;
scoped local Markdown links/anchors and tracked/staged/source whitespace pass.
Tracking branch is `origin/main`; pre-publication remote matched starting HEAD
`0b23ebe75feeef2988c45a6bee1d82bdce5b9983`.

All bounded F acceptance and required validation gates are complete. Auth,
contact, consent/device/erasure handlers, OTP callbacks and live auth/portal/
account/device mappings have one implementation in the new plain script. Six
always-overwritten sample arrays/mappings and the initial auth-action default
are removed. Shared state/boot/session cleanup/unmount/navigation/template/row
cache, API client and backend are preserved. No SQL transaction, concurrency or
migration change and no new PostgreSQL gate apply. Existing callback/cancellation
semantics remain; no broader race-safety, live delivery/provider or quality claim
is made. Working storage/demo are preserved. Only F completed this session;
T4/F13/sprint/PI remain open. No G implementation or deployment started.

### Completion review and publication

After required checks and completion records, a distinct final same-agent
self-review examined HEAD `0b23ebe` plus the exact fifteen staged files:
HTML/new portal-auth module, named static allowlist, existing Node/checker/
browser/HTTP entry points, mount test, feature overview, handoff, roadmap,
PI/evidence and active T4 parent. Specification review confirms the bounded
auth/portal extraction, proof of dead samples/default, required validation,
unchanged ordered API/auth contract, child evidence ownership and G-only next
pointer, with T4/F13/sprint/PI still open.

Correctness review rechecks base/derived field initialization, deferred state
reads, explicit helpers, effective busy auth action, portal/account map order,
stable detached callbacks and per-instance OTP/contact/row-cache state,
uniform auth responses, local server echo only, resend/verify recovery,
strict contact states/encoded IDs, existing boot/navigation/session/unmount
cleanup, consent/device saved-state reads, typed erasure and other-subject
survival, metadata-only reports/redacted contacts, assurance/retention/access
actors, static confinement and packaging. Current-device UI action remains
inert; its inaccurate source comment is corrected without changing expressions.
Existing callback/cancellation limits are preserved and disclosed. No blocking
finding remains. This final self-review is separate from implementation review;
no independent review is claimed.

`completion-review -I .pytest_cache/review_r4_s1_t4f.py --staged`: exit 0,
2.15s runner. All 29 original fields and effective live mappings match after
normalizing only the reviewed comment. Shared template/state/boot/session/
unmount/navigation/row cache, other screens and main AST comparisons pass.
The six retired sample arrays/mappings and initial auth-action default have
no remaining callers. Shipped/test/checker/inline syntax and all 20 reviewed
hashes match. The exact fifteen staged files match reviewed contents, excluding
working data, secrets and local artifacts. Preservation confirms 714 unrelated
tracked files, working DB and 20 reviewed hashes unchanged; 289 scoped local
links/anchors and tracked/staged/source whitespace pass. Review-record prose is
checked separately for scope/evidence/status accuracy before publication; no
application tests need rerunning for prose.

Scoped task commit **`6a7ac7a`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`0b23ebe` to `6a7ac7a`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`6a7ac7a65daf46a43a5bfe3f81dbda5180cfe06e`**. Working tree was clean.

This two-file documentation-only confirmation records verified publication in
the handoff and this evidence section. Separate final same-agent self-review
against `6a7ac7a` checks the exact prose diff, actual remote evidence, open T4
parent and G-only next pointer; no blocking finding remains. Scoped links,
whitespace and preservation pass. Application/test/harness code remains at the
full pytest/HTTP/Chrome validated state; no application tests are rerun for prose.
The final response reports the verified remote SHA after this confirmation's
commit/push. No G work, working-data change, demo restart or deployment occurred.

### Handoff

Exact next: **R4-S1-T4G - Extract interview UI handlers and view values**, not
started. Define its bounded contract in the existing T4 record next session.
Stop after F publication.

## <a id="r4-s1-t4g"></a>R4-S1-T4G - Extract interview UI handlers and view values

Status: done and published (2026-10-23). Parent:
[T4](#r4-s1-t4). Prerequisite: [F](#r4-s1-t4f), done/published.

### Contract and acceptance

Move the contiguous interview handler/media helper/view-value area from
`frontend/Veritas.dc.html` to `frontend/interview.js` using the established
plain-script factory/subclass seam. Pass existing API/resource/display helpers
explicitly; retain dynamic browser media/timer access. Keep shared state, boot,
session loss, navigation/pagehide/unmount callers, row cache, template, generated
runtime, API client and backend unchanged. Preserve interview mapping precedence
and other screens. Remove only proven dead code in this area. No schema, scoring,
transport, API/auth, visual, privacy-policy or broader race-safety change.

Acceptance: candidate-only list/detail/start/answer/finish retains routes,
encoded IDs, domain/question binding, duplicate-write suppression, malformed/
mismatched response refusal and explicit finish. Empty/blank/oversize/expired
states refuse without false success. Uncertain writes require saved-state reads
without automatic replay. Late responses/permissions/recorder events cannot
restore a departed or replaced actor's view; a newer refresh wins. Typed drafts
and text/audio mode changes keep their current behavior. Microphone remains
explicit audio-only; limits/deadlines, stop/discard, stream/recorder/reader/timer
cleanup and question/actor-bound clips remain intact. Detached callbacks retain
receiver/identity; same-class instances isolate drafts, pending loads/writes and
media state. Saved assessments preserve original v1/v2 values, unknown/mixed/
insufficient refusal, evidence/truncation warnings and advisory/human review.
Content is assessed, never appearance or inferred emotion. Existing tenant/
subject/CSRF/consent/erasure and ordered API contracts remain unchanged.

### Required validation

Extend existing `scripts/test_ui_interview.js` and `scripts/test_ui_interview_audio.js`
with before/after callback/same-class/load/write/media characterizations; retain
their existing failure, media-bound and rubric-semantic cases and run all offline
handlers. Extend mount and existing migrated interview HTTP module-byte checks.
Run focused UI/mount/image/interview/auth/route pytest, full offline pytest,
bindings and shipped/inline JS syntax/diff checks. Actual Chrome:
`scripts/check_ui_interview_integration_browser.py` (existing synthetic microphone
plus text/audio/session/consent/restart journey) and
`scripts/check_ui_evaluate_browser.py` for shared navigation/actor cleanup callers.
Migrated HTTP/graceful restart: `scripts/smoke_r3_s3_t3.py --combined`, including
anonymous exact module delivery. Fakes/synthetic media prove mechanics, not live
ASR/codec compatibility or measured assessment quality. Browser restart is forced
on Windows; the separate HTTP lifespan gate proves graceful shutdown. No SQL
transaction/concurrency/migration change means no new PostgreSQL gate. Record
implementation self-review, preservation, completion and distinct final
self-review before scoped commit/push/remote verification. Preserve working
storage, unrelated work and the existing demo. Stop after G. Exact next:
**R4-S1-T4H - Extract employer roles and compensation UI logic**; define its
bounded contract next session. T4/F13/sprint/PI remain open.

### Evidence

Starting HEAD `893f42a851f5dafb6f8e2a6ec4aa6528e5534406`; initial worktree
clean. Sanitized runner `.resume/Scripts/python.exe
.pytest_cache/run_r4_s1_t4g.py <tag> <Python args>` clears inherited DEE config/
keys, ignores `.env`, blocks external GitHub and uses fake providers/isolated
stores. Omitted Python args run project `-m pytest -q --tb=short`; logs use
`.pytest_cache/r4-s1-t4g-<tag>.txt`. Baseline hashes cover 729 tracked files
including working DB. This extraction uses passing before/after
characterizations, not a product-defect reproducer.

`node --test scripts/test_ui_interview.js`: before **49 passed, 0 failed,
0 skipped, 853.80ms**; after **49 passed, 0 failed, 0 skipped, 904.82ms**.
`node --test scripts/test_ui_interview_audio.js`: before **74 passed, 0 failed,
0 skipped, 989.54ms**; after **74 passed, 0 failed, 0 skipped, 916.25ms**.
All exit 0. Suites overlap: text includes 27 evaluation/client cases; audio
includes the text suite. Five new cases cover stable detached field callbacks,
same-class draft/pending-write isolation across actor loss, independent list
loads and encoded ID selection, separate microphone captures/chunks/tracks/
timers/clips and late permission after one instance's unmount while another
continues recording. Existing text/audio cases retain candidate-only routes,
selected domain/question binding, duplicate/blank/oversize/expired/refused writes,
malformed replies, saved-state recovery without replay, version/evidence wording,
permission/recorder/reader failures and deadlines, five-MB/two-minute limits,
mode/navigation/session/pagehide/unmount cleanup and stale-clip refusal. These
offline checks are not actual Chrome.

Initial `focused` pytest invocation exited 4 with **no tests run in 0.04s**
(10.78s runner) because its file selection included nonexistent microphone/
ownership/summary filenames. Corrected the selection to the existing interview
API/employer API/service/scoring/erasure modules; this was not a product finding.
Final focused `focused-final -m pytest -q --tb=short tests/test_ui_handlers.py
tests/test_ui_mount.py tests/test_image_contents.py tests/test_interview_api.py
tests/test_interview_org_api.py tests/test_interview_service.py
tests/test_interview_scoring.py tests/test_interview_erasure.py
tests/test_api_route_extraction.py tests/test_api_auth_gate.py tests/test_auth_api.py
tests/test_route_table_guard.py tests/test_openapi_contract.py`:
**201 passed, 0 skipped, 1 warning in 43.66s**, exit 0 (54.73s runner).
Includes all eight offline handler subprocesses, anonymous exact module bytes/
JavaScript media type, static confinement/packaging, interview ownership/
consent/erasure/scoring and unchanged ordered 102-operation API/auth/OpenAPI
contract. Image contract checks are not an image build.

Migrated HTTP `http-journey scripts/smoke_r3_s3_t3.py --combined`: **27/27**,
exit 0, 51.15s runner. Both migrated scratch SQLite (0029) starts anonymously
declare/deliver exact interview module bytes and JavaScript media type;
unrelated static paths refuse. Existing text/audio continuation, fake ASR
failure/privacy/bounds, question/actor conflicts, duplicate/stale refusal,
saved assessments/turns across restart, employer summary consent/redaction,
revocation/erasure and both graceful SQL shutdowns pass. HTTP fixtures do not
prove real microphone/codec/ASR compatibility or assessment quality.

Actual Chrome `evaluation-browser scripts/check_ui_evaluate_browser.py`:
**42/42**, plus shared harness **1/1**, exit 0, 48.52s runner. Organization/
operator/candidate sign-in, text/PDF evaluation, reports/feedback/uncertain
write recovery, navigation/session expiry/stale 401, candidate resend/wrong-code
recovery, sibling device revocation, contact verification, consent/access,
document reload/errors and erasure/other-subject survival retain behavior with
no console exceptions. Real HTTP and captured mail use migrated scratch SQL;
existing transport faults are injected. CDN internet required; Windows stop
is forced, not graceful-lifecycle evidence.

Implementation self-review: HEAD `893f42a` plus HTML/new interview module,
named static allowlist, existing Node/checker/HTTP entry points and mount test.
Specification review maps the bounded extraction to before/after Node,
migrated interview HTTP and shared evaluation Chrome. Correctness review traces
composed-class initialization (handlers are created before shared state but
read it only on invocation), explicit API/resource/display capture, dynamic
window media/timer access, unchanged mapping order, detached handlers and
per-instance request/media state, encoded IDs, strict saved-body validation,
question/actor-bound clips, uncertain-write reads/no replay, media/timer/reader
cleanup through shared navigation/session/pagehide/unmount callers, historical/
unknown rubric semantics, content-only advisory wording and static packaging.
No dead handler or duplicate sample/live interview source was found to remove.
No blocking finding remains; same-agent self-review is not independent review.
No backend/scoring/schema/concurrency changes or new PostgreSQL gate apply.

`review -I .pytest_cache/review_r4_s1_t4g.py`: exit 0, 5.30s runner. All **24**
original fields (23 handler/helpers and `interviewValues`) are text-identical.
Shared state/boot/session/pagehide/unmount/navigation/template/row cache and
other screen logic are identical after normalizing only script/base composition.
Main's AST changes only the named static allowlist entry. Shipped/test/checker/
extracted inline JS syntax passes; **22** reviewed source/harness/contract hashes
recorded. Bindings `node scripts/check_ui_bindings.js`: **589 bindings /
18 states**, pass. `compile -m compileall -q src/app/main.py
tests/test_ui_mount.py scripts/smoke_r3_s3_t3.py`: exit 0, 0.31s runner.

Actual Chrome `interview-browser scripts/check_ui_interview_integration_browser.py`:
**40/40**, plus shared harness **1/1**, exit 0, 83.86s runner. Synthetic
microphone/real MediaRecorder bytes and fake ASR cover explicit audio-only
permission, denial/fallback, stop/discard/mode switch, oversize chunks, provider
failure/empty/unavailable, delayed ASR/client deadline, duplicate submit/lost
committed acknowledgement/read-only recovery, cross-actor/stale-question refusal,
truncation and saved advisory assessment. Combined typed repetition + audio
continuation, exact saved mixed-channel state across actual process restarts,
version/confidence/evidence warnings, employer consent-only summary without
transcripts/media, other employer refusal, current revocation, late permission,
navigation/reload/signout media cleanup and new-account isolation pass. No
console exceptions; app logs omit transcript/private provider error. Migrated
scratch SQL/captured email only. CDN internet and forced Windows restart apply;
the HTTP journey separately proves graceful shutdown. Fake ASR/synthetic media
do not prove live provider/codec compatibility or measured assessment quality.

Full pytest `full-reviewed` (no extra runner arguments; project `-m pytest -q
--tb=short`): **3540 passed, 505 skipped, 127 warnings in 596.34s (0:09:56)**,
exit 0 (605.42s runner). Existing
Starlette/httpx deprecation and SQLite expression-index reflection/autogenerate
warnings remain. Optional/environment skips do not prove omitted cases. All
twenty-two reviewed source/harness/contract hashes match; only documentation
changed during/after the full run.

Preservation `.resume/Scripts/python.exe .pytest_cache/verify_r4_s1_t4g.py`:
**715** unrelated tracked files, working DB and **22** reviewed hashes unchanged;
scoped local Markdown links/anchors and tracked/staged/source whitespace pass.
Tracking branch is `origin/main`; pre-publication remote matched starting HEAD
`893f42a851f5dafb6f8e2a6ec4aa6528e5534406`.

All bounded G acceptance and required validation gates are complete. The 23
handler/helper fields and interview view mapping have one implementation in the
new plain script. Shared state/boot/session/pagehide/unmount/navigation/template/
row cache, other screens, API client, backend and scoring are preserved. No dead
handler or duplicate sample/live interview source was found to remove. No SQL
transaction/concurrency/migration changes and no new PostgreSQL gate apply.
Existing media/cancellation/provider/quality limits remain. No live ASR/codec
compatibility or measured assessment claim is made. Working storage is preserved;
demo not restarted. Only G completed this session; T4/F13/sprint/PI remain open.
No H implementation or deployment started.

### Completion review and publication

After required checks and completion records, a distinct final same-agent
self-review examined HEAD `893f42a` plus the exact fifteen staged files:
HTML/new interview module, named static allowlist, existing Node/checker/HTTP
entry points, mount test, feature overview, handoff, roadmap, PI/evidence and
active T4 parent. Specification review confirms the bounded text/audio
extraction, required validation, unchanged ordered API/auth contract, one
interview implementation, child evidence ownership and H-only next pointer,
with T4/F13/sprint/PI still open.

Correctness review rechecks composed-class field initialization and deferred
state reads, explicit API/resource/display helpers, dynamic window media/timer
access, unchanged view precedence, detached handlers and per-instance drafts/
load/write/capture/clip state, encoded IDs and strict body validation, candidate/
question binding, uncertain-write read-only recovery without replay, recording
limits and permission/stop/encoding deadlines, track/recorder/reader/timer cleanup
through shared navigation/session/pagehide/unmount callers, historical/unknown/
insufficient rubric and evidence/truncation wording, content-only advisory
semantics, anonymous static confinement and packaging. No blocking finding
remains. This final self-review is separate from implementation review; no
independent review is claimed.

`completion-review -I .pytest_cache/review_r4_s1_t4g.py --staged`: exit 0,
1.90s runner. All 23 original handler/helper fields and complete view mapping
are text-identical. Shared template/state/boot/session/pagehide/unmount/
navigation/row cache, other screens and main AST comparisons pass. Shipped/
test/checker/inline syntax and all 22 reviewed hashes match. Exact fifteen-file
staged scope matches reviewed contents and excludes working data, secrets and
local artifacts. Preservation confirms 715 unrelated tracked files, working DB
and 22 reviewed hashes unchanged; 295 scoped local links/anchors and tracked/
staged/source whitespace pass. Only documentation changed during/after full
pytest. Review-record prose is checked separately for scope/evidence/status
accuracy before publication; application tests do not need rerunning for prose.

Scoped task commit **`27d8400`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`893f42a` to `27d8400`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`27d8400d274425562cfedb9ee75ec693c1a4cdc3`**. Working tree was clean.

This two-file documentation-only confirmation records verified publication in
the handoff and this evidence section. Separate final same-agent self-review
against `27d8400` checks the exact prose diff, actual remote evidence, open T4
parent and H-only next pointer; no blocking finding remains. Scoped links,
whitespace and preservation pass. Application/test/harness code remains at the
full pytest/HTTP/Chrome validated state; no application tests are rerun for prose.
The final response reports the verified remote SHA after this confirmation's
commit/push. No H work, working-data change, demo restart or deployment occurred.

### Handoff

Exact next: **R4-S1-T4H - Extract employer roles and compensation UI logic**,
not started. Define its bounded contract in the existing T4 record next session.
Stop after G publication.

## <a id="r4-s1-t4h"></a>R4-S1-T4H - Employer roles and compensation UI extraction

Status: done (2026-10-23); bounded child of [T4](#r4-s1-t4), F13.
Baseline `cbf6c17`, clean `main` tracking `origin/main`. Only H completes this
session; T4/F13/sprint/PI stay open. Working data preserved; demo not restarted.

### Contract specified before implementation

This is a behavior-preserving extraction: passing before/after characterization
is appropriate, not a fabricated failing defect reproducer.

When an employer opens Roles, selects a saved requisition or opens Comp
intelligence, the same requests, selected-role fallback, rendered data and
read-error recovery must result. Move the four load/select handlers and the
roles/board/compensation view mapping into `frontend/employer-roles.js`, using
the existing plain-script class-factory pattern and explicit helpers. Remove
only the JOBS/SHORTLIST samples and their initial mappings, which live mappings
always replace. Shared state, loading helper, boot/session lifecycle, navigation
callbacks, template and other screens stay in the component. Add only the named
public static asset. No API/scoring/auth behavior, schemas, SQL/migrations,
visual redesign, new role editor, live-provider validation or demo restart.

Acceptance and validation:

1. Same detached handlers act on their component; concurrent same-class
   instances retain separate selected roles, pending resources and view values.
   Extend the existing offline evaluation suite with behavior characterizations
   before extraction, including first-role selection and direct-comp loading.
2. Empty pool, consent refusal and failed reads remain distinct; manual retry
   recovers. Missing scores/coverage, zeroes, unknown bands, wrapped and legacy
   compensation, missing/degenerate bounds, k-floor/prior and no-band wording
   retain honest rendered values. Tests assert outcomes rather than file shape.
3. Actual Chrome exercises saved role/board selection, advisory explanation,
   wrapped compensation, reload and read-failure/recovery with no uncaught
   errors. Extend the existing review-context journey for compensation failure
   and recovery; synthetic data/fakes do not establish empirical quality.
4. Migrated scratch HTTP verifies the named asset's declaration, exact bytes,
   content type and unrelated-path refusal, owned/foreign employer routes,
   consent and exact persisted board/compensation across graceful restart.
   Reuse `scripts/smoke_r4_s1_t3a.py`; preserve its existing auth/ledger checks.
5. Run focused UI/employer/auth/API pytest, full pytest, bindings, shipped/inline
   JS syntax, Python compile, diff/links and preservation checks. No new PG gate
   is required for a frontend-only extraction with unchanged SQL/transactions.
6. Record implementation self-review and a distinct final completed/staged
   self-review. Update owned evidence, PI and short handoff, publish scoped
   reviewed changes, verify remote, then stop. T4/F13/sprint/PI remain open.

### Implementation and regression evidence

The four original fields (`loadJobs`, `selectJob`, `loadComp`, `loadCompFor`)
and complete roles/board/compensation data/value mapping are text-identical in
`frontend/employer-roles.js`. Roles/Comp screen flags and navigation styling
move with the view mapping, substituting `st.screen` for the equivalent `s`.
The factory takes explicit API/error/style/risk/confidence/navigation helpers;
all handlers remain bound fields with deferred state reads. Shared state,
loading, boot/session/unmount/navigation callbacks, template and other modules
are unchanged. Only the named static asset is added to the server allowlist.

JOBS/SHORTLIST arrays and initial render mappings were always overwritten by
`liveVals()`; callers were searched and those dead samples are removed. There
is one roles/compensation mapping. No backend/API/auth/scoring/store/SQL change,
role editor or visual redesign. Existing shared-load and concurrency semantics
are preserved; this extraction adds no new cancellation or stale-response claim.

Seven cases extend `scripts/test_ui_evaluate.js` using its existing fixture:
first-role/retained selection and live-only rows; same-class separate pending
board/compensation and detached callbacks; direct comp role loading/fallback;
failed discovery without fictional data/writes; missing versus zero scores and
coverage/unknown risk; wrapped/legacy/prior/skewed/degenerate/missing comp values;
and explicit read retry clearing failure/stale data. Existing consent/empty-pool
and evaluation/session/client cases remain. Other suites import this fixture,
so overlapping Node totals are not additional unique coverage.

The first characterization run had 30 passes/four fixture failures in 281.90ms:
new tests mutated shared IDLE envelopes instead of replacing each resource.
Fixed the test setup before extraction; no product defect or failing regression
is claimed from that setup error. Final before/after runs of
`node --test scripts/test_ui_evaluate.js` pass **34/34**, zero skipped/failed,
262.25ms before and 312.67ms after.

### Commands and observed validation

Python commands use `.resume/Scripts/python.exe`. The ignored runner
`.pytest_cache/run_r4_s1_t4h.py <tag> <Python args>` removes inherited DEE
configuration, selects a nonexistent config file, clears model/GitHub keys,
uses localhost refusal for GitHub and null/captured mail, and supplies project
paths. Scratch harnesses own disposable SQLite migrated to 0029 with fake
providers. Logs/helpers remain ignored; no working DB or demo is used.

- `focused -m pytest -q --tb=short tests/test_ui_handlers.py
  tests/test_ui_mount.py tests/test_image_contents.py tests/test_jobs_api.py
  tests/test_comp_api.py tests/test_comp_service.py tests/test_comp_schema.py
  tests/test_comp_estimate.py tests/test_comp_bands.py
  tests/test_api_route_extraction.py tests/test_api_auth_gate.py
  tests/test_auth_api.py tests/test_route_table_guard.py
  tests/test_openapi_contract.py`: **137 passed**, zero skipped, one warning,
  48.73s pytest; exit 0, 54.38s runner.
- `employer-browser scripts/check_ui_review_context_browser.py`: actual Chrome
  **30/30 checks** (includes shared API/UI-host check), exit 0, 32.75s runner.
  Captured-mail org login, real saved role/empty pool/materialized board,
  advisory explanations, wrapped prior benchmark, page reload, failed board
  read/no stale shortlist and explicit recovery pass. Added comp 503/missing
  benchmark/no stale band and explicit navigation recovery pass. Shared report
  plain/polished, historical/unknown/missing evidence, ownership, reload/404
  recovery and Instant-check input refusal remain covered; no console errors or
  uncaught exceptions. Chrome needs existing CDN internet; this is not an
  offline browser or live-provider/empirical-quality result.
- `http-journey scripts/smoke_r4_s1_t3a.py`: **87/87**, exit 0, 35.50s runner.
  Extended existing public-surface check delivers declared employer module
  anonymously with exact bytes/JS type and unrelated-path 404 on both starts.
  Existing employer tenant/foreign-key/CSRF, empty/materialized pools, consent,
  wrapped advisory comp, saved role/overview/match/comp and session/ledger/
  feature/portal/revocation/erasure contracts pass across two graceful lifespans.
- Review strengthened the same HTTP journey to compare the **complete board
  response** across restart as well. `http-final scripts/smoke_r4_s1_t3a.py`:
  **87/87**, exit 0, 20.81s runner, including exact board and comp equality.
  Both owned servers exit 0 and dispose SQL at revision0029. Browser reload
  proves a new document; graceful process-restart proof comes from HTTP.
- `node scripts/check_ui_bindings.js`: **589 bindings /18 states**, all resolve.
  All shipped JS plus changed checker/Node suite and extracted inline logic
  pass `node --check` (includes `frontend/api.js` and `frontend/support.js`).
- `compile -m compileall -q src/app/main.py tests/test_ui_mount.py
  scripts/smoke_r4_s1_t3a.py scripts/check_ui_review_context_browser.py`:
  exit 0, 0.26s runner.
- `full-reviewed` defaults to `-m pytest -q --tb=short`: **3540 passed,
  505 skipped, 127 warnings in 656.32s (0:10:56)**; exit 0, 663.57s runner.
  Existing Starlette/httpx and SQLite reflection/autogenerate warnings;
  optional/environment skips do not prove omitted cases. No application or
  pytest-collected code changed during this run; only the standalone HTTP
  harness's stronger board assertion was added, separately rerun and reviewed.

No new PostgreSQL gate applies: SQL/constraints/transactions/migrations are
unchanged. Synthetic fixtures prove mechanics, not scoring accuracy, calibrated
compensation, live providers or media/codecs. Advisory/human review, domain
independence, style versus factual evidence, consent and erasure remain intact.

### Implementation self-review

Same-agent review of baseline `cbf6c17` plus the HTML/new module, loader/checker,
mount/static allowlist and extended existing offline/browser/HTTP harnesses
checks specification compliance and correctness separately. All acceptance
criteria map to the observed tests above. Original four fields and both complete
view blocks compare text-identically; expected HTML comparison confines edits
to module composition/declaration, mapping delegation and dead samples/comment.
Python AST comparison permits only `employer-roles.js` in UI_ASSETS; the ordered
API/auth fixture and all other code remain unchanged.

Review checks class initialization/deferred state reads, detached receiver and
per-instance resources, mapping precedence, first/saved/fallback role selection,
read-only requests/manual recovery, empty/consent/error distinctions, numeric
zero/missing and unknown bands, wrapped/legacy comp, units/median clamp/prior/
k-floor/no-band and advisory wording, navigation callers, anonymous static
confinement and Docker frontend packaging contract. No blocking product finding
remains. One validation gap was found: restart did not compare the complete
board body. The added assertion and final 87/87 HTTP run close it. This is
self-review, not independent review.

`implementation-review -I .pytest_cache/review_r4_s1_t4h.py`: exit 0, 1.87s.
After the board assertion, `implementation-review-final -I
.pytest_cache/review_r4_s1_t4h.py --review-strengthened-http`: exit 0, 1.82s.
Only that harness hash changed; all 18 other reviewed hashes matched. All
19 final source/harness/contract hashes, syntax and moved-body/main comparisons
are recorded for final preservation review. Baseline 730 tracked file hashes
protect unrelated files and working data; local artifacts are excluded.

### Distinct final completion self-review and publication

After required validation and completion records, a distinct final same-agent
self-review examined baseline `cbf6c17` plus the exact fourteen staged files:
HTML/new employer module, named static allowlist, existing Node/checker/browser/
HTTP entry points, mount test, feature overview, handoff, roadmap, PI/evidence
and active T4 parent. Specification review confirms all six acceptance items,
the bounded extraction/sample retirement, observed browser versus HTTP evidence,
unchanged API/auth fixture, evidence ownership and I-only next pointer, with
T4/F13/sprint/PI still open.

Correctness review rechecks class initialization and deferred state access,
explicit helpers, view precedence, detached handlers and per-instance selected
roles/pending board/comp resources, first/saved/fallback selection, read-only
requests/manual recovery, empty/consent/error distinctions, missing/zero/unknown
risk, wrapped/legacy comp, units/median/prior/k-floor/no-band wording, advisory
human review, shared navigation/lifecycle callers, confined static serving and
packaging. No blocking product finding remains. This is a distinct final
self-review, not independent review.

`completion-review -I .pytest_cache/review_r4_s1_t4h.py --staged`: exit 0,
2.11s runner. All four original handlers and complete data/value blocks,
expected HTML and main AST comparison, JS syntax, 19 reviewed hashes and exact
fourteen-file staged contents pass. No working data/secrets/local artifacts
are staged. Initial final preservation found an extra blank line at EOF in
FEATURE_STATUS.md; that prose-only whitespace was removed and the affected
checks rerun before publication. No application tests require rerunning for
this documentation fix. `completion-review-final -I
.pytest_cache/review_r4_s1_t4h.py --staged`: exit 0, 2.19s runner. Final
preservation (`preservation-reviewed -I .pytest_cache/verify_r4_s1_t4h.py`):
exit 0, 1.50s runner; 717 unrelated tracked files, working DB and 19 reviewed
hashes unchanged, 300 local Markdown links/anchors valid, staged/tracked/source
whitespace pass. Review-record prose was separately checked for observed
evidence, scope and status accuracy.

Scoped task commit **`32d504c`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`cbf6c17` to `32d504c`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`32d504c0678d78c08ff90c8c654f3178f7d46bb4`**. Working tree was clean.

This two-file documentation-only confirmation records verified publication in
the handoff and this section. Separate final same-agent self-review against
`32d504c` checks the exact prose diff, actual remote evidence, open T4 parent and
I-only next pointer; no blocking finding remains. Scoped links, whitespace,
preservation and the unchanged 19 reviewed source/harness/contract hashes are
checked before publication. Application code remains at the validated state;
no application tests are rerun for prose. The final response reports the verified
remote SHA after this confirmation's commit/push. No I work, working-data change,
demo restart or deployment occurred.

### Handoff

Exact next: **R4-S1-T4I - Shared display and dead-code cleanup**, not started.
Define the bounded contract from remaining shared display/default/helper callers
in the existing T4 record next session; preserve module composition/lifecycle,
all planes, live data and missing/error/advisory states. Stop after H publication.

## <a id="r4-s1-t4"></a>R4-S1-T4 - Extract frontend components and remove dead handlers

Status: done (2026-10-23; split before implementation, 2026-10-22). PI-R4 / R4-S1;
F13. Prerequisite: [T3](#r4-s1-t3), done/published.

Extract one cohesive frontend area per session while preserving the existing
plain-script/DC runtime, auth/CSRF, tenant/subject boundaries, request recovery
and advisory/human-review behavior. Remove only proven dead code in that area.
No bundler, runtime rewrite, backend behavior, data migration or visual redesign
is implied. Each child requires offline behavior tests, full pytest, bindings,
syntax/static serving checks, actual migrated-scratch Chrome and separate reviews.
Passing bindings are not browser execution. Keep this parent open until all
selected screen modules and dead-code cleanup have their required evidence.

| Child | Bounded area | Status |
|---|---|---|
| [T4A](#r4-s1-t4a) | Operator-account handlers and view values | Done (2026-10-22); child owns evidence |
| [T4B](#r4-s1-t4b) | Organization administration handlers and view values | Done (2026-10-22); child owns evidence |
| [T4C](#r4-s1-t4c) | Curation handlers and view values | Done (2026-10-22); child owns evidence |
| [T4D](#r4-s1-t4d) | Evaluation/report handlers and view values | Done (2026-10-22); child owns evidence |
| [T4E](#r4-s1-t4e) | Screening handlers and view values | Done (2026-10-23); child owns evidence |
| [T4F](#r4-s1-t4f) | Candidate portal and authentication UI logic | Done (2026-10-23); child owns evidence |
| [T4G](#r4-s1-t4g) | Interview handlers and view values | Done (2026-10-23); child owns evidence |
| [T4H](#r4-s1-t4h) | Employer roles and compensation UI logic | Done (2026-10-23); child owns evidence |
| [T4I](#r4-s1-t4i) | Shared display and dead-code cleanup | Done (2026-10-23); child owns evidence |

A-I contracts, implementation/validation evidence, reviews and publication
records are owned by their linked child sections. I is the final bounded child:
all selected screen areas are extracted, shared display composes their existing
factories directly, and proven unused handlers/defaults/helpers are retired.
Required evidence is complete for each child; no generic runtime rewrite or
unbounded cleanup was included. The shared styles/formatters and actual
boot/state/loading/lifecycle/navigation/file-reader/row-cache callers stay in
the HTML intentionally; moving them to another wrapper would not simplify them.

Only I completes this session, closing T4. The parent contract is preserved
here and its active file retired after inbound links are updated. I owns this
session's full/focused pytest, actual multi-plane/employer/interview Chrome,
migrated HTTP/graceful restart, preservation and separate completion review.
Prior child evidence is historical, not a new execution. F13/sprint/PI stay
open for the separate **R4-S1-Q - Sprint integration review**, not started.

## <a id="r4-s1-t4i"></a>R4-S1-T4I - Shared display and dead-code cleanup

Status: done (2026-10-23); final child of [T4](#r4-s1-t4), now done.
Baseline `1ab03bd`, clean `main` tracking `origin/main`. Only I completes this
session; F13/sprint/PI remain open for R4-S1-Q. Working data preserved and demo
not restarted. This is cleanup with passing characterization, not a defect
reproducer or an independent review.

### Contract specified before implementation

When any plane boots, signs in or changes screens/theme/domain, shared display
must resolve the same live identity, navigation, page flags, styles, advisory
copy, empty/error states and callbacks. Simplify `renderVals()` composition and
remove only proven dead shared paths: the unused `nodeDot` helper, overwritten
account/organisation/search defaults and obsolete orgName design prop, and the
always-false sample banner plus its styling/registry/API text export. Compose
the eight extracted areas directly in the current precedence, removing the
now-unnecessary `liveVals()` wrapper. Retain the small shared display/style
helpers in the HTML; a new shell class/factory is unnecessary. Do not rewrite
the runtime, module APIs, request handling, loading/lifecycle/navigation, backend,
SQL/migrations or UI design. No demo restart, deployment or live-provider claim.

Acceptance and validation:

1. Before/after offline characterizations in the existing evaluation suite cover
   boot/login/verify, every app screen and all three planes, correct live account
   and org-form values despite prototype props, search visibility, advisory
   placement, page flags, API base, theme/domain and detached shared callbacks.
   Same-class instances retain independent theme/domain and module resources.
   This is cleanup with passing characterization, not a defect reproducer.
2. Keep module mapping precedence, shared state and lifecycle exact. Search
   declarations, template/callers and all shipped modules before removal; retain
   live helpers/callbacks. Replace obsolete test metadata assertions with actual
   rendered-operation assertions already owned by their existing suites.
3. Actual migrated-scratch Chrome uses all planes, navigation/theme, saved
   report/reload/errors and candidate portal/consent/devices/erasure; extend the
   existing evaluation journey for shared shell assertions. Run employer review
   context Chrome and combined interview Chrome for extracted callers/advisory
   and media cleanup. Binding/syntax checks alone are not browser execution.
4. Migrated scratch HTTP delivers exact HTML/API script bytes with the static
   allowlist intact and retains owned/foreign/consent flows across graceful
   restart. Extend the existing public-surface check in `smoke_r4_s1_t3a.py`;
   use fake providers and captured mail without working storage or .env.
5. Run focused UI/auth/route/packaging pytest, full pytest, all shipped/inline JS
   syntax, bindings, changed Python compile, links/diff and data/unrelated-file
   preservation. No new PG gate: SQL/constraints/transactions are unchanged.
6. Record implementation self-review, completion evidence and a distinct final
   staged self-review. Fold the completed T4 parent/child contracts into existing
   PI-R4 evidence and fix inbound links; publish scoped reviewed changes and
   verify remote. Stop after I/T4 publication; do not start R4-S1-Q here.

### Implementation and behavior preservation

`renderVals()` directly composes the same shared shell, auth/evaluation,
screening/interview/operator/organization/curation/portal/employer mappings in
the original order, with final search/API-base values retaining precedence.
The redundant `liveVals()` wrapper is gone. The same state, composed module
factories, boot/session/unmount/pagehide/navigation, request loading, row/cache,
file reader and detached callbacks remain; no new shell abstraction is added.

Caller searches and shipped-source declaration inventory found `nodeDot` as
the only unused top-level helper. It is removed; live style/formatting helpers
remain. The initial accountName/accountInitial/orgName/search values were always
overwritten by live mappings; those defaults and the unused orgName design prop
are removed. The empty MOCK_SCREENS registry made the sample banner unreachable
on every screen. Its template branch, style, three view metadata properties,
API.MOCK_NOTE text export and stale comments are retired. API credentials/CSRF,
session generations, request methods/timeouts/body handling are text-identical.
Four obsolete flag assertions are removed from existing suites; their real
server-row/status/report/session assertions remain. No backend, allowlist,
schema/scorer/store/SQL/migration or visual redesign occurs.

Four new cases extend `scripts/test_ui_evaluate.js`: all 17 screen flags across
all three planes with search/advisory placement and no requests from rendering;
boot/login/verify shell visibility; actual identity/org draft/API base despite
prototype props and missing/failed profile; and stable detached theme/domain
callbacks with separate same-class state. Existing per-module pending-state,
consent/erasure/error/read-recovery and report/interview tests remain.
`node --test scripts/test_ui_evaluate.js`: **38/38** before (420.60ms) and after
(441.31ms), zero skipped/failed. No failing defect is claimed for this cleanup.

The local comparison harness executes the existing binding fixtures against
baseline and current shipped source. **18 complete render bags** retain all live
values and callback shapes; only mockChip/mockNote/isMockScreen are excluded
as intentionally retired. Behavioral callback execution is tested separately;
this comparison is not browser execution. The remaining **586 bindings /18
states** resolve, down from 589 only because the three dead banner bindings are
removed. No old sample/live mapping remains for selected screens.

### Commands and observed validation

Python commands use `.resume/Scripts/python.exe`. The ignored sanitized runner
`.pytest_cache/run_r4_s1_t4i.py <tag> <Python args>` removes inherited DEE config,
selects a nonexistent config file, clears model/GitHub keys, uses localhost
GitHub refusal/null or captured mail and project paths. All journeys use
synthetic data, fake providers and disposable SQLite migrated to 0029; no .env,
working DB, external mail or demo restart. Local helpers/logs stay ignored.

- `focused -m pytest -q --tb=short tests/test_ui_handlers.py
  tests/test_ui_mount.py tests/test_image_contents.py
  tests/test_api_route_extraction.py tests/test_api_auth_gate.py
  tests/test_auth_api.py tests/test_route_table_guard.py
  tests/test_openapi_contract.py`: **111 passed**, zero skipped, one warning,
  106.86s pytest; exit 0, 123.20s runner. The eight existing offline Node suites
  retain operation/ownership/error/media assertions; imported suite counts
  overlap and are not extra unique tests.
- `shared-browser scripts/check_ui_evaluate_browser.py`: actual Chrome,
  **48/48 plus shared API/UI-host 1/1**, exit 0, 81.66s runner. Added live identity,
  current-plane search/navigation and theme switch/restore in organisation,
  operator and candidate shells. Existing captured OTP signup/sign-in/refusal,
  saved reports/PDF/domain, feedback, uncertain writes, 403/401/503/network/
  deadline, reload/read-only recovery, actor changes, device revoke, contact,
  consent/access and erasure flows pass with no uncaught console exceptions.
- `employer-browser scripts/check_ui_review_context_browser.py`: actual Chrome
  **30/30** including shared host check, exit 0, 73.67s runner. Saved role,
  empty/materialized board, advisory factual/style/unknown/insufficient context,
  missing/error/read recovery, wrapped comp/prior, document reload and board/
  comp 503 recovery pass; no uncaught console errors.
- `interview-browser scripts/check_ui_interview_integration_browser.py`:
  actual Chrome **40/40 plus shared host 1/1**, exit 0, 118.13s runner. Typed/
  synthetic microphone/mixed channels, actual MediaRecorder bytes, saved state,
  repeated-keyword insufficient evidence, advisory v2/historical/unknown content,
  consented summary/redaction/revocation, question/actor ownership, late media/
  navigation/reload/signout cleanup and errors pass. Its Windows process restart
  is forced; graceful process-restart proof is the HTTP journey. Synthetic
  media/fake ASR are not live-provider/codec or empirical-quality validation.
- `http-journey scripts/smoke_r4_s1_t3a.py`: **91/91**, exit 0, 100.90s runner.
  Extended existing public-surface checks serve exact HTML/API script bytes,
  declared JS assets/type and unrelated-path 404 on both lifespans. Owned versus
  foreign employer, CSRF/session precedence, consent/revocation/erasure, portal/
  ledger/features and saved role/board/comp responses survive graceful restart;
  both owned servers exit 0 and dispose SQL at revision 0029.
- `node scripts/check_ui_bindings.js`: **586/18**, all resolve. Implementation
  review runs `node --check` on every shipped JS asset (including api/support),
  every existing test_ui Node suite, checker and extracted inline logic.
- `compile -m compileall -q scripts/smoke_r4_s1_t3a.py
  scripts/check_ui_evaluate_browser.py`: exit 0, 0.38s runner.
- `full-reviewed` defaults to `-m pytest -q --tb=short`: **3540 passed,
  505 skipped, 127 warnings in 1128.85s (0:18:48)**; exit 0, 1139.43s runner.
  Existing Starlette/httpx and SQLite reflection/autogenerate warnings;
  optional/environment skips do not establish omitted cases. All application,
  test and harness code remained unchanged during this run.

No new PostgreSQL gate applies: SQL/constraints/transactions/migrations are
unchanged. Chrome requires existing CDN internet and is not an offline runner.
Fakes prove mechanics, not calibrated compensation or measured factual/interview
accuracy. Advisory/human review, domain independence, truthful polished writing,
content-only interview assessment, tenant isolation and consent/erasure persist.

### Implementation self-review

Same-agent specification review covers baseline `1ab03bd` plus the HTML/API
cleanup, screening comment and existing checker/offline/browser/HTTP changes.
All six criteria map to observed evidence; T4 closes only because A-I evidence
is complete, with R4-S1-Q/F13/sprint/PI still open. Historical results are not
represented as new validation. The parent is folded under its stable anchor,
and child/PI/handoff links target the evidence owner instead of an inactive file.

Correctness review checks mapping evaluation/overwrite order, unchanged class
field initialization and shared lifecycle, detached callbacks and separate
instance state, live identity instead of props, neutral missing/error states,
plane navigation/search/advisory, theme/domain, module resource lifetimes,
request credentials/CSRF/deadlines/generations, anonymous static confinement and
packaging. Searches confirm retired paths had no remaining production callers;
all retained top-level helpers have callers. No blocking findings remain.
This is self-review, not independent review or a sprint integration review.

`implementation-review -I .pytest_cache/review_r4_s1_t4i.py`: exit 0, 6.39s runner.
Expected HTML transform permits only the specified shared cleanup; exact API
comparison permits only retired text metadata. Shared state/lifecycle/navigation
and module factories remain unchanged. Shipped/test/checker/inline JS syntax,
18-state live-value comparison and **25 reviewed source/harness/contract hashes**
pass. Baseline 731 hashes protect unrelated files and working data.

### Distinct final completion self-review and publication

After required checks and completion records, a distinct final same-agent
self-review examined baseline `1ab03bd` plus the exact sixteen staged files:
HTML/API shared cleanup, screening comment, existing checker/offline/browser/
HTTP harness changes, feature overview, handoff, roadmap, PI/evidence and the
retired completed T4 task file. Specification review confirms all six acceptance
items, A-I evidence and bounded parent closure, preserved contract/anchors and
inbound links, Q-only next pointer and F13/sprint/PI still open. It does not
claim a new sprint gate or independent review.

Correctness review separately rechecks direct mapping evaluation/overwrite
order, class initialization/shared lifecycle, detached callbacks and per-instance
resources, live identities/drafts and missing/error states, all-plane flags/
navigation/search/advisory and theme/domain, unchanged API credentials/CSRF/
timeouts/generations, module resource cleanup, retired paths' caller inventory,
static confinement and packaging. No blocking finding remains.

`completion-review -I .pytest_cache/review_r4_s1_t4i.py --staged`: exit 0,
3.61s runner. Expected HTML/API comparison, all shipped/test/checker/inline
syntax, 18 complete live-value bags, 25 reviewed hashes and exact sixteen-file
staged contents pass. The completed parent deletion is deliberate and its
contract/child evidence links are preserved in this file; no working data,
secrets or local artifacts are staged.

Initial completion preservation caught an extra blank line at evidence EOF;
that documentation-only whitespace was removed and affected checks rerun.
`preservation-final -I .pytest_cache/verify_r4_s1_t4i.py`: exit 0, 1.49s runner;
715 unrelated tracked files, working DB and 25 reviewed hashes unchanged,
290 scoped local Markdown links/anchors valid, tracked/staged/source whitespace
pass. Review-record prose is checked separately for observed evidence, scope
and status accuracy before publication. Application tests need no rerun for
prose.

Scoped task commit **`e7d7bc1`** was created; `git -c
credential.https://github.com.username=RevanParimi push` (with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) exited 0, advancing main from
`1ab03bd` to `e7d7bc1`. Verification compared local HEAD with `git -c
credential.https://github.com.username=RevanParimi ls-remote origin refs/heads/main`:
both were **`e7d7bc11c31cb8e7cf65f1d974ef3543a128dc9c`**. Working tree was clean.

This two-file documentation-only confirmation records verified publication in
the handoff and this section. Separate final same-agent self-review against
`e7d7bc1` checks the exact prose diff, actual remote evidence, completed T4 anchor
and Q-only next pointer, with F13/sprint/PI open; no blocking finding remains.
Scoped links, whitespace, preservation and all 25 reviewed source/harness/
contract hashes are checked before publication. Application code remains at
the validated state; application tests are not rerun for prose. The final
response reports the verified remote SHA after this confirmation's commit/push.
No Q work, working-data change, demo restart or deployment occurred.

### Handoff

Exact next: **R4-S1-Q - Sprint integration review**, not started. Read its PI-R4
section, WORKFLOW and T1-T4 evidence. Test/review the combined production
composition on migrated scratch storage in its own session; do not start it
during I/T4 publication. Stop after this publication.

## <a id="r4-s1-q"></a>R4-S1-Q - Sprint integration review

Status: done (2026-10-23). Prerequisites: [T1](#r4-s1-t1),
[T2](#r4-s1-t2), [T3](#r4-s1-t3), [T4](#r4-s1-t4), all done.
Scope: only this sprint gate. The acceptance contract was specified in PI-R4
before editing the validation harness; no product defect has been reproduced
and no application implementation change is included.

### Contract and integration mode

Boot final production composition on migrated scratch storage, evaluate,
materialize/search and use candidate portals with two subjects/employers; shut
down gracefully and restart without losing saved reports, portal identity or
search state. Current consent revocation must mask historical search, erasure
must invalidate the subject and its report while preserving the survivor.
Each lifespan must share one SQL factory/reused services, close owned provider
transports exactly once, dispose/detach SQL and avoid Chroma with default and
retired settings. Preserve the full ordered 102-operation OpenAPI/auth fixture,
anonymous-plane refusals, actual entry/script delivery and private-asset refusal.
Actual Chrome must exercise the eight extracted screen areas, auth navigation,
reload/errors and console exceptions. Require focused/full pytest, applicable
PostgreSQL lock/migration and real HTTP gates, static checks, preservation,
implementation self-review and a distinct final completion self-review.

Extend the existing SQL smoke's `composition_checks` mode and expose it through
`scripts/smoke_r4_s1_t1b.py --integration` (also `--postgres`). T1B's provider
wrapper now composes T2's existing Chroma guard around the same default app;
no copied server launcher or extra app container. On both process starts, real
anonymous HTTP reads the OpenAPI document and entry page, checks each declared
local script against its actual bytes/content type and refuses protected planes
and private/retired assets. The second schema must equal the first. The existing
evaluation/audio, SQL lifecycle, actor/consent/erasure and provider-close checks
remain, with default/legacy Chroma events asserted across both lifespans.

No production source, schema, dependency, scorer or frontend behavior changes.
This adds a repeatable integration acceptance journey; an initial red product
reproducer is inapplicable because this task validates the completed sprint.
New checks assert actual requests, saved state and lifecycle events. Existing
offline regressions retain the constituent defect reproducers and failure paths.

### Implementation self-review

Reviewed state: `18caf49` plus the two smoke-script changes, with the T1-T4
combined call paths. Reviewed the service/engine ownership diff, lazy wrappers,
default/fake builders and lifespan; final router assembly/shared principal-CSRF
dependencies and evaluation/search/portal boundaries; entry script/factory and
value precedence, shared navigation/unmount and extracted request/media cleanup.
Used the T1-T4 contracts/evidence to map acceptance and reviewed the applicable
changes/callers, rather than re-running the historical audit.

Specification: the same production builders serve both starts and all moved
surfaces; fake SDK/HTTP adapters replace external effects only. PostgreSQL and
browser gates remain separately identified. Correctness/maintenance: borrowed
resources remain caller-owned, late/failed/canceled cleanup and actor checks
have existing behavioral regressions; no parallel ownership registry or runtime
framework was added. The smoke's Chroma guard wraps the same app before owned
providers are created; shutdown assertions run after real lifespan completion.
No blocking finding in this pass. It is same-agent self-review, not independent
review, and does not establish measured quality, general speedup or zero leaks.

### Validation evidence

Sanitized runner: `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_q.py <tag>
<Python args>`; omitted arguments run `-m pytest -q --tb=short`. It clears inherited
`DEE_` settings/keys, pins a nonexistent config plus null/loopback providers and
uses project `src`/root paths. HTTP/browser harnesses select migrated disposable
storage and explicitly pin external effects. Combined HTTP and Chrome app
children run outside the working directory; the cookie/CSRF contract uses the
root directory with the sanitized runner's config/key pins and captured mail.
Logs: `.pytest_cache/r4-s1-q-<tag>.txt`.
Baseline hashes cover 730 tracked files; local logs/screenshots/runners are
ignored artifacts, not portable environment setup or committed candidate data.

| Gate | Actual command/result |
|---|---|
| Focused | Runner `focused -m pytest -q --tb=short tests/test_services_features.py tests/test_service_lifecycle.py tests/test_api_route_extraction.py tests/test_route_table_guard.py tests/test_ui_mount.py tests/test_ui_handlers.py tests/test_provenance.py tests/test_config.py tests/test_smoke_harness.py`: **225 passed, 1 warning, 85.17s**, exit 0 |
| Provenance/config/posture | Runner `provenance -m pytest -q --tb=short tests/test_provenance_runtime.py tests/test_boot_config.py tests/test_cookie_posture.py`: **41 passed, 9.63s**, exit 0 |
| Combined migrated SQLite HTTP/graceful restart | Runner `http scripts/smoke_r4_s1_t1b.py --integration`: **45/45**, exit 0; exact report/portal/search persistence, shared SQL and owned provider cleanup, default/retired-settings Chroma refusal, actual HTTP API/UI surface |
| Evaluation/portal/shared shell Chrome | Runner `evaluate-browser scripts/check_ui_evaluate_browser.py`: **48/48** plus host **1/1**, exit 0 |
| Operator accounts Chrome | Runner `users-browser scripts/check_ui_admin_users_browser.py`: **29/29** plus host **1/1**, exit 0 |
| Organization administration Chrome | Runner `orgs-browser scripts/check_ui_admin_orgs_browser.py`: **28/28** plus host **1/1**, exit 0 |
| Curation HTTP/Chrome/graceful restart | Runner `curation-browser scripts/smoke_curation_activation.py --browser`: **53/53**, exit 0 |
| Screening Chrome | Runner `screening-browser scripts/check_ui_screening_extraction_browser.py`: **24/24**, exit 0 |
| Cookie/CSRF HTTP contract | Runner `csrf-contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0 |
| Interview Chrome | Runner `interview-browser scripts/check_ui_interview_integration_browser.py`: **40/40** plus host **1/1**, exit 0 |
| Employer roles/compensation/report Chrome | Runner `employer-browser scripts/check_ui_review_context_browser.py`: **30/30**, exit 0 |
| PostgreSQL configured lock/migration selection | `.resume/Scripts/python.exe .pytest_cache/run_r4_s1_q_postgres.py` creates/owns a fresh disposable cluster; `-m pytest -q --tb=short tests/test_service_lifecycle.py tests/test_services_features.py tests/test_job_store_match.py tests/test_features_current_consent.py tests/test_interview_lifecycle_concurrency.py tests/test_interview_erasure_concurrency.py tests/test_screening_erasure_concurrency.py tests/test_candidate_login_binding_migration.py tests/test_curation_storage_migration.py`: **226 passed, 59 skipped, 21 warnings, 436.73s**, exit 0 |
| Combined migrated PostgreSQL HTTP/graceful restart | Same owned runner invokes `scripts/smoke_r4_s1_t1b.py --postgres --integration`: **45/45**, exit 0; actual PostgreSQL storage/shared lifecycle and owned transport cleanup; fresh schema migrated to 0029 |
| Full pytest | Runner `full` (project `-m pytest -q --tb=short`): **3540 passed, 505 skipped, 127 warnings, 962.41s**, exit 0, on the reviewed source/harness state |
| Static | `node scripts/check_ui_bindings.js`: **586 bindings / 18 states**, all resolve. `node --check frontend/api.js`, `frontend/support.js`, each of the **10** frontend JS files and the entry document's extracted inline logic (`.pytest_cache/r4-s1-q-inline.js`) pass. `git diff --check` passes |

PostgreSQL **18.6**, READ COMMITTED, Asia/Calcutta. The selected tests include
backend-neutral and SQLite-only composition fixtures; the configured count is
not a claim that every passed case used PostgreSQL. Parameterized PG cases use
actual competing connections/current-consent, lifecycle/erasure and constraints,
with existing 0028/0029 up/down/up coverage; SQLite cases and skips do not prove
PG behavior. The separate migrated HTTP run uses PostgreSQL throughout. PG logs
use `.pytest_cache/r4-s1-q-pg-<tag>.txt`; the local distribution/owned runner is
not a portable setup guarantee. The owned cluster stopped successfully (exit 0;
`.pytest_cache/r4-s1-q-pg-runtime.json`). CPython **3.13.11** is the project environment.

Browser actions use actual Chrome/CDP, scratch HTTP and saved data; selected
timeout/network/503/media cases inject faults and synthetic device streams.
Browser document reload is distinct from HTTP's real graceful process restart.
Synthetic providers/media demonstrate mechanics, not live-provider/ASR/codec
compatibility or empirical assessment quality. Chrome still depends on CDN
internet. No CI, Docker, fresh dependency installation or deployment claim.

### Completion review and publication

All acceptance gates are complete. The new integration mode and existing
constituent regressions pass with no acceptance-blocking product finding.
Warnings are the existing Starlette TestClient deprecation and SQLAlchemy/
Alembic expression-index reflection limits. Skipped optional/environment cases
do not establish omitted behavior. No fresh dependency/CI/provider/quality claim.
R4-S1 and the bounded F12/F13 gates close; PI-R4 remains open for S2/S3.

Completion records update the PI, traceability/feature summary, roadmap and
handoff. After those records and all gates, a distinct final same-agent
self-review inspected the exact staged eight-file diff against `18caf49`:
`scripts/smoke_r4_s1_t1a.py`, `scripts/smoke_r4_s1_t1b.py`, `FEATURE_STATUS.md`,
`docs/PROGRESS.md`, `docs/ROADMAP.md`, and delivery `PI-R4.md`, `README.md`,
`EVIDENCE-R4.md`. Specification review maps every acceptance criterion to the
recorded requests/state/lifecycle/browser evidence and leaves S2/S3 pending.
Correctness/maintenance review rechecks composition mode selection, fake SDK
ownership, guard order, actual script/schema comparisons, restart semantics,
cleanup/privacy and exclusions. It corrected an overbroad prose claim about
child working directories: the cookie/CSRF contract runs from root under the
sanitized runner; it still uses migrated scratch SQL/captured mail. No product
change or blocking finding remains. This is self-review, not independent review.

`.resume/Scripts/python.exe .pytest_cache/review_r4_s1_q.py` confirms **722**
unrelated tracked files and working DB match the 730-file baseline, all **646**
reviewed source/harness hashes remain unchanged and **15** added local links/
anchors resolve. Staged whitespace and explicit scope checks pass; no secrets,
working storage or ignored artifacts are staged. Subsequent edits are completion
prose only, so application checks need no rerun. Commit/push and remote
verification follow this distinct final review.

Scoped task commit **`0d3309d`** was created and pushed to `origin/main` using
`git -c credential.https://github.com.username=RevanParimi push` with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never` (exit 0). Local HEAD and
`git -c credential.https://github.com.username=RevanParimi ls-remote origin
refs/heads/main` both returned **`0d3309d1ab7f56f232d471b4b9ac2611703d208f`**;
the working tree was clean. This two-file documentation-only confirmation
records verified publication in the handoff and Q evidence. Its separate final
self-review against `0d3309d` checks the exact publication prose, actual remote
result, completed Q/bounded F12/F13 scope and pending S2-T1 pointer. No blocking
finding remains; source hashes, storage preservation, links and whitespace are
checked before publication. Application checks are not rerun for prose. The
final response reports the verified remote SHA after this confirmation.

### Handoff

Exact next: **R4-S2-T1 - Make batch leases and counts truthful**, not started.
Only Q is completed in this session. No working storage migration, demo restart,
deployment, ignored-artifact cleanup or next-task implementation occurred.

## <a id="r4-s2-t1a"></a>R4-S2-T1A - Claim work when it starts and acknowledge failure writes

Status: done (2026-10-23). Bounded child of R4-S2-T1 / F14;
prerequisite R4-S1-Q done. The parent remains open for T1B. The contract was
specified inline in PI-R4 before implementation, splitting scheduling and
failure acknowledgment from terminal outcome/expiry/idempotence work.

### Contract and behavior

Previously, a process request claimed the whole capped chunk before awaiting
the first evaluation. Later items aged while waiting, blocked another worker
and remained leased after task cancellation. Both ingest-refusal and unexpected
exception paths incremented `failed` even if the store rejected the failure write.

Claim exactly one item immediately before ingest, with a fresh clock reading,
up to the existing per-call cap. While one provider is paused, another worker
can consume unstarted items. Count those two failure paths only on acknowledged
`fail=True`; stop after a refused failure/completion write so this call cannot
immediately reclaim the same item. Ordinary acknowledged failures still let
other work continue. Preserve quota/auth/CSRF, tenant/subject ownership, current
consent/erasure, input-retention and advisory/API contracts. Task cancellation
propagates with at most its active item outstanding; committed work persists
and a later authorized call uses existing timeout/private-input recovery.

No schema, store predicate, expiry policy, scorer, API shape or frontend source
changes. A false completion still increments a failed-attempt counter; terminal
acknowledgments, active expiry and persistence/idempotence remain **T1B**. Active
lease theft can duplicate provider work; existing partial ingest/report commits
can survive unsuccessful completion. Do not infer exactly-once model calls or
globally deduplicated report persistence. HTTP disconnect/navigation does not
promise server cancellation. Durable continuation remains R4-S2-T4; event-loop/
aggregate resource work remains T3, and existing exception-detail diagnostics
remain R4-S3-T2. A closes none of those parent/backlog contracts.
The fresh-clock regression retains the present acceptance of an active item
past timeout when no reclaimer has won. B must define that expiry policy and
adjust the first item's outcome accordingly while preserving a fresh lease for
the next item; A does not treat timestamp equality as proof of an unexpired lease.

### Red regressions and implementation review

Initial `red -m pytest -q --tb=short tests/test_screening_service.py -k
'waiting_provider or refused_failure or cancellation_leaves'`: **4 failed,
4 skipped, 20 deselected**, exit 1. All failures are behavioral: two processing
items instead of one, refused writes counted as two failures, and two leases
left after cancellation. No broken fixture/import is counted as reproduction.

The later clock/completion-stop/API tests also run against a scratch copy of
`src` with only the original `a3e9232:src/app/screening/service.py` restored.
`red-extra -m pytest -q --tb=short -o
pythonpath=.pytest_cache/r4-s2-t1a-before/src tests/test_screening_service.py
tests/test_screening_batches_api.py -k 'next_item_lease or refused_completion_stops
or two_process_requests'`: **3 failed, 2 skipped, 48 deselected, 1 warning**,
exit 1, for stale next-item timing, additional work after refused completion and
preclaimed concurrent-request work. The working source was never rolled back.

The production fix changes only `ScreeningService.process`: a capped loop claims
one item with the current time, both failure paths require acknowledgment and
false completion stops the loop. It retains the existing input/report callbacks
and propagating cancellation; no heartbeat/retry framework or new scheduler.

Implementation self-review: `a3e9232` plus the service, tests and smoke diff.
Specification mapping covers paused evaluations, actual lease theft, per-call/
retry counts and cancellation/recovery. Reviewed quota/auth-before-claim order,
one-at-a-time acquisition/fresh clock, both failure returns, completion refusal
and existing ingest/erasure callbacks. The smoke extends the existing harness;
two owned OS app processes share migrated scratch storage, only one synthetic
evaluation pauses, and `finally` releases its gate before graceful shutdown.
No blocking A finding. B's outcome/expiry/duplicate-cost limits remain explicit.
Same-agent self-review is not independent review.

### Validation evidence

Sanitized runner: `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1a.py
<tag> <Python args>`; omitted arguments run full `-m pytest -q --tb=short`.
It clears inherited `DEE_` configuration/keys and pins missing config, null/
loopback providers and project paths. App/browser harnesses additionally pin
their scratch storage and fake/captured effects; real app children use scratch
working directories. Logs: `.pytest_cache/r4-s2-t1a-<tag>.txt`. Local evidence,
runner/snapshot artifacts and synthetic data stay ignored. Baseline: 730 tracked
files. CPython 3.13.11/project dependencies remain in use.

| Gate | Actual command/result |
|---|---|
| Broader focused | Runner `focused-final -m pytest -q --tb=short tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_batches_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_durable_input.py tests/test_screening_unresolved_input.py tests/test_screening_report_input.py tests/test_screening_refusal_retention.py tests/test_api_route_extraction.py`: **173 passed, 75 skipped, 3 warnings, 93.10s**, exit 0, before two additional service regressions; unchanged production fix |
| Final service/API selection | Runner `lease-final -m pytest -q --tb=short tests/test_screening_service.py tests/test_screening_batches_api.py`: **47 passed, 6 skipped, 1 warning, 18.31s**, exit 0, includes all new cases |
| Migrated two-process SQLite HTTP/retry/graceful restart | Runner `http scripts/smoke_r4_s1_t3d.py --leases`: **27/27** plus reused cookie/CSRF HTTP **31/31**, exit 0; two OS app processes, held fake evaluation, exact `(2,0,1)` / `(1,0,0)` responses, three advisory queue results, retry no-op, cross-tenant refusal and exact saved queue/summary after restart; three graceful lifespans |
| Actual screening Chrome | Runner `browser scripts/check_ui_screening_extraction_browser.py`: **24/24**, exit 0; actual intake/queue/feedback/deletion, second intake/reload and injected read failure/recovery; no console exceptions |
| PostgreSQL-configured selection | `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1a_postgres.py` owns a fresh disposable cluster; `-m pytest -q --tb=short tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_batches_api.py tests/test_screening_erasure_concurrency.py`: **97 passed, 3 skipped, 1 warning, 204.97s**, exit 0 |
| Migrated two-process PostgreSQL HTTP/retry/graceful restart | Same owned runner invokes `scripts/smoke_r4_s1_t3d.py --postgres --leases`: **27/27** plus cookie/CSRF HTTP **31/31**, exit 0; actual PG storage shared by two OS app processes; three graceful lifespans, exact concurrent queue/summary and retry no-op after restart |
| Full pytest | Runner `full` (project `-m pytest -q --tb=short`): **3547 passed, 511 skipped, 127 warnings, 1247.30s**, exit 0, on the reviewed production/test/harness state |
| Static | `node scripts/check_ui_bindings.js`: **586 bindings / 18 states**, all resolve; `node --check frontend/api.js`, `frontend/support.js` and `git diff --check` pass |

An initial focused invocation named nonexistent `tests/test_screening_input_erasure.py`
and exited 4 with no tests; the corrected `focused-final` invocation above owns
the actual evidence. Initial red failures are expected defect reproduction.
Fakes and synthetic waits/media prove mechanics, not live-provider compatibility,
assessment quality, cost savings or latency/resource bounds. Browser actions and
HTTP simulation are separate; Chrome still requires the existing CDN internet.
No fresh dependency, CI, Docker or deployment claim. No migration gate is added
because A changes no schema/constraint/store transaction predicate.

The PostgreSQL-configured selection includes backend-neutral/SQLite-only
fixtures as well as the new database-parameterized lease cases and existing
actual competing-connection/erasure cases. Its entire pass count is not a count
of PostgreSQL tests; SQLite and skips do not prove PG semantics. PostgreSQL
18.6 uses READ COMMITTED/Asia/Calcutta. PG logs use
`.pytest_cache/r4-s2-t1a-pg-<tag>.txt`; the owned local distribution/runner is not
a portable environment setup guarantee. No new schema migration is required.
The owned cluster stopped successfully (exit 0), recorded in
`.pytest_cache/r4-s2-t1a-pg-runtime.json`; all owned application/browser processes
also stopped. The HTTP helper's reused contract runs 31 checks; its standalone
host-start check is outside that reused call and is not claimed as an extra test.

### Completion review and publication

All A acceptance gates are complete, with no unresolved A blocker. Warnings are
the existing Starlette TestClient deprecation and SQLAlchemy/Alembic expression-
index reflection limits. Skips do not prove omitted cases. No source changes
follow the reviewed/tested state; subsequent completion edits are prose only.

Completion records fold A under this stable evidence anchor and update its PI
status, feature/product notes, roadmap and short handoff. The parent T1, F14,
sprint and PI stay open. After that completion record and all required gates, a
distinct final same-agent self-review inspected the exact staged ten-file diff
against `a3e9232`: screening `service.py`, `test_screening_service.py`,
`test_screening_batches_api.py`, `smoke_r4_s1_t3d.py`, `SCREENING.md`,
`FEATURE_STATUS.md`, `PROGRESS.md`, `ROADMAP.md`, delivery `PI-R4.md` and this
evidence file. Specification review checks every A criterion against real saved
state, failure/cancellation interleavings, API/OS-process/browser evidence and
the explicitly pending B contract. Correctness/maintenance review rechecks
claim timing/cap, both failure acknowledgment branches, refusal stop, quota/auth
order, closure/cancellation behavior, unchanged ingest/erasure callbacks, fake
gate ownership/release and PG scratch-schema isolation/cleanup. No blocking A
finding remains. B's legacy completion/expiry/persistence cases remain explicit;
this is self-review, not independent review.

`.resume/Scripts/python.exe .pytest_cache/review_r4_s2_t1a.py` verifies **720**
unrelated tracked files and the working DB against the 730-file baseline, all
**646** reviewed source/test/harness hashes unchanged and **7** added local
links/anchors resolved. Staged scope/whitespace checks pass; secrets, working
data and ignored artifacts are excluded. Only completion prose changes after
validation, including clarifying the handoff's prior PG runner label. No
application rerun is needed for prose. Commit/push and remote verification
follow this distinct final review.

Scoped task commit **`7e7ee34`** was created and pushed to `origin/main` with
`git -c credential.https://github.com.username=RevanParimi push` under
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never` (exit 0). Local HEAD and
`git -c credential.https://github.com.username=RevanParimi ls-remote origin
refs/heads/main` both returned **`7e7ee3417427bbd21c4a3cc3f6e9083dffd7348b`**;
the working tree was clean. This two-file documentation-only confirmation
records verified publication in A evidence and the handoff. Its distinct final
self-review against `7e7ee34` checks the exact publication prose, actual remote
result, A-only completion, open parent/F14 and pending B pointer; no blocking
finding remains. Preservation/source hashes, local links and whitespace are
checked before publishing this confirmation. Application checks need no rerun
for prose. The final response reports the verified remote SHA after confirmation.

### Handoff

Exact next: **R4-S2-T1B - Fence terminal outcomes and define expiry/idempotence**,
not started. Read its inline PI contract and A's explicit legacy completion/
expiry cases before implementation; preserve input/report erasure lock ordering.
Only A completed in this session. Working data, existing demo and unrelated
work remain preserved; no deployment, cleanup or next-task implementation.

## <a id="r4-s2-t1b1"></a>R4-S2-T1B1 - Distinguish acknowledged terminal outcomes

Status: done (2026-10-24). Bounded child of R4-S2-T1B / T1 / F14;
prerequisite A done. B was split inline in PI-R4 before implementation: B1
fixes terminal acknowledgment without changing the input/report transaction
protocol; B2 owns expiry and persistence/idempotence. Only B1 is in this
session. B, T1, F14, sprint and PI remain open.

### Contract and implementation

Previously `complete=False` meant either a newly committed erasure-failed item
or no write at all (stolen/deleted/already-terminal item or cleanup losing its
lease after rollback). `process` counted both as one failed attempt. Replace
that boolean with internal `CompletionOutcome.DONE/FAILED/REFUSED`. DONE and
FAILED acknowledge only this attempt's newly committed transition; REFUSED
acknowledges neither. The service counts DONE as processed and FAILED as
failed. Both erasure cleanup and refusal retain the existing stop behavior;
refusal increments neither counter and cannot immediately reclaim/rebill the
same item or count a newer worker's outcome.

Acceptance: success counts once; candidate/resume/report erasure cleanup counts
one failure only after its lease-checked cleanup commits; stolen/deleted/
already-terminal completion or cleanup losing its lease counts nothing and
cannot overwrite newer state. Repeated completion is refused. Unrelated
constraint errors propagate. Preserve raw/private input scrubbing and retry,
existing lock ordering, advisory/tenant/CSRF behavior and public JSON shape.

The production change touches only the screening store's completion return
contract and the service's outcome accounting (plus a misleading lease comment).
Both success and erasure cleanup commit before returning an acknowledgment;
cleanup's conditional update still reasserts the lease after rollback. No new
schema, SQL predicate, timeout, ingest/report callback, identity/scoring logic
or frontend change. All production completion callers and existing smoke/test
wrappers were inspected; wrappers forward the new outcome.

A matching expired lease still can write until reclaimed. Input/report commits
can precede terminal refusal, and retries can create duplicate reports. Duplicate
provider work/cost also remains possible. B2 must define expiry at input/report/
terminal boundaries, including lock waits and rollback, and idempotent persisted
results without breaking erasure lock ordering or private input lifetime.
This task establishes no hard expiry deadline, atomic report completion,
globally unique reports, heartbeat, durable continuation or exactly-once model
calls. Those exclusions were explicit before implementation.

### Reproduction and implementation self-review

Sanitized runner: `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1b1.py
<tag> <Python args>`; omitted arguments run project `-m pytest -q --tb=short`.
It clears inherited DEE config/keys, pins missing config and null/loopback
providers, and sets project paths. HTTP/browser harnesses additionally use
fake/captured effects, scratch storage and scratch app working directories.
Logs: `.pytest_cache/r4-s2-t1b1-<tag>.txt`; local runner/snapshot/synthetic
artifacts remain ignored. Baseline `dc4c4fe`: 730 tracked files.

Pre-fix runner `red -m pytest -q --tb=short tests/test_screening_service.py
tests/test_screening_erasure_concurrency.py -k 'refused_completion_stops or
does_not_count_lost_completion'`: **2 failed, 1 skipped, 60 deselected,
1 warning, 8.49s**, exit 1. Both failures are real lease replacement incorrectly
counted as failed despite no failed transition, through service and API. The API
regression replaces its old constant-false stub with a real store reclamation.
No import/fixture failure is counted as reproduction.

Initial focused four-module run: **78 passed, 22 skipped, 1 warning, 55.64s**.
Added winner/rollback races selection: **6 passed, 6 skipped, 61 deselected,
1 warning, 13.24s**, before the final commit-refusal cases. The final selection
below owns all final tests. New assertions distinguish an active replacement,
its committed done/failed result, cleanup refused after rollback, preserved
private retry input, repeated completion and success/cleanup commit rollback.
Existing erasure order, actual PostgreSQL locks, unrelated constraint failures,
cancellation and retry cases remain in the final selections.

Implementation same-agent self-review: `dc4c4fe` plus screening `store.py`,
`service.py`, existing service/store/erasure test modules and
`smoke_r4_s1_t3d.py`. Specification review maps each B1 criterion to saved
state/count assertions; no B2 or parent completion is inferred. Correctness/
maintenance review checks commit-before-acknowledgment, cleanup rowcount after
rollback, explicit outcome comparisons, stop/cap behavior, unchanged erasure
scrubbing/lock order and completion callers/wrappers. The scratch-only
terminal gates pause one worker after report save, release in `finally` and
publish gate metadata atomically. A second OS app process takes the stale lease
and commits a replacement, or executes real candidate-erasure HTTP before
terminal persistence. No blocking B1 finding. This is self-review, not an
independent review.

Resumed review on 2026-10-24 verified the retained 642 code hashes against the
working tree and the working DB against the 730-file baseline before changing
anything. The interrupted final gates had not passed: broader focused was
**1 failed, 181 passed, 84 skipped, 3 warnings, 182.26s**, and full pytest was
**1 failed, 3553 passed, 518 skipped, 127 warnings, 1025.75s**. Both exposed the
same missed completion adapter below. Those failed runs are not final proof.

Resumed implementation self-review findings against `dc4c4fe` plus the B1 diff:

- **Medium, `tests/test_screening_report_input.py`, interrupted-completion HTTP
  adapter:** after committing `store.fail`, it still returned the old `False`.
  The new service correctly counted neither enum outcome, so the existing
  retry/count regression failed. Return `CompletionOutcome.FAILED` after the
  actual acknowledged failure and assert exact response and persisted counts.
  This fixes the test adapter's contract, with no compatibility boolean branch
  added to production. The initial all-wrapper review missed this adapter.
- **Low, `scripts/smoke_r4_s1_t3d.py`, `run`:** the terminal-mode flag reused
  `outcomes`, later overwritten by the saved employer outcome list. As a result
  `--leases` unintentionally ran terminal scenarios. Rename the flag to
  `terminal_outcomes`; preserve the saved list and verify both explicit modes.

The resumed review rechecks all screening completion callers, the full
store/service/test/harness diff, commit-before-acknowledgment and cleanup
rowcount after rollback. No production B1 blocker found; the two validation
findings are fixed. Final gates use the revised test adapter/harness and the
unchanged production fix. Source hashes are recorded separately in
`.pytest_cache/r4-s2-t1b1-reviewed-source-resumed.json`. B2's expiry and partial/
duplicate report persistence remain explicit; this is same-agent self-review.

### Final validation

All resumed final reviewed-state gates completed on 2026-10-24.
The runner prefix below is `.resume/Scripts/python.exe
.pytest_cache/run_r4_s2_t1b1.py`; commands/log tags with `-resumed` are the
2026-10-24 reruns on the corrected test adapter/harness. Production code was
unchanged across these reruns. Source hashes bind the reviewed/tested state.

| Gate | Actual command/result |
|---|---|
| Broader focused | Runner `focused-resumed -m pytest -q --tb=short tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_batches_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_durable_input.py tests/test_screening_unresolved_input.py tests/test_screening_report_input.py tests/test_screening_refusal_retention.py tests/test_api_route_extraction.py`: **182 passed, 84 skipped, 3 warnings, 108.20s**, exit 0 |
| Migrated two-process SQLite terminal outcomes / HTTP / graceful restart | Runner `http-resumed scripts/smoke_r4_s1_t3d.py --outcomes`: **36/36** plus reused cookie/CSRF HTTP contract **31/31**, exit 0; real lease replacement acknowledges one result, stale worker returns `(0,0,0)`, candidate-erasure cleanup returns `(0,1,0)`, exact saved queue/summary survive restart |
| Scheduling-only mode regression | Runner `leases-resumed scripts/smoke_r4_s1_t3d.py --leases`: original **27/27** plus HTTP contract **31/31**, exit 0; terminal scenarios stay opt-in after flag/list separation |
| Actual screening Chrome | Runner `browser-resumed scripts/check_ui_screening_extraction_browser.py`: **24/24**, exit 0; rendered intake, queue, feedback, deletion, second intake, saved reload and injected read failure/recovery; no console exceptions |
| PostgreSQL-configured selection | `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1b1_postgres.py` owns a fresh disposable cluster and invokes `-m pytest -q --tb=short tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_batches_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_report_input.py`: **135 passed, 4 skipped, 2 warnings, 238.49s**, exit 0 |
| Migrated two-process PostgreSQL terminal outcomes / HTTP / graceful restart | Same owned runner invokes `scripts/smoke_r4_s1_t3d.py --postgres --outcomes`: **36/36** plus cookie/CSRF HTTP contract **31/31**, exit 0; actual PG storage shared by both app processes, exact terminal responses, saved queue/summary, retry no-op and restart |
| Full pytest | Runner `full-resumed` (project `-m pytest -q --tb=short`): **3554 passed, 518 skipped, 127 warnings, 913.09s**, exit 0 |
| Static | `node scripts/check_ui_bindings.js`: **586 bindings / 18 states**, all resolve; `node --check frontend/api.js`, `node --check frontend/support.js` and `git diff --check` pass |

SQLite and PostgreSQL application journeys use migrated disposable storage and
two OS application processes, with three gracefully closed lifespans including
restart. HTTP simulation is separate from Chrome. Synthetic providers/gates
prove mechanics, not live-provider compatibility, assessment quality, measured
latency or reduced cost. Chrome still needs the existing CDN internet. No new
schema, constraint or migration; no deployment/CI/runtime-alignment claim.

The PostgreSQL-configured selection includes backend-neutral/SQLite-only
fixtures as well as actual PG competing-connection/rollback/erasure cases;
its entire pass count is not a PostgreSQL test count. Existing populated report
migration roundtrips run in that selection; B1 adds no schema migration.
SQLite and skipped lock cases are not PG evidence. PostgreSQL **18.6** uses
**READ COMMITTED / Asia/Calcutta**. PG logs use
`.pytest_cache/r4-s2-t1b1-pg-<tag>.txt`; the portable distribution metadata and
owned runner are local artifacts, not a portable environment setup guarantee.
The owned cluster stopped successfully (exit 0), recorded in
`.pytest_cache/r4-s2-t1b1-pg-runtime.json`; all owned application/browser
processes from the completed journey gates stopped as well.

### Completion review and publication

All B1 acceptance gates are complete, with no unresolved implementation-review
blocker. CPython **3.13.11** and the existing dependencies remain in use.
Warnings are the existing Starlette TestClient deprecation and SQLAlchemy/
Alembic expression-index reflection limits; skips do not prove omitted cases.
No project code/test/harness changes follow the reviewed/tested source snapshot;
completion edits are prose only and need no application rerun.

Completion records consolidate the B1 contract/evidence here and update PI
status, product/feature notes, the short handoff and roadmap. B/T1/F14/sprint/PI
remain open. A distinct final self-review of the exact staged thirteen-file
scope was performed after the completion record and all required checks,
against `dc4c4fe`: screening `store.py` and `service.py`, existing
`test_screening_store.py`, `test_screening_service.py`,
`test_screening_erasure_concurrency.py`, `test_screening_report_input.py`,
`smoke_r4_s1_t3d.py`, `FEATURE_STATUS.md`, `SCREENING.md`, `PROGRESS.md`,
`ROADMAP.md`, delivery `PI-R4.md` and this evidence record.

Specification review maps every B1 criterion to committed state/counts, repeated
completion, active/settled replacement, rollback, erasure/retry and the actual
SQL/HTTP/browser gates; B2 and all parent statuses stay open. Correctness/
maintenance review rechecks commit-before-acknowledgment on both outcomes,
lease reassertion/rowcount after rollback, no acknowledgment on commit failure,
all completion callers/adapters, explicit enum comparisons, unchanged erasure
scrubbing/lock order, input retention, quota/tenant/CSRF/advisory/JSON contracts,
and opt-in fake gates with release-before-shutdown. The two earlier validation
findings are resolved and covered by the final green checks. No blocking B1
finding remains. This distinct final review is self-review, not independent
review; active expiry and partial/duplicate report/provider work remain B2.

`.resume/Scripts/python.exe .pytest_cache/review_r4_s2_t1b1.py --staged`
verifies **717** unrelated tracked files and the working DB against the
730-file baseline, all **642** reviewed code hashes unchanged, **8** added local
links/anchors resolved and exactly **13** scoped staged files. Staged whitespace
checks pass. Secrets, working data and ignored local artifacts are excluded;
only completion prose changes after validation. Commit/push and remote
verification follow this distinct final review; no B2 work starts here.

Scoped task commit **`bdf2cfb`** was created and pushed to `origin/main` with
`git -c credential.https://github.com.username=RevanParimi push` under
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never` (exit 0). Local HEAD and
`git -c credential.https://github.com.username=RevanParimi ls-remote origin
refs/heads/main` both returned **`bdf2cfba0167a9fe70be15f1f2af7b8e60c944ba`**;
the working tree was clean. Preservation and all reviewed code hashes still
matched. This two-file documentation-only confirmation records verified B1
publication here and in the handoff. Its distinct final self-review against
`bdf2cfb` checks the exact publication prose, actual remote result, B1-only
completion and pending B2/open parent statuses. No blocking finding remains.
Preservation/code hashes and the exact two-file staged scope/whitespace checks
pass; no new local links are added. Application checks need no rerun for prose.
Confirmation publication follows this review. The final response reports the
verified remote SHA after confirmation.

### Handoff

Exact next after B1 completion/publication: **R4-S2-T1B2 - Fence expiry and make
batch persistence idempotent**, not started. Refine its remaining contract before
implementation. B/T1/F14/sprint/PI remain open. Preserve working storage and the
existing demo; B1's HTTP/browser fakes prove mechanics, not live-provider
behavior or assessment quality.

## <a id="r4-s2-t1b2a"></a>R4-S2-T1B2a - Fence terminal transitions at lease expiry

Status: done (2026-10-24). Prerequisite B1 complete/published at `ffbb645`.
B2 was split inline in PI-R4 before implementation; only B2a is in this session.
B2b owns input/report fencing and saved-report reuse. B2/B/T1/F14/sprint/PI
remain open.

### Contract and implementation

Previously a matching lease could commit success/failure past timeout, including
after a database lock wait or rollback before erasure cleanup. Terminal done,
fail and erasure cleanup now require that processing lease, a fresh application
clock after acquiring its lock, and another clock check after terminal writes,
before commit. Refuse/roll back on expiry; the service counts neither outcome
and stops the call. Erasure cleanup reacquires/rechecks after rollback. Keep
the existing strict stale inequality: age equal to timeout is eligible; greater
age is expired. The last check admits a commit under the held lock; clock reads
and database commit are not atomic. No physical commit/HTTP delivery deadline
or clock-skew guarantee is established.

PostgreSQL uses a conditional `SELECT FOR UPDATE`; SQLite uses a conditional
no-op update to acquire its writer lock before reading the clock. Refusal leaves
status, public result fields and raw/private input unchanged by that terminal
transaction; previously committed erasure/retention is not undone. Complete and
fail retain their B1 outcome/boolean contracts. Service calls pass their clock
callback, rather than a pre-wait snapshot; direct stores default to current UTC.
The existing `at` remains the caller's event timestamp. No new schema/migration,
heartbeat, claim/read inequality, identity/scoring or frontend source change.

Preserve erasure lock order, input TTL/scrubbing/retry, cancellation, per-call
cap, auth/CSRF/tenant/advisory and public JSON shape. Input/report callbacks
still check lease identity without expiry. Their earlier commits and duplicate
provider/report work can survive terminal refusal. Atomic report/terminal
persistence and report reuse remain B2b; B2a closes no parent acceptance gate.

### Reproduction and implementation self-review

Sanitized runner: `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1b2a.py
<tag> <Python args>`; omitted args run `-m pytest -q --tb=short`. It clears
inherited DEE config/keys, pins missing config, null/loopback providers and
project paths. App/browser harnesses additionally use scratch storage, scratch
app working directories and fake/captured effects. Logs use
`.pytest_cache/r4-s2-t1b2a-<tag>.txt`; snapshots/runners/synthetic artifacts stay
ignored. Baseline: 730 tracked files, with the B2 split contract already written.

Pre-fix `red -m pytest -q --tb=short tests/test_screening_erasure_concurrency.py
-k 'requires_unexpired or expiry_after_write or rechecks_expiry'`: **5 failed,
4 passed, 9 skipped, 41 deselected, 1 warning, 9.79s**, exit 1. Pre-fix
`red-lock -m pytest -q --tb=short tests/test_screening_erasure_concurrency.py
-k terminal_waiting`: **2 failed, 2 skipped, 59 deselected, 1 warning, 3.73s**,
exit 1. Failures are actual expired done/failed/cleanup commits or committed
writes after waiting, with live/equality positive examples still passing.

Supplemental `red-final -m pytest -q --tb=short -o
pythonpath=.pytest_cache/r4-s2-t1b2a-code-before/src
tests/test_screening_erasure_concurrency.py tests/test_screening_service.py
-k 'requires_unexpired or expiry_after_write or rechecks_expiry or
terminal_waiting or expired_failure or expired_provider_result'`: **11 failed,
4 passed, 15 skipped, 75 deselected, 1 warning, 27.81s**, exit 1. The scratch
copy contains tracked current source with only `ffbb645` screening store/service
restored; working source was never reverted. This also proves the service's
expired completion/failure count and stop/recovery regressions. An earlier
supplemental run started before its scratch copy was ready and used current
source (**15 passed, 15 skipped, 75 deselected**); it is not pre-fix proof. The
owned copy helper was stopped, then tracked-only preparation completed before
the valid `red-final` run. No import/fixture failure counts as reproduction.

Initial terminal suite: **31 passed, 32 skipped, 1 warning, 24.90s**. Initial
broader selection: **195 passed, 97 skipped, 3 warnings, 91.19s** before adding
the second cleanup-expiry phase; final selection below owns all final cases.
Historical direct-store fixtures now inject their explicit terminal clock,
while service calls use their own dynamic clock. The existing unrelated-error
injector ignores the new PostgreSQL lock SELECT and still asserts IntegrityError
propagation/unchanged data.

Implementation self-review against `ffbb645` plus screening store/service,
six existing screening test modules, `smoke_r4_s1_t3d.py` and the PI contract:
every B2a criterion maps to saved status/input/counts, equality, no reclaimer,
actual competing locks, post-write rollback, erasure rollback/cleanup, stop and
later recovery. Rechecked lock order, fresh callback reads at both boundaries,
rollback before refusal, commit before acknowledgment, all terminal callers and
unchanged earlier callbacks. Conditional locks still require the matching
processing token; no queue read or default provider output is counted as a
commit. The smoke's opt-in gate is released in finally before process shutdown.
No blocking implementation finding; this is same-agent self-review, not
independent review. B2b's remaining persistence/cost risks stay explicit.

### Final validation

All final gates completed on 2026-10-24. Runner prefix is the sanitized runner
above; project code/test/harness hashes match the reviewed/tested snapshot.

| Gate | Actual command/result |
|---|---|
| Broader focused | Runner `focused-final -m pytest -q --tb=short tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_batches_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_durable_input.py tests/test_screening_unresolved_input.py tests/test_screening_report_input.py tests/test_screening_refusal_retention.py tests/test_api_route_extraction.py`: **196 passed, 98 skipped, 3 warnings, 147.96s**, exit 0 |
| Two-process SQLite expiry / HTTP / graceful restart | Runner `http-initial scripts/smoke_r4_s1_t3d.py --expiry`: **41/41** plus cookie/CSRF HTTP contract **31/31**, exit 0; no reclaimer is needed for expired `(0,0,1)`, pending queue has no public result links, later request recovers retained input, saves one queue result and exact state survives restart; includes prior scheduling/terminal/tenant/advisory checks |
| Actual screening Chrome | Runner `browser scripts/check_ui_screening_extraction_browser.py`: **24/24**, exit 0; rendered intake/queue/feedback/deletion, second intake, reload, injected read failure/recovery; no console exceptions |
| PostgreSQL-configured selection | Owned `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1b2a_postgres.py` creates a disposable cluster and invokes `-m pytest -q --tb=short tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_batches_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_report_input.py tests/test_screening_durable_input.py tests/test_screening_unresolved_input.py tests/test_screening_refusal_retention.py`: **251 passed, 9 skipped, 3 warnings, 387.75s**, exit 0 |
| Two-process PostgreSQL expiry / HTTP / graceful restart | Same owned runner invokes `scripts/smoke_r4_s1_t3d.py --postgres --expiry`: **41/41** plus cookie/CSRF HTTP contract **31/31**, exit 0; both OS app processes share actual PG storage; exact terminal responses, recovery, saved queue/summary and graceful restart |
| Full pytest | Runner `full` (project `-m pytest -q --tb=short`): **3568 passed, 532 skipped, 127 warnings, 955.87s**, exit 0 |
| Static | `node scripts/check_ui_bindings.js`: **586 bindings / 18 states**, all resolve; `node --check frontend/api.js`, `node --check frontend/support.js`, `git diff --check` pass |

Fakes and synthetic waits/media prove mechanics, not live-provider behavior,
quality, cost reduction or measured latency. HTTP simulation and Chrome are
separate; Chrome still requires CDN internet. SQLite and skips are not PG lock
evidence. No deployment, dependency/runtime alignment or CI claim.

The PG-configured selection includes backend-neutral and SQLite-only fixtures
as well as actual PostgreSQL tests; 251 passes is not a count of PG-only tests.
New lock tests observe the actual blocking backend PID before advancing the
clock and releasing the competing connection. Existing populated input/report
migration roundtrips also run; B2a adds no migration. PostgreSQL **18.6** uses
**READ COMMITTED / Asia/Calcutta**. PG logs use
`.pytest_cache/r4-s2-t1b2a-pg-<tag>.txt`; local runner/distribution metadata are
not portable environment setup guarantees. The owned cluster stopped with
exit 0, recorded in `.pytest_cache/r4-s2-t1b2a-pg-runtime.json`; completed HTTP/
browser processes stopped too. All owned validation processes have stopped.

### Completion review and publication

All B2a acceptance/validation gates are complete; no implementation-review
blocker remains. CPython **3.13.11** and existing dependencies remain in use.
Warnings are the existing Starlette TestClient deprecation and SQLAlchemy/
Alembic expression-index reflection limits; skips do not prove omitted cases.
Completion records fold the contract/evidence here and update PI status,
product notes, short handoff and roadmap. No project code/test/harness change
follows validation; later edits are prose only. B2/B/T1/F14/sprint/PI stay open.

A distinct final self-review was performed after all required checks and this
completion record, against `ffbb645` plus the exact staged fifteen-file scope:
screening `store.py`/`service.py`, `smoke_r4_s1_t3d.py`, existing screening
store/service/erasure/durable-input/unresolved-input/refusal-retention test
modules, `FEATURE_STATUS.md`, `SCREENING.md`, `PROGRESS.md`, `ROADMAP.md`,
delivery `PI-R4.md` and this evidence file.

Specification review maps every B2a criterion to saved state/input/counters,
equality, no-reclaimer expiry, actual competing connections, post-write and
erasure rollback, stop/recovery and the SQL/HTTP/Chrome gates. B2b and all parent
statuses remain open. Correctness/maintenance review rechecks conditional
processing-token locks, fresh callback reads after waits and writes, rollback
before refusal, cleanup lock reacquisition, commit before acknowledgment,
unchanged input TTL/erasure/lock order, all terminal callers, quota/tenant/CSRF/
advisory/JSON contracts, fixture clocks and opt-in gate release/shutdown.
The commit-admission boundary and earlier report/provider duplication remain
explicit; there is no physical commit deadline or complete persistence claim.
No blocking B2a finding remains. This distinct final review is self-review,
not independent review.

`.resume/Scripts/python.exe .pytest_cache/review_r4_s2_t1b2a.py --staged`
verifies **715** unrelated tracked files and the working DB against the
730-file baseline, **642** code hashes matching the reviewed/tested snapshot,
**6** added local links/anchors resolved and exactly **15** scoped staged files.
Staged whitespace checks pass. Secrets, working data and ignored artifacts are
excluded. Subsequent changes are completion prose only; application checks need
no rerun. Authorized commit/push and remote verification follow this review.
Working DB/demo remain preserved; no B2b work starts here.

Scoped task commit **`3c368d2`** was created and pushed to `origin/main` with
`git -c credential.https://github.com.username=RevanParimi push` under
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never` (exit 0). Local HEAD and
`git -c credential.https://github.com.username=RevanParimi ls-remote origin
refs/heads/main` both returned **`3c368d2303b9884eb33950eb682327a3a274c2a5`**;
the working tree was clean. Working DB, unrelated tracked files and all code
hashes still matched the baseline/reviewed snapshot. This two-file prose-only
confirmation records verified B2a publication here and in the handoff.
Its distinct final self-review against `3c368d2` checks the exact publication
prose, verified remote result, B2a-only completion and pending B2b/open parent
statuses. No blocking finding remains. Preservation/code hashes, exact two-file
staged scope and whitespace pass; no new local links are added. Application
checks need no rerun for prose. Confirmation publication follows this review;
the final response reports the verified remote SHA after confirmation.

### Handoff

Exact next after B2a completion/publication: **R4-S2-T1B2b - Fence input/report
persistence and reuse saved reports**, not started. Refine atomicity/retry and
expiry eligibility before implementation. B2/B/T1/F14/sprint/PI remain open.

## <a id="r4-s2-t1b2b1"></a>R4-S2-T1B2b1 - Fence input and report transaction admission

Status: done (2026-10-24). Prerequisite B2a is
complete/published. B2b was split in PI-R4 before implementation: this session
owns persistence admission; B2b2 owns saved-report reuse and remaining parent
acceptance. B2b/B2/B/T1/F14/sprint/PI remain open.

### Contract and implementation

A matching processing token previously admitted ingest/private-input and report
transactions after lease timeout without a replacement claimant. Both callbacks
now require a fresh clock after the conditional item write acquires its lock,
and another after private-input operations/flushes before returning to commit.
Equality at timeout remains eligible; greater age refuses. Direct callers
default to current UTC; the service passes its dynamic clock. The caller raises
IngestRefused on refusal, rolling back the entire candidate/resume/extraction/
input or report/binding transaction. Terminal expiry then refuses too: the
service stops without counting success/failure or immediately replaying work.

The existing separate ingest, report and terminal commits remain. A transaction
admitted while live may survive later expiry. These are commit-admission clock
checks under held locks, not an atomic physical commit/delivery deadline or
cross-worker clock-skew guarantee. Optional fingerprinting retains its existing
separate subject/erasure checks; earlier ingest/fingerprint commits may survive
report/terminal refusal. Later authorized process calls recover through
the existing timeout, retained-input TTL and erasure rules; no automatic extra
provider retry is added.

Input refusal preserves the prior raw/private input and original created_at;
report refusal preserves an existing report binding and earlier ingest.
Preserve subject -> item -> private-input lock order, generation/erasure
barriers, tenant checks, present consent, public JSON/advisory behavior, per-call
cap and cancellation. No schema/migration, heartbeat, identity/scoring or
frontend change. Saved-report reuse is deliberately pending B2b2; duplicate
persisted reports and provider cost remain possible after a live report save
and later terminal refusal.

Acceptance maps to initial ingest, resume-bound retry and report-save durable
rows: live/equality/expired admission, actual competing SQLite/PostgreSQL locks,
and expiry after private-input writes/reads/flushes must roll back all changes
in that transaction. Service tests cover extraction/provider expiry, zero
counters, stop and later recovery. Migrated two-process HTTP/restart, actual
screening Chrome, focused/full pytest, static and separate self-reviews are
required. Existing populated input/report migration roundtrips remain in the
selected SQL suites; no new migration needs an additional roundtrip.

### Reproduction and implementation self-review

Sanitized runner: `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1b2b1.py
<tag> <Python args>`; omitted args run `-m pytest -q --tb=short`. It clears
inherited DEE settings/keys, uses missing config and null/loopback providers;
app/browser harnesses use migrated scratch storage and synthetic providers.
Logs use `.pytest_cache/r4-s2-t1b2b1-<tag>.txt`. Ignored runners, hashes and
synthetic artifacts remain local. Baseline: 730 tracked files, captured after
the pre-implementation PI split; working tree was clean before that split.

Pre-fix runner `red -m pytest -q --tb=short
tests/test_screening_erasure_concurrency.py -k persistence`: **9 failed,
6 passed, 15 skipped, 65 deselected, 1 warning, 36.97s**, exit 1. Each failure
is an expired transaction committing rather than refusing; live/equality
examples pass. Runner `red-service -m pytest -q --tb=short
tests/test_screening_service.py -k expired_persistence`: **2 failed, 2 skipped,
40 deselected, 16.47s**, exit 1. Input expiry still called the evaluator;
report expiry retained a report. Import/fixture failures are not reproduction.

Initial green runner `green -m pytest -q --tb=short
tests/test_screening_erasure_concurrency.py tests/test_screening_service.py
-k 'persistence or expired_provider'`: **18 passed, 18 skipped, 103 deselected,
1 warning, 21.47s**, exit 0. Implementation self-review then strengthened the
report cases to start with an existing bound report, so snapshots prove its
preservation on refusal, and clarified HTTP check labels. Final checks below
own that reviewed code state. Report-input direct-store fixtures pin their
historical clock; service tests still use the service's clock.

Implementation self-review against `e9a7f16` plus screening store/service,
existing erasure-concurrency/service/report-input tests, the screening smoke
and PI contract checked every criterion against saved rows, original TTL,
counts and recovery. All callback callers propagate refusal to rollback;
fresh clocks follow the potentially blocking conditional item write and final
private-input operations. Rechecked existing erasure lock order, report/tenant
binding predicates, commit before terminal acknowledgment, generation guard,
cancel/cap behavior and opt-in smoke gate release in finally. No blocking
implementation finding remains. This is self-review, not independent review.

### Final validation

All required gates completed on 2026-10-24. The 642 reviewed Python/JS/HTML/CSS
hashes match the validated code/test/harness state. Later changes are prose only.

| Gate | Actual command/result |
|---|---|
| Broader focused selection | Runner `focused -m pytest -q --tb=short tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_batches_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_durable_input.py tests/test_screening_unresolved_input.py tests/test_screening_report_input.py tests/test_screening_refusal_retention.py tests/test_api_route_extraction.py`: **213 passed, 115 skipped, 3 warnings, 197.72s**, exit 0; collected before final report-fixture strengthening/HTTP labels; final selection/full/PG below cover the final state |
| Final focused expiry regressions | Runner `focused-final -m pytest -q --tb=short tests/test_screening_erasure_concurrency.py tests/test_screening_service.py -k 'persistence or expired_provider'`: **18 passed, 18 skipped, 103 deselected, 1 warning, 27.20s**, exit 0, on the reviewed final code/test snapshot |
| Two-process SQLite persistence / HTTP / graceful restart | Runner `http scripts/smoke_r4_s1_t3d.py --persistence`: **53/53** plus cookie/CSRF HTTP contract **31/31**, exit 0; two app processes, expired ingest subject absent, expired report absent with earlier subject retained, zero outcome counts, pending queue without public result links, later recovery and exact queue/summary across graceful restart; also retains prior scheduling/terminal/tenant/advisory checks |
| Actual screening Chrome | Runner `browser-retry scripts/check_ui_screening_extraction_browser.py`: **24/24**, exit 0, **35.10s**; intake/queue/feedback/deletion, second intake, reload, injected read failure/recovery, no console exceptions. Initial identical runner `browser` was **23/24**, exit 1, **53.78s**: injected read-error text was not observed within its wait; recovery and other checks passed. Unchanged code passed the rerun; the cause of that intermittent browser observation remains unproven |
| PostgreSQL-configured selection | Owned `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1b2b1_postgres.py` creates a disposable cluster and invokes `-m pytest -q --tb=short tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_batches_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_report_input.py tests/test_screening_durable_input.py tests/test_screening_unresolved_input.py tests/test_screening_refusal_retention.py`: **285 passed, 9 skipped, 3 warnings, 421.91s**, exit 0 |
| Two-process PostgreSQL persistence / HTTP / graceful restart | Same owned runner invokes `scripts/smoke_r4_s1_t3d.py --postgres --persistence`: **53/53** plus cookie/CSRF HTTP contract **31/31**, exit 0; both app processes share actual PG storage and repeat expiry rollback, exact response/counts, later recovery, tenant/advisory and saved queue/summary restart assertions |
| Full pytest | Runner `full` (project `-m pytest -q --tb=short`): **3585 passed, 549 skipped, 127 warnings, 1036.11s**, exit 0 |
| Static | `node scripts/check_ui_bindings.js`: **586 bindings / 18 states**, all resolve; `node --check frontend/api.js`, `node --check frontend/support.js`, `git diff --check` pass |

Fakes and deterministic expiry gates prove mechanics, not live-provider
behavior, empirical quality, measured latency or cost reduction. HTTP simulation
and Chrome are separate; Chrome still requires CDN internet. SQLite and skips
are not PostgreSQL evidence. No deployment, runtime/dependency alignment or CI
claim. CPython **3.13.11** and existing dependencies remain in use. Warnings are
the existing Starlette TestClient deprecation and SQLAlchemy/Alembic expression
index reflection limits; skips do not prove omitted cases.

The PG-configured selection includes backend-neutral and SQLite-only fixtures;
285 is not a PG-only count. Each PostgreSQL lock-wait case observes the actual
blocking backend PID before advancing the clock and releasing the competing
connection. Existing populated input/report migration roundtrips run in the
selection. PostgreSQL **18.6**, **READ COMMITTED / Asia/Calcutta**; local logs
use `.pytest_cache/r4-s2-t1b2b1-pg-<tag>.txt`. Owned cluster stopped with exit 0,
recorded in `.pytest_cache/r4-s2-t1b2b1-pg-runtime.json`; completed HTTP/Chrome
and pytest processes stopped too. All owned validation processes have stopped.
Local distribution/runner metadata are not portable setup guarantees.

### Completion review and publication

All B2b1 acceptance/validation gates are complete and no implementation-review
blocker remains. Completion records fold the bounded contract/evidence here,
update PI/product status, the short handoff and roadmap. B2b/B2/B/T1/F14/sprint/
PI remain open for saved-report reuse and remaining mapped work. Working DB and
unrelated tracked files match baseline; demo remains untouched. No code change
follows final validation. A distinct final self-review of the exact staged
scope and authorized commit/push/remote verification follow this record.

A distinct final self-review was performed after the completed checks and
completion record, against `e9a7f16` plus the exact twelve-file staged scope:
screening store/service, the screening smoke, existing erasure-concurrency/
service/report-input tests, FEATURE_STATUS/SCREENING/PROGRESS/ROADMAP, PI-R4
and this evidence file. Specification review maps each B2b1 criterion to durable
rollback, live/equality/expiry, real lock waits, prior binding/original TTL,
zero counters/stop/recovery and SQL/HTTP/Chrome/full evidence. Only B2b1 closes;
saved-report reuse and all parent statuses remain open. The initial Chrome
observation miss is retained: its injected client-side GET response is outside
the modified ingest/report write path, and the unchanged rerun covers the
required rendered failure/recovery journey. No cause or UI fix is claimed.

Correctness/maintenance review rechecks all callback callers' rollback behavior,
fresh clocks after potentially blocking item writes and private operations,
unchanged subject/item/input lock order and generation guard, tenant/report
predicates, no TTL refresh or swept capability restoration, separate commits,
terminal acknowledgments, cap/cancellation and finally-released smoke gates.
Earlier commits, duplicate report/provider cost, optional fingerprint checks
and the commit-admission limitation remain explicit. No blocking B2b1 finding
remains. This later completion review is self-review, not independent review.

`.resume/Scripts/python.exe .pytest_cache/review_r4_s2_t1b2b1.py --staged`
verifies **718** unrelated tracked files/working DB against the 730-file
baseline, **642** code hashes matching the reviewed/tested snapshot, **6** added
local links/anchors and exactly **12** scoped staged files. Staged whitespace
checks pass; secrets, working data and ignored artifacts are excluded. Later
edits are completion prose only, requiring documentation/preservation checks
rather than another application rerun. Authorized scoped commit/push and remote
verification follow this final self-review. No B2b2 implementation starts here.

Scoped task commit **`8dbf168`** was created and pushed to `origin/main` with
`git -c credential.https://github.com.username=RevanParimi push` under
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never` (exit 0). Local HEAD and
`git -c credential.https://github.com.username=RevanParimi ls-remote origin
refs/heads/main` both returned **`8dbf1687912b6172602fde211834ff1f83b86940`**;
the working tree was clean. Working DB, unrelated tracked files and all 642
code hashes still matched baseline/reviewed snapshots. This two-file prose
confirmation records verified B2b1 publication here and in the handoff.

Its distinct final self-review against `8dbf168` checks the exact publication
prose, verified remote result, B2b1-only completion and pending B2b2/open parent
statuses. No blocking finding remains. Preservation/code hashes, exact two-file
staged scope and whitespace pass; no new local links are added. Application
checks need no rerun for prose. Confirmation publication follows this review;
the final response reports the verified remote SHA after confirmation.

### Handoff

Exact next after B2b1: **R4-S2-T1B2b2 - Reuse saved reports on authorized
recovery**. Refine saved-result metadata/authorization/atomicity/retry before
implementation; B2b/B2/B/T1/F14/sprint/PI remain open. No B2b2 work this session.

## <a id="r4-s2-t1b2b2a"></a>R4-S2-T1B2b2a - Preserve original private ingest facts

Status: done (2026-10-24). Prerequisite B2b1
complete/published. B2b2 was split in PI-R4 before implementation: this session
owns the private prerequisite; B2b2b owns authorized report reuse together with
binding protection. B2b2/B2b/B2/B/T1/F14/sprint/PI remain open.

### Contract and implementation

A bound report lacks the first ingest's matched_existing/matched_on/
duplicate_resume facts; reconstructing them from a retry changes history.
New private retry references now store precisely those three typed outcome
scalars plus version 1 in nullable JSON ingest_facts. Creation shares the
candidate/resume/extraction/input transaction and existing expiry/lease/tenant/
generation checks. Bound retries and report saves preserve facts and original
created_at. Historical NULL facts remain unknown, including after retry; no
inferred backfill. No text, contact hashes, identifiers, profile or report copy
is added. Public batch/result/queue/summary schemas and ordinary retry behavior
remain unchanged.

Facts live only with screening_item_inputs: completion, batch/subject/report
erasure and TTL sweep remove the same private row. Existing erasure lock order,
consent, advisory/human review, identity and scorer semantics remain. Migration
0030 adds only this nullable JSON column; downgrade drops only these new facts.
Re-upgrade preserves existing links/timestamps/data but leaves facts unknown.
Working storage is not migrated. Populated SQLite/PG tests preserve old report/
resume/input links, raw copies and erased absence across up/down/up; a genuine
post-upgrade ingest records new facts. The older input-table roundtrip now
unwinds/reapplies 0030 around its existing 0024/0025 roundtrip.

Twenty scratch smoke/browser head assertions advance to 0030; nineteen files
have only revision literal/label changes. The existing screening persistence
journey also captures synthetic private facts/timestamps immediately before
terminal completion, compares original/replacement checkpoints across app
processes and proves they do not enter public reads. It still proves current
report duplication is possible: reuse/protection remain B2b2b. Protecting a
binding alone would break current retries, so that protection ships with the
consumer in the next child. No exactly-once provider/result or parent closure
claim is made here.

### Reproduction and implementation self-review

Sanitized runner: `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1b2b2a.py
<tag> <Python args>`; omitted args run `-m pytest -q --tb=short`. It clears
inherited DEE config/keys, uses missing config and null/loopback providers;
HTTP/Chrome harnesses use isolated migrated scratch storage and fake effects.
Logs use `.pytest_cache/r4-s2-t1b2b2a-<tag>.txt`. Baseline: 730 tracked files,
captured after the PI split; tree was clean before the split. New migration is
the sole new tracked artifact. Local runners, hashes and synthetic captures stay
ignored.

Pre-fix runner `red -m pytest -q --tb=short
tests/test_screening_durable_input.py -k 'ingest_facts or ordinary_retry'`:
**4 failed, 3 skipped, 45 deselected, 1 warning, 30.11s**, exit 1. Failures
assert missing persisted facts for new/preexisting identities and HTTP ordinary
retry; no import/fixture errors count as reproduction. Initial `green -m pytest
-q --tb=short tests/test_screening_durable_input.py -k 'ingest_facts or
ordinary_retry or rollback'`: **7 passed, 4 skipped, 41 deselected, 1 warning,
11.38s**, exit 0, before final migration/lifetime assertions.

Implementation self-review against `63c73b4` plus models/store, migration 0030,
existing durable-input/report-input tests and scratch harness changes checks
each criterion against persisted facts, original TTL, retry/unknown behavior,
rollback/erasure/sweep, public non-disclosure and populated migrations. The
store writes only the private reference's initial insert; all existing guards,
flush/rollback and lock ordering remain. Migration has no default/backfill/FK
change. Head-only harness edits assert the actual new scratch head; their
individual journeys are not all claimed run. Report reuse and binding
protection remain explicitly pending. No blocking application finding remains.
This is self-review, not independent review.

Validation found one harness blocker: initial `http scripts/smoke_r4_s1_t3d.py
--persistence` passed the 31-check HTTP contract and early checkpoint assertions
but stopped on PermissionError reading a just-published input-expiry gate file
on Windows. The reader now polls absent/sharing-denied files within the existing
15-second deadline; finally still releases the gate and stops owned servers.
This is not an application data failure. HTTP rerun and script compilation
validate the fix. The final 643-code-file snapshot includes it. Application/
pytest sources were unchanged during these runs; pytest does not import this
standalone smoke script. The full run remains on the final application/tests;
the changed harness is rerun through its affected HTTP checks before closure.

### Final validation

All required gates completed on 2026-10-24 on the reviewed final application,
migration, test and harness state. Later edits are completion prose only.

| Gate | Actual command/result |
|---|---|
| Focused screening/migrations | Runner `focused -m pytest -q --tb=short tests/test_screening_durable_input.py tests/test_screening_report_input.py tests/test_screening_erasure_concurrency.py tests/test_screening_service.py tests/test_screening_batches_api.py tests/test_migrations.py`: **154 passed, 99 skipped, 18 warnings, 207.35s**, exit 0; final application/migration/test state |
| Two-process SQLite checkpoint / HTTP / graceful restart | Runner `http-final scripts/smoke_r4_s1_t3d.py --persistence`: **61/61** plus cookie/CSRF HTTP contract **31/31**, exit 0; original facts/TTL survive stolen/expired/report-refused attempts and cross-process recovery, private checkpoints absent from public reads, prior expiry/count/tenant/advisory checks and exact saved queue/summary survive restart |
| PostgreSQL-configured selection | Owned `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1b2b2a_postgres.py` invokes `-m pytest -q --tb=short tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_batches_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_report_input.py tests/test_screening_durable_input.py tests/test_screening_unresolved_input.py tests/test_screening_refusal_retention.py tests/test_migrations.py`: **307 passed, 9 skipped, 18 warnings, 515.78s**, exit 0 |
| Two-process PostgreSQL checkpoint / HTTP / graceful restart | Same owned runner invokes `scripts/smoke_r4_s1_t3d.py --postgres --persistence`: **61/61** plus cookie/CSRF HTTP contract **31/31**, exit 0; both actual PG app processes repeat original facts/TTL, public non-disclosure, expiry/refusal/counts, tenant/advisory and restart checks |
| Full pytest | Runner `full` (project `-m pytest -q --tb=short`): **3589 passed, 553 skipped, 127 warnings, 1484.19s**, exit 0 |
| Screening Chrome | Runner `browser scripts/check_ui_screening_extraction_browser.py`: **24/24**, exit 0, **55.81s**; rendered intake/queue/report/outcomes/deletion, second intake, reload and injected read-error recovery, no console exceptions |
| Static | `node scripts/check_ui_bindings.js`: **586 bindings / 18 states**, all resolve; `node --check frontend/api.js`, `node --check frontend/support.js`; project `-m compileall -q src/app/screening alembic/versions/0030_screening_ingest_facts.py scripts` and final smoke-script compilation; `git diff --check` pass |

Fakes/synthetic checkpoints prove mechanics, not live providers, measured cost,
latency or assessment quality. HTTP simulation and Chrome are separate; Chrome
still needs CDN internet. No deployment, working-store migration, dependency/
runtime alignment or CI claim. Missing/skipped cases are not evidence.

PG-configured tests include backend-neutral/SQLite fixtures, so 307 is not a
PG-only count. The actual PG fixtures exercise competing connections and
populated 0030 up/down/up, alongside existing input/report/erasure races.
PostgreSQL **18.6**, **READ COMMITTED / Asia/Calcutta**; owned disposable runner
logs use `.pytest_cache/r4-s2-t1b2b2a-pg-<tag>.txt`. Local distribution/runtime
metadata are not portable setup guarantees. Owned cluster stopped with exit 0,
recorded in `.pytest_cache/r4-s2-t1b2b2a-pg-runtime.json`; HTTP/Chrome/pytest
processes stopped too. All owned validation processes are stopped. Existing
CPython **3.13.11** dependencies remain; warnings are Starlette TestClient
deprecation and SQLAlchemy/Alembic expression-index reflection limitations.

### Completion review and publication

All B2b2a acceptance and validation gates are complete; the Windows gate-read
harness blocker is fixed and the affected HTTP/compilation checks pass.
Completion records fold the contract/evidence here and update PI/product
status, the handoff and roadmap. Working DB and unrelated tracked files match
baseline; demo was not restarted and no working-store migration occurred.
Only B2b2a closes. B2b2/B2b/B2/B/T1/F14/sprint/PI remain open. The distinct
final self-review of the exact staged scope and authorized publication follow
this completion record.

A distinct final self-review followed the completed checks and completion
record, against `63c73b4` plus the exact **31-file staged scope**: screening
models/store, migration 0030, durable-input/report-input tests, twenty scratch
harnesses, and FEATURE_STATUS/SCREENING/PROGRESS/ROADMAP/PI-R4/this evidence.
Specification review maps each criterion to original-versus-retry/unknown
facts, rollback and deletion, private API shape, original TTL, populated
SQLite/PG up/down/up, cross-process checkpoint observations, HTTP/restart,
Chrome and full pytest. Only this prerequisite closes; all parent statuses
and pending report-reuse/protection behavior remain explicit.

Correctness/maintenance review rechecks that only the initial private-reference
insert writes facts, validated outcomes supply the closed scalars, retries
cannot infer/replace them or refresh TTL, and erasure/sweep/completion remove
the same row. Lease/expiry/tenant/generation checks, lock order, public contracts,
consent/advisory/scoring and ordinary retries are unchanged. Migration changes
only the nullable column, has no default/backfill and preserves existing data;
downgrade's metadata loss is explicit. Nineteen harness files were verified
against exact revision-literal/label substitution; only screening adds logic.
Its synthetic checkpoint writes and bounded gate reads retain timeout/finally
shutdown behavior. The initial Windows read failure, fix and rerun are recorded.
No blocking B2b2a finding remains. This distinct completion review is self-review,
not independent review.

`.resume/Scripts/python.exe .pytest_cache/review_r4_s2_t1b2b2a.py --staged`
confirms **700** unrelated tracked files/working DB preserved against the
730-file baseline, **643** code hashes matching the final reviewed/tested
snapshot, **6** added local links/anchors and exactly **31** staged files.
Staged whitespace checks pass. The new migration is the sole added tracked
artifact; secrets, working data and ignored artifacts are excluded. No
application/migration/test/harness change follows final validation; remaining
publication edits are prose only. Authorized scoped commit/push and remote
verification follow. No next-child implementation starts here.

Scoped task commit **`71afb32`** was created and pushed to `origin/main` with
`git -c credential.https://github.com.username=RevanParimi push` under
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never` (exit 0). Local HEAD and
`git -c credential.https://github.com.username=RevanParimi ls-remote origin
refs/heads/main` both returned **`71afb3233e23ca9054f5e97379815b0d78a11483`**;
the working tree was clean. All 643 code hashes, working DB and 700 unrelated
tracked files still matched the reviewed/baseline snapshots. This two-file
prose confirmation records verified B2b2a publication here and in the handoff.

Its distinct final self-review against `71afb32` checks publication prose,
verified remote result, B2b2a-only completion, new migration/scratch-only limits
and pending B2b2b/open parent statuses. No blocking finding remains. Exact
two-file staged scope, preservation/code hashes and whitespace pass; no new
local links are added. Application checks need no rerun for prose. Confirmation
publication follows; the final response reports its verified remote SHA.

### Handoff

Exact next after B2b2a: **R4-S2-T1B2b2b - Recover the authorized report
checkpoint**. Refine its atomic recovery/first-report protection, historical
unknown/invalid facts, current authorization/erasure/TTL and concurrency policy
before implementing. All parents remain open; no B2b2b implementation here.

## <a id="r4-s2-t1b2b2b"></a>R4-S2-T1B2b2b - Recover the authorized report checkpoint

Status: done (2026-10-24). Prerequisite B2b2a is
complete/published. This bounded child owns report protection/recovery and
review of the remaining B2b2/B2b/B2/B/T1 acceptance. F14/sprint/PI stay open.

### Contract specified before implementation

After claiming one item, inspect its current private checkpoint before any
extraction/evaluation.
No bound report follows the existing ingest path. A bound report completes in
one store transaction from that same report and strict version-1 original
matching facts; no extraction, identity update, fingerprint, evaluation or new
report save occurs. Report binding is first-write-only, including refusal of
same-ID batch resaves, so an in-flight callback rolls its report transaction
back rather than replacing a committed checkpoint.

Recovery holds the erasure guard before shared batch/subject/report locks,
then the processing-token item lock, then rechecks/locks the private reference.
Preserve subject-before-item-before-private ordering. Recheck current org,
resume/report candidate and domain ownership, report/body IDs, advisory contract,
private links, strict facts, fresh lease clock and original private-input TTL
after waits and writes. Timeout/TTL equality remains eligible. Lease refusal
rolls back, stops and counts neither outcome. Missing/swept/invalid/unknown or
TTL-expired checkpoint raises fresh_upload_required; only an acknowledged
current-lease failure counts, and retry skips it. Preserve earlier reports and
private data until their existing erasure/sweep lifetimes; never restore a
missing reference or reset TTL. These are commit-admission checks under locks,
not physical commit/delivery deadlines or clock-skew guarantees.

Current report authorization is the existing org-owned resume/report boundary;
recovery creates no consent grant, reads no ledger/features/source data, and
does not relax report redaction or erasure. The existing fresh-ingest path and
separate earlier commits remain. Duplicate provider cost before checkpoint
commit remains possible; claims about historical duplicate cleanup, exactly-once
providers or empirical quality are excluded. No schema/frontend change.

**Acceptance/tests:** red/green failed/interrupted/expired completion recovers
the same report with original signals and exact counts, without provider calls
or duplicate persisted reports; settled replay is a no-op. Refuse replacement
and same-ID mutation atomically. Strict malformed/history/ownership/domain/TTL
cases, no checkpoint fallback, erasure/sweep races, real competing SQLite/PG
locks and post-write/commit rollback; verify saved state/TTL/report counts.
Extend existing screening tests and two-process migrated HTTP/restart smoke;
run focused/full pytest, actual PG selection, screening Chrome, static and
preservation checks, implementation and distinct final self-reviews. Existing
populated migration roundtrips stay in the selection. Review every parent T1
criterion before closing it; F14/sprint/PI remain open.

### Implementation and privacy boundary

ScreeningService checks the private checkpoint immediately after each claim.
No report checkpoint retains the existing ingest path. A bound report enters
ScreeningStore.recover_report: erasure guard, shared batch/resume/report locks,
current-token item lock and private input lock/recheck, then one terminal
transaction. It validates strict version-1 facts, row/body IDs and domains,
resume/report org ownership, candidate linkage, advisory/human-review fields,
original private TTL and fresh lease eligibility after waits and writes. The
same report builds scalar queue signals from the first ingest's original flags;
no extraction, identity update, fingerprint, evaluation or report save runs.
Queue completion and private-reference removal commit together. Competing or
expired recovery refuses without counters and stops this call; interrupted
commit, post-write TTL/lease expiry and zero affected rows roll back.

The report-save callback binds only an unbound report_id. Replacement and
same-ID mutation fail the callback and roll back the entire report transaction,
including the attempted body change. This protects the batch checkpoint; it
is not a universal immutability rule for unrelated internal report-store callers.
Missing/swept/erased, malformed, unknown/future or TTL-expired checkpoint facts
require fresh_upload_required without replay or inferred flags. Only a current-
lease acknowledged failure increments failed; retry skips that input. Existing
report/private-row retention remains until normal sweep/erasure. No reference
is recreated or TTL refreshed; completion removes private facts as before.

Current org report authorization is the existing org-owned report/resume
boundary. Inspection of screening.scope, reports.store.get_for_org and the
ingest/evaluation callers confirms recovery reads no ledger, consent features
or source data and grants no consent. Public projection/redaction and advisory
semantics remain. Other-tenant processing is 404; wrong stored owners refuse.
Custom saved domains are supported without a hardcoded domain whitelist.
No migration, frontend source or working-store change is added.

The earlier ingest/fingerprint/report commits remain separate. Before a report
checkpoint commits, retries/interrupted workers may repeat extraction/evaluation
and spend provider work. A saved checkpoint is reused per batch item; distinct
items and historical duplicates are not merged or cleaned up. Equality at the
lease/TTL boundary remains eligible. Fresh checks admit commit while locks are
held, not a physical commit/delivery deadline or clock-skew guarantee. Browser
navigation/disconnection still does not guarantee server cancellation, and
there is no heartbeat or durable scheduler added here.

### Reproduction and implementation self-review

Sanitized runner: `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1b2b2b.py
<tag> <Python args>`; omitted args run `-m pytest -q --tb=short`. It clears
inherited DEE config/keys, pins missing config and null/loopback providers;
HTTP/Chrome use migrated scratch stores and synthetic/fake effects. Logs use
`.pytest_cache/r4-s2-t1b2b2b-<tag>.txt`. Baseline: 731 tracked files, captured
after the refined PI contract; the tree was clean before that contract edit.
Local runners, snapshots and synthetic captures remain ignored.

Pre-fix `red -m pytest -q --tb=short tests/test_screening_report_input.py -k
'first_report_checkpoint or http_interrupted'`: **3 failed, 2 skipped,
24 deselected, 1 warning, 4.67s**, exit 1. Replacement and same-ID writes were
accepted; HTTP retry reran the prohibited provider. Initial `green` with the
same selection: **3 passed, 2 skipped, 24 deselected, 1 warning, 3.97s**,
exit 0. These are behavioral reproducers, not broken imports/fixtures.

An intermediate `recovery` selection returned **1 failed, 31 passed, 31 skipped,
24 deselected, 1 warning, 34.64s**: the ORM considered JSON true equal to 1,
so the bool-version fixture had not persisted malformed data. The fixture now
uses an explicit Core UPDATE, then asserts recovery refuses it. This was a
fixture defect, not an application version-validation failure. The application
explicitly rejects bool as a version and validates strict flags/required keys.
The existing report-expiry fixture now admits a first report instead of seeding
an already-bound report; otherwise first-write protection would refuse before
the intended expiry boundary. Dedicated replacement/mutation regressions retain
that preservation contract.

Implementation self-review against `7a165ab` plus the three screening modules,
three existing screening test modules and smoke diff maps every child criterion
to persisted state, original flags, refusal/counts, erasure/TTL/authorization,
rollback and real competing-transaction assertions. Review found and resolved
a low-severity defensive terminal-write issue in src/app/screening/store.py,
recover_report: if its conditional update
affected zero rows it could have removed the private capability and returned
DONE. It now rolls back and returns REFUSED before deletion. The held token lock
normally prevents that race; service/refusal and competing-recovery regressions
exercise observable no-count/no-replay behavior. The final private-lock check
also reads a fresh clock after waiting, before validating saved state.

Correctness review checks erasure guard before subject/item locks, compatible
shared subject/report locks before the item/private lock, no locks across
provider awaits, callback exceptions rolling back same-ID body changes,
post-write rollback restoring private input, fresh clocks/TTL equality, strict
historical refusal, tenant/projection and no source/consent expansion. No
remaining implementation blocker. This is self-review, not independent review.
The final reviewed source snapshot hashes 643 tracked code/test/harness files;
later completion prose must preserve those hashes.

### Validation

All required gates passed on the reviewed application/test state. The initial
full-run failure and unchanged rerun are recorded below. Later tracked changes
are completion prose only.

| Gate | Actual command/result |
|---|---|
| Initial broad focused | Runner `focused -m pytest -q --tb=short tests/test_screening_report_input.py tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_erasure_concurrency.py tests/test_screening_batches_api.py tests/test_screening_durable_input.py tests/test_screening_unresolved_input.py tests/test_screening_refusal_retention.py tests/test_screening_schema.py tests/test_migrations.py`: **263 passed, 158 skipped, 18 warnings, 140.63s**, exit 0; before the defensive rowcount check and final service/API/competing regressions |
| Final focused | Runner `focused-final -m pytest -q --tb=short tests/test_screening_report_input.py tests/test_screening_service.py tests/test_screening_erasure_concurrency.py`: **131 passed, 112 skipped, 2 warnings, 87.31s**, exit 0; final application and service/API state |
| Additional competing transactions | Runner `competing -m pytest -q --tb=short tests/test_screening_report_input.py -k competing_checkpoint`: **2 passed, 2 skipped, 102 deselected, 1 warning, 3.91s**, exit 0; final test additions, two connections for first-save and recovery; full/PG include them |
| Two-process SQLite HTTP / graceful restart | Runner `http scripts/smoke_r4_s1_t3d.py --persistence`: **71/71** plus cookie/CSRF HTTP contract **31/31**, exit 0, 31.32s wrapper; same report/body/original flags, ingestion/evaluation attempt counts, one persisted report, refused stale writes and pending checkpoint recovery after actual app restart |
| PostgreSQL-configured selection | Owned `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t1b2b2b_postgres.py` invokes `-m pytest -q --tb=short tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_batches_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_report_input.py tests/test_screening_durable_input.py tests/test_screening_unresolved_input.py tests/test_screening_refusal_retention.py tests/test_migrations.py`: **389 passed, 10 skipped, 18 warnings, 587.04s**, exit 0 |
| Two-process PostgreSQL HTTP / graceful restart | Same owned runner invokes `scripts/smoke_r4_s1_t3d.py --postgres --persistence`: **71/71** plus cookie/CSRF HTTP contract **31/31**, exit 0, 70.96s wrapper; actual PG app storage, original report reuse without provider replay, exact counts/body/flags, expiry/erasure/tenant/CSRF/advisory and pending report recovery after graceful app restart |
| Full pytest | Runner `full-repeat` (project `-m pytest -q --tb=short`): **3630 passed, 595 skipped, 127 warnings in 1423.97s (0:23:43)**, exit 0; unchanged reviewed code |
| Actual screening Chrome | Runner `browser scripts/check_ui_screening_extraction_browser.py`: **24/24**, exit 0, 19.44s wrapper; intake/queue/report/outcomes/deletion, second intake, reload, injected read failure/recovery and no console exceptions |
| Static | `node scripts/check_ui_bindings.js`: **586 bindings / 18 states**, all resolve; `node --check frontend/api.js`, `frontend/support.js`, project `-m compileall -q src/app/screening scripts/smoke_r4_s1_t3d.py` and `git diff --check` pass |

The PG-configured selection mixes SQLite/backend-neutral fixtures and actual
PG parameterizations; its entire count is not a count of PostgreSQL tests.
Controlled actual PG connections inspect pg_blocking_pids before releasing the
writer in competing saves/recovery, private/report/item waits and erasure races;
PG also sweeps between recovery reads, proving no capability restoration.
The owned PostgreSQL 18.6 cluster uses READ COMMITTED/Asia/Calcutta. Existing
populated migration up/down/up cases remain in the selection; scratch head is
0030, with no new migration. Working storage is untouched. Local cluster/setup
artifacts are not a portable environment guarantee.
Owned PG shutdown returned exit 0, recorded in
`.pytest_cache/r4-s2-t1b2b2b-pg-runtime.json`; all owned HTTP/Chrome app
processes also stopped. The demo was not restarted. The reused HTTP contract
has 31 checks; its separate standalone host-start check is not claimed here.

HTTP/UI contract simulation is separate from Chrome. Fakes and synthetic waits
prove transaction/recovery mechanics, not live-provider compatibility, empirical
quality, cost savings or measured latency/resource bounds. Chrome still uses
existing CDN internet. Skips do not prove omitted cases; no dependency/CI,
deployment, other-browser or historical-duplicate cleanup claim is made.


The initial full run returned **1 failed, 3629 passed, 595 skipped,
127 warnings, 10691.34s**, exit 1. Existing
tests/test_ratelimit_auth.py::test_a_session_records_the_ip_hash_and_never_the_ip
expected verify 200 but received 400/invalid_code. Captured logs show its signup
request took 4,567,365.6ms (about 76 minutes), then verification immediately
refused. That is consistent with OTP expiry during the long delay; the cause
of that delay is not established. No screening/auth code change or expiry
relaxation is justified by this result. Runner `auth-check -m pytest -q
--tb=short tests/test_ratelimit_auth.py::test_a_session_records_the_ip_hash_and_never_the_ip`
passes unchanged: **1 passed, 1 warning, 5.10s**, exit 0. Runner `full-repeat`
passed the unchanged entire suite as recorded above; the initial failure remains
recorded. No cause for the original delay or auth fix is claimed.
Two collection-only diagnostic calls returned 4225 tests, with no test execution;
they identified the failing node before the aggregate traceback printed.

### Parent T1 acceptance review

This is closure review of the current task's parents, not a new backlog task.
A/B1/B2a/B2b1/B2b2a evidence remains linked from PI-R4; final suites rerun their
combined acceptance with B2b2b, instead of treating old counts as fresh evidence.

| Parent criterion | Final-code assertion/journey |
|---|---|
| Claim when work starts; unstarted work stays available | waiting-provider service/API regressions and two actual app processes; fresh next-item clock; current per-call cap |
| Acknowledge complete/fail; expired/stolen outcomes cannot count or overwrite | refused/expired ingest, error, completion and recovered-report cases assert exact counters, stop and unchanged durable state; HTTP slow worker cannot overwrite recovered report |
| Bound retry and define cancellation | capped process loop; refusal stops before reclaim/rebill; settled process/retry no-op; fresh-upload failures skip retry; cancellation propagates with one active lease, recovery later uses fresh leases |
| Input/report/terminal admission and rollback | fresh clocks after real lock waits and writes; equality/expiry; partial earlier commits remain explicit; populated migration tests remain in SQL selection |
| Persisted report idempotence on authorized recovery | replacement/same-ID atomic refusal; competing saves/recoveries commit one result; same report/body/original flags and exactly one saved report; no ingestion/evaluation replay including app restart |
| Tenant, erasure, retention and consent boundaries | wrong org/owners/domain/body refuse; private TTL equality/expiry; erasure-first/sweep absence cannot restore; recovery-first erasure waits for commit; public metadata non-disclosure, CSRF/404 and unchanged projection |

No exactly-once provider claim is needed for this bounded T1 contract: provider
cost before a committed checkpoint is explicitly separate from persisted-report
idempotence. Current full/PG/HTTP/Chrome gates and specification/correctness
self-review close B2b2b and its B2b2/B2b/B2/B/T1 parents, with no acceptance
blocker remaining. This is same-agent review, not independent review.
T2 ingest identity/version races, T3 aggregate/off-loop limits, T4 durable browser
continuation and R4-S2-Q remain separate. F14/sprint/PI cannot close with T1.


### Completion record

B2b2b and the combined parent T1 acceptance are complete. PI-R4 owns status;
FEATURE_STATUS/SCREENING describe current recovery; PROGRESS names exact next
R4-S2-T2, and ROADMAP has one brief session entry. No next-task work, deployment
or working-data change is included. Existing Starlette/SQLAlchemy/Alembic
warnings and skipped optional/backend cases do not prove omitted behavior.
The unchanged clean full rerun resolves the validation blocker while preserving
the initial auth timing failure and its limits. All later edits are completion
prose; the 643-code-file reviewed snapshot remains the tested state. The distinct
final staged completion self-review and authorized publication follow.


### Distinct final completion self-review and publication

After all required gates and the completion record, a distinct final self-review
against `7a165ab` inspected the exact thirteen-file staged scope: screening
schema/service/store, the screening smoke, existing report-input/service/erasure-
concurrency tests, FEATURE_STATUS/SCREENING/PROGRESS/ROADMAP, PI-R4 and this
existing evidence file. Specification review maps each child and parent T1
criterion to the final persisted-state, original-fact, rollback/expiry, competing
SQL, tenant/erasure/TTL, HTTP/restart, Chrome and full-suite assertions. Parent
closure is bounded to B2b2/B2b/B2/B/T1; F14/sprint/PI and T2/T3/T4/Q stay open.
The first auth failure, 76-minute signup, unchanged isolated/full passes and
unproven delay cause remain explicit; there is no auth-code/expiry-policy change.

Correctness/maintenance review rechecks callback rollback of replacement/same-ID
mutations, strict original facts and report/body identity, shared parent locks
before item/private locks under the erasure guard, fresh clocks after waits and
writes, no restored capability/TTL refresh, atomic queue/input transition and
acknowledged counters/stop behavior. No provider await holds recovery locks;
separate earlier commits/provider cost, existing org report/consent boundary and
unchanged public projection remain. Scratch trace files use synthetic data and
remain ignored; restart gates release in finally and owned servers/PG stopped.
No blocking application finding remains. This is self-review, not independent
review, separate from implementation review.

One low-severity documentation finding in PI-R4's T1 heading replaced its dash
with a question mark during a PowerShell text rewrite. This affected formatting;
a direct Unicode patch restores the heading and wraps completion prose. Local
link/anchor and whitespace checks validate it; application code is unchanged.

The staged preservation check (`.resume/Scripts/python.exe
.pytest_cache/review_r4_s2_t1b2b2b.py --staged`) verifies exactly **13** scoped
files, **718** unrelated tracked files/working DB unchanged from the 731-file
baseline, **643** code hashes matching the reviewed/tested snapshot and **12**
added local documentation links/anchors. Staged whitespace passes. Secrets,
working data and local artifacts are excluded. Later edits are completion prose,
so application checks need no rerun. Authorized scoped commit/push and remote
verification follow this distinct completion self-review; no T2 work starts.


Scoped task commit **`8fb5122`** was created and pushed to `origin/main` using
`git -c credential.https://github.com.username=RevanParimi push` under
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never` (exit 0). Local HEAD and
`git -c credential.https://github.com.username=RevanParimi ls-remote origin
refs/heads/main` both returned **`8fb512206d0efce980808df30428283605b794bf`**;
the working tree was clean. All 643 code hashes, 718 unrelated tracked files
and the working DB still matched reviewed/baseline snapshots. This two-file
prose confirmation records publication here and in PROGRESS.

Its distinct final self-review against `8fb5122` checks the exact publication
prose, verified remote result, bounded parent closure and exact next T2 pointer.
No blocking finding remains. Preservation/code hashes, exact two-file staged
scope, local links and whitespace pass. This is self-review, not independent
review. Application checks need no rerun for prose; confirmation publication
follows, and the final response reports the verified remote SHA afterwards.

### Handoff

Exact next: **R4-S2-T2 - Resolve candidate and resume ingest races**, pending.
Read its PI contract and current handoff; do not begin it as part of this task's
publication. B2b2b/B2b2/B2b/B2/B/T1 close; F14/sprint/PI remain open for their
other mapped tasks and gates. Working data and the existing demo are preserved.

## R4-S2-T2

### Contract and implementation (2026-10-25)

Status: done (2026-10-25). Prerequisite R4-S2-T1 is done. This
session handles candidate/resume ingestion races only; F14/sprint/PI stay open.

Trigger: two first uploads both resolve no candidate before either commits.
Previously each created its own subject, so identical safe contact/text input
could split identity and resume history. After the batch pre-write erasure
barrier, unresolved contact lookups take a transaction-scoped key and recheck
before creating. Email uses existing login/redemption/erasure ordering; phone-only
keys have a disjoint prefix. PostgreSQL uses the existing advisory lock, SQLite
its writer lock. Lookup queries populate current matching rows after waits.
Concrete resolved/expected subjects are never re-resolved after erasure.

Acceptance and scope:

- A unique compatible email/phone match shares one candidate across competing
  uploads. Identical text reuses the caller-owned resume and records another
  extraction; changed text/another tenant gets a unique candidate-wide version.
  Existing candidate UPDATE locking already serializes dedup/version allocation;
  this task proves that path as well as fixing absent-subject creation.
  The operator plane retains its existing unowned/available-text reuse policy.
- First mailbox redemption and upload agree on the subject. Proof is set only
  by exact-code redemption. Creation rollback releases ordering and persists no
  partial candidate/resume/extraction; callback failures are not auto-replayed.
- Missing/ambiguous/incompatible hints retain distinct-submission policy, and
  asserted hints stay non-unique. No historical identity merge, schema change,
  migration, working-data cleanup, UI contract or scoring change.
- Provider/report operations remain separate commits. This is candidate/resume
  deduplication under the supported SQLite/PostgreSQL ordering, not exactly-once
  provider/report execution or an assertion that hints prove identity.

The pre-implementation read-only command `.resume/Scripts/python.exe
scripts/inventory_candidate_contacts.py --database data/veritas.db` found one
candidate, zero email/phone duplicate groups, one missing phone, one historical
login subject and revision `0023_correction_pins_the_name`. Proof columns were
unavailable, so proof was unknown. Only aggregates were printed; baseline hashes
preserve this named working DB. Synthetic duplicate asserted emails are explicitly
retained and cause separate submissions. A unique asserted-contact constraint
would reject legitimate ambiguity and is intentionally unnecessary here.

### Regressions and validation

Sanitized local runner `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t2.py
<tag> <Python args>` clears inherited `DEE_*`, uses a nonexistent config instead
of `.env`, disables live LLM/GitHub/mail delivery and sets project import paths.
Omitted arguments run `-m pytest -q --tb=short`. Scratch SQL/providers and the
working DB are separate. Ignored logs/runners are local artifacts, not portable
setup guarantees; reproducible HTTP entry points are tracked in the existing smoke.

| Check | Actual result |
|---|---|
| Red: runner `red -m pytest -q --tb=short tests/test_candidate_store.py -k 'competing_ingests and first-creation and commit and identical'` | **2 failed, 2 skipped, 69 deselected**; both SQLite email/phone assertions found different committed candidate IDs, the intended defect |
| Initial focused candidate/contact/login/erasure/screening group, runner `focused` | **213 passed, 138 skipped**, 2 warnings; before final lookup refresh/test-gate refinements |
| Final full pytest | Runner `full-final` invokes `.resume/Scripts/python.exe -m pytest -q --tb=short`: **3659 passed, 623 skipped**, 127 warnings, exit 0 (876.78 s pytest time) |
| Final PostgreSQL-configured focused group | `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t2_postgres.py`: **551 passed, 12 skipped**, 18 warnings, exit 0; includes actual controlled PostgreSQL connections and SQLite cases |
| Migrated SQLite two-process HTTP, runner `http-fixed scripts/smoke_r4_s1_t3d.py --ingest-races` | **41/41** plus reused cookie/CSRF HTTP contract **31/31**, exit 0 |
| Migrated PostgreSQL two-process HTTP/restart | Same PG runner invokes `scripts/smoke_r4_s1_t3d.py --postgres --ingest-races`: **41/41 + 31/31**, exit 0 |
| Static | `node scripts/check_ui_bindings.js`: **586** bindings/18 states; `node --check scripts/test_ui_screening.js` and `git diff --check` passed |

The owned PG runner provisions a new disposable PostgreSQL 18.6 database with
Asia/Calcutta timezone and READ COMMITTED isolation, then runs the following
project-environment command with its explicit `DEE_TEST_DB_URL` (URLs/passwords
are not printed):

```powershell
.resume/Scripts/python.exe -m pytest -q --tb=short tests/test_candidate_store.py tests/test_candidate_login_binding_concurrency.py tests/test_candidate_login_binding.py tests/test_asserted_contact_policy.py tests/test_asserted_contact_concurrency.py tests/test_ingest_erasure_concurrency.py tests/test_screening_api.py tests/test_screening_service.py tests/test_screening_store.py tests/test_screening_batches_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_report_input.py tests/test_screening_durable_input.py tests/test_screening_unresolved_input.py tests/test_screening_refusal_retention.py tests/test_migrations.py
```

It then runs `.resume/Scripts/python.exe scripts/smoke_r4_s1_t3d.py --postgres
--ingest-races` and stops only its owned server in `finally` (stop exit 0).
Both HTTP runs prove three migrated app lifespans and graceful cleanup. The full
suite's skips and warnings are not evidence for omitted environments/features;
the PG-configured group separately exercises the relevant actual PG contention.
No schema changed;
the existing migration suite and migrated HTTP startup check compatibility,
without claiming a new migration or touching working storage. Python compilation
also passed for the store, two changed test modules and changed smoke script.

`tests/test_candidate_store.py` adds controlled committed/rolled-back competing
email/phone, first/existing subject, identical/changed text and other-tenant
uploads. The second lookup runs while the first write is uncommitted. PostgreSQL
checks actual blocking PIDs; SQLite checks the pending writer. Assertions cover
subject count, caller ownership, contiguous unique versions, resume reuse,
extraction count and absent proof. Synthetic duplicate emails remain unmodified.
`tests/test_candidate_login_binding_concurrency.py` covers both creation orders
against actual exact-code redemption, commit/rollback, proof and session history.
Existing erasure/contact/retry regressions preserve refusal and transaction scope.

The tracked smoke's `--ingest-races` adds controlled first-email, first-phone,
existing-identical, existing-changed, cross-tenant and operator/employer HTTP
uploads through two actual app processes. It checks persisted versions, separate
advisory reports/tenant reads, exact resume state after graceful restart, and
reuses the earlier worker scheduling and cookie/CSRF HTTP contract. This is
HTTP execution with fake providers, not a browser or live-provider test. No
screen/handler/UI contract changed, so actual browser execution is not required.

Harness corrections: initial new login tests passed settings as a positional
argument to the single-argument heuristic helper (4 setup failures); fixed by
hashing its profile with the configured salt and wrapping ExtractionResult.
The first HTTP attempt requested an unsupported candidate-detail endpoint (404);
it now asserts ownership through supported report routes with evaluation enabled
for the cross-tenant case. The initial PostgreSQL run exposed two failure markers
because the login-first pause attached to an earlier rate-limit commit. The pause
now occurs after principal establishment under the address lock. Superseded full
and PG runs were explicitly stopped, with no final counts claimed; the PG runner
shut down its owned server. Clean final runs use the corrected gate and final code.

### Implementation self-review

Reviewed against base `82eb351` plus the scoped candidate-store, two test modules,
smoke and candidate behavior documentation. Specification review traced safe and
ambiguous/no-contact matching, tenant text reuse, version uniqueness, callback
rollback and proof authority to behavioral assertions. Correctness review traced
both routers and the batch caller, barrier -> contact -> candidate ordering,
the existing resume/retry lock order, erasure refusals, and separate fingerprint/
report/provider persistence. No blocking product finding remains. The lookup
refresh uses populate-existing on the two matching queries instead of expiring
the whole session, preserving caller-owned callback state. This is same-agent
self-review, not independent review. Validation refinements above were resolved;
final code hashes and required gates must agree before closure.

Low documentation finding, `CANDIDATES.md` matching paragraph: unqualified
caller-owned wording could imply that the operator plane owned a resume row.
Clarified organization-only reuse and the existing operator exception here and
in that behavior guide; runtime behavior is unchanged. Documentation checks
validate the clarification.

### Completion review and publication

Distinct final completion self-review (2026-10-25), after the required gates
and completion record: reviewed all **10 staged files** against `82eb351`:
the candidate store, two regression modules, extended smoke, candidate guide,
feature overview, PI status, this evidence, handoff and roadmap entry. This is
a separate same-agent self-review, not independent review. Specification review
matched each acceptance criterion to current implementation and final evidence.
Correctness review rechecked key/row/barrier ordering, rollback and erasure,
proof authority, tenant-specific resume reuse, version allocation, unchanged
public contracts and independent provider/report commits. No blocking finding
remains. A low handoff wording issue pointed the persistence setup at T2's
creation-only PG runner; the prior persistence runner and current T2 runner are
now named under their respective journeys. No application change was needed.

Final preservation checks (`.resume/Scripts/python.exe
.pytest_cache/review_r4_s2_t2.py --staged`) verify **643** code hashes unchanged
from the reviewed/tested snapshot, **721** unrelated tracked files including the
working DB unchanged, exactly **10** scoped staged files and **7** added local
documentation links/anchors. Staged whitespace passes. Secrets, working data,
ignored validation artifacts and unrelated work are excluded. Owned PG/HTTP/
pytest processes finished; the existing demo was untouched. Final edits after
application validation only refine completion prose, so affected documentation
and staging checks suffice. Authorized publication targets `origin/main`; the
final chat response records its verified remote commit after push.

All acceptance gates, the completion record and both self-reviews are complete.
Exact next is
**R4-S2-T3 - Bound requests and move blocking work off-loop**; do not start it here.

## R4-S2-T3A

### Contract and implementation (2026-10-25)

Status: done (2026-10-26). T3 was split before implementation
into A (ingress bytes), B (bounded PDF execution) and C (remaining SQL/SMTP).
This session completes A only; T3/F14/sprint/PI remain open. T2 is done.

Trigger: per-item and item-count checks ran after framework JSON parsing; a
batch or ignored JSON field could allocate an unbounded body before those
checks. A positive `max_request_body_bytes` setting defaults to 32,000,000 raw
bytes in Settings/YAML and accepts `DEE_MAX_REQUEST_BODY_BYTES` overrides.
The new small ASGI gate lives inside request-context/CORS and outside routing
and JSON/model validation. Known oversized lengths refuse before receiving;
actual streamed bytes are counted even without a trustworthy length. Decimal
length comparison avoids untrusted integer conversion. Equality is accepted;
oversized events are not appended, empty chunks retain no event list, and the
accepted bytes replay once before delegating later receives to the transport.
The last event/temporary buffer is released before downstream work.

Acceptance: uniform safe HTTP 413 for application-bound oversized bodies on
operator/org/auth/unknown/public paths, before PDF/provider/persistence work.
Existing CORS preflights can finish without consuming any body. Accepted bodies
retain byte equality, UTF-8 content, auth/tenant/CSRF/validation, request IDs and
CORS. Disconnect stops without routing and attempts HTTP 400 with
`request_body_incomplete` to complete outer middleware; delivery to a disconnected
client is not guaranteed. Cancellation propagates. A paused upload permits
unrelated health and authorized reads within a measured one-second total budget.

This bounds bytes per request, not global RSS, simultaneous uploads, JSON object
expansion or decoded media. Server-owned events and transient copies remain;
existing transport read timeouts and per-item/PDF limits are unchanged. No
schema/transaction, provider, scorer or frontend change. SQL sessions never move
between threads in this child. Worker saturation/cancellation/timeout/shutdown
and slow PDF/provider/SQL/mail responsiveness remain B/C and the parent review.
No new PostgreSQL concurrency/migration gate is required for an ingress-only
change; SQLite journey evidence is not called actual PG evidence.

### Validation

Sanitized runner `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t3a.py
<tag> <Python args>` clears inherited `DEE_*`, uses a nonexistent config instead
of `.env`, disables live LLM/GitHub/mail delivery and sets project import paths.
Omitted args run `-m pytest -q --tb=short`. Isolated SQL and fake providers are
used throughout; no working-store migration or demo restart. Ignored logs and
local runners are artifacts, not portable setup guarantees.

| Check | Actual result |
|---|---|
| Original red, runner `red -m pytest -q --tb=short tests/test_resume_input_boundary.py -k aggregate_batch` | **1 failed, 64 deselected**; HTTP 200 registered two oversized-batch items instead of 413 |
| Disconnect integration red, runner `disconnect-red -m pytest -q --tb=short tests/test_resume_input_boundary.py -k unhandled_application_error` | **1 failed, 76 deselected**; silent return raised `No response returned` and produced a 500 access event |
| Final focused, runner `focused-reviewed-final` | **201 passed**, 1 warning; exact file set below |
| Final full, runner `full-final` | **3695 passed, 623 skipped, 127 warnings** in **904.38 s**, exit 0 |
| Migrated HTTP/restart, runner `http-reviewed-final scripts/smoke_r4_s1_t3d.py --body-limit` | **28/28 + 31/31** reused cookie/CSRF HTTP contract, exit 0; final latency below |
| Actual Chrome, runner `chrome-final scripts/check_ui_screening_extraction_browser.py --body-limit` | **27/27**, exit 0; actual 413, Clear/fresh-file recovery, one completed batch and reload, with no console exceptions |
| Static | `node scripts/check_ui_bindings.js`: **586 bindings/18 states**; `node --check frontend/api.js`, `node --check frontend/support.js`, changed-file Python compilation and `git diff --check` passed |

The focused command is `.resume/Scripts/python.exe -m pytest -q --tb=short
tests/test_api.py tests/test_resume_input_boundary.py tests/test_config.py
tests/test_config_screening.py tests/test_openapi_contract.py tests/test_metrics.py
tests/test_api_auth_gate.py tests/test_cookie_posture.py tests/test_auth_api.py`.
Existing modules group transport, resume integration and config checks; no new
test file was introduced. Tests assert exact/UTF-8/chunked bytes, early refusal
and unread tail, absent/underreported/huge/leading-zero lengths, empty chunks,
disconnect/cancellation, replay, non-HTTP scopes, API auth/validation/CORS, no
PDF calls or candidate/resume/extraction/fingerprint/report/batch/input writes,
and omitted body sentinels in responses/logs. Fakes prove mechanics, not quality.

The tracked HTTP flag uses migrated scratch SQL, fake providers and graceful
restart. A real socket receives 413 from headers alone, and HTTP chunked and
malformed bodies get the same refusal. A test-only ASGI marker acknowledges a
partial upload prefix before timing health plus an authorized batch read;
the two complete in **0.0161 s** total against a **1.0000 s** budget on this host.
PDF instrumentation and exact saved batch lists prove refusal precedes parsing/
registration. An exact-size accepted request survives restart with tenant
isolation. Chrome separately proves the real rendered error and recovery; HTTP
contract simulation is not mislabeled browser execution. Browser uses existing
CDN runtime internet and Windows process termination; the HTTP journey owns
the graceful lifecycle evidence.

Harness corrections are separate from the reproducers: two initial selections
named nonexistent `test_auth_middleware.py`/`test_cors.py` (no tests ran); the
preflight test used an unsupported convenience-method `content` argument,
corrected to generic `request`. The full-ASGI disconnect test initially inspected
only the final empty response event, corrected to join response body events.
Browser replacement initially assumed selection overwrote existing files, but
the picker appends; it now uses the existing Clear action and waits for cleared
selection/error rather than a hidden zero-files label. An immediate one-shot
mock batch-read 503 could race navigation rendering; the injected response now
waits 100 ms and stays armed until explicit restoration. Clean final focused,
HTTP and Chrome runs pass; these setup failures are not product defect proof.

### Implementation self-review

Reviewed `388baf6` plus the ingress module, Settings/main wiring, YAML, three
existing test modules and two existing journey scripts. Specification review
mapped byte limits, no parsing/writes, compatibility, cancellation/disconnect and
partial-upload responsiveness to behavioral checks. Correctness review traced
middleware ordering, all paths/methods, CORS preflight short-circuit, raw-byte
versus decoded/aggregate-memory bounds, reentrancy, safe details and storage/
provider bypass on refusal. No blocking finding remains after these fixes:

- Medium: silent disconnect return in the new ingress gate triggered a 500 in
  outer BaseHTTPMiddleware. The red full-ASGI regression reproduced it; safe
  incomplete-body response completes that wrapper without route work.
- Low: the last ASGI event/chunk could remain referenced throughout downstream
  provider work. Release it with the temporary bytearray after preparing replay;
  final byte/replay regressions and required journeys cover compatibility.

This is same-agent self-review, not independent review. Final full pytest ran
on the reviewed source/config state, subsequently verified unchanged. B/C and
the parent acceptance review are not implemented by this session.

### Completion review and handoff

Implementation and required validation are complete. Final full pytest passed
on the reviewed code/config; no application changes followed it. Settings,
operating guidance, feature status, PI status, this completion record and the
short handoff agree. T3/F14/sprint/PI remain open. Working DB and unrelated
tracked files are preserved; no demo restart, working-store migration or
live-provider validation is claimed.

Distinct final self-review (2026-10-26), after the completion record: reviewed
the exact **15-file staged diff** against `388baf6`: ingress/Settings/main/YAML,
three existing regression modules, two existing journey scripts, operating and
feature guidance, handoff, roadmap, PI and this evidence. Specification review
mapped all A acceptance criteria to the final checks and kept B/C/parent gates
open. Correctness review traced header/stream limits, bounded accumulation and
replay, disconnect/cancellation, middleware/CORS order, sanitized errors, no
rejected-body persistence, tenant/CSRF compatibility, browser recovery and owned
scratch-process lifecycle. No blocking finding or application change resulted.
This is same-agent self-review, not independent review.

Final preservation/staging checks: **644 code hashes plus YAML** match the
reviewed full-test state; **717 unrelated tracked files and the working DB**
match baseline. Exactly the 15 scoped files are staged, with no unstaged scope
changes; nine added local documentation links/anchors and `git diff --cached
--check` pass. Packaging includes the new module through existing `src/app`
package/image inclusion; no dependency or image change is needed. No secrets,
working data or ignored validation artifacts are included.

Both reviews and acceptance gates are complete. Authorized scoped publication
uses `main` tracking `origin/main`; the final chat response records the verified
remote commit after push. Exact next after A is
**R4-S2-T3B - Bound PDF execution and keep it off the event loop**, under the
existing [T3 child contract](PI-R4.md#r4-s2-t3b). Stop after A publication.

## R4-S2-T3B

### Contract and implementation (2026-10-26)

Status: done (2026-10-26), including reviewed publication/remote verification.
This session handles B only. A/T2
are complete; C, parent T3/F14/sprint/PI remain open.

Trigger: candidate intake, batch registration and the async graph ingest node
called the synchronous disposable PDF supervisor on the event loop; candidate
document submission did the same inside its synchronous service. Per-parse
process/time/resource limits bounded an individual parse, but did not prevent
unrelated requests waiting or concurrent callers creating too many children.

The pre-implementation contract was recorded under B in PI-R4. One lazy
`PdfExecutor` per Services bundle admits at most `pdf_max_concurrent_parses`
jobs (positive, default **2**, YAML/DEE override), with no waiting queue. Resume
input adapters, graph ingestion and candidate document parsing share admission.
Only pure input/parsing operations cross threads; no store/session/provider does.
All document formats use the document parsing admission; text resumes keep
their normal validation path, including text precedence and cheap size refusals.

Full capacity returns safe HTTP **503**, `pdf_capacity_exhausted`, with
`Retry-After: 1`; closed admission uses `pdf_executor_closed`. No partial batch
registration is saved: files parse sequentially and registration starts only
after every file succeeds. Invalid/timeout resume errors keep 422 and safe
indexed detail; verification parse errors retain 400 and safe detail. Existing
auth/tenant/CSRF, per-parse disposable worker, memory/logical/input/output/time
limits, blank/metadata verification behavior and deterministic fallbacks remain.

Application-task cancellation signals its supervisor and propagates immediately.
The admission slot remains occupied until the child is killed/reaped and pipes
close. The child wait checks cancellation every at-most 50 ms, excluding
launch/decoding/cleanup. Service cleanup closes admission, signals active jobs and joins
supervisor threads before owned SQL disposal. Repeated/canceled shutdown callers
still finish cleanup. Verification repeats candidate/method/present-consent
gates after the awaited parse, before assessment/writes; async erasure can no
longer pass solely on the pre-parse existence snapshot. Synchronous parser and
verification-service APIs remain available with caller-owned scheduling.

Acceptance requires a red blocking regression; all five HTTP PDF doors allowing
health plus authorized reads within a documented **1.0000 s** total budget during
a controlled real PDF child stall; bounded admission without partial writes;
valid/invalid multi-file intake, timeout/failure recovery, cancellation/shutdown
cleanup; focused/full pytest; migrated scratch HTTP/restart and actual Chrome
error/recovery/reload. No frontend, schema, migration or SQL transaction/thread
change; no actual PostgreSQL gate is required by this PDF-only boundary. SQLite
journey evidence is not called PostgreSQL evidence.

### Validation

Sanitized runner: `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t3b.py
<tag> <Python args>`. It clears inherited `DEE_*`, bypasses live config/.env,
disables live LLM/GitHub/mail and sets project import paths. Omitted Python args
run `-m pytest -q --tb=short`. Tests use fake external providers and isolated
stores; journeys use migrated scratch SQL. Ignored local runners/logs are
artifacts, not portable setup guarantees. The demo and working storage are
untouched. Synthetic evidence proves mechanics, not empirical scoring quality
or live-provider validation.

| Check | Actual result |
|---|---|
| Original red, runner `red -m pytest -q --tb=short tests/test_pdf_resource_limits.py -k slow_pdf_intake` | **1 failed, 70 deselected**; controlled 0.3-second parser delayed the event-loop/health check to **0.5822 s** |
| Focused, runner `focused` with file set below | **249 passed**, 1 warning in **125.76 s**, exit 0 |
| Final stop/admission regressions, runner `focused-stop-final -m pytest -q --tb=short tests/test_pdf_resource_limits.py -k 'slow_pdf_intake or capacity_is_shared or cancellation_retains or async_pdf_stop or document_parse_runs'` | **8 passed, 72 deselected**, 1 warning in **11.11 s**, exit 0; includes two later-added retained-admission/repeated-shutdown-cancellation cases |
| Migrated HTTP/restart, runner `http scripts/smoke_r4_s1_t3d.py --pdf-execution` | **28/28 + 42/42**, exit 0; actual per-door latency below |
| Actual Chrome, runner `chrome scripts/check_ui_screening_extraction_browser.py --pdf-execution` | **27/27**, exit 0; real PDF 503, fresh PDF recovery, one screening and reload, no console exceptions |
| Consent fixture correction, runner `fixture-final -m pytest -q --tb=short tests/test_comp_api.py` | **6 passed**, 1 warning in **4.41 s**, exit 0 |
| First completed full, runner `full-final` | **2 failed, 3704 passed, 623 skipped, 127 warnings** in **1017.65 s**; two more expired dashboard consent fixtures, below |
| All corrected fixture modules, runner `fixtures-reviewed-final -m pytest -q --tb=short tests/test_comp_api.py tests/test_dashboard_api.py tests/test_dashboard_service.py` | **18 passed**, 1 warning in **4.51 s**, exit 0 |
| Final full, runner `full-reviewed-final -m pytest -q --tb=short -x` | **3706 passed, 623 skipped, 127 warnings** in **1020.06 s**, exit 0; all **4329** collected cases accounted for; `-x` omitted nothing on this successful run |
| Static | `node scripts/check_ui_bindings.js`: **586 bindings/18 states**; `node --check frontend/api.js`, `node --check frontend/support.js`, changed-file `py_compile` and `git diff --check` passed |

Focused file set: `tests/test_pdf.py tests/test_pdf_resource_limits.py
tests/test_resume_input_boundary.py tests/test_service_lifecycle.py
tests/test_verification_api.py tests/test_verification_claim_api.py
tests/test_verification_claim_service.py tests/test_verification_documents_parse.py
tests/test_config.py tests/test_openapi_contract.py`, using the standard
`-m pytest -q --tb=short` arguments. Existing test modules own the added cases;
no new regression module was introduced.

Controlled offline checks assert health completes before the parser is released;
all five HTTP doors share safe admission with no candidate/resume/report/batch/
verification writes on refusal; text intake and another executor remain usable;
valid two-file intake succeeds after capacity returns. Real instrumented parser
children prove cancellation, timeout and shutdown kill/reap/pipe closure and
recovery or closed admission. A held supervisor proves canceled callers cannot
free capacity early; repeated cancellation of shutdown cannot abandon cleanup.
Service cleanup proves PDF finishes before SQL disposal and cannot be lazily
recreated after closing. Document erasure during a held parse refuses before
writes, with parsing on a different thread and SQL on the caller.

Migrated HTTP uses an instrumented copy of the actual disposable worker, paused
after a real PdfReader construction, with normal child/timeout/resource behavior.
Health plus an authorized batch read measured **0.0356 s** (`/evaluate`),
**0.0165 s** (`/candidates`), **0.0194 s** (`/screening/candidates`), **0.0167 s**
(`/screening/batches`) and **0.0275 s** (`/portal/documents`), each within the
one-second total budget on this host. Concurrent registration gets 503 with no
partial batch; release completes valid PDF/two-file intake. Timeout, private
worker error and invalid second file refuse atomically, then a fresh PDF
immediately succeeds. Exact intake survives graceful restart with tenant
isolation. The reused cookie/CSRF/UI HTTP contract is not called browser evidence.
Chrome separately exercises rendered 503, Clear/fresh PDF intake, completion and
reload. Chrome needs the existing CDN runtime internet and uses Windows process
termination; the HTTP harness owns graceful lifecycle evidence.

Harness corrections: the original tight unit timing budget included PDF fixture/
request setup and remained noisy after offloading (health already completed
before upload). The final unit check uses controlled parser admission/release
and checks health finishes before release; measured latency belongs to the real
HTTP test. The initial broad green run had that one timing failure (**183
passed**); a subsequent focused stop run had it with **4 passed**. These are
test-budget corrections, not new application defects. The smoke's evaluation
observer now tolerates a PDF source instead of assuming `resume_text` is present.
Clean final focused, HTTP and Chrome runs pass.

The first full run (`full`) exposed an unrelated dated fixture at
`tests/test_comp_api.py::test_submit_offer_requires_consent_then_succeeds`:
its 2026-07-28 plus 90-day grant expired on **2026-10-26**, so the endpoint
correctly returned 403. An isolated `full-failure-probe` reproduced **1 failed**.
Both tests using that fixed grant now patch the ledger's clock to their fixture
time; the six-test module passes. Application consent behavior is unchanged.
The first full run was stopped at approximately 20% after identifying the
failure; it is not completion evidence. `full-final` restarts the entire suite
with the corrected fixture. This small test repair supports B's required full
gate and does not start another backlog task.

That completed full run found the same fixed-grant expiry in
`test_dashboard_api.py::test_card_consent_flow` and
`test_dashboard_service.py::test_card_sections_available_after_read_grant`.
Both now pin the ledger clock to their existing `NOW` fixture, preserving
consent-required/no-data/available assertions and actual permission checks.
The three affected modules pass together (**18 passed**). `full-reviewed-final`
reruns the whole suite with these test-only corrections; no application consent
or dashboard behavior changed. Progress-tail monitoring initially missed these
two failures; the completed summary identified them, and the final run uses
fail-fast reporting. No failed full run is presented as a green completion gate.

### Implementation self-review

Reviewed `06a7f42` plus the PDF executor/supervisor, async resume adapters and
graph node, verification parse split/recheck, Services lifecycle, safe API
handler, Settings/YAML, three existing test modules and two existing journeys.
Specification review mapped every B acceptance criterion to the checks above
and kept C/parent work open. Correctness review traced shared admission and
slot retention, thread/session ownership, process/pipe/time/memory limits,
exception sanitization, cancellation/repeated shutdown, text compatibility,
atomic registration, tenant/CSRF guards and verification erasure/present consent.

Review refinements closed late lazy admission after service cleanup and added
a post-work cancellation check before delivering a parsed result. Lifecycle
and retained-admission regressions cover them. No blocking finding remains.
This is same-agent self-review, not independent review. **604 code/config file
hashes** identify the reviewed state for comparison after full pytest. No
application/config changes followed that snapshot.
The separate review of the dated consent fixture correction confirmed that it
pins only synthetic test time and preserves the initial 403 then authorized 200
assertions. The final code/config snapshot includes that corrected test module.
The same separate fixture review covers the two dashboard clock pins and the
unchanged consent-required/no-data/available contracts. The final snapshot was
refreshed for these test-only corrections; application/config hashes remain
unchanged from the earlier HTTP/Chrome/focused validation.

### Completion and handoff

Implementation, required validation and the completion record are complete.
Final full pytest passed on the reviewed state; **604 code/config hashes**
remain unchanged. B is published; C/parent/F14/sprint/PI remain open. Settings,
operating/feature guidance, PI, roadmap and the short handoff agree. No working
store migration, demo restart or live-provider validation is claimed.
The distinct final staged self-review/publication follows this completion record.

Per-process admission is not a global RSS,
HTTP-body concurrency or cross-process budget. Each active supervisor also uses
two pipe-I/O threads. A transport disconnect alone need not cancel the app task;
accepted work can finish within its existing deadline. Direct synchronous
callers retain caller-owned scheduling. Normal server shutdown first drains
in-flight HTTP requests; the existing per-item/count limits are not a new
whole-batch deadline. SQL/SMTP blocking and combined parent
acceptance remain **R4-S2-T3C**; no C implementation belongs to this session.

Distinct final self-review (2026-10-26), after the completion record: reviewed
the exact **26-file staged diff** against `06a7f42`: executor/supervisor,
resume/graph/HTTP adapters, verification split/recheck, service lifecycle,
Settings/YAML, six existing test modules, two existing journeys, operating and
feature guidance, handoff, roadmap, PI and this evidence. Specification review
mapped every B acceptance criterion to the recorded checks, kept C/parent
acceptance open and distinguished real child/HTTP/Chrome evidence from fakes
and skipped environments. Correctness review traced admission/retained slots,
cancel/timeout/closed admission, thread/session ownership, child/pipe/resource
cleanup, present verification gates, atomic batch refusal, safe details,
auth/CSRF/tenant compatibility and browser recovery. The three dated fixture
modules only pin synthetic clocks and retain their permission assertions.

Low documentation finding: A's PI summary retained its old next-B pointer after
B closed. It now delegates B/C status to the cards below; the handoff names C.
No application change or blocking finding resulted. This is same-agent
self-review, not independent review. Final code/config hashes still match the
successful full run; only completion prose changed afterwards. Added local
documentation links, staged whitespace and preservation checks pass. Packaging
already includes the new module via `src/app`; no dependency/image change.
No secrets, working data or ignored validation artifacts are staged.

Final preservation/staging checks: **604 code/config hashes** match the tested
state; **707 unrelated tracked files, including the working DB**, match baseline.
Exactly **26 scoped files** are staged with no unstaged changes. **8 added local
documentation links/anchors** and `git diff --cached --check` pass.

Both reviews and B's validation gates are complete. Authorized scoped publication
uses `main` tracking `origin/main`; the authentication issue below is resolved.
Next backlog is
**R4-S2-T3C - Bound remaining blocking SQL/SMTP boundaries**, under the
existing [C contract](PI-R4.md#r4-s2-t3c).

Publication attempt (2026-10-26): the reviewed scoped commit was created, but
`git push origin main` stalled in Git Credential Manager awaiting interactive
credentials. Stopped only that owned push/helper tree; a noninteractive retry
failed with `Cannot prompt because user interactivity has been disabled` /
`unable to get password from user`. GitHub CLI and inherited GitHub token
credentials are unavailable; SSH refused because no trusted host key is present.
No host trust, credential configuration or remote URL was changed. Read-only
`git ls-remote origin refs/heads/main` verified remote main still at
`06a7f4227188f9dda3c63fb571784fad7c9b517b`. No successful push was claimed then.

The implementation commit retained that earlier blocker handoff. After the user
confirmed authentication readiness, a noninteractive retry still could not
select credentials. `git credential-manager github list` identified multiple
accounts. Using the per-command `-c credential.username=RevanParimi` selection
allowed `git push origin main` to succeed without changing saved configuration,
host trust or the remote URL. Missing noninteractive account selection did not
prove stored accounts were absent. The implementation commit
**`5afe648c7b7244f89b4c0c60ed16893b32f0ddf0`** was verified exactly by
`git ls-remote origin refs/heads/main`; the publication blocker is resolved.

Publication continuation changes only PROGRESS, PI status, this evidence and
the existing roadmap entry. Its scoped self-review confirms B is done, C/parent
remain open, historical failed attempts stay labeled, and no application/test/
config or working data changed. **604 code/config hashes** and **707 unrelated
tracked files including the working DB** still match their reviewed baselines.
Prior focused/full/HTTP/Chrome results remain applicable; no application tests
are rerun for publication prose. Documentation links and staged whitespace are
checked before the separate documentation commit. The final chat response
records its verified remote SHA. Exact next is C; stop after this publication
record is pushed and verified.

## R4-S2-T3C1

Status: done (2026-10-26); required validation and completion record complete.
This session implements C1 only. C2/C3, C, parent
T3/F14/sprint/PI remain open. Prerequisite: B, done.

### Contract defined before implementation

C was split into bounded children in its existing PI section before code
changes. Trigger: all five async signup/login code-issuing handlers directly
perform synchronous SQL and SMTP. Organization signup also performs its name
check on the event loop. Move the entire owning operation to a dedicated
worker, opening/using/closing every store-created SQL session on that thread.
Pass plain request values and service references; never pass HTTP Request,
Response or live Session objects between threads. Preserve provider-first
refusal, limits, reservations/activation, erasure, local-only echo and existing
DTOs/cookies. Verification/resolution and other SQL/mail operations remain C2/C3.

Per-service `auth_code_max_concurrent_requests` is positive, defaults to two
and admits without a waiting queue. Saturation or closed admission returns a
safe 503 plus `Retry-After: 1` before account/SQL/mail work. Positive finite
`auth_code_wait_seconds` defaults to 20 and bounds the HTTP caller's wait.
Timeout returns the ordinary generic 202 `{"status":"accepted"}`; a distinct
mail-timeout status could identify a known account. There is no automatic
replay, delivery promise or rollback promise. Caller cancellation propagates.
Timeout/cancellation retain capacity until the original operation finishes.
Shutdown closes admission and joins accepted calls before owned SQL disposal.
Threads cannot safely be killed; existing SMTP/socket/driver limits remain,
with no new whole-operation or server-drain deadline.

Every ordinary accepted UI request permits manual code entry and explains
possible delivery delay. Busy admission has readable recovery copy; guarded
local echo remains. Acceptance requires a red SQL/mail stall regression,
shared admission across all five routes, no unadmitted writes, late completion
without replay, cancellation/shutdown, safe provider failure, anti-enumeration,
ownership/erasure and session thread ownership. Health plus an authorized SQL
read must complete within a measured one-second total budget under controlled
stalls. Required layers: focused/full pytest, actual PostgreSQL competing
connections, migrated scratch HTTP/restart, actual Chrome capacity/delayed-mail/
manual verification/reload, bindings/syntax and separate final staged review.

### Implementation and preserved boundaries

`AuthCodeExecutor` owns a dedicated bounded pool, atomically checks admission,
copies request context and retains each concurrent future until real completion.
Its caller wait neither cancels the worker nor disguises an operation's own
TimeoutError as the executor's timeout. Late exceptions are consumed without
exposing addresses, codes or provider details. Services lazily owns this pool,
refuses late admission during cleanup and joins it before disposing SQL;
repeated cancellation still waits for that cleanup.

The auth adapter moves organization-name checking plus complete `issue_code`
operations together. Other principal/consent/erasure and verification behavior
is unchanged. UI accepted-state copy now explains uncertainty consistently for
first send and resend, with manual entry and readable admission refusal.
Settings/YAML and [operating guidance](../../OPERATING.md#authentication-code-execution-budget)
define the limits. No dependency, model, schema or migration changes; therefore
no new migration roundtrip is applicable. Existing migrations are exercised by
both HTTP journeys. Working storage and the demo are not test targets.

### Commands and observed evidence

All Python commands use `.resume/Scripts/python.exe`. Ignored sanitized runner
`.pytest_cache/run_r4_s2_t3c1.py <tag> <Python args>` clears inherited DEE/live
configuration, disables real providers and uses isolated stores. Logs share the
ignored `r4-s2-t3c1-` prefix; no credentials or working data are evidence.

- Red: runner `red -m pytest -q --tb=short tests/test_auth_api.py -k
  'slow_auth_issuance and sqlite'`: **2 failed, 33 deselected, 1 warning**.
  Each controlled three-second SQL/mail stall finished before unrelated health
  could execute. This reproduced event-loop blocking, not a fixture/import error.
- Initial green auth API/org-name/debug-echo group: **47 passed, 2 skipped,
  1 warning**. New API scenarios alone (`focused-new` with `-k
  'slow_auth_issuance or admission_retains or real_competing'`): **7 passed,
  7 skipped, 65 deselected, 1 warning**. The global filter deselected config and
  lifecycle cases; the complete focused group below includes them.
- Runner `focused -m pytest -q --tb=short tests/test_auth_api.py
  tests/test_auth_org_name_taken.py tests/test_auth_debug_echo.py
  tests/test_auth_service.py tests/test_auth_store.py
  tests/test_login_redemption_erasure.py tests/test_email_seam.py
  tests/test_ratelimit_auth.py tests/test_service_lifecycle.py
  tests/test_config.py tests/test_api_auth_gate.py tests/test_openapi_contract.py`:
  **219 passed, 27 skipped, 1 warning**, 63.58 s. PostgreSQL parameters skip
  without an explicit disposable DB; they are run separately below.
- Runner `http scripts/smoke_r4_s1_t3a.py --auth-code-workers`:
  **112/112 OK**, exit 0. Actual migrated SQLite app startup, all-plane auth,
  stalled code issuance, failure/recovery, ledger/employer/portal/consent/
  erasure and graceful restart. Two late-issued sessions survive restart.
  Health plus admin-key SQL read totals: mail **0.0088 s**, SQL **0.0086 s**,
  against one second. These are controlled host measurements, not throughput
  or live SMTP claims.
- `.resume/Scripts/python.exe .pytest_cache/run_r4_s2_t3c1_postgres.py`:
  **251 passed, 1 warning**, 215.31 s, no skips; migrated PostgreSQL HTTP
  `scripts/smoke_r4_s1_t3a.py --postgres --auth-code-workers`: **112/112 OK**,
  exit 0. Focused files: auth API/store/service/org-name/debug-echo, email seam,
  auth rate limits, login redemption/erasure, candidate login binding
  concurrency, service lifecycle and config. The owned disposable PostgreSQL
  **18.6** cluster uses read committed and a validation-only 25,000 ms statement
  timeout. Controlled separate connections hold actual conflicting locks;
  `pg_stat_activity` confirms a worker waits on a lock. Health plus admin-key
  SQL read totals: mail **0.0079 s**, SQL **0.0584 s**, against one second.
  Owned server stopped successfully; local runtime/log metadata stays ignored.
- Runner `chrome-reviewed scripts/check_ui_screening_extraction_browser.py
  --auth-code-workers`: **28/28 OK**, exit 0. Actual Chrome sees busy 503 copy,
  delayed generic acceptance before mail delivery, manual six-digit entry,
  successful sign-in and session reload, then the existing screening/recovery
  flow. Runner `browser-resend-final scripts/check_ui_evaluate_browser.py`:
  **1/1 OK and 48/48 OK**, exit 0, including real resend, all-plane navigation,
  evaluation/report/PDF, contact/consent/erasure and reload.
  After the static copy finding below, runner `chrome-copy-final
  scripts/check_ui_screening_extraction_browser.py --auth-code-workers` again
  passes **28/28 OK**, exit 0, and explicitly checks rendered `Requested for`
  with no `Sent to` claim while mail remains held. Runner `ui-copy-final -m
  pytest -q --tb=short tests/test_ui_mount.py tests/test_ui_handlers.py`:
  **20 passed, 1 warning**, 7.80 s.
- Initial full command, runner `full -m pytest -q --tb=short -x`, stopped at
  **1 failed, 3432 passed, 614 skipped, 127 warnings**, 834.04 s. The failure
  was `test_ui_handlers.py::test_shipped_handlers_offline[verification]`:
  six initial-send assertions still required no notice and resend required
  the old copy. Those expectations were missed during implementation review.
  The existing handler tests now assert the rendered delivery-pending notice,
  six manual code boxes, no principal and no verify/replay before manual entry;
  resend still preserves digits, uses its own route and covers local echo.
  Runner `ui-handlers-final -m pytest -q --tb=short tests/test_ui_handlers.py`:
  **8 passed**. This is offline Node behavior, not browser evidence.
  Entire suite restarted as runner `full-final -m pytest -q --tb=short -x`:
  **3721 passed, 630 skipped, 127 warnings**, 1061.38 s, exit 0. Optional,
  environment and unconfigured PostgreSQL skips do not prove omitted cases;
  the actual owned PG run above supplies the required DB evidence. Warnings
  concern existing Starlette/httpx deprecation and SQLite expression-index
  reflection/autogenerate limits, not a new migration.
- Static checks: `node scripts/check_ui_bindings.js` resolves **586 bindings
  across 18 states**; `node --check frontend/api.js`, `frontend/support.js`
  and `frontend/portal-auth.js` pass. Project-Python `py_compile` passes for
  all **11 changed Python files**, including the new executor. `git diff
  --check` and the refreshed **616-file** reviewed-state comparison pass.
  The final browser script compiles again after its copy assertion change;
  `node --check scripts/test_ui_verification.js` also passes.

API regressions cover all five admission refusals and exact unchanged rate/
issuance/challenge rows, late success without duplicate mail, caller cancel,
erasure while delivery is held and surviving unrelated subjects. Session
transaction hooks check one thread owns each Session. Controlled actual SQLite
writer/PG row locks separately prove worker behavior under contention.
Lifecycle regressions cancel shutdown twice, refuse fresh admission and prove
SQL disposal follows actual accepted completion. Existing fake-provider tests
retain local echo, refusal, anti-enumeration, OTP/CSRF/tenant and consent rules.

Harness corrections: initial Chrome reload attempts found an unhydrated page
before the Candidate button was visible. The final check waits for a new
document and its rendered plane button. The additional resend browser initially
reused the previously displayed notice to decide that resend had completed;
first-send now displays that same honest notice. It therefore read the old code.
The harness now observes the actual resend HTTP 202 before reading capture mail;
the clean browser rerun passes. These synchronization corrections do not change
application behavior. Chrome requires existing CDN internet and its harness
terminates Windows app processes; HTTP owns graceful restart evidence. Fakes
and capture mail prove mechanics, not live-provider delivery or scoring quality.

### Implementation self-review

Reviewed `7081eb2` plus the scoped executor, five route adapters, Services cleanup,
Settings/YAML, portal auth, existing test modules and three existing journey
scripts. Specification review maps the child contract to the assertions above
and leaves C2/C3/parent acceptance open. Correctness review traces atomic
queue-free admission, retained futures, context propagation, timeout/operation
exception distinction, no automatic replay, uniform 202 anti-enumeration,
owning-session threads, erasure cancellation, shutdown ordering, safe details,
local echo, readable recovery and reload. No blocking finding remains; this is
same-agent self-review, not independent review.

Acceptance finding (medium): `frontend/Veritas.dc.html`'s login hint and OTP
heading still said a code was on its way / `Sent to`. A timed-out caller could
see those claims before delivery. The hint now describes possible delay and
the OTP heading says `Requested for`. The actual held-mail Chrome assertion
and the complete 20-test UI mount/handler group pass on this correction.
No backend/auth/SQL behavior changed. This finding is resolved.

The reviewed-state snapshot covers **616 code/config files**, now including
the frontend HTML as well as JS.
The final resend harness synchronization was the sole code hash change during
the first full run; no application, test, frontend or config changed during
that run. Its affected actual browser journey was rerun successfully. After
that full run exposed stale offline handler expectations, their small test diff
was separately reviewed and the complete handler group passed. The snapshot
was refreshed for these validation-only changes before `full-final`. During
that run, the two static HTML copy corrections and the browser assertion above
were reviewed and their affected UI/actual Chrome checks rerun successfully.
The snapshot was refreshed to include HTML. No backend, Python test, frontend
logic or config changes followed the HTTP/PG evidence. Full pytest plus the
explicitly repeated affected UI/Chrome checks validate the final reviewed state.

Per-service admission does not bound global/process-wide request load, guarantee
fairness or create durable mail jobs. A transport disconnect may leave its app
task running; even cancelled/timed-out callers can see late delivery/activation.
Thread joins can wait for existing SQL/SMTP limits. Direct synchronous service
callers own scheduling. Authentication verification/resolution and other async
SQL are C3; candidate contact-verification mail is C2. No combined T3, F14,
sprint or PI closure is claimed.

### Completion and handoff

C1 implementation, required validation and completion record are complete.
Focused SQLite/actual PostgreSQL, migrated HTTP/restart on both, actual Chrome,
offline UI/static checks and the final full suite pass. The initial failed
full run, stale handler expectations, browser synchronization corrections and
static delivery-copy finding remain recorded with their resolutions. Only
affected UI checks were repeated for the final copy change; backend, tests and
configuration remain at their validated state. No live-provider/empirical
quality, schema migration, working-store change or demo restart is claimed.

The handoff/feature/PI/roadmap/operating records agree. C2/C3, C, T3/F14/sprint/
PI remain open; exact next is **R4-S2-T3C2 - Bound contact-verification mail
operations** under its [existing contract](PI-R4.md#r4-s2-t3c2). Do not start C2
in this session. The distinct final staged self-review and scoped publication
follow this completion record.

Distinct final staged self-review (2026-10-26), after required validation and
the completion record: reviewed the exact **22-file staged diff** against
`7081eb2`, covering the executor, all five adapters, Services ownership,
Settings/YAML, auth JS/static HTML, existing API/config/lifecycle/fixture/Node
tests, three existing HTTP/browser journey scripts and completion/operating
documentation. Specification review maps every C1 criterion to its observed
evidence, keeps C2/C3/parent gates open and labels actual PG/Chrome separately
from skipped environments and capture providers. Correctness review traces
atomic admission, slot retention, session threads, context, late exceptions,
uniform timeout/no replay, erasure, repeated cancellation and join-before-SQL
disposal. UI manual entry, busy recovery, no premature delivery claim, resend,
local echo and reload agree with the actual browser checks. No blocking finding
remains. This is same-agent self-review, not independent review.

The final **616 code/config hashes** match the reviewed state after the full
run and separately repeated copy-affected UI checks. **712 unrelated tracked
files, including the working DB**, match baseline. No dependency/image/migration
change is needed; existing package discovery includes the new auth module.
No secrets, working data or ignored validation artifacts are staged. Only final
review prose changes after this pass; documentation links, staged whitespace,
scope and preservation are checked before commit. Publication uses `main`
tracking `origin/main`, with GCM account selection limited to the command.
The final response reports the verified remote SHA; stop after publication,
without starting C2.

Final pre-commit checks pass: **15 added local documentation links/anchors**,
`git diff --cached --check`, the 616-file reviewed-state comparison and the
712-file preservation comparison. Exactly **22 scoped files** are staged,
with no unstaged or untracked changes. No application changes followed review.

## R4-S2-T3C2

Status: done (2026-10-27); required validation and completion record complete.
Prerequisite C1 is published at `02f536f`. Only C2 is
this session's task; C3, C, T3/F14/sprint/PI remain open.

### Contract defined before implementation

Async `POST /portal/verifications`, shared by contact start and resend, directly
performs synchronous SQL/mail. Move the complete owning operation into a
dedicated bounded worker. No Request/Response or live Session crosses threads.
Candidate identity/CSRF, destination proof, method/consent gates, challenge
cooldown/supersession, provider-failure rollback, erasure serialization and
guarded local echo remain. Self-attestation shares this start entry point and
retains its result; confirm/list/documents and other SQL are not moved.

Positive `contact_code_max_concurrent_requests` defaults to two per Services,
separate from auth issuance. There is no waiting queue. After the principal/
CSRF gate, full/closed admission refuses safe 503 plus `Retry-After: 1` before
verification-service SQL/mail. Finite positive `contact_code_wait_seconds`
defaults to 20 and bounds the caller wait, not the operation. Timeout returns
504 `contact_code_pending`, without a code or invented success DTO. The UI
explains possible late delivery, saved-state recovery and manual confirmation,
without automatic replay. Busy admission has readable recovery copy.

Timeout/cancellation retain capacity until actual completion; cancellation
propagates. Shutdown closes both pools and joins accepted calls before SQL
disposal. Share C1's existing mechanics through a neutral executor instead of
copying lifecycle/admission code; preserve C1's separate settings/pool and
opaque 202 timeout. No thread kill, rollback promise, durable mail queue or new
whole-operation/server-drain deadline; existing driver/socket limits remain.

SMTP retains its candidate-locked transaction (SQLite writer lock). Competing
writes/erasure can wait; already-delivered mail cannot be recalled. Earlier
principal resolution, periodic session-touch writes and other synchronous SQL
remain C3. Measure health plus an admin-key SQL read against a one-second total
budget under controlled mail/SQL stalls, without claiming that every
authenticated write or stale-session refresh is nonblocking.

Acceptance requires red event-loop SQL/mail stalls; shared start/resend
admission and unchanged unadmitted rows; late success/manual recovery without
replay; cancellation, safe provider failure/rollback, session threads and
shutdown; actual SQLite/PG competing transactions and erasure ordering with a
surviving subject. Required layers: focused/full pytest, C1 shared-executor
regressions, actual disposable PG, migrated HTTP/restart, real contact Chrome
busy/timeout/refresh/manual confirm/reload, offline handlers, bindings/syntax,
implementation and distinct final staged self-reviews, scoped commit/push and
remote verification. No schema/migration change. Stop before C3.

### Implementation and observed evidence

C1's executor moves from `auth/execution.py` to `core/blocking.py`, with neutral
names and a required operation name for safe refusal codes/thread labels.
Admission, context propagation, future retention, wait/cancel and join semantics
are unchanged. Services owns separate contact/auth pools, closes them together
and joins both before SQL disposal. The contact adapter awaits the entire
existing service; transaction structure and stored schemas do not change.
The UI maps busy/closed/uncertain responses and reuses its existing own-subject
refresh, Enter delivered code and confirmation flow. No new queue/status API.
See [operating limits](../../OPERATING.md#contact-code-execution-budget).

All Python commands use `.resume/Scripts/python.exe`. Ignored sanitized runner
`.pytest_cache/run_r4_s2_t3c2.py <tag> <Python args>` clears inherited DEE/live
config and disables external providers; all stores/media/mail are synthetic.
Logs and runtime metadata use the ignored `r4-s2-t3c2-` prefix. No URL credentials,
working data or raw contact/code values are published as evidence.

- Red: runner `red -m pytest -q --tb=short tests/test_verification_api.py -k
  'slow_contact_start and sqlite'`: **2 failed, 16 deselected, 1 warning**,
  13.49 s. In each controlled three-second mail/SQL stall, unrelated requests
  ran only after the stalled operation finished (SQL POST **3143.3 ms**).
  This reproduces event-loop blocking, not a fixture/import failure.
- Initial green API/auth/lifecycle group (`green`): **75 passed, 9 skipped,
  1 warning**, 45.77 s. New contact API group (`owning-final`, filter `contact_`):
  **8 passed, 8 skipped, 14 deselected, 1 warning**, 14.39 s. A later erasure
  case is included in the full focused group below, not this earlier run.
- Runner `focused -m pytest -q --tb=short -x tests/test_verification_api.py
  tests/test_verification_delivery.py tests/test_verification_service.py
  tests/test_verification_concurrency.py tests/test_verification_consent.py
  tests/test_verification_erasure.py tests/test_verification_otp.py
  tests/test_config_verification.py tests/test_service_lifecycle.py
  tests/test_auth_api.py tests/test_auth_debug_echo.py
  tests/test_auth_org_name_taken.py tests/test_config.py tests/test_ui_mount.py
  tests/test_ui_handlers.py tests/test_api_auth_gate.py tests/test_openapi_contract.py`:
  **218 passed, 32 skipped, 1 warning**, 91.58 s. Unconfigured PG cases skip
  here; actual PostgreSQL is a separate gate below.
- Runner `http scripts/smoke_r3_s1_t2.py --contact-code-workers`: **32/32 OK**,
  exit 0. Actual migrated SQLite composition, delivery refusal/rollback,
  prior-code preservation, challenge expiry/budget, cross-subject refusal,
  held mail/SQL admission, timeout-to-late-success and manual saved-state
  recovery, restart, erasure and two graceful SQL disposal/detachment lifespans.
  During controlled stalls, health plus authorized SQL read totals were mail
  **0.0111 s** and SQL **0.0126 s**, against one second on this host.
- Runner `chrome-final scripts/check_ui_verification_browser.py
  --contact-code-workers`: **1/1 OK and 23/23 OK**, exit 0. Actual Chrome
  candidate/CSRF/provider/refusal/expiry/reload/session-loss flow, plus shared
  busy refusal, caller wait uncertainty without a sent claim, own-state refresh,
  late code confirmation without resend and actual reload. Console/privacy
  assertions pass. Chrome requires existing CDN internet and terminates Windows
  app processes; migrated HTTP owns graceful restart evidence.
- `node --test scripts/test_ui_verification.js`: **68 passed**, including three
  new busy/closed/pending cases which settle, retain destination, refresh saved
  status and confirm explicitly with exactly two total POSTs (start + confirm).
  This is offline handler evidence, not a browser run.
- Static: **586 bindings across 18 states** resolve; `node --check frontend/api.js`,
  `frontend/support.js` and `frontend/portal-auth.js` pass. Project-Python
  `py_compile` passes for all **12 changed Python files**, including the moved
  executor. `git diff --check` passes. Reviewed-state snapshot: **616 code/config
  files**, including HTML/JS.
- Actual PostgreSQL owned runner `.pytest_cache/run_r4_s2_t3c2_postgres.py`:
  **253 passed, 1 warning**, 228.36 s, no skips, on disposable **PostgreSQL 18.6**,
  read committed, Asia/Calcutta,
  validation-only `statement_timeout=25000`. It runs verification API/delivery/
  service/store/concurrency/consent/erasure/OTP, verification config, lifecycle,
  auth API/debug/org-name, config, auth gate and OpenAPI; then migrated contact
  and C1 auth worker HTTP/restart journeys. Contact `--postgres
  --contact-code-workers`: **32/32 OK**; C1 `--postgres --auth-code-workers`:
  **112/112 OK**, both exit 0. Contact health plus authorized-read totals:
  mail **0.0623 s**, SQL **0.0166 s**, against one second. C1 totals:
  mail **0.0075 s**, SQL **0.0809 s**, against one second. These are controlled
  host observations, not production latency/throughput claims. Owned server
  stopped successfully (stop exit 0, 31.22 s); runtime metadata stays ignored.
  No migration roundtrip is applicable because
  no model/schema/migration changes; existing migrations run in both journeys.
- Full regression: runner `full -m pytest -q --tb=short -x`: **3738 passed,
  639 skipped, 127 warnings**, 1144.05 s, exit 0. Optional/environment and
  unconfigured PG skips do not prove omitted cases; the actual PG gate above
  supplies the required concurrency evidence. Warnings concern the existing
  Starlette/httpx deprecation and SQLite expression-index reflection/autogenerate
  limitations. No application/test/config changes followed the reviewed snapshot.

The API regressions assert unchanged unadmitted verification/challenge/audit
rows, both subject actors sharing capacity, unauthenticated 401 before service
admission, late success/failure, no automatic replay, caller cancellation,
saved-state/manual confirmation and foreign 404. Transaction hooks assert one
thread owns each Session. Controlled separate connections hold real SQLite
writer/PG candidate locks; PG observes actual `pg_stat_activity` lock waits.
Erasure before issuance leaves no restored subject/verification/challenge or
mail and preserves another subject. Existing dispatch-vs-erasure races prove
activation-first secrets are swept after the serialized erasure; the survivor
is now asserted too. Lifecycle tests cover both pools, repeated cancellation,
late-admission refusal and SQL disposal only after accepted work finishes.

Harness corrections: the first owning-group run was **1 failed, 1 passed,
14 deselected, 1 warning** because a fresh self-attestation exceeded its synthetic
50 ms caller budget. Capacity had recovered correctly. The check now allows
the documented 200/504 outcomes, waits for that accepted work and asserts the
exact saved verified record; it still rejects busy refusal. The initial Chrome
run required the background blocking request to time out even though the test
released it after observing busy copy, before its wait budget expired. That
background request can correctly return 200 or 504; the target browser timeout
still must return the actual uncertain-state copy before release. The clean
Chrome rerun passes. No application behavior changed for these corrections.

### Implementation self-review

Reviewed `02f536f` plus the neutral executor move, two Services pools and cleanup,
auth import-only adaptation, verification start adapter, Settings/YAML, three
UI error messages, existing API/config/concurrency/lifecycle/Node tests and the
two existing contact journeys. Specification review maps C2's contract to the
checks above and keeps C3/parent acceptance open. Correctness review traces
queue-free admission, future/context retention, timeout/operation-error
distinction, owning-session threads, late error privacy, safe 504/no replay,
authentication/CSRF/destination/consent guards, failure rollback, erasure ordering,
local echo, readable recovery and join-before-SQL disposal. Neutral extraction
does not change C1's statuses or scheduling. No blocking finding remains;
this is same-agent self-review, not independent review. Shared-worker and
contact-specific acceptance and all required validation gates pass.

Limits: per-service admission is not global request concurrency/RSS or durable
jobs. Thread joins can wait on existing SQL/SMTP limits; an HTTP failure does
not imply rollback. SMTP's candidate/SQLite writer lock, earlier auth/session
touches and other synchronous SQL remain explicit. Direct synchronous callers
own scheduling; fake providers prove mechanics, not live delivery or quality.

### Completion and handoff

C2 implementation, required validation and completion records are complete.
Focused SQLite/actual PostgreSQL, migrated contact HTTP/restart on both, C1
actual PG HTTP/restart, real contact Chrome, offline handlers/static and final
full pytest pass. The two harness timing corrections remain recorded with their
clean reruns; neither changed application behavior. The neutral executor move
preserves C1's pool/settings/opaque timeout; C2's separate pool reports an honest
uncertain outcome and recovers through own saved records without replay.

No schema/migration, live delivery, measured scoring quality or working-store
change is claimed. The owned PostgreSQL server is stopped; demo remains untouched.
The PI/feature/operating/verification/roadmap/handoff records agree. C3, C, parent
T3/F14/sprint/PI remain open. Exact next is **R4-S2-T3C3 - Bound remaining
measured SQL and review combined T3 acceptance**, under its
[existing contract](PI-R4.md#r4-s2-t3c3): inventory/measure and define bounded
child groups before implementation. Do not start C3 in this session.
The distinct final staged self-review and scoped publication follow this record.

Distinct final staged self-review (2026-10-27), after required validation and
the completion record: reviewed the exact **22-file staged diff** (including
the executor rename) against `02f536f`. Scope: neutral executor move and auth
adaptation; contact adapter and Services pools/cleanup; Settings/YAML; three UI
messages; existing API/config/concurrency/lifecycle/fixture/Node tests; two
existing contact journeys; and operating/verification/feature/PI/handoff/roadmap/
evidence documentation. Specification review maps all C2 criteria to recorded
checks and leaves C3/parent acceptance open. Correctness review traces immediate
admission, retained futures/context, owning-session threads, error privacy,
timeout/no replay, auth/CSRF/destination/consent, provider rollback, erasure,
local echo, manual saved-state recovery and join-before-SQL disposal. C1's
separate admission and opaque 202 remain covered by actual PG HTTP and full
regression. No blocking finding remains. This is same-agent self-review,
not independent review.

All **616 code/config hashes** match the reviewed/full-tested state. **712
unrelated tracked files, including the working DB**, match baseline; preservation
handles both sides of the executor rename. Existing package discovery includes
the moved core module; no dependency/image/migration changes are needed.
No secrets, working data or ignored validation artifacts are staged. Only
final review prose changes after this pass. Documentation links, staged
whitespace, exact scope and preservation are checked before commit. Publication
uses `main` tracking `origin/main`, with per-command GCM account selection and
no saved credential/remote changes. The final response records the remotely
verified SHA. Stop after publication, without starting C3.

Final pre-commit checks pass: **16 added local documentation links/anchors**,
staged whitespace, core-module compilation, reviewed-state and preservation
comparisons. Exactly **22 scoped file changes** (23 paths counting both sides
of the rename) are staged, with no unstaged/untracked changes.
