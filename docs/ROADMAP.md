# Veritas Roadmap — living plan (update every session)

> **New chat? Start here.** Read this file top to bottom, then open the spec:
> `docs/superpowers/specs/2026-07-06-veritas-talent-platform-design.md`.
> Work happens sprint by sprint: each sprint gets a spec/plan under
> `docs/superpowers/`, is built TDD-offline, and ends with `pytest -q` green
> plus a local smoke run. Update the status board + "Current state" section
> below before ending any session.

## ▶ Current state

- **Session 2026-08-22 (latest) — S9.2 MERGED to `main` at `2ad59f8`; PI-9's
  second sprint is closed. 2080 passing on the MERGED result, `smoke_s92`
  17/17, branch deleted. `main` is 33 commits ahead of `origin/main` and
  NOTHING IS DEPLOYED.**
  The merge was a clean fast-forward — `main` had not moved since the branch
  point — and the suite was re-run ON THE MERGE COMMIT, not just the branch.
  **THE UI'S REMAINING WORK WAS MEASURED, NOT ASSUMED, AND HAS NO BLOCKER.**
  Five screens are unwired, not three: `MOCK_SCREENS` in
  `frontend/Veritas.dc.html` names `evaluate`, `interview`, `adminorgs`,
  `adminusers`, `curation` — the board's "operator console" is three of them.
  A throwaway probe drove every one of their routes over real HTTP in the
  BROWSER's posture (session cookie + `X-CSRF-Token` + `Origin`) and got
  **12/12**: `require_api_key` has been session-capable since S8.2, so an
  operator cookie satisfies the admin gate and no new backend work is owed.
  The candidate-plane interview runner answers too — `POST /portal/interviews`
  returns a 422 that NAMES what the screen must do first ("only 2 question(s)
  available; 3 required. Add a resume or run a depth evaluation first").
  **THE BOARD'S "RE-RUN THE 36/36 CONTRACT SUITE" ITEM IS STALE.** No such
  script exists or ever existed — `git log --diff-filter=A` over
  `scripts/check_ui*` returns exactly three files, all still present. Its
  successor `check_ui_screening_contract.py` is **31/31 green**, bindings are
  **402/402**, and the org-signup 409 that was supposed to break it is handled
  (`frontend/api.js:143` maps it to `kind:"conflict"`) and covered by
  `tests/test_auth_org_name_taken.py`. The item can be struck, not worked.
  **⚠ ONE REAL GAP FOUND, AND IT IS S9.2'S OWN QUESTION ONE DOOR LATER.**
  `POST /evaluate` returns `extraction_coverage: null` — STRUCTURALLY, because
  `routes.py:521` calls `engine.evaluate(...)` without the argument the
  screening door passes at `screening/ingest.py:147`. `cross_field` falls back
  to `heuristic_profile(text)` (nodes/cross_field.py:31), the very extractor
  S9.2 fixed, so the instrument APPLIES to this path — it is simply not wired
  to it. Measured on the repo's own `tests/fixtures/genuine_genai_resume.txt`
  (976 chars): the heuristic profile is **0 experience, 0 education, 0 skills**;
  `cross_field` and `fabrication_risk` both honestly answer `insufficient_data`
  with zero findings; depth still reports **deep 0.81**. (CORRECTED 08-24: the
  `major_gaps / education_not_extracted` first reported here was a FALSE
  POSITIVE from the `b.com`-in-`github.com` bug below, not a dropped degree.
  The `/evaluate` gap itself stands — that door returns null coverage
  regardless.) This is the
  repo's signature defect shape (a rule at one entry point and not the other)
  and it lands on the INSTANT CHECK screen, the fraud-screen wedge's fastest
  demo path. Wiring that screen to `/evaluate` as-is ships a headline
  fabrication number that reads empty with no explanation. **Decide the scope
  before wiring it, not during.**
  **➤ NEXT: wire the five screens + local testing including the UI. GO-LIVE
  MOVES TO LAST** by the user's call this session — it happens only after local
  testing is finished, UI included.

- **Session 2026-08-20/21 — S9.2 (EXTRACTION COVERAGE) BUILT, REVIEWED
  AND REGRESSION-FIXED on branch `s92-extraction-coverage`. (MERGED the next
  session; see above.) Not pushed, nothing deployed. 1996 → 2080 passing, 21/21 mutants dead,
  `smoke_s92` 17/17, tree clean.**
  Spec `docs/superpowers/specs/2026-08-20-s92-extraction-coverage-design.md`,
  plan `docs/superpowers/plans/2026-08-20-s92-extraction-coverage.md` (14 tasks,
  all done), executed subagent-driven with a per-task review loop.
  **THE SPRINT ASKS THE QUESTION UNDERNEATH S9.1'S.** S9.1 asked whether the
  advisory numbers predict a human's judgment. This one asks whether they were
  computed from the resume **or from a hole where the resume used to be** —
  `src/app/candidates/coverage.py`, an advisory instrument comparing raw text to
  the extracted profile, plus `Report.extraction_coverage` (no migration:
  `ReportRow.body` is JSON).
  **FIVE SHAPES WERE MEASURED BROKEN BEFORE A LINE WAS WRITTEN**, and all are
  now closed: roles written as bullets → 0 experience entries; a `CAREER
  HISTORY` header → 0; a spelled-out `Bachelor of Technology` → 0 education; and
  `Programming Languages: Python, Java, Go` → a skill literally named
  `"Programming Languages: Python"`.
  **THE SYSTEM WAS BEHAVING CORRECTLY, WHICH WAS THE PROBLEM.** `cross_field`
  gates every check on having dated entries and honestly says
  `insufficient_data`; fusion excludes insufficient components rather than
  scoring them zero. So a dropped section made the headline fabrication number
  **quieter, not louder**, and the operator could not tell a fresher from a
  senior hire nobody screened. Six readers of `profile.experience` ran vacuously.
  **THE INSTRUMENT DOES NOT SHARE THE EXTRACTOR'S EYES**, enforced by an AST
  guard, because an evidence detector imported from the code being measured is
  blind exactly where that code is. Point the education check at `_DEGREE` and
  widening `_DEGREE` silently switches the check off.
  **SIXTEEN RULINGS were made mid-flight; the ones that changed the product:**
  R10 (a line containing `,;|·` is not a header — without it a bare skills list
  was stolen into a phantom header and the instrument reported `complete` on a
  resume whose skills were dropped) · R13 (`professional summary` is NOT an
  experience alias: `_experience` opens an entry for any dated line in its
  section, so prose reading "2015 - 2023" would manufacture a job with no
  employer — inventing a role is worse than missing one) · R14 (`bs`/`ms`
  dropped from the degree pattern; they match `MS Office` and `MS SQL Server` —
  **the implementer was right and the spec is still wrong**) · R15 (the skill
  label strip was DELETING real skill names: `Python: 5 years` → `5 years`).
  **THE FINAL WHOLE-BRANCH REVIEW RETURNED NOT MERGE-READY, AND WAS RIGHT.**
  Two Criticals: the bulleted-roles fix **fabricated employment entries** from
  dated achievement bullets under an undated role line (`'Led the'`,
  `'Delivered the'`, employer `None`) — R13's own argument arriving through the
  other door — and `blocks()` promoted single-token content lines to headers, so
  `KEY SKILLS` with one skill per line reported `complete`. Plus a false
  `contact_not_extracted` on anonymised resumes, because `_PHONEISH` matched
  `2019 - 2021` as a phone number.
  **THEN THE FIX WAVE INTRODUCED TWO MORE**, both caught by the scoped
  re-review: the tightened header gate blinded checks 3 and 5 on Title-Case
  headers (`Tech Stack` → `complete`), and a 6-word cap on role heads **silently
  dropped `Tata Consultancy Services` and `Larsen and Toubro Infotech`** — real
  roles lost, in an Indian-market product, invisible because §3.3 fires check 1
  only on a TOTAL drop.
  **THE RECURRING CAUSE, THREE TIMES: A PREDICATE CHANGE BROKE A SHAPE NO TEST
  COVERED.** Every coverage fixture put its evidence on lines carrying a comma
  or a year — exactly where the header predicate correctly returns False — so
  the suite never entered the region where the instrument was blind. That is
  S8.6's "every check fetched an asset, never the page" in a new sprint. The
  answer is `tests/test_coverage_shape_matrix.py`: a table-driven corpus of
  every shape S9.2 discovered, so the next predicate change must satisfy all of
  them at once.
  **FIVE VACUOUS TESTS WERE FOUND AND KILLED** across the sprint, including one
  named and documented for the exact property it did not test.
  **THE INSTRUMENT DECLARES ITS OWN LIMITS** (CANDIDATES.md "Known limits"):
  coverage detects TOTAL drops only, so a partial loss produces no gap; and
  `Key Skills` over a bare one-per-line list still reports `complete`.
  Contorting the predicate to catch it reopens the other two.
  **➤ NEXT STEP: the user's merge decision on `s92-extraction-coverage`.** Then
  the still-owed ultra review on `s86-review-target` (user-triggered; six
  session-limit failures now). PI-8's remainder is unchanged — the user-gated
  go-live in `DEPLOY.md` including the Railway cron, plus alerting thresholds on
  `/metrics`, the only unbuilt technical item on the board. CI has still never
  been read. **Open for the next session:** six of the thirteen shape fixtures
  are under `coverage_min_chars: 200`, so the matrix exercises them only with
  the knob lowered (R16, deferred); and spec §5.3 still lists `bs`/`ms`, which
  R14 deliberately did not ship.

- **Session 2026-08-18/19 — S9.1 COMPLETE, and the S8.6 review fixes
  merged. `main` carries both. 1854 → 1989 passing, `smoke_s91` 15/15,
  `smoke_s43` 8/8, 15/15 mutants dead. Nothing deployed.**
  **THE OWED ULTRA REVIEW IS STILL OWED, and has now failed FOUR times** on
  "You've hit your session limit" (2026-08-14, twice on 08-18, once on 08-19).
  Across roughly forty angle-agent launches, **ONE has ever produced output** —
  the Reuse angle on 08-18. Target `s86-review-target`; S8.6 remains
  **unreviewed for correctness**, and retrying costs quota without result.
  **THE ONE SURVIVING ANGLE'S 8 FINDINGS ARE ALL FIXED AND MERGED.**
  Two were silent-failure shapes: `_UNADVERTISED_PATHS` hand-copied four doc
  paths out of `PUBLIC_PATHS` (now derived from `app.docs_url` et al — and
  four of its five entries were **already dead**, because FastAPI registers
  docs with `add_route`, a starlette `Route`, while `_iter_api_routes` filters
  on `APIRoute`); and two test files hand-rolled a flat Mount scan **in the
  same branch that added `_mount_paths()`**, whose docstring calls flat scans
  broken — measured, a mount nested in an included router is seen ZERO times.
  The other six became `scripts/_smoke.py`, the one smoke harness: `Smoke`
  (was 8 copies), `wait_healthy` (21), `base_env` (33), `client` (33),
  `uvicorn_argv` (~30), `boot_until_exit` (2). A drift guard over all 35
  scripts fails if anyone re-rolls one.
  **AND THE SHARED `base_env` CAUGHT A SMOKE BILLING A LIVE VENDOR.**
  `smoke_s43`'s docstring has said "LLM-free" since S4.3; it inherited the real
  `DEE_OPENROUTER_API_KEY` from `.env` and logged `"llm": "OpenRouterLLM"` on
  `main`. Its ranking half had ALWAYS built `Settings(openrouter_api_key="")`
  itself — the key was pinned on one door and not the other, this repo's
  signature defect once more. With both doors closed, 4 of 8 checks failed and
  the other 4 were passing on INSERTION ORDER over three candidates whose
  `years_experience` was None. Cause: one character per fixture —
  `extractor._experience` skips `_BULLET` lines because under a bullet a dated
  line is a DUTY, so `- Engineer, Acme (2013 - Present)` yielded zero entries.
  De-bulleted, all eight assertions are real and green.
  **STILL OPEN, and now a product decision:** the heuristic extractor ignores
  dated role lines written as bullets, which is a common resume shape. That is
  an S1.1 call with a wide blast radius, deliberately not made inside a smoke
  fix.
  **THE CORRECTNESS PASS WAS RUN BY HAND (2026-08-19) AND FOUND ONE, ON THE
  GO-LIVE PATH.** `/code-review ultra` was rejected a FIFTH time -- not on
  quota this time but on SIZE: with `main` 25 commits ahead, the diff it
  computed was 273 files / 13,058 lines against a 500-file / 8,000-line
  ceiling. The real S8.6 diff is 36 files / 4,832 lines (1,737 code, 3,095
  docs), reachable from the new `s86-review-base` branch at the fork point
  `8ae08cb`. So the pass was done by reading, over ~340 lines of production
  code.
  **DEPLOY.md step 7 sent the operator to a 404.** It says "Sign up through
  the UI at `/ui`"; measured, `/ui` 307s to `/ui/` which answered **404** --
  StaticFiles runs html=False with no index.html (the design tool emits
  `Veritas.dc.html`) and the allowlist keys on the first path segment, which
  Starlette hands over as `"."` for a directory. **No document anywhere named
  the working URL.** Fixed at `13edb33`: `/ui/` serves the entry document by
  NAME rather than via html=True, which would have started serving an
  index.html out of any future subdirectory -- a second public-surface rule
  nobody wrote. DEPLOY.md is deliberately UNCHANGED: the fix makes its
  existing instruction true instead of rewriting the runbook to match a broken
  surface.
  **IT SURVIVED FOUR REVIEW PASSES BECAUSE EVERY CHECK FETCHED AN ASSET** --
  the smoke's `the_ui_is_served_same_origin`, `test_ui_mount`'s
  unauthenticated-access test and the CI image job all asked for `api.js`.
  Proving a JavaScript file is reachable is not proving the UI loads. That is
  S8.6's own review lesson 7 recurring **inside the fix written for it**. The
  new guard reads its paths OUT OF DEPLOY.md, so rewording step 7 moves the
  test with it. 1991 -> 1996 green, `smoke_s86` 27/27 -> 28/28.
  **Also pinned: the trailing slash is load-bearing.** The shell references its
  script relatively (`src="./api.js"`), so from `/ui/` that resolves to
  `/ui/api.js` and from `/ui` it would resolve to `/api.js`, which is not
  mounted.
  **BRANCH HYGIENE:** `s86-review-fixes`, `s43-offline-assertions` and
  `s91-signal-quality` merged and deleted. **`s86-review-target` SURVIVES ON
  PURPOSE** — it is the frozen diff the owed ultra review targets, and deleting
  it would take the review with it. `s84-dev-login-echo` still carries its one
  unmerged commit (a local-only login-code echo), left alone for the same
  reason as before: merging something that echoes login codes needs a review
  first.
  **➤ NEXT STEP: the ultra review on `s86-review-target` (user-triggered), then
  S9.2. PI-8's remainder is unchanged — the user-gated go-live in `DEPLOY.md`
  including the Railway cron, plus alerting thresholds on `/metrics`. CI has
  still never been read: `main` was pushed for the `image` and `postgres` jobs
  and `gh` is not installed here.**

- **Session 2026-08-17/18 — PI-9 OPENED. S9.1 (signal quality
  harness) SPECCED, PLANNED, and PARTLY BUILT on branch `s91-signal-quality`.
  PAUSED MID-SPRINT at `35dcd6e` on a session limit, 1875 green. NOT merged.
  `main` was PUSHED for the first time since S8.4a.**
  **➤ RESUME AT TASK 5.** Ledger:
  `.superpowers/sdd/2026-08-17-s91-signal-quality-harness/progress.md` (it
  holds every ruling and the exact stop point; it is GIT-IGNORED, so if it is
  gone, recover from `git log` plus this entry). Spec
  `docs/superpowers/specs/2026-08-17-s91-signal-quality-harness-design.md`,
  plan `docs/superpowers/plans/2026-08-17-s91-signal-quality-harness.md`
  (13 tasks; 1 and 2-4 done, 5-13 pending).
  **THE SPRINT PROCEEDS DESPITE PI-9'S OWN GATE, and the gate is answered by
  construction rather than by waiting.** Gap-analysis v2 §5 parked calibration
  on "real orgs submitting outcomes" because "a harness measuring test fixtures
  would have been actively misleading". That argues against a harness that
  emits a number no matter what it is fed — so this one *cannot*: three
  refusals (insufficient samples · degenerate class · label-kind mismatch)
  return a type that carries **no metric fields at all**. Same posture as
  S7.1's `government_id` and S7.2's EPFO: ship the mechanism, make the missing
  input a refusal.
  **TWO PRIOR FRAMINGS DIED ON CONTACT WITH THE CODE.** (1) §3.3's
  "metrics over the S4.2 × S4.4 join" — `FeatureVector` is keyed
  `(candidate_id, as_of)` with EXACT matching while `outcomes` is keyed by
  `report_id`, so that join needs a nearest-before rule and a tolerance window.
  The **Report body** already carries every signal at its point in time and is
  the artifact the human actually saw, so it is both simpler and more correct;
  the harness never touches `ml_feature_vectors`. (2) "the ledger is the ground
  truth" — S8.5 shipped an org door writing to `outcomes`, and the GTM keeps
  the ledger off the pitch, so a ledger-only harness would still be empty
  **after** the launch it was gated on.
  **THE LOAD-BEARING IDEA IS THAT THE LABEL SEAM CARRIES SEMANTICS.**
  `OutcomeLabel` is a FRAUD vocabulary, `InterviewOutcome` a HIRING one.
  Scoring `depth_score` against `VERIFIED_FABRICATED` is a category error that
  would still produce a plausible AUC — so signals declare the `LabelKind` they
  can be scored by and mismatches REFUSE. Nine fraud signals measurable today;
  the three `depth.*` correctly report nothing until ledger data exists.
  **⚠ THE PLAN'S OWN REFERENCE CODE HAD A BUG THE REVIEW CAUGHT.**
  `calibration_curve` computed `int(s / width)` with `width = 1.0/bins`, which
  misplaces exact tenths at the DEFAULT `bins=10` (`0.3/0.1 =
  2.9999999999999996` → bin 2). Every test used `bins=4`, whose width is an
  exact binary fraction — so the fixtures were green and **the default argument
  had zero coverage**. This is the "rule holds at one door, not the other"
  shape with the second door being a *default parameter*. Fixed to
  `int(s * bins)`, pinned by a `bins=10` test, verified by execution.
  **⚠ A FIX REPORT CLAIMED A TEST RUN IT HAD NOT DONE** — "Expecting: 1875
  passed" instead of output. Re-run by the controller: 1875 is right, but a
  predicted result is not evidence.
  **⚠ THE SESSION LIMIT KILLED THE RE-REVIEWER MID-FLIGHT** (resets 10:20am),
  the same limit that killed nine of ten agents in the S8.6 review. That fix
  was verified by the controller executing the code instead of by a second
  agent — recorded as ruling R11, and the only task-review gap on the branch.
  **THE OTHER OPEN RULING TO CARRY INTO TASK 7: R1.** The plan passed
  `consent_allowed=True` hardcoded into `build_label`; that is a consent
  bypass, and `LedgerLabelSource` must call
  `materialization_consent(candidate_id, at=report.created_at)` instead.
  **`origin/main` IS NOW CURRENT** (`a1b34a1..9ac59b9`, 91 commits) — pushed so
  CI could finally run the `image` + `postgres` jobs, which are the only things
  that can execute S8.7's `COPY src/app` and `PYTHONPATH=/srv/app/src`.
  **CI RESULT NOT YET READ** (`gh` is not installed here — check the Actions
  tab). Branch `s86-review-target` was pushed as a review target: a synthetic
  commit whose tree is byte-identical to `6f19d32` parented at `8ae08cb`, so
  its diff IS the S8.6 range (36 files, 4,679 insertions). **The owed S8.6
  ULTRA review is still owed** — run `/code-review ultra s86-review-target`,
  then delete that branch. Nothing deployed.
- **Session 2026-08-15/17 — S8.7 BUILT AND MERGED: `app/` →
  `src/app/`, a PURE MOVE. `main` is at `d0d8b56`. 1852 → 1854 passing (the
  two new guards), ALL TWENTY SMOKES GREEN, bindings 402/402 · contract 31/31
  · browser 19/19. NOT PUSHED. Nothing deployed.**
  The suite and the smokes were re-run **ON THE MERGE COMMIT**, and
  `git diff s87-src-layout HEAD` is empty — `main` never moved while the
  branch was built, so the merge tree is byte-identical to the tested tip and
  the evidence above is the merge's, not just the branch's.
  Spec `docs/superpowers/specs/2026-08-15-s87-src-layout-design.md`, plan
  `docs/superpowers/plans/2026-08-15-s87-src-layout.md`.
  **THE OPEN DECISION IS SETTLED: the package KEEPS the name `app`.** The user
  declined the `veritas` rename. It buys nothing for the sprint's stated goal —
  `/code-review ultra src/` scopes identically either way — and the "pay the
  disruption twice" argument does not survive inspection, because the rename is
  *cheaper* after this move than before it. So 1,489 import statements across
  368 files are untouched, and the diff is nine files rather than every Python
  file in a sprint whose whole justification is reviewable diffs.
  **THE ROADMAP'S OWN TOUCHPOINT LIST WAS AN UNDERCOUNT — six listed, nine
  real — and all three extras fail SILENTLY.**
  **⚠ EXTRA 1 — `tests/test_metrics.py`'s METRIC-NAME SCAN WOULD HAVE GONE
  VACUOUS.** `root = parent.parent / "app"` was absent from the list. `rglob`
  over a directory that no longer exists yields nothing, so
  `test_every_declared_metric_has_a_call_site` keeps passing while checking
  **nothing at all** — the guard that caught four declared-inert metrics in
  S8.3a would simply have stopped working, without ever going red. Its own
  backstop (`test_the_call_site_scanner_can_actually_find_something`) is what
  makes this a red test instead of a hole.
  **⚠ EXTRA 2 — `tests/test_model_registration.py` BUILDS A DOTTED NAME FROM A
  PATH.** Only the `rglob` base is obvious; `rel = path.relative_to(ROOT)` is
  the one that bites, emitting `src.app.rights.models` — matching nothing in
  either import list, so every module reads as missing.
  **⚠ EXTRA 3 — THE CI POSTGRES JOB WOULD HAVE FAILED ON THE NEXT PUSH, AND NO
  LOCAL RUN COULD SEE IT.** Its "migrations up/down/up" step is a bare
  `python -` heredoc: no pytest, so pyproject's `pythonpath` does not apply,
  and CI installs only `requirements.txt`, **which declares no project**
  (verified — the only matching line is a comment). `sys.path[0]` is the repo
  root, which no longer holds `app/`, so `alembic/env.py`'s `import
  app.candidates.models` raises. Locally invisible because the venv's editable
  `.pth` puts `<repo>/src` on `sys.path` for **every** process; both sides
  measured. Fixed with `PYTHONPATH: src` on the job. **This is the third time a
  path fact was true in one execution context and false in another** — and CI
  has not run since S8.4a, so nothing would have contradicted it until a push.
  **THE IMAGE MIRRORS THE REPO RATHER THAN FLATTENING.** `COPY src/app ./app`
  was the tempting one-liner — the container keeps its shape and needs no
  `PYTHONPATH` at all — and it would leave `migrate.py`'s `parents[3]` at
  `/srv` instead of `/srv/app`: `alembic.ini` not found, **at runtime, after
  the container reports itself started**. Same failure class as S8.6's missing
  `frontend/`. So the image is `/srv/app/src/app/...` with
  `ENV PYTHONPATH=/srv/app/src`, and `CMD`/`railway.json` still say
  `app.main:app`, byte-identical.
  **THE COMMIT DISCIPLINE HELD, and cost one deliberately red commit.**
  `3049119` is `git mv` alone — 169 renames, zero other entries, and the tree
  does **not** import at that commit (measured: `pytest -q` dies in conftest
  with `No module named 'app'`). Verified afterwards that `git log --follow
  src/app/core/migrate.py` still traces back to its S8.1 creation.
  **NOT PROVEN, said plainly:** the container. This machine has no Docker and
  the `image` job is push-only, so the mirrored `COPY` and the `PYTHONPATH` are
  both **unexecuted**. `tests/test_image_contents.py` proves the Dockerfile and
  `.dockerignore` agree about `src/app`; it does not prove the container
  imports. `DEPLOY.md` §0 now says so.
  **➤ NEXT STEP: the only things left in PI-8 are the user-gated go-live
  (`DEPLOY.md`, including the Railway cron for the retention sweep) and the
  still-owed ULTRA review. After that, PI-9 (calibration harness).**
  **BRANCH HYGIENE:** `s87-src-layout` merged and deleted. `s84-dev-login-echo`
  still survives with ONE unmerged commit (a local-only login-code echo), left
  alone for the same reason as before — merging something that echoes login
  codes needs a review first. It is again the only branch left.
  **On that review: S8.7 did NOT cost it.** The range `8ae08cb..6f19d32` is
  fixed, so its diff is frozen and commits landing after it cannot disturb it.
  The roadmap's earlier "do S8.7 after the review" caution applies only to a
  review invoked with **no base**, which diffs against `origin/main` (~80
  commits behind) and blows the 12,000-line ceiling regardless. Pass the range.
- **Session 2026-08-14 — THE OWED S8.6 REVIEW, PARTLY RUN. TWO MORE
  REAL DEFECTS, both fixed and MERGED at `6f19d32`. 1850 → 1852 passing,
  `smoke_s86` 27/27. NOT PUSHED. Nothing deployed.** The merge tree is
  byte-identical to the tested branch tip (`git diff s86-review-fixes-2 HEAD`
  is empty — `main` never moved), so the evidence above is the merge commit's,
  not just the branch's.
  **⚠ `/code-review ultra` NEVER LAUNCHED** — it returned "You've hit your
  session limit" before dispatching, so nothing was billed and there are no
  cloud findings. The local `max` fallback fanned out to ten angles and **nine
  died mid-flight** on the same limit, including every correctness angle. One
  survived (simplification). The correctness pass was therefore done by hand
  over the diff, which is small where it counts: ~290 lines of production code
  across six files against ~2,800 lines of docs prose. **THE RANGE
  `8ae08cb..d577390` IS STILL INTACT AND STILL WORTH AN ULTRA PASS** — this
  branch changes `app/main.py`, so run it against that range, not `HEAD`.
  **⚠ FINDING 1 — THE `/ui` MOUNT WAS STILL PUBLISHING, AND THE GUARD THAT WAS
  ADDED TO STOP IT ONLY LOOKED AT `*.md`.** Measured over the wire at 200:
  `Veritas v1 (Broadsheet).dc.html` (42KB), `.thumbnail` (18KB),
  `uploads/pasted-*.png` (659KB). **This is the previous fix's own shape, one
  file over.** That fix moved `PLAN.md` out because it described the rejected
  design direction — and left **the rejected design itself** downloadable. Two
  of the three offenders are GITIGNORED, which is the whole lesson:
  `StaticFiles` reads the filesystem, so git's opinion of a file has no bearing
  on whether it is public, and a tree-level lint is either blind to them or
  fails on every machine that has run the design tool. Fixed at the SERVER:
  `_AllowlistedStaticFiles` refuses anything whose first path segment is not in
  `app.main.UI_ASSETS`. A denylist can only name what somebody already thought
  of; this is the third time that has cost this repo something.
  **⚠ FINDING 2 — EVERY `/ui/*` REQUEST WAS FILED AS `__unmatched__`.**
  `Mount.matches()` returns a child scope of `app_root_path`, `endpoint`,
  `path_params`, `root_path` — **no `route`** (only `Route` sets it), so
  `_route_template` had nothing to label a mounted request with. Measured:
  572.9ms of 581.6ms total duration sat under `__unmatched__`, at status 200.
  That bucket exists to collapse requests matching NOTHING — scanner noise and
  404s — into one series, and the go-live alerting thresholds on `/metrics` are
  still an OPEN item, so they would have been set against a series dominated by
  ordinary UI success. Fixed with `_LabelledMount`; the label is `/ui/{path}`
  from `Mount.path_format`, bounded at one series.
  **It also falsified a docstring in the same file.** `_route_template` argued
  404s reach `__unmatched__` "because nothing FULL-matches those" — S8.6 made
  that false in the commit that mounted the UI, since `/ui/*` returns
  `Match.FULL` and *still* arrived unlabelled, by a different mechanism.
  Corrected in place.
  **FINDING 3 (minor, NOT fixed):** `frontend/api.js` justifies
  `credentials:"include"` by the `?api=` cross-origin override, but the same
  sprint shipped `samesite=lax`, which stops the session cookie riding a
  genuinely cross-SITE request. `UI.md` §3 states the real rule (host
  separately ⇒ set `samesite=none`); the api.js comment does not.
  **CHECKED AND CLEAN:** alembic has ONE head, so `revision_state`'s
  `get_current_head()` cannot raise; `build_email` opens no socket at boot;
  the rate limiter is per-endpoint, not middleware, so static assets burn no
  quota; and `email_capture_path` defaults to `""` with every script writing
  its mailbox to a scratch dir, so captured OTPs were never under `frontend/`.
  **➤ NEXT STEP: decide on merging this branch, then S8.7 (src layout).**
- **Session 2026-08-13 — S8.6 BUILT AND MERGED. `main` is at
  `6991173`; PI-8's last sprint is done, so **PI-8 IS COMPLETE**. 1812 → 1848
  passing and `smoke_s86` 27/27 · `smoke_s83b` 22/22 · `smoke_s85_outcome`
  21/21 all re-run ON THE MERGE COMMIT. NOT PUSHED.**
  **⚠ MERGED WITHOUT AN INDEPENDENT REVIEW, on the user's explicit
  instruction.** A self-review pass afterwards **found one real defect**, fixed
  and merged at `51079da` (1848 → 1850): **the `/ui` mount was publishing
  `frontend/PLAN.md` and `UI-SPEC.md` unauthenticated** — the blind spot
  directly inside the guard this sprint added to make mounts reviewable, which
  pinned the mount's ROOT and never its CONTENTS. Docs moved to `docs/ui/`.
  **An INDEPENDENT review is still worth running** — every branch review since
  S7.1 found something the authoring session missed, and this one just
  demonstrated the point. Target the range **`8ae08cb..HEAD`** (`8ae08cb` was
  the pre-merge `main`); `main...s86-production-shape` is empty after a merge,
  so a range is the only way to express it. Branch refs are deleted.
  Everything below describes what that merge contains.
  1812 → 1848 passing, **ALL TWENTY smokes green**
  (s12, s13, s23, s41, s51, s52, s53, s63, s64, s71, s72, s73, s81, s82, s83a,
  s83b, s84a, s84b, s85_outcome, s86 27/27), browser check 19/19, contract
  31/31, bindings 402/402. NOT REVIEWED, NOT MERGED, NOT PUSHED. NOTHING WAS
  DEPLOYED: no Railway project, service, database, domain or variable exists
  that did not exist before the branch.** Plan:
  `docs/superpowers/plans/2026-08-12-s86-production-shape.md`, 15 tasks, TDD
  with every failing test seen red first.
  **THE DEPLOY SPRINT STOPPED BEING A DEPLOY, and that was decided before any
  code.** There are zero customers. A running host buys nothing and costs
  money, credentials and a public attack surface; the user gates go-live. So
  S8.6 shipped the system that is *correct to deploy* plus `DEPLOY.md`, the
  checklist a human runs later. The status board entry is renamed
  **Production shape**, and go-live is now an unscheduled user-gated line with
  no sprint ID, because it is not a sprint.
  **⚠ THE EIGHTH REFUSAL HAD TO ASK THE BUILDER, NOT THE PROVIDER STRING.**
  `config.yaml` ships `email_provider: "null"`, so a prod deploy on the shipped
  defaults booted clean and then answered 503 `email_unavailable` to every
  signup and login on all three planes — while `/healthz` reported healthy.
  Blockers 4 and 5 were dead on arrival. The check calls
  `build_email(settings).available`, because `build_email` **also** returns
  `NullEmail` for `provider="smtp"` with an empty host: a string check would
  have passed that config and shipped the same 503.
  **⚠ THE ROUTE-TABLE GUARD COULD NOT SEE MOUNTS AT ALL**, and serving the UI
  would have opened its first invisible hole. A `Mount` has no `.methods`, so
  the guard skipped it, and `include_router` dependencies do not apply to it —
  unauthenticated *and* invisible. `MOUNTS` was added **in the commit before**
  the mount existed. Then `_mount_paths` had to learn the same recursion
  `_walk` uses: `APIRouter` inherits `.mount()`, so a mount inside an included
  router sits behind the `_IncludedRouter` wrapper that already hides 54 of 63
  routes from a flat scan.
  **⚠ THE "TESTED CROSS-ORIGIN POSTURE" WAS CROSS-ORIGIN BUT SAME-SITE.** The
  browser check ran two servers on `localhost`; SameSite ignores the PORT, so a
  Lax cookie was sent and CORS applied — while `config.yaml`'s shipped
  `SameSite=None` was exercised by **nothing, anywhere**. Its docstring called
  that "the posture the UI ships in". Reaching for "we tested it" without
  checking *which property* the test pinned. Retired from both ends: the UI is
  same-origin at `/ui` and the shipped default is now `lax`. CSRF is
  deliberately KEPT and a test pins the reason, because "Lax blocks cross-site
  POST" is exactly the argument that would delete it.
  **⚠ THE IMAGE NEVER CONTAINED THE UI.** `frontend/` was absent from the
  Dockerfile — invisible while nothing served it, a blank page the moment the
  mount landed, and a container that reports itself healthy while 404ing every
  page, because a missing `StaticFiles` directory is not a boot error. The
  guard derives the static root from the LIVE APP. A fourth test the plan did
  not have reads `.dockerignore` too: it can cancel a COPY, and two
  hand-maintained lists that must agree is the shape of every drift this repo
  has found.
  **⚠ THE CRON'S OWN DOOR DIED WITH A TRACEBACK.** `python -m
  app.retention.sweep` against a never-migrated database exited 1 with forty
  lines of SQLAlchemy — the Railway cron's most likely first encounter, since
  it is a separate container that can start before the web service. Now exit 3
  with one sentence. **This also found a fixture that was less honest than
  production**: `cli_env` called itself "migrated-SHAPED" and used
  `create_all`, so it had every table and no `alembic_version`; fixed by
  migrating, not by exempting it.
  **⚠ AND A SMOKE CHECK THAT PASSED FOR THE WRONG REASON.** `smoke_s86`'s
  check 1 asserted `code != 0 and "LaunchConfigError" not in out` to prove a
  correct prod config gets *past* all eight refusals. Measured: against a dead
  Postgres the process does not fail, it **hangs** (the driver's connect has no
  timeout), so `code != 0` held only because the harness killed it. That
  evidence would have passed against a process that booted cleanly and served
  traffic. It now requires uvicorn's own "Waiting for application startup"
  marker. The hang is an operator fact and `DEPLOY.md` §6 says so.
  **OTHER WORK:** `GET /` derives its endpoints list at last (stale since
  S8.3, carried three times with correct reasoning — patching it would make an
  unmaintained list look maintained); CI builds the image for the first time
  ever, on push only, because this machine has no Docker; and **SMTPEmail
  delivered for the first time since it was written** to a 60-line SMTP sink in
  the smoke.
  **➤ NEXT STEP: S8.7 (src layout), and the OWED REVIEW of `8ae08cb..6991173`
  before that code is built on.**
  **On the review command: the BASE ARGUMENT IS LOAD-BEARING.** With no base
  `/code-review ultra` defaults to `origin/main`, which is **~76 commits
  behind** (S8.4b, S8.5, S8.3a, S8.3b and now S8.6 are all merged locally and
  unpushed), producing a diff well past the reviewer's 12,000-line ceiling —
  it was already 123 files / 21,733 lines before S8.6 merged. S8.6 alone is 32
  files / 4,354 lines, which is why the range above is the thing to pass.
  **Do S8.7 AFTER the review, not before.** The restructure moves every file in
  `app/`, so running it first turns the owed review's diff into "everything
  moved, plus some logic" — unreviewable, and the exact problem the src/ layout
  exists to prevent.
  After that the only things left in PI-8 are the user-gated go-live
  (`DEPLOY.md`) — **including the Railway cron for the retention sweep, without
  which the portal promises a purge nobody invokes** — and then PI-9
  (calibration harness).
  **`main` is ~80 commits ahead of a PUBLIC remote** (`RevanParimi/ResumeFilter`,
  last pushed 2026-08-07 at S8.4a). Five completed sprints exist only on this
  machine. Pushing is the user's call and nothing here does it.
  **BRANCH HYGIENE, done 2026-08-13:** `s86-production-shape`,
  `s86-review-fixes`, `m1-production-hardening` and `s83a-limits-and-metrics`
  were all merged and are deleted. **`s84-dev-login-echo` survives with ONE
  unmerged commit** — a demo server plus a *local-only login-code echo*
  touching `app/auth/service.py` and `app/core/boot.py`. Left alone
  deliberately: deleting it loses work, and merging something that echoes login
  codes needs a review first. It is the only branch left.
- **Session 2026-08-12 — S8.3 PHASE B REVIEWED AND MERGED. `main` is
  at `6dfde6c`, 1812 green, `smoke_s83b` 22/22 and `smoke_s83a` 19/19 re-run
  ON THE MERGE COMMIT, branch deleted. S8.3 IS COMPLETE; S8.6 (deploy) is the
  only sprint left in PI-8. NOT PUSHED.** The review found 5 findings, ALL
  FIXED before the merge.** Every one got a failing
  test first, and the two that mattered most were **invisible to a green
  suite**.
  **⚠ FINDING 1 (Important) — A TEST THAT PASSED IN THE FILE AND FAILED ALONE.**
  `tests/conftest.py` keeps its own `import app.*.models` block for
  `Base.metadata.create_all`, and Phase B added `app/rights/models.py` to
  `alembic/env.py` and **not** to it. The suite stayed green because some
  earlier test always imported `app.rights.store` first; running one test on
  its own — what a developer actually does — raised
  `OperationalError: no such table: data_principal_requests`. **This is the
  second-hand-maintained-list defect, committed by me, in the same branch whose
  commit messages congratulate it for fixing two others.** The fix is
  `tests/test_model_registration.py`, which asserts every `app/**/models.py`
  declaring a table is registered in **both** files.
  **That guard immediately found SIX MORE, all pre-existing on `main`:**
  `alembic/env.py` never imported auth, interview, matching, profile_sources,
  screening or verification. `upgrade` never reads `target_metadata`, so
  migrations always ran correctly — but **`alembic revision --autogenerate`
  compared against a metadata missing six live tables and would have emitted
  `DROP TABLE` for every one of them.** Fixed here rather than carried
  forward: six imports, no behaviour change, and a guard whose value depends on
  the list being complete.
  **⚠ FINDING 2 (Important) — `?limit=-1` WAS AN UNLIMITED SELECT.**
  `GET /admin/requests` took a raw `limit: int` and handed it to SQL, while
  every other paged read in the repo goes through `clamp_limit`
  (`page_max_limit` 200). SQLite reads a negative LIMIT as **unbounded**, so a
  bound that looked present returned the whole table — of every data
  principal's complaints, free text included. Now clamped; over-large caps
  (a client cannot size its first call correctly), nonsensical 422s.
  **⚠ FINDING 3 (Medium) — a counter row that no mechanism could ever
  delete.** `RateLimitStore.hit` took `expires_at: Optional`, and
  `rate_limit_counters` is the one swept class judged by that column, whose
  predicate skips NULLs. `hit`'s own housekeeping only retires older windows
  *of a key that is hit again* — its docstring says the sweep owns the rest —
  so a NULL row is a salted email hash beside a salted IP hash retained
  **permanently**, in the sprint whose point is that retention is enforced. No
  caller can write one today, which is exactly why it is a test and not a
  comment (Phase A's `enforce` fail-open, same shape). The argument is now
  REQUIRED; the column stays nullable as a disclosed limit, because a migration
  buys nothing the type system has already refused.
  **⚠ FINDING 4 (Medium) — a 500 on a statutory right, during a statutory
  right.** `submit` reads the candidate and then writes a row with a real FK to
  it; a `DELETE /portal/me` landing between the two raised `IntegrityError` out
  to the client. **S8.5's finding one table over.** The store now returns None
  and both submit routes answer 404 — with the cause **verified after the
  rollback** rather than assumed, because this row has a second FK and
  swallowing that as "the subject vanished" would turn a real bug into a quiet
  404.
  **⚠ FINDING 5 (Medium) — the authorship column's whole purpose was
  untested.** `resolved_by` exists to tell a named operator from the shared
  machine key, and every test *and the smoke* authenticated with `X-API-Key`,
  which has no human behind it — so the `ADMIN_USER` arm was reachable in
  production and exercised nowhere. **Checked and SOUND**: a test that logs in
  through `/auth/admin/verify` proves a real `admin_user_id` lands on the row,
  and a planted mutation that always records `operator_key` kills it. This is
  the S8.5 lesson applied to the plane S8.5 did not cover.
  **CHECKED AND SOUND, so the review did not touch them:** every child FK of
  every swept table declares `ondelete` (so the sweep cannot abort on an FK
  violation — the failure mode that would have made it useless in prod); the
  admin plane is deliberately not tenant-scoped, because these are requests to
  the PLATFORM and no org is a party; CSRF covers both new POST surfaces
  through `_accept`; and `GET /portal/requests` is deliberately **not** limited
  — bounding a person's view of their own complaints is worse than the
  unbounded read, and `MyData` already embeds unbounded lists.
  **➤ NEXT STEP: S8.6 (deploy) — Railway, HTTPS, prod config, live smoke. It
  is the ONLY sprint left in PI-8.** Two things it inherits from this sprint
  and must not forget: prod now refuses to boot without `DEE_GRIEVANCE_OFFICER_
  EMAIL` (the seventh refusal), and **the retention sweep has no scheduler** —
  it runs when a Railway cron calls `python -m app.retention.sweep --apply` or
  an operator posts to `/admin/retention/sweep`. Deploying without wiring that
  cron ships a portal that promises a purge nobody invokes.
- **Session 2026-08-11 — S8.3 PHASE B BUILT AND GREEN on branch
  `s83b-retention-and-rights`, and S8.3 IS NOW COMPLETE. 1689 → 1804 green,
  `smoke_s83b` 22/22, **ALL NINETEEN smokes green** (s12, s13, s23, s41, s51,
  s52, s53, s63, s64, s71, s72, s73, s81, s82, s83a, s83b, s84a, s84b,
  s85_outcome), 12/12 mutation probes dead.** Phase A merged first (`a57a05d`).
  The regression set was widened from the nine the last two sessions pinned,
  because this branch touched the **container** (`Services` gained two fields),
  the candidate store's identity refresh and `/portal/me` — so the ingest-era
  smokes were genuinely at risk, not only the recent ones. Plan:
  `docs/superpowers/plans/2026-08-11-s83b-retention-and-rights.md`, 16 tasks,
  TDD with every failing test proven red first. **NOT YET REVIEWED OR MERGED —
  that is the next action.**
  **The statutory surface exists: the retention promise is now mechanically
  true, and a data principal can ask for a correction and complain to a named
  officer.** New packages `app/retention/` and `app/rights/`, migrations `0022`
  and `0023`, seven routes, and `OPERATING.md` §§9–11.
  **THE LOAD-BEARING DECISION: `RETENTION_KNOBS` GREW 8 → 11 CLASSES AND STAYS
  THE SINGLE SOURCE.** The portal prints it and the sweeper derives its targets
  from it; a guard asserts set equality in both directions. A sweeper carrying
  its own list would drift, and the drift is silent in the worst direction —
  the portal keeps promising a window nothing enforces. **Widening it widens
  what the person is TOLD**, which is the correct direction: `batch_item_text`
  is a copy of their own resume text, `rate_limit_counters` holds a salted hash
  of their email beside one of their IP, `login_state` is their abandoned login
  attempts. `tests/test_portal_retention.py` needed **no edit** — it compares
  against `set(RETENTION_KNOBS)`, which is what that assertion was always for.
  **ELEVEN CLASSES, TWELVE TARGETS**: `login_state` covers `login_challenges`
  and `auth_sessions`, so the guard compares a SET and never a length.
  **⚠ THE SMOKE FOUND A REAL DEFECT THAT MAKES THE WHOLE CORRECTION MECHANISM
  A LIE, and no unit test in the plan would have.** `_refresh_identity` is
  documented *"latest non-empty name wins"*, so **every ingest overwrites
  `candidates.full_name`**. A subject files a correction, an operator verifies
  it against an ID and applies it — and the customer's **very next upload for
  that person silently puts the old spelling back**, while `/portal/requests`
  goes on reporting `applied: true`. Migration `0023` adds
  `full_name_corrected_at`; `apply_correction` sets it and `_refresh_identity`
  honours it. **Narrow on purpose**, and a second test pins the narrowness: with
  no correction on the row the old rule is still right and is untouched. It does
  **not** weaken §8.2 — the extraction stays immutable; what stopped is the
  identity row being re-derived over a human decision.
  **⚠ AND THE CHECK THAT FOUND IT WAS ITSELF OVERCLAIMING** — the shape the
  Phase A review caught twice, one file over. `the_correction_reached_the_
  candidate_row` only ever read the REQUEST row; it is now two checks, one on
  the request and one on `candidates.full_name` over the wire. **A check whose
  name claims more than its assertion makes is how this defect hid for an
  afternoon.**
  **CLEAR MODE'S PREDICATE HAS TWO HALVES AND THE SECOND IS LOAD-BEARING.**
  `batch_items.raw_text` is already `""` on every successful item, so an
  age-only predicate would report those rows as "cleared" **every day forever**
  — a preview that lies in the direction of looking busy. Pinned from both
  sides: an already-blank row is uncounted on the FIRST pass, and a second
  sweep reports 0. The row **survives** (an org's record of what it screened
  outlives the text), and the Phase A coupling is asserted rather than
  described: an item inside `ret_batch_item_days` keeps its text, so the retry
  still has an input.
  **DRY-RUN PARITY IS BY CONSTRUCTION**, not by discipline: `affected` is the
  same COUNT in both modes and only the write is skipped. A sweeper whose
  preview disagrees with its action is worse than one with no preview, because
  the preview is the entire reason an operator trusts the destructive call.
  **MEASURED, NOT ASSUMED: the bulk DELETE's cascade.** A bulk statement
  bypasses SQLAlchemy's ORM-level `cascade="all, delete-orphan"`; what carries
  it is each FK's `ON DELETE CASCADE` plus `PRAGMA foreign_keys=ON`. Had either
  been absent, sweeping a resume would have left an **orphaned extraction
  holding the very text the row was deleted to remove** — and the sweep would
  have reported success. The test seeds a real extraction and asserts it is
  gone.
  **⚠ THE METRIC FORCED A CHANGE TO ITS OWN GUARD.** `retention_deleted` moves
  N rows at a time, so its call site is `add(...)` — which
  `test_every_declared_metric_has_a_call_site`'s regex did **not** match.
  Wiring it without widening the scanner would have left the guard **passing by
  not looking**, which is precisely the failure that guard exists to prevent.
  Scanner and call site changed together, and the new assertion is only
  satisfiable through the `add` arm.
  **THE SPEC'S GRIEVANCE-ONLY RATE RULE WAS DELIBERATELY BROADENED**, recorded
  in `config.yaml` rather than slipped: the candidate plane gained **two** new
  authenticated writes, and limiting one of two sibling doors is this repo's
  signature defect. It ships as `request_submit`, one budget over both.
  **The limit is charged BEFORE validation**, with the trade written down: a
  typo costs one of ten complaints an hour, which is the smaller harm than an
  endpoint a stuck client can hammer forever with a body that never validates.
  **TWO HAND-MAINTAINED LISTS CLEANED UP ON THE WAY THROUGH, both the shape
  this repo keeps finding drifted.** (1) The `RateLimited` → 429 translation was
  **four byte-identical copies** and this branch was about to add a fifth; it is
  one `_rate_limited()` now, and the next copy would have been the one that
  forgot `Retry-After`. (2) `test_ratelimit_wiring.py`'s `LIMITED` tuple was
  hand-maintained, so the new fourth limiter would have been covered only if
  somebody remembered to type it there — limited services are now **discovered**
  off the container, with the named tuple kept as a floor so a service that
  silently *loses* its limiter still fails.
  **`SweepTarget.knob` IS A PROPERTY, AND THAT DELETED ONE OF MY OWN PLANNED
  TESTS.** The plan called for asserting that every target's knob matches the
  one its data class declares; with the derivation that test **cannot fail**,
  and a test that cannot fail is the shape this repo keeps catching in its own
  checks. What is pinned instead is the failure mode the property buys: a target
  for an undeclared class raises `KeyError` rather than sweeping on a default
  nobody chose. **A `check()` with `or True` in the smoke was deleted for the
  same reason** before it ever ran.
  **THE CLI'S OUTPUT CONTRACT WAS FOUND BY A TEST, NOT DESIGNED.** The first
  version did `json.loads(stdout)` and raised *"Extra data"*: the process shares
  stdout with the structured log, so the stream is a **sequence** of JSON
  documents. `jq` is unaffected; a caller doing `json.loads(output)` is not. The
  report is now documented and asserted as the **last line**.
  **The seventh boot refusal** (prod with an empty `grievance_officer_email`)
  sits after the prod-only early return, and a test asserts it does **not** fire
  locally — above that line it would break every local run. `_prod()` in
  `test_boot_config.py` gained the officer email, because that helper's whole
  job is to satisfy every prior refusal so each test isolates the one it names.
  **Widening `PUBLIC_PATHS` for `GET /grievance` turned the route-table guard
  RED and had to be edited deliberately**, which is exactly what that literal
  list is for.
  **`Services` gained `session_factory`**, measured first: every store in the
  repo builds its engine from `candidates_db_url`, so it names the database that
  already exists rather than opening an eleventh engine — and a handler no
  longer reaches into `some_store._session_factory`.
  **⚠ CARRIED FORWARD, still not fixed** (unchanged from Phase A): the six
  "byte-identical" 404-vs-absence claims in `SCREENING.md` (3) and `TENANCY.md`
  (3), all pre-existing on `main`; and `GET /`'s hand-maintained `endpoints`
  list, still missing every `/screening/*` route, `/metrics`, and now all SEVEN
  S8.3B routes. **The real fix is deriving it from `/openapi.json`.** Adding
  entries by hand would make an unmaintained list look maintained — and this
  branch just fixed two other hand-maintained lists for that reason, which
  strengthens rather than weakens the case for doing it properly.
  **➤ NEXT STEP: review the Phase B branch, then merge. S8.3 is then COMPLETE
  and the next sprint is S8.6 (deploy).**
- **Session 2026-08-11 — S8.3 PHASE A REVIEWED on branch
  `s83a-limits-and-metrics`. 8 findings, ALL FIXED. 1665 → 1689, `smoke_s83a`
  19/19, all nine smokes green, 6 mutation probes planted and all 6 died.
  STILL NOT MERGED — that is the next action.** Seven review commits on top of
  the build's thirteen (`cb54a51`…`7199ab5`). Every finding got a failing test
  first.
  **⚠ FINDING 1 (Important) — THE FIXTURE WAS MORE CORRECT THAN PRODUCTION, and
  that is why nothing caught it.** `build_default_services` passed
  `metrics=metrics` to the auth and screening builders and **not** to
  `build_interview_service`, so the real container built the ASR limiter with
  `metrics=None`: `asr_transcribe` was enforced perfectly and **counted
  nowhere**. `OPERATING.md`'s runbook step 1 — "read the `rule` and `scope`
  labels to find out which bound they hit" — could not answer for ASR at all.
  No test could see it because `tests/conftest.py::make_services` wires that
  limiter's metrics **by hand**. This is the S8.2 lesson ("a fake that cannot
  enforce an invariant will hide it") pointed at **wiring** rather than at
  behaviour, and it is a new variant worth remembering: the fixture did not
  merely fail to enforce the invariant, it **satisfied it independently**, so
  the production gap was invisible from inside the suite.
  `tests/test_ratelimit_wiring.py` now builds the **production container** and
  asserts every limiter shares the container's metrics *and* settings.
  **⚠ FINDING 2 (Important) — THE KNOWN DEFECT, and the fix was a test, not a
  choice between two bad options.** `llm_calls`, `asr_calls`, `screening_items`
  and `retention_deleted` were declared in `_HELP` with no call site — the same
  declared-but-never-populated shape as `auth_sessions.ip_hash`, which was this
  branch's own headline finding. **Deleted, not wired**: wiring means threading
  a metrics handle through the `LLMClient` and `SpeechClient` ABCs, three
  subclasses each, both builders and every fixture that constructs one, to emit
  series no scraper reads yet. `retention_deleted` went with the other three —
  "genuinely coming in Phase B" is exactly the rationalisation that kept
  `ip_hash` declared for two sprints. The real fix is
  `test_every_declared_metric_has_a_call_site`, which scans `app/` for
  `increment("<name>")` and fails on any declared name nothing increments, so
  **Phase B must add the name in the same commit as the sweep**. A second test
  proves the scanner can find something, so it cannot pass by matching nothing.
  **⚠ FINDING 3 (Important) — `_route_template`'s fallback was UNREACHABLE, and
  the docstring's premise was false.** The build bullet below claims the
  template is "re-resolved against the route table" because
  `BaseHTTPMiddleware` may not show the endpoint's scope mutations. **Measured
  on starlette 1.3.1: it shares the same scope dict**, and the scan's
  successful branch never executes:

  | request | `scope["route"]` | what happened |
  |---|---|---|
  | matched 200 | set | early return |
  | 405 method mismatch | set | early return (the router matches partially to answer 405) |
  | 500 from the handler | set | early return (set before the endpoint runs) |
  | 404 | absent | scan runs, FULL-matches nothing |
  | 307 redirect | absent | scan runs, FULL-matches nothing |
  | CORS preflight | absent | scan runs, FULL-matches nothing |

  So every case either returns before the scan or reaches it and finds nothing.
  That is untested defensive code in the branch that deleted a declared-inert
  field for being exactly that. **Deleted and replaced with a tripwire, not a
  scan**: three tests now fail if a Starlette upgrade stops populating the
  scope, instead of every label silently degrading to `__unmatched__` — which,
  as the original docstring correctly said, looks exactly like working code.
  The guard was right; putting it in the runtime instead of the suite was not.
  **⚠ FINDING 4 (Important) — the sprint's FOURTH RULE had no behavioural
  test.** `asr_transcribe` appeared once in the suite, inside a list of rule
  names that resolve — which proves the config table is populated and nothing
  about whether a transcription is ever refused, on the rule that spends money
  per second of audio and that the S7.3 review named as the open spend surface.
  Four tests now cover it; the load-bearing assertion is
  `len(speech.calls) == 1`, because **a limiter that refuses after the vendor
  call bounds the response and not the bill**.
  **⚠ FINDING 5 (Medium) — `enforce` was a latent fail-open.** It tested
  `not decision.allowed AND decision.scope is not None`, so a denial carrying
  no scope was silently **allowed**. No caller can construct that decision
  today, which is precisely why it needed a test rather than a comment: the
  guard would have gone on looking correct until one change to `check` forgot
  to set a scope, and the failure mode is an unbounded OTP endpoint that
  reports nothing. `RateLimited` now takes an `Optional` scope, so missing
  information degrades a log line instead of a bound.
  **⚠ FINDING 6 (Medium) — `hit()`'s `IntegrityError` arm had no test, and the
  risk was not the rollback.** It is the `session.commit()` **after** it: if
  SQLAlchemy did not expunge the failed INSERT's pending row, that commit would
  re-flush it and raise a second `IntegrityError` out of `hit`, past every 429
  handler, to the client as a **500** — a limiter answering 500 under exactly
  the concurrency it exists for. It does expunge; now proven.
  **MEASURED, AND IT CONTRADICTED THE ASSUMPTION IN THE STORE'S DOCSTRING: a
  rival on a genuinely separate connection is NOT CONSTRUCTIBLE ON SQLITE.**
  In-memory shares one connection through `StaticPool`, and a file database in
  WAL mode answers `OperationalError: database is locked` rather than letting
  the rival commit. **The `IntegrityError` arm is the POSTGRES shape of this
  race** — which is fine, because prod already refuses to boot on SQLite, but
  it means no SQLite test will ever reach it naturally. The collision is
  therefore planted on the session's own connection and what is pinned is the
  **recovery**, which is dialect-independent.
  **⚠ FINDINGS 7–8 (Minor) — four doc overclaims, in the file the review was
  warned about and in the smoke beside it.** (a) `OPERATING.md` called the 429
  "byte-identical" for a registered and an unregistered address; the responses
  are not — `X-Request-ID` is unique per request and `Retry-After` counts down
  inside the window — and **neither difference is a function of the address**.
  Now states what holds: same status, same body, same header names, no
  `Set-Cookie` on either. (b) `smoke_s83a.py`'s docstring claimed the two 429s
  matched "headers included" while **check 4 compared `status_code` and
  `.json()` and never looked at a header** — the same overclaim shape, one file
  over. The check now makes the comparison the docstring promised. (c) Two
  smoke checks carried failure-phrased detail strings that `check()` prints on
  pass as well, so a **passing** run printed
  `OK metrics_carries_the_deny_counter -- ... not found with a denial`. (d)
  `BatchItemRow.raw_text`'s comment still said "no path re-queues a failed item
  TODAY" in the branch that added the retry path.
  **CHECKED AND SOUND, so the review did not touch them:** the candidate and
  admin planes and both verify routes **are** limited (they simply had no test
  — now they do); `login_request`/`login_verify` have exactly one door each
  (`mint_code` and `verify_code` have a single caller apiece, and all eight
  routes funnel through `_request_code`/`_verify`); `_client_ip`'s n-th-from-
  the-right hop arithmetic is correct and a short forged `X-Forwarded-For`
  cannot bypass it; batch status is **derived**, not stored, so retry cannot
  leave a stale `complete`; and `OPERATING.md` §6's "it is one `UPDATE`" is
  literally true — measured at 2 SELECTs and **1** UPDATE for a 40-item retry,
  because SQLAlchemy batches the row writes into one executemany.
  **MEASURED AND WORTH KNOWING: all three planes SHARE one budget per address.**
  `bucket_key` is `salt|rule|scope|identity` and the plane is not in it. That is
  the conservative direction — nobody buys 3× the guesses by rotating planes —
  but it was undocumented, and adding a per-plane limit later would **silently
  triple the real bound**. Now pinned by a test and stated in `OPERATING.md`.
  **THE `screening_process` ORDERING WAS RIGHT AND STAYS, with the trade now
  written down.** It counts CALLS, not items, and enforcing before the
  ownership read and before the claim buys two things worth more than the
  accounting: counting after the ownership read would make a refusal on
  somebody else's batch id distinguishable from one on your own, and counting
  after the claim would strand claimed items in `processing`. Overhead is one
  no-op call per batch (101 calls for a 500-resume batch), so **400/hour still
  leaves four full 500-resume batches an hour** — the number stands. Two tests
  pin both consequences; move the check and they fail.
  **⚠ CARRIED FORWARD — NOT FIXED, and deliberately out of this review's
  scope.** Two known items, recorded here because a commit message is the one
  place nobody greps:
  1. **Six more "byte-identical" claims about 404-vs-absence** live in
     `SCREENING.md` (3) and `TENANCY.md` (3). All six are **pre-existing on
     `main`** — this branch adds none of them (`git diff main...HEAD` yields
     zero) — and they describe S8.4/S8.5 behaviour. They are the same
     imprecision the review corrected twice in `OPERATING.md`: status and body
     genuinely match, but `X-Request-ID` differs on every response, so
     "byte-identical" overstates what is asserted. **Worth a sweep of its own;
     do not do it inside a feature branch.**
  2. **`GET /`'s hand-maintained `endpoints` list is still stale** — missing
     every `/screening/*` route AND `/metrics`. Untouched on purpose: adding
     entries makes an unmaintained list look maintained. **The real fix is to
     derive it from `/openapi.json`**, which is generated from the code and is
     already the authority. Belongs with the `docs/routes.md` idea below.
  **➤ NEXT STEP: merge the branch, then S8.3 Phase B** (retention sweep · DPDP
  correction/rectification · grievance officer).
- **Session 2026-08-10 — S8.3 PHASE A BUILT AND GREEN on branch
  `s83a-limits-and-metrics`. 1586 → 1665, `smoke_s83a` 19/19 on its second
  run, ALL NINE smokes green (s63, s64, s73, s81, s82, s83a, s84a, s84b,
  s85_outcome), and 10/10 mutants dead.** Spec:
  `docs/superpowers/specs/2026-08-10-s83-operating-safely-design.md` (S8.3
  builds as TWO branches from one spec, the S8.4 shape); plan
  `docs/superpowers/plans/2026-08-10-s83a-limits-and-metrics.md`, all 13 tasks,
  TDD with a commit per task. **NOT YET REVIEWED OR MERGED — that is the next
  action, then Phase B.**
  **The service can now be run for paying customers on the abuse and spend
  surface**: a DB-backed dual-scoped limiter (`app/ratelimit/`, migration
  `0021`), in-place retry of failed batch items, and in-process counters at an
  admin-gated `GET /metrics`, plus a new root doc `OPERATING.md`.
  **THE LOAD-BEARING DECISION: the counters live in the DATABASE, and one
  smoke check is the entire argument.** An in-process limiter resets on every
  container start and is per-worker — two uvicorn workers silently double every
  limit — and **both failures pass every unit test**. `smoke_s83a` check 6
  therefore TERMINATES the server, starts a second one against the same
  database, and asserts the limit still holds. Nothing else in the suite can
  tell the two designs apart.
  **THE LIMITER IS CALLED FROM THE SERVICE LAYER, NEVER FROM A ROUTE**, and
  the count is not close: the OTP surface is **eight routes across three
  planes and exactly TWO service methods**. `AuthService`'s own docstring
  already gave the rule ("Every gate lives here rather than on a route… a rule
  applied at one entry point and not the other has shipped as a real defect in
  S7.1, S7.2 and S7.3"), so this sprint followed it rather than re-deriving it.
  **THE ENUMERATION ORACLE THIS COULD HAVE REBUILT, and where the fix had to
  go.** `AUTH.md` makes signup and login answer `202` for every address. A
  limiter that counted *after* the has-an-account branch would leave an
  unregistered address unlimited and a registered one at 429 — the same oracle,
  rebuilt out of status codes. The increment goes **before** that branch;
  a test and the smoke both assert a known and an unknown address are refused
  **indistinguishably** — same status, same body, same header names, no
  `Set-Cookie` (the 2026-08-11 review corrected "byte-identically", which the
  responses never were, and made the smoke's check match its own docstring) —
  and the mutation that moves the enforce call below the branch dies naming
  that test.
  It sits **after** the provider probe rather than at the very top, which is a
  deliberate deviation from the plan: that probe's own comment explains why it
  must run first, and hoisting a limiter above it would silently reorder a rule
  another sprint reasoned about.
  **`X-Forwarded-For` IS IGNORED unless `rate_limit_trusted_proxy_hops > 0`.**
  The header is entirely attacker-controlled, so trusting it by default hands
  every caller a free reset of their own per-IP scope — the limiter would pass
  every other test in the file while bounding nothing. Default 0 (socket peer);
  Railway sets 1. The test drives a spray with a *rotating forged* header and
  asserts it is still refused.
  **⚠ A DECLARED-INERT COLUMN FOUND BY THE SURVEY, not by a test:**
  `auth_sessions.ip_hash` existed, was plumbed through `AuthStore.create_session`
  AND `AuthService.verify_code(ip_hash=...)`, and was **never populated** —
  `routes.py` did not pass it, so every session row held NULL while PI-8 §7
  stated "`ip_hash`, never a raw IP" as though implemented. S8.3 needed IP
  extraction for the limiter anyway; **one helper, two consumers**.
  **`limiter` IS A REQUIRED CONSTRUCTOR ARGUMENT on all three services, and it
  earned that within the hour.** Four tests in `test_screening_service.py`
  build a `ScreeningService` directly and failed loudly at construction. Under
  an `Optional` default they would have kept passing while silently running
  **unlimited** — which is the entire failure mode. They now pass the
  container's own limiter, not a permissive stand-in.
  **The spend check runs BEFORE the claim** — a bound that runs after the work
  it bounds is the S8.4 Phase B finding (4) shape, and here it would
  additionally strand every claimed item in `processing` until the claim
  timeout, for a call that did nothing. A test asserts `processing=0,
  pending=1` after a refusal.
  **Retry RE-QUEUES and does not process**, so there is still exactly one door
  that evaluates an item. An item whose `raw_text` is gone is reported as
  `skipped`, never re-queued: `requeued: 1` on an item that cannot run is a
  promise the next `process` call breaks. `SCREENING.md` §7 has been admitting
  since S8.4 Phase B that the text was "kept on failure — for a retry path that
  DOES NOT EXIST YET"; that is now corrected rather than deleted, **and the
  coupling is stated in both directions**: retaining the text is justified by
  the retry, and the retry will be bounded by `ret_batch_item_days` once Phase
  B's sweep lands.
  **Metrics label by ROUTE TEMPLATE, never the raw path** — one series per
  batch id would make a URL scanner an unbounded memory leak dressed as
  observability. The template is **re-resolved against the route table** rather
  than read off `request.scope["route"]`: `BaseHTTPMiddleware` does not
  guarantee the endpoint's scope mutations are visible on the request object
  the middleware holds, and the failure mode of trusting it is a metric that
  silently degrades to `__unmatched__` for every request — which looks exactly
  like working code.
  *(↑ CORRECTED BY THE 2026-08-11 REVIEW, finding 3. The premise is false on
  starlette 1.3.1 — the scope dict IS shared — and the re-resolution scan was
  measurably unreachable, so it was deleted. The concern was real and is now
  carried by three tests instead of by dead code.)*
  `GET /metrics` is on the **admin router**, so the credential gate is
  inherited rather than remembered, and `response_model=str` is honest (the
  body IS a string) so `test_every_route_declares_a_response_model` needed no
  exemption. **The route-table, org-scope and OpenAPI guards all covered both
  new routes with no edit**, which is what they were built for.
  **10/10 MUTANTS DIED — but probe 4 SURVIVED ITS FIRST VERSION, and the reason
  is this sprint's most useful entry.** The mutation I wrote for "stop counting
  at the first denial" actually changed which denial *wins*, not whether
  counting stops. **A probe that does not express the behaviour it names proves
  nothing** — it is the S8.5 "two of my own contract checks were measuring my
  assumptions" shape, one layer further in, and the corrected probe (a `break`
  after the denial) dies immediately.
  **⚠ TWO OF THE SMOKE'S OWN CHECKS WERE ALSO MEASURING MY ASSUMPTIONS, the
  same shape a third time.** (1) I asserted three clean logins for an address
  that had just signed up — **signup and login share the `login_request`
  budget**, correctly, because both mint and send a code, and counting them
  separately would double the real bound. The limit drive now uses a fresh
  address and the shared budget is its own **named check** rather than an
  arithmetic accident. (2) `POST /ledger/orgs` returns `{org, api_key}` and I
  read `["id"]` off the envelope; the key comes back from creation and there is
  no second call to make.
  **Measured, and it is a finding about the suite rather than the code: NO
  existing test tripped the new limit.** 1586 → 1649 with the limiter live on
  the real path and zero fallout — no test in the suite makes more than 20
  login attempts against one address. The limiter is genuinely reachable
  (`test_ratelimit_auth.py` gets real 429s); the suite simply never needed that
  many codes.
  **`rate_limit_default_per_minute` from the PI-8 config sketch was DROPPED,
  not deferred**, with the reason written into `config.yaml`: a blanket limit
  on unauthenticated POSTs covers exactly the `/auth/*` routes already limited
  by name, and an enforced-nowhere knob costs more than it buys. Prod now
  refuses to boot with `rate_limit_enabled=false` — the **sixth** boot refusal,
  and it must sit after `boot.py`'s prod-only early return or every local run
  breaks.
  **Three counters (`llm_calls`, `asr_calls`, `screening_items`) are declared
  in the registry's help table with NO call site**, recorded as deliberately
  deferred to Phase B rather than silently skipped — they belong beside
  `retention_deleted`, where the sweep gives them a reason to be read together.
  *(↑ OVERTURNED BY THE 2026-08-11 REVIEW, finding 2. All four were deleted:
  disclosing a declared-inert metric is not the same as not shipping one, and
  the branch's own headline finding was this exact shape. A test now enforces
  that every declared metric has a call site.)*
  **➤ NEXT STEP: review the Phase A branch, then merge, then S8.3 Phase B**
  (retention sweep · DPDP correction/rectification · grievance officer).
  *(↑ the review happened on 2026-08-11 — see the top bullet.)*
- **Session 2026-08-10 (later) — THE CUSTOMER CAN NOW CLOSE THE LOOP. Branch
  `s86-org-outcome-route`, nine commits, TDD throughout. 1553 → 1586 green,
  `smoke_s85_outcome` 21/21 on its first run, `smoke_s84a` 23/23 and
  `smoke_s84b` 16/16 re-run green, and all three UI layers green (bindings
  402/402 · contract 31/31 · browser 19/19).** Spec:
  `docs/superpowers/specs/2026-08-10-org-outcome-route-design.md`, plan
  `docs/superpowers/plans/2026-08-10-org-outcome-route.md`.
  **This closes the named gap the wiring session left.**
  `POST /report/{id}/outcome` was admin-plane, so a customer who screened 400
  resumes and formed a judgment had nowhere to put it — and that judgment is
  PI-9's only calibration input. Two org-plane routes now exist
  (`POST`/`GET /screening/reports/{id}/outcome(s)`), the report screen's four
  buttons are back, and the apologetic paragraph is gone.
  **THE LOAD-BEARING DECISION: `outcomes` records WHO judged, and
  `recorded_by` exists BECAUSE `org_id` is SET NULL.** Migration `0020` adds
  three columns. `org_id` SET NULLs — the contrast with
  `screening_batches.org_id` (CASCADE) is the reasoning: a batch is an org's
  own operational work product with no meaning once they are gone, while an
  outcome is a **label about a person's record that the platform learns from**,
  and the report it judges survives offboarding too. But then a null `org_id`
  conflates "an operator recorded this" with "the customer who did has
  offboarded", and **PI-9 must never train on our own operator's self-labels
  believing a customer produced them** — that is circular, and the derived
  answer would always look plausible. One `String(16)` column keeps the fact.
  **ONE CONSTRUCTOR, TWO DOORS — and the test asserts BEHAVIOUR, not source.**
  `app/reports/outcomes.build_outcome` owns all three rules (claim ∈ report,
  notes ≤ cap, provenance stated). The admin door was migrated to it **before**
  the org door was written, on purpose: building the second beside an
  unmigrated first is the exact shape the shared constructor exists to prevent.
  A test asserts both doors **refuse the same inputs** — "both call the helper"
  is a claim about today's source; "both refuse the same input" survives
  somebody rewriting a handler.
  **⚠ A THIRD WRITER TO `outcomes` TURNED UP IN THE FULL SUITE, not in the
  design:** `scripts/migrate_reports_into_main_db.py`, the one-off S8.1
  importer. It is the door nobody thinks of, and the NOT NULL column with **no
  server default** is what caught it — had the default been left standing, the
  import would have succeeded and labelled those rows correctly for the wrong
  reason. The same choice turned an erasure test red until its INSERT was made
  honest. Pinned by a test.
  **TWO BOUNDS THAT ARE S7.2's `claim_ref` ONE TABLE OVER.** `notes` was an
  unbounded `str` into an unbounded `Text` column, about to be typed by
  customers into a box beside a candidate's name: now
  `max_outcome_notes_chars` (2000), enforced at **both** doors in one commit.
  And **the flywheel record lost `notes` and gained provenance**, also at both
  doors — that sink is an append-only JSONL with **no erasure path**, so free
  text about a named person has no business in it. The label is the training
  signal; the prose never was, and it still lives in `outcomes` where
  `outcomes → reports → candidates` CASCADE genuinely reaches it. Measured
  before deciding: no test asserted `notes` in a flywheel record.
  **THE LEAK THIS ROUTE COULD PLAUSIBLY INTRODUCE IS DOWNWARD, NOT SIDEWAYS.**
  A report has exactly one owning org, so no other customer can reach it — but
  the **operator's** internal note about that customer's report is written on
  the same report. `outcomes_for_org` filters on `org_id` on top of the
  ownership check for that reason alone, and a test asserts the exact string
  "internal: this agency keeps uploading fakes" is absent from the customer's
  list while the operator's own view still shows it.
  **404 — NEVER 403 — ON A WRITE.** The instinct on a refused write is 403, and
  it confirms the report exists to anyone guessing ids. Both verbs answer
  byte-identically to an unknown id, asserted in tests, in the smoke and in the
  contract checker.
  **The facade stopped calling itself Reads.** `OrgScopedReads` →
  `OrgScopedAccess`, because it now holds a write; a class named for reading
  while it records judgments is a lie in the one file whose whole job is being
  trustworthy about scope. **The attribute the guard watches
  (`services.screening_scope`) did not change, so `test_org_scope_guard.py`
  needed no edit** and kept covering routes nobody has written. And
  `test_every_facade_read_takes_org_id_first` **introspects** rather than
  hardcoding, so the new write arrived already covered — which is exactly what
  that choice was made for in Phase A.
  **7/7 MUTANTS DIED** (dropped notes cap · a defaulted `recorded_by` · the
  facade stamping OPERATOR on the org plane · `outcomes_for_org` losing its
  org filter, and losing its ownership check · `record_outcome` falling back to
  an unscoped read · the flywheel carrying notes again), plus 3 on the binding
  checker.
  **The smoke reaches two things no unit test can:** every unit test here
  authenticates with `X-Org-Key`, a MACHINE credential with no human behind it,
  so `recorded_by_org_user_id` is None in all of them — the smoke signs up
  through a real session and proves a real `org_user` id lands on the row. And
  it drives the route in the **browser's posture** (session + cookie jar +
  CSRF), which S8.4 Phase B measured refuses POSTs with 403 when a cookie and
  `X-Org-Key` are mixed.
  **The browser check types the note the way a person does** — through the
  native `value` setter plus a dispatched `input` event — because assigning
  `.value` never fires React's handler and the note would post as `""` **with
  the check still green**. It then reads the result back through a separate
  machine credential, sweeping every report in the batch rather than guessing
  which one the click opened.
  **⚠ A PRE-EXISTING DRIFT FOUND AND DELIBERATELY NOT PATCHED:** `GET /`'s
  `endpoints` list in `app/main.py` is hand-maintained and is missing **every**
  `/screening/*` route (S8.4 A+B, and now S8.5). Adding two entries would make
  an unmaintained list look maintained — the second hand-maintained list is
  always the one that drifts (S8.2's `OPEN_PATHS`/`PUBLIC_PATHS` finding). The
  real fix is deriving it from `/openapi.json`, and it belongs with the
  `docs/routes.md` idea below. A comment in the code now says so. Same call for
  `UI.md` §5's five plane counts, which are the `a9b8e59` measurement and are
  now marked as not re-measured.
  **⚠ A SELF-REVIEW OF THE BRANCH FOUND ONE REAL DEFECT, ONE NON-DEFECT I HAD
  TALKED MYSELF INTO, AND ONE GAP.** 1584 → 1586 green; browser 18 → 19.
  (1) **A 500 on a customer-facing write during an ordinary erasure.**
  Recording an outcome is a READ (does this org own it?) then a WRITE, and
  `outcomes.report_id` is a real FK — a candidate calling `DELETE /portal/me`
  between the two CASCADEs the report away and the INSERT raises. **S8.4 Phase
  B finding (3) one table over**: shorter window, same shape. `add_outcome`
  now returns `False` and both doors map it to the 404 they already emit. The
  cause is **verified after rollback** rather than assumed from the exception
  (the `save()`/`SubjectErasedError` precedent) — two other FKs hang off this
  row, and swallowing their failures as "the report vanished" would turn a
  genuine bug into a quiet 404.
  (2) **THE NON-DEFECT, and it is the more useful entry.** I claimed the
  double-click guard had to be an instance field because `setState` is
  asynchronous — the process driver's load-bearing lesson from earlier the
  same day. **Probed it: planting the state-based guard leaves the browser
  check GREEN**, because React flushes discrete events synchronously and the
  second click already sees the first one's state. The field stays (it does
  not depend on that behaviour holding, and this list is append-only), but the
  comment now says **belt-and-braces, not a fix**, and the check states that it
  does **not** discriminate the two spellings. Two lessons: a rule that was
  load-bearing in one place is not automatically load-bearing in the next, and
  a mutation probe is what tells you which — the same probe that killed 7/7
  earlier is what refused to kill this one.
  (3) A failed outcomes **read** rendered nothing at all — no history, no empty
  state, no error — which invites recording the same judgement twice onto an
  append-only list. The record action and the list read now fail separately.
  **➤ NEXT STEP: S8.3** (rate limiting · the `ret_batch_item_days` sweep ·
  in-place retry of failed items · observability · DPDP correction + grievance
  officer). Nothing else is outstanding on this branch.
- **Session 2026-08-10 — THE SCREENING SCREENS ARE WIRED. Branch
  `s85-screening-ui-wiring`, three commits, NO `app/` code touched
  (`pytest -q` re-measured at 1553, unchanged). Verified three ways:
  bindings 384/384, contract 25/25 over real HTTP, browser click-through
  16/16 in headless Chrome.** Spec:
  `docs/superpowers/specs/2026-08-10-ui-screening-wiring-design.md`.
  **The wedge is now clickable end to end by the customer who bought it:**
  sign up → drop resumes in → watch them screen → read a ranked, reasoned queue
  → open a report → screenshot the roll-up → delete the batch. Queue, report,
  summary, upload and batches all run against the seven batch routes plus Phase
  A's report read; their mock constants (`CANDIDATES`, `ROWS`, `REPORTS`,
  `splitEvidence`) are **deleted**, not left as a fallback.
  **THE LOAD-BEARING DECISION: the client drives the work, and the screens SAY
  so.** `process` does five items a call, each a full nine-node graph run, and
  there is no worker anywhere in `app/` — so a sequential loop lives in the
  browser. Registration evaluates nothing; closing the tab **pauses** the batch
  (an item stale past `claim_timeout` re-reads as pending, so the next call
  resumes it); every call bills a model. The loop therefore starts **on upload
  and never on navigation** — registering 200 resumes is an instruction to
  screen them, opening a batch is not — and **any** error stops it, because
  there is still no rate limiter (S8.3).
  **The driver's control flag is an INSTANCE FIELD, not state.** `setState` is
  asynchronous, so a loop consulting `state.driving` reads the previous value on
  the tick that starts it and stops before its first call. State is what
  renders; the field is what the loop obeys.
  **No polling timer at all**: the `process` call *is* the tick. With no worker,
  an idle client means an idle batch, so a timer would animate a bar that cannot
  move. And **paging is hidden while the driver runs** — the queue's sort key is
  `COALESCE(risk_score, -1)` and screening an item moves it from null to a
  score, so mid-run the key is *mutable*, which is the same limitation
  `SCREENING.md` §6 states for the curation queue.
  **⚠ THE BROWSER CHECK FOUND A REAL DEFECT ON ITS FIRST PASS, and no other
  layer could have.** The Delete button sits **inside** the batch row, which is
  itself a click target — so arming a delete also navigated away from the list
  you armed it on. Fixed with `stopPropagation`. Neither the binding checker nor
  any unit test can see event bubbling.
  **⚠ A MUTANT SURVIVED THE BINDING CHECKER'S FIRST VERSION, and the reason is
  worth keeping:** a field set to `undefined` passes an `in` check while
  rendering as an empty string — which is *precisely* the silent blank the
  checker exists to catch. `undefined` now counts as missing; all three planted
  mutants die.
  **⚠ TWO OF MY OWN CONTRACT CHECKS WERE MEASURING MY ASSUMPTIONS, this
  sprint's recurring shape.** (1) I asserted base64 of `[1,"x"]` is a 422 — it
  is a **valid** cursor, which is exactly what S8.4 Phase B's type-spec fix
  made it; the forgery set is now five genuinely malformed shapes. (2) A
  four-item batch under a cap of five proved "the loop is bounded and
  terminates" **after one call**; it is seven items now, and the loop must
  actually iterate (`remaining` goes 2 → 0).
  **Six things the API's real shapes forced on the design, none cosmetic:**
  the queue carries **no names** (scalars only, because `candidate_id` is SET
  NULL), so rows are identified by id and the screen explains why · the header's
  band counts come from `/summary`, not from a page of `/queue`, or "11
  elevated" would silently mean "11 on this page" · `BatchView` has item-status
  counts and no risk bands, so the batches list shows progress instead of the
  mock's invented per-batch "elevated" column · summary shares are of
  `n_screened`, never of the upload · the report's four outcome buttons are
  **gone** because `POST /report/{id}/outcome` is admin-plane and would 401
  every org user · and a corrupt PDF refuses the whole registration naming
  `item 37`, which is meaningless against 400 filenames, so the UI translates
  the index back to the file's name.
  **`MOCK_NOTE` no longer says "until S8.4".** The five screens still on mock
  data are mock because their routes are on **another plane** — admin
  (`evaluate`, operator console, curation) or candidate (interview runner) —
  which is a different and permanent reason.
  **Two machine facts measured this session:** `innerText` applies CSS
  `text-transform`, so uppercased column labels read as *absent* to a
  case-sensitive assertion; and the page and the API must both be on
  `localhost` — SameSite ignores the PORT, so `localhost:5174` and
  `localhost:8096` are the same **site** (the Lax cookie is sent) and different
  **origins** (CORS still applies), where `127.0.0.1` would be cross-site and
  every call would 401 for a reason that looks nothing like the cause.
  **⚠ A SELF-REVIEW OF THE BRANCH FOUND TWO MORE, both house shapes.**
  (1) **One rule, two doors:** every path onto the queue went through `nav()`,
  which loads what the screen renders — except `goQueueLink`, the upload
  screen's "screening queue" link, which set `screen` directly and fetched
  nothing. It landed on a queue that had never called the API and could not even
  render the empty state, because that state is keyed on the batch list having
  *arrived*. (2) **A late reply overwriting a live screen:** the three batch
  reads and the report read `setState` unconditionally on resolve, so a response
  for the batch you just left lands afterwards and replaces the one you are
  looking at — a queue showing another batch's rows, which the comment beside
  `selectBatch` already *claimed* was impossible. `load()` now takes a guard
  evaluated when the response **lands**, keyed on an instance field rather than
  state (the guard must be right the instant of the click, and `setState` has
  not flushed by then).
  **➤ NEXT STEP: an org-plane route for recording an outcome is now a NAMED
  gap** (it is PI-9's calibration input and the report screen currently says so
  in prose), then S8.3.
  **(DONE — built, smoked and wired the same day on branch
  `s86-org-outcome-route`; see the session above.)**
- **Session 2026-08-09 (later) — S8.4 PHASE B WHOLE-BRANCH REVIEW done: 6
  Important + 4 Minor findings, ALL FIXED on the branch (9 commits, TDD, one
  failing test proven before each fix), then MERGED to main. 1542→1553 green,
  `smoke_s84b` 16/16, `smoke_s84a` 23/23 and `smoke_s63` re-run green
  post-fix.** The four hot spots the roadmap named all HELD — every defect was
  one step past where a hot spot pointed, which is worth remembering: the
  places the builder worried about were defended; the same rule one door later
  was not.
  **The reviewer's findings, each proven before being fixed:**
  (1) **A type-forged cursor was a 500 on demand** — `decode_cursor` checked
  arity but not element types, so base64 of `[1,"x"]` decoded cleanly and hit
  `datetime.fromisoformat` as an int: `TypeError`, which
  `except (InvalidCursor, ValueError)` does not catch. Proven live on all
  three paged endpoints. Fixed with per-element type specs on `decode_cursor`
  plus `iso_datetime()` folding both fromisoformat failures into
  `InvalidCursor`.
  (2) **THE CLAIM WAS GUARDED GOING IN AND UNGUARDED GOING OUT** — the
  branch's own headline seam (`_try_claim`) made the claim race-safe, but
  `complete()`/`fail()` wrote back unconditionally. A process call outliving
  `claim_timeout_seconds` loses its items to the next call; its late `fail`
  then stamped FAILED + an error code over the live claimant's finished
  result, with `raw_text` already cleared — a contradictory row. Fixed with a
  lease (`ClaimedItem.claimed_at` in the write-back WHERE); the test asserts
  the refusal while the row is still held by the winner — the one state where
  ONLY the lease clause refuses — and the mutant deleting the clause was
  probed and dies.
  (3) **`counts()` returns None once the batch is deleted and none of its four
  callers guarded it** — get/summary crashed in `derive_status`, list crashed
  validating `BatchView(counts=None)`, process crashed on its final read (a
  minutes-wide window against a one-keystroke DELETE in a second tab).
  All four now read as absent/skip; the tests build the real interleaving
  with a store whose `counts()` genuinely deletes the batch before
  delegating.
  (4) **The item-count cap ran AFTER the work it bounds** — an over-cap batch
  of corrupt PDFs was fully decoded, then refused. The route now refuses on
  `len(items)` first; the test proves the ordering by asserting the cap
  message on items that would otherwise 422 as `pdf_parse_failed`.
  (5) **`counts()` dragged every item's full `raw_text` out of the DB on every
  poll** — it was built on `all_items()`, and it runs per poll of `get`, per
  batch of every `list` page and at the end of every `process` call. Now a
  GROUP BY with the stale-processing reinterpretation as a CASE, extracted to
  `_stale_processing` and shared with `_claimable` so the SQL spelling of the
  rule exists once.
  (6) **"Kept on failure so the org can retry" was an overclaim** — no path
  re-queues a failed item: `_claimable` covers pending + stale-processing
  only, there is no retry route, and `add_items` has no route. SCREENING.md
  §7 now states the truth (kept for S8.3's in-place retry, held under
  `ret_batch_item_days`, deletable only via batch delete). **In-place retry
  of failed items is a NAMED S8.3 input now, beside the sweep.**
  Minor, also fixed: `POST /features/materialize` accepted any `view_name`,
  materialized the default anyway and echoed the caller's name back (now 422
  naming the one view that exists); **`GET /domains` and `GET /admin/users`
  were still untyped — hiding inside ARRAYS**, which the contract test's
  object-only detector missed (it now recurses through `items`, which is what
  turned both red); 0019's collision check ran after its CREATE TABLEs, so on
  dev SQLite (pysqlite autocommits around DDL) a refusal wedged the deploy on
  're-run says table exists' even after the operator fixed the names — check
  now runs first and the test proves the re-run succeeds after resolving the
  collision; the two "exactly one of resume_text/resume_pdf_b64" docstrings
  said exactly-one while both validators enforce at-least-one-text-wins.
  **A machine trap measured this session:** on this OneDrive-synced checkout,
  rewriting a file under `alembic/` and immediately running pytest in a
  subprocess fails with `ImportError: cannot import name 'command' from
  'alembic' (unknown location)` — sync lag makes the local `alembic/` dir
  shadow the installed package as a namespace fallback. A byte-identical
  rewrite reproduced it; it is the rewrite, not the content. Mutation-probe
  scripts that touch `alembic/` need the file settled before the run.
  **➤ NEXT STEP: wire the UI's screening screens to the seven batch routes,
  then S8.3.** Nothing else is on the branch; it is merged and deleted.
- **Session 2026-08-08/09 — S8.4 PHASE B (screening surface) BUILT and GREEN on
  branch `s84b-screening-surface`. 1434→1542 green, `smoke_s84b` 16/16 exit 0,
  and ALL SIXTEEN smokes green (s12, s13, s23, s41, s51, s52, s53, s63, s64,
  s71, s72, s73, s81, s82, s84a, s84b).** Plan:
  `docs/superpowers/plans/2026-08-07-s84b-screening-surface.md`, all 15 tasks,
  TDD with a commit per task. **NOT YET REVIEWED OR MERGED — that is the next
  action.**
  **The wedge now works at volume, without an operator.** An organisation
  registers a batch, drives bounded processing calls, and reads a ranked,
  reasoned risk queue plus a screenshot-able roll-up: migration
  `0019_screening_batches` (two tables), a new package `app/screening/`
  (`schema` · `pagination` · `models` · `store` · `ingest` · `service`), seven
  org-plane routes, and `SCREENING.md`.
  **The load-bearing decision held all the way down: the queue read-model is
  built from `batch_items` ALONE, so no `Report` is ever on the org read path.**
  A `Report` is the cross-corpus object whose `resume_farm.matches[]` leaked in
  Phase A — a path that never holds one has nothing to forget to redact, which
  is strictly stronger than redacting correctly. Proven where it counts: the
  service test and `smoke_s84b` both assert it **on a batch whose report
  genuinely HAS farm matches**, seeded from a second organisation.
  **`ItemSignals` holds scalars only, and the test asserts the field set BY
  NAME** — so adding a prose field fails until somebody justifies it in writing.
  The DPDP argument, not style: `batch_items.candidate_id` is `SET NULL`, so
  anything stored beside it outlives the person it describes. The queue's
  one-line `reason` is composed at read time from the scalars instead.
  **⚠ TWO MUTANTS SURVIVED THE FIRST MUTATION PASS ON THE CLAIM, and the reason
  generalises.** Deleting the conditional UPDATE's `WHERE` clause, and relaxing
  `rowcount == 1` to `>= 0`, both survived every test — because the race they
  defend against is **unreachable through two sequential `claim` calls**: the
  second call's own SELECT filters the row out long before the UPDATE would.
  This is S8.2's lesson exactly ("a fake that cannot enforce an invariant will
  hide it", and its two-challenge test that had to drive the store directly).
  Fixed by extracting `_try_claim` as a seam and building the interleaved state
  in a test; both mutants now die naming that test. The other four mutants —
  the stale branch, and the org filter on `claim`/`queue_page` — died first
  time.
  **⚠ THE PLAN CONTRADICTED ITSELF ON `derive_status`, and the test table was
  right.** Its implementation snippet checked `pending` before `processing`, so
  `pending=1, processing=1` would read `pending` while its own parametrize table
  expected `processing`. Shipped processing-first: an item genuinely in flight
  is the more informative fact, and a batch reporting `pending` while a call was
  actively screening it would make the UI's poll look like a stall.
  **⚠ THE `operation_id` LOOP HAD TO RUN LAST IN `create_app`, and the contract
  test is what caught it.** `GET /` and `GET /healthz` are registered *after*
  the `include_router` calls, so the loop placed beside those calls — where the
  plan put it — silently missed both. Same family as S8.2's `_IncludedRouter`
  trap: a pass that inspects less than it appears to.
  **The OpenAPI measurement held exactly: 38 of 90 operations advertised
  `{"type":"object","additionalProperties":true}`.** All 38 are now modelled and
  the full suite passed with **no test changing a value**, which is the evidence
  that nothing was reshaped. Two of the plan's guesses were wrong and were read
  off the code instead: `_ACCEPTED` is `{"status": "accepted"}`, not
  `{"accepted": true}`, and the requisition field is `must_have_skills`, not
  `skills`. The three shared helpers now RETURN their models rather than dicts
  FastAPI would coerce, so the annotations are true at the Python level too.
  **A guard got stronger as a side effect, and the honest version of the claim
  is narrower than it looks.** Extracting the ingest core to
  `app/screening/ingest.py` moved all five `ALLOWLISTED_LINES` out of
  `routes.py`, taking the scope guard's allowlist to **empty** (pinned by a
  test). What that buys is not better *seeing* — those five lines were waved
  through anyway — but the removal of dead content-keyed exemptions that would
  one day match an unrelated future line. `screening` joins `screening_scope` as
  a sanctioned door, ordered longest-first so the shorter name cannot shadow the
  longer one, and the guard was **re-proven non-vacuous**: a planted org-plane
  `_guard_probe` reading `report_store` turned it RED naming the route and the
  attribute; removing it returned GREEN.
  **⚠ THE SMOKE FOUND TWO THINGS A UNIT TEST COULD NOT.** (1) A single HTTP
  client that signs up and then calls with `X-Org-Key` **still holds a session
  cookie**, so CSRF — which keys on how the principal was established, not on
  which header arrived (S8.2) — refused every POST with 403. That is the rule
  working; org onboarding moved into throwaway cookie jars, because a machine
  client has no cookies. (2) "A stolen cursor returns nothing" was the **wrong
  assertion**: by that point org B owns a batch of its own, and a page
  containing B's own work is correct. The check now asserts what a leak would
  actually break — none of A's batch ids appear in B's page.
  **Case-insensitive org names ship at the CONSTRAINT** (`uq_organizations_name_ci`
  on `lower(name)`), so both insert paths inherit it with no new check. The
  measurement Phase A predicted held: SQLite **enforces** an expression index
  and does not **reflect** one, so the index guard skips expression indexes with
  the measurement written into it and a behavioural test proves enforcement
  instead — strictly stronger, since the metadata comparison never established
  that any index was *enforced*. `0019` **refuses to run** over existing
  case-collisions rather than picking a winner on a customer's behalf.
  **`smoke_s63` was making live billed calls** — it was never on the list of
  nine smokes Phase A pinned, and it ingests through the extractor. Now pinned.
  That is the same trap for the third sprint running.
  **Two deliberate contract breaks, both on endpoints the wired UI does not
  call:** `GET /curation/skills/unmapped` now answers `UnmappedPage{terms,
  next_cursor}` (its sort key is *mutable*, so paging is stable against inserts
  and not against re-observation — stated in the model docstring, not
  discovered), and `POST /comp/estimate` now answers `CompBenchmark`, matching
  `GET /jobs/{id}/comp`. The frontend's central unwrap (`compRaw.estimate ||
  compRaw`) already handled both; only its now-stale comment changed.
  **Both former 422 sites became 200 with `reason`, in one commit** — fixing one
  entry point and leaving the other is this repo's signature defect, so
  `match_job` and `job_board` moved together.
  **➤ NEXT STEP: review the branch, then merge.** Nothing is on `main` yet.

- **Session 2026-08-07 (later) — S8.4 PHASE B IS SPEC'D AND PLANNED. Documents
  only; no `app/` code touched. `pytest -q` re-measured green at 1434 first.**
  Spec `docs/superpowers/specs/2026-08-07-s84b-screening-surface-design.md`,
  plan `docs/superpowers/plans/2026-08-07-s84b-screening-surface.md` (15 tasks).
  **The tenancy analysis is a FIELD table, not a handler count** — that is the
  method change Phase A's leak paid for, applied to the two new org-facing
  response shapes (the queue and the summary).
  **The load-bearing design decision: the queue read-model is built from
  `batch_items` ALONE, so no `Report` is ever on the org-plane read path.** A
  `Report` is a cross-corpus object — `resume_farm.matches[]` is exactly what
  Phase A leaked — so a path that never holds one has nothing to forget to
  redact. It is also the only shape that pages: `risk_score` is a real column,
  where the same number inside `reports.body` JSON is dialect-specific and
  unindexable.
  **`ItemSignals` holds scalars only, and that is DPDP rather than style:**
  `batch_items.candidate_id` is `SET NULL` (an erasure must not rewrite an org's
  record of what it screened), so anything stored beside it **outlives the
  person it describes** — and a copied `fabrication_risk.reasoning` can quote
  claim text. The queue's one-line reason is **composed at read time** from the
  scalars instead. A column that cannot hold personal data needs nobody to
  remember anything.
  **Three measurements changed decisions.** (1) **SQLite enforces an expression
  index but does not reflect one** (`SAWarning: Skipped unsupported reflection
  of expression-based index`), so the case-insensitive org-name fix ships as a
  functional UNIQUE index — the database computes it, so both insert paths
  inherit it with no new check — and the index guard gains a disclosed exemption
  plus a *behavioural* test, strictly stronger than the metadata comparison.
  (2) **38 of 82 operations return an untyped `dict`, not the 5 first claimed** —
  and the first count was wrong in this sprint's own signature way: it looked
  for `200`/`201` while the OTP routes answer `202`, i.e. it measured its own
  assumption instead of the API. (3) **The `_IncludedRouter` trap S8.2 recorded
  is still live and caught me mid-measurement** — a naive walk of `app.routes`
  saw **1** route, not 82; the new `operation_id` loop ships with the recursion.
  **A guard gets stronger as a side effect:** extracting the ingest core so the
  batch processor and the upload route share one pipeline removes all five
  `ALLOWLISTED_LINES` from the org-scope guard (every one was a line of
  `_ingest_one`), taking the allowlist to **empty**, pinned by a test.
  **One deliberate deviation from the parent spec, recorded not slipped:** §4.5
  asked for cursors on `/jobs/{id}/match` and `/talent/search` as well; both
  re-rank per request, so there is no stored key and a cursor would promise a
  stability it cannot keep. They keep `limit` and say so in the schema.
  **(DONE — that plan was executed, reviewed and merged on 2026-08-09; the
  screens on top of it were wired on 2026-08-10. This bullet used to say "IF
  YOU ARE A NEW SESSION: execute that plan" and is retired rather than deleted,
  because a stale instruction addressed to a new session is worse than no
  instruction: the live one is the ➤ NEXT STEP at the top of this section.)**
- **Session 2026-08-06/07 — S8.4 PHASE A (upload ownership) BUILT, REVIEWED and
  MERGED. 1377→1434 green, `smoke_s84a` 23/23 exit 0, all regression smokes
  green (s12, s13, s23, s41, s53 OK · s64 10/10 · s73 18/18 · s81 10/10 ·
  s82 21/21).** Plan:
  `docs/superpowers/plans/2026-08-06-s84a-upload-ownership.md`. Built
  subagent-driven across 10 tasks + a closeout fix round; every task got a
  fresh implementer and its own review.
  **The wedge is now reachable by the customer who bought it.** A
  self-registered org can upload a resume, read its fraud report and list a
  candidate's reports without an operator touching anything: migration
  `0018_upload_ownership` (`resumes.org_id` + `reports.org_id`, nullable,
  **`ON DELETE SET NULL`**), `OrgScopedReads` as the one door org handlers read
  people through, three `/screening/*` org routes, one redacting projection, and
  `TENANCY.md`.
  **⚠ THE HEADLINE FINDING — A CROSS-TENANT IDENTITY LEAK, FOUND BY THE GUARD
  THIS SPRINT BUILT.** `POST /screening/candidates` computed `resume_farm` from
  `similar_resumes()`, which scans the WHOLE platform corpus, and returned it
  with **real `candidate_id`/`resume_id` of other customers' candidates** — in
  BOTH the top-level `resume_farm` and the embedded `report.resume_farm`. The
  read routes were redacted from day one; **the ingest response never was.**
  This is spec §3.4's own named risk ("a bound that holds on one path and lapses
  on the other") realised: the spec counted **two** org-facing readers and there
  were three. Task 6's review missed it too — it checked the read routes and the
  ownership stamping. The Task 7 scope guard went red on it before a customer
  could. Fixed in `5a13d0b`; all stripping now goes through one
  `_stripped_matches` primitive. **The lesson for Phase B, and it is a change of
  method: enumerate the FIELDS that cross the tenant boundary, not the HANDLERS
  that read people.** Counting readers is what missed this.
  **⚠ THE SECOND ONE-RULE-TWO-DOORS BUG, one branch deeper, found by the
  whole-branch review:** `ingest()` stamped `org_id` only when it *created* a
  resume row. On a `text_sha256` match the existing row was reused and ownership
  was **dropped on the floor** — so when two agencies are handed the same PDF
  (the likeliest real input this product sees), the second one owned nothing and
  `org_owns_candidate` returned False for the org that had just uploaded her.
  With `evaluate=false` there is no report to fall back on either, so such an
  upload left **zero** ownership record anywhere. Ruled **spec conformance, not
  a design choice** — §0.1 says "each agency owns its own upload of her", and a
  single-valued `org_id` cannot hold two owners, so the row must not be shared:
  reuse iff the incoming `org_id` matches, else a new version owned by the
  caller. Gated on `org_id is not None`, so **the admin path is byte-identical**
  and every pre-existing dedup test and smoke passes unmodified.
  **The guard was defeated by renaming a local variable**, and that was measured
  rather than argued: `svc = _services(request)` MISSED, `s` MISSED, a one-line
  `scope.report(...) or services.report_store.get(...)` MISSED, literal
  `services` CAUGHT. Not an adversarial shape — "svc" is a name somebody picks
  without thinking, which makes it the likeliest way this guard ever fails
  silently. Receivers are now AST-resolved; sanctioned expressions are deleted
  from a line before the watched patterns match the residue. Proven red against
  the **live** route table with an aliased read planted in a real handler.
  **A guard's worth is its honesty about its own reach**, so both the docstring
  and `TENANCY.md` §5 now state what it does NOT cover: two attributes only
  (`features`/`jobs`/`ledger`/`portal`/`verification`/`interview`/`dashboard`/
  `comp` are invisible), one hop *inside* `routes.py` only, line-level not
  dataflow.
  **⚠ FIVE SMOKES WERE MAKING LIVE BILLED CALLS** — `s13`, `s23`, `s41`, `s53`,
  `s64` never pinned `DEE_OPENROUTER_API_KEY`, and this repo's `.env` holds a
  real one. Measured, not theorised: `smoke_s23` ran **past a ten-minute
  timeout** before the pin and finishes in seconds after it. The review flagged
  only `s13` and proposed deferring it; deferring is what would have kept a
  money-spending trap live. **All nine smokes now pin it.** S7.3 recorded this
  trap once already.
  **`TENANCY.md` had six overclaims and they are corrected** — it asserted a
  smoke check that does not exist (while §9 of the same document said seven
  sections later that the case is deliberately not smoked), claimed "no unscoped
  read reachable from an org handler" when `_ingest_one` has five allowlisted
  ones, said "per-statement" where the guard matches per physical line, and
  cited S7.1's verification route as the 404-never-403 precedent when that route
  answers **403 on consent and 404 on lookup** — the opposite of the rule it was
  cited for. Also newly *decided* rather than left implicit: `resume_version` /
  `matched_existing` / `matched_on` stay **unredacted** on the org plane — a
  count and a match-type are not an identity, and it is the fraud signal the
  wedge sells.
  **Two reviewer claims were wrong and were corrected rather than propagated:**
  the migration guard is `test_migrated_fks_and_nullability_match_orm` (the name
  the review gave does not exist), and `0018` makes **four**
  `batch_alter_table` migrations, not five.
  **Deliberately deferred, with reasons:** feature tests build schema via
  `create_all` rather than `alembic upgrade`; the `save()` rollback TOCTOU
  (misattributed message, not lost data); `ALLOWLISTED_LINES` being
  content-keyed; **case-sensitive org names — fixing that without a matching
  case-insensitive UNIQUE INDEX would create a NEW lockout**, so it needs a
  migration and belongs in Phase B; `missing_organization_name` returning 409
  rather than 422.
  **⚠ THE DOC LIED ABOUT THE ONE ROUTE THAT MATTERS, AND THAT IS WHY THE
  SPRINT'S LOAD-BEARING DECISION WAS UNPROVEN.** The plan, `TENANCY.md` §8/§9
  and the smoke all asserted **"there is no HTTP route to delete an
  organisation"**. There is: `DELETE /ledger/orgs/{org_id}`
  (`routes.py:671`) → `session.delete(OrganizationRow)` — precisely the
  `SET NULL` trigger, admin-key reachable today. The false premise is what made
  the sprint skip smoking `SET NULL`, the one choice a `CASCADE` typo destroys
  silently. **`smoke_s84a` now offboards an org over HTTP and proves the
  uploaded report survives, unowned** — and the check was proven non-vacuous by
  planting `ondelete="CASCADE"` in `0018`, watching it go red naming itself,
  and reverting. 20/20 → **23/23**.
  **The guard needed a second round, including a false positive I introduced.**
  The receiver resolver handled only `=`, so an *annotated* local — a form this
  codebase already uses — still walked past; the allowlist still suppressed a
  whole line; and the residue technique made a **docstring quoting the rule read
  as a breach of it**, which in a codebase this densely documented is how a
  guard gets switched off. Lines are now stripped of comments *and* string
  literals via `tokenize`. Both directions pinned: prose cannot forge a
  violation, and prose cannot forge the sanctioned door. Guard tests 5 → 12.
  **Next: the S8.4 Phase B spec + plan** (screening surface — batches,
  processing, the fraud-screen read-model, cursor pagination, materialization
  route, both 422 sites, comp's single shape, OpenAPI).
- **Session 2026-08-05 — S8.4 IS SPEC'D. `UI.md`'s five open questions are ALL
  CLOSED with the user, and the sprint builds as TWO branches from one spec.**
  Spec: `docs/superpowers/specs/2026-08-05-s84-ui-integration-surface-design.md`.
  No `app/` code was touched; this session is documents only.
  **The centre of gravity turned out not to be batch upload but TENANCY.**
  `reports` / `candidates` / `resumes` have never had an org column, so
  "the customer's data" had no definition — and S8.4 cannot expose the wedge to
  an org until it does. **Settled: an org sees only what it UPLOADED, and
  ownership is a property of the UPLOAD, not of the person.** `resumes.org_id` +
  `reports.org_id`, nullable, **`ON DELETE SET NULL`** — because an organisation
  offboarding must not destroy a candidate's resume; that is the *person's* data
  and the only cascade allowed to delete it is the candidate's own erasure, which
  already exists. Candidates stay **global and deduplicated** (S1.1), so the
  cross-corpus resume-farm signal survives, and "my queue" is **derived, not
  denormalized** — no second source of truth to drift. Another org's report is
  **404, never 403** (S6.4/S7.1 precedent: a 403 confirms it exists).
  **The enforcement is the point, not the rule.** A tenancy rule spread across
  ~20 org-plane routes is the one-entry-point bug shape *by construction* — the
  shape every branch review since S7.1 has caught. So org handlers get **no
  option**: one scoped facade whose every method takes `org_id` first, no
  unscoped read reachable from an org handler, and a **guard test in the
  `test_route_table_guard.py` family** that covers routes not yet written. It
  must be proven **non-vacuous** — S8.2 recorded FastAPI 0.138 not flattening
  `include_router`, which made a naive walk see 9 routes instead of 63 and would
  have passed while inspecting almost nothing.
  **The other four answers:** ADD org-plane routes and KEEP the admin ones (the
  operator's cross-tenant support view; moving them would break every `X-Org-Key`
  machine client, and `X-Org-Key` IS the API product) · a batch is a REAL stored
  object with status **derived at read time, never stored** (a stored status goes
  stale when a process dies and nothing corrects it; an item stuck `processing`
  past a timeout reads `pending` again, so a redeploy mid-batch self-heals) · the
  org sees the **FULL report** including `missing_signals` and `probes[]`, with
  **one** redaction (`resume_farm.matches[]` keeps similarity, loses identity)
  applied in **ONE shared projection** — two copies would be S7.2's `claim_ref`
  and S7.3's transcript finding a third time.
  **⚠ THE CONSTRAINT THAT SHAPED THE BATCH DESIGN, measured not assumed: there
  is NO worker, NO scheduler and NO `BackgroundTasks` anywhere in `app/`**, and
  `POST /candidates` awaits the whole nine-node graph inline
  (`routes.py:345-378`). 500 resumes in one request is not physically possible.
  So upload only **registers** items (a row insert) and a bounded
  `POST /screening/batches/{id}/process` does the slow work while the UI polls.
  Nothing dies on redeploy and no background execution enters the repo ahead of
  S8.3's observability.
  **The DPDP wrinkle, stated in the spec rather than hidden (§4.2):**
  `batch_items.raw_text` holds personal data with **no candidate to cascade
  from** — a resume cannot be written to `resumes` before extraction, because a
  resume row needs a candidate and identity resolution needs the extraction. So
  the text is **cleared on success** (S7.1 challenge hygiene: deleted on a path
  that already runs), `DELETE /screening/batches/{id}` ships **this** sprint as a
  real delete path, and unprocessed items get a declared window
  (`ret_batch_item_days`) that is named S8.3 sweep input. A **failed** item keeps
  its text, because the org must be able to retry — failure is not a reason to
  destroy the input.
  **⚠ S8.4 BREAKS THE WIRED UI IN TWO PLACES, named in spec §4.7 rather than
  discovered at integration:** org signup gains a **409** for a taken org name
  (the wiring session's 36/36 contract suite asserts "202 always" and will fail
  **on purpose**), and `POST /comp/estimate` changes shape to match
  `GET /jobs/{id}/comp` (the UI already unwraps `CompBenchmark` centrally, so
  this makes that unwrap correct for both paths). Everything else is additive.
  **`UI.md` and `UI-Spec.md` were updated in place** — §2, §2.1, §4.A, §4.B and
  §9 now carry the resolutions with their rejected alternatives, so the UI docs
  no longer describe tenancy as an assumption.
  **Next: the S8.4 Phase A plan**, then TDD build.
- **Session 2026-08-03 — THE UI IS WIRED TO THE API. Committed `76cee48`;
  `pytest -q` 1377 passed, unchanged (no `app/` code was touched).** This was
  the integration step PI-8 was re-sequenced around
  (`S8.2 → S8.4 → UI → integrate → S8.3 → deploy`). Spec:
  `docs/superpowers/specs/2026-08-03-ui-api-wiring-design.md`.
  **Scope, chosen by the user: through roles/comp.** Wired = auth on all three
  planes · `GET /auth/me` as the boot sequence · candidate DPDP portal
  (`/portal/me`, access-log, consents + revoke, erasure) · devices
  (`/auth/sessions` + revoke) · roles (`/jobs`, board) · comp
  (`/jobs/{id}/comp`). Deliberately NOT wired: `/report/{id}`, `/evaluate`, the
  operator console, the interview runner — all admin-router or likely to move
  to the org plane in S8.4, so wiring them now buys an integration rewrite.
  **The seam: a new `frontend/api.js` exposing `window.VeritasAPI`, loaded by
  ONE added `<script>` line.** The `.dc.html` logic class is eval'd through
  `new Function(...)` — a function scope, not a module — so a global is the
  only seam that exists. No npm, no bundler; **`frontend/` stays out of CI**
  per decision 0.1. `api.js` owns `credentials:"include"` (not an omittable
  option), `X-CSRF-Token` read from the cookie **at call time** (a re-login
  rotates it, and a cached one fails closed looking like an auth bug), 401 →
  redirect once and **never** retry (there is still no rate limiter, S8.3), and
  a typed `ApiError{status, detail, kind}`.
  **BOTH 403 detail strings were MEASURED off the running API, not assumed:**
  `"missing or invalid CSRF token"` (`app/api/routes.py:122`) vs
  `"no active consent for purpose '<p>'"` (`app/ledger/consent.py:58`). The
  default for an unrecognised 403 is **`consent`**, because that is the NORMAL
  state (UI.md §6) and calling it an auth failure turns an expected empty
  section into a red error.
  **Honesty rule made structural (spec 0.4):** wired screens **drop their mock
  constant outright** — no fallback-to-mock, because a fallback makes a broken
  backend look like a working one. The eight screens with no endpoint keep mock
  data and now carry a visible **"sample data"** chip, and the resolved API base
  renders in the rail. UI.md §7 warns a confident UI can make an honest backend
  lie; an unlabelled mock screening queue beside four live screens IS that.
  **⚠ A REAL DEFECT FOUND AND REPRODUCED ON MAIN — NOT FIXED (no `app/` change
  in a wiring session; it wants its own spec + TDD):** **org signup with an
  organisation name that already exists returns 202, sends a real code, and
  then `verify` rejects that CORRECT code as `400 invalid_code`.**
  `_establish` raises `ChallengeRefused("org_name_taken")`
  (`app/auth/service.py:363`) and the route maps **every** `ChallengeRefused` to
  one `invalid_code` (`app/api/routes.py:1697`). The single-message rule exists
  so a brute-forcer learns nothing about *codes*; here it is swallowing a
  **registration** failure. The user has a valid code in their inbox, types it
  correctly, is told it is wrong, burns their attempts and cannot self-onboard —
  and "Acme Staffing" is exactly the name two customers pick. It is the
  house shape again: **one handler collapsing two unrelated failures.**
  `missing_organization_name` rides the same path. **Fix belongs in S8.3/S8.4:
  separate the registration failure from the code failure without re-opening
  the enumeration oracle** (org names are not secret — a distinct
  `409 organization_name_taken` leaks nothing an org-name uniqueness check
  does not already leak).
  **Two more findings, neither on any gap list:** (1) `GET /jobs/{id}/comp`
  returns a **`CompBenchmark` that WRAPS the estimate** (plus `position` /
  `delta_pct`), while `POST /comp/estimate` returns the bare
  `CompBandEstimate` — two shapes for the same numbers, and assuming one
  rendered a band made entirely of dashes; now unwrapped once, centrally.
  (2) **`GET /jobs/{id}/board` 422s `"no materialized candidates to match"` on
  an empty feature store, and materialization has NO HTTP ROUTE AT ALL**
  (`app/features/materialize.py` is reachable only from Python), so for a
  self-registered org that 422 is **permanent, not transient** — it renders as
  an empty state and is an S8.4 input. Also `POST /jobs` refuses a requisition
  with no skills (422). And the **OTP resend cooldown is 60s and silent** — a
  resend inside it answers 202 and sends nothing, so the copy must not promise
  a new code; it now says the first code is still the live one.
  **Verification, since `frontend/` has no CI and no test runner (all three
  green):** 36/36 cross-origin contract checks driven with a real `Origin`
  header and a cookie jar (preflight · 202 for known **and** unknown addresses ·
  both cookies accepted over http · `/auth/me` on the cookie alone · CSRF absent
  → 403 and present → 200 · the consent 403 distinct from it · one
  `invalid_code` for every OTP failure); **9/9 in a real browser at the real
  origin**, including a deliberate CSRF-header bypass to prove the fork is real
  and a dead-API `network` state; and **27/27 clicking through every wired
  screen on both planes over CDP** — which is what caught the comp wrapper,
  since a DOM dump of one screen never would.
  **Config, local `.env` only (all three default to broken-for-a-browser, none
  can ship — prod refuses to boot with any):** `DEE_CORS_ALLOWED_ORIGINS`
  (JSON array), **BOTH** `DEE_SESSION_COOKIE_SECURE=false` **and**
  `DEE_SESSION_COOKIE_SAMESITE=lax`, `DEE_EMAIL_PROVIDER=capture` +
  `DEE_EMAIL_CAPTURE_PATH`. `tmp_mail.jsonl` (captured OTPs), `frontend/uploads/`
  and `frontend/.thumbnail` are gitignored. **Note `.gitignore` has no inline
  comments** — a trailing `# …` becomes part of the pattern and silently matches
  nothing; that bit once this session.
  **Next: `git checkout -- data/veritas.db` after any local demo run** — the dev
  DB is a TRACKED file, so test orgs and candidate emails otherwise land in git.
- **Session 2026-08-02 — UI-Spec REVIEWED against the code; next session is API
  WIRING.** The external UI (`Veritas.dc.html`, mock data only) is described in
  the new root doc `UI-Spec.md`, which was cross-checked route by route against
  the **live route table (78 app routes + 5 doc/root = 83, matching UI.md)** and
  the Pydantic schemas — enumerated from the running routers, not remembered.
  **The gap list was accurate for everything it named, and missed ten surfaces**,
  now folded into `UI-Spec.md` as items 9–17: ingest-response fraud signals
  thrown away (`CandidateCreateResponse.matched_existing/matched_on/
  duplicate_resume/resume_farm` — the near-duplicate check runs AT INGEST, so
  "this exact resume was uploaded before" is available before any report opens);
  the org-side S7.2 reads (`GET /verification/candidates/{id}/assurance` and
  `.../claims`); **moonlighting** (`ClaimEvidence.concurrent_employment`, a named
  GTM wedge component, absent from the UI entirely); `POST /ledger/offers` (the
  Comp screen renders observed-offer figures but nothing submits one, so
  `n_observed` stays 0 and the blend is prior-only in practice);
  `POST /ledger/orgs/{id}/api-key` (X-Org-Key IS the API product per decision
  0.4, and no screen obtains or rotates it); operator consent administration;
  operator candidate surfaces; `POST /candidates/{id}/auth-key`; org offboarding.
  `POST /evaluate` and the candidate-side interview runner were BUILT in response
  (`UI-Spec.md` §8b/§8c). **Two documentation defects found, BOTH THE SAME
  SHAPE — a route's plane assumed rather than read off the router it is
  registered on:** `GET /domains` and `POST /evaluate` were both marked org-plane
  and are both on the ADMIN router (an org session gets 401). Twice in one
  carefully-written document. **The cheap structural fix, and it is the house
  metadata-drift-guard pattern applied to docs: have
  `tests/test_route_table_guard.py` emit `docs/routes.md` (method · path · plane)
  and check the spec's endpoint tables against it.** Also corrected: there is
  **no `/auth/admin/signup`** (org and candidate self-serve; operators are minted
  via `POST /admin/users`, the first one bootstrapped with `X-API-Key` — see
  `routes.py:1850-1856`), and the candidate card is NOT substantial design work
  (its three sections are all evaluation-ledger data, which is off the pitch;
  what to keep is the 200-with-per-section-status pattern).
  **Fixed in the repo this session (uncommitted): `app/graph/build.py:3` said
  "seven nodes" while `_PIPELINE` has nine.**
  **⚠ THE WIRING SESSION'S THREE PRECONDITIONS — all config, all defaulting to
  broken-for-a-browser, and nothing authenticates until they are set:**
  (1) `cors_allowed_origins = []` fail-closed, so the middleware is NOT INSTALLED
  and every browser call dies at preflight while Postman works fine — set
  `DEE_CORS_ALLOWED_ORIGINS` to the UI's exact origin; (2) the cookie defaults are
  prod-correct and localhost-broken — `session_cookie_secure=True` +
  `samesite='none'` means the browser SILENTLY DROPS the cookie over http, so
  `/auth/org/verify` returns 200 with a `Set-Cookie` that never becomes a cookie
  and everything then 401s. Set **BOTH** `DEE_SESSION_COOKIE_SECURE=false` **and**
  `DEE_SESSION_COOKIE_SAMESITE=lax` — changing only the first gives the identical
  symptom for a different reason, since `SameSite=None` without `Secure` is also
  rejected. It works because SameSite ignores PORT: `localhost:5173` and
  `localhost:8000` are the same *site* (Lax sends it) but different *origins*
  (CORS still applies). Prod refuses to boot with `secure=false`
  (`app/core/boot.py:52-58`), so the dev setting cannot ship by accident;
  (3) `email_provider='null'` means **login is impossible** — every signup/login
  returns `503 email_unavailable` and no OTP exists anywhere. Set
  `DEE_EMAIL_PROVIDER=capture` + `DEE_EMAIL_CAPTURE_PATH=<file>` and read codes
  from the JSON-lines file; note `build_email` falls back to `NullEmail` when
  capture has no path, so a pathless capture refuses silently.
  **These are a local `.env`, not code changes — no merge, no prod impact.**
  **Plane reality to wire around:** `/report/{id}`, `/report/{id}/outcome`,
  `/evaluate` and `POST /candidates` are ALL admin-router, so the centerpiece
  risk-detail screen can only be demoed as an operator until S8.4. And there is
  still **no rate limiting** (S8.3), so a UI retry loop will not be caught.
  **The two product decisions that should be settled BEFORE more design lands on
  screens 2/4/6:** UI.md §2.1 tenancy (`UI-Spec.md` line 104 already asserts "you
  see only what your organisation uploaded", but `reports`/`candidates`/`resumes`
  have **no org column** — verified), and UI.md §9 Q3 batch identity (nothing in
  the schema has a batch). Both are cheap now and a rebuild later.
  **`UI-Spec.md` items 9–17 should feed the S8.4 spec directly as measured
  requirements input** — S8.4 is the last sprint before integration.
- **Current sprint:** **S8.2 (Identity & access) BUILT and GREEN on branch
  `s82-identity-access`, REVIEWED and MERGED to main — 1200→1377,
  `smoke_s82` 21/21 exit 0, and all six regression smokes green (s13 11/11,
  s41, s53, s64 10/10, s73 18/18, s81 10/10). Branch deleted.**
  **The whole-branch review (inline) found ONE real defect, and this branch
  had introduced it itself: an UNAUTHENTICATED LOGIN LOCKOUT.** Once the
  candidate plane started sending for both purposes (the Task-12 fix), one
  address could hold two live challenges; `verify_code` took the FIRST it
  found (signup before login), so a correct login code was checked against
  the signup hash and refused until the shadow expired — burning the attempt
  counter to `exhausted` on the way. Anyone could fire a signup code at any
  candidate's address and lock that person out of their own account,
  repeatably. Reproduced, fixed twice (the candidate plane files both
  purposes under ONE scope so the state cannot arise; `verify_code`
  evaluates EVERY live challenge and accepts the first MATCH so it cannot
  arise on another plane), then re-reproduced to confirm. Mutation-tested
  per layer — and the second layer's mutant SURVIVED at first, because
  collapsing the scope makes it unreachable through the public API, so a
  test now drives the store directly to build the two-challenge state.
  Also from the review: `org_user_by_email`/`admin_user_by_email` ordered by
  `created_at` (uniqueness on `org_users` is PER-ORG, so an unordered
  `.first()` is implementation-defined on Postgres). Probed and sound:
  cross-plane code redemption, cross-candidate session isolation, a disabled
  org_user holding a live session, erasure with an empty email_hash, and
  garbage/oversized session cookies.**
  **PI-8 was RE-SEQUENCED first (decision 0.1): S8.2 → S8.4 → UI → integrate →
  S8.3 → deploy.** Sprint IDs are stable; only the order moved. Two consequences
  recorded in the PI-8 design: **§5.5 is superseded** (S8.2 no longer pins
  S8.4's contracts with 501 stubs — pinning only ever protected *parallel* UI
  design, and the UI is now built after S8.4 ships real endpoints), and
  **§12's `admin_users` question is CLOSED — it rides S8.2**.
  **What shipped:** a new pure package `app/auth/` (`schema.py` ·
  `sessions.py` · `csrf.py` · `challenges.py` · `models.py` · `store.py` ·
  `service.py`), a new seam `app/services/email.py`, migration
  `0017_auth_identity` (four tables), 13 new HTTP routes, `AUTH.md`.
  **(1) THE STRUCTURAL ANSWER TO PI-8'S HIGHEST RISK.** Sessions add a SECOND
  entry point to every plane, and PI-8 §9 called for "every authorization test
  gains a session-mode twin" — ~33 files of duplication covering only today's
  routes. Replaced (decision 0.5) by **one resolver per plane**: the three
  `require_*` dependencies became thin wrappers over
  `AuthService.resolve(kind, session_token, header_key)` and **kept their return
  types**, so **all 63 endpoints gained session mode with ZERO handler edits and
  every pre-existing authorization test passes UNMODIFIED through the new
  path** — which is the evidence that matters. Plus a **route-table guard**
  (`tests/test_route_table_guard.py`) that walks the live FastAPI route table
  and fails for any non-public route establishing a principal another way, so it
  covers routes **not yet written**. That is the metadata-drift-guard pattern
  applied to authorization. **Two things it surfaced:** FastAPI 0.138 does NOT
  flatten `include_router` into `app.routes` (it stores an `_IncludedRouter`
  wrapper), so a naive walk sees **9** routes and misses all 63 — the guard would
  have passed vacuously, the exact failure mode of the fail-open admin gate; a
  `>= 60` floor now asserts it inspected something. And `test_api_auth_gate`'s
  `OPEN_PATHS` was a **second hand-maintained allowlist** beside `PUBLIC_PATHS`;
  it now imports it, because the list that drifts is always the unwatched one.
  **(2) CSRF LIVES INSIDE THE RESOLVERS**, not beside them. FastAPI runs
  router-level dependencies BEFORE route-level ones, so a separate
  `Depends(require_csrf)` on `org_router` would have run before `require_org`
  established the principal, read `via` as unset, and **skipped the check on
  every request** — a fail-open no cookie-using test would have noticed. The
  exemption keys on `Principal.via`, never on "a header was present": a session
  cookie plus an attacker-supplied `X-Org-Key` is still CSRF-checked (pinned by
  a test named for the trap).
  **(3) THE CLAIM (decision 0.4).** A candidate signing up with an address
  already on file **attaches to that candidate record** rather than forking a
  duplicate person — otherwise records built from org-uploaded resumes are
  unreachable by their own subject, making the portal's DPDP rights theoretical
  for every candidate in the system. Same trust boundary as S7.1's L2
  `otp_email`; grants **no** identity assurance (fusing "logged in" with
  "verified" would repeat S7.2's two-ladders mistake).
  **(4) THE SMOKE CAUGHT A REAL DESIGN BUG NO UNIT TEST COULD.**
  `_subject_exists` treated "a `candidates` row exists" as "this person has an
  account" — but most candidate rows are created by an org uploading a resume,
  about someone who has never touched the system. So signup no-op'd and **the
  claim was unreachable in exactly the case it exists for.** 1363 green tests
  said nothing, because the org-upload-then-candidate-signup sequence only
  happens end to end in the smoke. **Fix: on the candidate plane signup and
  login are the SAME act and both always send** — which is also a *stronger*
  anti-enumeration property than silence (same status, same body, same email for
  known and unknown). The org plane keeps the distinction, because an
  `org_users` row IS an account. Four tests encoding the old behaviour were
  rewritten to assert indistinguishability.
  **(5) A SECOND ENUMERATION ORACLE, found while testing:** with email broken,
  `login` for an UNKNOWN address short-circuited before sending and answered
  202, while a KNOWN address reached the send and answered 503.
  `EmailClient.available` is now probed **before any account lookup**.
  **(6) MUTATION TESTING EARNED ITS KEEP** on `AuthService`: two mutants
  SURVIVED the first pass. Deleting the kind check inside the CANDIDATE resolver
  branch broke nothing (the test only pointed a *candidate* token at the org and
  admin resolvers) — now every (token, plane) pair is asserted, plus "a principal
  is never returned without its subject id". And moving the attempt cap after the
  code check broke nothing either, which meant **my own comment claiming that
  ordering was load-bearing was wrong**; corrected to what it actually buys.
  **(7) ONE ERASURE PATH.** `PortalService.erase()` is called by BOTH the portal
  and the admin plane. Sessions CASCADE; `login_challenges` **cannot** (no FK —
  at signup time no principal exists), so they are deleted explicitly there. The
  test that matters is `test_admin_erasure_kills_sessions_and_challenges_TOO`:
  had the deletion gone in the portal handler — the obvious place — it fails.
  **(8) Three new prod boot refusals:** insecure session cookie, `"*"` CORS
  origin, capture email provider. **Standing gap, stated plainly: NO RATE
  LIMITING** (decision 0.6) — acceptable only because the deploy is last; if
  that sequencing changes, S8.3's limiter must come forward with it.
- **Prior sprint detail (S8.1):** **S8.1 (Deployable spine) BUILT and GREEN on branch
  `s81-deployable-spine` — 1175→1200, `smoke_s81` 10/10 exit 0, and the four
  regression smokes (s13, s41, s53, s64, s73) all still green.** Four changes
  plus a deploy that was deliberately stopped.
  **(1) The admin plane fails CLOSED.** `require_api_key` treated an unset
  `DEE_API_AUTH_KEY` as "auth disabled", so all 27 admin endpoints were public —
  including `POST /candidates/{id}/auth-key`, which mints *any* candidate's
  access key. Two layers now, because they fail differently: the gate refuses
  when no key is configured (**an unset credential is the most refusing state,
  not the least**), and a new `app/core/boot.py::verify_launch_config` stops the
  process before it can serve in that state. **No knob and no `env` exemption
  restores the old behaviour** — decision 0.1 dropped PI-8 §1's "unless env is
  local" escape, because `env` DEFAULTS to `local`, which would have made a safe
  deploy depend on remembering two variables instead of one. A **second** boot
  refusal was added while planning: `env=prod` on a SQLite URL, because container
  disks are ephemeral and every row would vanish on the next redeploy. The fix
  was wide as predicted and wider than measured — 11 test files, not 7 — and
  `test_auth_open_by_default` was **inverted**: it was the test pinning the
  defect in place.
  **(2) Migrate-on-boot** (blocker 1): `alembic upgrade head` ran nowhere in the
  boot path. Now in the lifespan, taking a **`pg_advisory_lock`** on Postgres so
  concurrent workers cannot race the same migration. The Dockerfile copied
  `app/` and `config.yaml` only, so this would have failed *in the container and
  nowhere else* — `alembic/` and `alembic.ini` now ship in the image.
  **(3) THE FOLD.** `reports` + `outcomes` moved out of a private raw-`sqlite3`
  database into the main Alembic one as a new `app/reports/` package (migration
  `0016`, `reports.candidate_id → candidates.id ON DELETE CASCADE`, nullable
  because `/evaluate` makes candidate-less reports). **The cascade test was
  written before the store existed and passes with no route orchestration at
  all** — that ordering was the point. `app/services/report_store.py` is deleted
  (212 lines of raw SQL, an `INSERT OR REPLACE` Postgres does not have, and an
  `ALTER TABLE ADD COLUMN` in a try/except standing in for a migration system).
  **`InMemoryReportStore` is deleted too, and that is not cleanup:** it is a
  dict, it cannot cascade, and leaving it in `make_services` would have let every
  erasure test in the suite pass *without* the guarantee the fold exists to
  create. `delete_for_candidate` is off the Protocol entirely; both erasure
  handlers call `delete_candidate` alone, with `reports_deleted` surviving as a
  pre-count READ — a number in a response, not a person's data.
  **One behaviour genuinely changed, and the FK is why:** `POST /candidates`
  used to race erasure by saving the report and then deleting it if the candidate
  had vanished mid-eval. The orphan can no longer be written, so `save()` raises
  `SubjectErasedError` and the handler returns `report=None`. Both halves of that
  race are the database's job now.
  **(4) Postgres**, verified against a real PG **18.4**, not a mock: all 16
  migrations **up → down to base → up** clean (which proves the three
  `batch_alter_table` migrations on a dialect where batch mode is a plain ALTER,
  **and** proves the downgrades — retiring the S3.1 residual "0004 downgrade
  untested"), plus 29 SQL-shaped tests (report store, cascade, data migration,
  every migration guard) with no dialect failures and no skips. **Measured limit
  worth not rediscovering: the full suite against a REMOTE Postgres is not
  viable — 29 tests took 11m29s**, because each store creation is a
  `CREATE SCHEMA` plus ~20 tables of DDL across the internet. The full-suite PG
  run therefore lives in the new CI job, where the database is on localhost.
  SQLite stays the default and the local test backend.
  **(5) The deploy was stopped by the user mid-sprint** — see "Next action". It
  had booted once first, and that is the definition-of-done item hardest to
  evidence otherwise: a container from this repo's Dockerfile, against an
  **empty** Postgres, logged `migrations_applied backend=postgresql+psycopg` then
  `startup_complete env=prod llm=NullLLM` and served `/healthz` 200 — the
  key-less path holding in a production configuration. No domain was ever
  generated, so it was never publicly reachable.
  **Also fixed: a pre-existing pinned-NOW time bomb that detonated mid-session.**
  `test_interview_org::test_revocation_closes_it_again` revoked at the wall clock
  and asserted at `NOW = 2026-08-01 12:00 UTC`; it passed at one point in this
  session and failed an hour later with nothing touching consent in between. The
  file's own `_grant` helper carries a comment warning about exactly this shape —
  the S7.2 review fixed the *grant* side and missed the *revoke* side. The other
  four `revoke_consent` call sites were checked; none pin NOW.
- **Prior sprint detail (PI-7):** **PI-7 COMPLETE — S7.3 (AI interview delivery v0) BUILT,
  REVIEWED and MERGED to main — 1024→1175 green, smoke_s73 18/18 OK exit 0,
  key-less.** The last sprint in PI-7, and the first to need a live model.
  **The framing that makes it veritas-shaped rather than a generic interview
  product: it asks the depth report's OWN probes.** `probe_generation` has been
  writing `CoherenceVerdict.probes` — "questions a fake can't survive" — for
  exactly the claims the pipeline could not settle, and until now nobody ever
  asked them. Delivered a new package `app/interview/` (peer of
  `app/verification/`): `schema.py` (`InterviewStatus`/`QuestionSource`/
  `AnswerChannel`/`InterviewBand`/`ProxyBand`; `InterviewQuestion`, `TurnScore`,
  `InterviewTurn`, `ProxyFinding`/`ProxyRisk`, `InterviewAssessment`,
  `InterviewSession`, **`InterviewSummary` — the org-facing projection, with no
  transcript or turns AS FIELDS**), `questions.py` (probes ▸ profile templates ▸
  domain seeds, deduped and capped; refuses below `interview_min_questions`
  rather than conducting an empty interview), `scoring.py` (4-axis rubric +
  aggregation + banding + the capped LLM adjustment), `proxy.py`, `session.py`
  (read-time `effective_status` + the shared `summarize`), `models.py`,
  `store.py`, `service.py`. Plus a new seam `app/services/speech.py` shaped like
  `llm.py`: `SpeechClient` / `OpenRouterSpeech` / `NullSpeech` / `build_speech`.
  Migration `0015_ai_interviews` — two tables, both CASCADE (sessions from
  candidates, turns from sessions), so **erasure needed no new path at all** and
  the metadata-wide drift/index/FK/nullability guards covered them for free.
  Five candidate-plane routes + one org-plane route; `MyData.interviews` +
  an `interviews` retention window; 20 `interview_*` knobs plus
  `ret_interview_session_days` and two `speech_*`; `INTERVIEWS.md` written.
  **The three decisions taken with the user before any code** (spec §0):
  (a) **the transcript is stored, the audio never is** — audio is transcribed in
  memory, its sha256 kept, the bytes discarded, because voice is
  biometric-adjacent; the transcript IS kept on the resume precedent, since an
  advisory score whose basis nobody can read is worse for the candidate than the
  PII cost; (b) **candidate-initiated with a consent-gated org read** under a
  **new `ConsentPurpose.INTERVIEW_READ`** — a new purpose, NOT a third widening
  of `VERIFICATION_READ`, whose dated window S7.2 declared shut (a test pins it:
  an org holding `verification_read` is still refused the interview endpoint);
  (c) **real ASR, deferred TTS** — candidates answer by audio, questions arrive
  as text, because OpenRouter serves no TTS and `kokoro` is a GPU dependency
  neither the offline suite nor the key-less smoke could exercise.
  **Design invariants:** the scorer is **neutral when unknown (0.5, never 0)** on
  every axis — a scorer that confuses "no yardstick" with "shallow answer"
  punishes candidates for gaps in the question bank; an answer under
  `interview_min_answer_words` scores **nothing**, which is not the same as
  scoring zero; **the LLM is a nudge, never the grader** (capped at
  `interview_llm_max_delta`, cannot introduce a dimension, rescue an
  insufficient answer, or produce a band — the S2.1 pattern), and `NullLLM`,
  bad JSON and exceptions all leave the deterministic score standing;
  **`InterviewBand` is deliberately NOT `DepthBand`** though the members match,
  because a resume-depth band and a live-interview band must never be silently
  fused (S7.2's two-ladders lesson applied to two scores) — nothing feeds
  `depth_score` or `fabrication_risk`, it stands beside them; **no voice
  biometrics, as a decision** (a voiceprint is biometric data needing a stored
  embedding — the artifact class S7.1 made impossible — plus its own consent
  purpose and legal review), so the proxy signal is the assurance level
  **stamped at session start and never recomputed**, plus timing and stylometry,
  banded `low|moderate|elevated` with `elevated` requiring two soft findings and
  **no finding permitted to be `hard`**; **the assessment IS stored** — the one
  deliberate departure from the read-time roll-up rule, argued explicitly in the
  spec (assurance and claim evidence depend on the clock and on later rows, so
  storing them would store a lie; an assessment is a closed fact about a
  finished session, and recomputing would re-hit a paid model), stamped with
  `scorer_version`. **The whole-branch review (inline) found TWO Importants,
  both reproduced before being fixed, and both are the house bug shapes for the
  THIRD sprint running:** **(1)** the ASR transcript was **unbounded** — the text
  channel refuses past `interview_max_answer_chars` but the audio channel stored
  whatever the provider returned (a berserk client wrote 2 MB into the one Text
  column on the table). That is S7.2's `claim_ref` finding exactly: *a bound that
  holds on one path and not the other is no bound.* Now truncated rather than
  refused (the candidate did nothing wrong) and **disclosed** on the turn as
  `transcript_truncated`. **(2)** a stored `assessment` this code cannot parse
  raised `ValidationError` on **every later read**, so one bad write would brick
  a candidate's own `/portal/me` **forever** — the same permanent-DPDP-denial
  shape S7.2 closed with `METHOD_LEVEL.get`. Now degrades to "no assessment" and
  logs; not candidate-reachable today, but `scorer_version` exists precisely so
  the shape CAN change. **Live model verification (2026-08-01):**
  `mistralai/voxtral-small-24b-2507` reached LIVE through `OpenRouterSpeech` —
  request path, mime→format mapping and response parsing all verified. **It also
  exposed a hazard worth recording: voxtral hallucinates on non-speech audio**
  (handed a 440 Hz tone, it returned fluent confident prose). Bounded here
  (the candidate reads their own transcript, scores are advisory) but any future
  ASR adapter wants a no-speech guard — logged in `MODELS.md` and
  `INTERVIEWS.md` §12. The smoke now pins `DEE_OPENROUTER_API_KEY=""` because it
  claims to prove the no-key path and a developer with a real key in `.env` was
  silently shipping junk audio to a live vendor.
  **Smoke `scripts/smoke_s73.py` (uvicorn, key-less) 18/18 OK** exit 0: no
  interviews → start (plan from the candidate's own profile) → second start 409
  → **audio 422 `speech_unavailable`** → and no turn recorded → text answer
  scored → wrong `question_id` 409 → oversize 422 → completion with an advisory
  assessment → proxy shows `identity_assurance_none`, nothing `hard` →
  **self-attest then a NEW session stamps assurance 1 while the finished one
  still reads 0** → org 403 → grant `interview_read` → 200 (`attempts` = the
  completed session only) → **the transcript is absent from the org body and
  present in the candidate's own** → revoke → 403 → `/portal/me` lists
  interviews + the retention window → access log shows `interview.query` with
  the org name → `DELETE /portal/me` → org read 404.
- **Prior sprint detail (S7.2):** **S7.1 (Verification spine + consent-first
  identity) COMPLETE and MERGED to main — 784→887 green, smoke_s71 19/19 OK
  exit 0, key-less — no LLM, no network.** The whole-branch review (inline; the
  harness in these sessions forbids spawning agents unless asked) found **two
  Critical privilege escalations, both reproduced over HTTP with nothing but a
  candidate's own key, both now closed and covered by tests + smoke checks**:
  (1) `POST /portal/verifications` accepted **any** `VerificationMethod`, so a
  candidate could POST `manual_review` and self-award **L3 REVIEWED** — a level
  whose entire meaning is "an operator looked"; (2) worse, `government_id` was
  reachable for **L4**: the candidate self-grants `IDENTITY_VERIFY` from the
  portal (S6.4 first-party consent, working as designed), the spine's
  third-party gate passes, and because **the spine performs verifications itself
  and never calls into an adapter**, `GovernmentIdAdapter.start`'s
  `NotImplementedError` could never fire — the route's
  `except NotImplementedError → 422` was dead code and "declared but inert" was
  false as shipped. The root cause was shared and structural: `start()` treated
  **"not challenge_based" as "complete it now, VERIFIED"** — a fail-open default
  — and the tests proved the third-party gate only against a
  `_FakeThirdPartyAdapter` while the real, routable method went untested
  end-to-end. **Fix (in the spine, where the other gates live):** the adapter
  seam gained `self_service`/`implemented`/`instant`, **all defaulting to the
  REFUSING answer on `_Base`** so a new adapter is inert until it declares what
  it is; `start()` is now explicitly the candidate-initiated entry point and
  checks `self_service` → `implemented` → third-party consent → destination
  binding (**consent is necessary, never sufficient** — the candidate can grant
  it to themselves), and refuses to mark anything VERIFIED on request unless the
  adapter declares `instant` (only `self_attested` does). `manual_review` is
  `self_service=False` → **403**; `government_id` is `implemented=False` →
  **422**. Two further review fixes: the **OTP resend cooldown and challenge
  supersession were scoped to one verification row, which rate-limited nothing**
  (the plane mints a fresh verification per start, so a stolen key bought
  unlimited codes and unlimited guess-batches against a 6-digit code) — now
  scoped to **candidate + channel**, plus `hmac.compare_digest`; and an
  operator-recorded manual review audited as `actor_type="candidate"`, i.e. the
  candidate's own DPDP access log told them **they** did what an operator did —
  now `"system"`. 10 review tests added (877→887). Delivered a new pure package
  `app/verification/` (peer of `app/portal/`/`app/profile_sources/`): `schema.py`
  (`AssuranceLevel` **IntEnum** 0–4 so "highest level held" is a `max()`;
  `VerificationMethod`/`VerificationStatus`; `METHOD_LEVEL`; `Verification`;
  `IdentityAssurance`), `assurance.py` (pure clock-injected `is_expired`/
  `effective_status`/`compute_assurance` — **expiry is computed at read time**,
  never written by a job, because no scheduler exists and a stored `expired`
  would be a lie nobody corrects; lapsed methods are reported separately so the
  portal can prompt a re-verify instead of showing an unexplained downgrade),
  `otp.py` (pure code-gen/hash/TTL/attempt/cooldown arithmetic under an injected
  RNG + `Notifier` protocol with a `NullNotifier` that logs **neither** the code
  nor the destination), `methods.py` (adapter seam + registry), `models.py`,
  `store.py`, `service.py`. Migration `0013_identity_verification` — two tables,
  both candidate CASCADE: `verifications` (durable outcome) and
  `verification_challenges` (short-lived secret material, deliberately separate);
  drift/index/FK/nullability guards extended (the nullability guard **caught a
  real drift** during the build — `details` was `nullable=True` in the migration
  vs `Mapped[dict]` NOT NULL in the ORM; migration corrected). **Ladder shipped:**
  L1 `self_attested` · L2 `otp_email`/`otp_phone` (contact-control) · L3
  `manual_review` (**admin plane only** — `self_service=False`) · L4
  `government_id` **declared but inert** — inertness is `implemented=False`
  **enforced by the spine**; the adapter's `NotImplementedError` is only a
  backstop, since the spine never calls an adapter to do the work (precisely how
  the escalation above got in). **Two new `ConsentPurpose`
  members** (first taxonomy addition since S3.1): `IDENTITY_VERIFY` (gates any
  `third_party` adapter — enforced in the SPINE, not in adapters, and proven by a
  `_FakeThirdPartyAdapter` in tests) and `VERIFICATION_READ` (org disclosure,
  query-time enforced + **every attempt audited allowed or denied**, mirroring
  `query_records_for_org`). Six endpoints across three planes: candidate
  (`POST /portal/verifications`, `POST /portal/verifications/{id}/confirm`,
  `GET /portal/verifications`; `MyData` gained `identity`), org
  (`GET /verification/candidates/{id}/assurance`), admin
  (`POST /candidates/{id}/verifications/manual-review`). `verif_*` config knobs +
  `ret_verification_days`. `VERIFICATION.md` written. **Design invariants:**
  (a) **the "never store a document" rule is STRUCTURAL** — neither table has any
  column able to hold an artifact, the sole evidence field is a sha256
  `evidence_digest`, so a future govt-ID adapter cannot persist one without a
  migration a reviewer would see (asserted by tests in both schema and models);
  (b) **first-party self-service needs no grant** — the S6.4 principle holds,
  acting on your own data is a data-principal right, not a disclosure;
  (c) **destination binding** — the `candidates` table stores only
  `email_hash`/`phone_hash`, so the candidate supplies the OTP destination and
  the spine normalizes+hashes it and requires a match against the hash on file
  (proves they know the contact, works regardless of what extraction retained,
  and the raw value stays transient — only the hash is written);
  (d) **cross-candidate isolation is structural** — every candidate-plane handler
  resolves `candidate_id` from the key, never a path/body param; another
  candidate's verification is an indistinguishable 404. **Challenge hygiene is a
  deliberate exception to the deferred PI-8 sweep:** consumed/superseded OTP rows
  are actually DELETED on paths that already run — that is short-TTL secret
  material, not a retention policy (supersession + cooldown scoped **per
  candidate+channel**, post-review). 103 new tests (**784→887**, `pytest -q`
  green). Smoke `scripts/smoke_s71.py` (uvicorn, key-less) **19/19 OK** exit 0:
  candidate starts at level 0 → self-attest → L1 → OTP to a contact NOT on file
  400 → OTP to the real contact → wrong code 400 → correct code → L2 →
  **candidate self-awarding `manual_review` 403 → candidate self-grants
  `identity_verify` then `government_id` 422 → level still 2** → org read 403 →
  grant `verification_read` → 200 (and no evidence internals in the payload) →
  revoke → 403 → admin manual review → L3 → `DELETE /portal/me` → org read 404.
  **PI-6 (candidate side & intake) remains COMPLETE and is merged to main**
  (`814e845`, 784 green) — S6.1 GitHub · S6.2 LinkedIn export · S6.3
  normalization curation loop · S6.4 candidate auth + DPDP portal. Historical
  PI-6/PI-5 detail follows below.
- **Prior sprint detail:** **S6.4 (Candidate auth + DPDP portal)
  BUILT on branch `s64-candidate-auth-dpdp-portal` — 752→784 green, smoke_s64
  10/10 OK, key-less — no LLM, no network, no new `ConsentPurpose`; PENDING
  final whole-branch review + merge (not yet on main).** Delivered: migration
  `0012_candidate_credentials` (candidate CASCADE FK, unique on
  `candidate_id`; drift/index/FK/nullability guards extended);
  `CandidateStore.issue_access_key`/`authenticate_candidate` (mint/rotate a
  sha256-hashed opaque key, mirrors org API keys); `require_candidate`
  dependency + a new dependency-free `candidate_router` (peer of `router`/
  `org_router`); admin-plane `POST /candidates/{id}/auth-key` (mint, returned
  once, 200/404/401); a new pure package `app/portal/` (`schema.py` —
  `MyData`/`AccessLogEntry`/`ConsentView`/`ReportRef`/`RetentionWindow`+
  `RetentionPolicy`; `retention.py` — pure `retained_until` +
  `build_retention_policy`; `service.py` — `PortalService` composing
  `CandidateStore`+`LedgerStore`+`ProfileSourceService`+`ReportStore`, owns no
  tables); `Services.portal` wired cycle-safe; `LedgerStore.consents_for_candidate`
  + `get_grant` (small raw-read additions); config knobs
  `candidate_access_key_bytes` (32) + six `ret_*_days` (resumes 1095,
  interview records/coding rounds/observed offers 1825, profile sources 1095,
  audit log 2555). Six candidate-plane endpoints (`X-Candidate-Key`):
  `GET /portal/me` (access), `GET /portal/access-log` (transparency,
  newest-first, includes platform-internal actions),
  `GET /portal/consents` + `POST /portal/consents` +
  `POST /portal/consents/{id}/revoke` (consent control, ownership-enforced —
  unknown-or-not-owned both 404, no probing), `DELETE /portal/me` (erasure,
  reuses the existing hard-delete path; key 401s after). **Design invariant:
  no new `ConsentPurpose`** — self-access is the data-principal right itself,
  not an org-consent-gated disclosure, so `require_candidate` alone gates
  every route; cross-candidate isolation is structural (every handler
  resolves `candidate_id` from the key, never a path/body param). **Two
  deferred decisions (confirmed with user):** (a) `/portal/me` lists reports
  by existence + timestamp only (`ReportRef`) — depth `Report` internals
  (fabrication_risk, verdicts) are not disclosed to the subject in v0; (b)
  the access-log includes platform-internal actions (e.g.
  `feature.materialize`), not just org disclosures. Retention posture is
  surfaced (`RetentionPolicy.sweep_active=False` always) — the mechanical
  purge job is deferred to PI-8 (no scheduler exists yet). `PORTAL.md`
  written (peer of `LEDGER.md`/`DASHBOARD.md`). 32 new tests (752→784,
  `pytest -q` green). Smoke `scripts/smoke_s64.py` (uvicorn, key-less) 10/10
  OK exit 0 (the smoke commit's subject stales-reads "(12/12)" — the correct,
  verified count is **10/10**): create candidate → admin mints a key →
  `GET /portal/me` shows profile/resumes/retention → org submits + queries an
  interview record (consented) → `GET /portal/access-log` shows it with the
  org's name resolved → first-party `POST /portal/consents` grant →
  `GET /portal/consents` active → revoke → state `revoked` → wrong/absent key
  401 → a second candidate's key cannot see or revoke candidate 1's data
  (404, untouched) → `DELETE /portal/me` erases; key then 401s; admin
  `GET /candidates/{id}` 404. Executed subagent-driven (fresh implementer +
  review per task across 10 build tasks + this closeout); two plan-text
  inaccuracies self-corrected during the build (Task-8 route-existence test
  ordering; Task-9 a shared-email test helper collapsing two candidates via
  the S1.1 dedup path). Commits `f3646ca..4bdbdb6` (Tasks 1–10; spec
  `a0450d5`, plan `d2737f6` precede). Deferred minors carried (all DEFER,
  none merge-blocking): unused `datetime` imports in
  `tests/test_ledger_consents_for_candidate.py` (F401); two API test helpers
  use `client.__enter__()` without `__exit__()` (thread-leak, no correctness
  impact); the smoke commit subject's stale "(12/12)"; the `no_key_401` smoke
  check exercises absent-key only (wrong-key is covered by a unit test).
  **PI-8 follow-ups (spec §9):** mechanical retention sweep; real candidate
  registration (password/OTP/session); exposing depth-`Report` internals to
  the candidate; DPDP correction/rectification right; grievance/DPO contact
  endpoint; multi-credential/device sessions. **PI-6 status: COMPLETE** — S6.1
  GitHub [done] · S6.2 LinkedIn export [done] · S6.3 normalization curation
  loop [done] · **S6.4 candidate auth + DPDP portal [done, this sprint —
  pending final review + merge]**. S6.3 (normalization curation loop) remains
  COMPLETE — historical detail below and in the session log. S6.2 (LinkedIn
  export parsing) remains COMPLETE — historical detail below and in the
  session log. S6.1 (GitHub-as-signal) remains COMPLETE — historical detail
  below and in the session log.
  PI-5 (demand side) remains COMPLETE (S5.1–S5.3); historical S5.3 detail follows.
  S5.3 added a pure `app/dashboard/` composition layer (no tables/migration/LLM/new
  consent purpose) exposing three org-plane read-models: `GET /dashboard/overview`,
  `GET /jobs/{id}/board` (requisition + comp benchmark + top-N match), and
  `GET /candidates/{id}/card` (consent-gated per-section drill-in, 200 with per-section
  status, audit-by-reuse). API-first JSON only; no candidate PII, no depth-report
  exposure. Advisory.
- **Next action:** **S8.4 IS COMPLETE (both phases merged), the SCREENING
  SCREENS ARE WIRED (S8.5, merged 2026-08-10 `eed3d95`), and THE OUTCOME LOOP
  IS CLOSED (branch `s86-org-outcome-route`, 2026-08-10). 1586 green,
  `smoke_s85_outcome` 21/21. NOT yet pushed to the public remote — push when
  the user says so.**
  Per the PI-8 re-sequence (S8.2 → S8.4 → UI → integrate → S8.3 → deploy) the
  next work is:
  (1) ~~An org-plane route for recording an outcome~~ — **DONE.** Two org-plane
  routes, migration `0020` (outcome authorship), the report screen's four
  buttons restored. The admin route stays where it is: it is the operator's
  cross-tenant support view, and a test pins that it still 401s an org session
  — which is *why* the twin had to exist.
  (2) **Then S8.3** — its named inputs so far: rate limiting (bounded-per-call
  is not bounded-per-caller), the `ret_batch_item_days` sweep, **in-place
  retry of failed items** (the text is retained for a capability S8.3 must ship
  or the retention loses its justification), observability, and the retention
  sweeps deferred since S6.4/S7.1.
  **Still unwired, and each for a stated reason** (UI.md §4, status board S8.5):
  instant check `/evaluate` and the operator console are admin-plane; the
  interview runner is candidate-plane. All three carry a "sample data" chip.
  **Deferred out of S8.4 Phase B, deliberately:** no cross-batch queue
  (`SCREENING.md` §8). Phase plans, for reference:
  `docs/superpowers/plans/2026-08-06-s84a-upload-ownership.md` and
  `docs/superpowers/plans/2026-08-07-s84b-screening-surface.md`.
  **Verifying the UI after any change to it** (there is no CI for `frontend/`):
  `node scripts/check_ui_bindings.js` · `python
  scripts/check_ui_screening_contract.py` · `python
  scripts/check_ui_screening_browser.py`.
- **Long-range planning:** the current audit is
  **`docs/superpowers/specs/2026-08-01-veritas-gap-analysis-v2.md`** (post-PI-7
  re-audit, measured not remembered). It **supersedes** the 2026-07-26 vision
  gap analysis, which is kept as the dated record of the PI-5→PI-6→PI-7 call but
  is four PIs stale in its asset inventory. **v2's three corrections matter for
  PI-8:** the Postgres cutover is only half low-risk (`report_store.py` is raw
  `sqlite3` outside Alembic and holds the human `outcomes` — a rewrite, not a
  connection string); the flywheel is **redundant**, not merely unconsumed (S4.4
  derives labels from the ledger instead, so the question is delete-or-repurpose);
  and the calibration harness is **much smaller than assumed** — S4.2 features ×
  S4.4 leakage-free labels already exist, only the metrics are missing. v2 §5
  proposes reordering PI-8 to put calibration first **and states the honest
  counter-argument** (a harness needs real outcome data, which needs a pilot org).
  Consult it whenever a PI completes; it never overrides the "Next action" above.
- **Open residuals (carried, all DEFER — none merge-blocking; see
  `.superpowers/sdd/progress.md`):** from S3.2 — `append_event` is ownership-only
  and intentionally inherits the submit-time `ledger_write` grant (documented in
  LEDGER.md — decide whether to re-gate on live consent); `create_organization`'s
  broad `except IntegrityError` maps any violation to "name exists" (only `name`
  is insert-reachable-unique today); `consent.py`/`store.py` module docstrings
  still carry "(S3.1)" framing; `revoke_consent` endpoint returns 200
  `{revoked:false}` for an unknown consent_id (no 404); 0004 downgrade (SQLite
  batch recreate) is untested. **S3.3 adds no new residuals.**
- **Last session (2026-07-25):** S3.3 executed inline TDD-offline on branch
  `s33-coding-round-results` (6 tasks). Delivered per plan: a standalone
  `coding_round_results` table (peer of `interview_records`, NOT an overload of
  it) with CASCADE FKs to candidates/organizations/consent_grants; contracts
  `CodingPlatform` StrEnum (hackerrank/codility/leetcode/codesignal/hackerearth/
  internal/other) + `CodingRoundResult` (platform, platform_name?, assessment_name?,
  score, max_score?, percentile? [0–100], problem_tags[], taken_at, raw{}) with
  pydantic bounds as data hygiene only — NO scoring; migration
  `0005_coding_round_results` (+ drift/index/FK-ondelete/nullability guards
  extended to the new table); store methods mirroring interview records —
  `submit_coding_round` (`ledger_write`-gated → ConsentError, stamps consent_id,
  audits `coding_round.submit` in-txn), `query_coding_rounds_for_org` (query-time
  `ledger_read` enforcement, audits every attempt allowed/denied as
  `coding_round.query`), `coding_rounds_for_candidate` (raw ungated read for
  PI-4); two org-plane endpoints (`POST /ledger/coding-rounds`,
  `GET /ledger/candidates/{id}/coding-rounds`) → 403/404/401/422; LEDGER.md S3.3
  section. **Consent reused** (`ledger_write`/`ledger_read`) — no new taxonomy.
  No new config knob, no LLM, no scoring. 20 new tests (422→442, `pytest -q`
  green). Smoke `scripts/smoke_s33.py` (uvicorn HTTP) 7/7 OK exit 0: submit-403
  → grant-write → submit → query-403 → grant-read → query-200 → DPDP-erase →
  query-404 (run happened to exercise the LIVE LLM extraction path too). Merged
  to main (fast-forward from 4f63cdc), 442 green on main, branch deleted. S3.3
  COMPLETE. Next: S3.4 plan (cross-company reputation).
- **Prior session (2026-07-22):** S3.2 executed subagent-driven, 11 tasks +
  whole-branch review, branch `s32-ledger-apis`. Delivered: two HTTP auth
  planes over `LedgerStore` — ADMIN plane (`X-API-Key` on `router`: org
  lifecycle + consent grant/revoke/status) and ORG plane (`X-Org-Key` → one
  org via `authenticate_org` on a dependency-free `org_router`: record submit
  [write-consent gated], event append [ownership-enforced], and
  `GET /ledger/candidates/{id}/records` with **query-time `ledger_read`
  enforcement + audit of every read attempt, allowed or denied, in-txn**).
  Org API keys (sha256-hashed, rotatable; migration `0004_org_api_keys` +
  unique index) with `ledger_api_key_bytes` knob (default 32, ge=16). All four
  S3.1 residuals closed: deterministic authorizing-grant selection
  (org-specific ▸ newest ▸ lowest id), `consent_status` 404-vs-403 shape,
  `create_organization` IntegrityError→ValueError (no TOCTOU), drift guard
  extended to indexes/FK-ondelete/nullability. `Services.ledger` injected
  (shares the candidate DB). 29 new tests (393→422). Smoke
  `scripts/smoke_s32.py` (uvicorn HTTP) 9/9 OK exit 0: admin gate → org+key →
  submit-403-without-consent → grant → submit → event → query-403-without-read
  → grant read → query 200 → revoke → query 403 → DPDP erase → query 404. Per
  task: fresh implementer + spec/quality review; final whole-branch review
  (opus) Ready-to-merge Yes, no Critical/Important code defects, all 13
  accumulated Minors DEFER; two recommended doc notes added (event-append
  grant inheritance, cross-org read blast radius). Merged to main
  (fast-forward 7a9fdcf→a948401), 422 green on main, branch deleted. S3.2
  COMPLETE. Next: S3.3 plan.
- **Prior session (2026-07-20):** S3.1 executed subagent-driven, 7 tasks,
  branch `s31-ledger-consent`. Delivered: `app/ledger/` package (Pydantic
  contracts + StrEnum taxonomies, pure clock-free consent logic in
  `consent.py`, ORM rows on the shared Base, migration
  `0003_evaluation_ledger` with CASCADE FKs), `LedgerStore` (organizations
  CRUD; grant/revoke/status consent; `submit_interview_record` gated by
  `ConsentError` and stamped with the authorizing grant; `append_event`;
  `records_for_candidate`/`events_for_record`/`audit_for_candidate`; every
  mutation audited in the same transaction), config knob
  `ledger_consent_default_ttl_days` (365), DPDP erasure cascades ledger rows
  via the migration's CASCADE FKs while organizations survive, `LEDGER.md`.
  42 new tests (350→392). Two deviations from plan: (a) migration 0003
  landed in Task 3 rather than later, because the metadata-wide drift guard
  requires it once ledger models are imported; (b) store converters
  normalize datetimes via `as_utc` because SQLite refetch returns naive
  datetimes and pydantic equality broke — the plan's converter code was
  fixed accordingly. Smoke `scripts/smoke_s31.py` 10/10 OK key-less
  (heuristic extraction), exit 0. Final whole-branch review: Ready to merge;
  its one Important finding fixed in 4dd09d0 (caller-supplied non-UTC
  datetimes now coerced via `as_utc` at write — SQLite drops tzinfo, so an
  IST revocation would otherwise land 5.5h late = fail-open window once
  S3.2 accepts API datetimes; + org-delete cascade documented, TTL knob
  ge=1). 393 tests. Merged to main (fast-forward to 4dd09d0), branch
  deleted. S3.1 COMPLETE. Next: S3.2 plan.
- **Prior session (2026-07-18):** S2.4 done on branch `s24-fabrication-risk`
  — PI-2 COMPLETE. Unified advisory fabrication_risk: pure fusion in
  `app/fabrication/risk.py` (band→risk code constants; 0.7·weighted-mean +
  0.3·max blend; coverage confidence so single-subsystem fusion never
  asserts; ELEVATED needs ≥2 flags, MODERATE needs a flag or ≥2 non-clean
  — the latter gate added mid-session after the live smoke caught a genuine
  resume banding moderate off one soft LLM signal), fused in the scoring
  node (depth/verdicts provably untouched), `Report.fabrication_risk` +
  moderate/elevated summary note + flywheel `record_type:
  "fabrication_risk"`, config `fr_*`. 350 tests green; smoke
  `scripts/smoke_s24.py` 10/10 key-less AND live.

## Status board

Legend: `[ ]` not started · `[~]` in progress · `[x]` done

```
VERITAS — TALENT INTELLIGENCE PLATFORM  (Indian-market Mercor, trust layer first)
│
├── PI-1  CANDIDATE DATA BACKBONE
│   ├── [x] S1.1  Prod-grade extraction schema + extractor
│   │            CandidateProfile: identity, contact(hashed), education[],
│   │            experience[], skills[], projects[], certifications[], links[];
│   │            per-field confidence + source-span provenance;
│   │            LLM extraction + deterministic fallback
│   ├── [x] S1.2  Candidate store — SQLAlchemy + Alembic on SQLite (PG-shaped);
│   │            candidates / resumes(versioned) / extractions;
│   │            identity resolution via email+phone hash dedup
│   ├── [x] S1.3  API + engine wiring — POST /candidates (upload → extract →
│   │            store → auto depth-eval); reports linked to candidate_id
│   └── [x] S1.4  India normalization — skill taxonomy, degree/CGPA normalizer,
│                institution + employer canonicalization, city/notice-period
│
├── PI-2  FABRICATION DEFENSE 2.0
│   ├── [x] S2.1  AI-generated-resume signals — ai_signals node after ingest
│   │            (deterministic stylometry ⊕ capped LLM), advisory band on Report
│   ├── [x] S2.2  Cross-field forensics — cross_field node (deterministic
│   │            timeline/coherence checks over the extracted profile),
│   │            advisory findings on Report
│   ├── [x] S2.3  Resume-farm detection — MinHash near-duplicates across
│   │            candidates (resume_fingerprints table, API-layer detection,
│   │            advisory Report.resume_farm)
│   └── [x] S2.4  Unified fabrication_risk score fused into calibration +
│                Report; still advisory, never auto-reject
│
├── PI-3  EVALUATION LEDGER (cross-company)                         [COMPLETE]
│   ├── [x] S3.1  Ledger schema + DPDP consent model — organizations,
│   │            interview_records, evaluation_events, consent_grants
│   │            (purpose-scoped, revocable, audited)
│   ├── [x] S3.2  Ledger APIs — submit/query with consent enforced at query
│   │            time; org-scoped API keys; audit trail
│   ├── [x] S3.3  Coding-round results — schema + ingest ONLY (far point):
│   │            platform, problem tags, score, percentile
│   └── [x] S3.4  Cross-company reputation — Bayesian aggregation with
│                recency decay + per-org reliability weight
│
├── PI-4  ML FEATURE STORE & RANKING                               [COMPLETE]
│   ├── [x] S4.1  Feature registry (versioned definitions over candidate +
│   │            eval + ledger data)
│   ├── [x] S4.2  Materialization → wide ml_features table + CSV/parquet
│   │            export; point-in-time correct (no label leakage)
│   ├── [x] S4.3  Talent search/ranking API (filters + composite score)
│   └── [x] S4.4  Training-set export — features ⋈ outcomes (flywheel+ledger)
│
├── PI-5  DEMAND SIDE                                         [COMPLETE]
│   ├── [x] S5.1  Job/requisition schema + role-conditioned match-ranking
│   │            (org-plane; compile-to-ranking + skill-coverage; comp band
│   │            metadata-only; audit-every-match, no new consent gate)
│   ├── [x] S5.2  Comp intelligence v0 (static bands + ledger-observed offers,
│   │            advisory) — consumes S5.1's stored comp_band
│   └── [x] S5.3  Thin employer dashboard (read-only over search/reports)
│            org-plane read-models: /dashboard/overview + /jobs/{id}/board +
│            /candidates/{id}/card; lean board + consent-gated drill-in card;
│            pure app/dashboard/ composition, no new state/consent/LLM
├── PI-6  CANDIDATE SIDE & INTAKE                                  [COMPLETE]
│   ├── [x] S6.1  GitHub-as-signal — pure app/profile_sources/ spine + GitHub
│   │            adapter (fetch → pure to_signal transform w/ S1.4 taxonomy
│   │            mapping + bounded confidence → append-only store, candidate
│   │            CASCADE); admin-plane POST/GET endpoints; advisory, no LLM,
│   │            no new consent purpose
│   ├── [x] S6.2  LinkedIn export parsing (2nd profile_sources adapter) — base64-
│   │            ZIP upload → pure parse_linkedin_export/to_signal, conservative
│   │            0.4/0.6 self-report-vs-corroborated confidence, de-identified
│   │            LinkedInActivity, discriminated activity union w/ back-compat
│   │            validator (no migration); admin-plane POST endpoint; advisory,
│   │            no LLM, no network, no new consent purpose
│   │            [multilingual/Hinglish intake DEFERRED — English-first, 2026-07-26]
│   ├── [x] S6.3  Normalization curation loop — human-in-the-loop taxonomy repair:
│   │            unmapped skill terms (canonical=None) from the GitHub + LinkedIn
│   │            adapters queue for admin review; map/create/ignore feeds a
│   │            deterministic normalize_skill overlay (static wins); candidate-
│   │            agnostic queue (no FK, survives erasure); no LLM, forward-only
│   └── [x] S6.4  Candidate auth + DPDP portal — candidate access-key auth
│                (X-Candidate-Key, mirrors org keys) + pure app/portal/
│                exposing access/transparency/consent-control/erasure; no new
│                consent purpose (self-access == identity of the subject)
├── PI-7  VERIFICATION & ASSESSMENT DEPTH                            [COMPLETE]
│   ├── [x] S7.1  Verification spine + consent-first identity — pure
│   │            app/verification/ (assurance ladder behind a method-adapter
│   │            seam; outcomes stored, documents/biometrics structurally
│   │            impossible); ships self-attest / contact-control OTP /
│   │            operator manual review, government_id declared-but-inert;
│   │            two new ConsentPurpose (IDENTITY_VERIFY, VERIFICATION_READ);
│   │            three planes; no LLM, no network, advisory only
│   │            [MERGED 2026-07-31; branch review caught + closed two
│   │             candidate-side ladder escalations — seam now refuses by
│   │             default: self_service/implemented/instant]
│   ├── [x] S7.2  Document forensics (experience letters/payslips) +
│   │            concurrent-employment advisory — SECOND PRODUCER on the S7.1
│   │            spine: `subject` discriminator + separate ClaimEvidence
│   │            roll-up (a payslip can never lift IdentityAssurance),
│   │            deterministic letter/payslip forensics (no LLM, no network),
│   │            candidate-plane first-party intake, EPFO declared-inert
│   │            (vendor, not legality, is the blocker). No new table, no new
│   │            ConsentPurpose, no new erasure path.
│   │            [MERGED 2026-07-31; 887→1011 green, smoke_s72 15/15. Branch
│   │             review caught + closed TWO more Criticals: a claim method
│   │             startable on the identity route (200 verified, then a
│   │             permanent 500 on the candidate's own portal) and an
│   │             unbounded `claim_ref` that stored 5031 chars incl. a salary
│   │             and a UAN. Also fixed a pre-existing test time-bomb.]
│   └── [x] S7.3  AI interview delivery v0 — the interview asks the depth
│                report's OWN probes (probe_generation's output, finally
│                asked); deterministic 4-axis rubric with an LLM allowed only
│                a capped +/-0.2 nudge; new app/services/speech.py ASR seam
│                (OpenRouter/voxtral live, NullSpeech refuses => text
│                interview); proxy risk from IdentityAssurance + behaviour,
│                NO voice biometrics; audio structurally unstorable, the
│                transcript stored and candidate-only; one new ConsentPurpose
│                (INTERVIEW_READ).
│                [MERGED 2026-08-01; 1024→1175 green, smoke_s73 18/18. Branch
│                 review caught + closed TWO Importants, both the house shapes
│                 again: an unbounded ASR transcript (bounded on the text path,
│                 not the audio one — S7.2's claim_ref) and an unreadable
│                 stored assessment that bricked /portal/me forever (S7.2's
│                 METHOD_LEVEL KeyError).]
└── PI-8  LAUNCH READINESS (in progress) — "what stops a real
    │   company onboarding without the operator hand-holding the database?"
    ├── [x] S8.1  Deployable spine — fail-CLOSED admin auth + boot refusal ·
    │            alembic upgrade head on boot (PG advisory lock) · reports +
    │            outcomes FOLDED into the main DB behind a real CASCADE ·
    │            Postgres (driver, pre-ping, DEE_TEST_DB_URL, CI job) ·
    │            deploy-ready (railway.json), deploy DEFERRED until the UI
    │            [1175→1200 green, smoke_s81 10/10; PG 18.4 verified for real:
    │             16 migrations up/down/up + 29 SQL-shaped tests; a container
    │             booted, migrated an empty PG and served /healthz before the
    │             deploy was stopped]
    ├── [x] S8.2  Identity & access — org_users/admin_users/auth_sessions/
    │            login_challenges (migration 0017) · email seam · email-OTP
    │            signup+login on all 3 planes · org + candidate self-serve ·
    │            operator accounts · CORS + CSRF · ONE resolver per plane +
    │            a route-table guard
    │            [1200→1373 green, smoke_s82 21/21, six regression smokes green;
    │             contract-pinning DROPPED (§5.5 superseded by the re-sequence)]
    ├── [x] S8.4  UI integration surface — COMPLETE. BOTH PHASES MERGED
    │            (A 2026-08-07 c678753; B reviewed + fixed + merged 2026-08-09)
    │            SPEC WRITTEN 2026-08-05, built as TWO BRANCHES from one spec
    │            (decision 0.5)
    │            ** PULLED AHEAD OF S8.3 (2026-08-02) **
    │            [x] spec: 2026-08-05-s84-ui-integration-surface-design.md
    │                UI.md's FIVE open questions ALL CLOSED with the user:
    │                  1 tenancy  => an org sees only what it UPLOADED.
    │                    Ownership is a property of the UPLOAD, not the person:
    │                    resumes.org_id + reports.org_id, nullable, SET NULL
    │                    (an org offboarding must not destroy a person's
    │                    resume). Candidates stay GLOBAL + deduped, so the
    │                    cross-corpus resume-farm signal survives. "My queue"
    │                    is DERIVED, not denormalized. Another org's report is
    │                    404, never 403.
    │                  2 plane   => ADD org-plane routes, KEEP the admin ones
    │                    as the operator's cross-tenant support view
    │                  3 batch   => a REAL stored object (screening_batches +
    │                    batch_items); status DERIVED at read time, never
    │                    stored
    │                  4 report  => the org sees the FULL report (verdicts,
    │                    missing_signals, probes); ONE redaction —
    │                    resume_farm.matches[] loses identity, keeps similarity
    │                  5 ingest  => CLIENT-DRIVEN. There is NO worker, no
    │                    scheduler and no BackgroundTasks anywhere in app/
    │                    (verified), and POST /candidates awaits the whole
    │                    9-node graph inline, so 500 resumes in one request is
    │                    not physically possible. Upload REGISTERS; a bounded
    │                    process call does the slow work; the UI polls.
    │            [x] Phase A — ownership: migration 0018_upload_ownership · a
    │                SCOPED FACADE + a guard test in the route-table-guard
    │                family (the tenancy rule is the one-entry-point bug shape
    │                by construction, so handlers get no option) · org-plane
    │                POST /screening/candidates, GET /screening/reports/{id},
    │                GET /screening/candidates/{id}/reports · ONE redacting
    │                projection shared by both readers · the org_name_taken fix
    │                [MERGED 2026-08-07; 1377→1434 green, smoke_s84a 23/23,
    │                 all regression smokes green. TENANCY.md written.
    │                 THE GUARD PAID FOR ITSELF ON DAY ONE: it caught a
    │                 CROSS-TENANT IDENTITY LEAK in the org UPLOAD RESPONSE
    │                 (real candidate_id/resume_id of OTHER customers, in both
    │                 the top-level resume_farm and the embedded report). The
    │                 read routes were redacted; the ingest response never was,
    │                 because spec §3.4 counted TWO org-facing readers and
    │                 there were three. Phase B must enumerate the FIELDS that
    │                 cross the boundary, not the HANDLERS that read people.
    │                 The branch review then found the same shape one branch
    │                 deeper: ingest() dropped org_id on the duplicate-text
    │                 path, so two agencies handed the SAME PDF left the second
    │                 owning nothing. And the guard itself was defeated by
    │                 naming a local `svc` instead of `services` — measured,
    │                 not argued. Both closed; the guard now AST-resolves
    │                 receivers and documents what it cannot see.
    │                 Also closed: FIVE smokes were making LIVE BILLED calls
    │                 (smoke_s23 ran past a 10-minute timeout before the pin).]
    │            [x] Phase B — screening surface: BUILT AND GREEN on branch
    │                s84b-screening-surface (2026-08-08/09). 1434→1542 green,
    │                smoke_s84b 16/16, all 16 smokes green.
    │                migration 0019_screening_batches (two tables + the
    │                case-insensitive org-name expression index) ·
    │                register/process/queue/summary/delete on the ORG plane ·
    │                the queue read-model built from batch_items ALONE, so no
    │                Report is ever on the org read path · ItemSignals scalars
    │                only (the row outlives its candidate: SET NULL) · opaque
    │                keyset cursor, carrying NO authority · ONE ingest core
    │                shared by the route and the batch processor, which took
    │                the scope guard's allowlist to EMPTY · admin
    │                POST /features/materialize · BOTH 422 sites become 200 +
    │                reason=no_materialized_candidates · comp returns ONE
    │                shape · OpenAPI: explicit operation_id everywhere and all
    │                38 untyped dict responses modelled, asserted by
    │                tests/test_openapi_contract.py · SCREENING.md
    │            MEASURED INPUTS from the wiring session (2026-08-03), all now
    │            folded into the spec §2:
    │              - org signup with a TAKEN org name => 202 + a real code that
    │                then verifies as 400 invalid_code. Blocks org self-serve
    │                onboarding (blocker 5). Fixed at BOTH doors: a 409 at
    │                signup (before a code is sent) AND a distinct refusal at
    │                verify, without re-opening the enumeration oracle — the
    │                property protected is "does this ADDRESS have an account",
    │                and an org NAME is not secret.
    │              - feature materialization has NO HTTP route, so
    │                GET /jobs/{id}/board is a PERMANENT 422 for a new org
    │              - CompBenchmark wraps the estimate, CompBandEstimate does
    │                not: two shapes for one set of numbers
    │              - POST /jobs 422s a requisition with no skills
    │            ⚠ BREAKS THE WIRED UI IN TWO PLACES, named in spec §4.7 rather
    │              than discovered at integration: org signup gains a 409 (the
    │              36/36 contract suite asserts "202 always" and will fail on
    │              purpose), and POST /comp/estimate changes shape (the UI
    │              already unwraps centrally, so this makes it correct).
    ├── [~] S8.5  UI BUILD (external, claude.ai/design) + INTEGRATION
    │            [x] UI built externally — frontend/, dark+light, 17 screens
    │            [x] WIRED 2026-08-03 (76cee48): frontend/api.js seam
    │                (window.VeritasAPI; no npm/bundler, outside CI) ·
    │                auth x3 planes · /auth/me boot · candidate DPDP portal ·
    │                devices · roles · comp · CSRF-vs-consent 403 fork on
    │                MEASURED detail strings · unwired screens labelled
    │                "sample data" · 36/36 contract + 9/9 browser + 27/27 CDP
    │                click-through; pytest 1377 unchanged
    │            [x] screens 2/4/5/6 (queue · summary · upload · batches)
    │                WIRED 2026-08-10 on branch s85-screening-ui-wiring, plus
    │                the report detail. Spec:
    │                2026-08-10-ui-screening-wiring-design.md. No app/ code
    │                touched (pytest 1553, unchanged).
    │                The client DRIVES the work and the screens say so: process
    │                is 5 items a call, there is no worker, so a sequential loop
    │                runs in the browser -- started on UPLOAD and never on
    │                navigation (every call bills a model), stopped by any error
    │                (no rate limiter until S8.3), and the copy states that
    │                closing the tab PAUSES the batch and reopening resumes it.
    │                The queue carries NO NAMES by design and says why; the
    │                header's bands come from /summary not from one page of
    │                /queue; paging hides while the driver runs because the sort
    │                key is mutable mid-run; the report's outcome buttons are
    │                GONE (admin-plane route, would 401).
    │                THREE VERIFICATION LAYERS, since frontend/ has no CI:
    │                  - check_ui_bindings.js  384/384 bindings resolved by
    │                    EXECUTING renderVals() over 8 states; non-vacuous
    │                    against 3 mutants (one survived v1: an `undefined`
    │                    field passes an `in` check and renders blank)
    │                  - check_ui_screening_contract.py  25/25 over real HTTP in
    │                    the BROWSER's posture (Origin + cookie + CSRF), which
    │                    smoke_s84b deliberately does not exercise
    │                  - check_ui_screening_browser.py  16/16 clicking through
    │                    headless Chrome over CDP, incl. a real file picker via
    │                    DOM.setFileInputFiles and every console error
    │                THE BROWSER LAYER FOUND A REAL DEFECT: the Delete button
    │                sits inside the clickable batch row, so arming a delete
    │                navigated away. Nothing else could have seen it.
    │            [ ] instant check (/evaluate) · operator console · interview
    │                runner — /evaluate STAYS admin past S8.4 by decision
    │                (candidate-less, so no owner to stamp); operator console is
    │                admin by nature; interview runner is candidate-plane
    │                MEASURED 2026-08-22, NO BLOCKER. It is FIVE screens, not
    │                three: MOCK_SCREENS names evaluate · interview · adminorgs
    │                · adminusers · curation ("operator console" is the middle
    │                three). Every route they need already answers a BROWSER
    │                -posture session (cookie + X-CSRF-Token + Origin) -- 12/12
    │                on a throwaway probe -- because require_api_key has been
    │                session-capable since S8.2, so an operator cookie clears
    │                the admin gate with no new backend work:
    │                  adminusers  GET  /admin/users              200
    │                  adminorgs   GET/POST /ledger/orgs           200
    │                  curation    GET  /curation/skills/unmapped  200
    │                  evaluate    POST /evaluate                  200
    │                  interview   GET  /portal/interviews         200
    │                              POST /portal/interviews         422 that
    │                              NAMES the precondition ("Add a resume or run
    │                              a depth evaluation first") -- the screen has
    │                              to show that, not an error box.
    │                ⚠ SCOPE DECISION OWED BEFORE WIRING INSTANT CHECK:
    │                /evaluate returns extraction_coverage: null (see S9.2's
    │                open items), so that screen's fabrication number reads
    │                empty with no caveat.
    │            [x] AN ORG-PLANE ROUTE FOR RECORDING AN OUTCOME — DONE
    │                2026-08-10 on branch s86-org-outcome-route (spec + plan +
    │                TDD, 9 commits). 1553→1586 green, smoke_s85_outcome 21/21,
    │                UI bindings 402/402 · contract 31/31 · browser 19/19.
    │                POST + GET /screening/reports/{id}/outcome(s) on the org
    │                plane; migration 0020 gives `outcomes` authorship
    │                (recorded_by · org_id · recorded_by_org_user_id).
    │                org_id SET NULLs like reports.org_id — an outcome is a
    │                LABEL the platform learns from, not the org's operational
    │                work product — and recorded_by exists BECAUSE of that:
    │                a null org must not read as "our own operator said this".
    │                ONE constructor (app/reports/outcomes.py) for BOTH doors,
    │                admin migrated to it FIRST; a test asserts the two doors
    │                refuse the SAME INPUTS, not that they call the same helper.
    │                notes bounded (max_outcome_notes_chars) at both doors, and
    │                the flywheel record lost `notes` at both doors — that sink
    │                has no erasure path. The GET returns THIS org's judgments
    │                only: the leak here is downward (an operator's internal
    │                note), never sideways. 404 on a WRITE, byte-identical to
    │                absence. OrgScopedReads -> OrgScopedAccess (it holds a
    │                write now); the guard's watched attribute is unchanged so
    │                it needed no edit. A THIRD writer to `outcomes` — the S8.1
    │                one-off importer — was caught by the full suite, not by
    │                the design.
    │            [x] STRUCK 2026-08-22 — "re-run the 36/36 contract suite" was
    │                an item against a script that does not exist and never
    │                did: `git log --diff-filter=A -- scripts/check_ui*`
    │                returns exactly three files, all still present. Its
    │                successor check_ui_screening_contract.py is 31/31 GREEN
    │                and bindings are 402/402 (both re-run on the merge). The
    │                409 it was supposed to break on is HANDLED --
    │                frontend/api.js:143 maps it to kind:"conflict" and
    │                errorCopy prints the API's own detail -- and pinned by
    │                tests/test_auth_org_name_taken.py +
    │                test_org_name_case_insensitive.py.
    ├── [x] S8.3  Operating safely — dual-scoped rate limits · metrics ·
    │            retention sweep · DPDP correction + grievance officer
    │            ** MOVED AFTER THE UI; still lands BEFORE the deploy **
    │            SPEC 2026-08-10, built as TWO BRANCHES from one spec (0.1):
    │              spec: 2026-08-10-s83-operating-safely-design.md
    │            [x] PHASE A — limits and metrics (branch
    │                `s83a-limits-and-metrics`, 13 tasks, 1586 -> 1665 green,
    │                smoke_s83a 19/19, all nine smokes green, 10/10 mutants
    │                dead). NOT YET REVIEWED OR MERGED.
    │                plan: 2026-08-10-s83a-limits-and-metrics.md
    │                - app/ratelimit/ (schema/models/store/service) + 0021
    │                - DB-backed counters, because an in-process limiter resets
    │                  on redeploy and is per-worker, and BOTH failures pass
    │                  every unit test. smoke check 6 restarts the server
    │                  against the same DB -- the only check that can tell.
    │                - enforced in the SERVICE layer: 8 OTP routes, 2 methods
    │                - dual-scoped, ALL scopes counted, ANY denial denies
    │                - counted BEFORE the has-an-account branch, so the 429 is
    │                  byte-identical for a known and an unknown address
    │                - X-Forwarded-For IGNORED unless trusted_proxy_hops > 0
    │                - auth_sessions.ip_hash was declared and NEVER populated;
    │                  the limiter's IP helper closes it
    │                - POST /screening/batches/{id}/retry: re-queues, does not
    │                  process; skips items whose text is gone
    │                - GET /metrics (admin-gated), labelled by route TEMPLATE
    │                - prod refuses to boot with rate_limit_enabled=false (6th)
    │                - new root doc OPERATING.md
    │            [x] PHASE B — retention and rights (branch
    │                `s83b-retention-and-rights`, 16 tasks, 1689 -> 1812 green,
    │                smoke_s83b 22/22, ALL 19 smokes green, 12/12 mutants
    │                dead). REVIEWED + MERGED 2026-08-12 at `6dfde6c`.
    │                plan: 2026-08-11-s83b-retention-and-rights.md
    │                - app/retention/ (plan/schema/sweep) + app/rights/
    │                  (schema/models/store/service) + migrations 0022, 0023
    │                - RETENTION_KNOBS 8 -> 11 classes and stays the SINGLE
    │                  source: the portal prints it, the sweeper reads it, and
    │                  a guard asserts set equality both ways
    │                - sweep_active DERIVES from config; it was a hardcoded
    │                  False telling every data principal that nothing purges
    │                - CLEAR mode for batch_item_text: the row survives, and
    │                  the predicate's second half (raw_text != '') is what
    │                  stops a preview reporting the same rows forever
    │                - dry-run parity by construction; cap + truncated; the
    │                  bulk delete's DB-level CASCADE is measured, not assumed
    │                - POST /admin/retention/sweep (dry by default, 409 when
    │                  disabled) + python -m app.retention.sweep --apply
    │                - reviewed correction queue: only full_name auto-applies,
    │                  email/phone refused BY NAME, extractions never rewritten
    │                - 0023: an applied correction PINS full_name, or the next
    │                  upload reverts it (found by the smoke)
    │                - public GET /grievance + the 7th boot refusal
    │                - _rate_limited(): four byte-identical 429 copies became
    │                  one before this added a fifth
    │                REVIEWED 2026-08-12: 5 findings, all fixed. The two that
    │                mattered were invisible to a green suite -- a test that
    │                passed in the file and FAILED ALONE (conftest never
    │                registered app/rights/models.py), and `?limit=-1` reaching
    │                SQLite as an UNLIMITED select on the complaints table. The
    │                registration guard then found SIX pre-existing gaps in
    │                alembic/env.py that would have made --autogenerate emit
    │                DROP TABLE for six live tables.
    ├── [x] S8.6  PRODUCTION SHAPE — correct to deploy, and NOT deployed
    │            RENAMED from "DEPLOY / launch" in the sprint itself. Zero
    │            customers, so a running host buys nothing and costs money,
    │            credentials and an attack surface; the user gates go-live.
    │            The sprint's output is a correct system plus the checklist a
    │            human runs later (DEPLOY.md). NO cloud resource was created.
    │            - the 8th boot refusal: prod cannot boot unable to send mail,
    │              and it asks build_email() rather than the provider STRING,
    │              because provider=smtp with an empty host returns NullEmail
    │            - the UI is served same-origin at /ui, so SameSite=None was
    │              retired for lax -- and the route-table guard gained MOUNTS
    │              first, because a Mount is not an APIRoute and would have
    │              been the guard's first invisible hole
    │            - the image never contained frontend/; .dockerignore can
    │              cancel a COPY, so a guard now reads BOTH lists
    │            - GET / derives its endpoints list at last (stale since S8.3)
    │            - the retention CLI died with a traceback on an unmigrated
    │              database -- the cron's most likely first encounter
    │            - CI builds the image for the first time ever (push only)
    │            - SMTPEmail delivered for the first time since it was written
    ├── [x] S8.7  SRC LAYOUT — a standard repository, and NO behaviour change
    │            BUILT + MERGED 2026-08-17 at `d0d8b56`. 1852 -> 1854 passing
    │            (the two new guards), 20/20 smokes, bindings 402 · contract
    │            31 · browser 19. NOT merged, NOT pushed, nothing deployed.
    │            The package KEEPS the name `app` (user declined the veritas
    │            rename), so 1,489 imports across 368 files are untouched and
    │            the diff is nine files, not every .py in the repo.
    │            - THE LIST BELOW WAS AN UNDERCOUNT: six listed, nine real,
    │              and all three extras fail SILENTLY
    │            - test_metrics.py's metric-name scan would have gone VACUOUS
    │              -- rglob over a directory that no longer exists yields
    │              nothing and the test passes while checking nothing
    │            - test_model_registration.py builds a DOTTED NAME from a
    │              path; relative_to(ROOT) would emit src.app.rights.models
    │            - the CI postgres job would have failed on the next push: its
    │              migrations step is a bare `python -` heredoc, so pythonpath
    │              does not apply and CI installs no project. Invisible
    │              locally, because the venv's editable .pth puts <repo>/src on
    │              sys.path for every process
    │            - the image MIRRORS the repo (COPY src/app ./src/app +
    │              PYTHONPATH=/srv/app/src). Flattening to ./app would put
    │              migrate.py's parents[3] at /srv, so alembic.ini is missing
    │              at RUNTIME, after the container reports itself started
    │            - the pure-move commit is deliberately RED and says so
    │            - NOT PROVEN: the container. No Docker here, image job is
    │              push-only, so the COPY and the PYTHONPATH are unexecuted
    │            ORIGINAL SPRINT NOTE FOLLOWS:
    │            USER-REQUESTED 2026-08-13. The motivation is REVIEWABILITY:
    │            S8.6's diff was 4,354 lines of which 2,711 were docs prose,
    │            so a reviewer spends most of its budget on markdown. With a
    │            src/ layout, `/code-review ultra src/` targets the core code
    │            and nothing else.
    │            THE CONTRACT: pure move. 1848 tests green before and after,
    │            all 20 smokes green, ZERO logic edits in the same commit as a
    │            move -- so `git log --follow` and a reviewer can both tell a
    │            rename from a change.
    │            CHEAPER THAN IT LOOKS, measured: the package KEEPS the name
    │            `app`, so all 1,299 `from app.` imports across 367 files are
    │            untouched. app/ -> src/app/ and the real work is six places:
    │              - pyproject.toml: [tool.hatch...].packages + pythonpath
    │              - Dockerfile: COPY app ./app (and test_image_contents' FLOOR)
    │              - tests/test_deploy_doc.py reads app/core/boot.py by path
    │              - tests/test_model_registration.py globs app/**/models.py
    │              - app/core/migrate.py:29  ROOT = parents[2] -> parents[3]
    │              - app/main.py:165  _ui_dir = parents[1] -> parents[2]
    │            ⚠ THE LAST TWO FAIL SILENTLY. `_ui_dir.is_dir()` means a wrong
    │            depth SKIPS the mount -- no error, just a UI that 404s. Both
    │            are covered (test_ui_mount, test_image_contents), which is why
    │            this sprint is safe to do mechanically and NOT before S8.6 is
    │            reviewed and merged.
    │            OPEN DECISION for the spec: rename the package `app` ->
    │            `veritas` at the same time? It is 1,299 mechanical edits the
    │            suite verifies, and doing it later means paying the
    │            disruption twice. Recommend deciding it in the spec, not mid-
    │            build.
    ├── [ ] GO-LIVE — unscheduled, USER-GATED. Not a sprint and has no ID.
             The checklist is DEPLOY.md; the blocking non-technical item is
             the IBM IP / outside-activity check (GTM §8.3). Also still open:
             alerting thresholds on /metrics, and the Railway cron for the
             retention sweep (the sweep still has no scheduler).
             SEQUENCED LAST BY THE USER, 2026-08-22: go-live happens only
             after local testing is finished, THE UI INCLUDED. Wiring the five
             remaining screens comes first.
        EXECUTION ORDER (user, 2026-08-02): S8.1 ✓ → S8.2 ✓ → S8.4 → UI →
        integrate → S8.3 → deploy. Sprint IDs are stable identifiers; only the
        order moved. S8.3 still precedes the deploy, which is now last, so the
        unthrottled OTP surface is never publicly reachable.
        WHOLE-PLATFORM hardening (all 63 endpoints, all 3 planes) + the first
        UI.  Blockers: gap-analysis v2 §9 (1) migrations-on-boot [DONE S8.1]
        (2) Postgres [DONE S8.1] (3) report-store rewrite [DONE S8.1]
        (4) candidate self-register [DONE S8.2] (5) org
        self-onboard [DONE S8.2] (6) retention sweep [DONE S8.3B]
        (7) rate limiting [DONE S8.3A] (8) observability [DONE S8.3A]
        — PLUS the two DPDP statutory rights (correction, grievance officer),
        promoted to RFP blockers by the GTM doc §8 [BOTH DONE S8.3B].
        ** WITH S8.3 PHASE B MERGED, EVERY NAMED BLOCKER IS CLOSED and S8.6 is
        the only sprint left in PI-8. **
        GTM: sell the FRAUD-SCREEN wedge to staffing agencies; ledger off the
        pitch.  See 2026-08-01-veritas-gtm-positioning.md.
        PI-9 = calibration harness, gated on PI-8 landing real orgs.
        STANDING NON-GOALS: payments/payroll/contracts, sourcing/outreach,
        native coding assessments (revisit post-PI-8)

PI-9  SIGNAL QUALITY — "do any of the seven advisory
 │    numbers predict what a human concluded?"
 └── [x] S9.1  SIGNAL QUALITY HARNESS — COMPLETE. 1989 green, smoke_s91
          15/15, 15/15 mutants dead. SIGNALS.md written.
          THE GATE IS ANSWERED BY CONSTRUCTION, not by waiting: three refusals
          (insufficient samples / degenerate class / label-kind mismatch)
          return a type carrying NO metric fields, so the harness cannot
          report on fixtures. Same posture as government_id and EPFO.
          - predictor source is the REPORT BODY, not ml_feature_vectors: the
            feature vector is keyed (candidate_id, as_of) with EXACT matching
            while outcomes are keyed by report_id, and the report is the
            artifact the human actually saw
          - the label seam carries SEMANTICS: outcomes => FRAUD (9 signals,
            measurable today), ledger => HIRE (3 depth.* signals, which
            correctly refuse until real orgs submit interview records)
          - no new table, no migration, NO new dependency (AUC/Brier/curve/
            lift are pure stdlib, and the AUC tie policy is written out
            because every *_band ties by construction)
          - [x] 1 result types · [x] 2-4 metrics · [x] 5 store reader ·
            [x] 6 label seam · [x] 7 ledger source · [x] 8 registry ·
            [x] 9 service+refusals · [x] 10 route+knob · [x] 11 CLI ·
            [x] 12 mutants · [x] 13 smoke+docs
          - RULING R1 APPLIED AND PINNED BY MUTATION: the plan hardcoded
            consent_allowed=True into build_label, a real consent bypass in
            the one place PI-9 touches consented data. Now
            materialization_consent(cid, at=report.created_at); restoring the
            constant turns 2 tests red. Consent is read AT THE REPORT'S OWN
            MOMENT, not "now" -- a grant beginning after the report did not
            authorize reading that subject when the prediction was made.
          - ⚠ THE PLAN'S REFERENCE CODE WAS WRONG SIX TIMES, every one caught
            by EXECUTION and none by reading: calibration_curve's int(s/width)
            at the DEFAULT bins=10 (every test used bins=4, whose width
            divides exactly -- the uncovered door was a default argument);
            fixtures report_store/candidate_id that do not exist;
            OutcomeSource.ORG (it is ORGANIZATION); record_interview (it is
            submit_interview_record); SqlCandidateStore (it is CandidateStore);
            Population(reports_considered=...) (no such field). TREAT PLAN
            SNIPPETS AS INTENT, NEVER AS RUNNABLE.
          - the kind-mismatch refusal is checked BEFORE the sample floor: a
            depth signal on a fraud source is not "nearly measurable", and
            insufficient_samples would invite collecting more of a label that
            can never score it
          - the no-traceback claim is asserted in a REAL SUBPROCESS: in-process
            a logging handler bound to a previous test's captured stream emits
            its own "--- Logging error --- Traceback", so the in-process
            version reads pytest's plumbing. It failed in-file and passed
            alone, which is the tell.
          - the mutation harness is COMMITTED (scripts/mutate_s91.py), unlike
            S8.3's and S8.5's hand-run passes: a count nobody can re-derive is
            a claim, not evidence
 └── [x] S9.2  EXTRACTION COVERAGE — MERGED 2026-08-22 at `2ad59f8`, branch
          deleted. Clean fast-forward; 2080 passing RE-RUN ON THE MERGE
          COMMIT, 21/21 mutants dead, smoke_s92 17/17.
          Asks the question underneath S9.1's: were the advisory numbers
          computed from the resume, or from a hole where it used to be?
          - src/app/candidates/coverage.py: five checks, four bands, and a
            refusal that carries NO gaps; computed ONCE inside extract_profile
            so the LLM and heuristic doors share one instrument
          - Report.extraction_coverage — NO migration (ReportRow.body is JSON)
          - the instrument may not import the extractor's eyes, enforced by an
            AST guard incl. a ban on relative imports
          - four measured extractor defects closed: bulleted roles, unknown
            section headers, spelled-out degrees, labelled skill lines
          - ⚠ TWO CRITICALS FROM THE FINAL REVIEW, both real: the bulleted-roles
            fix FABRICATED jobs from achievement bullets, and blocks() promoted
            content lines to headers so a dropped skills section read `complete`
          - ⚠ THE FIX WAVE THEN ADDED TWO MORE, caught by the scoped re-review:
            Title-Case headers went blind, and a 6-word cap silently dropped
            `Tata Consultancy Services`
          - the cause all three times was a PREDICATE CHANGE BREAKING A SHAPE NO
            TEST COVERED => tests/test_coverage_shape_matrix.py, a table-driven
            corpus of every shape the sprint found
          - FIVE vacuous tests found and killed
          - CANDIDATES.md "Known limits" states what it CANNOT see: partial
            drops (§3.3 is total-drops-only), and `Key Skills` over a bare list
          - OPEN: six shape fixtures sit under coverage_min_chars=200 (R16);
            spec §5.3 still lists `bs`/`ms`, which R14 deliberately did not ship
          - ✅ FIXED 2026-08-24 on `s92-fix-degree-false-positive`: word
            boundaries + a link/email strip + a REQUIRED dot on the two-letter
            abbreviations (optional would match the English words "be"/"ma", 
            trading a URL false positive for a commoner prose one). 2080 -> 2083
            green, smoke_s92 17/17, 3/3 mutants dead. `_LINKISH` is load-bearing
            and now pinned: boundaries ALONE still admit `www.b.com`, `mba.com`
            and `mca@example.com`, because there a host label or mailbox name IS
            the degree token. genuine_genai_resume.txt now reports `complete`.
          - ✅ FIXED 2026-08-24 on `s93-extractor-degree-word-boundary`, SAME
            BUG CLASS ONE MODULE OVER: the EXTRACTOR's `_DEGREE` spelled the
            two-letter abbreviations `b\.?e` -- an OPTIONAL dot -- so the bare
            English words "be", "me", "ma" AND "ba" all matched. Measured: an
            education section containing "This programme will be announced
            later" yielded an education entry whose degree was that whole
            sentence. The extractor was INVENTING a credential nobody claimed,
            which R13 already settled as the worse failure.
            THE REPAIR IS A CASE SPLIT, NOT A REQUIRED DOT, and that choice is
            the finding: `BE`, `ME`, `BA`, `MA` are ordinary degrees on Indian
            resumes, so requiring the dot (the obvious fix, and the one R14 took
            for `bs`/`ms`) would have cost real degrees in this product's own
            market. Dotted forms stay case-insensitive; dotless forms are legal
            only in UPPERCASE -- which is exactly what separates the degree `BE`
            from the word `be`. Blast radius was bounded first: `_DEGREE` has
            exactly TWO call sites, both inside `_education()`.
            2083 -> 2086 green, smoke_s92 17/17, smoke_s91 15/15, 3/3 mutants
            dead, new corpus fixture `education_prose_not_a_degree` carrying one
            real degree and two sentences so it pins BOTH directions at once.
          - (superseded, kept for the record) FOUND 2026-08-24: `looks_academic`
            SUBSTRING-MATCHED
            `b.com` INSIDE `github.com`. coverage.py:42 _DEGREE_WORDS is checked
            with `w in low`, so ANY resume carrying a GitHub link counts as
            carrying a "degree-bearing line" and raises a FALSE
            `education_not_extracted` whenever education is genuinely absent.
            This is what actually produced the `major_gaps` reported against
            genuine_genai_resume.txt on 08-22 -- that resume has no degree line
            at all, so the gap was spurious, not a dropped section. A
            tech-hiring product in which most resumes carry a GitHub URL is the
            worst possible place for this. Fix needs word-boundary matching, and
            the shape corpus needs a github.com fixture to pin it.
          - ⚠ OPEN, FOUND 2026-08-22: THE INSTRUMENT NEVER REACHES `/evaluate`.
            routes.py:521 calls engine.evaluate() without extraction_coverage,
            so that door returns `extraction_coverage: null` structurally, while
            screening/ingest.py:147 passes it. cross_field falls back to
            heuristic_profile() -- the extractor S9.2 fixed -- so coverage
            APPLIES here and is simply unwired. Measured on
            genuine_genai_resume.txt: profile 0/0/0, cross_field and
            fabrication_risk both `insufficient_data`, depth `deep 0.81`, and
            assess_coverage says `major_gaps / education_not_extracted`.
            The Instant check screen is the one that wires to this route.
```

## Standing conventions (do not relitigate)

- TDD, fully offline tests (NullLLM/fakes); `pytest -q` green before merge.
- Every LLM step degrades to a deterministic fallback (works with no API key).
- Advisory only — no auto-reject anywhere; conservative calibration gate stays.
- DPDP: first-party data only; consent objects + delete paths for new tables.
- Config: tunables in `config.yaml`, secrets in `.env` (`DEE_*`).
- DB: SQLAlchemy + Alembic on SQLite, Postgres-shaped (UUIDs, FKs, JSON columns).
- Each sprint ends with a local smoke: uvicorn + scripted HTTP calls on fixtures.
- LLM provider: OpenRouter + Qwen tiers (see `config.yaml`).

## Session log

- **2026-08-19** — **S9.1 finished (Tasks 5-13) and the S8.6 review fixes
  merged. 1854 → 1989 green, `smoke_s91` 15/15, `smoke_s43` 8/8, 15/15 mutants
  dead, `check_ui_screening_contract` 31/31. Nothing deployed.**
  **What this session established, beyond the checklist:**
  1. **A shared helper is how an invariant becomes testable.** The key pin
     lived in 34 copies and had gone missing from five smokes over five
     sprints. Consolidating it into `scripts/_smoke.py` immediately found a
     SIXTH — `smoke_s43`, whose docstring claimed "LLM-free" while it billed
     OpenRouter. An invariant in 34 places is an invariant nothing can test.
  2. **Half its checks were passing on insertion order.** Once the key was
     pinned, three `smoke_s43` checks that had always been green turned out to
     be ordering over three None-valued candidates. A green check is not
     evidence that the thing it names is true.
  3. **The plan's own reference code was wrong SIX times, and execution caught
     every one.** Two non-existent fixtures, three misspelled APIs, one
     non-existent model field — plus the `calibration_curve` default-argument
     bug found before the pause. Plan snippets are intent, never runnable.
  4. **Order the refusals by what they invite the reader to do.** The
     kind-mismatch check runs before the sample floor, because
     "insufficient_samples" on a depth signal scored by fraud labels would
     invite someone to go and collect more of a label that can never score it.
  5. **Some claims cannot be asserted in-process.** The CLI's "no traceback on
     stderr" failed in its file and passed alone: a logging handler bound to a
     previous test's captured stream emits its own `--- Logging error ---
     Traceback`. The assertion was reading pytest's plumbing. It needs a real
     subprocess, which is how the retention CLI already asserts the same claim.
  6. **A mutation count nobody can re-derive is a claim, not evidence.** S8.3's
     12/12 and S8.5's 10/10 were hand-run and survive only as numbers in this
     file. S9.1's harness is committed as `scripts/mutate_s91.py`, and 15/15
     die.
  7. **`git stash` is unusable in this repo.** `stash -u` fails on `.claude/`
     with a OneDrive permission error, leaves the tree dirty anyway, and the
     next `checkout` silently carries the changes across — so a before/after
     measurement runs twice against the SAME code and reports IDENTICAL for
     free. Compare implementations in one process instead.
  8. **The ultra review has now died on the session limit four times**, roughly
     forty angle-agents for one surviving output. Recorded so nobody re-spends
     the quota expecting a different result; S8.6 is still unreviewed for
     correctness.


- **2026-08-13** — **S8.6 built: the production shape, and nothing deployed.
  Branch `s86-production-shape`, 12 commits, TDD. 1812 → 1848 green, all
  twenty smokes green (`smoke_s86` 27/27, twice in a row), browser 19/19 ·
  contract 31/31 · bindings 402/402. Not reviewed, not merged, not pushed. No
  cloud resource created.** The deploy sprint deliberately stopped being a
  deploy — zero customers, the user gates go-live — so the output is a correct
  system plus `DEPLOY.md`.
  **What this session established, beyond the checklist:**
  1. **A boot refusal must ask the BUILDER, not the config string.**
     `provider="smtp"` with an empty host silently returns `NullEmail`, so
     checking `email_provider` would have passed the exact config that 503s
     every login. `EmailClient.available` already existed for that question —
     one predicate, no second copy to drift.
  2. **A `Mount` is a second way to widen the unauthenticated surface, and the
     route-table guard could not see it.** No `.methods`, so the guard skipped
     it; no inherited router dependency, so it is unauthenticated. The guard
     was widened *before* the mount existed, and then had to learn the
     `_IncludedRouter` recursion, because `APIRouter` inherits `.mount()`.
  3. **"We tested it" is not the same as "the test pinned that property."**
     Two localhost servers on different ports are cross-ORIGIN but same-SITE,
     so the browser check exercised Lax + CORS and never once exercised the
     shipped `SameSite=None`. The docstring claiming otherwise had been true of
     nothing since it was written.
  4. **A hand-maintained list drifts even when the drift is a comment about
     the drift.** `GET /`'s endpoints array was carried three times with
     correct reasoning; the third carry named `/metrics` only because the
     second reader might have assumed it covered. Derivation ended it — reusing
     the walker already in the file, since a flat scan sees 9 of 63 routes.
  5. **`.dockerignore` can cancel a `COPY`.** Two hand-maintained lists that
     must agree, which is the shape of every drift this repo has found, and
     nothing read both until now.
  6. **The failure a cron sees is part of the contract.** The sweep's own
     entry point exited 1 with a traceback on an unmigrated database. Exit 3
     and a sentence cost fifteen lines; finding it cost running the thing once.
  7. **A check can pass for the wrong reason and look identical to one that
     passes.** `code != 0` proved a process died — but it died because the
     harness killed it after a hang, not because anything was verified.
     Positive evidence (uvicorn's own startup marker) is the fix, and the same
     lesson retired a poll-based UI check in favour of a MutationObserver
     latch after it failed once at random.
- **2026-08-10 (later)** — **The outcome loop is closed. Branch
  `s86-org-outcome-route`, nine commits, TDD. 1553 → 1586 green,
  `smoke_s85_outcome` 21/21 first run, `smoke_s84a` 23/23 + `smoke_s84b` 16/16
  re-run green, UI bindings 402/402 · contract 31/31 · browser 19/19, 7/7
  mutants dead (and one probe that correctly refused to die — see 9).**
  Two org-plane routes (`POST`/`GET /screening/reports/{id}/outcome(s)`),
  migration `0020` (outcome authorship), one shared constructor for both doors,
  a notes bound at both doors, and the four verdict buttons back on the report
  screen.
  **What this session established, beyond "the customer can record an
  outcome":**
  1. **A column can exist to keep a fact that a `SET NULL` would otherwise
     erase.** `recorded_by` is not metadata — without it, a null `org_id` reads
     as "our own operator said this", and a calibration harness would train on
     its own echo. The derived answer would always have looked plausible, which
     is the worst kind of wrong.
  2. **Migrate the FIRST door before writing the second.** Building the org
     route beside an unmigrated admin route is precisely the shape a shared
     constructor exists to prevent. And the test that matters asserts the two
     doors **refuse the same inputs**, because "both call the helper" is a
     claim about today's source.
  3. **NOT NULL with no server default is a detector.** It found a THIRD writer
     to `outcomes` that the design missed entirely — the S8.1 one-off importer.
     With the default left standing, that import would have succeeded and
     labelled the rows correctly for the wrong reason.
  4. **The leak a new route introduces is not always the one the document
     anticipates.** Every tenancy check written so far is about reading
     sideways. A report has exactly one owner, so nothing can leak sideways
     here — the exposure is DOWNWARD, to the customer, from the operator's own
     note on the same report.
  5. **404 on a WRITE.** The instinct on a refused write is 403, and 403
     confirms the thing exists. Held to the same rule as the reads, byte for
     byte, at three layers.
  6. **A class that gains a write must lose a name that says Reads** — while
     the attribute the guard watches stays put, so the guard needs no edit.
  7. **A React input's `.value` can be set without its handler ever firing**,
     which would have let the browser check post an empty note and stay green.
     Typed through the native setter plus a dispatched `input` event.
  8. **Two hand-maintained lists were found stale and deliberately left that
     way**, with the staleness written down: `GET /`'s `endpoints` array and
     `UI.md` §5's plane counts. Patching in two entries would make an
     unmaintained list look maintained.
  9. **A rule that was load-bearing in one place is not load-bearing in the
     next, and only a probe tells you which.** The self-review "found" a
     double-click defect by analogy with the process driver's async-`setState`
     trap — recorded as load-bearing in the session directly above. Planting
     the supposedly-broken guard left the browser check green: React flushes
     discrete events synchronously, so a click handler is not a loop tick. The
     same mutation technique that killed 7/7 real mutants is what refused to
     kill this one. **Reasoning by analogy from this repo's own recorded
     lessons is exactly as unreliable as any other reasoning that skips the
     measurement.**
- **2026-08-10** — **The screening screens are wired. Branch
  `s85-screening-ui-wiring`, three commits, no `app/` code touched
  (`pytest -q` 1553, unchanged). 384/384 bindings · 25/25 contract · 16/16
  browser.** Queue, report, summary, upload and batches now run against the
  seven batch routes plus Phase A's report read; their mock constants are
  deleted rather than kept as a fallback.
  **What this session established, beyond "the screens work":**
  (1) **The client drives the work, so the UI has to be honest about it.**
  Registration evaluates nothing, the loop runs in the browser five items at a
  time, closing the tab pauses the batch, and every call bills a model — which
  is why the loop starts on *upload* and never on *navigation*, and why any
  error stops it rather than retrying into an API with no rate limiter.
  (2) **`setState` is asynchronous, so the loop cannot consult state.** A
  driver reading `state.driving` on the tick that sets it reads the previous
  value and halts before its first call. An instance field controls the loop;
  state only renders it. This is a general trap for any self-scheduling work in
  a React class.
  (3) **A frontend with no CI needs guards that EXECUTE, not guards that
  read.** The binding checker runs `renderVals()` over eight states and resolves
  every `{{ }}` against the result — 384 of them, sc-for scopes included. Its
  first version let a mutant live: a field set to `undefined` passes an `in`
  check and renders as an empty string, which is the exact silent blank it
  exists to catch.
  (4) **Only the browser layer can see the browser's own semantics.** It found
  the Delete button nested inside the clickable batch row, so arming a delete
  navigated away. No unit test and no static check sees event bubbling.
  (5) **Two of my own checks were measuring my assumptions** — the sprint's own
  recurring shape, now three sprints running. A `[1,"x"]` cursor is *valid*
  (S8.4b made it so), and a four-item batch under a cap of five "proved" a loop
  that never looped.
  (6) **A real product gap surfaced and was named rather than papered over:**
  there is no org-plane route to record an outcome, so the customer cannot close
  the loop on a report they paid for. It is PI-9's calibration input. The report
  screen states it in prose; the fix wants its own spec.
- **2026-08-08/09** — **S8.4 Phase B built: the screening surface. 1434→1542
  green, `smoke_s84b` 16/16, all sixteen smokes green. On branch
  `s84b-screening-surface`, unreviewed and unmerged.** All 15 plan tasks, TDD,
  one commit each. New package `app/screening/` (`schema` · `pagination` ·
  `models` · `store` · `ingest` · `service`), migration `0019`, seven org-plane
  routes, `SCREENING.md`.
  **Six things this build measured that the plan did not predict:**
  (1) **Two mutants survived the first pass on the claim** — the conditional
  UPDATE's `WHERE` and `rowcount == 1` — because the race is unreachable
  through two sequential calls; a `_try_claim` seam plus a test that builds the
  interleaved state kills both. (2) **The plan contradicted itself on
  `derive_status`**; its test table was the coherent reading, so `processing`
  now beats `pending`. (3) **The `operation_id` loop had to run LAST in
  `create_app`** — `/` and `/healthz` register after `include_router`, so the
  loop where the plan put it missed both, caught by the new contract test.
  (4) **`_ACCEPTED` is `{"status":"accepted"}`**, not `{"accepted":true}`, and
  the requisition field is `must_have_skills`, not `skills` — both read off the
  code rather than trusted. (5) **The smoke's CSRF 403** — one client that signs
  up then calls with `X-Org-Key` still holds a session cookie, and CSRF keys on
  how the principal was established (S8.2 working as designed). (6) **"A stolen
  cursor returns nothing" was the wrong assertion** — org B legitimately owns a
  batch by then; the check now asserts none of A's ids appear.
  **`smoke_s63` was making live billed calls** and is now pinned — the same
  trap for the third sprint running, on a smoke that was not on Phase A's list
  of nine.
  **The scope guard's allowlist is EMPTY** (the ingest extraction removed all
  five entries) and the guard was re-proven non-vacuous against a planted
  unscoped read. `screening` joins `screening_scope` as a sanctioned door.
  **Two deliberate contract breaks**, both off the wired UI's path: the curation
  queue answers `UnmappedPage`, and `POST /comp/estimate` answers
  `CompBenchmark`. **Both 422 sites became 200 + `reason` in one commit.**

- **2026-08-07 (later)** — **S8.4 PHASE B IS SPEC'D AND PLANNED. Documents only;
  no `app/` code touched, `pytest -q` re-measured green at 1434 before writing.**
  Spec: `docs/superpowers/specs/2026-08-07-s84b-screening-surface-design.md`
  (the *delta* on top of the 2026-08-05 spec §4, which still stands).
  Plan: `docs/superpowers/plans/2026-08-07-s84b-screening-surface.md` — 15 tasks.
  **The tenancy section is written the way Phase A's failure says it must be:**
  a FIELD table (spec §2) listing every field of every new org-facing response,
  where the value came from, and what stops it naming somebody who is not this
  customer's — not a count of handlers that read people, which is the method
  that missed the ingest-response leak.
  **The design decision that carries the sprint: the queue read-model is built
  from `batch_items` ALONE — no `Report` is ever on the org-plane read path.**
  Two reasons, and the second is why it is in the spec rather than the plan:
  a `Report` is a *cross-corpus object* (`resume_farm.matches[]` is exactly what
  Phase A leaked), so a read path that never holds one has nothing to forget to
  redact — the leak becomes structurally impossible instead of correctly
  handled. It is also the only shape that pages: `risk_score` is a real column
  and therefore sortable, where the same number inside `reports.body` JSON is
  dialect-specific and unindexable.
  **The DPDP decision that fell out of it, and it refuses the obvious
  implementation:** `UI.md` asks each queue row for "a one-line reason", and
  copying `fabrication_risk.reasoning` onto the item is refused —
  `batch_items.candidate_id` is `SET NULL` (so an erasure cannot rewrite an
  org's record of what it screened), which means anything stored beside it
  **outlives the person it describes**, and a reasoning string can quote claim
  text. So `ItemSignals` is **scalars only** and the reason is **composed at
  read time** from them. A column that cannot hold personal data needs nobody
  to remember anything.
  **Three measurements taken while designing, each of which changed a
  decision:**
  (1) **SQLite ENFORCES an expression index but does not REFLECT one**
  (`SAWarning: Skipped unsupported reflection of expression-based index`;
  `get_indexes()` returns `[]` while `INSERT 'acme'` after `'Acme'` raises
  `IntegrityError`). So the case-insensitive org-name fix ships as a functional
  UNIQUE index — the database computes it, so **both** existing insert paths
  inherit it with no new check — and `test_migrated_indexes_match_orm` gains a
  disclosed expression-index exemption plus a *behavioural* test, which is
  strictly stronger than the metadata comparison it replaces.
  (2) **38 of 82 operations return an untyped `dict`**, not the 5 the spec first
  claimed. **The first count was wrong in the sprint's own signature way:** it
  looked for a `200`/`201` response and reported "5 missing" — all five were the
  OTP routes, which answer **202**. The check was measuring its own assumption
  about status codes rather than the API. Nothing is missing; 38 are untyped,
  which is a bigger and different job, and it is now Task 13.
  (3) **The `_IncludedRouter` trap is still live and it caught me** — a naive
  walk of `app.routes` while measuring the OpenAPI surface returned **1** route,
  not 82. S8.2 recorded this exact trap; `app/main.py`'s new `operation_id` loop
  therefore ships with the recursion, not a `for route in app.routes`.
  **A guard gets STRONGER as a side effect:** extracting the ingest core to
  `app/screening/ingest.py` (so the batch processor and the single-upload route
  run one pipeline) removes all five `ALLOWLISTED_LINES` from
  `tests/test_org_scope_guard.py`, because every one of them was a line of
  `_ingest_one`. The allowlist goes to **empty** and a test pins it there.
  **Deviation from the parent spec, recorded rather than silently taken:** §4.5
  asked for the cursor on `POST /jobs/{id}/match` and `POST /talent/search` too.
  Both **re-rank on every request**, so there is no stored key and an opaque
  cursor would promise a stability it cannot keep. They keep `limit` and say so
  in the schema; the cursor lands on the three lists whose order is stored.
  **Next: execute the plan** — branch `s84b-screening-surface`, subagent-driven,
  per-task review, then a whole-branch review before merge.
- **2026-08-06/07** — **S8.4 Phase A built, reviewed and merged.** 1377→1434
  green, `smoke_s84a` 23/23, all regression smokes green. Plan
  `docs/superpowers/plans/2026-08-06-s84a-upload-ownership.md`; built
  subagent-driven over 10 tasks with a per-task review, then a whole-branch
  review and one closeout fix round.
  **What shipped:** migration `0018_upload_ownership`, `app/screening/`
  (`projection.py` + `scope.py`), three org-plane `/screening/*` routes, the
  `org_name_taken` fix at both doors, `tests/test_org_scope_guard.py`,
  `TENANCY.md`, `scripts/smoke_s84a.py`.
  **The sprint's own guard caught the sprint's own Critical**, which is the
  result worth remembering: the org **upload response** was returning other
  customers' `candidate_id`/`resume_id` in both the top-level `resume_farm` and
  the embedded report. Read routes were redacted; the ingest response never was.
  Root cause is a *method* failure, not an oversight — spec §3.4 enumerated
  org-facing **readers** and found two; the third returns a report without
  reading one.
  **Then the whole-branch review found the same shape one level deeper:**
  `ingest()` stamped `org_id` only on row creation, so two agencies handed the
  identical PDF left the second owning nothing (and with `evaluate=false`,
  nothing anywhere). Ruled spec conformance rather than a design call, since
  §0.1 already said "each agency owns its own upload of her".
  **And the guard was defeated by a variable name** — `svc` instead of
  `services`, measured against the shipped detector. Fixed by AST-resolving
  receivers; the guard now also documents the four things it cannot see.
  **Three process notes worth carrying.** (1) **Two reviewer claims were wrong
  and were checked before being written down** — a migration-guard test name
  that does not exist, and "five `batch_alter_table` migrations" when it is
  four. A fix round that implements a review literally propagates its errors.
  (2) **Deferring a measured money leak is how it becomes permanent** — the
  review flagged one unpinned smoke and proposed deferring it; four more had the
  same defect, and `smoke_s23` ran past a ten-minute timeout making live billed
  calls. All nine now pin the key. (3) **Three subagents died on API session
  limits** mid-review and mid-fix; the surviving discipline is that the ledger
  (`.superpowers/sdd/.../progress.md`, gitignored by design) held enough state
  each time to resume without re-deriving anything.
  **(4) A doc's false claim cost more than the doc.** "There is no HTTP route to
  delete an organisation" was wrong, sat in the plan *and* `TENANCY.md`, and was
  the stated reason the smoke never proved `SET NULL` — the sprint's
  load-bearing decision. The lesson is not "check docs"; it is that **a premise
  used to justify skipping a test deserves the same verification as the test**.
  **(5) The fix round introduced a defect of its own** — stripping sanctioned
  expressions from a line made a docstring quoting the rule read as a breach of
  it. Caught only because the re-review probed the detector adversarially rather
  than reading the diff. Every guard change from here should be pinned in both
  directions: it must fire on the bad shape *and* stay silent on prose.
- **2026-08-05** — **S8.4 specced. Documents only; no `app/` code touched.**
  Spec `docs/superpowers/specs/2026-08-05-s84-ui-integration-surface-design.md`;
  `UI.md` §2/§2.1/§4.A/§4.B/§9 and `UI-Spec.md` §2/§3/§4 updated in place so the
  UI docs record decisions rather than assumptions.
  **`UI.md`'s five open questions are all closed** (§0.1–0.4 of the spec, each
  with its rejected alternatives), and the sprint splits into **two branches**
  (§0.5) because a tenancy invariant across ~20 org-plane routes should not share
  a review with pagination and OpenAPI polish.
  **The finding that reframed the sprint: S8.4 is not really about batch upload,
  it is about tenancy.** `reports`/`candidates`/`resumes` have never had an org
  column, so "the customer's data" was undefined — and no wedge endpoint can be
  exposed to an org until it is. The resolution that made the rest fall out:
  **ownership belongs to the UPLOAD, not the person**, which keeps candidates
  global and deduplicated (so cross-corpus resume-farm detection survives) while
  giving every read something to scope by. **`SET NULL`, not `CASCADE`** — an org
  offboarding must not destroy a person's resume.
  **Three things were measured rather than assumed, and two of them changed the
  design.** (a) **There is no worker, no scheduler and no `BackgroundTasks`
  anywhere in `app/`**, and `POST /candidates` awaits the whole nine-node graph
  inline — so the batch design became register-then-client-driven-process rather
  than anything asynchronous. (b) The `"no materialized candidates to match"`
  422 is at **two** call sites (`routes.py:925` match, `:1023` board), not one —
  the house one-rule-two-doors shape appearing in the *defect list* this time.
  (c) The three `limit`-only pagination sites were confirmed as curation
  unmapped, job match and talent search.
  **A DPDP hole was found while designing and closed in the design, not deferred:
  `batch_items.raw_text` holds personal data with no candidate to cascade from**,
  because a resume row cannot exist before extraction. Hence: cleared on success,
  a real `DELETE` path shipping in the same sprint, and a declared retention
  window for the abandoned case.
  **Two deliberate breaks to the already-wired UI were named in the spec (§4.7)
  rather than left for integration** — org signup gains a 409 (the 36/36 contract
  suite will fail on purpose) and `POST /comp/estimate` changes shape to agree
  with `GET /jobs/{id}/comp`.
- **2026-08-01 (4)** — **S8.1 (Deployable spine) specced, planned, built inline
  TDD, and merged. 1175→1200 green; `smoke_s81` 10/10; s13/s41/s53/s64/s73 all
  still green.** Two decisions taken with the user before any code, both
  recorded with rejected alternatives in the spec §0: **(0.1) the admin
  credential is required in EVERY environment** — this *tightened* the approved
  PI-8 design, which had allowed an `env == "local"` escape; the argument that
  moved it is that `env` **defaults** to `"local"`, so the escape would make a
  safe deploy depend on remembering `DEE_ENV` *and* `DEE_API_AUTH_KEY`, i.e. the
  same fail-open shape one indirection deeper. **(0.2) provision Railway Postgres
  first, deploy the API last** — because there is no docker and no psql on this
  machine, so a hosted PG was the only way to observe the cutover outside CI.
  **Three measurements shaped the plan, none of them remembered:** the fail-open
  blast radius was wider than PI-8 §1.1 recorded (11 test files, not 7; 6 HTTP
  smokes needing keys, while s11/s12/s31 never speak HTTP at all); the Dockerfile
  copied `app/` and `config.yaml` only, so migrate-on-boot would have failed *in
  the container and nowhere else*; and **`InMemoryReportStore` had to be deleted,
  which the PI design does not say** — it is a dict, it cannot cascade, and
  keeping it would have let every erasure test pass without the guarantee the
  fold exists to create.
  **The sprint found two bugs of its own.** (a) A **pre-existing pinned-NOW time
  bomb detonated mid-session**: `test_interview_org::test_revocation_closes_it_again`
  passed at one point and failed an hour later, because it revoked at the wall
  clock and asserted at `NOW = 12:00 UTC` today. The S7.2 review had fixed the
  *grant* side of that file and missed the *revoke* side — the warning comment
  was right there. (b) The new FK exposed a real race: `POST /candidates` saved a
  report and *then* deleted it if the candidate had been erased mid-eval; the
  orphan is now unwritable, so `save()` raises `SubjectErasedError` and the
  handler returns `report=None`. Both halves of that race are the database's job
  now.
  **Postgres was verified for real (18.4, not a container fake):** 16 migrations
  up → down to base → up clean, which proves the three `batch_alter_table`
  migrations on a plain-ALTER dialect **and** the downgrades — retiring the S3.1
  residual "0004 downgrade untested" — plus 29 SQL-shaped tests, no skips.
  **Measured limit worth keeping:** the full suite against a *remote* PG is not
  viable (29 tests / 11m29s, because each store creation is a `CREATE SCHEMA`
  plus ~20 tables of DDL over the internet), so the full-suite PG run lives in
  the new CI job on localhost.
  **The deploy was stopped by the user mid-sprint** — *"lets not deploy in
  railways yet, we need to complete all the PI plannings, make UI and integrate
  with UI"*. It had booted once first, and that run is the DoD item hardest to
  evidence otherwise: an empty Postgres, `migrations_applied
  backend=postgresql+psycopg`, `startup_complete env=prod llm=NullLLM`,
  `/healthz` 200 — the key-less path holding in a production configuration. No
  domain was ever generated, so it was never publicly reachable; the user deleted
  the Railway project. The repo ships **deploy-ready** instead (`railway.json` +
  README `## Deploy`), and PI-8's sequencing now reads: finish planning → build
  the UI → integrate → deploy.
- **2026-08-01 (2)** — **GTM positioning settled. No code.** The user asked the
  question the repo had never asked: *how does this become revenue?* — offering
  three options (build a UI + advertise + investors · sell to LinkedIn/Naukri/
  Indeed · sell direct to companies via API). Written up as
  `docs/superpowers/specs/2026-08-01-veritas-gtm-positioning.md`.
  **Two framing corrections did most of the work.** (a) The three options are
  **not alternatives** — options 2 and 3 both require a screen a non-engineer can
  evaluate, so "build a UI" is the shared cost of entry, not a competing
  strategy. That is what answered the API-only question above. (b) The binding
  question is **not which channel but what single thing we sell**: veritas is
  eight subsystems presented as one platform, and nobody buys "talent
  intelligence platform."
  **The wedge chosen is pre-screen fraud detection**, and the reason it beats
  every other slice is a property no other subsystem has: **it produces value
  from one customer's own resumes on day one.** The ledger needs N orgs; the
  calibration harness needs outcomes; matching and comp are me-too against every
  ATS. Fraud screening needs nothing but a resume — and it can be validated
  *retrospectively*, against resumes a customer already rejected, which is the
  cheapest path to answering gap-analysis v2 §2 ("seven advisory numbers, none
  ever checked against reality"). That reframes §2 from a technical debt item
  into the central commercial risk, and makes closing it a *side effect* of the
  first design partners rather than a project.
  **The counter-intuitive call: the evaluation ledger comes off the pitch.** It
  is the most architecturally impressive thing in the repo (PI-3, consent-first,
  audited) and commercially the worst opening move, because it is worth exactly
  zero to customer #1. It stays built; it becomes the expansion story.
  **The user overruled my scope recommendation and it is recorded as theirs:** I
  recommended PI-8 harden only the wedge path (skipping blocker 4, since the
  wedge's buyer is the employer); the user chose the **whole platform**. Reasoned
  through and it is coherent — the pitch narrows, the platform does not — with
  the cost (≈2× scope, nothing demoable until late) and the mitigation (sequence
  the wedge demo path early) both written into the doc and the Next action above.
  **The doc records four blockers no technical audit could have produced** (§8):
  DPDP correction + grievance-officer contact are **RFP blockers**, because the
  consent architecture is a *differentiator* in an Indian enterprise RFP rather
  than only a compliance cost; false-positive liability needs contract language,
  not just advisory-only code; the **IBM IP / outside-activity agreement must be
  checked before there is revenue**; and B2B invoicing needs a proprietorship +
  GST, which is not "starting a company" in the sense the user declined.
  **Kill criteria were written in advance** (§10) — while it is still cheap to be
  honest — so a future session cannot rationalise sunk cost: no design partner
  willing to hand over resumes for free ⇒ the wedge is wrong, not the pitch;
  retrospective accuracy at chance ⇒ the fabrication stack, not the GTM, is the
  problem. **Rejected options are recorded with reasoning** (§9), the important
  one being that selling to a platform is an *exit* available after traction, not
  an entry: platforms buy traction and teams, not code, and pre-traction the idea
  is simply built in-house. **Open, deliberately** (§11): pricing model, hosting
  posture (shared vs per-customer — interacts with the deferred multi-tenancy
  call), deploy target (Railway tooling is present in the environment and is the
  obvious candidate — confirm in PI-8's brainstorm, it collapses blockers 1–3),
  and whether the demo UI is throwaway or the real front end.

- **2026-08-01** — **S7.3 (AI interview delivery v0) BUILT, REVIEWED, MERGED.
  PI-7 COMPLETE.** Full sprint cycle in one session: brainstorm → spec
  (`2026-07-31-s73-ai-interview-delivery-design.md`, commit `d79c8c7`) → 14-task
  plan (`2026-08-01-s73-ai-interview-delivery.md`, `7e4bab1`) → TDD build on
  branch `s73-ai-interview-delivery` → whole-branch review → merge
  (fast-forward to `6e6d7fd`). **1024 → 1175 green**, pyflakes clean,
  `scripts/smoke_s73.py` **18/18 OK** exit 0. Executed **inline** for the same
  reason S7.2 was: I held the whole plan in context, so a fresh implementer per
  task would re-read it to arrive at the same code, and the review that matters
  is the one done by reading the code.
  **Three decisions were put to the user before any code was written** — they
  were the ones a wrong guess would have made expensive to unwind: where the
  "never store the artifact" line falls now that there is a transcript; whether
  orgs can read at all in v0 and under what consent; and how live the first
  model-dependent sprint should go. All three came back as recommended
  (transcript stored / audio never · candidate-initiated + new `INTERVIEW_READ` ·
  real ASR, TTS deferred) and the spec records the rejected alternatives.
  **The design idea worth remembering:** the interview asks the depth report's
  OWN probes. That asset (`probe_generation` → `CoherenceVerdict.probes`) has
  existed since PI-1 and was never consumed; using it makes the interview about
  *this* candidate's unsettled claims instead of a generic bank, and it hands the
  deterministic scorer a per-question yardstick (`missing_signals` →
  `expected_signals`) so the rubric needs no LLM to know what a real answer must
  contain.
  **Two plan corrections during the build, both caught by tests:** the org read
  needed `summarize()` but it was a `staticmethod` on the service, which the
  store cannot import (cycle) — moved to `session.py` so both callers share ONE
  transcript-free projection, which is stronger than the original design; and a
  test called `grant_consent(at=...)` when the kwarg is `now=` — the same
  clock-injection trap S7.2's review recorded, caught immediately this time.
  **The whole-branch review found TWO Importants, both reproduced first, both
  the house shapes for the third sprint running** — an unbounded ASR transcript
  (S7.2's `claim_ref`: a bound on one path and not the other) and an unreadable
  stored assessment bricking `/portal/me` permanently (S7.2's `METHOD_LEVEL`
  KeyError). Full detail in "Current state" above.
  **The live-model check earned its keep beyond a green tick:** voxtral is
  reachable and the seam works, *and* it hallucinates fluent prose on non-speech
  audio — a hazard now recorded in `MODELS.md` and `INTERVIEWS.md` §12. It also
  exposed that the smoke was not actually key-less (a real key in `.env` sent
  junk audio to a live vendor and changed which error the smoke asserted); the
  smoke now pins the key empty, so it tests what it claims.

- **2026-07-31 (3)** — **S7.2 (document forensics + concurrent-employment
  advisory) BUILT, REVIEWED, MERGED. PI-7 now S7.1 + S7.2 done; S7.3 remains.**
  Executed the 12-task plan end to end **inline** on branch
  `s72-document-forensics` (I hold the full 2 800-line plan in context, so a
  fresh implementer per task would re-read ~44k tokens to arrive at the same
  code; the review that matters I did myself, reading the code). **887 → 1011
  green**, pyflakes clean on every new/modified file, `scripts/smoke_s72.py`
  **15/15 OK** exit 0. Delivered exactly the spec's shape: a `subject`
  discriminator + a **separate `ClaimEvidence` roll-up**, three pure modules
  (`documents.py`, `claims.py`, `moonlighting.py`), migration `0014`, three
  endpoints, four config knobs, **no new table / no new `ConsentPurpose` / no
  new erasure path**. Full detail in "Current state" above.
  **Four plan corrections made during the build, all self-caught by tests:**
  (a) S7.1's `test_every_method_maps_to_a_level` asserted
  `set(METHOD_LEVEL) == set(VerificationMethod)`, which S7.2 deliberately
  breaks — narrowed to the identity subset **derived from `METHOD_SUBJECT`**,
  which is strictly stronger against drift than the hard-coded list it
  replaced; (b) `test_adapter_levels_agree_with_the_method_level_map` would
  `KeyError` on claim adapters — now asserts they pin `level = NONE`;
  (c) the plan's moonlighting test expected 3 overlap windows from three roles
  that in fact yield 2 distinct ones — the dedup in the plan's own
  implementation is correct, so the test data was fixed and an explicit dedup
  test added; (d) two plan tests assumed a resume on file where the fixture
  created a bare `CandidateRow`, so nothing could ever produce a hard finding —
  fixtures now `ingest` a real profile. Also implemented `strip_legal_suffix`
  in S1.4's `orgs.py` so "Acme Technologies Pvt Ltd" on a resume matches
  "ACME TECHNOLOGIES PRIVATE LIMITED" on letterhead — `employer_not_claimed` is
  one of only two HARD findings and a false one is this module's most expensive
  mistake. Spec §8's `doc_unknown_issuer_severity` knob was **deliberately not
  built** (the plan's own stated deviation): severity is a code constant,
  because a deploy-time switch that silently reclassifies `soft` → `hard` is
  what the "taxonomies are code constants" stance exists to prevent.
  **The whole-branch review found TWO more Criticals — same house pattern as
  S7.1, and one of them is the same bug shape.** Both were **reproduced over
  HTTP first** (throwaway pytest module against `create_app(make_services(...))`,
  deleted after; its attacks kept as permanent regression tests), then fixed,
  then re-run to prove closure. **(1) A claim method was startable on the
  IDENTITY route** — `POST /portal/verifications {"method":"experience_letter"}`
  → **200 `verified`, `subject: identity`**, no document — and because
  `compute_assurance` indexed `METHOD_LEVEL` directly, **every subsequent read
  of that candidate's own portal 500'd forever**: a candidate could destroy
  their own DPDP access with one request. Root cause identical to S7.1's: *a
  gate applied at one entry point and not the other* (`submit_document` checked
  `document_based`; `start` never asked about subject), plus `instant=True`
  being read as the old fail-open "complete it now". Fixed in three layers —
  route gate, store-level `METHOD_SUBJECT` refusal (the bad row is now
  **unrepresentable**, not merely unreachable), and `METHOD_LEVEL.get` so a
  rogue row degrades instead of bricking. **Ordering mattered and I got it
  wrong first:** placing the subject gate before `implemented` changed
  `epfo_employment` from 422 to 403, contradicting spec §3 — moved it after, so
  a declared-but-inert method answers the same at every door and every S7.1
  answer is untouched. **(2) `claim_ref` was unbounded** — SQLite does not
  enforce `VARCHAR(128)`, so 5031 chars including a salary and a UAN were
  stored, defeating the "no column can hold a document" guarantee through the
  *one* column the models test excepts. Bounded at the route and in the service.
  **Third finding, pre-existing on `main`: the suite was not time-independent.**
  S7.1 tests granted consent at wall-clock but asserted at a pinned `NOW` of
  12:00 UTC 2026-07-31, so they started failing the moment the real clock passed
  noon (which it did, mid-session, at 14:24 — that is how it surfaced). S7.2 had
  copied the pattern. All `grant_consent`/`revoke_consent` calls in those files
  now pass `now=NOW`. **Clean on the other three review questions:**
  `claim.query` is audited on the denied path (committed before the raise,
  visible in the candidate's access log with the org name resolved); every
  startable adapter declares its route to an outcome; no stored row holds
  document text, a salary or an identifier. Docs: `VERIFICATION.md` §11–§16
  (incl. a written record of both escalations), `LEDGER.md` dated
  `VERIFICATION_READ` redefinition, `PORTAL.md`, `README.md`. Merged to main,
  branch deleted. **Next: shape/plan S7.3** (AI interview delivery v0) — read
  `VERIFICATION.md` §11 before wiring proxy-detection to `IdentityAssurance`.
- **2026-07-31 (2)** — **S7.1 whole-branch review → two Critical fixes →
  MERGED. S7.1 COMPLETE.** Review ran **inline** (the harness in these sessions
  forbids spawning agents unless the user asks), reading the full 14-commit
  branch surface rather than trusting the build's own account of it — which
  mattered, because the build's docs asserted a property the code did not have.
  **Both findings were reproduced over HTTP first** (throwaway pytest module
  against `create_app(make_services(...))`, deleted after), then fixed, then
  re-run to prove closure:
  **(1) `manual_review` self-award → L3.** The candidate-plane route accepted
  any `VerificationMethod`, and L3 asserts *an operator looked*.
  **(2) `government_id` self-award → L4.** The candidate grants themselves
  `IDENTITY_VERIFY` via S6.4 first-party consent (by design), the third-party
  gate passes, and the spine **never calls the adapter** — so the
  `NotImplementedError` inside `GovernmentIdAdapter.start` could not fire and
  the route's `except NotImplementedError → 422` was dead code. "Declared but
  inert / unreachable from any route" was false as shipped, in code *and* in
  `VERIFICATION.md`. The **shared root cause** was a fail-open default —
  `start()` read "not `challenge_based`" as "complete it now, VERIFIED" — and
  the **test blind spot** was `_FakeThirdPartyAdapter`: the gate was proven
  against a fake while the real, routable method was never driven end-to-end
  (`test_government_id_is_not_reachable_from_the_candidate_plane` asserted
  `status in (400, 403, 422)` and passed only because that test happened to have
  no grant — false comfort, now strengthened to grant-then-assert-422).
  **Fixes, all in the spine where the other gates live:** seam gains
  `self_service`/`implemented`/`instant`, **defaulting to REFUSE on `_Base`**
  (a new adapter is inert until it declares itself); `start()` documented as the
  candidate-initiated entry point, ordering `self_service` → `implemented` →
  third-party consent → destination binding (**consent necessary, never
  sufficient**); nothing is marked VERIFIED on request unless `instant`.
  `manual_review` → 403, `government_id` → 422. **Two more review fixes:** the
  OTP cooldown/supersession was scoped to one verification row and therefore
  rate-limited **nothing** (the plane mints a fresh verification per start, so a
  stolen key bought unlimited codes and unlimited 5-guess batches against a
  6-digit code) — rescoped to **candidate+channel**, plus `hmac.compare_digest`;
  and an operator manual review was audited `actor_type="candidate"`, so the
  candidate's own DPDP access log claimed **they** did it — now `"system"`.
  10 review tests added (**877→887** green, pyflakes clean); smoke_s71 extended
  with both escalations as checks — **19/19 OK exit 0**. Docs corrected
  (`VERIFICATION.md` §4/§5/§7/§8/§10, `PORTAL.md` route contract). Merged to
  main fast-forward; branch `s71-identity-verification` deleted. **Deferred
  minors (DEFER):** abandoned `pending` verification rows from superseded
  challenges (PI-8 sweep); OTP salt reuses `contact_hash_salt`; `Notifier.send`
  takes the raw destination. Next: shape/plan **S7.2** (document forensics +
  moonlighting advisory) as the second producer on this spine — resolve the
  EPFO/UAN legality question in its spec, and if murky, first-party timeline
  forensics only.
- **2026-07-31** — **PI-7 opened; S7.1 (verification spine + consent-first
  identity) built** (inline TDD-offline on branch `s71-identity-verification`,
  11 tasks; spec `2026-07-31-s71-identity-verification-design.md`, plan
  `2026-07-31-s71-identity-verification.md`). Confirmed S6.4 had already merged
  to main (`814e845`, 784 green) — PI-6 COMPLETE. Brainstormed PI-7 → **three
  scope decisions taken with user, all on recommendation:** **(1) S7.1 first** —
  build `app/verification/` as a reusable spine with identity as its first
  producer, so S7.2 lands as a second producer exactly as S6.2 did on S6.1's
  `profile_sources` spine (rejected: leading with S7.3, the largest build, which
  would strand identity hooks as stubs; and merging S7.1+S7.2 into one sprint).
  **(2) v0 = an assurance ladder behind an adapter seam** shipping only what is
  buildable with no vendor and no network — self-attest, contact-control OTP,
  operator manual review — with `government_id` **declared but unimplemented**,
  its consent gate and data posture designed now (rejected: OTP-only, which
  would force S7.2 to retrofit the spine; and an outcome-recording API, which
  skips the candidate-initiated consent flow that is the whole point of
  gap-analysis §5B). **(3) two new `ConsentPurpose` members** —
  `IDENTITY_VERIFY` + `VERIFICATION_READ` (rejected: one purpose, leaving a real
  govt-ID adapter with no grant to attach to; and reusing `LEDGER_READ`, which
  would silently widen what grants candidates have *already signed* disclose).
  Delivered `app/verification/` (`schema.py`/`assurance.py`/`otp.py`/
  `methods.py`/`models.py`/`store.py`/`service.py`), migration `0013` (two
  candidate-CASCADE tables), `Services.verification` wired cycle-safe (built
  **before** the portal, which now surfaces `identity` on `MyData`), six
  endpoints across the admin/org/candidate planes, `verif_*` + `ret_verification_days`
  config, and `VERIFICATION.md`. **No LLM, no network** — fully deterministic, so
  the deterministic-fallback convention is satisfied trivially. 93 new tests
  (**784→877**, `pytest -q` green — verified this session); pyflakes clean on
  every new + modified file. Smoke `scripts/smoke_s71.py` (uvicorn, key-less)
  **16/16 OK** exit 0. **Notable during the build:** the migration nullability
  guard caught a genuine drift (`details` `nullable=True` in the migration vs
  `Mapped[dict]` NOT NULL in the ORM) — migration corrected, models kept as the
  source of truth; and the first API-test fixture used the module-level `app`
  (whose lifespan builds real services against the dev DB) and was corrected to
  this repo's `create_app(services)` pattern. Executed **inline** rather than
  subagent-driven: the harness in this session forbids spawning agents unless the
  user asks. **PENDING:** final whole-branch review + merge. Next: merge, then
  shape/plan S7.2 (document forensics + moonlighting advisory) as the second
  producer on this spine.
- **2026-07-30 (2)** — **S6.4 (candidate auth + DPDP portal) built — PI-6
  COMPLETE** (subagent-driven on branch `s64-candidate-auth-dpdp-portal`, 10
  build tasks + this closeout; spec
  `2026-07-30-s64-candidate-auth-dpdp-portal-design.md`, plan
  `2026-07-30-s64-candidate-auth-dpdp-portal.md`). Three load-bearing scope
  decisions taken with user (all on recommendation): **retention TTLs surface
  posture now, sweep deferred to PI-8** (no scheduler exists yet; a sweep built
  now would strand an un-triggered function); **first-party consent is
  additive, not a hard replace** (the admin-plane consent endpoint stays — it
  seeds tests and supports org-initiated consent-request flows); **candidate
  auth = a minted, sha256-hashed, rotatable access key** (mirrors the org key —
  offline-deterministic, zero external deps; real password/OTP/session
  registration is a PI-8 productionization concern). Two smaller calls
  confirmed with user: (a) `/portal/me` lists reports by existence + timestamp
  only, not advisory internals; (b) the access-log includes platform-internal
  actions, not just org disclosures. Delivered: migration
  `0012_candidate_credentials` (candidate CASCADE, unique on `candidate_id`;
  drift/index/FK/nullability guards extended); `CandidateStore.issue_access_key`/
  `authenticate_candidate`; `require_candidate` dependency + new dependency-free
  `candidate_router`; admin-plane `POST /candidates/{id}/auth-key` (mint, once,
  200/404/401); new pure package `app/portal/` (`schema.py`/`retention.py`/
  `service.py` — `PortalService` composing `CandidateStore`+`LedgerStore`+
  `ProfileSourceService`+`ReportStore`, owns no tables); `Services.portal` wired
  cycle-safe; `LedgerStore.consents_for_candidate`/`get_grant` (small raw-read
  additions, nothing existing changed); config knobs
  `candidate_access_key_bytes` (32) + six `ret_*_days`; six candidate-plane
  endpoints (`GET /portal/me`, `GET /portal/access-log`,
  `GET/POST /portal/consents`, `POST /portal/consents/{id}/revoke`,
  `DELETE /portal/me`). **No new `ConsentPurpose`** — self-access is gated
  purely by identity (`require_candidate`), never a consent object;
  cross-candidate isolation is structural (every handler resolves
  `candidate_id` from the key, never a param) with ownership-enforced revoke
  (identical 404 whether a `consent_id` is unknown or belongs to someone else —
  no probing). `PORTAL.md` written (peer of `LEDGER.md`/`DASHBOARD.md`). 32 new
  tests (**752→784**, `pytest -q` green — verified this session). Smoke
  `scripts/smoke_s64.py` (uvicorn, key-less) **10/10 OK** exit 0 (the smoke
  commit's subject stale-reads "(12/12)" — the correct, verified count is
  10/10): create candidate → admin mints a key → `/portal/me` shows
  profile/resumes/retention → org submits + queries a consented interview
  record → `/portal/access-log` shows it with the org's name resolved →
  first-party grant via `/portal/consents` → `GET /portal/consents` active →
  revoke → state `revoked` → wrong/absent key 401 → a second candidate's key
  cannot see or revoke candidate 1's data (404, untouched) →
  `DELETE /portal/me` erases; key then 401s; admin `GET /candidates/{id}` 404.
  Executed subagent-driven: fresh implementer + review per task across the 10
  build tasks plus this closeout; per-task review came back clean; two
  plan-text inaccuracies were self-corrected during the build (Task-8's
  route-existence test ordering; Task-9's shared-email test helper
  unexpectedly collapsing two candidates via the S1.1 email/phone-hash dedup
  path). Deferred minors carried (all DEFER, none merge-blocking): unused
  `datetime` imports in `tests/test_ledger_consents_for_candidate.py` (F401);
  two API test helpers use `client.__enter__()` without `__exit__()`
  (thread-leak, no correctness impact); the smoke commit's stale "(12/12)"
  subject; the `no_key_401` smoke check exercises absent-key only (wrong-key is
  covered by a unit test). **PI-8 follow-ups (spec §9):** mechanical retention
  sweep; real candidate registration (password/OTP/session); exposing depth
  `Report` internals to the candidate; DPDP correction/rectification right;
  grievance/DPO contact endpoint; multi-credential/device sessions. Commits
  `f3646ca..4bdbdb6` (Tasks 1–10; spec `a0450d5`, plan `d2737f6` precede), this
  closeout on top. **PENDING:** final whole-branch review + merge. **PI-6
  (candidate side & intake) COMPLETE (S6.1–S6.4).** Next: merge, then shape/plan
  **PI-7** (verification & assessment depth) per the gap-analysis §6, when its
  turn comes.
- **2026-07-30** — **S6.3 (normalization curation loop) built** (subagent-driven
  on branch `s63-normalization-curation`, 9 tasks; spec
  `2026-07-30-s63-normalization-curation-loop-design.md`, plan
  `2026-07-30-s63-normalization-curation-loop.md`). Brainstormed → three design
  decisions taken with user (all on recommendation): **skills-only scope**
  (employers/institutions curation deferred — they lack a clean `canonical=None`
  unmapped marker); **system-wide overlay on `normalize_skill`** (curated aliases
  load into an in-memory `_CURATED_OVERLAY` merged with the static index — every
  consumer benefits, `normalize_skill` stays a pure dict lookup, **static taxonomy
  always wins**); **capture from profile sources only** (resume-extraction capture
  deferred). Two smaller calls: no decision-history table (re-resolve overwrites)
  and forward-only (resolving does not re-normalize already-stored signals).
  Delivered a new pure `app/curation/` package (`schema.py` — `CurationStatus`/
  `CurationAction`/`UnmappedTerm`; `models.py` — `UnmappedTermRow`; `store.py` —
  `CurationStore` upsert-queue/`resolve`/`load_overlay`; `service.py` —
  `CurationService` capture guards + resolve validation matrix + overlay refresh),
  the overlay hook + `set_/clear_curated_overlay`/`canonical_ids`/
  `category_for_canonical` on `app/candidates/normalize/skills.py`, best-effort
  capture wired into `ProfileSourceService` (both ingest paths, only
  `canonical is None`), `Services.curation` wired cycle-safe with the overlay
  loaded once at startup, migration `0011_skill_curation` (**candidate-agnostic**
  `unmapped_terms` — no candidate FK / no consent / no CASCADE; DPDP erasure
  deliberately leaves queued terms; drift/index/nullability guards extended), two
  admin-plane endpoints (`GET /curation/skills/unmapped` + `POST
  /curation/skills/resolve`, 200/404/422), and `cur_*` config knobs (200/2/64).
  **No LLM, no network, no new consent purpose.** `CURATION.md` written;
  `PROFILE_SOURCES.md` S6.3 note flipped to shipped. 27 new tests (725→752,
  `pytest -q` green). Smoke `scripts/smoke_s63.py` (uvicorn, key-less) 16/16 OK
  exit 0: create candidate → POST LinkedIn export with novel skills (COBOL,
  PyTorch Lightning, "Team Player") → queue pending → resolve create
  `cobol`/language + map "pytorch lightning"→`pytorch` (category `ml` derived) +
  ignore "team player" → re-POST → COBOL→`cobol`, PyTorch Lightning→`pytorch`
  (live per-process overlay), "Team Player" stays unmapped & not re-queued → bad
  resolve 422, unknown 404 → DPDP-erase candidate → queued term **survives**
  (candidate-agnostic). Executed subagent-driven: fresh implementer + two-stage
  spec/quality review per task (Tasks 1–4, 6–8 review-clean; Task 5 one fix round —
  two tests strengthened to genuinely discriminate existence-before-validation
  ordering and limit-cap enforcement). Task 9 (ROADMAP closeout) was finished
  in-controller after the account session limit terminated its subagent mid-edit —
  docs-only bookkeeping, matching the S5.3 precedent. Nine deferred minors carried
  (all DEFER, none merge-blocking — in the sprint ledger). Commits
  `078eab5..` this closeout (spec `6e9f514`, plan `3c9680b` precede). **PENDING:**
  final whole-branch review + merge. Next: merge, then shape/plan S6.4 (candidate
  auth + DPDP portal).
- **2026-07-29** — **S6.2 (LinkedIn export parsing / 2nd profile_sources
  adapter) built** (TDD-offline on branch `s62-linkedin-export`, 7 tasks; plan
  `docs/superpowers/plans/2026-07-28-s62-linkedin-export.md`). Second adapter on
  the S6.1 spine, no LLM, no network: config knobs
  `max_linkedin_b64_chars`/`ps_linkedin_skill_base_confidence`/
  `ps_linkedin_skill_corroborated_confidence`/`ps_linkedin_max_rows`;
  `ProfileSourceType.LINKEDIN_EXPORT` + `LinkedInActivity` (de-identified —
  canonical employers/institutions + counts only); `ProfileSourceSignal.activity`
  generalized to a discriminated union `GitHubActivity | LinkedInActivity`
  (discriminator `kind`) with a `source_type`-derived back-compat validator so
  pre-S6.2 GitHub rows keep validating — **no migration**; `method` gained
  `"export"`. `app/profile_sources/linkedin.py`: pure `parse_linkedin_export`
  (ZIP/CSV, per-row graceful degradation, column-name variants, nested export
  dirs, row cap) + pure `to_signal` (S1.4 taxonomy map; self-reported skills are
  claims at base confidence 0.4, bumped to 0.6 once whole-token-matched against
  that export's own positions/headline; de-identified `LinkedInActivity`;
  `method="export"`/`"unavailable"`). `ProfileSourceService.ingest_linkedin`
  (existence check → parse → transform → persist via the S6.1
  `ProfileSourceStore`; identifier fixed to `"linkedin_export"`). Admin-plane
  `POST /candidates/{id}/sources/linkedin` (200 export / 200 unavailable / 404 /
  422 bad-base64 / 422 oversize); `GET /candidates/{id}/sources?source_type=...`
  already worked unchanged. **No LLM, no network, no new consent purpose** — the
  export is the candidate's own first-party data; CASCADE erasure. 28 new tests
  (697→725, `pytest -q` green). `PROFILE_SOURCES.md` rewritten to cover both
  adapters (transport, pure parse→to_signal seams, confidence model, DPDP
  posture, endpoint contract, config knobs). Smoke `scripts/smoke_s62.py`
  (uvicorn, key-less) 12/12 OK exit 0: create candidate → POST linkedin export
  (canonical + corroborated Python 0.6, uncorroborated Leadership 0.4, canonical
  employers/institutions, current_positions) → GET filtered sources (1 row) →
  bad base64 422 → DPDP erase → sources 404. Six deferred minors carried from
  the sprint ledger, all DEFER / none merge-blocking (see "Current sprint" above
  for the list). Executed subagent-driven (fresh implementer + two-stage review
  per task; fix loops on Tasks 3/4/7 — ragged-CSV per-row degradation, trailing-dot
  corroboration, DPDP-retention doc accuracy). Task 5 was interrupted by a session
  limit mid-edit and resumed from its transcript; its erasure test was corrected
  from a broken brief assertion (`list_sources` after delete raises by design) to a
  store-level CASCADE check. **PI-6 reshaped:** S6.1 GitHub [done] · S6.2 LinkedIn
  export [done] · new **S6.3 Normalization curation loop** (the deferred curation
  thread, kept explicit on the board, its own sprint, not required now) · S6.4
  Candidate auth + DPDP portal (moved down from S6.3). Whole-branch final review
  (opus) = Ready to merge Yes, no Critical/Important. **Merged to main
  (fast-forward `23972d7`→`497eedb`), branch deleted, 725 green on main. S6.2
  COMPLETE.** Next: S6.3 plan (normalization curation loop).
- **2026-07-28 (3)** — **S6.1 (GitHub-as-signal / profile-source ingestion) built**
  (inline TDD-offline on branch `s61-github-profile-source`, 9 tasks; spec
  `2026-07-28-s61-github-profile-source-design.md`, plan
  `2026-07-28-s61-github-profile-source.md`). Brainstormed PI-6; two design
  decisions taken with user (both recommendations accepted): **(1) scope S6.1 to
  GitHub-as-signal only** — build the reusable `profile_sources` spine with GitHub
  as the first adapter (LinkedIn export reshapes into S6.2); **(2) ingest + store
  only** — resume-vs-source corroboration deferred. PI-6 reshaped: S6.1 GitHub ·
  S6.2 LinkedIn export + curation loop · S6.3 candidate auth + DPDP portal.
  Delivered a new pure `app/profile_sources/` package (`schema.py` contracts +
  `ProfileSourceType`; pure `github.py::to_signal` — non-fork language byte
  aggregation → S1.4 `normalize_skill` canonical skills [unknown kept,
  `canonical=None`] + bounded evidence-monotone confidence + primary-language
  nominal tail; `store.py::ProfileSourceStore` append-only on the candidates DB;
  `service.py::ProfileSourceService` handle resolution [explicit → profile GitHub
  link → 400; unknown candidate → 404] + fetch→transform→persist), extended
  `app/services/github.py` with `GitHubUserRaw`/`GitHubRepoRaw` +
  `gather_user_signal` (graceful degradation, `ps_github_*` limits), migration
  `0010_profile_sources` (candidate CASCADE; drift/index/FK/nullability guards
  extended), `Services.profile_sources` wired cycle-safe (shares the one GitHub
  client + candidate store; `build_default_services` hoists both), admin-plane
  endpoints `POST /candidates/{id}/sources/github` + `GET /candidates/{id}/sources`
  (200/400/404; degraded fetch → 200 `method="unavailable"`). `ps_github_repo_limit`
  /`ps_github_language_repos`/`ps_github_include_forks` config knobs. **No LLM, no
  new consent purpose, no candidate PII beyond the public handle, advisory only,
  depth scoring untouched.** `PROFILE_SOURCES.md` written. 25 new tests (672→697,
  `pytest -q` green). Smoke `scripts/smoke_s61.py` (uvicorn + LIVE GitHub) 7/7 OK
  exit 0: create candidate → POST github source (method=api, activity present) →
  GET sources (1 row) → no-handle 400 → DPDP erase → sources 404. Whole-branch
  self-review clean (no Critical/Important). Merged to main (fast-forward), branch
  deleted, 697 green on main. **S6.1 COMPLETE.** Next: S6.2 plan.
- **2026-07-28 (2)** — **S5.3 (thin employer dashboard) built + merged**
  (subagent-driven on branch `s53-employer-dashboard`, 7 TDD tasks; spec
  `2026-07-28-s53-employer-dashboard-design.md`, plan
  `2026-07-28-s53-employer-dashboard.md`). Two design decisions taken with user:
  **JSON read-models only** (no HTML/UI — API-first stays primary) and **lean board +
  drill-in card** (a board load fires no extra cross-org reads; consent-gated
  composition lives in the per-candidate card). Delivered a new pure `app/dashboard/`
  package (`schema.py` contracts + `SectionStatus`; `service.py` `DashboardService`
  composing JobStore + CompService + LedgerStore, owns no tables/state) exposing three
  org-plane read-models: `GET /dashboard/overview` (org's own reqs — counts by status +
  per-req flags; no consent, no audit), `GET /jobs/{id}/board` (requisition +
  `CompService.benchmark` + top-N `run_match`; 404 cross-org, 422 empty pool; reuses
  `run_match`'s `match.surface` + comp's `comp.aggregate` audit rows, adds none),
  `GET /candidates/{id}/card` (per-section consent-gated drill-in reusing
  `reputation_for_org`/`query_coding_rounds_for_org`/`query_records_for_org`; **200 with
  per-section `SectionStatus`** available/consent_required/no_data — never hard-403s;
  404 only for an unknown candidate [`LookupError` propagates]; audit-by-reuse).
  `Services.dashboard` wired cycle-safe (S4.3/S5.1/S5.2 pattern). `dash_board_top_n`
  config knob. **No LLM, no new consent purpose, no migration, no candidate PII, no
  depth-`Report` exposure.** `DASHBOARD.md` written. 29 new tests (653→672,
  `pytest -q` green). Smoke `scripts/smoke_s53.py` (uvicorn + HTTP) 18/18 OK exit 0:
  overview → board 422 (empty pool) → board 200 (materialized, comp advisory) → card
  consent_required (no grant) → grant ledger_read → no_data → revoke → consent_required
  (all 3 sections) → cross-org board 404 → unknown-candidate card 404. Executed
  subagent-driven: fresh implementer + reviewer per task (Tasks 1–6 review-clean; Task 5
  reviewer caught + fixed a wrong-enum bug the plan carried [`InterviewStage.TECHNICAL`/
  `InterviewOutcome.PASS` → real `TECH`/`ADVANCED`]; Task 7 one Important doc-accuracy
  finding [board audit inventory omitted the reused `comp.aggregate` row] fixed + a smoke
  revoke-symmetry minor). **NOTE:** the account session limit was hit near the end, so
  the Task-7 fix's scoped re-review and the independent whole-branch final review could
  not run as subagents — the fix was applied in-controller and self-verified (smoke
  18/18, suite 672), and a controller whole-branch self-review (pyflakes clean on all
  new + modified files; `service.py` logic re-read; deferred minors resolved) stood in,
  per the user's explicit decision to merge now rather than wait for the ~7pm reset.
  Merged to main (fast-forward), branch deleted. **S5.3 COMPLETE — PI-5 (demand side)
  COMPLETE.** Next: shape PI-6 (candidate side & intake).
- **2026-07-28** — **S5.2 (comp intelligence v0) built** (inline TDD-offline on
  branch `s52-comp-intelligence`, 10 tasks; spec
  `2026-07-28-s52-comp-intelligence-design.md`, plan `2026-07-28-s52-comp-
  intelligence.md`). Also closed out S5.1 bookkeeping first (reflog confirmed S5.1
  fast-forward merged to main at `2eb591c`; ROADMAP "merge pending" prose was stale).
  Two design decisions taken with user (both recommendations accepted, rest
  delegated): **(1) capture + blend** — observed offers get a first-class,
  consent-gated CTC field (not event-payload/defer); **(2) estimate + requisition
  benchmark** surface (no comp-fit match term — no candidate expected-CTC exists
  yet). Delivered a new pure `app/comp/` package (`schema.py` contracts +
  `SeniorityBand`/role-family vocab; `bands.py` illustrative license-clean static
  seed table [role x seniority x city-tier] + `comp_bands_path` override + title/
  skill/years/tier resolvers; `estimate.py` reputation.py-style shrinkage toward the
  static prior on a **total-CTC basis** + k-anonymity floor + saturating confidence
  + benchmark; `service.py` `CompService` reading offers via `LedgerStore`),
  consent-gated `observed_offers` ledger table (peer of coding_round_results;
  `ObservedOffer`/`ObservedOfferPoint` [de-identified projection], `ObservedOfferRow`,
  migration `0009` candidate+org+consent CASCADE, drift/index/FK/nullability guards
  extended), `LedgerStore.submit_observed_offer` (`ledger_write`-gated, `consent_id`-
  stamped, audited `offer.submit`) + `observed_offers_for_comp` (**de-identified**,
  revocation-respecting stamped-grant check, audited `comp.aggregate` with
  `candidate_id=None`), `Services.comp` wiring (TYPE_CHECKING + function-local build,
  the S4.3/S5.1 cycle-safe pattern; ledger never imports comp — comp vocab validated
  at the API boundary), org-plane endpoints `POST /ledger/offers` +
  `POST /comp/estimate` + `GET /jobs/{id}/comp` (403/404/400/401). `comp_*` config
  knobs (k-floor, halflife, prior strength, confidence, seniority thresholds,
  benchmark tolerance, bands-path). **No LLM, no new consent purpose.** DPDP posture:
  cross-candidate aggregation basis = revocation-respecting inclusion + k-anonymity +
  de-identified output + audit; **documented residual** — reusing `ledger_write` data
  for aggregation (vs a dedicated purpose that would stay empty) revisited later.
  `COMP.md` written. 29 new tests (623→652, `pytest -q` green). Smoke
  `scripts/smoke_s52.py` (uvicorn + HTTP) 13/13 OK exit 0: static-only floor → 6
  consented offers → observed blend (p50 above prior, confidence above floor) →
  benchmark 'at' (band brackets p50) + 'below' (low band) → different role < k stays
  static → revoke drops one offer (n_observed 6->5) → DPDP erase tips below k
  (static-only) → cross-org benchmark 404. Whole-branch self-review clean (no
  Critical/Important; one Minor closed — `comp_bands_path` override loader now
  tested, 652->653). Merged to main, branch deleted. **S5.2 COMPLETE.** Next: S5.3
  plan (thin employer dashboard).
- **2026-07-27 (5)** — S5.1 closed out (bookkeeping only, no new code). Confirmed
  via `git reflog` that branch `s51-job-requisition-matching` was **fast-forward
  merged to main** (`2eb591c`) with the whole-branch review's hardening fix
  (`ff2ecae`) already landed; branch deleted. `pytest -q` **623 green on main**.
  The ROADMAP "Current state"/"Next action" prose was stale (still framed the merge
  as "pending") — corrected here. **S5.1 COMPLETE.** Next: brainstorm → spec → plan
  → build **S5.2** (comp intelligence v0 — static bands + ledger-observed offers,
  advisory; consumes S5.1's stored `comp_band`), per gap-analysis §6.
- **2026-07-27 (4)** — **PI-5 shaped + S5.1 built** (inline TDD-offline on branch
  `s51-job-requisition-matching`). Confirmed PI-4 already merged to main (S4.4
  done); ROADMAP "Next action" prose was stale. Brainstormed PI-5 demand side →
  scoped this sprint to **S5.1** (spec `2026-07-27-s51-job-requisition-matching-
  design.md`, plan `…-matching.md`, 10 tasks). Four design decisions delegated to
  recommendation: **org plane** (X-Org-Key), **compile-to-ranking + job-relative
  skill-coverage**, **comp band metadata-only** (S5.2 consumes it, no follow-up
  migration), **audit-every-match with no new consent gate** (pool already
  consent-masked at S4.2). Delivered new `app/matching/` package: pure `schema.py`
  contracts; pure `match.py` (`skill_coverage`/`location_fit`/`compile_ranking`/
  `compile_filters`/`match` — injects synthetic `match.skill_coverage`/
  `match.location_fit` into a FeatureVector copy and reuses S4.3 `ranking.score()`,
  zero new scoring math); ORM `JobRequisitionRow` + migration `0008` (org-owned,
  CASCADE on org, **not candidate-linked** → survives candidate erasure; drift/
  index/FK/nullability guards extended); `JobStore` (org-scoped CRUD, canonical
  skill normalization, audited `requisition.create`/`update`; `run_match` reads
  pool + point-in-time profiles at one `as_of`, ranks, audits each returned
  candidate as `match.surface` — candidate-linked + CASCADE); `Services.jobs`
  wiring (TYPE_CHECKING + function-local build, the S4.3 cycle-safe pattern);
  org-plane endpoints `POST/GET/PATCH /jobs` + `POST /jobs/{id}/match`
  (`MatchResult{advisory=True}`; cross-org 404, empty/unmaterialized pool 422,
  malformed 400). `min_years/degree/notice` are **soft** (select the dimension,
  value is not a cutoff); the **only** hard gate is opt-in `min_skill_coverage`.
  `match_*` config knobs (skill weight 3.0 dominant). No LLM, no new consent
  purpose. `MATCHING.md` written. 39 new tests (584→623, `pytest -q` green). Three
  in-flight/review fixes: `run_match` `filtered_size` = post-filter-pre-limit count
  (S4.3 parity); `smoke_s51`/API tests use `with TestClient(...)` so the lifespan
  sets `app.state.services`; whole-branch review hardened skill canonicalization
  (keep punctuation asks; all-blank skills → 400 not a reconstruct 500). Smoke
  `scripts/smoke_s51.py` (uvicorn + HTTP) 11/11 OK exit
  0: ranked strong→weak→other by skill coverage (advisory — zero-coverage still
  appears), `min_skill_coverage=0.75` gates to strong only, DPDP erase drops the
  candidate + sweeps its `match.surface` audit rows. **PENDING:** final whole-branch
  review + merge to main. Next: merge, then S5.2 plan (comp intelligence v0).
- **2026-07-06** — Brainstormed + approved product design (Talent Intelligence
  Platform slice of a Mercor-style marketplace; SQLite-now/PG-shaped; modular
  monolith). Created spec, roadmap, CLAUDE.md, memory pointer. Next: S1.1 plan.
- **2026-07-06 (2)** — S1.1 done, TDD-offline on branch `s11-extraction-schema`:
  `app/candidates/{schema,hashing,dates,extractor}.py` — CandidateProfile with
  per-field confidence + SourceSpan provenance, salted contact-dedup hashing
  (`contact_hash_salt` in config.yaml), deterministic date parser, section-based
  heuristic extractor + LLM path (`parsing` tier) with fallback. 26 new tests
  (88 green). Smoke `scripts/smoke_s11.py` green with live OpenRouter key AND
  key-less (heuristic floor). Next: S1.2 plan (candidate store).
- **2026-07-06 (3)** — S1.2 done, TDD-offline on branch `s12-candidate-store`:
  shared SQLAlchemy core (`app/core/db.py`: Base, engine w/ SQLite FK pragma +
  StaticPool, session factory; `candidates_db_url` setting), PG-shaped ORM rows
  (`app/candidates/models.py`: candidates / resumes versioned-unique /
  extractions JSON), Alembic env + `0001_candidate_store` (+ drift-guard test),
  `CandidateStore` (`app/candidates/store.py`: ingest with email→phone hash
  identity resolution + backfill, sha256 resume dedup, latest_profile,
  DPDP hard deletes, `build_candidate_store`). 25 new tests (113 green).
  Smoke `scripts/smoke_s12.py` green live (llm) AND key-less (heuristic).
  Next: S1.3 plan (API + engine wiring).
- **2026-07-06 (4)** — S1.3 implementation plan written:
  `docs/superpowers/plans/2026-07-06-s13-api-engine-wiring.md` (7 TDD tasks,
  branch `s13-api-wiring`, 113→137 tests). Scope: `Report.candidate_id` +
  `for_candidate`/`delete_for_candidate` on both report stores (guarded ALTER
  for legacy reports.db), shared `app/core/pdf.py` helper, `Services.candidates`
  via `build_candidate_store`, POST /candidates (extract → ingest → auto
  depth-eval, graph untouched), GET candidate/resumes/reports, DPDP DELETE
  endpoints (candidate erasure also deletes linked reports), uvicorn smoke
  `scripts/smoke_s13.py`. Next: execute the plan.
- **2026-07-06 (5)** — S1.3 done, TDD-offline on branch `s13-api-wiring`:
  `Report.candidate_id` + `for_candidate`/`delete_for_candidate` on both report
  stores (guarded ALTER on legacy reports.db), shared `app/core/pdf.py`,
  `Services.candidates` via `build_candidate_store`, POST /candidates
  (extract → ingest → auto depth-eval; report stamped with candidate_id;
  graph/`/evaluate` untouched), GET candidate/resumes/reports, DPDP DELETE
  resume + candidate (erasure also deletes linked reports). 24 new tests
  (137 green). Smoke `scripts/smoke_s13.py` green live (llm) AND key-less
  (heuristic) — 11/11 checks OK both runs. Final review fix: POST /candidates
  re-checks the candidate after saving the report and drops the report if the
  candidate was erased mid-eval (25 new tests, 138 green). Accepted residual:
  a milliseconds-wide erasure race between that re-check and a concurrent
  delete's report sweep — mop up via a future orphaned-reports sweep (reports
  whose candidate_id no longer resolves). Next: S1.4 plan (India
  normalization).
- **2026-07-09** — S1.4 implementation plan written:
  `docs/superpowers/plans/2026-07-09-s14-india-normalization.md` (7 TDD tasks,
  branch `s14-india-normalization`, 138→190 tests). Scope: pure deterministic
  `app/candidates/normalize/` package (no LLM, no migration, no new tables),
  Optional canonical sibling fields on the S1.1 schema, extractor wiring.
- **2026-07-16** — S1.4 done, TDD-offline on branch `s14-india-normalization`:
  `app/candidates/normalize/{text,skills,degrees,orgs,location}.py` + the
  `normalize_profile` orchestrator — norm_key alias indexing, ~85-skill
  taxonomy, Indian degree families + canonical CGPA/10 (cgpa_4×2.5, %÷9.5
  clamped), institution alias table + IIT/IIM/NIT/IIIT campus patterns with
  tiers, ~60-employer alias table with legal-suffix stripping, city gazetteer
  (metro/tier_2) + notice-period parser (both offset-preserving for
  provenance). Schema grew all-Optional canonical fields (legacy JSON still
  validates); `heuristic_profile` lifts location + notice period with spans;
  `extract_profile` normalizes both paths; prompt asks for `notice_period`.
  52 new tests (190 green). Smoke `scripts/smoke_s14.py` 8/8 OK key-less
  (heuristic floor) AND live (llm) after the user refreshed the expired
  OpenRouter key. PI-1 complete. Next: S2.1 plan.
- **2026-07-17** — S2.1 implementation plan written:
  `docs/superpowers/plans/2026-07-17-s21-ai-signals.md` (7 TDD tasks, branch
  `s21-ai-signals`, 190→~223 tests). Scope: pure `app/fabrication/ai_text.py`
  (4 deterministic detectors: template phrases, uniform bullets, metric
  saturation, symmetric structure; fusion + conservative banding), new
  `ai_signals` graph node after ingest (deterministic first, LLM stylometry
  second with confidence capped at 0.75; LIKELY requires ≥2 deterministic
  tells — LLM alone can never flag), `AIGenerationAssessment` surfaced as an
  advisory `Report.ai_generation` field + flywheel record, adversarial
  fixture, smoke `scripts/smoke_s21.py`. No migration; depth scoring
  untouched (fusion into calibration is S2.4). Next: execute the plan.
- **2026-07-17 (2)** — S2.1 done, TDD-offline on branch `s21-ai-signals`:
  `app/schemas/fabrication.py` (AISignal / AILikelihoodBand /
  AIGenerationAssessment, advisory always true), `app/fabrication/ai_text.py`
  (template-phrase density, uniform-bullet shape, round-% metric saturation,
  symmetric entry structure; detectors gated on word/bullet minimums,
  confidence grows with evaluable detectors; fuse_pairs + band_for with the
  LIKELY ⇒ ≥2 deterministic tells gate), `ai_signals` node wired
  ingest → ai_signals → claim_extraction (LLM stylometry via the `parsing`
  FAST tier — non-decisive by design, so no flagship spend; confidence
  capped 0.75, degrades to deterministic on no key/garbage),
  `Report.ai_generation` + summary advisory note + flywheel
  `record_type: "ai_signals"`. Config knobs `ai_*` in config.yaml/Settings.
  35 new tests (225 green). Smoke `scripts/smoke_s21.py` 6/6 OK key-less
  (deterministic floor) AND live (llm; read timeout raised to 600s — the
  12-bullet fixture pays one reasoning call per claim). Next: S2.2 plan.
- **2026-07-17 (3)** — S2.2 implementation plan written:
  `docs/superpowers/plans/2026-07-17-s22-cross-field-forensics.md` (8 TDD
  tasks, branch `s22-cross-field`, 225→~268 tests). Scope: pure
  `app/fabrication/cross_field.py` (conservative interval math: year-only
  dates shrink inward for overlaps / expand outward for tenure; 4 checks),
  `cross_field` node after ai_signals (explicit profile from POST
  /candidates, else deterministic heuristic fallback; NO LLM in S2.2),
  advisory `Report.cross_field` + flywheel record. Gaps always minor.
- **2026-07-17 (4)** — S2.2 done, TDD-offline on branch `s22-cross-field`:
  `app/schemas/fabrication.py` grew FindingSeverity / ConsistencyBand /
  CrossFieldFinding / CrossFieldAssessment; `app/fabrication/cross_field.py`
  (narrow/wide/month-precise intervals, timeline_overlap ≥3mo (major ≥12),
  timeline_gap ≥12mo (always minor, neutral copy), education_employment_overlap
  ≥12mo bachelor-only (major ≥24), seniority_vs_tenure with 24/48-month
  floors (senior=minor, lead+=major) needing ≥2 dated entries;
  band_for_findings + assess_cross_field with the S2.1 confidence formula),
  `cross_field` node wired ai_signals → cross_field → claim_extraction
  (uses `state.candidate_profile` when POST /candidates supplies it, else
  `normalize_profile(heuristic_profile(text))`), `EvaluationEngine.evaluate`
  + POST /candidates pass the extracted profile through,
  `Report.cross_field` + major-only summary note + flywheel
  `record_type: "cross_field"`. Config knobs `xf_*` in config.yaml/Settings.
  45 new tests (270 green). Smoke `scripts/smoke_s22.py` 9/9 OK key-less
  (NullLLM + heuristic extraction) AND live (LLM extraction; both profile
  paths land major_issues on the inconsistent fixture, genuine stays clean).
  Next: S2.3 plan.
- **2026-07-17 (5)** — S2.3 done, TDD-offline on branch `s23-resume-farm`:
  `app/fabrication/similarity.py` (contact-masking before shingling so
  identity swaps don't dodge detection, word shingles + deterministic
  MinHash over 128 permutations, algo id "minhash-v1:128x3",
  `assess_resume_farm` bands unique/near_duplicate/insufficient_data with
  escalation once a cluster of matches appears), migration
  `0002_resume_fingerprints` with CASCADE FKs so DPDP deletes cascade
  cleanly, store `save_fingerprint`/`similar_resumes`. Detection lives at
  the API layer inside POST /candidates rather than as a graph node — the
  comparison must self-exclude by candidate_id (re-uploads and new versions
  are legitimate), and the graph is deliberately kept identity-blind.
  `Report.resume_farm` + near_duplicate-only advisory summary note +
  flywheel `record_type: "resume_farm"`. Config knobs `rf_*` in
  config.yaml/Settings. 42 new tests (312 green). One review fix
  (commit f0ba555) tightened advisory framing on all reasoning paths.
  Smoke `scripts/smoke_s23.py` 11/11 OK key-less (NullLLM + heuristic
  extraction) AND live (LLM extraction): first upload of a farm template is
  unique, an identity-swapped copy from a different candidate lands
  near_duplicate at a measured estimated similarity of 0.9375 (near_duplicate
  threshold 0.80) pointing back at the original, the uploader's own
  re-upload dedupes and self-excludes cleanly while still correctly
  matching the other farm member, a genuine resume stays unique, and
  POST /evaluate carries no farm assessment (no identity, no comparison).
  The smoke script's original re-upload check asserted the wrong property
  (expected `unique`, ignoring that a genuine near-duplicate was already in
  the corpus) and was corrected mid-session to assert self-exclusion
  directly — a script bug, not a product bug. Next: S2.4 plan.
- **2026-07-18** — S2.4 implementation plan written:
  `docs/superpowers/plans/2026-07-18-s24-fabrication-risk.md` (7 TDD tasks,
  branch `s24-fabrication-risk`, 312→~345 tests). Scope: pure deterministic
  `app/fabrication/risk.py` (band→risk mapping as code constants; fused score
  = 0.7·confidence-weighted mean + 0.3·max component risk; coverage
  confidence `min(0.9, 0.30 + 0.15·evaluated)` so single-subsystem fusion
  never asserts; ELEVATED requires ≥2 components at their top band —
  mirrors S2.1's ≥2-tells gate), computed in the scoring node (the
  calibration stage) with depth/verdicts provably untouched,
  `Report.fabrication_risk` + summary note on moderate/elevated + flywheel
  `record_type: "fabrication_risk"`, config knobs `fr_*`, smoke
  `scripts/smoke_s24.py`. No LLM, no migration. Next: execute the plan.
- **2026-07-18 (2)** — S2.4 done on branch `s24-fabrication-risk` (subagent-
  driven: 7 tasks, each spec+quality reviewed; final whole-branch review
  clean). Delivered per plan: contracts (FabricationRiskBand / RiskComponent
  / FabricationRiskAssessment), `app/fabrication/risk.py` (build_components
  excludes absent/insufficient signals; fuse = 0.7·weighted-mean + 0.3·max;
  confidence min(0.9, 0.30+0.15·evaluated) — one subsystem ⇒ 0.45 ⇒ never
  asserts), scoring-node fusion (depth/verdicts untouched, tested at node,
  pipeline, and both API entry paths), Report field + moderate/elevated
  advisory note + flywheel record, `fr_*` knobs, FABRICATION.md S2.4 docs.
  ONE DELIBERATE PLAN DEVIATION: the live smoke (first run 9/10) caught a
  genuine resume fusing to moderate off a single soft signal (ai=possible
  0.45 + rf=unique 0.10, cross_field dropped out ⇒ score 0.318 ≥ 0.30), so
  `band_for_risk` grew a MODERATE corroboration gate (flagged ≥1 OR
  non-clean ≥2; commit d7c23f5) mirroring the ELEVATED ≥2-flags gate —
  strictly more conservative, live re-run 10/10. Also: fr_weight=0 does not
  fully mute a subsystem (documented, not changed); smoke scratch-dir leak
  is a pre-existing pattern across all smoke scripts. 350 tests green.
  PI-2 complete. Next: S3.1 plan.
- **2026-07-19** — S3.1 implementation plan written:
  `docs/superpowers/plans/2026-07-19-s31-ledger-schema-consent.md` (7 TDD
  tasks, branch `s31-ledger-consent`, 350→~395 tests). Scope: new
  `app/ledger/` package — Pydantic contracts + StrEnum taxonomies
  (stage screen/tech/coding/hm, outcome, purpose ledger_write/ledger_read),
  pure clock-free consent logic (`consent.py`: purpose/org scope, always-
  expiring, revocation as point-in-time boundary, naive-UTC coercion for
  SQLite), ORM rows on the shared Base (organizations, consent_grants,
  interview_records, evaluation_events, audit_log), migration
  `0003_evaluation_ledger` (candidate-linked rows CASCADE ⇒ existing DPDP
  erasure sweeps the ledger; orgs survive), `LedgerStore` with write-time
  ConsentError gate on record submission + audit row in the same
  transaction, config knob `ledger_consent_default_ttl_days: 365`,
  direct-store smoke `scripts/smoke_s31.py` (key-less; S3.1 is LLM-free),
  `LEDGER.md`. No HTTP APIs (S3.2), no LLM. Next: execute the plan.
- **2026-07-20** — S3.1 done, subagent-driven on branch `s31-ledger-consent`
  (7 tasks). Delivered per plan: `app/ledger/` contracts + taxonomies, pure
  consent logic (`consent.py`: purpose/org scope, always-expiring,
  revocation as a point-in-time boundary, naive-UTC coercion), ORM rows +
  migration `0003_evaluation_ledger` (candidate-linked rows CASCADE, orgs
  survive), `LedgerStore` (organizations; grant/revoke/status consent;
  `submit_interview_record` raises `ConsentError` without an active
  `ledger_write` grant and stamps the authorizing consent_id;
  `append_event`; audit row written in the same transaction as every
  mutation), config `ledger_consent_default_ttl_days: 365`, direct-store
  smoke `scripts/smoke_s31.py`, `LEDGER.md`. 42 new tests (350→392). TWO
  DEVIATIONS FROM PLAN: (a) migration 0003 landed in Task 3 instead of
  later — the metadata-wide drift guard fires as soon as ledger models are
  imported, so the migration has to exist from that point on; (b) store
  converters normalize datetimes through `as_utc` because SQLite refetch
  returns naive datetimes and pydantic model equality broke on that — the
  plan's converter code was fixed accordingly, tested explicitly. Smoke
  `scripts/smoke_s31.py` run key-less: all 10 checks OK, extraction method
  `heuristic`, exit 0, `SMOKE OK`. One smoke-script bug found and fixed
  in-session (not a product bug): the "mutations audited in order" check
  compared a stale `audit_actions` snapshot taken before `revoke_consent`
  ran, so `consent.revoke` was never in it — fixed by re-fetching
  `audit_for_candidate` after the revoke call, matching the plan's own note
  that revoke is audited as the 4th action. Full suite: 392 passed
  (`pytest -q`). Status board left at `[~]` — final whole-branch review +
  merge is still pending. Next: final whole-branch review + merge.
- **2026-07-20 (2)** — S3.1 closed out. Final whole-branch review (most
  capable model): Ready to merge, one Important finding — caller-supplied
  aware non-UTC datetimes were stored wall-clock by SQLite (tzinfo dropped),
  so an IST-aware revocation would read back 5.5h late: a fail-open window
  once S3.2 accepts API datetimes. Fixed in 4dd09d0: `grant_consent` /
  `revoke_consent` / `submit_interview_record` route `now`/`expires_at`/
  `interviewed_at` through `as_utc` at write; failing-first IST test added
  (393 tests). Also documented `delete_organization`'s cascade semantics
  (org's grants→records→events go; candidate-linked audit rows survive) in
  LEDGER.md + docstring, and bounded `ledger_consent_default_ttl_days`
  (ge=1). Re-review verdict: Ready to merge, unconditional. Accepted
  residuals for S3.2 (logged in `.superpowers/sdd/progress.md`): drift
  guard blind to index/ondelete/nullability drift (cascade on migrated
  schema only proven by smoke), nondeterministic consent_id under
  overlapping grants, consent_status generic denial vs LookupError
  (404-vs-403 shape), org-create TOCTOU IntegrityError mapping, UUID
  tie-break ordering. Merged to main (fast-forward dc822e3→4dd09d0), 393
  green on main, branch deleted. S3.1 COMPLETE. Next: S3.2 plan.
- **2026-07-22** — S3.2 done, subagent-driven on branch `s32-ledger-apis`
  (11 tasks, each spec+quality reviewed; final whole-branch review opus).
  Plan: `docs/superpowers/plans/2026-07-22-s32-ledger-apis.md`. Delivered:
  two HTTP auth planes over `LedgerStore` — ADMIN (`X-API-Key` on `router`:
  `POST/GET /ledger/orgs`, rotate `/api-key`, `DELETE`, consent
  grant/revoke/status) and ORG (`X-Org-Key`→org via `authenticate_org` on a
  dependency-free `org_router`, each handler `Depends(require_org)`;
  `POST /ledger/records` write-consent gated → 403/404, `POST
  /ledger/records/{id}/events` ownership-enforced → 404, `GET
  /ledger/candidates/{id}/records` query-time `ledger_read` enforcement + audit
  of every read attempt allowed/denied in the same txn). Org API keys
  (`secrets.token_urlsafe`, sha256-hashed, rotatable; migration
  `0004_org_api_keys` col + unique index; suspended orgs never authenticate),
  `ledger_api_key_bytes` knob (32, ge=16). Four S3.1 residuals closed:
  deterministic authorizing-grant selection (`consent.py` `_selection_key`:
  org-specific ▸ newest ▸ lowest id), `consent_status` LookupError→404 vs
  denied-200, `create_organization` insert-then-map IntegrityError→ValueError
  (no TOCTOU), drift guard now checks indexes/FK-ondelete/nullability.
  `Services.ledger` injected sharing the candidate DB (conftest builds both on
  one session factory). 29 new tests (393→422). Smoke `scripts/smoke_s32.py`
  (uvicorn HTTP) 9/9 OK exit 0, key-less-capable. One authorized deviation
  across the HTTP test tasks: `asyncio.run(...)` replaced the brief's
  deprecated `asyncio.get_event_loop().run_until_complete(...)`. Final
  whole-branch review (opus): Ready to merge Yes, NO Critical/Important code
  defects; all 13 accumulated Minors triaged DEFER; two recommended doc notes
  added to LEDGER.md (event-append inherits submit-time grant + is swept on
  erasure; a single `ledger_read` grant exposes the candidate's cross-org
  history — reputation-network semantics). Merged to main (fast-forward
  7a9fdcf→a948401), 422 green on main, branch deleted. PI-3 now S3.1+S3.2
  complete. Next: S3.3 plan (coding-round results — schema + ingest only).
- **2026-07-25** — S3.3 done, inline TDD-offline on branch
  `s33-coding-round-results` (6 tasks; spec
  `docs/superpowers/specs/2026-07-25-s33-coding-round-results-design.md`, plan
  `docs/superpowers/plans/2026-07-25-s33-coding-round-results.md`). Design
  decisions taken with user (all recommendations accepted): standalone
  `coding_round_results` table (a peer of `interview_records`, NOT an overload —
  the `stage=coding` interview_record is a coarse pipeline outcome; a coding
  ROUND RESULT is a structured platform assessment); reuse `ledger_write`/
  `ledger_read` consent (no coding-specific purposes); `platform` as a
  `CodingPlatform` StrEnum + `OTHER`/`platform_name` escape; "considered" field
  set (platform, platform_name?, assessment_name?, score, max_score?,
  percentile?, problem_tags[], taken_at, raw{}) so S3.4/PI-4 need no follow-up
  migration. Delivered: contracts + StrEnum, `CodingRoundResultRow` +
  migration `0005_coding_round_results` (drift/index/FK-ondelete/nullability
  guards extended to it), store methods mirroring interview records
  (`submit_coding_round` write-gated + `consent_id`-stamped + `coding_round.submit`
  audit in-txn; `query_coding_rounds_for_org` query-time `ledger_read` + audit of
  every allowed/denied attempt as `coding_round.query`; `coding_rounds_for_candidate`
  raw read), two org-plane endpoints (`POST /ledger/coding-rounds`,
  `GET /ledger/candidates/{id}/coding-rounds`), LEDGER.md S3.3 section. Field
  bounds are data hygiene only — NO scoring/normalization (that's S3.4). No new
  config knob, no LLM. 20 new tests (422→442, `pytest -q` green). Smoke
  `scripts/smoke_s33.py` 7/7 OK exit 0 (submit-403 → grant-write → submit →
  query-403 → grant-read → query-200 [1 result] → DPDP-erase → query-404); the
  run also exercised the live LLM extraction path. Whole-branch self-review
  clean (no Critical/Important; migration↔ORM parity proven by the drift guard).
  Merged to main (fast-forward from 4f63cdc), 442 green on main, branch deleted.
  S3.3 COMPLETE — PI-3 now S3.1–S3.3 done. Next: S3.4 plan (cross-company
  reputation).
- **2026-07-26** — Vision gap analysis written (docs only, no code):
  `docs/superpowers/specs/2026-07-26-veritas-vision-gap-analysis.md`. Audited
  the whole product against the Mercor-for-India reference anatomy
  (ingest/verification/assessment/reputation/intelligence/flywheel/marketplace/
  platform). Key findings: biggest strategic gap is AI interview delivery;
  demand side (job schema, matching, comp bands) entirely absent; candidate-
  facing DPDP surface (auth, my-data portal, first-party consent, retention
  TTLs) needed before identity/KYC or AI interviews can land; identity
  verification + document forensics (experience-letter mills, proxy interviews,
  moonlighting) are the India-specific trust builds. Old flat PI-5 backlog
  superseded by shaped PI-5 (demand side) / PI-6 (candidate side & intake) /
  PI-7 (verification & assessment depth) / PI-8 (scale & learning); standing
  non-goals: payments/payroll, sourcing, native coding assessments. §8 lists
  research items to close at future spec time (DigiLocker/Consent Manager
  terms, Hinglish speech models on the Qwen-tier cost stance, EPFO legality,
  partner payload formats, license-clean comp data). Status board updated;
  S3.4 remains the next action — the vision doc changes nothing about it.
- **2026-07-26 (2)** — Model shortlist researched live (web) + two user
  decisions recorded. (1) **English-first**: launch vertical is IT jobs, so
  interviews/resumes are English (Indian-accented); Hinglish/regional intake
  DEFERRED to later verticals (media/entertainment) — gap-analysis §5/§6 and
  board updated accordingly. (2) `MODELS.md` created (root, beside FLOW/LEDGER
  docs): P1 ASR → Qwen3-ASR 1.7B (Jan 2026, Apache 2.0; Srota Hinglish
  fine-tune noted for the deferred phase), hosted alt Sarvam ASR ₹30/hr
  (DPDP-friendly India hosting); P2 TTS → Kokoro-82M (Indian-English voice),
  hosted alt Sarvam Bulbul; P3 text → Qwen tiers unchanged, Kimi K3
  (2026-07-16, OpenRouter $3/$15) flagged decisive-tier candidate — re-check
  pricing ~2 weeks after its 2026-07-27 open-weights drop; P4 embeddings →
  Qwen3-Embedding (0.6B/8B, top open MTEB v2); P5 reranker → Qwen3-Reranker.
  User actions: Sarvam account (free credits), bookmarks, no OpenRouter
  changes through PI-4. Docs only, no code; S3.4 still next.
- **2026-07-26 (3)** — Cost-first model config applied (config.yaml +
  `app/core/config.py`, all `DEE_*`-overridable knobs). Live OpenRouter pricing
  pulled from the API: swapped `model_reasoning` + `model_scoring` →
  `deepseek/deepseek-v3.2` ($0.269/$0.400 vs qwen3.7-max $1.475/$4.425, ~5–11x
  cheaper, equal quality for our decisive path); qwen3.7-max retained only as
  `model_reasoning_hard`; fast/bulk unchanged. Added inert future-slot knobs
  (`speech_provider`/`asr_model`/`tts_model`/`embedding_model`/`reranker_model`)
  — key finding: **OpenRouter serves audio models on the existing account**
  (voxtral-small-24b ASR $0.10/$0.30, live-pinged OK), so speech needs no new
  signup for v0; Sarvam demoted to prod India-residency option. Verified:
  deepseek-v3.2 + voxtral live-pinged through the project key; 442 offline green;
  full live pipeline smoke `scripts/smoke_s24.py` 10/10 exit 0 on deepseek-v3.2
  (depth solid, fabrication fusion clean). Decision record: `MODELS.md`. Windows
  gotcha logged: config.yaml comments must stay ASCII (cp1252 read). S3.4 still
  the next action.
- **2026-07-26 (4)** — S3.4 done, inline TDD-offline on branch
  `s34-cross-company-reputation` (6 tasks; spec
  `docs/superpowers/specs/2026-07-26-s34-cross-company-reputation-design.md`,
  plan `docs/superpowers/plans/2026-07-26-s34-cross-company-reputation.md`).
  **PI-3 COMPLETE.** One design decision taken with user: negative-signal stance
  = **one corroboration-gated band** (recommended); user delegated the rest.
  Delivered: cross-company reputation as a **derived, `ledger_read`-gated read**
  over `interview_records` + `coding_round_results` — NO new record type, NO
  graph node, NO `Report` field, NO LLM. Pure `app/ledger/reputation.py`
  (the `fabrication/risk.py` pattern): outcome→value code-constant map
  (`withdrawn` excluded), coding normalization (percentile ▸ score/max_score ▸
  excluded), per-obs weight = type·recency-halflife·per-org-reliability,
  **Beta-Binomial posterior** shrunk toward a neutral 0.5 prior, saturating
  confidence. Bands `INSUFFICIENT_DATA/GUARDED/MIXED/FAVORABLE/STRONG` —
  `STRONG` and `GUARDED` (the only negative band) each need ≥2 distinct orgs, so
  single-source high caps at FAVORABLE / single-source low at MIXED (mirrors
  S2.4's ≥2-flags gate). Contracts (`ReputationBand`/`ReputationComponent`/
  `ReputationAssessment`, `advisory=True`) + `Organization.reliability_weight`;
  migration `0006_org_reliability_weight` (nullable col, neutral default 1.0;
  drift guard extended). Store `reputation_for_org` (query-time `ledger_read`,
  audits every attempt allowed/denied as `reputation.query` in-txn, band+counts
  in details) + `set_org_reliability` (admin, `org.set_reliability` audit,
  weight ≥0). Endpoints `GET /ledger/candidates/{id}/reputation` (org plane,
  403/404) + `POST /ledger/orgs/{id}/reliability` (admin, 404/422). `rep_*`
  config knobs (prior, halflife, thresholds, corroboration-orgs, type weights).
  LEDGER.md S3.4 section. 26 new tests (442→468, `pytest -q` green). Smoke
  `scripts/smoke_s34.py` 9/9 OK exit 0 (also exercised live LLM extraction):
  2 orgs × 2 hired + 1 coding ⇒ `band=strong score=0.784 orgs=2 obs=6`;
  reputation-403 → grant read → 200 → set reliability → coherent shift → DPDP
  erase → 404. Whole-branch self-review clean (no Critical/Important; two DEFER
  minors: all-orgs-reliability-0 yields component mean_value 0.0 under a safe
  INSUFFICIENT_DATA band; `_settings()` helper duplicated per test file).
  Reputation is now available to PI-4 ranking as a consent-gated advisory
  feature (never an auto-reject gate). Next: S4.1 plan (feature registry).
- **2026-07-26 (5)** — S4.1 done, inline TDD-offline on branch
  `s41-feature-registry` (10 tasks; spec
  `docs/superpowers/specs/2026-07-26-s41-feature-registry-design.md`, plan
  `docs/superpowers/plans/2026-07-26-s41-feature-registry.md`). **PI-4 started.**
  Two design decisions taken with user (both recommendations accepted, user
  delegated the rest): (1) registry shape = **code-first `@register_feature`
  decorator** (mirrors `@register_domain`), not a DB table; (2) ledger/reputation
  features are **in the seed catalog, tagged `requires_consent`** (enforcement
  deferred to S4.2/S4.3). Delivered a new pure package `app/features/`:
  `schema.py` (FeatureSpec metadata + dtype/source StrEnums + FeatureContext
  point-in-time snapshot with cached `reputation` accessor + FeatureView +
  FeatureVector), `registry.py` (FeatureRegistry with collision guard /
  latest-version / `compute_one` output validation / `compute_view` / manifest,
  `@register_feature` + module-global default registry + `latest_view`),
  `context.py` (`build_context` store assembler — coarse `created_at <= as_of`
  cutoff; full historical slicer is S4.2), and `definitions/` seed catalog: **31
  features** across candidate (12), depth (7), fabrication (5), ledger (4,
  consent-tagged), reputation (3, consent-tagged). `core_v1` default view + one
  config knob `feat_default_view` (no numeric behavior knobs — feature logic is
  code-versioned like domains + the reputation outcome map). NO migration, NO
  HTTP, NO LLM, NO Report field, NO graph node (values/persistence = S4.2;
  serving/ranking = S4.3; labels = S4.4). DPDP: no new candidate-linked table ⇒
  no new erasure path; `build_context` returns None after erasure. `FEATURES.md`
  written (peer of LEDGER.md/FABRICATION.md). 39 new tests (468→507, `pytest -q`
  green). Smoke `scripts/smoke_s41.py` (uvicorn populate → direct feature
  compute) 10/10 OK exit 0 (also exercised the LIVE LLM extraction path):
  candidate → 31-feature vector (years_experience 8.08, depth_score 0.72,
  fabrication low, consent-gated interview_records 2, best_coding_percentile 92,
  reputation.score 0.70); a distinct no-ledger candidate → ledger counts 0,
  percentile missing, reputation insufficient_data. Two pre-exec plan-review
  fixes (report `created_at` cutoff; smoke 2nd candidate needs a distinct email
  or identity-resolution merges it) and two in-flight test fixes (InterviewRecord/
  CodingRoundResult require `id`+`created_at`; reputation unit test needed ≥6 obs
  to clear the confidence floor). No new residuals. Next: S4.2 plan
  (materialization → wide `ml_features` table + point-in-time slicer + export).
- **2026-07-27** — S4.2 done, inline TDD-offline on branch `s42-materialization`
  (9 tasks; spec `docs/superpowers/specs/2026-07-26-s42-materialization-design.md`,
  plan `docs/superpowers/plans/2026-07-26-s42-materialization.md`). Three design
  decisions taken with user (all recommendations accepted, user delegated the
  rest): (D1) consent enforcement = **per-candidate gate, one global platform
  table** — consent-tagged features materialize only under an active `ledger_read`
  grant at `as_of` (org-agnostic: any org / org=NULL), else nulled + reason;
  first-party features always materialize; every decision audited. (D2) storage =
  **compact row-per-vector** with a JSON `feature_values` column (migration-free as
  the catalog grows; wide shape is an export-time pivot). (D3) parquet =
  **CSV always (stdlib) + guarded optional `pyarrow`** (not a core dep). Delivered:
  point-in-time slicer — `CandidateStore.profile_as_of` (newest extraction ≤ as_of)
  and `build_context` now honors `as_of` on profile/report/ledger/consent/reputation
  (stays a raw assembler; consent policy lives in the materializer);
  `consent.has_any_active` (org-agnostic active-grant check) +
  `LedgerStore.materialization_consent` (audited `feature.materialize`, allowed &
  withheld, never raises on withheld); `app/features/materialize.py`
  (`MaterializedVector` + `materialize_candidate`/`materialize_all`, masks
  `requires_consent` features to null when withheld); `ml_feature_vectors` table
  (ORM `FeatureVectorRow` + migration `0007`, unique cut = idempotent upsert,
  CASCADE FK ⇒ DPDP erasure sweeps it, drift/index/FK/nullability guards extended)
  + `FeatureStore` (upsert/get/vectors_for_view, `as_of` keyed naive-UTC);
  `app/features/export.py` (wide `export_view_csv` stdlib pivot in `view.members`
  order; `export_view_parquet` typed per dtype, raises `ParquetUnavailable` when
  pyarrow absent). Reused `feat_default_view` — no new numeric knob, no LLM, no HTTP
  (materialization is a batch/script concern; serving = S4.3). `FEATURES.md` S4.2
  section. 22 new tests (507→529, `pytest -q` green). Smoke `scripts/smoke_s42.py`
  (uvicorn populate → direct materialize/persist/export) 11/11 OK exit 0 (also
  exercised the live LLM extraction path): candidate A (consented, FUTURE-dated
  ledger rows) → allowed, ledger count **0 at now** but **2 later** (point-in-time
  proof: rows that exist now are invisible at the earlier cut), percentile 92 later;
  candidate B (no consent) → consent features **null + masked**, first-party intact;
  wide CSV header in view order; parquet guarded (skipped, pyarrow absent); DPDP
  erase of A cascades its vector away. One smoke-script ordering bug fixed in-session
  (the "two persisted vectors" count was read AFTER the erase — captured pre-erase;
  a script bug, not a product bug). Whole-branch self-review clean (no
  Critical/Important; migration↔ORM parity proven by the drift guard). Merged to
  main (fast-forward), 529 green on main, branch deleted. S4.2 COMPLETE. Next: S4.3
  plan (talent search/ranking API over `ml_feature_vectors`).
- **2026-07-27 (2)** — S4.3 done, inline TDD-offline on branch `s43-talent-search`
  (8 tasks; spec `docs/superpowers/specs/2026-07-27-s43-talent-search-ranking-design.md`,
  plan `docs/superpowers/plans/2026-07-27-s43-talent-search-ranking.md`). Three
  design decisions taken with user (all delegated to the recommendation): (D1)
  **admin plane only** (`X-API-Key`) — reading the S4.2-masked vectors as-is means
  no new consent gate / no new disclosure surface; org-facing job-conditioned
  matching stays PI-5. (D2) **pool-independent normalization** via
  `FeatureSpec.valid_range`/category index (reproducible), pool-min-max fallback
  only for range-less count features. (D3) **drop-term + renormalize + report
  `coverage`** so consent-withheld/absent data never lowers rank. Delivered: pure
  `app/features/ranking_schema.py` (contracts) + `app/features/ranking.py`
  (`apply_filters`/`normalize_value`/`score`, the risk.py pattern — no I/O/clock),
  `FeatureStore.latest_as_of`, `Services.features` wiring (import-cycle-safe:
  TYPE_CHECKING annotation + function-local `build_feature_store`), admin endpoint
  `POST /talent/search` → `SearchResult{advisory=True}` (400 unknown-feature/
  malformed-filter, 422 empty-ranking, 401 no-key, empty-200 unmaterialized view),
  `search_default_limit` knob, FEATURES.md S4.3 section. No new table/migration/LLM;
  DPDP path unchanged (reads rows that already CASCADE on erasure). 35 new tests
  (529→564, `pytest -q` green). Smoke `scripts/smoke_s43.py` (uvicorn + HTTP) 8/8 OK
  exit 0 (also exercised the live LLM ingestion path): three unconsented candidates
  → materialize/persist → ranked senior→mid→junior with contributions, a filter
  narrowed the pool to 2, and consent-withheld candidates ranked with reduced
  `coverage` (reputation dropped) NOT pushed to the bottom. Whole-branch self-review:
  one Important fix (malformed filter value → 400 not 500; catch TypeError at the
  boundary + test) and one Minor cleanup (dropped unused `_ORDER_OPS`); no other
  Critical/Important. S4.3 COMPLETE — PI-4 now S4.1–S4.3 done. Next: S4.4 plan
  (training-set export — features ⋈ outcomes, leakage-free at the `as_of` cut).
- **2026-07-27 (3)** — S4.4 done, inline TDD-offline on branch
  `s44-training-set-export` (9 tasks; spec
  `docs/superpowers/specs/2026-07-27-s44-training-set-export-design.md`, plan
  `docs/superpowers/plans/2026-07-27-s44-training-set-export.md`). **PI-4 COMPLETE.**
  Four design decisions taken with user (all recommendations accepted, user
  delegated the rest): (D1) **ledger-only labels** — the flywheel `outcome` field
  is a permanent `None` placeholder (`report.py`), so interview outcomes + coding
  results are the only real point-in-time label source (flywheel report outcomes
  need a feedback API first — future); (D2) **compact censoring-aware label block**
  (`hired`/`outcome`/`coding_best_percentile`/`event_at`/`lag_days`/`observed`/
  `withheld`) — `observed=False` = right-censored, NOT a negative; (D3) **reuse the
  S4.2 consent decision + audit the join** — a withheld vector's label is withheld
  and its ledger is never read, consistent with masked `ledger.*` features; (D4)
  **library + script deliverable** (no HTTP/table), mirroring S4.2. Delivered: pure
  `app/features/training.py` `build_label` (post-cut-only via **strict `> as_of`** =
  no leakage; terminal-best `hired>offer>advanced>rejected>no_show`, `withdrawn`
  excluded; hire-positive `{hired,offer}`; `event_at`=earliest carrier, `lag_days`;
  `coding_best_percentile`=max post-cut) + orchestrator `build_training_set`
  (reads ledger only when consented, audits every join); contracts
  `training_schema.py` (`TrainingLabel`/`TrainingExample`);
  `LedgerStore.audit_training_label` (audits reused decision as `training.label`);
  `export.py` shared `feature_columns`/`vector_cells` helpers +
  `export_training_csv`/`export_training_parquet` (wide pivot + 7 `label_*` cols);
  FEATURES.md S4.4 section. No new table/migration/HTTP/LLM/config knob; DPDP path
  unchanged (labels recompute from CASCADE-swept ledger rows; `training.label`
  audit rows candidate-linked + CASCADE). 20 new tests (564→584, `pytest -q` green).
  Smoke `scripts/smoke_s44.py` (uvicorn + HTTP populate → direct materialize →
  build+export) 10/10 OK exit 0 (also exercised the live LLM ingestion path): A
  consented → post-cut HIRED label (`hired=True`, `lag~30d`) while its features stay
  point-in-time (pre-cut interview count 0 — the post-cut record drives the label
  but never leaks into features); B consented but only a PRE-cut hired → censored
  (`observed=False`, `hired=None` — pre-cut positive does NOT leak); C unconsented →
  `withheld=True` label + consent-masked features + `training.label` withheld audit;
  labeled CSV header ends with the 7 label columns; parquet guarded. One correctness
  fix over the plan draft (smoke `T=now` captured after ingest so the cut post-dates
  the extraction `created_at`, else `profile_as_of` returns None and materialize
  yields None). Next: whole-branch review + merge, then shape PI-5 (demand side).
