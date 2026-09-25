# R1-S1-T3b-D3d2b - Profile-source erasure refusal and response review

Status: done (2026-09-24). Parent: [D3d2](R1-S1-T3b-D3d2.md). Prerequisite: D3d2a.

Entry points: `profile_sources/service.py`, `profile_sources/store.py`, source
routes in `api/routes.py`, related source tests and `_capture_unmapped` callers.
Initial trace only: GitHub fetch and LinkedIn parse follow an early candidate
read. `save_signal` commits a candidate-FK row without erasure translation;
the service returns its in-memory signal after save. Curation capture precedes
save and has a separate lifetime.

Bounded acceptance (before implementation): both source POST callers and their
store writes. Preserve existing LookupError compatibility with narrow domain
subclasses; routes map only those known erasures to safe 404 responses.
- Reproduce candidate erasure during fetch/parse and before/after signal commit;
  define safe refusal for observed absence and preserve unrelated errors.
- Demonstrate no orphan/recreated signal after erasure, unaffected other subjects,
  unchanged source/ownership behavior and permitted fresh ingestion. Separate
  durable-write protection from response snapshots after the final read.
- Trace curation capture's stored fields/ownership and established retention
  policy; do not silently delete shared vocabulary or invent identity links.
- For code changes: red/green tests, full pytest, relevant scratch migrated
  HTTP/restart journeys, SQLite/PostgreSQL controlled connections, migrations
  where applicable, diff self-review and static/documentation checks. Use fake
  providers; do not label them live-provider validation.

- Roll back a failed insert before confirming candidate disappearance; translate
  only FK failures, leaving unrelated constraints/provider/lookup failures intact.
- After save, one fresh joined read checks the candidate and the exact returned
  storage row ID (distinct from the signal JSON ID). Candidate disappearance
  takes precedence; source-only deletion returns a safe source-not-found refusal.
  Wrong ownership is an error. No locking across later response delivery.
- Cover both adapters at initial service read, fetch/parse, flush and after
  commit; fresh ingestion for a surviving/new candidate, unaffected subjects,
  unavailable-source 200 behavior, append-only history and admin-only access.
  SQLite/PG controlled connections cover both write/delete orders and PG locking.
- No schema, consent/scoring or frontend change. List/portal aggregate reads
  retain their existing snapshot behavior; their combined response review is
  D3d2d, not a claim of whole-response atomicity from this write-path fix.

Curation trace: `unmapped_terms` stores normalized key, raw display name, source
types, counts/times and reviewer decisions. It has no candidate identity/FK, and
CURATION.md/models/store explicitly retain shared terms after candidate erasure.
Capture runs before signal persistence and may therefore survive a refused write.
Preserve and regression-test that policy; absence of a candidate ID does not
prove raw skill names contain no personal data. Correct the documentation's
stronger claim; do not delete shared terms or infer ownership here. Any broader
input/retention policy remains an explicit residual for combined review.

Login-state ordering and combined closure remain D3d2c/d. D3d2 and higher parents
stay open until every required child and validation gate is complete.

## Review and evidence

Self-review: HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus bounded diffs
against `.pytest_cache/d3d2b-start`: source store/service, two POST handlers,
new regressions/HTTP smoke and PROFILE_SOURCES.md/CURATION.md. Specification
mapped rollback/refusal, exact storage ID/ownership, both adapters, recovery,
snapshot limits, unavailable sources and retained curation to behavioral checks.
Correctness traced both save callers, exception compatibility, dialect FK codes,
session rollback/closure, unchanged route authorization and raw taxonomy fields.
Medium review finding: implicit GitHub handle resolution could turn candidate
erasure into a 400 input error. Added a fresh absence check before that fallback
and a direct API regression. No acceptance-blocking finding remains in this
bounded write-path contract. No independent review or whole-portal claim.

- Initial red: `.resume/Scripts/python.exe -m pytest -q tests/test_profile_source_erasure.py --tb=short`:
  **12 failed, 4 passed, 6 skipped**, 1 warning, 7.05s. Raw FK errors, initial
  read/fetch/flush HTTP 500 and stale after-commit/source-only HTTP 200 reproduced.
- First green focused: **41 passed, 6 skipped**, 1 warning, 6.04s (new file plus
  source store/service/API and curation capture). Expanded pre-review focused:
  **76 passed, 7 skipped**, 1 warning, 8.51s (adds curation store/service and
  LinkedIn parse/transform). Final state results follow.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d2b.py`: initial migrated
  SQLite HTTP/restart **29/29**, before the implicit-handle adjustment.
- Compilation and `git diff --check` passed before that adjustment. Node binding
  command was attempted but remains unavailable; no frontend assets/handlers
  changed and no browser execution is claimed.

- `.resume/Scripts/python.exe .pytest_cache/check_d3d2b_implicit_red.py` loads
  only the saved pre-task handle resolver in memory: **1 failed, 30 deselected**,
  1 warning, 5.40s; 400 instead of 404 reproduced. No working source replacement.
- Final focused command:
  `.resume/Scripts/python.exe -m pytest -q tests/test_profile_source_erasure.py tests/test_profile_sources_store.py tests/test_profile_sources_service.py tests/test_profile_sources_api.py tests/test_curation_capture.py tests/test_curation_store.py tests/test_curation_service.py tests/test_linkedin_parse.py tests/test_linkedin_transform.py --tb=short`:
  **77 passed, 7 skipped**, 1 warning, 20.14s. Six unconfigured PG variants plus
  the SQLite variant of PostgreSQL lock inspection skipped.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d2b_postgres.py`:
  broad PostgreSQL 18.6 **96 passed, 1 skipped**, 16 warnings, 112.43s. Adds
  migrations to the focused files. Includes controlled FK deletion blocking
  (`pg_blocking_pids`), both orderings and unrelated NOT NULL failures. Migration
  up/down/up and HTTP/restart **29/29** passed. Run began before the handle
  adjustment; final-source supplement follows. No full PG suite claimed.

- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d2b_final_postgres.py`:
  final source/tests **52 passed, 1 skipped**, 1 warning, 72.39s; source erasure,
  source service/API and curation capture. Migration up/down/up and final PG
  HTTP/restart **29/29** passed. Both disposable PG clusters stopped cleanly.
- Final SQLite repeat: `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d2b.py`:
  **29/29**, both adapters at fetch/flush/commit/source-only removal, fresh
  candidates/ingestion, snapshots, retained histories/curation, unavailable 200,
  malformed transport, org-only authorization denial and persisted restart reads.
- Final compilation and `git diff --check` passed again.

- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2488 passed, 170
  skipped**, 44 warnings, 381.06s on final reviewed source/tests.
- `.resume/Scripts/python.exe .pytest_cache/check_d3d2b_docs.py`: local
  links/IDs/status/whitespace passed across **12 documents**. Working DB SHA256
  remains `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

Logs: `.pytest_cache/r1-s1-t3b-d3d2b-*.txt`. Synthetic providers only; no live-provider
or worker-crash claim. No working-data migration/deletion or deployment. Next:
**R1-S1-T3b-D3d2c**. D3d2 and higher parents remain open, including aggregate-read
response windows and raw curation-display-name policy review in D3d2d.
