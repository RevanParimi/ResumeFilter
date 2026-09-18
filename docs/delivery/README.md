# Remediation delivery plan

Updated: 2026-09-09. This is the execution plan for the approved audit fixes,
feature completion and simplification. It adds structure to the existing work;
it does not claim any pending implementation or validation is complete.

**One task per chat.** `docs/PROGRESS.md` names the exact next task.
Read [WORKFLOW.md](WORKFLOW.md), that task's PI section and its evidence record.
Do not load all PIs or the historical roadmap in each session.

## Increments and sprint order

PI-R identifies remediation work; historical product PI identifiers remain unchanged.
Sprints are dependency/acceptance groups, not calendar promises. There are **5 PIs,
12 sprints, 38 development tasks and 12 sprint integration-review tasks**.

| PI | Outcome | Sprint sequence |
|---|---|---|
| [PI-R1](PI-R1.md) | Deleting or revoking access to a candidate's data must remain effective across reports, derived stores and concurrent requests. | R1-S1, R1-S2 |
| [PI-R2](PI-R2.md) | Invalid inputs and provider output fail clearly; evidence and style observations do not masquerade as verified facts. | R2-S1, R2-S2 |
| [PI-R3](PI-R3.md) | Each advertised screen performs a real authorized operation and handles errors, with browser evidence for the user journey. | R3-S1, R3-S2, R3-S3 |
| [PI-R4](PI-R4.md) | Reduce unnecessary machinery while proving ownership, concurrency, resource lifecycle and operating behavior remain correct. | R4-S1, R4-S2, R4-S3 |
| [PI-R5](PI-R5.md) | Deliver a content-scored interview experience and distinguish functional correctness from measured assessment effectiveness. | R5-S1, R5-S2 |

## Session order

Follow the order below unless recorded dependencies or new evidence require an
explicit plan update. A `-Q` task is a separate chat to test/review the integrated
sprint. Do not close a parent finding after only its first subtask.

| Sprint | Development tasks (in order) | Closing task |
|---|---|---|
| [R1-S1 — Complete erasure](PI-R1.md) | R1-S1-T1, R1-S1-T2, R1-S1-T3 | R1-S1-Q |
| [R1-S2 — Enforce current authorization](PI-R1.md) | R1-S2-T1, R1-S2-T2, R1-S2-T3, R1-S2-T4 | R1-S2-Q |
| [R2-S1 — Input and evidence boundaries](PI-R2.md) | R2-S1-T1, R2-S1-T2, R2-S1-T3 | R2-S1-Q |
| [R2-S2 — Separate style from factual risk](PI-R2.md) | R2-S2-T1, R2-S2-T2 | R2-S2-Q |
| [R3-S1 — Evaluation and verification flows](PI-R3.md) | R3-S1-T1, R3-S1-T2 | R3-S1-Q |
| [R3-S2 — Operator and curation screens](PI-R3.md) | R3-S2-T1, R3-S2-T2, R3-S2-T3 | R3-S2-Q |
| [R3-S3 — Trustworthy interview baseline](PI-R3.md) | R3-S3-T1, R3-S3-T2, R3-S3-T3 | R3-S3-Q |
| [R4-S1 — Simplify construction and boundaries](PI-R4.md) | R4-S1-T1, R4-S1-T2, R4-S1-T3, R4-S1-T4 | R4-S1-Q |
| [R4-S2 — Concurrency and bounded work](PI-R4.md) | R4-S2-T1, R4-S2-T2, R4-S2-T3, R4-S2-T4 | R4-S2-Q |
| [R4-S3 — Cross-worker state and reproducibility](PI-R4.md) | R4-S3-T1, R4-S3-T2, R4-S3-T3 | R4-S3-Q |
| [R5-S1 — Conversational interview transport](PI-R5.md) | R5-S1-T1, R5-S1-T2, R5-S1-T3, R5-S1-T4 | R5-S1-Q |
| [R5-S2 — End-to-end regression and effectiveness](PI-R5.md) | R5-S2-T1, R5-S2-T2, R5-S2-T3 | R5-S2-Q |

