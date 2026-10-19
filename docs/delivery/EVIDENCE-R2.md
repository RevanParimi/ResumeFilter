# PI-R2 completed evidence

Reference history, consolidated 2026-10-18. Start with [the handoff](../PROGRESS.md)
and [PI-R2](PI-R2.md) for current status. Each task's original contract,
decisions, validation and limits are retained below; historical next-task pointers
and commands describe their recorded date, not today's execution order or paths.
Moved pytest cases now live in their product-area modules. No old result is a new
execution, independent review, live-provider check or broader quality claim.

- [R2-S1-Q](#r2-s1-q)
- [R2-S1-T1](#r2-s1-t1)
- [R2-S1-T2](#r2-s1-t2)
- [R2-S1-T2A](#r2-s1-t2a)
- [R2-S1-T2B](#r2-s1-t2b)
- [R2-S1-T3](#r2-s1-t3)
- [R2-S2-Q](#r2-s2-q)
- [R2-S2-T1](#r2-s2-t1)
- [R2-S2-T2](#r2-s2-t2)

## <a id="r2-s1-q"></a>R2-S1-Q - Input and evidence sprint integration review

Status: done (2026-10-12). PI/sprint: R2/R2-S1. Audit: F07; F02/F14 bounded overlap.
Prerequisites: [T1](#r2-s1-t1), [T2](#r2-s1-t2), [T3](#r2-s1-t3), done.

### <a id="r2-s1-q--scope-and-acceptance"></a>Scope and acceptance

Validate T1 model structures, T2 input/parser containment and T3 neutral GitHub
context together through actual app composition. This closure adds a combined
fake-provider journey; fix only acceptance-blocking findings. Preserve advisory
review, domain-independent evaluation, tenant/candidate ownership, erasure,
historical report semantics and existing working data. No style/risk redesign,
deployment, external delivery or user-data cleanup.

| ID | Observable contract | Required evidence |
|---|---|---|
| AC1 | Empty/unreadable/oversized/resource-hostile inputs fail before any model/GitHub call or intake write through all four doors | Migrated scratch HTTP, safe details, provider counters and store row counts |
| AC2 | Readable text/PDF with malformed/failed model output retains deterministic assessment and neutral GitHub context in both domains | Same-app baseline comparisons, valid sparse/structured replies and partial/outage GitHub cases |
| AC3 | Only linked claims carry their own fetch context; saved reports and valid batches retain actor ownership/advisory behavior across restart | Multiple orgs/candidates, claim anchors, persisted readback and actual restart |
| AC4 | Existing PDF containment and packaged worker remain effective on Linux/image runtime | Current allowlisted snapshot/image hashes, real RLIMIT/allocation, parser/resource regressions and combined HTTP |
| AC5 | Final combined diff has no unresolved acceptance findings; current regressions and handoff are complete | Recorded self-review, focused/full pytest, Chrome/contract/bindings, preservation and documentation checks |

Reuse T1's ModelFake, T3's MockTransport factory and the shared smoke harness;
provider overrides remain inside the isolated child app. SQL/migration/UI
handlers/scoring formulas remain unchanged unless a concrete review defect
requires a bounded fix. No PostgreSQL gate applies to the existing sprint
changes; browser execution supplements backend closure and preserves T3's
rendered report check. Linux validation uses the prior owned VM with new Q
artifacts/image; old T2B evidence is retained.

### <a id="r2-s1-q--evidence-and-review"></a>Evidence and review

Separate same-agent review, 2026-10-11: HEAD `5480498` plus the combined T1/T2/T3
uncommitted changes and new `scripts/smoke_r2_s1_q.py`. Reviewed AC1-5, all six
model consumers and strict whole-reply fallback, four HTTP intake doors and
shared graph/ingest/batch boundaries, PDF worker limit ordering/pipe cleanup,
verification compatibility, repository-result consumers and neutral scoring,
current actor/erasure guards, persisted schema/history and provider diagnostics.
No unresolved application findings or application changes in Q. The new runner
composes the existing fakes inside its isolated child, compares complete claim
assessment with an abstaining baseline and rule interview scores, and shuts down
owned processes. An initial launcher import error occurred before app startup;
the project test-helper path was corrected and the journey rerun. That error is
not a defect reproduction. Prior leaf records own intended failing reproductions.

Starting workspace: 838 existing files in `.pytest_cache/r2-s1-q-baseline.json`.
Reviewed state: 40 code/test/journey hashes in `.pytest_cache/r2-s1-q-reviewed.json`.
No independent review, live-provider compatibility or empirical quality claim.
Commands use `.resume/Scripts/python.exe`. Windows ignored runner
`.pytest_cache/run_r1_s2_q.py NAME ARGS` sanitizes inherited settings and captures
`.pytest_cache/r1-s2-q-NAME.txt`; no external credentials or working stores.

| Check | Actual evidence |
|---|---|
| Combined migrated HTTP | `r2-s1-q-http-initial-corrected scripts/smoke_r2_s1_q.py`: 234/234, 51.71s; startup to 0029, four-door safe refusal/provider counters/eight-store counts, both domains/text/PDF, malformed/failed replies with GitHub outages/partial/success, valid capped opinion, linked-claim cache, batch/org/candidate denials, report/interview readback and actual restart |
| Reviewed focused | `r2-s1-q-focused -m pytest -q --tb=short` plus files below: 576 passed, 1 Starlette/httpx deprecation warning, 178.45s |
| Full regression | `r2-s1-q-full` (defaults to `-m pytest -q --tb=short`): 3237 passed, 476 skipped, 113 warnings, 907.53s; exit 0 |
| Browser | `r2-s1-q-browser scripts/check_ui_github_browser.py`: 22/22, 28.47s runner; actual Chrome/CDP signup, TXT/PDF batch, neutral 404 report context, reasons, judgments/history, deletion and clean console; fake providers, CDN internet |
| UI API contract | `r2-s1-q-contract scripts/check_ui_screening_contract.py`: 32/32, 29.47s runner; scratch HTTP cookie/CSRF, queue/report/outcome shapes, deletion |
| Static | `node scripts/check_ui_bindings.js`: 425 bindings / 10 states; `git -c core.safecrlf=false diff --check`: passed |
| Linux/image | `.pytest_cache/r2_s1_q_snapshot.py`, `r2_s1_q_ssh.py upload q-source.tar.gz q-source-manifest.json`, `r2_s1_q_ssh.py run .pytest_cache/r2_s1_q_guest_build.sh q-build`: new image build passed; all 657 source / 236 shipped hashes match the 40-file reviewed state |
| Linux acceptance | `r2_s1_q_ssh.py run .pytest_cache/r2_s1_q_guest_checks.sh q-checks`: real hard RLIMIT_AS 64 MiB refused 256 MiB allocation; `python -m pytest -q --tb=short tests/test_pdf_resource_limits.py`: 68 passed, 98.41s; `python -u scripts/smoke_r2_s1_q.py`: 234/234; native packaged worker retained blank-page metadata and safely refused over-page input; combined command exit 0, 181.43s |
| Preservation | `.pytest_cache/verify_r2_s1_q.py`: 838-file baseline, 828 unchanged prior files, all 40 reviewed hashes and working DB unchanged; only scoped docs/archival changes, no unrelated changes/additions; 238 local Markdown links, archived IDs/count, next-task status and diff checks passed |

Focused files: `tests/test_model_output_boundaries.py tests/test_llm_config.py
tests/test_candidate_extractor_llm.py tests/test_interview_scoring_llm.py
tests/test_plausibility.py tests/test_ai_signals_node.py tests/test_claim_extraction.py
tests/test_probe_generation.py tests/test_silent_swallows.py
tests/test_resume_input_boundary.py tests/test_pdf_resource_limits.py tests/test_pdf.py
tests/test_verification_documents_parse.py tests/test_github_repo_evidence.py
tests/test_provenance.py tests/test_scoring.py tests/test_api.py
tests/test_screening_api.py tests/test_screening_batches_api.py
tests/test_openapi_contract.py tests/test_image_contents.py
tests/test_requirements_pinned.py tests/test_smoke_harness.py`.

Image `veritas:r2-s1-q` is non-root appuser, Python 3.12.15/pypdf 6.13.3,
Debian 13 on Linux 6.12.110-0-virt:
`sha256:bbc77d9a4c0070d9c9942c01d6a608222354d463b4787d2af3708dfde143f5cc`.
New Q artifacts/logs live beside retained T2B evidence in the scratch directory
named by `.pytest_cache/r2-t2b-linux-runtime.json`; old snapshot/image preserved.
`r2_s1_q_ssh.py download q-container-freeze.txt` retrieved runtime dependencies;
`r2_s1_q_ssh.py run .pytest_cache/r2_t2b_guest_shutdown_owned.sh q-shutdown`
confirmed no active containers and requested owned VM shutdown; PID 25540 exited, disk/logs retained.
Linux full pytest is not rerun in Q; the current Windows full suite is required.
No SQL/concurrency/migration/public-schema/UI-handler change, so no PostgreSQL
gate applies. Browser/bindings do not replace HTTP/parser validation; synthetic
providers and regressions do not establish assessment accuracy or live delivery.

### <a id="r2-s1-q--handoff"></a>Handoff

AC1-5 and required gates passed; R2-S1 and bounded F07 input/provider/evidence
remediation are complete. PI-R2 stays in progress for R2-S2; F02 infrastructure
and F14 operational residuals remain in their mapped tasks. No application,
dependency, SQL/schema, working-data or deployment change in Q. Full warnings
are Starlette/httpx deprecation and SQLite expression-index reflection/comparison;
skips cover environment/optional cases, not passing PostgreSQL/live-provider gates.
New runner/leaf evidence is retained; detailed completed T1/T3 records archived
with corrected links, T2 child-group and Q sprint summaries remain in tasks.
Working DB SHA256 remains `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Local demo health/UI returned 200; its server remains running. Next: **R2-S2-T1**,
remove style from factual-risk fusion; not started. Stop after Q.

## <a id="r2-s1-t1"></a>R2-S1-T1 — Validate model response structures

Status: done (2026-10-10). PI/sprint: R2/R2-S1. Audit: F07, structure slice only.
Prerequisite: [R1-S2-Q](EVIDENCE-R1.md#r1-s2-q), done.

### <a id="r2-s1-t1--scope-and-acceptance"></a>Scope and acceptance

Six reachable JSON consumers: `graph/nodes/{claim_extraction,plausibility,
ai_signals,probe_generation}.py`, `candidates/extractor.py` and
`interview/scoring.py`; shared parser `services/llm.py`.
Before this task, malformed structures crashed, coerced numeric strings/nonfinite
values or retained valid fragments. Reject the whole invalid reply
and retain the existing deterministic result. Preserve valid replies, confidence
and interview delta caps, domain-independent claims and advisory behavior.
Optional schema fields remain optional; required scoring keys and collection
member fields must exist. No input/PDF, GitHub polarity, style fusion, UI,
database schema or provider-delivery changes belong to this task.

| ID | Observable contract | Evidence/result |
|---|---|---|
| AC1 | Parser returns only JSON objects; rejects nonfinite JSON without rescuing nested fragments | Passed: `test_llm_config.py` |
| AC2 | Each consumer falls back for wrong top-level type, null/wrong collections, invalid members, missing required keys and transport errors | Passed: affected consumer regressions |
| AC3 | Numeric strings, booleans, nonfinite and out-of-range numbers cannot contribute scores/confidence; invalid mixed replies contribute nothing | Passed: affected consumer regressions |
| AC4 | Valid sparse extraction and interview adjustments, enum strings, source spans and confidence caps remain usable | Passed: existing/added valid-reply tests |
| AC5 | Actual migrated scratch app evaluates/ingests with malformed provider, persists deterministic reports, preserves actor access and interview baseline | Passed: HTTP/subprocess smoke |

Required: failing behavioral reproductions, focused/full pytest, actual HTTP
journey, bindings, diff review and preservation checks. Browser/PG gates do not
apply: no visible contract, SQL/transaction/migration changes. Fakes prove
fallback mechanics, not live-provider compatibility or scoring accuracy.

### <a id="r2-s1-t1--evidence-and-review"></a>Evidence and review

- Before fix: `.resume/Scripts/python.exe -m pytest -q --tb=short
  tests/test_model_output_boundaries.py tests/test_llm_config.py`:
  **115 failed, 54 passed (8.14s)**. Intended failures: wrong-shape exceptions,
  numeric coercion/nonfinite promotion, retained invalid fragments and raw
  provider detail in fallback logs/warnings. No fixture/import failures.
- Seven production files changed. Shared parsing refuses nonobjects/nonfinite
  values. Existing Claim/CandidateProfile contracts validate complete extraction
  replies strictly; small local reply schemas cover opinions, probes and capped
  interview dimensions. Valid integer numbers and enum strings remain accepted.
  Optional extraction fields remain optional; null lists/invalid members do not.
  Profile warnings now expose only `llm_extraction_failed`; logs expose error
  class only. Invalid scores/confidence are refused rather than clamped into
  plausible opinions. Valid confidence/delta caps and scoring mathematics stay
  unchanged; public schemas, scorer version and historical stored reports stay
  unchanged. No migration/data rewrite.
- Reviewed-state focused command: `.resume/Scripts/python.exe -m pytest -q
  --tb=short tests/test_model_output_boundaries.py tests/test_llm_config.py
  tests/test_candidate_extractor_llm.py tests/test_interview_scoring_llm.py
  tests/test_plausibility.py tests/test_ai_signals_node.py
  tests/test_claim_extraction.py tests/test_probe_generation.py
  tests/test_silent_swallows.py tests/test_normalize_integration.py
  tests/test_extraction_coverage.py tests/test_interview_api.py tests/test_api.py`:
  **310 passed, 1 warning (28.15s)**; Starlette/httpx TestClient deprecation.
- `node scripts/check_ui_bindings.js`: **425 bindings / 10 states**, passed.
  `git diff --check`: passed; Git CRLF conversion notices are not whitespace
  failures.
- Final `.resume/Scripts/python.exe -m pytest -q --tb=short`: **3059 passed,
  476 skipped, 113 warnings (811.44s)**, exit 0. Sanitized subprocess cleared
  inherited DEE settings, pinned no key/null email/memory vector store, localhost
  GitHub and no config, with `PYTHONPATH=src`; no PostgreSQL URL. Log:
  `.pytest_cache/r2-s1-t1-full.txt`. Skips include unavailable PostgreSQL/optional
  gates; this task has no SQL/transaction/migration or UI/browser gate.
  Warnings: 1 Starlette/httpx deprecation, 111 SQLite expression-index reflection
  warnings and 1 Alembic expression-index comparison warning.
- `.resume/Scripts/python.exe -u scripts/smoke_r2_s1_t1.py`: **23/23 passed**,
  real child startup/migration to 0029, five invalid-provider modes compared
  with the abstaining baseline, report readback, org ingest/profile fallback,
  two-org/two-candidate denials, mixed-dimension interview baseline, valid
  capped opinions, all six provider consumers and report/turn readback after
  actual restart. Synthetic logs in `%TEMP%/r2-s1-t1-7vyl7jtb/server.log`.

Separate self-review, 2026-10-10: HEAD `54804988` plus these seven production
diffs, three existing test diffs, new boundary tests and smoke. Checked AC1–AC5,
all six callers (including shared org/batch ingest and interview service),
atomic acceptance of provider replies, fallback privacy, present ownership,
valid sparse profiles, enum/numeric compatibility, schema/history and scope.
Tests compare whole deterministic outcomes; synthetic opinions prove mechanics.
Review findings (both resolved):
- Medium, `claim_extraction._parse_llm_claimset`: false/empty-array
  `source_excerpt` was replaced by valid text through truthiness, retaining
  malformed data. Explicit None handling and strict validation now refuse;
  invalid-excerpt regression passes. Scalar object checks improve diagnostics.
- Medium, `services.llm._extract_json`: prose around an array let recovery accept
  its nested score object. Additional parser reproduction: `.resume/Scripts/
  python.exe -m pytest -q --tb=short tests/test_llm_config.py`, **1 failed,
  17 passed (4.44s)**, intended nested-object acceptance. Recovery now captures
  the outer array and abstains. Final focused/journey checks include prose-array
  rejection. Superseded full run interrupted; final run restarted after fix.
Final smoke review covered the isolated provider override, sanitized child env,
actual migrations, stable deterministic comparison, actor denials and restart.
No remaining findings; no independent review claimed. Initial runner errors
(speech setting, lazy fake import and report route) were corrected and the
whole journey rerun. A separate SDK/local-wire attempt timed out during lazy
generated-resource imports (scratch faulthandler diagnosis); it is not passing
provider evidence. Final journey reuses FakeLLM and makes no SDK/live-provider
compatibility claim. Production dependencies were not changed.

### <a id="r2-s1-t1--handoff"></a>Handoff

AC1–AC5 and required gates passed. Working DB SHA256 remains
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`;
141 baseline unrelated file hashes preserved. Documentation links/status and
final diff checks passed. Task-owned child servers stopped. No working migration,
dependency change, cleanup, deployment or external message.
R2-S1/PI-R2/F07 remain open. Next: **R2-S1-T2** (resume input validation),
starting with its PI section and a bounded brief. T2 not started; stop after T1.

## <a id="r2-s1-t2"></a>R2-S1-T2 - Refuse unreadable or oversized resumes

Status: done (Unicode correction validated 2026-10-13; original closure 2026-10-11). PI/sprint: R2/R2-S1. Audit: F07; F14 input overlap.
Prerequisite: [R2-S1-T1](#r2-s1-t1), done.

Split into two bounded contracts because input acceptance and hostile parser
resource containment require different implementation and validation. The PDF
helper is also used by verification documents; page counts alone do not bound
decompression, recursive objects or parser stalls.

| Child | Contract | Status |
|---|---|---|
| [R2-S1-T2A](#r2-s1-t2a) | Shared validation, safe refusals before persistence, decoded-text caps and readable sparse inputs | Done (2026-10-10) |
| [R2-S1-T2B](#r2-s1-t2b) | Explicit PDF page/work/expansion limits with real parser containment and compatibility checks | Done; Unicode correction validated (2026-10-13) |

Both child acceptance contracts passed; child records own exact evidence and
limits. T2B includes actual Linux allocation/stall/cleanup, migrated HTTP,
production-image parsing and a full suite on hash-matched source.
[Q](#r2-s1-q) owns the completed combined R2-S1/F07 gate; PI-R2 is complete within its bounded scope. T2B owns the subsequent Unicode correction and validation. No OCR/DOCX expansion, scoring,
GitHub polarity, UI redesign or working-data rewrite is included.

## <a id="r2-s1-t2a"></a>R2-S1-T2A - Align resume input validation

Status: done (2026-10-10). Parent: [R2-S1-T2](#r2-s1-t2), done 2026-10-11.
Prerequisite: [R2-S1-T1](#r2-s1-t1), done. Evidence/handoff below records
the T2A session; subsequent parent closure is owned by [T2B](#r2-s1-t2b).

### <a id="r2-s1-t2a--scope-and-acceptance"></a>Scope and acceptance

Evaluation currently continues after PDF/empty-input failure. Candidate/batch
intake leaks parser exception text and batch registration accepts whitespace.
Use one input validator at graph, candidate and batch boundaries, before model
work or persistence. Keep text precedence when both sources are supplied,
existing raw-size error messages and the standard 422 detail envelope.

| ID | Observable contract | Evidence |
|---|---|---|
| AC1 | Whitespace and unreadable corrupt/truncated/password-protected/image-only PDFs yield safe 422 errors, no report/candidate/batch saved | Passed: boundary tests and HTTP |
| AC2 | Strict base64 and decoded PDF text limits apply to every intake path; exact boundaries remain valid | Passed: boundary/PDF tests and HTTP |
| AC3 | Direct graph and ingest callers refuse before model/store work; batch registration is atomic for invalid items | Passed: direct callers, SQL counts, legacy failure isolation |
| AC4 | Readable TXT/Markdown/PDF and sparse text retain advisory fallback; org ownership and erasure guards remain | Passed: focused existing tests and HTTP/restart |

Required: intended failing regressions, focused/full pytest, migrated scratch
HTTP, bindings, separate recorded self-review, diff and preservation checks.
No screen/handler/response-shape or SQL/migration change: browser/PostgreSQL
gates do not apply. External providers stay fake. Parser page/time/expansion
containment is explicitly [T2B](#r2-s1-t2b), not proved by T2A text caps.

### <a id="r2-s1-t2a--evidence-and-review"></a>Evidence and review

- Before fix: `.resume/Scripts/python.exe -m pytest -q --tb=short
  tests/test_resume_input_boundary.py tests/test_pdf.py`: **38 failed, 7 passed,
  1 warning (16.02s)**. Intended failures were successful evaluations/registrations,
  leaked parser detail, permissive base64 and decoded-size acceptance, not fixtures.
- Shared `core/resume.py` owns safe refusal and text validation. The graph's
  first node raises `ResumeInputError` before downstream work; `/evaluate`
  maps it to 422 and never saves a report. Admin/org upload and batch decoding
  use the same boundary; direct ingest/registration revalidate before writes.
  Raw size messages and `item N:` prefixes remain compatible. Password-protected
  parse failures expose only `pdf_parse_failed`; blank/image-only PDFs expose
  `pdf_no_readable_text`; whitespace text exposes `empty_resume`. Text wins
  when both inputs are supplied; empty text can still fall back to PDF.
- Base64 decoding is strict; resume PDF parsing checks the header and uses
  strict reader mode. Verification's metadata/page-count helper retains its
  reader policy and blank-document behavior, with strict base64 already enforced
  by its caller. No public response shape, score math, schema/migration or
  historical record rewrite. Decoded-text cap includes padding before trimming.
- Final focused `.resume/Scripts/python.exe -m pytest -q --tb=short
  tests/test_resume_input_boundary.py tests/test_pdf.py tests/test_ingest.py
  tests/test_screening_ingest.py tests/test_api.py tests/test_candidates_api.py
  tests/test_screening_api.py tests/test_screening_batches_api.py
  tests/test_screening_service.py tests/test_screening_retry.py
  tests/test_screening_tenancy.py tests/test_screening_durable_input.py
  tests/test_screening_refusal_retention.py tests/test_ingest_response_erasure.py
  tests/test_ingest_erasure_concurrency.py tests/test_report_response_erasure.py
  tests/test_verification_documents_parse.py tests/test_integration.py
  tests/test_model_output_boundaries.py`: **462 passed, 46 skipped, 2 warnings
  (72.46s)**. Skips are optional PostgreSQL cases; warnings are TestClient
  deprecation and SQLite expression-index reflection. Sanitized offline runner
  clears inherited DEE settings; no PostgreSQL URL. Log:
  `.pytest_cache/r1-s2-q-t2a-focused-reviewed.txt`.
- `.resume/Scripts/python.exe -u scripts/smoke_r2_s1_t2a.py`: **74/74 passed**,
  actual startup/migration to 0029 on scratch SQLite, 44 invalid-input checks
  across four routes with unchanged eight-table counts, 20 readable/exact-boundary
  flows, org ownership, completed batch processing and actual restart/readback.
  NullLLM and localhost-disabled external providers; no live-provider evidence.
  Synthetic artifacts: `%TEMP%/r2-s1-t2a-ej_sci9c/server.log`.
- Updated existing HTTP checks to refuse whitespace at registration and accept
  sparse input: `.resume/Scripts/python.exe -u scripts/smoke_s84b.py`
  **17/17 passed** and `.resume/Scripts/python.exe -u
  scripts/check_ui_screening_contract.py` **32/32 passed**, via sanitized
  `.pytest_cache/run_r2_s1_t2a_scripts.py`. Capture email is synthetic and local.
  The second script drives cookie/CSRF HTTP contracts; it is not browser evidence.
- `node scripts/check_ui_bindings.js`: **425 bindings / 10 states**, passed.
  AST checks for 14 task code/test/script files and `git diff --check` passed.
- Final `.resume/Scripts/python.exe -m pytest -q --tb=short`: **3125 passed,
  476 skipped, 113 warnings (641.79s)**, exit 0. Actual sanitized launcher:
  `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_q.py t2a-full -m pytest
  -q --tb=short`; root cwd, `PYTHONPATH=src`, inherited DEE settings cleared,
  no keys/no PostgreSQL URL, null email, memory vectors and localhost GitHub.
  Focused and primary HTTP checks used the same runner with their listed args.
  Log: `.pytest_cache/r1-s2-q-t2a-full.txt`. Skips cover optional environments;
  no new UI/SQL gate applies. Warnings: 1 TestClient deprecation, 111 SQLite
  expression-index reflection and 1 Alembic index-comparison warning.

Separate self-review, 2026-10-10: HEAD `54804988` plus six task production files,
three existing tests, new PDF helper/boundary tests/smoke and two adapted existing
HTTP scripts. Reviewed AC1-AC4, all resume callers, caps before work/writes,
safe errors, legacy batches/retries, text precedence, sparse/advisory behavior,
tenant and erasure guards, PDF/verification compatibility and scope. Reviewed
file hashes are recorded locally in `.pytest_cache/r2-s1-t2a-reviewed.json`.
Findings resolved:
- Medium, `ScreeningService.register`: direct callers bypassed route validation
  and saved whitespace/oversized items. Separate intended reproduction:
  `.resume/Scripts/python.exe -m pytest -q --tb=short
  tests/test_resume_input_boundary.py -k direct_batch_registration`:
  **2 failed, 42 deselected (2.26s)**. Common text validation now precedes batch
  creation; both cases pass. Existing low-level legacy-row fixture still proves
  failed-item isolation, preserving compatibility without allowing new invalid input.
- Low, `core/resume.read_resume_input`: PDF whitespace was trimmed before its
  decoded cap. Reordered shared validation to check size first, translating only
  the empty-text refusal. PDF padding/whitespace-over-cap regressions pass without
  writes; final focused/HTTP were rerun after this change.
No unresolved T2A acceptance findings. No independent review claimed. This
does not prove parser resource containment or scoring accuracy; T2B stays pending.

### <a id="r2-s1-t2a--handoff"></a>Handoff

AC1-AC4 and required T2A gates passed on the reviewed final code. Working DB
SHA256 remains `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`;
150 unrelated baseline file hashes preserved. Prior API/ingest work was retained
with targeted patches. Final reviewed-code hashes, local links, status pointers
and diff checks passed; task-owned servers stopped. No working migration,
dependency change, deployment, external delivery or data cleanup.
Next: **R2-S1-T2B**, its brief plus `core/pdf.py`, installed parser and verification
callers. Parser page/work/expansion limits are not implemented by T2A; parent
T2/R2-S1/PI-R2/F07 remain incomplete. T2B/T3 not started; stop after T2A.

## <a id="r2-s1-t2b"></a>R2-S1-T2B - Bound PDF parser resources

Status: done (Unicode correction validated 2026-10-13; original closure 2026-10-11). Parent: [R2-S1-T2](#r2-s1-t2).
Prerequisite: [R2-S1-T2A](#r2-s1-t2a).

### <a id="r2-s1-t2b--scope-and-acceptance"></a>Scope and acceptance

Bound PDF page/work consumption using explicit positive settings, including
decompression expansion and parser stalls. Audit page-tree traversal, content
arrays, recursive form resources and allocation before text extraction. A
post-extraction text cap is not parser containment. Reuse the PDF boundary used
by resume intake and preserve verification metadata/page-count behavior.

| ID | Observable contract | Planned evidence |
|---|---|---|
| AC1 | Page and parser work/expansion limits refuse safely before costly downstream work | Actual adversarial PDF fixtures, exact/over boundaries |
| AC2 | Expanding streams, recursive resources and parser stalls cannot perform unbounded request work; cleanup is reliable | Real isolated parser/timeout/cleanup checks; describe memory guarantees and limits |
| AC3 | Valid PDF extraction and verification metadata remain compatible; invalid resumes still persist nothing | Shared helper, API and verification regressions |
| AC4 | Limits work through actual app composition | Migrated scratch HTTP journey, full pytest, recorded review |

Choose the smallest defensible containment after inspecting installed parser
and deployment/runtime support. No live candidate data or working DB. Required
gates inherit WORKFLOW.md; assess packaging/subprocess and affected browser/SQL
gates from the chosen implementation.

Design (2026-10-11): one disposable worker per parse, with an OS memory limit
before importing pypdf/reading PDF bytes, a parent deadline and kill/wait/close
on every exit. Apply positive page, graph/operation work, depth, decoded-stream
and output limits before extraction. Bound Flate allocation and audit actual
page leaves, repeated content arrays and invoked form graphs rather than trust
declared counts or unique-stream size. Use the same worker for verification,
passing its page cap before parsing; retain normalized metadata and blank PDFs.
No dependency, SQL, schema, UI, scoring or live-data change is planned. Windows
Job process committed-memory and Linux address-space limits are distinct;
neither promises an aggregate service RSS/concurrency bound. Unsupported OS or
failed limit installation refuses, with no in-process parser fallback.

### <a id="r2-s1-t2b--implementation-and-bounds"></a>Implementation and bounds

- Shared helper passes only bounded bytes/options to an adjacent installed worker
  using `sys.executable -I`; its environment omits app/provider credentials.
  Bounded concurrent pipes keep PDF/text off disk; timeout/interruption/startup
  failure kills/reaps the child, joins IO and closes both handles. Diagnostics
  carry fixed codes, never parser output. Resume errors retain safe 422 details;
  verification retains its existing 400 parse refusal and blank-document policy.
- Defaults: 40 pages, 100,000 work units, depth 64, 16,000,000 decoded bytes,
  1,000,000 output characters, 10 seconds and 256 MiB worker memory; all positive,
  deadline finite. Verification passes `min(doc_max_pages, pdf_max_pages)` before
  extraction. Work counts graph/container visits, filter stages and expanded
  content/form operations; it is not an instruction-count or CPU guarantee.
- Actual page leaves, page/parent cycles, content arrays and invoked form graphs
  are checked before extraction. Flate emits at most remaining budget + one
  detection byte; chained stages and repeated array concatenations count toward
  expansion. Other decoder, predictor, object/font and extraction allocations
  remain inside the OS cap. JBIG2/external-tool decoding is refused; images are
  not decoded for text. Strict zlib rejects damaged/truncated streams instead
  of attempting repair. Valid common-filter PDFs retain text and normalized
  producer/creator/date metadata; unusually complex/unsupported files can refuse.
- The Windows Job limits per-process committed virtual memory, **not RSS**;
  Linux sets hard `RLIMIT_AS` address space (executed by the closure gate below). See
  [Microsoft's memory-limit contract](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information)
  and [Python's RLIMIT_AS contract](https://docs.python.org/3/library/resource.html#resource.RLIMIT_AS).
  Limits install before pypdf import/PDF input reads in the child. Interpreter
  startup, bounded parent input/JSON buffers, parent thread stacks, concurrent
  requests and aggregate service memory are outside this cap. Parent deadline
  includes worker IO/startup after process creation; OS launch/kill/join overhead
  is additional. Graceful request failures are covered, not abrupt app/host death.

### <a id="r2-s1-t2b--evidence-and-review-2026-10-11"></a>Evidence and review (2026-10-11)

Sanitized offline runner for commands below:
`.resume/Scripts/python.exe .pytest_cache/run_r1_s2_q.py <log-name> <args>`;
root cwd, `PYTHONPATH=src`, inherited DEE settings cleared, no keys/PG URL,
null email, memory vectors and localhost-disabled GitHub. No live provider.
Local runtime: Windows CPython 3.13.11, pinned pypdf 6.13.3.

- Before-fix `t2b-repro -m pytest -q --tb=short
  tests/test_pdf_resource_limits.py -k real_adversarial`: **3 failed, 1 deselected
  (1.55s)**, all `DID NOT RAISE` for actual lying page counts, compressed expansion
  and repeated content arrays. Missing fields were installed directly only for
  this reproduction, avoiding config/fixture errors as defect evidence.
- Resource regressions include a real 256 MiB compressed allocation bomb built
  incrementally, xref-stream expansion during reader construction, raw/chained/
  cumulative/repeated streams, form cycles/exponential invocation, nesting,
  exact expansion/output boundaries and positive/finite settings. Actual OS
  allocation refusal, controlled entered parser stall, unexpected stdout,
  kill/wait/closed handles, failed containment installation and healthy next
  parsing are exercised. Four resume doors prove no model work/intake writes;
  verification proves safe refusals and metadata/page/digest compatibility.
- Final focused `t2b-reviewed-final -m pytest -q --tb=short`:
  **332 passed, 1 warning (96.68s)**, no skips. Files: `test_pdf_resource_limits`,
  `test_pdf`, `test_resume_input_boundary`, `test_verification_documents_parse`,
  `test_verification_documents_letter`, `test_verification_documents_payslip`,
  `test_verification_documents_corroboration`, `test_verification_service`,
  `test_verification_api`, `test_ingest`, `test_screening_ingest`, `test_config`,
  `test_config_verification`, `test_image_contents`, `test_requirements_pinned`,
  `test_smoke_harness` (each `tests/<name>.py`, in that order). Warning is the
  existing TestClient deprecation. Log: `.pytest_cache/r1-s2-q-t2b-reviewed-final.txt`.
- Final `t2b-full -m pytest -q --tb=short`: **3194 passed, 476 skipped,
  113 warnings (891.31s)**, exit 0 on the frozen reviewed code. Skips are optional
  environments including PostgreSQL; warnings are 1 TestClient deprecation,
  111 SQLite expression-index reflections and 1 Alembic index-comparison warning.
  Log: `.pytest_cache/r1-s2-q-t2b-full.txt`.
- Migrated scratch `t2b-http-reviewed -u scripts/smoke_r2_s1_t2b.py`:
  **99/99 passed**. Four intake doors, 60 no-write refusals, exact text/PDF caps,
  advisory sparse reports, org isolation, valid batch processing, four document
  resource refusals without verification/challenge/audit rows, candidate actor
  isolation, actual restart/readback and actual HTTP deadline/health recovery.
  Actual startup migrated disposable SQLite to 0029; three server lifecycles
  stopped. Synthetic scratch: `%TEMP%/r2-s1-t2b-3lbjocmz`.
- Actual wheel built and unpacked using `.resume/Scripts/python.exe
  .pytest_cache/r2_t2b_build.py`; alternate-cwd packaged worker extracted valid
  text and refused expansion. Hatchling 1.27.0 and build-only dependencies live
  in ignored `.pytest_cache/r2-t2b-build-backend`; project dependencies unchanged.
- Advertised minimum pypdf 4.2.0 was downloaded into an ignored scratch target;
  `.resume/Scripts/python.exe .pytest_cache/r2_t2b_floor.py` executed the current
  worker with only its parser import path redirected: **8/8 passed** for valid
  text/xref, pages, stream/xref expansion, repeated arrays and recursive/expanded
  forms. This is a bounded parser-floor probe, not the whole suite on 4.2.0.
- `node scripts/check_ui_bindings.js`: **425 bindings / 10 states**, passed.
  Python AST, CI YAML, `git diff --check`, reviewed-code hash and preservation
  checks passed. No visible UI, SQL, schema or migration change; no browser or
  PostgreSQL gate applies. Source/binding checks are not browser execution.

Separate self-review: HEAD `54804988` plus 13 task-owned code/config/CI files
(hash manifest `.pytest_cache/r2-t2b-reviewed.json`). Reviewed AC1-AC4, all helper
callers, allocation before/after preflight, decoder recovery and form recursion,
page/metadata compatibility, safe refusals before model/writes, child/pipes on
failure and interruption, credential isolation, packaging and prior edits.
Findings resolved:
- Medium, `pdf_worker` decoder/form recovery: ordinary limit exceptions can be
  swallowed by pypdf and become partial text. Worker-only containment exceptions
  bypass its `Exception` recovery; nested-form MemoryError also escapes safely.
  Recursive-form and xref-construction expansion regressions exercise the refusal.
- Medium, `verification/documents.parse_document`: direct calls decoded before
  their encoded-size cap. Explicit settings/cap now precede decoding; service
  passes its settings/page cap. Oversized-invalid-base64 regression checks order.
- Medium, `core/pdf._parse`: pipe thread submission failure could leave a child
  outside cleanup. Submissions now sit inside kill/wait/join/close protection.
  Entered stall and oversized stdout checks prove bounded read and cleanup.
No unresolved Windows acceptance finding. Initial operation fixture underfilled
its budget and HTTP harness referenced a nonexistent audit table/wrong status;
corrected fixture/harness errors are not defect reproductions. No independent
review or scoring/quality claim. That Windows review left Linux validation to
the closure gate below.

### <a id="r2-s1-t2b--linux-validation-and-closure-2026-10-11"></a>Linux validation and closure (2026-10-11)

Resumed the existing task-owned QEMU/WHPX VM; Windows WSL/Docker remain absent.
Alpine host kernel `6.12.110-0-virt`, Docker, Debian 13 production-image runtime,
CPython **3.12.15**, pypdf **6.13.3**, non-root `appuser`. Allowlisted source
excludes working data, .env, credentials and uploads. Actual manifest checks
match all **653 snapshot files**, **236 shipped files** and **13 reviewed task
hashes** against current source. Image ID:
`sha256:8fe31c4786277410926106f782fcfe73f1f74a4543bc60030b03303972dc127f`.

Commands use `.resume/Scripts/python.exe .pytest_cache/r2_t2b_ssh.py run
.pytest_cache/r2_t2b_guest_<gate>.sh <log-name>`; scripts run the real Docker image
with fake/null providers, isolated mounted source and scratch stores. Logs live
under the scratch directory recorded by `.pytest_cache/r2-t2b-linux-runtime.json`.

- Recovered, hash-verified `<focused>`: **332 passed (154.99s)**; `<full>` final
  log `full-final.log`: **3194 passed, 476 skipped, 112 warnings (764.13s)**.
  This closure verified those completed runs; it did not rerun full pytest.
  Skips are optional environments including PostgreSQL; warnings are SQLite
  expression-index reflections and Alembic comparison. The first incomplete
  snapshot omitted DEPLOY.md; after including it, **6 document tests passed**
  and the complete full run above passed. Incomplete runs are not acceptance.
- Current `<resumed_checks>`/`resumed-resources`: cached **docker build passed**;
  real hard `RLIMIT_AS=(64 MiB, 64 MiB)` verified before parsing, actual **256 MiB
  allocation refused**; resource pytest **68 passed (52.61s)**, exit 0. Includes
  entered parser stalls, bounded stdout, killed/reaped children, closed handles,
  failed limit installation and healthy next parse. Initial build wrapper's
  extra base-tag inspection failed; the current build/verification gates pass.
- Current `<http>`/`resumed-http`: **99/99 passed**, exit 0; migrated scratch
  HTTP refusal/no-write, readable inputs, ownership, verification metadata,
  restart/readback and actual deadline/health recovery.
- Current `<image_gate>`/`resumed-image-gate`: actual CI valid-blank-PDF metadata
  and over-page refusal passed, as did shipped UI presence. `<verify>` checks
  current/shipped hashes and actual image runtime. Local execution proves these
  gates; no GitHub Actions execution, browser, live-provider or quality claim.

Separate closure self-review covered AC1-AC4, Linux limit ordering/hard ceiling,
worker cleanup, non-root image composition, artifact/source correspondence and
refusals before persistence. No code change or unresolved acceptance blocker;
no independent review claimed. Documentation links/statuses and diff checks
passed; **826 prior workspace files** and working DB bytes were preserved.
VM shut down after validation; its scratch disk/logs retained. No working
migration, dependency replacement, deployment, external delivery or data cleanup.
**T2B and parent T2 complete. Next: R2-S1-T3; not started in this session.**

### <a id="r2-s1-t2b--unicode-output-correction-2026-10-13"></a>Unicode output correction (2026-10-13)

Reopened AC3 after self-review found a medium correctness defect at
`core/pdf.py:46`: JSON emits two six-byte surrogate escapes for one non-BMP
character. The six-byte estimate refused valid Unicode metadata at the character
limit. Both helpers now allow `12 * pdf_max_output_chars + 1024` protocol bytes,
with one detection byte; the worker's character quota, memory/work limits and
cleanup remain. Only the helper and resource test file changed in this correction.

Windows commands use the sanitized runner above with the following log names:

- `t2b-unicode-repro -m pytest -q --tb=short tests/test_pdf_resource_limits.py
  -k unicode_metadata`: **2 failed, 68 deselected, 1 warning (14.87s)**, both
  `pdf_output_limit` on actual readable PDFs at the exact character limit.
- `t2b-unicode-focused -m pytest -q --tb=short` with the same 16 focused files
  listed above: **343 passed, 1 warning (139.47s)**. Both helpers preserve text
  and normalized Unicode metadata at the exact limit and refuse one character over.
- `t2b-unicode-full -m pytest -q --tb=short`: **3379 passed, 479 skipped,
  113 warnings (1105.40s)**, exit 0. Skips are conditional environments including
  PG; warnings are existing Starlette/httpx and SQLite reflection/Alembic warnings.
- `t2b-unicode-http -u .pytest_cache/smoke_t2b_unicode.py`: **10/10 passed**.
  Migrated scratch HTTP accepts the Unicode boundary through all four intake
  routes, reads saved reports/processes the batch, and refuses one character
  over without eight-table writes. Scratch: `%TEMP%/t2b-unicode-http-uraa3l35`.

Current Linux commands use the existing SSH runner and `<gate>.sh` files above:
`<resumed_checks>/unicode-linux-resources` rebuilt the non-root image, proved hard
64 MiB RLIMIT_AS and actual 256 MiB allocation refusal, and passed resource pytest
**70/70 (110.79s)**. `<http>/unicode-linux-http` passed **99/99**; `<image_gate>`
passed the actual CI PDF gate. `.pytest_cache/r2_t2b_unicode_image.sh` also proved
packaged Unicode exact/over boundaries in both helpers. `<verify>/unicode-verify`
matched **673 source files, 237 shipped files and 13 reviewed composition hashes**.
Runtime remains Linux 6.12.110, Python 3.12.15 and pypdf 6.13.3. Image ID:
`sha256:a376a69f1308c12eec777f29b8e577b18e64a6fc518ca0e7dec7df222f1690f4`.
The historical Linux full run above is not a full run of this corrected code.

Separate same-agent review: HEAD `54804988` plus the two-file correction,
manifest `.pytest_cache/r2-t2b-unicode-reviewed.json`; checked UTF encoding,
exact/over quota enforcement, bounded unexpected stdout, cleanup and callers.
No unresolved acceptance blocker or independent review claim. AST, diff,
**474 bindings / 15 states**, links/statuses and preservation passed.
**854 prior files and working DB bytes preserved**; no UI/schema/scoring change,
so no browser/PG gate applies. VM shut down; synthetic artifacts retained.
Existing demo remains healthy and running, with its controlled restart pending.
No live provider, dependency replacement, working migration, deployment or cleanup.
T2B/T2 maintenance complete. The newer handoff remains **R3-S1-Q**, not started.

## <a id="r2-s1-t3"></a>R2-S1-T3 - Correct GitHub evidence polarity

Status: done (2026-10-11; GitHub repository evidence polarity). PI/sprint: R2/R2-S1.
Audit: F07; F02 residual.
Prerequisite: [R2-S1-T2](#r2-s1-t2), done.

### <a id="r2-s1-t3--scope-and-acceptance"></a>Scope and acceptance

GitHub fetch errors currently become ordinary provenance strings: plausibility
labels most as supporting and a 404 as contradictory. Separate repository
metadata from fetch diagnostics at the producer; neither proves a candidate's
claim or ownership. Preserve first-party anchors, evaluation-local caching and
domain independence. Keep report fields/enums, persisted historical reports,
SQL, UI handlers, scoring formulas and live-provider configuration unchanged.

| ID | Observable contract | Evidence |
|---|---|---|
| AC1 | 403/404/429/5xx, timeout/transport and malformed responses are unavailable context, never support/contradiction | MockTransport through actual client/nodes and final reports |
| AC2 | Successful repo/language/commit metadata remains visible without verifying claims; outages do not enter rule/model grounding or inflate scores/status | Valid/partial metadata and baseline comparisons; unverified generic claims |
| AC3 | Only linked claims receive their own observations/diagnostics; repeat links cache within one evaluation, with no cross-subject reuse | Existing/extended F02 isolation regressions |
| AC4 | Real app composition persists the corrected advisory report and preserves ownership/restart behavior | Migrated scratch HTTP with fake GitHub/model providers |

Design: a small repository-result DTO with observation/warning lists. Existing
private provenance strings hold metadata; a separate private warning map holds
diagnostics. Report them as neutral, zero-weight context; exclude repo metadata
and diagnostics from rule/model claim corroboration and zero-weight context
from evidence-presence classification. No new public schema/enum or migration.
GitHub [documents private-resource 404s and 403/429 rate limits](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api).

Required: intended failing reproduction, meaningful focused regressions, full
pytest, actual migrated HTTP/restart, bindings/contract checks, diff self-review
and preservation. No changed UI handler/schema or SQL/migration gate; browser
execution and live-provider/assessment-quality validation are not implied.

### <a id="r2-s1-t3--evidence-and-review"></a>Evidence and review

Implementation: the GitHub repository client separates observations/warnings
and returns fixed diagnostics for unavailable/invalid responses. Partial
metadata remains displayable; requests stop after a failed subfetch. Empty
public commit samples do not imply absence of work. Claim-linked maps retain
evaluation-local caching and copy lists per claim. Rules/model assessment
exclude metadata/diagnostics; final evidence is neutral with weight zero and
separate metadata/unavailable refs. Zero-weight context alone leaves a generic
claim unverified. Existing report serialization, advisory review, model bounds,
user-profile GitHub intake, SQL/UI handlers and working data remain.

All commands use `.resume/Scripts/python.exe`. Ignored runner
`.pytest_cache/run_r1_s2_q.py NAME ARGS` pins offline providers/config and captures
`.pytest_cache/r1-s2-q-NAME.txt`; tests use isolated stores. Results so far:

| Check | Actual evidence |
|---|---|
| Intended reproduction | `r2-t3-repro -m pytest -q --tb=short tests/test_plausibility.py -k github_metadata`: 7 intended polarity failures, 2 deselected; no fixture/import errors |
| Reviewed focused | `r2-t3-final-focused -m pytest -q --tb=short tests/test_github_repo_evidence.py tests/test_provenance.py tests/test_plausibility.py tests/test_scoring.py tests/test_github_user_signal.py tests/test_model_output_boundaries.py tests/test_api.py tests/test_screening_api.py tests/test_screening_batches_api.py tests/test_openapi_contract.py`: 283 passed, 1 Starlette/httpx deprecation warning, 27.58s |
| Reviewed actual HTTP | `r2-t3-final-http scripts/smoke_r2_s1_t3.py`: 151/151; actual startup/migrated scratch SQLite 0029, both domains, all failure modes, baseline comparisons, unverified generic claims, per-claim/actor isolation, persisted readback and actual restart |
| Full regression | `r2-t3-full`: 1 failed, 3235 passed, 476 skipped, 113 warnings, 696.08s; outdated private test caller corrected below. Reviewed `r2-t3-full-final` (defaults to `-m pytest -q --tb=short`): 3236 passed, 476 skipped, 113 warnings, 718.48s; exit 0 |
| Review correction | `r2-t3-review-fix -m pytest -q --tb=short tests/test_silent_swallows.py tests/test_plausibility.py`: 16 passed, 0.90s |
| Reviewed browser | `r2-t3-browser-final scripts/check_ui_github_browser.py`: 22/22; actual Chrome/CDP signup, TXT/PDF batch processing, rendered GitHub 404 context, report reasoning, saved judgments, deletion and clean console. Fake GitHub/model; CDN internet used |
| UI API contract | `r2-t3-contract scripts/check_ui_screening_contract.py`: 32/32; actual scratch HTTP, organization cookie/CSRF, queue/report/outcome shapes and deletion |
| Bindings / whitespace | `node scripts/check_ui_bindings.js`: 425 bindings across 10 states; `git diff --check`: exit 0 |

Same-agent self-review after implementation: HEAD `5480498` plus task changes
to five app files, four existing/new test files and the fake fixture, HTTP and
browser runners. Reviewed AC1-4, all repository-result consumers, rule/model
fusion and classification, partial/malformed fetches, logging, persisted schema
and isolation. Low-severity test review finding: the first full run exposed a
stale direct private-helper caller
in `test_silent_swallows.py:38`: removing grounding left one extra positional
argument, so the logging regression never entered the helper. Updated the
caller, reviewed alias imports and reran logging/plausibility and full pytest.
No unresolved implementation findings. Separate provenance
does not establish ownership; provider diagnostics cannot become corroboration.
Existing strict model validation is preserved. No SQL/concurrency/migration,
frontend handler or public-schema change, so no PostgreSQL gate applies.
Reviewed hashes live in `.pytest_cache/r2-s1-t3-reviewed.json`.
App scope: `src/app/services/github.py`, `src/app/graph/state.py` and
`src/app/graph/nodes/{provenance,plausibility,scoring}.py`. Focused command above
owns the node/API test list; `test_silent_swallows.py` owns the final caller fix.

Validation corrections: an initial HTTP run was 149/151 because its screening
fixture put the URL on a standalone line; current heuristic screening discovers
anchors on claim lines. The corrected fixture passes. An initial browser launch
had a missing child-module path; its task-owned processes were stopped, the
runner path/log capture was fixed. The first completed browser run was 20/21:
its fixture supplied a GenAI-only claim to the UI's default data_eng domain;
the corrected domain-readable fixture reaches the actual fake repository client
and passes 22/22. Model test replies
now use actual JSON strings and assert the LLM branch was reached. These are
test corrections, not additional product changes.

Final preservation: `.resume/Scripts/python.exe .pytest_cache/verify_r2_s1_t3.py`
checks the 834-file starting snapshot, all 12 reviewed code/test/journey hashes,
821 task-unrelated files and unchanged working DB bytes. No unexpected additions
or unrelated changes. `.pytest_cache/r2-s1-t3-preservation.json` owns hash results.
`.resume/Scripts/python.exe .pytest_cache/check_r2_s1_t3_docs.py`: 19 task-relevant
local Markdown targets, status chain and `git diff --check` pass. Full warnings are
Starlette/httpx deprecation and SQLite expression-index reflection/autogenerate;
skipped environment/optional cases do not prove PostgreSQL/live-provider gates.
Browser launcher/fixture corrections were re-reviewed and rerun; application
hashes did not change during final API/browser/full checks.

No independent review, live GitHub/model compatibility, empirical scoring
quality, CI or deployment claim. Historical saved reports are not rewritten;
neutral context is guaranteed for newly generated reports. Standalone profile
links in heuristic screening remain outside this task's claim-anchor scope.

### <a id="r2-s1-t3--handoff"></a>Handoff

T3 complete; next is the separate R2-S1-Q integration gate, not started here. Do not close
R2-S1/PI-R2/F07 before Q and remaining mapped tasks pass.

## <a id="r2-s2-q"></a>R2-S2-Q — Combined style/factual-context acceptance

Status: done (2026-10-12). PI/sprint: R2/S2. Audit: F08.
Prerequisites: [T1](#r2-s2-t1) and [T2](#r2-s2-t2), done.

### <a id="r2-s2-q--contract"></a>Contract

Close the combined acceptance gate: plain and polished truthful resumes with
fixed factual inputs retain identical v2 risk, depth and verdicts; style remains
descriptive. Timeline/content findings must remain specific and advisory, with
uncertainty and candidate clarification. Missing/unsupported assessments must
refuse an interpretable numeric UI index; historical v1 must retain its stored
score/wording under an explicit version notice. Features, exports and current
measurements must preserve version separation through persistence/restart.

Review the combined T1/T2 diff and actual callers; fix only acceptance-blocking
regressions. Reuse their migrated scratch HTTP/Chrome journeys, fake providers,
fixtures and current consent tests. No planned application change, SQL/migration,
working-data cleanup, deployment, live-provider or assessment-accuracy claim.
No new PostgreSQL/Linux gate: this sprint changes pure fusion, versions and
presentation, not SQL/concurrency/migrations or parser containment.

### <a id="r2-s2-q--acceptance--validation"></a>Acceptance / validation

| ID | Observable criterion | Required evidence | Result |
|---|---|---|---|
| AC1 | Style/AI weight cannot alter factual risk, coverage, gates, depth or verdicts in either domain | focused risk/pipeline tests; paired actual HTTP | Passed |
| AC2 | Real timeline/content findings remain visible with uncertainty and clarification; style has no authorship/dishonesty probability presentation | report/API tests; real Chrome paired/overlap/duplicate reports | Passed |
| AC3 | Missing, absent and unsupported reports render neutral refusal; low remains numeric; historical v1 retains its score/wording | actual Chrome styling/accessibility, error/reload; HTTP/restart | Passed |
| AC4 | v1/v2 vectors, CSV/search and current quality samples remain distinct without rewriting reports | features/quality/serving tests; migrated HTTP/restart | Passed |
| AC5 | Org/candidate/operator boundaries, current consent, CSRF, outcomes and erasure/error recovery remain intact | isolation/consent tests; HTTP, browser and API contracts | Passed |

Required: fresh focused/full project pytest, actual migrated scratch app HTTP
with restart and fake providers, real Chrome report/batch/plane journeys,
UI API contracts, bindings/JS syntax, separate self-review and preservation/docs.
Child records own their original failing reproducers; add a new reproducer only
if this review finds an application regression.

### <a id="r2-s2-q--separate-self-review"></a>Separate self-review

Reviewed HEAD `5480498` plus the combined T1/T2 uncommitted delta, their relevant
callers, regressions, synthetic fixtures and journeys: 48 file hashes in
`.pytest_cache/r2-s2-q-reviewed.json`. Session-start snapshots and preservation
manifest are `.pytest_cache/r2-s2-q-before/`. Specification pass traced AC1-5;
correctness pass followed pure fusion and direct callers, scorer-version defaults,
report persistence/redaction/ownership, default and explicit feature views,
current consent masking, CSV/measurement separation, nullable/unsupported UI
states, raw historical summaries, style-source filtering, outcome guards and
scratch-process isolation/cleanup. Existing child diffs retain exact change
evidence; no application finding or change in Q.

No acceptance-blocking finding after the source/caller review and fresh checks.
Final pass confirmed evidence, source hashes and archival/status consistency.
Same-agent self-review only. Prototype operator/Instant check flows remain
R3; Chrome requires CDN internet and fake providers do not prove quality.

### <a id="r2-s2-q--validation-evidence"></a>Validation evidence

All commands use `.resume/Scripts/python.exe` on Windows/CPython 3.13.11.
The ignored runner clears inherited DEE settings and disables external providers.
Child tests/journeys are reused instead of duplicating the harnesses.

| Layer | Actual command/result | Local artifact |
|---|---|---|
| Focused | `.pytest_cache/run_r1_s2_q.py r2-s2-q-focused -m pytest -q --tb=short` + files below: **580 passed, 101 skipped, 2 warnings, 148.23s**, exit 0 | `.pytest_cache/r1-s2-q-r2-s2-q-focused.txt` |
| Full | `.pytest_cache/run_r1_s2_q.py r2-s2-q-full` executes `-m pytest -q --tb=short`: **3363 passed, 476 skipped, 113 warnings, 825.47s**, exit 0 | `.pytest_cache/r1-s2-q-r2-s2-q-full.txt` |
| Migrated HTTP/restart | `.pytest_cache/run_r1_s2_q.py r2-s2-q-http scripts/smoke_r2_s2_t1.py`: **67/67**, exit 0, 26.90s; actual 0029 scratch app, paired risk/depth/verdicts in both domains, factual observations, tenant denials, v1/v2 features/CSV/search/quality and restart without historical rewrite | `.pytest_cache/r1-s2-q-r2-s2-q-http.txt` |
| Chrome reports/planes | `.pytest_cache/run_r1_s2_q.py r2-s2-q-browser .pytest_cache/r2_s2_t2_role_browser.py`: **29/29**, exit 0, 41.48s; runs permanent report journey, then candidate/operator OTP sessions, references, labels and reload; exact observations, low/refusal ring styles, legacy/unknown versions, erasure/404 recovery and clean console | `.pytest_cache/r1-s2-q-r2-s2-q-browser.txt` |
| Chrome batch/outcomes | `.pytest_cache/run_r1_s2_q.py r2-s2-q-style-browser scripts/check_ui_style_browser.py`: **21/21**, exit 0, 28.12s; real TXT/PDF intake, factual/style report presentation, append-only review history and deletion, clean console | `.pytest_cache/r1-s2-q-r2-s2-q-style-browser.txt` |
| UI HTTP contract | `.pytest_cache/run_r1_s2_q.py r2-s2-q-contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 23.53s; actual cookie/CSRF/ownership, input refusal, queue/report/outcome/retry/delete contracts | `.pytest_cache/r1-s2-q-r2-s2-q-contract.txt` |
| Static | `node scripts/check_ui_bindings.js`: **435 bindings / 14 states**; `node --check frontend/api.js`, `node --check frontend/support.js`, `node --check scripts/check_ui_bindings.js`, `git -c core.safecrlf=false diff --check`: passed | Bindings are separate from Chrome evidence |
| Preservation/docs | `.pytest_cache/verify_r2_s2_q.py --final`: **222 prior files preserved**, **48 reviewed hashes unchanged**, working DB unchanged; **251 local links**, closure status/next pointer, unrelated git status/HEAD and archived child content verified | `.pytest_cache/r2-s2-q-before/`; archived children differ only in T1's prerequisite link |

Focused files (all under `tests/`): `test_fabrication_risk.py`,
`test_fabrication_risk_schema.py`, `test_fabrication_risk_integration.py`,
`test_scoring_fabrication_risk.py`, `test_report_review_context.py`,
`test_report_fabrication_risk.py`, `test_report_ai.py`, `test_ai_integration.py`,
`test_report_cross_field.py`, `test_report_resume_farm.py`, `test_resume_farm_api.py`,
`test_features_fabrication.py`, `test_features_catalog.py`, `test_report_store.py`,
`test_signal_quality_signals.py`, `test_signal_quality_service.py`,
`test_talent_search_api.py`, `test_job_store_match.py`, `test_ai_signals_node.py`,
`test_cross_field_timeline.py`, `test_cross_field_coherence.py`,
`test_cross_field_assess.py`, `test_cross_field_node.py`,
`test_cross_field_integration.py`, `test_resume_farm_assess.py`,
`test_screening_schema.py`, `test_screening_api.py`, `test_model_output_boundaries.py`,
`test_feature_serving_consent.py`, `test_features_current_consent.py`, `test_portal_api.py`.
Focused warnings: Starlette/httpx deprecation and SQLite expression-index reflection.
Full warnings add SQLite expression-index comparison/reflection; no failures.
Environment-conditional skips do not prove PostgreSQL or optional formats.

### <a id="r2-s2-q--handoff"></a>Handoff

AC1-5, fresh required checks and separate self-review are complete. R2-S2, PI-R2
and bounded F08 are done; R2-S1/bounded F07 retain their prior closure.
No application change or new reproducer needed in Q. Working DB/prior code intact;
task-owned HTTP/Chrome children stopped, synthetic artifacts retained. The local
demo remains running (HTTP health 200). No independent review, live-provider or measured-quality
claim; operator/Instant check tests prove presentation, not future R3 actions.
Existing v1 vectors still require operator materialization for default v2
search/matching. No working migration, historical rewrite, deployment, message
or user-data cleanup occurred. Detailed T1/T2 records archived with evidence intact.

Exact next task: R3-S1-T1 — Wire the evaluate screen. Read its PI-R3 section,
`frontend/Veritas.dc.html` evaluation handlers and API contracts, then write its
bounded brief. R3 work was not started; stop after this Q task.

## <a id="r2-s2-t1"></a>R2-S2-T1 — Remove style from fabrication fusion

Status: done (2026-10-12). PI/sprint: R2/S2. Audit: F08.
Prerequisite: [R2-S1-Q](#r2-s1-q), done.

### <a id="r2-s2-t1--contract"></a>Contract

Changing writing style currently changes the fused maximum, confidence and
corroboration even with `fr_weight_ai=0`. New assessments must use only timeline
and duplication components; style remains optional descriptive report context.
Keep factual component math/thresholds, insufficient-data refusal, deterministic
fallback, advisory review and tenant/consent boundaries. No UI work, data rewrite,
SQL/migration change or empirical accuracy claim; UI explanations belong to T2.

Version the risk assessment and risk features. Missing assessment version means
historical v1; new assessments explicitly emit v2. Feature extractors refuse
opposite/unknown semantics rather than relabel stored scores. Version the default
feature view so persisted v1 vectors are not silently served as current v2.
Retain `fr_weight_ai` as an ignored compatibility setting for existing configs.

### <a id="r2-s2-t1--acceptance--validation"></a>Acceptance / validation

| ID | Observable criterion | Evidence planned | Result |
|---|---|---|---|
| AC1 | Fixed factual inputs yield identical risk across absent/low/high style, confidences and AI weights, including zero | risk units; paired plain/polished pipeline and HTTP | Passed |
| AC2 | Style cannot supply missing factual coverage or flags; factual thresholds, overlaps and duplication still work | risk boundaries; existing detector tests; HTTP | Passed |
| AC3 | Depth/verdicts and separate style/timeline/duplication trails remain advisory | scoring/report/pipeline tests; HTTP/Chrome | Passed |
| AC4 | Historical stored scores/components/reasoning remain v1; v1/v2 features/exports stay distinct; current measurements omit v1/unknown samples | schema/store/features/CSV/quality; migrated HTTP/restart | Passed |

Required: intended failing reproducer, focused/full offline pytest, actual
migrated scratch app HTTP journey, actual Chrome rendering, UI API contracts,
bindings and diff review. T1 does not revise frontend code or wording; Chrome
checks the changed component data contract. PostgreSQL gate does not apply
because SQL/concurrency/migrations are unchanged.

### <a id="r2-s2-t1--implementation-and-evidence"></a>Implementation and evidence

`build_components` removes style entirely; direct `fuse_components` also excludes
legacy style components before mean/max/coverage. Factual maps, 70/30 blend and
band thresholds remain. Builder emits v2, including refusals; schema absence
defaults to historical v1. Risk feature versions accept only matching report
semantics; the default bundle is version 2. Observer records carry the scorer
version. Current measurement samples omit v1/unknown risk, preserving population.
No migrations, dependencies, working-store writes or historical recomputation.

Commands use `.resume/Scripts/python.exe` on Windows/CPython 3.13.11:

| Layer | Actual command/result | Local artifact |
|---|---|---|
| Reproducer | `-m pytest -q --tb=short tests/test_fabrication_risk.py -k 'style_cannot or direct_fusion'`: **61 failed, 30 passed, 22 deselected**, intended style dependence; after fix **91 passed** | `.pytest_cache/r2-s2-t1-reproduction.txt`, `r2-s2-t1-reproduction-fixed.txt` |
| Review reproducer | `-m pytest -q --tb=short tests/test_signal_quality_signals.py -k never_mix`: **2 failed, 1 passed**, v1/unknown scores admitted to current sample | `.pytest_cache/r2-s2-t1-review-reproduction.txt` |
| Reviewed focused | `-m pytest -q --tb=short` + files below: **281 passed, 2 warnings, 10.68s** | `.pytest_cache/r2-s2-t1-focused.txt` |
| Full | `-m pytest -q --tb=short`: **3353 passed, 476 skipped, 123 warnings, 749.20s**, exit 0 | `.pytest_cache/r2-s2-t1-full.txt` |
| HTTP/restart | `scripts/smoke_r2_s2_t1.py`: **67/67**, exit 0; actual 0029 scratch startup, both domains, real profile/fingerprint/timeline checks, fixed paired risk, org denials, v1 reads/CSV/quality isolation, v2 materialization/search and restart | `.pytest_cache/r2-s2-t1-http.txt`; temp `r2-s2-t1-euqbhw4u` |
| Chrome | `scripts/check_ui_style_browser.py`: **21/21**, exit 0; actual Chrome/CDP signup, TXT/PDF batch, high-style report with factual cards, reasoning, judgments/history, batch deletion and clean console | `.pytest_cache/r2-s2-t1-browser.txt`; temp `r2-s2-t1-browser-lbd1etjn` holds rendered text/server log |
| UI API contract | `.pytest_cache/run_r1_s2_q.py r2-s2-t1-contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 9.79s; runner strips inherited provider settings | `.pytest_cache/r1-s2-q-r2-s2-t1-contract.txt` |
| Static | `node scripts/check_ui_bindings.js`: **425 bindings / 10 states**; `node --check frontend/api.js`, `node --check frontend/support.js`, `git -c core.safecrlf=false diff --check`: passed | Git emitted existing LF/CRLF notices only |
| Preservation/docs | `.pytest_cache/verify_r2_s2_t1.py`: **184 untouched prior files**, **27 reviewed hashes**, unchanged working DB and **44 local links** after final handoff | Scoped edits in previously modified files also reviewed against snapshots/initial content; two test adjustments recover prior hashes in memory (accounting for changed-line endings) |

Focused file arguments: `tests/test_fabrication_risk.py`,
`test_fabrication_risk_schema.py`, `test_fabrication_risk_integration.py`,
`test_scoring_fabrication_risk.py`, `test_report_fabrication_risk.py`,
`test_report_ai.py`, `test_features_fabrication.py`, `test_features_catalog.py`,
`test_report_store.py`, `test_signal_quality_signals.py`,
`test_signal_quality_service.py`, `test_talent_search_api.py`,
`test_job_store_match.py`, `test_ai_signals_node.py`,
`test_cross_field_timeline.py`, `test_cross_field_coherence.py`,
`test_cross_field_assess.py`, `test_cross_field_node.py`,
`test_cross_field_integration.py`, `test_resume_farm_assess.py` (all in `tests/`).
Focused warnings: Starlette/httpx deprecation and SQLite expression-index reflection.
Full warnings add Chroma's legacy local `HashingEmbedding` configuration
deprecation (10); remaining warnings are Starlette/httpx and SQLite
expression-index reflection/comparison. Environment-conditional skips are not
PostgreSQL/Linux validation evidence.

### <a id="r2-s2-t1--separate-self-review"></a>Separate self-review

Reviewed HEAD `5480498` plus this task's uncommitted backend/schema/features,
tests, paired synthetic fixtures and two journeys; 27 file hashes recorded in
`.pytest_cache/r2-s2-t1-reviewed.json`. The source delta against session-start
snapshots is `.pytest_cache/r2-s2-t1-review.diff`; existing changes are preserved.
Specification pass mapped AC1-4 to behavior/assertions. Correctness pass traced
all builders/readers, feature materialization/search/matching/export/quality,
report ownership, default-version selection and scratch process cleanup.

- **Medium, `signal_quality/signals.py` risk extractors:** mixing old style-inclusive
  and new scores under one sample misinterpreted historical semantics. Fixed by
  accepting only v2; failing version regression, service sample/population and
  actual HTTP checks now pass.
- Stale default-view test fixtures/readers were changed to use the current
  bundle version. An intermediate matching-test rerun failed on a missing
  import (8 failures), then the reviewed focused run passed. Journey development
  also corrected an adapter syntax typo and its required `as_of` argument;
  final actual HTTP passed. These were test/harness defects, not app failures.
- No remaining acceptance finding after review. Same-agent review only; no
  independent review, live-provider compatibility, empirical quality or Linux/
  PostgreSQL validation claim. Chrome uses CDN internet; provider regressions
  remain fake/offline. The browser checks the v2 component contract, not T2's
  pending wording or historical-version explanation.

### <a id="r2-s2-t1--handoff"></a>Handoff

AC1-4, required checks and separate self-review are complete. Default search/matching
uses bundle v2; existing v1 vectors need operator materialization into the current
bundle. Old reports yield missing v2 risk rather than automatic reevaluation.
Use version-aware extractors for these reports/exports; there is no DB migration
or user-data cleanup. Working DB hash still matches the handoff; task-owned
servers/Chrome stopped and synthetic scratch artifacts retained.
Existing local demo process remains running; no deployment, external delivery,
working migration or cleanup occurred.

Exact next task after acceptance: R2-S2-T2 — Explain findings in the actual UI.
Read its [PI section](PI-R2.md#r2-s2-t2--explain-findings-in-the-actual-ui),
`frontend/Veritas.dc.html` report bindings, `graph/nodes/report.py` and this v1/v2
contract. No T2 implementation started; R2-S2/F08 remain open until T2 and Q.

## <a id="r2-s2-t2"></a>R2-S2-T2 — Explain findings in the actual UI

Status: done (2026-10-12). PI/sprint: R2/S2. Audit: F08.
Prerequisite: [R2-S2-T1](#r2-s2-t1), done.

### <a id="r2-s2-t2--contract"></a>Contract

Opening a report currently presents authorship likelihood, opaque component
scores and no historical-version explanation. Present descriptive writing-style
observations separately from current timeline/duplication review context. Show
specific timeline findings and overlap matches with uncertainty and candidate
clarification prompts. Insufficient data must have a neutral, explicit refusal
state rather than a low-score dial. Historical v1 assessments must be visibly
identified as style-inclusive, preserving their stored scores and summaries.

Review relevant candidate/org/admin report, queue, matching, feature and quality
labels. Keep wire identifiers, ranking/scoring math, advisory human decisions,
ownership and consent unchanged. No migration, historical rewrite, working-data
change, deployment or empirical authorship/fraud accuracy claim.

### <a id="r2-s2-t2--acceptance--validation"></a>Acceptance / validation

| ID | Observable criterion | Required evidence | Result |
|---|---|---|---|
| AC1 | Plain/polished truthful reports expose style observations without authorship/dishonesty probabilities; current risk excludes style | Report/API regressions; actual Chrome paired reports | Passed |
| AC2 | Timeline overlaps and content matches expose specific findings, uncertainty and candidate clarification | API findings; actual Chrome timeline/duplication reports | Passed |
| AC3 | Missing assessments/insufficient coverage render explicit neutral refusal, visibly distinct from a low assessment | Actual Chrome missing-data and low reports, reload/error recovery | Passed |
| AC4 | Historical v1 and current v2 interpretation is explicit; relevant feature/ranking/quality labels are descriptive | API compatibility; actual Chrome legacy and candidate/org/admin views | Passed |

Required: intended failing behavioral reproduction, focused/full project pytest,
real migrated scratch HTTP and Chrome journeys with fake providers, UI API
contracts, binding/JS syntax checks and a separate recorded self-review. SQL,
concurrency and migrations are unchanged, so no new PostgreSQL gate applies.

### <a id="r2-s2-t2--evidence"></a>Evidence

New summaries/OpenAPI/feature metadata describe heuristics and clarification;
wire identifiers, numeric assessments and scorer math stay compatible. Current
reports show both factual checks, including unavailable checks excluded from
fusion, exact timeline observations and identity-free estimated content matches.
Style displays deterministic details separately; unverified model suggestions
are counted without replaying their authorship claims. Historical summaries are
retained under an explicit v1 notice; unknown versions refuse index display.
Insufficient reports/queue rows hide numeric risk and the report uses a neutral
ring. Matching/help copy describes advisory context. The Instant check prototype
no longer illustrates a scored factual risk when corpus coverage is absent;
its real evaluation flow remains the separately scheduled R3-S1-T1 work.

Reproducer: `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_q.py
r2-s2-t2-reproduction -m pytest -q --tb=short tests/test_report_review_context.py`:
**7 failed**, intended missing explanations, before changes. All commands use the project
Python on Windows/CPython 3.13.11; the runner strips inherited provider settings.

| Layer | Actual command/result | Local artifact |
|---|---|---|
| Focused | `.pytest_cache/run_r1_s2_q.py r2-s2-t2-focused -m pytest -q --tb=short` + files below: **413 passed, 2 warnings, 37.93s** | `.pytest_cache/r1-s2-q-r2-s2-t2-focused.txt` |
| Full | `.pytest_cache/run_r1_s2_q.py r2-s2-t2-full` runs `-m pytest -q --tb=short`: **3363 passed, 476 skipped, 113 warnings, 740.57s**; completed log recovered on continuation, reviewed application/test hashes unchanged; not rerun during closure | `.pytest_cache/r1-s2-q-r2-s2-t2-full.txt` |
| Closure focused | `.pytest_cache/run_r1_s2_q.py r2-s2-t2-closure-focused -m pytest -q --tb=short` + same files below: **413 passed, 2 warnings, 40.49s**, exit 0 | `.pytest_cache/r1-s2-q-r2-s2-t2-closure-focused.txt` |
| HTTP/restart | `.pytest_cache/run_r1_s2_q.py r2-s2-t2-http scripts/smoke_r2_s2_t1.py`: **67/67**, exit 0, 32.18s; actual migrated 0029 scratch composition, paired factual results, stored v1/current feature semantics, tenant denials and restart | `.pytest_cache/r1-s2-q-r2-s2-t2-http.txt` |
| Chrome reports | `.pytest_cache/run_r1_s2_q.py r2-s2-t2-browser scripts/check_ui_review_context_browser.py`: **22/22**, actual org session/queue clicks for plain/polished, overlap, duplication, missing/absent/v1/unknown reports, ring styling, untouched historical JSON, erasure/404 recovery, reload, roles and Instant check presentation | `.pytest_cache/r1-s2-q-r2-s2-t2-browser.txt`; synthetic temp path printed in log holds per-report rendered text and server log |
| Closure Chrome / planes | `.pytest_cache/run_r1_s2_q.py r2-s2-t2-role-browser .pytest_cache/r2_s2_t2_role_browser.py`: **29/29**, exit 0, 43.05s; reruns the 22 report checks, then real candidate/operator OTP sessions, own report references without internal scores, restricted reference API shape, operator labels, both reloads and clean console | `.pytest_cache/r1-s2-q-r2-s2-t2-role-browser.txt`; rendered role text retained beside its disposable mailbox |
| Chrome batch | `.pytest_cache/run_r1_s2_q.py r2-s2-t2-style-browser scripts/check_ui_style_browser.py`: **21/21**, exit 0, 23.77s; TXT/PDF batch, current report component/style contract, reviewer outcomes/history and deletion, clean console | `.pytest_cache/r1-s2-q-r2-s2-t2-style-browser.txt` |
| UI API contract | `.pytest_cache/run_r1_s2_q.py r2-s2-t2-contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 23.44s; cookie/CSRF/ownership and batch/report/outcome contracts | `.pytest_cache/r1-s2-q-r2-s2-t2-contract.txt` |
| Static | `node scripts/check_ui_bindings.js`: **435 bindings / 14 states**; `node --check frontend/api.js`, `node --check frontend/support.js`, `node --check scripts/check_ui_bindings.js`, `git -c core.safecrlf=false diff --check`: passed | Binding checks are not browser evidence |
| Preservation / docs | `.pytest_cache/verify_r2_s2_t2.py`: final closure **208 untouched prior files**, **17 reviewed source hashes**, unchanged working DB, **100 local links** and task/PI/next-pointer consistency passed; common feature overview updated deliberately. Initial schema documentation inverse recovers its mixed-newline byte hash | Source snapshots/hash manifest and task delta retained under `.pytest_cache`; `git diff --check` passed |

Focused files, all under `tests/`: `test_report_review_context.py`,
`test_report_ai.py`, `test_ai_integration.py`, `test_report_cross_field.py`,
`test_report_resume_farm.py`, `test_resume_farm_api.py`,
`test_report_fabrication_risk.py`, `test_screening_schema.py`,
`test_features_fabrication.py`, `test_features_catalog.py`,
`test_screening_api.py`, `test_report_store.py`, `test_fabrication_risk.py`,
`test_fabrication_risk_integration.py`, `test_model_output_boundaries.py`.
Focused warnings: Starlette/httpx deprecation and SQLite expression-index reflection.
Full warnings add SQLite expression-index comparison/reflection; the 476
environment-conditional skips are not PostgreSQL/Linux evidence.

### <a id="r2-s2-t2--separate-self-review"></a>Separate self-review

Reviewed HEAD `5480498` plus the T2 delta against session snapshots (17 source,
test and journey files in `.pytest_cache/r2-s2-t2-review.diff` / reviewed hashes).
Specification pass traced AC1-4 through report rendering, API/schema explanations,
version compatibility and browser assertions. Correctness pass checked nullable
and unknown-version reports, org-redacted match lists, raw summary persistence,
default legacy markers, queue mappings, unverified model text, unchanged ranking/
scoring/consent boundaries and owned scratch-process cleanup.

- **Medium, report presenter:** unknown scorer versions would otherwise show a
  current-colored numeric index, misinterpreting future semantics. Refuses the
  numeric index/confidence and uses a neutral ring with an unsupported-version
  notice. Actual Chrome unknown-version fixture validates this behavior.
- Browser checks now inspect accessible index labels and computed ring styling
  as well as body text, so a neutral refusal cannot pass by displaying zero.
- Harness development corrected assumptions about report name/contact fields
  (candidate context is optional), the candidate detail shape and transformed
  chip casing. These were harness defects, not successful product validation.
- The existing batch-browser check initially retained the old "fabrication
  risk" copy assertion (**20/21**). Updated it to require the new advisory
  review context sentence; final **21/21** preserves row/reason validation.
- Visible labels were inspected across candidate/org/operator template branches.
  Candidate portal still exposes report references only, not internal risk.
  There is no feature/quality catalog screen here; their schema/feature metadata
  is described conservatively. Existing unrelated prototype handlers remain
  scheduled under R3; this task does not claim they execute real flows.
- Continuation review found AC4's candidate/operator browser evidence was still
  missing despite the template inspection. Filled that validation gap with the
  29-check Chrome run above. Operator organization/account data remain prototypes;
  the new checks prove authenticated rendering, labels and reload, not admin actions.
  Rechecked the task delta, 17 reviewed hashes, preservation, bindings/syntax and
  final documentation. No application, pytest or permanent journey source changed
  in closure; the supplemental role runner is retained in ignored scratch storage.

No remaining acceptance-blocking finding in the reviewed scope. Same-agent
self-review only; no independent, live-provider, empirical quality or Linux/
PostgreSQL evidence is claimed. Browser runtime uses CDN internet.

AC1-4 and all required task gates are complete. Working DB/prior edits are
preserved; task-owned app/Chrome processes stopped, synthetic evidence retained,
and the existing local demo remains running (HTTP health 200). No working
migration, historical rewrite, deployment or external message occurred.
Next task: R2-S2-Q; R2-S2/PI-R2/F08 remain open until combined acceptance.
