# Veritas unused-feature removal report

Completed on 17 November 2026 on `simplify/cut-unused`. No PR or deployment was made.
The historical remediation queue remains closed.

Counts below are passed / skipped. Earlier rows through 2.5 come from the handoff;
commit statistics were checked against Git. A `+ 1 rerun` is a failed-under-load
case that passed unchanged alone, not an additional distinct test. Documentation-only
steps did not rerun the suite; their prior count is carried forward.

| Step | Commit | Files changed | Lines added / removed | Suite before | Suite after |
|---|---|---:|---:|---|---|
| 0.1 Baseline | main `7c30821` | 0 | +0 / -0 | owner expected about 4470 / 1227 | 4599 / 1347 |
| 0.2 Instructions | `d9069a6` | 3 | +50 / -163 | 4599 / 1347 | unchanged; docs only |
| 1.1 Retired delivery docs | `55960de` | 28 | +75 / -31740 | 4599 / 1347 | unchanged; docs only |
| 1.2 Sprint smokes | `d74fa4d` | 82 | +33 / -12504 | 4599 / 1347 | 4535 / 1347 |
| 1.3 respx | `d959d38` | 2 | +0 / -2 | 4535 / 1347 | 4535 / 1347 |
| 1.4 Unused model settings | `f477404` | 4 | +5 / -17 | 4535 / 1347 | 4534 + 1 rerun / 1347 |
| 2.1 Signal quality | `e40518f` | 28 | +15 / -2236 | 4534 + 1 rerun / 1347 | 4452 / 1347 |
| 2.2 Training, export, search | `2092d44` | 32 | +79 / -2115 | 4452 / 1347 | 4354 / 1235 |
| 2.3 Rights queue | `903641b` | 35 | +86 / -4055 | 4354 / 1235 | 4182 / 1137 |
| 2.4 Profile intake, curation, documents | `0860457` | 111 | +248 / -11458 | 4182 / 1137 | 3700 / 907 |
| 2.5 Dashboard/cards | `2b38a9c` | 15 | +54 / -543 | 3700 / 907 | 3689 / 907 |
| 2.6 Cross-company records/reputation | `7006d03` | 60 | +241 / -2560 | 3689 / 907 | 3620 / 907 |
| 3.1 Compensation and duplicate match route | `61bf729` | 59 | +149 / -2040 | 3620 / 907 | 3581 + 1 rerun / 907 |
| 3.2 Curation UI | included in `0860457` | included in 2.4 | included in 2.4 | included in 2.4 | included in 2.4 |
| 3.3 Company reliability controls | `3d6d4c5` | 18 | +39 / -180 | 3582 / 907 | 3580 / 907 |
| 3.4 Resume writing-style step | `9273286` | 39 | +122 / -610 | 3580 / 907 | 3539 + 1 rerun / 907 |
| 4 Retired tables | `be85705` | 25 | +283 / -392 | 3540 / 907 | 3540 / 907 |
| 5 Sequential evaluation | `cf95653` | 10 | +72 / -42 | 3540 / 907 | 3543 / 907 |
| Finish: docs and final checks | this commit | 17 | +421 / -755 | 3543 / 907 | 3543 / 907 |

The final **sequential** suite passed **3543**, with **907 skipped**.
Postgres variants were not run: `DEE_TEST_DB_URL` was unset throughout. Provider
tests used the existing offline fakes, and the production walkthrough used provider-disabled deterministic fallbacks; these results do not establish live-provider
or deployed-host behavior.

## Final footprint

| Measure | main | Final |
|---|---:|---:|
| API operations | 102 | 75 |
| ORM tables | 35 | 26 |
| Settings fields | 236 | 185 |

Final source comparison with main: **369 files changed, 1694 insertions(+), 71134 deletions(-)**. The table count excludes Alembic's
version table. Default feature view: `core_v1` version 4, 23 named features. Evaluation:
eight fixed steps. Retention: seven classes, ten targets. LangGraph and langchain-core
were removed from both dependency manifests.

## Validation and scope

- 2.6: full suite 3620/907; edited smokes 72/72, 11/11, 21/21 and 62/62;
  real Chrome evaluation/portal 50/50, plus UI bindings.
- 3.1: targeted backend 230 passed; disclosure/erasure 20 passed, 16 skipped;
  API smoke 68/68, restart 11/11, Chrome role/report journey 27/27; Node evaluation 64/64.
- 3.3: targeted backend 82 passed and auth guard 8/8; Node org administration 81/81;
  combined operator/browser 36/36, org browser 25/25, API/restart 68/68.
