# R1-S1-T3b-D3c3 - Matching disclosure audit/response erasure

Status: done (2026-09-24). Parent: [D3c](../tasks/R1-S1-T3b-D3c.md).

## Acceptance and scope

Trigger: erasure after loading/ranking materialized vectors but before the
match.surface audit commits, or after that commit before response assembly.
Today one vanished subject aborts the whole audit with an IntegrityError, or its
cached match is returned. POST /jobs/{id}/match and GET /jobs/{id}/board
(the requisition board) must omit subjects whose erasure is observed, retain
surviving advisory matches and continue using the existing response schemas.

- Roll back a failed batch audit, check candidate existence in a fresh read, and
  retry only when an attempted subject disappeared. Each retry removes at least
  one subject; unrelated integrity/lookup errors propagate. No partial audit
  batch or duplicate survivor audit from a rolled-back attempt.
- Remove erased subjects from the ranked pool and refill the limit before a
  successful audit. Preserve original survivor scores, contributions, ordering,
  filter membership and stored consent masking. Re-number audit ranks on retry.
- Recheck existence after audit commit; filter response rows and pool/filtered
  counts. Do not backfill unaudited candidates after this final check. An
  after-commit erasure may shorten the result; audit rank records the committed
  ranking. Checks are snapshots, not locks across HTTP delivery or revocation of
  already delivered data. Preserve empty-result API behavior.
- Cover pre-audit/before-flush/after-commit erasure, multiple erasures during
  retries, all erased, filtered/outside-limit erasures, ownership rejection before
  reads/audits, retries and unrelated failures. Both direct and dashboard APIs
  must exercise the real matcher and isolated stores with synthetic providers.
- Required: red/green, full pytest, SQLite/PG controlled competing sessions and
  observed FK blocking, full migration up/down/up, migrated HTTP/restart journey,
  static checks and separate diff self-review. No new schema, consent policy,
  ranking formula, frontend handler or visible UI contract; no browser claim.
  Current-consent changes remain R1-S2; cross-store ordering remains D3d.

Use existing CASCADE foreign keys and a bounded retry of the existing batch
transaction. No per-candidate commits or generalized audit framework.

## Evidence

- Red: `.resume/Scripts/python.exe -m pytest -q tests/test_match_disclosure_erasure.py --tb=short`:
  **20 failed, 1 passed, 15 skipped**, 1 warning, 13.33s. Intended audit FK/HTTP
  500 failures, stale returned matches and stale pool counts reproduced.
- Focused: `.resume/Scripts/python.exe -m pytest -q tests/test_match_disclosure_erasure.py tests/test_job_store_match.py tests/test_jobs_api.py tests/test_dashboard_api.py tests/test_dashboard_service.py tests/test_matching_match.py tests/test_matching_engine.py tests/test_job_store.py --tb=short`:
  **63 passed, 16 skipped**, 1 warning, 16.00s. Includes final empty-response
  and unrelated LookupError regressions; exact survivor scores/contributions,
  retry audit counts/ranks, portal/operator erasure, two-actor ownership, and
  controlled competing SQLite connections.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3c3.py`: **21/21** on
  migrated scratch SQLite. Real app/HTTP on both routes, ranked/before-flush/
  after-commit erasure, unauthorized calls, retry, limit-one post-commit refusal
  to backfill, unrelated failure and recovery, restart/vector/audit inspection,
  existing all-erased empty response. Synthetic hooks, not worker-crash evidence.
- `.resume/Scripts/python.exe -m py_compile src/app/matching/store.py tests/test_match_disclosure_erasure.py scripts/smoke_r1_s1_t3b_d3c3.py`
  and `git diff --check`, changed-file whitespace and local documentation links
  passed. `node scripts/check_ui_bindings.js` unavailable
  (Node not installed); no frontend handler/schema changed, no browser claim.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3c3_postgres.py`:
  PostgreSQL 18.6 focused **167 passed, 3 skipped**, 16 warnings, 167.70s.
  Twelve files cover matching/dashboard, materialization/training audit callers,
  feature erasure and migrations. Skips are SQLite variants of PG lock inspection.
  Controlled delete-first/audit-first orderings and observed pg_blocking_pids
  blocking passed. Full migration chain up/down/up passed on disposable storage.
  PostgreSQL migrated HTTP/restart **21/21**, 20.62s; scratch cluster stopped
  cleanly (exit 0, 18.00s). No full PostgreSQL suite
  claim. Logs:
  `.pytest_cache/r1-s1-t3b-d3c3-*.txt`; smoke artifacts include `server.log`.
- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2398 passed,
  158 skipped**, 44 warnings, 305.25s, on the final reviewed source/tests.
  Skips include unconfigured PG variants and SQLite variants of PG lock inspection.

## Diff self-review (2026-09-24)

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus matching/store.py,
new regression/smoke files and MATCHING.md. Original store copy is in
`.pytest_cache/d3c3-start`; prior uncommitted work is preserved.
Specification review mapped every acceptance item to code and behavioral checks:
atomic rollback/retry, strictly shrinking attempted set, preserved rank snapshot,
top-N refill before audit only, final counts and existing API empty contract.
Correctness review traced both callers (direct match route and dashboard.board),
ownership rejection before pool/audit work, unchanged stored consent policy and
pure ranking engine, fresh sessions after rollback and commit, parameter-bounded
existence queries, survivor audit rank/score consistency and unrelated failures.
No new table, schema version, API field, frontend handler or private-payload log.

Documentation finding (MATCHING.md HTTP section): it still claimed empty pools
return 422. Corrected to the existing 200/reason contract, verified on both routes.
Final existence reads are snapshot boundaries, not an atomic whole-response
erasure guarantee; pools over 500 IDs use multiple bounded reads. Audits describe
the committed ranking, so after-commit removal may leave gaps in audited ranks.
No acceptance-blocking finding remains. This is self-review, not independent
review. Required checks completed on the final source/test state.

Working data/veritas.db remains SHA256
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
No working-data migration/deletion, deployment or live-provider validation.
Exact next task: **R1-S1-T3b-D3d** (cross-store erasure ordering
and post-fingerprint response review). D3c and all its children are done;
D3/D/T3b/T3/F05/R1-S1-Q remain open.
