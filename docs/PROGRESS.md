# Current handoff

Updated: 2026-09-26. Project: Veritas resume evaluation / talent platform.

## Start here

Feature overview: [FEATURE_STATUS.md](../FEATURE_STATUS.md). Detailed children
of closed groups are in [the archive](delivery/archive/README.md); active tasks
and completed children of open groups remain in `delivery/tasks/`. Read only
the evidence needed for the current task.

**Next task: R1-S1-T3b-D3d2c2 - challenge issuance across erasure.**
Read `docs/delivery/WORKFLOW.md`, the T3 section of `docs/delivery/PI-R1.md`,
`docs/delivery/tasks/R1-S1-T3b-D3d2c2.md` and D3d2c's split/trace. Trace the
send-before-persist boundary against erasure and define bounded acceptance
before implementation. Preserve fresh signup, all-plane cleanup, anti-enumeration,
send-failure retry and unrelated principals. Synthetic capture/null email only;
no external messages or working-data cleanup.

D3d2a/b and D3d2c1 are done. Issuance (c2), redemption/login closure (c3) and
combined validation (d) remain pending. Exactly one bounded task per session.
D3d2c/D3d2/D3d/D3/D/T3b/T3/F05/R1-S1-Q remain open. D3d2d must include source
list/portal aggregate response windows and shared curation raw-display-name policy.

## Latest completed task

**R1-S1-T3b-D3d2c1 done.** Resumed and validated the existing atomic login-state
fix. CandidateStore now deletes existing challenges for the stored email hash
in the same transaction as candidate deletion. Both portal/admin erasure inherit
commit/rollback together, independent of optional portal auth wiring. Sessions
and candidate-linked data cascade; all challenge planes/purposes retain the prior
cleanup policy. No schema/frontend change. Missing/null-address deletion leaves
unrelated challenges untouched; org/admin principals and sessions survive.

Failure or process exit before commit preserves candidate data, sessions and
existing codes. Retry completes erasure, old codes/sessions are refused, and
fresh signup remains allowed. Late issuance and already-consumed redemption are
still open c2/c3 boundaries; atomic cleanup alone does not prevent them.

- Initial red (preserved evidence): **4 failed, 4 passed, 4 skipped**, 1 warning,
  7.98s. Both API doors lost codes on candidate-delete failure; direct candidate
  deletion left challenges behind. Initial focused SQLite: **93 passed, 4 skipped**.
- Resumed full SQLite: **2497 passed, 178 skipped**, 44 warnings, 627.87s.
- Resumed focused PG 18.6: **113 passed, 2 skipped**, 16 warnings, 242.18s.
  Controlled connections, observed consume blocking, commit/rollback/retry and
  migration up/down/up passed. Disposable cluster stopped cleanly.
- Resumed migrated HTTP/process exit/restart: **24/24 per backend**, both erasure
  doors, six challenge scopes, old-code/session refusal, unrelated survivor and
  fresh signup. These runs executed 25 September; closure recorded 26 September.
- Diff self-review, compilation and whitespace passed. Node bindings now available:
  **402 bindings across 9 states passed**. No frontend change, browser execution,
  full PostgreSQL, live-provider or independent-review claim.

Evidence/commands: `docs/delivery/tasks/R1-S1-T3b-D3d2c1.md`. AUTH.md and PORTAL.md
reflect the transaction and remaining boundaries. Prior work and working DB preserved:
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B` (SHA256).
No working-data migration/deletion or deployment performed.

Documentation maintenance (2026-09-26): added `FEATURE_STATUS.md`, archived 12
detailed children of closed groups and updated links. Documentation checks passed
across 47 files; statuses and the next-task pointer are unchanged. Same-agent
review and whitespace check passed. Application code is unchanged from the
recorded full-suite run; no new application-test claim for this cleanup.

## Test environment

Use `.resume/Scripts/python.exe`. Restored matching CPython 3.13.11 base runtime
and existing project dependencies remain in use. Portable PostgreSQL 18.6:
`.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`. Latest focused/HTTP runner:
`.pytest_cache/run_r1_s1_t3b_d3d2c1_postgres.py`. These are ignored local artifacts,
not portable setup guarantees; each run creates a disposable cluster and stops
it in finally. No .env edits or Windows PostgreSQL service registration.

The remote test connection's earlier authentication rejection was not rechecked.
Use disposable storage only: shared pytest teardown drops all schemas matching
`s_%` (literal underscore). Fixtures read process DEE_TEST_DB_URL, not dotenv.
Never substitute the application database or print connection credentials.

## Standing direction and remaining risks

- Continue the named task without re-asking to perform authorized local fixes.
- Preserve user data, uncommitted work, tenant isolation and consent/erasure.
  User authorized committing/pushing the accumulated project changes and this
  documentation cleanup on 2026-09-26 using revan.datta132@gmail.com. Deployment,
  external messages and working-data/legacy-file cleanup remain unauthorized.
- Historical feature timestamps written under a non-UTC PostgreSQL session may
  still be shifted. Repair requires an explicit policy; do not guess their
  original timezone or silently rewrite existing data.
- Training final existence reads exclude erasures visible at each subject's
  check; they do not lock across later checks/file delivery or revoke returned
  snapshots/files. Current-consent enforcement remains R1-S2-T2.
- Matching final existence reads are snapshots (bounded batches for large pools),
  not locks across HTTP delivery. Committed audit ranks describe the pre-response
  ranking; after-commit erasure can leave rank gaps. D3d must not infer an atomic
  whole-response or whole-ingest guarantee from the individual-store fixes.
- Ingest candidate/resume/report checks and standalone report checks are
  snapshots, not locks across evaluation, save or HTTP delivery. Source POST
  guards have the same limit; login-state ordering and combined closure remain
  D3d2c/d. Source list/portal read windows and curation raw-display-name policy
  are explicitly carried into D3d2d.
  Current-consent gaps, identity repair, verification-attempt races
  and shared vector startup remain scheduled. Unknown input retains its original
  TTL; deletion pauses older unresolved items across tenants. This is not
  immediate erasure of unidentified text or a permanent fresh-upload ban.
- Preserve advisory/human-review behavior, domain independence and deterministic
  fallbacks. AI-polished truthful writing is not evidence of fabricated experience.
- Video scoring judges answer content, not appearance/emotion. Conversational
  video remains a recommendation, not a confirmed user format preference.
- F01-F04 are completed local fixes with baseline qualifications. T1/T2/T3a are
  done; F05-F16 remain open. Tests do not establish representative model quality.

Use `docs/delivery/README.md` for order, `docs/delivery/BASELINE.md` for prior
qualifications and `docs/CODEBASE_REVIEW_2026-09-07.md` for original findings.
`docs/ROADMAP.md` is historical reference; do not load it end to end.
