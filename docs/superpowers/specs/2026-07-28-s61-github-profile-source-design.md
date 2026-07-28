# S6.1 — GitHub-as-signal (profile-source ingestion) — Design

**Date:** 2026-07-28
**PI / Sprint:** PI-6 (Candidate Side & Intake) · S6.1
**Status:** Approved design — ready for implementation plan.
**Read first:** `docs/ROADMAP.md`, then
`docs/superpowers/specs/2026-07-26-veritas-vision-gap-analysis.md` §5.A / §6
(PI-6.1 landing zone), then this document.

---

## 1. Why this sprint

The gap analysis (§5.A) names two intake gaps that keep Veritas resume-only while
Mercor-class platforms ingest *profiles*:

- "GitHub used only as probe evidence, not as a structured skill signal."
- "Only resume text/PDF intake; no LinkedIn/GitHub *profile* ingestion as a
  first-class source."

Both land in **PI-6.1**. The India angle: OSS activity is a strong, verifiable
skill signal for **tier-2/3 candidates who lack brand-name employers** — exactly
the underserved segment the platform wants to surface.

Today `app/services/github.py` (`GitHubClient.gather_repo_evidence`) fetches a
*single repo's* evidence lines for the depth-eval provenance node. It does not
look at a candidate's overall GitHub presence, produces free-text evidence rather
than structured skills, and stores nothing. S6.1 closes that: a candidate's
GitHub handle becomes a **structured, normalized, provenanced, stored** skill +
activity signal — a peer of the resume extraction, advisory only.

## 2. Scope decisions (taken with user, 2026-07-28)

1. **GitHub-as-signal only for S6.1** (not GitHub + LinkedIn together). S6.1
   builds the reusable `profile_sources` *spine* (contracts + table + store + API
   + normalization) with GitHub as the first adapter. This keeps one live-API
   concern per sprint and lands the higher-India-value source first.
2. **Ingest + store only; corroboration deferred.** S6.1 stores clean structured
   signals. "Resume-claimed vs source-observed" skill corroboration (both
   directions) is a documented follow-up (natural S6.2 / fabrication-layer
   addition once the signal exists), *not* in this sprint.

### PI-6 reshape (record in ROADMAP)

The gap analysis bundled GitHub + LinkedIn into PI-6.1. With decision (1) the PI
re-shapes to:

```
PI-6  CANDIDATE SIDE & INTAKE
 ├ S6.1  GitHub-as-signal  (profile_sources spine + github adapter)   ← THIS
 ├ S6.2  LinkedIn export parsing (second adapter) + normalization curation loop
 └ S6.3  Candidate auth + DPDP portal (my-data / who-accessed / revoke /
         retention TTLs; first-party consent capture)
```

`profile_sources` is designed as a source-agnostic spine so S6.2's
`linkedin_export` adapter reuses the table, store, and API shape unchanged.

## 3. Non-negotiables inherited (do not relitigate)

- **Advisory only.** The signal is *evidence*, never a score, never a gate, never
  auto-anything. Depth-eval scoring and verdicts are untouched.
- **Deterministic, no LLM.** The raw→signal transform is pure Python
  (language aggregation + taxonomy mapping). No API key is ever required for the
  transform; the only network is the GitHub fetch, which degrades gracefully.
