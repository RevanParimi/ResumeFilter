# Current handoff

Updated: 2026-09-27. Project: Veritas resume evaluation / talent platform.

## Start here

**Next development task: R1-S1-T3b-D3d2c3 - redemption across erasure and login closure.**
Read [WORKFLOW.md](delivery/WORKFLOW.md), the T3 section of [PI-R1](delivery/PI-R1.md),
[the c3 brief](delivery/tasks/R1-S1-T3b-D3d2c3.md) and its
[login parent](delivery/tasks/R1-S1-T3b-D3d2c.md). Trace committed consumption,
principal establishment and session creation against erasure; define bounded
acceptance before implementation. Preserve fresh signup, single use, generic
refusal, all-plane cleanup and unrelated principals. Compose c1/c2 evidence.
Use synthetic capture/null email and disposable storage only.

One bounded development task per session. D3d2c1/c2 are done; c3 redemption
and D3d2d combined review remain open, as do T3/F05/R1-S1-Q. Combined review must
include source-list/portal aggregate response windows and curation display-name
retention. [FEATURE_STATUS.md](../FEATURE_STATUS.md) is the feature overview;
[archived evidence](delivery/archive/README.md) is read only when relevant.

## Latest work and evidence

- **D3d2c2 done:** sends reserve expiring tokens before delivery; erasure cancels
  them atomically, preventing late challenge activation. Short transaction locks
  preserve fresh signup, prior codes on send failure and unrelated principals.
  Full SQLite: 2517 passed, 188 skipped; focused PG: 167 passed, 2 skipped.
  Migrated issuance HTTP/interruption/restart: 34/34 on each backend; existing c1
  PG journey: 24/24. Migration up/down/up and cluster shutdown passed.
  Exact commands, warnings, acceptance and self-review are in the
  [leaf evidence](delivery/tasks/R1-S1-T3b-D3d2c2.md). Sent mail cannot be recalled;
  redemption remains c3. No browser, full-PG, live-provider or independent review.
  Existing summary/task files updated; no new Markdown file. Earlier clutter
  cleanup preserved and included with c2 in the user-authorized commit to main.
  Final local links/statuses, Python compilation, bindings and whitespace passed;
  working database hash below is unchanged.
- **Documentation organization committed/pushed:** `4c83cad` contains accumulated
  application fixes, feature summary and 12 archived completed child records.
- **User-requested clutter review (2026-09-26):** inventory of all 760 tracked
  files (156 Markdown before cleanup), targeted runtime caller tracing, merged
  diverged UI specs, condensed parent/PI summaries and removed competing workflow
  instructions. Findings and validation are in the existing
  [audit follow-up](CODEBASE_REVIEW_2026-09-07.md#follow-up-2026-09-26--repository-clutter-review).
  That review left application code, detailed leaf evidence and backlog unchanged.
  Checks passed for local links across 155 Markdown files, 34 task statuses,
  merged decisions, unchanged DB and whitespace; no application-test rerun.
  That follow-up is included with c2 in the user-authorized commit to main.

Working database SHA256 remains
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

## Test environment

Use `.resume/Scripts/python.exe`; full suite: `-m pytest -q --tb=short`.
CPython 3.13.11 and existing dependencies are in use. Portable PostgreSQL 18.6
metadata: `.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`; latest local runner:
`.pytest_cache/run_r1_s1_t3b_d3d2c2_postgres.py`. These ignored artifacts are not
portable setup guarantees. Each run must own a disposable cluster and stop it.
No .env edits or service registration. Remote authentication failure was not
rechecked. Fixtures use process DEE_TEST_DB_URL; shared teardown drops schemas
matching `s_%` (literal underscore). Never use the working database or print
credentials. Browser checks need their own environment; bindings are not a browser.

## Standing constraints and open risks

- Preserve data and prior work. Commit/push to main was authorized on 27 September;
  deployment, external messages and working-data/legacy-file cleanup are not.
- Historical feature timestamps may be shifted; repairs need an explicit policy.
- Final existence reads in training, matching, ingest, reports and sources are
  snapshots, not locks across delivery. Matching audits may retain pre-response
  rank gaps. No whole-response/whole-ingest guarantee follows from these fixes.
- Current consent/identity/verification-attempt races remain R1-S2; shared startup
  and resource simplification remain PI-R4. Older unresolved screening input pauses
  across tenants on erasure but keeps its original TTL; it is not immediately
  erased or permanently barred from fresh upload.
- Keep domain independence, deterministic fallbacks, advisory human review and
  tenant/consent isolation. Polished/AI-assisted truthful writing is not fabrication.
  Video scoring judges content, not appearance/emotion. Conversational video is
  still a recommendation, not a confirmed format preference.
- F01-F04 have qualified baseline fixes; F05-F16 remain open. Synthetic tests do
  not establish representative model quality. The [delivery plan](delivery/README.md),
  [baseline](delivery/BASELINE.md) and original audit own detailed traceability.
  [ROADMAP.md](ROADMAP.md) is history, not required end-to-end reading.
