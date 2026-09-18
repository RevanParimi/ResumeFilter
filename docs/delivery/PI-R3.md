# PI-R3 — Complete the existing product workflows

Status: planned. Each advertised screen performs a real authorized operation and handles errors, with browser evidence for the user journey.

Load only the current task section plus [WORKFLOW.md](WORKFLOW.md), not this entire PI by default.
Source entry points (paths relative to repository root): frontend/Veritas.dc.html; frontend/api.js; frontend/support.js; src/app/api/routes.py; src/app/verification/; src/app/interview/; src/app/curation/
Task test lists are starting points verified during planning; select/add regression cases from actual callers at implementation time.
Every task inherits the workflow's full pytest, review and relevant journey gates. Task evidence lives in `tasks/<task-id>.md`.

## R3-S1 — Evaluation and verification flows

Sprint acceptance journey: A browser user signs in, uploads, receives a real report, submits human outcome feedback and handles an invalid upload/provider outage without fake progress. Contact verification uses a captured provider in tests.

### R3-S1-T1 — Wire the evaluate screen

Status: pending. Audit mapping: F10. Prerequisites: R2-S2-Q.

**Development:** Replace timer/mock evaluation with the authorized API flow, real progress states and report navigation.

**Acceptance:** Valid input yields the server's report; invalid input, 401/403, timeout and retry behave visibly. Duplicate clicks do not create misleading success.

**Tests and journey:** Reuse screening/browser harness and API contract patterns; test text/PDF, invalid input, session expiry and real report IDs. Add an actual browser path, not only binding checks.

**Review focus:** Check correct account plane, candidate ownership and that loading state always settles on errors.

### R3-S1-T2 — Connect contact-verification delivery

Status: pending. Audit mapping: F09. Prerequisites: R3-S1-T1; R1-S2-T3.

**Development:** Inject the existing email capability into verification; use explicit refusal for unavailable phone/email delivery.

**Acceptance:** A captured email contains the challenge needed by the candidate; success/failure respects expiry/attempt limits. Delivery failure is not presented as sent. Codes and addresses are not exposed in logs.

**Tests and journey:** Extend tests/test_verification_service.py, tests/test_verification_api.py and production-wiring tests. Local HTTP capture-provider challenge → confirm; browser error/success display.

**Review focus:** Trace actual builder injection, unavailable-provider behavior and OTP privacy. No real email/SMS is sent by this task.

### R3-S1-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R3-S1.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R3-S1-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.

## R3-S2 — Operator and curation screens

Sprint acceptance journey: An authorized operator changes org/user/curation state through the browser, reloads and sees persisted results; wrong-plane callers are refused without disclosing tenant data.

### R3-S2-T1 — Wire organization administration

Status: pending. Audit mapping: F10. Prerequisites: R3-S1-Q.

**Development:** Replace adminorgs fixture data/actions with real list/detail/mutation APIs and honest empty/error states.

**Acceptance:** Actions persist across reload; authorization failures are explicit; destructive operations follow existing product confirmation behavior.

**Tests and journey:** Relevant admin API pytest plus browser create/edit/list or supported equivalent, pagination and denied-role scenarios.

**Review focus:** Review tenant scoping, response mapping and optimistic-state rollback.

### R3-S2-T2 — Wire user administration

Status: pending. Audit mapping: F10. Prerequisites: R3-S2-T1.

**Development:** Connect adminusers to supported user/membership/session actions; remove simulated success.

**Acceptance:** Server state drives role/status display; unsupported actions are not offered as working. Permission changes and reload agree.

**Tests and journey:** Relevant auth/admin API pytest; browser authorized mutation, denied role, stale session and error recovery.

**Review focus:** Review self-lockout behavior, owner/admin distinctions and accidental privilege escalation.

### R3-S2-T3 — Wire taxonomy curation

Status: pending. Audit mapping: F10. Prerequisites: R3-S2-T2.

**Development:** Connect queue/review/edit actions to curation APIs with persisted result and clear conflict/refusal handling.

**Acceptance:** Accepted/rejected decisions survive reload; one actor cannot silently overwrite another's stale review. No constants masquerade as live queue counts.

**Tests and journey:** Extend tests/test_curation_api.py and tests/test_curation_service.py; real browser queue → decision → reload plus stale item and empty states.

**Review focus:** Review taxonomy normalization consequences and distinguish single-worker correctness from R4 cross-worker work.

### R3-S2-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R3-S2.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R3-S2-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.

## R3-S3 — Trustworthy interview baseline

Sprint acceptance journey: A candidate completes a real text/audio interview in the browser and an authorized employer sees only the permitted summary. Repetitive nonsense cannot earn the strong band solely through keyword counts.

### R3-S3-T1 — Repair and version the interview rubric

Status: pending. Audit mapping: F11. Prerequisites: R3-S2-Q.

**Development:** Use distinct substantive details, relevance and repetition handling; assess semantic reasoning against explicit examples. Keep insufficient evidence neutral and score versions auditable.

**Acceptance:** The known repeated-keyword exploit fails; substantive paraphrases and concise correct answers are not punished for wording alone. No appearance/emotion scoring.

**Tests and journey:** Extend tests/test_interview_scoring.py and tests/test_interview_scoring_llm.py with repetition, fluent unrelated text, copied prompts, paraphrases and malformed model output. Freeze a small reviewed development rubric.

**Review focus:** Review confidence versus answer length, profile-term bias and historical SCORER_VERSION. This closes implementation regressions, not population accuracy.

### R3-S3-T2 — Wire interview lifecycle and text answers

Status: pending. Audit mapping: F11. Prerequisites: R3-S3-T1.

**Development:** Replace local mock handlers with start/current question/answer/finish APIs and resumable server state.

**Acceptance:** Reload resumes the correct question; duplicate/stale answers and expired sessions show clear errors. Completion displays the saved assessment.

**Tests and journey:** Extend tests/test_interview_api.py; browser start → answer → reload → finish; another candidate cannot access the session.

**Review focus:** Review state transitions, duplicate clicks and transcript disclosure to employers.

### R3-S3-T3 — Wire microphone answers and transcription

Status: pending. Audit mapping: F11. Prerequisites: R3-S3-T2.

**Development:** Connect browser audio capture to existing transcription flow with typed-answer fallback and explicit permission/size/provider errors.

**Acceptance:** Candidate can inspect or follow the documented transcript behavior; denied mic, timeout and unavailable ASR recover without losing the session. No unrequested raw-media retention.

**Tests and journey:** Fake-ASR API tests and browser media-device fixtures; permission denied, invalid MIME, size limit, retry and final assessment.

**Review focus:** Review recording indication, device cleanup, stored payloads and network/log leakage.

### R3-S3-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R3-S3.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R3-S3-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.

