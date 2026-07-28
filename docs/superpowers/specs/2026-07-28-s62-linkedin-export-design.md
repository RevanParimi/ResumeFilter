# S6.2 — LinkedIn export parsing (2nd profile-source adapter) — Design

**Date:** 2026-07-28
**PI / Sprint:** PI-6 (Candidate Side & Intake) · S6.2
**Status:** Approved design — ready for implementation plan.
**Read first:** `docs/ROADMAP.md`, then `PROFILE_SOURCES.md` (the S6.1 spine),
then `docs/superpowers/specs/2026-07-28-s61-github-profile-source-design.md`, then
this document.

---

## 1. Why this sprint

The gap analysis (§5.A) names the intake-breadth gap: *"Only resume text/PDF
intake; no LinkedIn/GitHub profile ingestion as a first-class source."* S6.1
closed the GitHub half and built the reusable `app/profile_sources/` spine. S6.2
adds the **second adapter on that spine — LinkedIn export parsing** — completing
the profile-ingestion story for the launch (IT) vertical.

The India angle: LinkedIn is under-maintained by many tier-2/3 candidates, but the
ones who *do* keep it hold structured position/education/skill history that a PDF
resume flattens. Ingesting the candidate's own **LinkedIn data export** recovers
that structure as advisory evidence, exactly as GitHub recovers OSS evidence.

Unlike GitHub, there is **no network fetch**: LinkedIn's *"Get a copy of your
data"* produces a **ZIP of CSVs** that the candidate downloads and uploads to
Veritas. So GitHub's "live fetch" seam is replaced by a **pure parse-bytes** seam;
everything downstream (pure transform → append-only store → advisory signal →
CASCADE erasure) is identical to S6.1.

## 2. Scope decisions (taken with user, 2026-07-28)

1. **LinkedIn export adapter only for S6.2** (not adapter + curation loop
   together). The reshaped-PI bundle put a normalization *curation loop* alongside
   this adapter; per the scope call it is **deferred to its own sprint** — kept on
   the roadmap, not dropped, not required now. Reason: two substantial, largely
   independent builds; and the curation loop is best designed once *both* adapters
   are feeding it real drift.
2. **Skills + de-identified activity; no raw contact PII.** The stored signal
   carries S1.4-mapped skills + activity aggregates (position/education/cert
   counts, canonical employers & institutions, headline, industry, languages). It
   does **not** persist raw contact PII (email/phone/address) or profile summary
   free-text — minimizing erasure surface and keeping the output advisory.
3. **Conservative + corroboration confidence.** LinkedIn `Skills.csv` entries are
   self-asserted *claims*, not GitHub's byte-measured evidence, so they get a low
   flat base confidence, bumped only when corroborated by a position
   title/description or the headline (§5.3).

### PI-6 reshape (record in ROADMAP)

```
PI-6  CANDIDATE SIDE & INTAKE
 ├ S6.1  GitHub-as-signal  (profile_sources spine + github adapter)   [DONE]
 ├ S6.2  LinkedIn export parsing (second adapter on the spine)        ← THIS
 ├ S6.3  Normalization curation loop  (surface taxonomy drift from all adapters;
 │       deterministic files, human-reviewed — no auto-learning)      [deferred here]
 └ S6.4  Candidate auth + DPDP portal (my-data / who-accessed / revoke /
         retention TTLs; first-party consent capture)
```

The curation loop (was bundled into S6.2) becomes **S6.3**; candidate auth + DPDP
portal slides to **S6.4**. The curation loop stays explicitly in the PI.

## 3. Non-negotiables inherited (do not relitigate)

- **Advisory only.** The signal is *evidence*, never a score, never a gate, never
  auto-anything. Depth-eval scoring and verdicts are untouched.
- **Deterministic, no LLM.** The bytes→raw parse and raw→signal transform are pure
  Python (CSV parsing + taxonomy mapping). No API key is ever required. There is
  **no network at all** in this adapter.