- **DPDP: first-party only.** We fetch *public* data from a handle the candidate
  themselves supplied (or already put in their resume's GitHub link). We never
  scrape third-party profiles. Every new candidate-linked row CASCADEs on erasure.
- **TDD offline; smoke per sprint; Postgres-shaped SQLite.**

## 4. Architecture

```
                 candidate handle (explicit, or from profile github link)
                                   │
        POST /candidates/{id}/sources/github        GET /candidates/{id}/sources
                                   │                             │
                                   ▼                             ▼
                         ProfileSourceService  ───────►  ProfileSourceStore
                          (app/profile_sources)          (candidates DB, CASCADE)
                                   │  ▲
                    gather_user_signal │  │ to_signal(raw, settings)  [PURE]
                                   ▼  │
                          GitHubService (live)      normalize_skill()  [S1.4 reuse]
                    (app/services/github.py, extended)
```

**Seams (each independently testable):**

- **Live fetch** (`GitHubClient.gather_user_signal`) — the only network. Injected
  as a `GitHubService` Protocol; tests use a `FakeGitHubService`.
- **Pure transform** (`profile_sources/github.py::to_signal`) — raw DTO → typed
  `ProfileSourceSignal`. No I/O, exhaustively unit-tested offline.
- **Persistence** (`ProfileSourceStore`) — append-only rows on the candidates DB.
- **Orchestration** (`ProfileSourceService`) — handle resolution, candidate
  existence check, fetch → transform → persist.
- **HTTP** (routes) — status-code contract only.

## 5. New package: `app/profile_sources/`

### 5.1 `schema.py` — contracts

- `ProfileSourceType(StrEnum)`: `GITHUB = "github"`. `LINKEDIN_EXPORT` is
  **reserved for S6.2** — not added until that sprint (YAGNI; the enum grows then).
- `SourceSkillSignal(BaseModel)`:
  - `name: str` — the raw source term (e.g. GitHub language `"Python"`).
  - `canonical: Optional[str]` — S1.4 taxonomy id (`"python"`) or `None` when the
    language is not in the taxonomy (kept, not dropped — a weaker signal).
  - `category: Optional[str]` — taxonomy category (`"language"`) or `None`.
  - `weight: int` — aggregated evidence volume (summed language bytes across
    repos). Deterministic, source-defined.
  - `confidence: float` (0..1) — grows with evidence volume; see §5.2.
- `GitHubActivity(BaseModel)`: `public_repos: int`, `followers: int`,
  `total_stars: int`, `top_languages: dict[str, int]` (name→bytes),
  `most_recent_push: Optional[str]` (ISO date), `account_created: Optional[str]`,
  `sampled_repos: int` (how many repos actually contributed to the signal after
  limits/fork filtering).
- `ProfileSourceSignal(BaseModel)`:
  - `id: str` (default-factory `psrc_...`), `source_type: ProfileSourceType`,
    `identifier: str` (the handle), `skills: list[SourceSkillSignal]`,
    `activity: GitHubActivity`, `method: Literal["api", "unavailable"]`,
    `fetched_at: datetime`, `warnings: list[str]`, `advisory: bool = True`.
  - `method="unavailable"` ⇒ `skills=[]`, `activity` zero-valued, `warnings`
    explain why (404 handle / rate-limited / network). Still a valid, stored,
    advisory outcome.

### 5.2 `github.py` — pure transform

`to_signal(raw: GitHubUserRaw, settings) -> ProfileSourceSignal`

- **Fork filter:** drop repos where `fork is True` unless
  `ps_github_include_forks` (default `False`) — forks aren't authored signal.
- **Language aggregation:** sum per-language bytes across the surviving repos'
  `languages` maps into `top_languages`. Repos beyond
  `ps_github_language_repos` (that had no per-repo `/languages` fetched) still
  contribute their primary `language` field with a nominal weight, so a large
  account isn't silently truncated.
- **Skill mapping:** for each aggregated language, `normalize_skill(name)`
  (S1.4). Mapped ⇒ `canonical`/`category` filled; unmapped ⇒ both `None`, raw
  `name` kept. Sorted by `weight` desc for stable output.
- **Confidence:** a saturating function of evidence volume, e.g.
  `min(0.9, 0.30 + 0.10·log2(1 + weight_share·sampled_repos))` — mirrors the
  fabrication/comp "coverage confidence never asserts" style. Exact form nailed
  down in the plan; the property that matters: bounded, monotone in evidence,
  never 1.0.
- **`total_stars`, `most_recent_push`:** reduced from the raw repos.
- Unavailable raw (`raw.available is False`) ⇒ the `method="unavailable"`
  signal with warnings copied through. **Pure — no network, no clock beyond an
  injected/`fetched_at` timestamp.**

### 5.3 `service.py` — `ProfileSourceService`

- Constructed with a `GitHubService` + `ProfileSourceStore` +
  `CandidateStore` (for handle derivation + existence check) + `Settings`.
- `async ingest_github(candidate_id: str, handle: Optional[str] = None) ->
  ProfileSourceSignal`:
  1. `candidate = candidates.get_candidate(id)`; `None` ⇒ raise `LookupError`
     (→404 at the API).
  2. **Handle resolution:** explicit `handle` wins; else derive from the
     candidate's latest profile `LinkType.GITHUB` link (parse the login out of
     the URL, reusing `parse_github_url`); else raise `ValueError` (→400).
  3. `raw = await github.gather_user_signal(login)`.
  4. `signal = to_signal(raw, settings)` with `identifier=login`.
  5. `store.save_signal(candidate_id, signal)`; return `signal`.
