# PI-R2 — Reliable and explainable evaluation

Status: done (2026-10-12 bounded remediation; Unicode PDF correction validated 2026-10-13). Invalid inputs and provider output fail clearly; evidence and style observations do not masquerade as verified facts.
Combined evidence: [R2-S1-Q](EVIDENCE-R2.md#r2-s1-q) and [R2-S2-Q](EVIDENCE-R2.md#r2-s2-q).
F07/F08 bounded gates are complete; parser operational residuals and empirical
quality remain assigned to their later PIs. No representative accuracy claim.

Load only the current task section plus [WORKFLOW.md](WORKFLOW.md), not this entire PI by default.
Source entry points (paths relative to repository root): src/app/graph/nodes/; src/app/services/llm.py; src/app/services/github.py; src/app/core/pdf.py; src/app/fabrication/; src/app/api/routes.py
Task test lists are starting points verified during planning; select/add regression cases from actual callers at implementation time.
Every task inherits the workflow's full pytest, review and relevant journey gates. Follow the linked records; completed child evidence is archived.

## R2-S1 — Input and evidence boundaries

Status: done (2026-10-12). [Integration evidence](EVIDENCE-R2.md#r2-s1-q) closes the
bounded F07 gate; PI-R2 closure is recorded above.

Sprint acceptance journey: Submit a readable PDF/text resume, corrupt PDF, empty input and malformed model JSON. Only valid inputs produce evaluation reports; provider failures retain deterministic behavior and never create supporting evidence.

### R2-S1-T1 — Validate model response structures

Status: done (2026-10-10; provider structure slice). Audit mapping: F07. Prerequisites: R1-S2-Q.
Evidence: [R2-S1-T1](EVIDENCE-R2.md#r2-s1-t1).

**Development:** Validate JSON shape, finite numeric bounds and collection members at provider-consumer boundaries. Use existing schemas before adding abstraction.

**Acceptance:** Wrong top-level type, null lists, numeric strings, NaN/infinity, missing keys and transport failure produce explicit deterministic fallback. Valid replies preserve behavior.

**Tests and journey:** Extend relevant node tests and tests/test_llm_config.py; add malformed-output cases for each reachable LLM-assisted consumer. Full evaluation HTTP smoke with a fake malformed provider.

**Review focus:** Inventory consumers; avoid fixing only plausibility while ai_signals/interview parsing retain the same defect. Do not silently accept partial invalid data as high confidence.

### R2-S1-T2 — Refuse unreadable or oversized resumes

Status: done (2026-10-11 child closure; Unicode output correction validated 2026-10-13).
Audit mapping: F07; F14 input overlap. Prerequisites: R2-S1-T1.
Children/status: [R2-S1-T2](EVIDENCE-R2.md#r2-s1-t2). Both child contracts passed;
archived child records own Windows/Linux/image evidence and limits.
[Q](EVIDENCE-R2.md#r2-s1-q) owns the completed combined sprint gate.

**Development:** Align evaluation and ingest validation for corrupt PDFs, whitespace and post-extraction text limits. Bound PDF page/work consumption using explicit settings.

**Acceptance:** Unreadable input returns a defined client error, no successful saved report. Sparse but readable input remains distinguishable. Extracted-text bounds apply after decoding.

**Tests and journey:** Extend tests/test_pdf.py and affected API/ingest tests. HTTP tests for corrupt/truncated/encrypted or scanned PDFs, whitespace, boundary sizes and valid TXT/Markdown/PDF.

**Review focus:** Review memory expansion, error leakage and all intake paths; reuse validation rather than divergent route-only checks.

### R2-S1-T3 — Correct GitHub evidence polarity

Status: done (2026-10-11; repository metadata/unavailable context). Audit mapping: F07; F02 residual. Prerequisites: R2-S1-T2.
Evidence: [R2-S1-T3](EVIDENCE-R2.md#r2-s1-t3).
New reports use neutral, zero-weight GitHub context outside rule/model claim
corroboration; claim/evaluation isolation, persisted ownership and advisory
review remain. Leaf evidence owns regressions, full pytest, HTTP/restart,
Chrome, contract checks and same-agent review. [Q](EVIDENCE-R2.md#r2-s1-q) closes
R2-S1/F07; PI-R2 closure is recorded above. Historical reports are not rewritten.

**Development:** Represent unavailable, rate-limited and failed GitHub fetches as unavailable evidence, separate from factual supporting/contradicting content.

**Acceptance:** 429/timeouts/transport errors never support a claim. Missing/private repositories are not automatically proof of fabrication. F02 isolation stays intact.

**Tests and journey:** Extend tests/test_provenance.py and plausibility/GitHub tests. Fake responses for success/404/403/429/timeout; report-level evidence assertions.

**Review focus:** Review text-to-polarity shortcuts, public/private visibility and whether a repo's existence actually corroborates the claim.

### R2-S1-Q — Sprint integration review

Status: done (2026-10-12). Prerequisites: all tasks in R2-S1, done.
Evidence: [R2-S1-Q](EVIDENCE-R2.md#r2-s1-q).

Run the [sprint closure gate](WORKFLOW.md#sprint-closure) against the acceptance journey above; record results in the existing sprint section.

## R2-S2 — Separate style from factual risk

Status: done (2026-10-12). [R2-S2-Q](EVIDENCE-R2.md#r2-s2-q) owns combined acceptance,
separate self-review and bounded F08 closure. Detailed T1/T2 evidence is archived;
historical reports retain their interpretation. PI-R2 is complete within scope.

Sprint acceptance journey: Two versions of the same truthful resume, plain and AI-polished, retain the same factual-risk result when their dates/evidence/duplication signals are fixed. Actual timeline/duplication findings remain visible.

### R2-S2-T1 — Remove style from fabrication fusion

Status: done (2026-10-12; factual-risk v2). Audit mapping: F08. Prerequisites: R2-S1-Q.
Evidence: [R2-S2-T1](EVIDENCE-R2.md#r2-s2-t1).
Style is excluded from new risk math/coverage/gates. Historical v1 reports and
vectors retain their interpretation; risk features/default bundle are versioned.
Leaf evidence owns full/focused pytest, migrated HTTP/restart, Chrome/contracts,
preservation and separate self-review. [Q](EVIDENCE-R2.md#r2-s2-q) closes R2-S2/F08.

**Development:** Keep style optional and descriptive; remove its influence from factual-risk mean, maximum, confidence coverage and corroboration gates. Version changed scoring semantics.

**Acceptance:** Style-only changes cannot elevate factual risk. Missing data still refuses; timeline/duplication boundaries are tested. Stored historical reports retain their original interpretation.

**Tests and journey:** Extend tests/test_report.py, tests/test_report.py and risk-unit tests. Plain/polished truthful fixtures and zero-weight/high-style cases.

**Review focus:** Review schemas, feature definitions, exports and historical versioning. Merely setting fr_weight_ai=0 is insufficient.

### R2-S2-T2 — Explain findings in the actual UI

Status: done (2026-10-12). Audit mapping: F08. Prerequisites: R2-S2-T1, done.
Scope, review and validation: [R2-S2-T2 evidence](EVIDENCE-R2.md#r2-s2-t2).
Reports separate descriptive style, factual observations and missing coverage,
with candidate clarification and explicit historical/current version notices.
Full/focused pytest, actual migrated HTTP, Chrome across the exposed planes,
contracts, preservation and same-agent review passed. [Q](EVIDENCE-R2.md#r2-s2-q)
closes the combined gate and bounded F08.

**Development:** Update report presentation and help text to explain observations, uncertainty and candidate clarification. Remove authorship/fraud-probability language unsupported by the code.

**Acceptance:** Polished wording is not labeled dishonesty. Timeline overlaps/shared templates provide specific review context. Insufficient data is visually distinct from low score.

**Tests and journey:** API contract tests plus browser report rendering for plain/polished, timeline, duplication and missing-data fixtures; binding and JS syntax checks.

**Review focus:** Review visible text and feature/ranking labels across candidate/org/admin views, not just backend descriptions.

### R2-S2-Q — Sprint integration review

Status: done (2026-10-12). Prerequisites: all tasks in R2-S2, done.
Scope and evidence: [R2-S2-Q](EVIDENCE-R2.md#r2-s2-q).
Combined factual invariance, observations/uncertainty, neutral refusal, historical
compatibility and ownership/consent passed through fresh focused/full pytest,
migrated scratch HTTP/restart, actual Chrome and UI contracts. No application
change in Q. Next R3-S1-T1, not started.

Run the [sprint closure gate](WORKFLOW.md#sprint-closure) against the acceptance journey above; record results in the existing sprint section.
