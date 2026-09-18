# PI-R5 — Video interviews and measured product quality

Status: planned. Deliver a content-scored interview experience and distinguish functional correctness from measured assessment effectiveness.

Load only the current task section plus [WORKFLOW.md](WORKFLOW.md), not this entire PI by default.
Source entry points (paths relative to repository root): src/app/interview/; src/app/services/; src/app/signal_quality/; frontend/; scripts/; .github/workflows/ci.yml
Task test lists are starting points verified during planning; select/add regression cases from actual callers at implementation time.
Every task inherits the workflow's full pytest, review and relevant journey gates. Task evidence lives in `tasks/<task-id>.md`.

## R5-S1 — Conversational interview transport

Sprint acceptance journey: A synthetic candidate completes a conversational camera/mic session, interrupts, reconnects and finishes. The transcript/assessment persists correctly and no media is retained outside the explicit policy.

### R5-S1-T1 — Define video contract and provider adapter

Status: pending. Audit mapping: F11. Prerequisites: R4-S3-Q; R3-S3-Q.

**Development:** Turn the working conversational-video recommendation into explicit session/message/state contracts, using a fake provider first. Camera preview alone must not be called AI video interviewing.

**Acceptance:** Define prompt/answer turns, adaptive follow-ups, audio output, interruption, reconnect, typed fallback and retention defaults. Provider secrets stay server-side; unavailable capability refuses honestly.

**Tests and journey:** Contract/state-machine pytest with fake streaming events, malformed messages and expired authorization; adapter smoke with no external calls.

**Review focus:** Review candidate consent and transport choice against current APIs. This is contract/adapter completion, not finished video UX.

### R5-S1-T2 — Implement streamed turns and adaptive follow-ups

Status: pending. Audit mapping: F11. Prerequisites: R5-S1-T1.

**Development:** Implement server turn sequencing, bounded follow-up generation, speech output and interruption/reconnect semantics behind the adapter.

**Acceptance:** Duplicate/out-of-order events cannot double-submit answers; follow-ups are grounded in current answers; interruption stops stale output. Scoring remains content-only.

**Tests and journey:** Fake-stream integration tests for normal turns, delayed packets, reconnect, invalid model replies and provider loss; authenticated transport smoke.

**Review focus:** Review session ownership, transcript reconciliation, time/cost bounds and prompt injection in candidate answers.

### R5-S1-T3 — Build the camera/microphone interview UI

Status: pending. Audit mapping: F11. Prerequisites: R5-S1-T2.

**Development:** Connect device preview and conversational transport with visible recording state, accessibility and recovery. Reuse the completed interview lifecycle.

**Acceptance:** Camera/mic denial, interruption and reconnect preserve the session; text fallback works; completion uses the stored assessment, not local simulated values.

**Tests and journey:** Browser synthetic media/WebRTC or selected-transport fixtures; console/network assertions, reload/reconnect and two-session ownership checks.

**Review focus:** Review device release, state transitions, keyboard access and unsupported browser behavior.

### R5-S1-T4 — Enforce media retention and deletion

Status: pending. Audit mapping: F05; F06; F11 extension. Prerequisites: R5-S1-T3.

**Development:** Default to no retained raw video unless explicitly required; define and enforce any recording retention, access and erasure lifecycle before enabling recording.

**Acceptance:** Erasure/revocation covers recordings, transcripts and derived artifacts as applicable; expired links and other users cannot read media; no appearance/emotion features enter scoring.

**Tests and journey:** Extend interview erasure/consent tests with fake media storage and in-flight upload. Browser finish → access policy → erase → retry old media link.

**Review focus:** Review caches, chunks, temporary files, provider retention and deletion receipts. Real provider retention remains unverified until separately checked.

### R5-S1-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R5-S1.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R5-S1-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.

## R5-S2 — End-to-end regression and effectiveness

Sprint acceptance journey: Core journeys run in CI with real browser/API/storage boundaries and fake external providers. Evaluation claims have a versioned held-out benchmark or remain explicitly unvalidated.

### R5-S2-T1 — Make browser journeys repeatable in CI

Status: pending. Audit mapping: F10; F11; F15. Prerequisites: R5-S1-Q.

**Development:** Extend existing browser checks to all completed screens; make runtime assets/dependencies reproducible. Use fake/capture providers and deterministic fixtures.

**Acceptance:** Sign in → upload → report → review outcome, operator curation, portal consent/erase, and interview journeys pass with console errors captured. No fixture secrets or live provider calls.

**Tests and journey:** Browser CI job plus API smokes, SQLite suite and existing PostgreSQL job. Negative paths cover wrong tenant, session expiry and provider outage.

**Review focus:** Review actual browser execution versus source/contract assertions; CI definitions alone are not successful CI runs.

### R5-S2-T2 — Build a representative benchmark and rubric

Status: pending. Audit mapping: F16. Prerequisites: R5-S2-T1.

**Development:** Define evidence-backed labels, review rubric and independent train/development/held-out partitions for resume signals and interviews. Use synthetic data for mechanics; do not call it representative human validation.

**Acceptance:** Include AI-polished truthful resumes, legitimate overlaps/templates, substantive paraphrases and fluent nonsense. Keep employers/candidates/templates separated across partitions where leakage is possible.

**Tests and journey:** Test metric/refusal math using existing signal_quality tests; inspect label provenance, split leakage, class balance and duplicate groups.

**Review focus:** Record dataset permissions, sample sizes, annotator disagreement and confidence intervals. No invented human labels or claimed 5–10% error rate.

### R5-S2-T3 — Measure quality and close the release assessment

Status: pending. Audit mapping: F16; all parents. Prerequisites: R5-S2-T2.

**Development:** Run the frozen benchmark, report false positives/negatives and uncertainty, resolve regressions, and produce a cross-PI acceptance matrix. Live-provider results are separate from offline results.

**Acceptance:** No unsupported accuracy/fraud probability claim. Each release gate is passed or explicitly awaiting evidence; missing real labels/providers cannot be filled with estimates. Parent findings close only with linked evidence.

**Tests and journey:** Versioned benchmark report, full pytest, PostgreSQL concurrency/migration evidence, browser journeys and startup/restart smoke at the final reviewed code state.

**Review focus:** Review test overfitting, calibration, remaining warnings and production-only limits. Release readiness does not authorize publishing or deployment.

### R5-S2-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R5-S2.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R5-S2-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.