- `list_sources(candidate_id, source_type=None) -> list[ProfileSourceSignal]` —
  newest first; raises `LookupError` for an unknown candidate (→404).
- Owns no LLM. `build_profile_source_service(settings)` builds store + a
  `GitHubClient`; the wired `Services.profile_sources` reuses `Services.github`.

### 5.4 `store.py` — `ProfileSourceStore`

- On the **candidates DB** session factory (`build_profile_source_store(settings)`
  uses `settings.candidates_db_url`, mirroring `build_candidate_store`).
- `save_signal(candidate_id, signal) -> str` — append-only insert; returns row id.
- `signals_for_candidate(candidate_id, source_type=None) -> list[...]` — newest
  first (by `created_at`), validated back to `ProfileSourceSignal`.
- `latest_for_source(candidate_id, source_type) -> Optional[...]`.
- No delete method needed: DPDP erasure flows through the existing
  `CandidateStore.delete_candidate` CASCADE (proven by test).

## 6. Live fetch — extend `app/services/github.py`

- `GitHubUserRaw` DTO (dataclass/pydantic): `login`, `available: bool`,
  `public_repos`, `followers`, `account_created`, `repos: list[GitHubRepoRaw]`
  (`name`, `language`, `languages: dict[str,int]`, `stargazers_count`,
  `pushed_at`, `fork`), `warnings: list[str]`.
- Extend the `GitHubService` Protocol with
  `async gather_user_signal(login: str) -> GitHubUserRaw`.
- `GitHubClient.gather_user_signal`:
  - `GET /users/{login}` → 404/network/≥400 ⇒ `available=False` + a warning
    (never raises), same posture as `gather_repo_evidence`.
  - `GET /users/{login}/repos?per_page=100&sort=pushed` up to
    `ps_github_repo_limit` repos.
  - For the top `ps_github_language_repos` by recency, `GET /repos/{login}/{name}/
    languages` to fill byte-accurate `languages`; the rest keep their primary
    `language` field only.
  - Any sub-fetch error is a warning, not a crash (bounded, best-effort).
- Unauthenticated works (public API, 60 req/hr/IP — ample for one candidate);
  `github_token` raises the limit when present. No new secret.

## 7. Persistence — migration `0010_profile_sources`

Table `profile_sources` on the shared `Base` (candidates DB):

| column | type | notes |
|---|---|---|
| `id` | String(36) PK | uuid |
| `candidate_id` | FK→`candidates.id` **ON DELETE CASCADE**, indexed | DPDP sweep |
| `source_type` | String(32), indexed | `"github"` |
| `identifier` | Text | the public handle |
| `signal` | JSON | the full `ProfileSourceSignal` payload |
| `method` | String(16) | `"api"` \| `"unavailable"` |
| `fetched_at` | DateTime(tz) | when the fetch ran |
| `created_at` | DateTime(tz) | row write time |

- **Append-only** (each fetch = a row) — keeps history for point-in-time feature
  materialization later; no unique constraint on `identifier` (a candidate may
  change handle). Mirrors `resumes`/`extractions` versioning intent.
- **Drift/index/FK-ondelete/nullability guards extended** to the new table (the
  every-migration pattern; the metadata-wide drift guard fires the moment the ORM
  model is imported, so 0010 lands with the model).

## 8. API — existing `router` (candidate-management plane)

Candidate-facing auth is **S6.3**; until then these live on the existing
admin/candidate router. The spec notes that S6.3 will move them under
candidate auth.

- `POST /candidates/{candidate_id}/sources/github`
  - Body: `{"handle": "octocat"}` — **optional**; omitted ⇒ derive from the
    candidate's GitHub profile link.
  - **200** `ProfileSourceSignal` (JSON). Includes the degraded case:
    `method="unavailable"` + warnings when the handle 404s / is rate-limited /
    network fails — a missing GitHub is a valid advisory outcome, **not** a
    client error.
  - **404** unknown candidate. **400** no resolvable handle (none supplied and no
    profile link) or a malformed handle.
