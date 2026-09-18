# Baseline entering remediation planning

Recorded 2026-09-09 from the current project handoff, not rerun during planning.
Original audit: `docs/CODEBASE_REVIEW_2026-09-07.md`. Behavior explanations:
`docs/FEATURE_LOGIC.md`. Historical implementation detail: `docs/ROADMAP.md`.

| Completed fix | Evidence already recorded | Remaining qualification |
|---|---|---|
| F01 email/phone fallback | Foundations regressions prevent unfamiliar email binding and ambiguous phone selection | Asserted contacts are still identity hints; no persisted identity repair. R1-S2-T4 covers the remaining binding policy |
| F02 provenance isolation | Different candidates/claims no longer share vector retrieval evidence | Fetch-error polarity and unnecessary Chroma startup remain R2-S1-T3 / R4-S1-T2 |
| F03 feature snapshots | Shared batch timestamp and latest eligible per-candidate snapshots; search/match tests | Current-consent enforcement remains F06 |
| F04 login OTP safety | Conditional DELETE identifies one consuming caller; id-scoped SQL attempt increment; SystemRandom default | No PostgreSQL concurrent load evidence. Contact-verification path is separate and scheduled R1-S2-T3 |

- Audit suite: 2140 passed, 42 warnings, Python 3.13 in `.resume`, 340.90s.
- Foundations: 2148 passed, 42 warnings, 346.20s; focused 45 passed. Log:
  `.pytest_cache/foundations-suite.txt`.
- F04: 2155 passed, 42 warnings, 467.80s; focused auth/static-code suite 94
  passed. Seven new regressions observed failing before the fix. Guarded local
  static login-code behavior preserved. Detailed F04 record is in the roadmap.
- UI baseline: 402 bindings across nine states and JS syntax passed. This is
  not proof that mock screens are connected or that browser journeys passed.
- PostgreSQL, live providers, production load and representative model accuracy
  have not been established by these local results.
- F04 tests prove controlled single-consumer behavior in SQLite; they do not
  establish transaction behavior under actual PostgreSQL concurrency.
- Existing CI defines SQLite/Python 3.11–3.12, PostgreSQL and image jobs.
  Browser/CDP script exists but relies on Chrome and CDN internet assets.
- Existing modified `data/veritas.db` and other uncommitted work must remain
  intact. Do not print `.env` secrets or turn the working DB into a test fixture.

Known open cross-cutting limits: retained flywheel text, stale consent, malformed
provider/input handling, unreliable style/fabrication association, gamed interview
rubric, missing screens/delivery, duplicated resources, ingest/batch races,
blocking async routes, unbounded work, worker-local state, shallow readiness,
raw exception disclosure, incomplete dependency locking and unmeasured accuracy.
Each has a task mapping in `README.md`; none is closed by writing this plan.