## Audit traceability

| Finding | Completed baseline or remaining tasks |
|---|---|
| F01 | Baseline fix complete; verified binding/identity-change residual R1-S2-T4 |
| F02 | Baseline isolation fix complete; fetch polarity R2-S1-T3, unused infrastructure R4-S1-T2 |
| F03 | Baseline snapshot fix complete; preserve it in R1-S2 consent checks and R4 refactors |
| F04 | Login fix complete; actual PostgreSQL evidence at R1-S2-Q; separate verification race R1-S2-T3 |
| F05 | R1-S1-T1/T2/T3 and R1-S1-Q; future-media extension R5-S1-T4 |
| F06 | R1-S2-T1/T2 and R1-S2-Q; future-media extension R5-S1-T4 |
| F07 | R2-S1-T1/T2/T3 and R2-S1-Q |
| F08 | R2-S2-T1/T2 and R2-S2-Q |
| F09 | R1-S2-T3 and R3-S1-T2; corresponding sprint gates |
| F10 | R3-S1-T1; R3-S2-T1/T2/T3; browser regression R5-S2-T1 |
| F11 | R3-S3-T1/T2/T3; video R5-S1-T1/T2/T3/T4; corresponding gates |
| F12 | R4-S1-T1 and R4-S1-Q |
| F13 | R4-S1-T2/T3/T4 and R4-S1-Q |
| F14 | R2-S1-T2; R4-S2-T1/T2/T3/T4 and R4-S2-Q |
| F15 | R4-S3-T1/T2/T3; R5-S2-T1; corresponding gates |
| F16 | R5-S2-T2/T3 and R5-S2-Q; no accuracy claim until empirical evidence exists |

Additional audit details are included explicitly: provider error disclosure and
readiness (R4-S3-T2), curation/metrics divergence (R4-S3-T1), tracked runtime DB
and floating transitive dependencies (R4-S3-T3), interrupted browser-driven
batches (R4-S2-T4), and unchanged historical score semantics (R2-S2/R3-S3).
An executable coding sandbox, government-identity integration, new trained
ranking model, DOCX/OCR expansion and calibrated compensation product are not
silently promised by this remediation plan. Existing scaffolds/heuristics remain
labeled as such; additions need explicit task scope and acceptance criteria.

## Durable context and evidence

- [BASELINE.md](BASELINE.md): what was actually completed/tested before this plan,
  plus unproven environments and residuals. The latest full suite recorded is
  2155 passed with 42 warnings; it was not rerun for this documentation task.
- [WORKFLOW.md](WORKFLOW.md): development/review/pytest/journey completion gates.
- [TASK_TEMPLATE.md](TASK_TEMPLATE.md): short reproducible task record, populated
  when each task starts. PI cards already contain its initial scope/tests.
- [R1-S1-T2 evidence](tasks/R1-S1-T2.md): legacy-file policy and cleanup validation.
- [Original audit](../CODEBASE_REVIEW_2026-09-07.md): detailed evidence, historical.
- [Feature logic](../FEATURE_LOGIC.md): current scoring/formulas and limitations.

Planning checks: verify every F01–F16 mapping, unique IDs, existing prerequisites,
acyclic task order, local links and source/test entry points. Record validation
results in the current handoff. No application tests are claimed from planning.

Planning review on 2026-09-09: a one-off Node filesystem/structure check passed
for all 10 delivery Markdown files, 38 development tasks, 12 sprint-review tasks,
16 audit mappings, task-card fields, local links and an acyclic dependency graph.
`git diff --check` passed. Self-review covered acceptance versus testing scope,
one-task session boundaries, missing environment evidence and historical
qualifications. No independent review or application test run is claimed.
