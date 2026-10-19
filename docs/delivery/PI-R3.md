# PI-R3 — Complete the existing product workflows

Status: done within bounded scope (2026-10-16); [final gate](EVIDENCE-R3.md#r3-s3-q). F10/F11 retain their PI-R5 residuals. Each advertised screen performs a real authorized operation and handles errors, with browser evidence for the user journey.

Load only the current task section plus [WORKFLOW.md](WORKFLOW.md), not this entire PI by default.
Source entry points (paths relative to repository root): frontend/Veritas.dc.html; frontend/api.js; frontend/support.js; src/app/api/routes.py; src/app/verification/; src/app/interview/; src/app/curation/
Task test lists are starting points verified during planning; select/add regression cases from actual callers at implementation time.
Every task inherits [WORKFLOW.md](WORKFLOW.md). Reuse inline active task sections; completed records use PI evidence anchors.

## R3-S1 — Evaluation and verification flows

Status: done (2026-10-13). Combined gate: [R3-S1-Q](EVIDENCE-R3.md#r3-s1-q).
Bounded F09 contact ordering/delivery is complete; PI-R3 closes at R3-S3-Q, while F10 retains R5-S2-T1 regression scope.

Sprint acceptance journey: A browser user signs in, uploads, receives a real report, submits human outcome feedback and handles an invalid upload/provider outage without fake progress. Contact verification uses a captured provider in tests.

### R3-S1-T1 — Wire the evaluate screen

Status: done (2026-10-12). Audit mapping: F10. Prerequisites: R2-S2-Q.
Evidence: [R3-S1-T1](EVIDENCE-R3.md#r3-s1-t1).

**Development:** Replace timer/mock evaluation with the authorized API flow, real progress states and report navigation.

**Acceptance:** Valid input yields the server's report; invalid input, 401/403, timeout and retry behave visibly. Duplicate clicks do not create misleading success.

**Tests and journey:** Reuse screening/browser harness and API contract patterns; test text/PDF, invalid input, session expiry and real report IDs. Add an actual browser path, not only binding checks.

**Review focus:** Check correct account plane, candidate ownership and that loading state always settles on errors.

### R3-S1-T2 — Connect contact-verification delivery

Status: done (2026-10-12). Audit mapping: F09. Prerequisites: R3-S1-T1; R1-S2-T3.
Evidence: [R3-S1-T2](EVIDENCE-R3.md#r3-s1-t2).

**Development:** Inject the existing email capability into verification; use explicit refusal for unavailable phone/email delivery.

**Acceptance:** A captured email contains the challenge needed by the candidate; success/failure respects expiry/attempt limits. Delivery failure is not presented as sent. Codes and addresses are not exposed in logs.

**Tests and journey:** Extend tests/test_verification_service.py, tests/test_verification_api.py and production-wiring tests. Local HTTP capture-provider challenge → confirm; browser error/success display.

**Review focus:** Trace actual builder injection, unavailable-provider behavior and OTP privacy. No real email/SMS is sent by this task.

### R3-S1-Q — Sprint integration review

Status: done (2026-10-13). Prerequisites: all tasks in R3-S1.
Evidence: [R3-S1-Q](EVIDENCE-R3.md#r3-s1-q).

Run the [sprint closure gate](WORKFLOW.md#sprint-closure) against the acceptance journey above; record results in the existing sprint section.

## R3-S2 — Operator and curation screens

Status: done (2026-10-14). T1/T2/T3 (including T3A/T3B) and Q are done.
Combined acceptance/review: [R3-S2-Q](EVIDENCE-R3.md#r3-s2-q). Detailed children are
consolidated in PI-R3 evidence. PI-R3 closes at R3-S3-Q; F10 retains R5-S2-T1 scope.

Sprint acceptance journey: An authorized operator changes org/user/curation state through the browser, reloads and sees persisted results; wrong-plane callers are refused without disclosing tenant data.

### R3-S2-T1 — Wire organization administration

Status: done (2026-10-13). Audit mapping: F10. Prerequisites: R3-S1-Q.
Evidence: [R3-S2-T1](EVIDENCE-R3.md#r3-s2-t1).

**Development:** Replace adminorgs fixture data/actions with real list/detail/mutation APIs and honest empty/error states.

**Acceptance:** Actions persist across reload; authorization failures are explicit; destructive operations follow existing product confirmation behavior.

**Tests and journey:** Relevant admin API pytest plus browser create/edit/list or supported equivalent, pagination and denied-role scenarios.

**Review focus:** Review tenant scoping, response mapping and optimistic-state rollback.

### R3-S2-T2 — Wire user administration

Status: done (2026-10-13). Audit mapping: F10. Prerequisites: R3-S2-T1.
Evidence: [R3-S2-T2](EVIDENCE-R3.md#r3-s2-t2).

**Development:** Connect adminusers to supported user/membership/session actions; remove simulated success.

**Acceptance:** Server state drives role/status display; unsupported actions are not offered as working. Permission changes and reload agree.

**Tests and journey:** Relevant auth/admin API pytest; browser authorized mutation, denied role, stale session and error recovery.

**Review focus:** Review self-lockout behavior, owner/admin distinctions and accidental privilege escalation.

### R3-S2-T3 — Wire taxonomy curation

Status: done (2026-10-14). Audit mapping: F10. Prerequisites: R3-S2-T2.
Bounded children: [T3A/T3B contract and status](EVIDENCE-R3.md#r3-s2-t3).
T3A/T3B passed; required HTTP revisions and guarded browser decisions/lifecycle are complete. Combined sprint acceptance passed Q.

**Development:** Connect queue/review/edit actions to curation APIs with persisted result and clear conflict/refusal handling.

**Acceptance:** Accepted/rejected decisions survive reload; one actor cannot silently overwrite another's stale review. No constants masquerade as live queue counts.

**Tests and journey:** Extend tests/test_curation_api.py and tests/test_curation_service.py; real browser queue → decision → reload plus stale item and empty states.

**Review focus:** Review taxonomy normalization consequences and distinguish single-worker correctness from R4 cross-worker work.

### R3-S2-Q — Sprint integration review

Status: done (2026-10-14). Prerequisites: all tasks in R3-S2.
Evidence: [R3-S2-Q](EVIDENCE-R3.md#r3-s2-q). Combined Chrome/HTTP/restart, focused/full
pytest, PostgreSQL locks/migrations, separate self-review and preservation passed.
No application change in Q; scope and remaining limits belong to its evidence.

Run the [sprint closure gate](WORKFLOW.md#sprint-closure) against the acceptance journey above; record results in the existing sprint section.

## R3-S3 — Trustworthy interview baseline

Status: done (2026-10-16). Combined gate: [R3-S3-Q](EVIDENCE-R3.md#r3-s3-q); detailed records consolidated in PI-R3 evidence. Video and empirical quality remain PI-R5.

Sprint acceptance journey: A candidate completes a real text/audio interview in the browser and an authorized employer sees only the permitted summary. Repetitive nonsense cannot earn the strong band solely through keyword counts.

### R3-S3-T1 — Repair and version the interview rubric

Status: done (2026-10-15). Audit mapping: F11. Prerequisites: R3-S2-Q.
Evidence: [R3-S3-T1](EVIDENCE-R3.md#r3-s3-t1). Bounded `s73.2` content rubric, saved
version/history compatibility, full/focused pytest, actual migrated SQLite/PG
HTTP/restart/actor denials, common UI/contracts and separate self-review passed.
That evidence section owns findings, preservation and heuristic/quality limits; no interview
UI wiring, independent/live-provider or representative-accuracy claim. F11 stays open.

**Development:** Use distinct substantive details, relevance and repetition handling; assess semantic reasoning against explicit examples. Keep insufficient evidence neutral and score versions auditable.

**Acceptance:** The known repeated-keyword exploit fails; substantive paraphrases and concise correct answers are not punished for wording alone. No appearance/emotion scoring.

**Tests and journey:** Extend tests/test_interview_scoring.py and tests/test_interview_scoring_llm.py with repetition, fluent unrelated text, copied prompts, paraphrases and malformed model output. Freeze a small reviewed development rubric.

**Review focus:** Review confidence versus answer length, profile-term bias and historical SCORER_VERSION. This closes implementation regressions, not population accuracy.

### R3-S3-T2 — Wire interview lifecycle and text answers

Status: done (2026-10-15). Audit mapping: F11. Prerequisites: R3-S3-T1.
[T2A](EVIDENCE-R3.md#r3-s3-t2a) and [T2B](EVIDENCE-R3.md#r3-s3-t2b) passed their distinct
backend/browser gates; [parent scope/status](EVIDENCE-R3.md#r3-s3-t2). Leaf evidence
owns exact validation/review and limits. T3/Q close R3-S3/PI-R3; F11 retains PI-R5 scope.

**Development:** Replace local mock handlers with start/current question/answer/finish APIs and resumable server state.

**Acceptance:** Reload resumes the correct question; duplicate/stale answers and expired sessions show clear errors. Completion displays the saved assessment.

**Tests and journey:** Extend tests/test_interview_api.py; browser start → answer → reload → finish; another candidate cannot access the session.

**Review focus:** Review state transitions, duplicate clicks and transcript disclosure to employers.

### R3-S3-T3 — Wire microphone answers and transcription

Status: done (2026-10-16). Audit mapping: F11. Prerequisites: R3-S3-T2.
[R3-S3-T3](EVIDENCE-R3.md#r3-s3-t3) owns microphone/typed fallback, validation/privacy
fixes, actual Chrome/fake-ASR/native HTTP/restart, full regression, self-review
and preservation evidence. Q closes R3-S3/PI-R3; F11 retains PI-R5 scope. No live-ASR/quality claim.

**Development:** Connect browser audio capture to existing transcription flow with typed-answer fallback and explicit permission/size/provider errors.

**Acceptance:** Candidate can inspect or follow the documented transcript behavior; denied mic, timeout and unavailable ASR recover without losing the session. No unrequested raw-media retention.

**Tests and journey:** Fake-ASR API tests and browser media-device fixtures; permission denied, invalid MIME, size limit, retry and final assessment.

**Review focus:** Review recording indication, device cleanup, stored payloads and network/log leakage.

### R3-S3-Q — Sprint integration review

Status: done (2026-10-16). Prerequisites: all tasks in R3-S3.
Evidence: [R3-S3-Q](EVIDENCE-R3.md#r3-s3-q). Combined actual Chrome/text/audio/restart, employer consent/privacy, focused/full regression, PostgreSQL gates and separate self-review passed. No application change in Q; PI-R3 closes within scope.

Run the [sprint closure gate](WORKFLOW.md#sprint-closure) against the acceptance journey above; record results in the existing sprint section.