- 3.4: targeted backend 346 passed; Node evaluation/screening checks 64/64 and 146/146; factual-risk smoke 62/62 and real Chrome journeys 50/50, 21/21 and 27/27.
- Phase 5: all 29 normalized report/error outputs matched the prior LangGraph runner across both domains, existing fixture text, PDFs, fake GitHub/model evidence and invalid inputs; regression tests cover partial updates, concurrent requests and error propagation. Those same outputs also matched with imports of both removed libraries blocked.
- Surviving route order and OpenAPI were compared at each route removal. Only the
  intended routes/schemas disappeared; board `comp` was removed, `comp_band` retained.
- Migration `0031_cut_unused_tables` was tested upgrade/downgrade/upgrade on scratch
  SQLite, including populated dependent tables, restored empty schemas and preserved
  candidate, organisation and consent data. Old migration files were unchanged.
- Phase 4: targeted migration/model/lifecycle checks 54 passed, 27 skipped. All 11 edited scripts passed: organisation browser 25/25, operator browser 29/29; backend smokes 74/74, 151/151, 62/62, 22/22, 24/24, 11/11, 68/68, 18/18 and 20/20.
- Final UI checks passed: 578 bindings across 18 states, syntax for all nine frontend scripts plus the inline template, and 705 tests across all seven Node UI scripts. Real Chrome journeys passed. The production
  composition walkthrough passed 26/26 checks: company signup, job creation,
  resume upload, materialization, ranked board, candidate login/portal, typed interview
  start/answer/finish and every remaining nav item at `/ui/`.
  Synthetic walkthrough artifacts: `C:\Users\REVANP~1\AppData\Local\Temp\veritas-final-walk-1e_w09tf`.
- No operation opened, migrated or overwrote `data/veritas.db`.

## Adjustments, retained code and owner review

- 3.2 was folded into 2.4; no duplicate commit was made. Compensation and dashboard
  docs were removed in 3.1. Board tests moved into matching ownership.
- Kept auth, CSRF, tenancy, ranking, coverage, disclosure, erasure and refusal assertions
  were retained. Probes moved from removed ledger reads to verification assurance,
  from the duplicate match route to the board's `match` response, and from reliability
  writes to kept organisation create/key-rotation operations. Removed-route-specific
  validation and duplicate route variants were removed with their endpoints.
- The dependency-parser floor changed from 15 to 14 after the two direct dependencies were removed; exact pins, supported ranges, dependency-set equality and extras checks remain intact.
- The previously unlisted admin-route floor changed 27 to 26 with reliability removal;
  every surviving route is still checked for its auth dependency. Other pins were
  adjusted only for their intended smaller surfaces.
- An overly broad intermediate compensation-settings deletion was corrected by restoring
  the neighbouring grievance-contact settings. No intended step was reverted or skipped;
  the optional sequential runner was completed after comparison with the prior runner.
- Owner baseline expectation differed: observed 4599/1347 versus about 4470/1227
  (129 more passes and 120 more skips). The observed baseline was preserved.
- `pdf_b64_to_document` remains unused, as instructed, to avoid changing the bounded
  PDF worker. Decide separately whether to remove it.
- Feature consent masking remains intact but dormant in the shipped catalog; verification and interview disclosure gates remain active. Its tests use
  gated probe features. `FeatureSource.LEDGER`, `REPUTATION` and every `ConsentPurpose`
  value remain. Decide separately whether to retire that mechanism.
- 16 smoke scripts remain, a larger set than the owner's original list. In
  particular `smoke_r4_s1_t1a.py` supplies shared factories/lifecycle helpers to kept
  checks. Further retirement needs a separate dependency review.
- The handoff reported load-sensitive `real_lock` and `batch_recovery` checks passing
  alone. This continuation observed
  `test_batch_terminal_sql_owns_settlement_without_replay[sqlite-rollback-counts]`
  fail an eight-second wait in the 3.1 parallel run and pass unchanged alone
  (1 passed in 3.70 seconds). Its test and execution-pool budgets were not loosened. Browser harnesses gained positive render/click assertions so navigation waits for the actual card/form; no outcome assertion or timeout was weakened.
- In the 3.4 parallel run, `test_batch_admission_retains_slots_without_late_provider_continuation[sqlite-rollback-next]` failed an eight-second wait and passed unchanged alone (1 passed in 4.70 seconds). The role/report browser harness also encountered a render wait race and a bounded-worker 503 under concurrent load; after synchronizing on the actual card and moving the reference read before UI navigation, the quiet rerun passed 27/27. No application pool limit, refusal code or timeout was changed.
- The first final walkthrough used a fixture without enough extracted profile/probe questions and correctly received 422 (two questions available, minimum three). The rerun used the existing richer senior-profile fixture; no minimum, budget or application behavior was changed.
- The final navigation probe replaced a template inline-style locator with exact visible headings/empty states. All 17 nav items then passed; no application change was needed.
- OneDrive loose-object repairs rebuilt only blobs whose staged hash matched the
  working file; subsequent checks and phase pushes succeeded.