- **DPDP: first-party only.** The candidate uploads *their own* export. Same
  posture as PI-1 resume ingest. Every candidate-linked row CASCADEs on erasure.
- **TDD offline; smoke per sprint; Postgres-shaped SQLite; reuse the S6.1 table
  (no migration).**

## 4. Architecture

```
     candidate's LinkedIn "Get a copy of your data" ZIP (base64 in JSON body)
                                   │
        POST /candidates/{id}/sources/linkedin      GET /candidates/{id}/sources
                                   │                             │
                                   ▼                             ▼
                         ProfileSourceService  ───────►  ProfileSourceStore
                     .ingest_linkedin(id, bytes)         (candidates DB, CASCADE)
                                   │  ▲                    [SAME S6.1 store/table]
       parse_linkedin_export(bytes)│  │ to_signal(raw, settings)  [PURE, no I/O]
                                   ▼  │
                         LinkedInExportRaw          normalize_skill()  [S1.4 reuse]
                    (pure zip/CSV parse)            canonicalize_employer/institution()
```

**Seams (each independently testable):**

- **Pure parse** (`profile_sources/linkedin.py::parse_linkedin_export(bytes)`) —
  the analog of GitHub's live fetch, but pure (in-memory `zipfile`+`io.BytesIO`).
  Graceful degradation: non-zip / empty / no recognizable LinkedIn CSVs →
  `available=False` + warnings, never raises.
- **Pure transform** (`profile_sources/linkedin.py::to_signal`) — raw DTO → typed
  `ProfileSourceSignal`. No I/O; exhaustively unit-tested offline.
- **Persistence** (`ProfileSourceStore`) — **unchanged** S6.1 store; new rows just
  carry `source_type="linkedin_export"` and a `LinkedInActivity` payload.
- **Orchestration** (`ProfileSourceService.ingest_linkedin`) — candidate existence
  check, parse → transform → persist. No new dependency (parse is pure).
- **HTTP** (routes) — status-code contract only.

## 5. Changes to `app/profile_sources/`

### 5.1 `schema.py` — grow the contracts (generalize `activity`)

- `ProfileSourceType(StrEnum)`: add `LINKEDIN_EXPORT = "linkedin_export"`.
- `SourceSkillSignal` — **reused unchanged**. For LinkedIn, `weight` carries the
  **corroboration count** (how many positions/headline mention the skill) rather
  than bytes; `weight`'s docstring is generalized to "aggregated evidence volume
  (source-defined)". `canonical`/`category` come from `normalize_skill` exactly as
  GitHub; unknown skills are kept with `canonical=None`.
- **`method` literal extended** to `Literal["api", "export", "unavailable"]`. A
  successful LinkedIn parse reports `method="export"` (it is a parsed upload, not
  an API call — honest transport labelling); GitHub keeps `"api"`. Both existing
  values remain, so stored GitHub rows validate unchanged.
