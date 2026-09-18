# PI-R2 — Reliable and explainable evaluation

Status: planned. Invalid inputs and provider output fail clearly; evidence and style observations do not masquerade as verified facts.

Load only the current task section plus [WORKFLOW.md](WORKFLOW.md), not this entire PI by default.
Source entry points (paths relative to repository root): src/app/graph/nodes/; src/app/services/llm.py; src/app/services/github.py; src/app/core/pdf.py; src/app/fabrication/; src/app/api/routes.py
Task test lists are starting points verified during planning; select/add regression cases from actual callers at implementation time.
Every task inherits the workflow's full pytest, review and relevant journey gates. Task evidence lives in `tasks/<task-id>.md`.

## R2-S1 — Input and evidence boundaries

Sprint acceptance journey: Submit a readable PDF/text resume, corrupt PDF, empty input and malformed model JSON. Only valid inputs produce evaluation reports; provider failures retain deterministic behavior and never create supporting evidence.

### R2-S1-T1 — Validate model response structures

Status: pending. Audit mapping: F07. Prerequisites: R1-S2-Q.

**Development:** Validate JSON shape, finite numeric bounds and collection members at provider-consumer boundaries. Use existing schemas before adding abstraction.

**Acceptance:** Wrong top-level type, null lists, numeric strings, NaN/infinity, missing keys and transport failure produce explicit deterministic fallback. Valid replies preserve behavior.

**Tests and journey:** Extend relevant node tests and tests/test_llm_config.py; add malformed-output cases for each reachable LLM-assisted consumer. Full evaluation HTTP smoke with a fake malformed provider.

**Review focus:** Inventory consumers; avoid fixing only plausibility while ai_signals/interview parsing retain the same defect. Do not silently accept partial invalid data as high confidence.

### R2-S1-T2 — Refuse unreadable or oversized resumes

Status: pending. Audit mapping: F07; F14 input overlap. Prerequisites: R2-S1-T1.

**Development:** Align evaluation and ingest validation for corrupt PDFs, whitespace and post-extraction text limits. Bound PDF page/work consumption using explicit settings.

**Acceptance:** Unreadable input returns a defined client error, no successful saved report. Sparse but readable input remains distinguishable. Extracted-text bounds apply after decoding.

**Tests and journey:** Extend tests/test_pdf.py and affected API/ingest tests. HTTP tests for corrupt/truncated/encrypted or scanned PDFs, whitespace, boundary sizes and valid TXT/Markdown/PDF.

**Review focus:** Review memory expansion, error leakage and all intake paths; reuse validation rather than divergent route-only checks.

### R2-S1-T3 — Correct GitHub evidence polarity

Status: pending. Audit mapping: F07; F02 residual. Prerequisites: R2-S1-T2.

**Development:** Represent unavailable, rate-limited and failed GitHub fetches as unavailable evidence, separate from factual supporting/contradicting content.

**Acceptance:** 429/timeouts/transport errors never support a claim. Missing/private repositories are not automatically proof of fabrication. F02 isolation stays intact.

**Tests and journey:** Extend tests/test_provenance.py and plausibility/GitHub tests. Fake responses for success/404/403/429/timeout; report-level evidence assertions.

**Review focus:** Review text-to-polarity shortcuts, public/private visibility and whether a repo's existence actually corroborates the claim.

### R2-S1-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R2-S1.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R2-S1-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.

## R2-S2 — Separate style from factual risk

Sprint acceptance journey: Two versions of the same truthful resume, plain and AI-polished, retain the same factual-risk result when their dates/evidence/duplication signals are fixed. Actual timeline/duplication findings remain visible.

### R2-S2-T1 — Remove style from fabrication fusion

Status: pending. Audit mapping: F08. Prerequisites: R2-S1-Q.

**Development:** Keep style optional and descriptive; remove its influence from factual-risk mean, maximum, confidence coverage and corroboration gates. Version changed scoring semantics.

**Acceptance:** Style-only changes cannot elevate factual risk. Missing data still refuses; timeline/duplication boundaries are tested. Stored historical reports retain their original interpretation.

**Tests and journey:** Extend tests/test_report_ai.py, tests/test_report_fabrication_risk.py and risk-unit tests. Plain/polished truthful fixtures and zero-weight/high-style cases.

**Review focus:** Review schemas, feature definitions, exports and historical versioning. Merely setting fr_weight_ai=0 is insufficient.

### R2-S2-T2 — Explain findings in the actual UI

Status: pending. Audit mapping: F08. Prerequisites: R2-S2-T1.

**Development:** Update report presentation and help text to explain observations, uncertainty and candidate clarification. Remove authorship/fraud-probability language unsupported by the code.

**Acceptance:** Polished wording is not labeled dishonesty. Timeline overlaps/shared templates provide specific review context. Insufficient data is visually distinct from low score.

**Tests and journey:** API contract tests plus browser report rendering for plain/polished, timeline, duplication and missing-data fixtures; binding and JS syntax checks.

**Review focus:** Review visible text and feature/ranking labels across candidate/org/admin views, not just backend descriptions.

### R2-S2-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R2-S2.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R2-S2-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.