- `GET /candidates/{candidate_id}/sources?source_type=github`
  - **200** list of stored `ProfileSourceSignal` (newest first). **404** unknown
    candidate.
- `Services.profile_sources: ProfileSourceService` added to the container, wired
  cycle-safe (`TYPE_CHECKING` + function-local `build_*`, the S4.3/S5.1 pattern),
  reusing `Services.github`.

## 9. Consent / DPDP posture

- **No new `ConsentPurpose`.** The handle is candidate-supplied and the data is
  public — identical posture to PI-1 resume ingest (first-party, ingest-side, not
  a cross-org read). Documented explicitly so a future audit sees the reasoning.
- **Store the derived signal only** — canonical skills + activity aggregates + the
  public handle. We do **not** persist raw repo dumps or any third-party PII.
- **Erasure:** `profile_sources` CASCADEs with the candidate; a test proves
  `delete_candidate` sweeps it. No new delete path needed.

## 10. Config (`config.yaml` + `Settings`)

| knob | default | purpose |
|---|---|---|
| `ps_github_repo_limit` | 100 | max repos pulled for a user |
| `ps_github_language_repos` | 30 | top-N recent repos that get a byte-accurate `/languages` fetch (bounds rate-limit exposure) |
| `ps_github_include_forks` | false | forks excluded from the signal by default |

`github_api_base` / `github_token` already exist in `Settings`.

## 11. Testing & smoke

**TDD, fully offline:**

- Pure transform (`to_signal`): language aggregation across repos, canonical
  mapping (mapped + unmapped-language passthrough), fork exclusion,
  confidence monotonicity + bound, `total_stars`/`most_recent_push` reduction,
  unavailable-raw → `method="unavailable"`.
- Store: save + `signals_for_candidate` ordering + `latest_for_source`;
  **CASCADE** erasure via `delete_candidate`.
- Service: `FakeGitHubService` (available + unavailable), explicit-handle vs
  derived-from-link vs no-handle(→ValueError), unknown-candidate(→LookupError).
- API: 200 (available), 200 (degraded/unavailable), 400 (no handle), 404
  (unknown candidate); `GET` list ordering + 404.
- Drift/index/FK/nullability guards over `0010`.
- ~30 new tests; `pytest -q` green before merge.

**Smoke `scripts/smoke_s61.py`** (uvicorn + real HTTP): create a candidate →
`POST .../sources/github` for a stable public handle (`octocat`) →
`GET .../sources` shows canonical skills → DPDP `DELETE` candidate →
`GET .../sources` 404. **Robust to rate-limit/offline:** asserts the endpoint
returns 200 and `method ∈ {"api","unavailable"}` and the DPDP path works
regardless of whether the live fetch succeeded.

## 12. Explicit non-goals for S6.1 (documented follow-ups)

- **Corroboration** (resume-claimed vs source-observed skills, both directions) —
  deferred (decision 2).
- **Feature-store consumption** of the signal — a small PI-4 feature-definition
  addition later; S6.1 lands the data + API only.
- **LinkedIn export** parsing — S6.2 (second adapter on this spine).
- **Flywheel wiring** — the signal is not part of the eval graph; not recorded to
  the flywheel in this sprint.
- **Candidate auth** — S6.3; endpoints stay on the admin/candidate router for now.

## 13. Deliverables checklist

- [ ] `app/profile_sources/{schema,github,service,store}.py`
- [ ] `GitHubClient.gather_user_signal` + `GitHubUserRaw`/`GitHubRepoRaw` +
      Protocol extension
- [ ] `profile_sources` ORM model + migration `0010_profile_sources` + guard
      extensions
- [ ] `Services.profile_sources` wiring (cycle-safe)
- [ ] `POST /candidates/{id}/sources/github` + `GET /candidates/{id}/sources`
- [ ] `ps_github_*` config knobs
- [ ] `PROFILE_SOURCES.md` (peer of `MATCHING.md`/`COMP.md`/`DASHBOARD.md`)
- [ ] `scripts/smoke_s61.py`
- [ ] ROADMAP updated (PI-6 reshape + S6.1 status)