- **New `LinkedInActivity(BaseModel)`** (evidence context, not a score):
  - `positions_count: int`, `current_positions: int` (rows with empty "Finished
    On"), `employers: list[str]` (canonical, deduped, order-stable),
    `education_count: int`, `institutions: list[str]` (canonical, deduped),
    `certifications_count: int`, `languages: list[str]`,
    `headline: Optional[str]`, `industry: Optional[str]`,
    `skills_listed: int` (raw count from `Skills.csv`).
  - **No** raw name, summary, email/phone/address, geo, or connections.
- **`ProfileSourceSignal.activity` becomes a discriminated union.**
  - Add `kind: Literal["github"] = "github"` to `GitHubActivity` and
    `kind: Literal["linkedin_export"] = "linkedin_export"` to `LinkedInActivity`.
  - `activity: GitHubActivity | LinkedInActivity = Field(discriminator="kind",
    default_factory=GitHubActivity)` — the default keeps existing construction
    sites that omit `activity` working (both `to_signal` paths set it explicitly).
  - **Back-compat for existing GitHub rows** (stored before `kind` existed): a
    `@model_validator(mode="before")` on `ProfileSourceSignal` stamps
    `activity["kind"]` from the already-present top-level `source_type` **only when
    `activity` is a dict lacking the discriminator** (a model instance already
    carries its default `kind`; a dict from the DB may not). Existing rows have
    `source_type="github"` ⇒ backfill `kind="github"` ⇒ they validate unchanged.
    **No migration, no data rewrite.**
    A dedicated test validates a pre-S6.2 GitHub JSON blob (no `kind`) round-trips.

### 5.2 `linkedin.py` — pure parse + pure transform (NEW file)

**Raw DTO** `LinkedInExportRaw` (pydantic/dataclass):
`available: bool`, `skills: list[str]`, `positions: list[LinkedInPositionRaw]`
(`company`, `title`, `description`, `started_on`, `finished_on`),
`education: list[LinkedInEducationRaw]` (`school`, `degree`),
`certifications: list[str]`, `languages: list[str]`,
`headline: Optional[str]`, `industry: Optional[str]`, `warnings: list[str]`.

**`parse_linkedin_export(data: bytes, settings) -> LinkedInExportRaw`** — pure:

- Open `io.BytesIO(data)` with `zipfile.ZipFile`. Not a zip / empty ⇒
  `available=False` + a warning.
- Locate member CSVs **case-insensitively by filename stem** (`skills`,
  `positions`, `education`, `profile`, `certifications`, `languages`), tolerating
  the leading directory LinkedIn sometimes nests and locale spacing. Missing files
  are fine (each is optional).
- Parse via `csv.DictReader`; tolerate column-name variants (e.g. `Company Name`
  vs `Company`, `School Name` vs `School`). Bound rows at `ps_linkedin_max_rows`
  per file.
- If **no** recognizable LinkedIn CSV is present (e.g. a random zip) ⇒
  `available=False` + a warning ("no LinkedIn export CSVs found").
- Never raises: any per-file parse error becomes a warning and that file is
  skipped.

**`to_signal(raw, settings, *, fetched_at) -> ProfileSourceSignal`** — pure:

- `raw.available is False` ⇒ `method="unavailable"`, `skills=[]`, empty
  `LinkedInActivity`, warnings copied. (Mirrors GitHub's unavailable path.)
- **Skills:** for each `Skills.csv` name, `normalize_skill(name)` (S1.4). Compute a
  **corroboration count** = number of positions whose title+description, plus the
  headline, contain the skill token (case-insensitive whole-word). Confidence:
  - base `ps_linkedin_skill_base_confidence` (0.4) when corroboration == 0,
  - `ps_linkedin_skill_corroborated_confidence` (0.6) when corroboration ≥ 1.
  - `weight = corroboration` (int, ≥0). Sorted by `(weight desc, name)` for stable
    output. Duplicate skill names collapse (max corroboration wins).
- **Activity:** counts + canonical employers (`canonicalize_employer`, deduped,
  drop `None`) + canonical institutions (`canonicalize_institution(...).canonical`,
  deduped) + certifications_count + languages + headline + industry +
  skills_listed. `current_positions` = positions with empty `finished_on`.
- **Available raw ⇒ `method="export"`.** Corroboration matching is token-based
  (a skill matches a position/headline only as a standalone token — so short
  names like `"go"`/`"c"` don't false-match substrings; multi-word skills simply
  don't corroborate, an accepted limitation).
- **Pure — no network, no clock beyond the injected `fetched_at`.**

### 5.3 `service.py` — add `ingest_linkedin`

- **No constructor change** (parse is pure; the GitHub client is untouched and
  simply unused by this path).
- `async ingest_linkedin(candidate_id: str, data: bytes) -> ProfileSourceSignal`:
  1. `candidates.get_candidate(id) is None` ⇒ raise `LookupError` (→404).
  2. `raw = parse_linkedin_export(data, settings)`.
  3. `signal = to_signal(raw, settings, fetched_at=now_utc())`
     (`identifier` = a stable, non-PII label — see below).
  4. `store.save_signal(candidate_id, signal)`; return `signal`.
- **`identifier` for LinkedIn:** GitHub used the public handle. A LinkedIn export
  has no stable public handle we want to persist, and the vanity URL is PII-ish.
  Use a fixed non-PII label **`"linkedin_export"`** (the source *is* the upload;
  history is disambiguated by `fetched_at`/row id). Documented so it's not read as
  an accident.
- `list_sources` is unchanged (already generic over `source_type`).

### 5.4 `store.py` — unchanged

Append-only insert + newest-first reads already generic over `source_type`. New
rows carry `source_type="linkedin_export"`. No new method, **no migration** (the
`0010_profile_sources` table already fits; `signal` is JSON).

## 6. API — existing `router` (candidate-management plane)

Candidate-facing auth is **S6.4**; until then these live on the existing
admin/candidate router (same as S6.1's GitHub endpoints).

- `POST /candidates/{candidate_id}/sources/linkedin`
  - Body: `{"export_b64": "<base64 of the .zip>"}` — **required** (base64 in JSON,
    mirroring the existing `resume_pdf_b64` transport; no multipart machinery).
  - Decode + size checks first:
    - `export_b64` length > `max_linkedin_b64_chars` ⇒ **422**.
    - base64 decode failure ⇒ **422** (`invalid_base64`).
  - **200** `ProfileSourceSignal`. Includes the degraded case: a valid file with no
    recognizable LinkedIn CSVs (wrong zip) ⇒ **200** `method="unavailable"` +
    warnings — a "no signal" outcome is advisory, not a client error (the S6.1
    ethos: only *malformed input* is a 4xx).
  - **404** unknown candidate.
- `GET /candidates/{candidate_id}/sources?source_type=linkedin_export` — already
  exists (generic); returns stored signals newest-first. **404** unknown candidate.
- **No new service in the container** — `Services.profile_sources` already wired
  (S6.1); we only add a method + a route.

**Error-semantics rationale (explicit):** *malformed transport* (bad base64,
oversize) is a client error → 4xx; a *well-formed file that yields no signal* is a
valid advisory outcome → 200 `unavailable`. This matches S6.1, where a missing/
unreachable GitHub returns 200 `unavailable` rather than an error.

## 7. Consent / DPDP posture

- **No new `ConsentPurpose`.** The candidate uploads their own export — identical
  posture to PI-1 resume ingest (first-party, ingest-side). Documented explicitly.
- **Store the derived signal only** — S1.4-mapped skills + de-identified activity
  aggregates (counts + *canonical* employers/institutions + headline/industry +
  languages). We do **not** persist raw contact PII (email/phone/address), the
  profile summary free-text, connections, or the vanity URL.
- **Erasure:** `profile_sources.candidate_id` CASCADEs with the candidate
  (proven for GitHub in S6.1); a LinkedIn-row erasure test re-affirms it.

## 8. Config (`config.yaml` + `Settings`)

| knob | default | purpose |
|---|---|---|
| `max_linkedin_b64_chars` | 8_000_000 | reject oversized uploads (≈6 MB zip) before decode → 422 |
| `ps_linkedin_skill_base_confidence` | 0.4 | confidence for an uncorroborated listed skill |
| `ps_linkedin_skill_corroborated_confidence` | 0.6 | confidence when a position/headline mentions the skill |
| `ps_linkedin_max_rows` | 5_000 | per-CSV row cap (bounds a pathological export) |

(`ps_github_*` from S6.1 are untouched.)

## 9. Testing & smoke

**TDD, fully offline (no network anywhere in this adapter):**

- **Pure parse** (`parse_linkedin_export`): a well-formed in-test zip (built from
  CSV strings) → skills/positions/education/profile populated; column-name
  variants tolerated; missing optional files OK; nested-directory member names
  resolved; non-zip bytes → `available=False`; a zip with no LinkedIn CSVs →
  `available=False` + warning; row cap enforced.
- **Pure transform** (`to_signal`): canonical skill mapping (mapped + unmapped
  passthrough); corroboration bump (skill in a position title/headline →
  higher confidence + weight); duplicate-skill collapse; activity aggregates
  (counts, canonical employers/institutions dedup, current_positions, headline/
  industry); unavailable-raw → `method="unavailable"`; confidence bounded in
  {base, corroborated} and never 1.0.
- **Schema back-compat:** a pre-S6.2 GitHub `ProfileSourceSignal` JSON blob (no
  `activity.kind`) validates via the `source_type`-derived discriminator; a
  LinkedIn signal round-trips through `model_dump(mode="json")` → `model_validate`.
- **Store:** save a LinkedIn signal + `signals_for_candidate(..., LINKEDIN_EXPORT)`
  filter + newest-first ordering across mixed source types; **CASCADE** erasure via
  `delete_candidate` sweeps LinkedIn rows.
- **Service:** unknown candidate → `LookupError`; available export persists a
  signal; unrecognizable zip persists a `method="unavailable"` signal.
- **API:** 200 (real-ish zip), 200 (wrong-zip → unavailable), 404 (unknown
  candidate), 422 (bad base64), 422 (oversize); `GET` list filter by
  `linkedin_export`.
- ~28 new tests; `pytest -q` green before merge (697 → ~725).

**Smoke `scripts/smoke_s62.py`** (uvicorn + real HTTP): build a realistic LinkedIn
export zip in-script (Skills/Positions/Education/Profile CSVs) → create a candidate
→ `POST .../sources/linkedin` with the base64 zip → assert 200, `method="export"`,
canonical skills present, corroborated skill has the higher confidence, activity
employers canonicalized → `GET .../sources?source_type=linkedin_export` shows the
row → bad-base64 → 422 → DPDP `DELETE` candidate → `GET .../sources` 404. Key-less
(no LLM, no network in this path).

## 10. Explicit non-goals for S6.2 (documented follow-ups)

- **Normalization curation loop** — deferred to **S6.3** (surface taxonomy drift —
  unknown skills/employers/institutions from all adapters — for human review;
  deterministic files, no auto-learning).
- **Corroboration** (resume-claimed vs source-observed skills) — still deferred
  (an S6.1 follow-up; now has two sources feeding it).
- **Feature-store consumption** of the signal — later PI-4 addition.
- **Multilingual / Hinglish intake** — DEFERRED (user decision 2026-07-26,
  English-first for the IT vertical).
- **Candidate auth** — S6.4; endpoints stay on the admin/candidate router for now.
- **LinkedIn live API / OAuth scraping** — out; first-party export upload only
  (DPDP-clean, no third-party scraping).

## 11. Deliverables checklist

- [ ] `app/profile_sources/schema.py` — `LINKEDIN_EXPORT`, `LinkedInActivity`,
      `activity` discriminated union + `source_type`-derived back-compat validator
- [ ] `app/profile_sources/linkedin.py` — `LinkedInExportRaw` +
      `parse_linkedin_export` + `to_signal`
- [ ] `ProfileSourceService.ingest_linkedin`
- [ ] `POST /candidates/{id}/sources/linkedin` route (+ base64/size guards)
- [ ] `max_linkedin_b64_chars` / `ps_linkedin_*` config knobs
- [ ] `PROFILE_SOURCES.md` — LinkedIn section
- [ ] `scripts/smoke_s62.py`
- [ ] ROADMAP updated (PI-6 reshape: S6.2 LinkedIn · S6.3 curation loop · S6.4
      portal; S6.2 status)
