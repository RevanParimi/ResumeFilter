# S6.3 — Normalization Curation Loop — Design

**Date:** 2026-07-30
**PI / Sprint:** PI-6 (Candidate Side & Intake) · S6.3
**Status:** Approved design — ready for implementation plan.
**Read first:** `docs/ROADMAP.md`, then
`docs/superpowers/specs/2026-07-26-veritas-vision-gap-analysis.md` §5.A / §6
(the "normalization tables are static" gap → PI-6.2 curation-loop landing zone),
then `PROFILE_SOURCES.md` (how the GitHub + LinkedIn adapters surface unmapped
terms), then this document.

---

## 1. Why this sprint

The vision-gap analysis (§5.A) names one intake weakness that S6.1/S6.2 left open:

> **"Normalization tables are static."** Taxonomies drift (new skills, new
> unicorns); Indian startup employer churn is fast. Landing zone: **PI-6.2 —
> curation loop, still deterministic files — no auto-learning without review.**

Today the S1.4 skill taxonomy (`app/candidates/normalize/skills.py`) is a static
Python dict matched exactly on `norm_key`. When a term isn't in the table it is
**deliberately kept with `canonical=None`** (the system never guesses). The two
profile-source adapters both do this: GitHub keeps unknown languages, LinkedIn
keeps unknown self-reported skills, and resume extraction keeps unknown
`SkillClaim`s the same way. So `canonical=None` is already a precise, existing
**"unmapped" marker** flowing through the system — but nothing collects those
terms, and there is no way to teach the taxonomy a new mapping short of a code
change + redeploy.

S6.3 closes that with a **human-in-the-loop taxonomy repair loop**:

```
ingest surfaces unmapped skill term  →  it lands in a review queue  →
a reviewer maps / creates / ignores it  →  a deterministic overlay makes
normalize_skill resolve it everywhere, from the next normalization on.
```

No LLM. No auto-learning. A human is the only thing that changes the taxonomy.

## 2. Scope decisions (taken with user, 2026-07-30)

Three load-bearing calls, all taken on recommendation:

1. **Skills only.** Curate only skill terms — the ones carrying the explicit
   `canonical=None` marker. Employers/institutions go through
   `canonicalize_employer`/`canonicalize_institution`, which return a *best-effort
   string* (no clean unmapped marker), so they'd need extra machinery; degrees and
   locations rarely surface novel terms. Those become clean follow-ups (§9).
2. **System-wide overlay on `normalize_skill`.** A reviewer's decision loads into
   an in-memory overlay merged with the static taxonomy index; `normalize_skill`
   stays a pure dict lookup (no per-call I/O) but now resolves curated terms too.
   Every consumer benefits — profile sources, resume extraction, matching, comp —
   not just the adapters. (Alternative "apply inside the adapters only" was
   rejected: the taxonomy itself would never improve and there'd be two sources of
   truth. "Live DB-backed `normalize_skill`" was rejected: it turns a pure
   hot-path function into per-call I/O across the whole codebase.)
3. **Capture from profile sources only.** The queue is fed by unmapped terms from
   the GitHub + LinkedIn adapters — exactly the ROADMAP scope for S6.3.
   Resume-extraction capture (the same `canonical=None` marker on `SkillClaim`) is
   an easy follow-up (§9), deliberately out to keep the PI-1 ingest path untouched
   this sprint.

Two smaller calls (confirmed with user):

- **(a) Static taxonomy always wins over the overlay** — curation can only *fill
  gaps*, never silently override the vetted `_TAXONOMY`.
- **(b) No decision-history/audit table** — a re-resolve overwrites the prior
  resolution. History is a follow-up (§9).

## 3. Non-negotiables inherited (do not relitigate)

- **Advisory / no auto-anything.** A curation *decision* is a real deterministic
  data change, but the loop's guardrail is that **only a human review produces
  it** — no ML, no heuristic auto-mapping. Depth-eval scoring/verdicts untouched.
- **Deterministic, no LLM.** Capture, queue, resolve, and overlay application are
  all pure Python + a DB table. No API key ever required. (LLM-suggested mappings
  are a documented non-goal, §9.)
- **TDD offline; smoke per sprint; Postgres-shaped SQLite; Alembic migration with
  drift/index/nullability guards extended.**
- **Config in `config.yaml` (`cur_*`); no secrets.**

## 4. DPDP posture — the important one

The review queue is **candidate-agnostic**. Each row is keyed by `norm_key` and
holds only aggregate metadata: a display form, occurrence count, the set of
`source_types` the term has appeared through, first/last-seen timestamps, and
(once resolved) the decision. **No `candidate_id` is ever stored on a queue row.**

Consequences:

- It is **taxonomy-gap metadata, not candidate data** → **no new `ConsentPurpose`,
  no consent object, no CASCADE FK**. This is the deliberate, correct posture: a
  skill token like `cobol` or `verilog` is not personal data.
- Because there is no candidate link, `DELETE /candidates/{id}` does **not** remove
  queue terms — and that is by design, asserted by the smoke run. (Erasing a
  candidate must not erase the fact that "verilog" is a known taxonomy gap.)
- **Junk guard:** a self-reported LinkedIn "skill" is free text the candidate
  typed, so in principle it could contain something odd. `cur_max_term_len` (drop
  overlong terms) and `cur_min_term_len` (skip single-char noise) keep the queue
  clean before anything is persisted. This is data hygiene, not PII handling — but
  it also means we never persist a paragraph someone pasted into a skill field.

## 5. Architecture

### 5.1 New package `app/curation/`

Mirrors the shape of `app/profile_sources/` (schema · store · service), pure where
it can be, I/O isolated to the store.

**`schema.py`** — Pydantic contracts + StrEnums (no scoring, bounds are data
hygiene only):

- `CurationStatus(StrEnum)`: `PENDING` · `RESOLVED` · `IGNORED`.
- `CurationAction(StrEnum)`: `MAP` (alias → an existing canonical) · `CREATE` (a
  new canonical id + category) · `IGNORE` (confirmed not-a-skill).
- `UnmappedTerm(BaseModel)`:
  - `norm_key: str` — the stable identity (`norm_key(raw)`); also the API handle.
  - `display_name: str` — a human-readable raw form (first seen; refreshed to the
    most recent raw form on re-touch so reviewers see a natural spelling).
  - `source_types: list[str]` — union of `github` / `linkedin_export`.
  - `occurrences: int` (`ge=1`), `first_seen: datetime`, `last_seen: datetime`.
  - `status: CurationStatus`.
  - Resolution fields (all `Optional`, set only when resolved): `action`,
    `canonical`, `category`, `note`, `decided_by`, `decided_at`.

**`store.py`** — `CurationStore` on the candidates DB (the same DB the profile
sources + candidates live on):

- `record_unmapped(name: str, *, source_type: str, now: datetime) -> None`
  — upsert by `norm_key`: if new, insert `PENDING` with `occurrences=1`; if it
  exists **and is still `PENDING`**, bump `occurrences`, refresh `last_seen` +
  `display_name`, union `source_type` into `source_types`. A term that is already
  `RESOLVED`/`IGNORED` is **not** re-queued or re-counted (its resolution is final
  until re-resolved). Terms failing the length guards are skipped by the *service*
  before this is called (store stays dumb + total).
- `list_terms(status: Optional[CurationStatus], limit: int) -> list[UnmappedTerm]`
  — ordered by `occurrences` desc, then `last_seen` desc; `status=None` returns all.
- `get_term(norm_key) -> Optional[UnmappedTerm]`.
- `resolve(norm_key, *, action, canonical, category, note, decided_by, now)
  -> UnmappedTerm` — persist the resolution onto the row (status →
  `RESOLVED` for MAP/CREATE, `IGNORED` for IGNORE); raise `LookupError` if the
  term is unknown. Overwrites any prior resolution (decision (b)).
- `load_overlay() -> dict[str, SkillMatch]` — every `RESOLVED` row with a
  `canonical`+`category` becomes `norm_key -> SkillMatch(canonical, category)`.
  `IGNORED` and `PENDING` rows contribute nothing.
- `build_curation_store(settings) -> CurationStore` (same builder pattern as
  `build_profile_source_store`).

**`service.py`** — `CurationService`:

- `record_unmapped(name, *, source_type)` — applies `cur_min_term_len` /
  `cur_max_term_len` guards on `norm_key(name)` (and skips empty keys), then
  delegates to the store. This is what ingestion calls.
- `list_unmapped(status, limit)` — clamps `limit` to `cur_queue_default_limit`.
- `resolve(norm_key, action, *, canonical, category, note, decided_by)` —
  **validation** (raises `ValueError` → 422 at the API):
  - `MAP`: `canonical` required; it must already be a known canonical — either in
    the static `_TAXONOMY` canonical-id set **or** a `CREATE`d canonical already in
    the overlay. `category` is **always derived** from that known canonical; a
    `category` in the request body is ignored (not an error — an ops reviewer may
    include it for context).
  - `CREATE`: `canonical` required, must be a clean snake_case id
    (`^[a-z][a-z0-9_]*$`) not already a static canonical; `category` required and
    must be in `SKILL_CATEGORIES`.
  - `IGNORE`: `canonical`/`category` must **not** be supplied (422 if sent) — an
    ignore is a confirmed non-skill, so a mapping target is contradictory.
  - Unknown `norm_key` → `LookupError` → 404.
  On success: persist via the store, then **`refresh_overlay()`** so the fix is
  live in-process immediately.
- `refresh_overlay()` — `set_curated_overlay(self._store.load_overlay())`.
- `build_curation_service(settings, *, candidates=None) -> CurationService`.

To validate `MAP`/`CREATE`, the service needs the set of static canonical ids and
a way to look up a canonical's category. Add two tiny read-only helpers to
`app/candidates/normalize/skills.py` (§5.2) rather than reaching into `_TAXONOMY`
from another package.

### 5.2 Overlay hook — `app/candidates/normalize/skills.py`

- Module-level `_CURATED_OVERLAY: dict[str, SkillMatch] = {}`.
- `normalize_skill(name)` becomes:
  ```python
  key = norm_key(name or "")
  if not key:
      return None
  return _INDEX.get(key) or _CURATED_OVERLAY.get(key)
  ```
  Static index wins; the overlay only fills gaps (decision (a)). No per-call I/O —
  it is still a pure dict lookup; the DB read happens in the loader.
- `set_curated_overlay(mapping: dict[str, SkillMatch]) -> None` and
  `clear_curated_overlay() -> None` — the loader entry points (the latter keeps
  tests hermetic).
- `canonical_ids() -> frozenset[str]` and `category_for_canonical(cid) ->
  Optional[str]` — read-only introspection over `_TAXONOMY` for the service's
  validation. (`category_for_canonical` also consults the overlay so a
  just-`CREATE`d canonical is a valid `MAP` target.)

**Load timing.** `build_default_services` calls `CurationService.refresh_overlay()`
once at startup so a fresh process reflects prior curation. Each `resolve` refreshes
in-process, so the running app applies a correction on the very next normalization.
(Cross-process propagation — a second worker — is out of scope; single-process
uvicorn is the deployment today, and a restart reloads the overlay. Noted in §9.)

### 5.3 Capture wiring — `app/profile_sources/service.py`

`ProfileSourceService` gains an **optional** `curation: Optional[CurationService]`
dependency (kept optional so existing construction/tests don't break). After
`to_signal` in both `ingest_github` and `ingest_linkedin`, if a curation service is
present, iterate `signal.skills` and for each with `canonical is None` call
`self._curation.record_unmapped(skill.name, source_type=signal.source_type.value)`.
The adapters (`github.py`/`linkedin.py` `to_signal`) stay **pure** — capture is a
service-layer concern, where I/O already lives. Capture failures must never break
ingestion (best-effort; the signal is still returned/stored).

### 5.4 Wiring — `app/services/…`

- `Services.curation: CurationService` added (function-local build + `TYPE_CHECKING`
  import, the cycle-safe pattern S4.3/S5.1/S5.2/S5.3 established).
- `build_default_services` constructs `CurationService`, injects it into
  `ProfileSourceService`, and calls `refresh_overlay()` once.

### 5.5 Migration `0011_skill_curation`

One table `unmapped_terms`:

| column | type | notes |
|---|---|---|
| `id` | String PK | surrogate id (`cur_…`), matches repo convention |
| `norm_key` | String, unique, not null | stable identity + API handle |
| `display_name` | String, not null | |
| `source_types` | JSON, not null | list[str] |
| `occurrences` | Integer, not null | |
| `first_seen` / `last_seen` | DateTime, not null | |
| `status` | String, not null | CurationStatus value |
| `action` / `canonical` / `category` / `note` / `decided_by` | String, nullable | resolution |
| `decided_at` | DateTime, nullable | |
| `created_at` | DateTime, not null | store convention |

Surrogate `id` PK + a **unique index on `norm_key`** (the upsert key), consistent
with the other tables' UUID-style ids rather than a mutable natural key. **No
candidate FK** (§4). Extend the drift-guard / index / nullability tests to the new
table per repo convention. (SQLite-now / Postgres-shaped: both fine on both.)

## 6. API — admin plane (`X-API-Key`, existing `router`)

Candidate/org-facing auth is S6.4; until then curation is an operator function on
the existing admin key (same note as S6.1/S6.2's admin-plane endpoints).

- `GET /curation/skills/unmapped?status=pending&limit=N`
  → **200** `list[UnmappedTerm]`, occurrence-ranked. `status` optional
  (`pending`/`resolved`/`ignored`/omitted=all); `limit` clamped to
  `cur_queue_default_limit`. `401` without the admin key.
- `POST /curation/skills/resolve` — body
  `{ "norm_key": str, "action": "map|create|ignore", "canonical"?: str,
     "category"?: str, "note"?: str, "decided_by"?: str }`
  → **200** the updated `UnmappedTerm` · **404** unknown `norm_key` · **422**
  invalid decision per the §5.1 validation matrix (map without/to a non-existent
  canonical; create with a bad id or category, or a canonical that is already
  static; ignore with a canonical/category supplied) · **401** without the admin
  key.
  *(The term rides in the body, not the path — `norm_key` may contain spaces,
  `+`, or `#` (e.g. `c++`, `c#`) and is not URL-path-safe.)*

## 7. Config (`config.yaml` / `Settings`)

| knob | default | purpose |
|---|---|---|
| `cur_queue_default_limit` | 200 | default + max rows returned by the queue endpoint |
| `cur_min_term_len` | 2 | skip single-char noise before queueing |
| `cur_max_term_len` | 64 | drop overlong junk (also caps what we ever persist) |

## 8. Testing (TDD-offline) + smoke

**Unit / integration (offline, no key):**

- `skills.py`: overlay precedence (static wins; overlay fills gaps); `set_/clear_`
  overlay; `canonical_ids`/`category_for_canonical` (static + overlay).
- `CurationStore`: `record_unmapped` insert vs bump vs source-union; resolved terms
  not re-queued; `list_terms` ordering + status filter; `resolve` sets fields +
  status + raises on unknown; `load_overlay` includes only resolved map/create.
- `CurationService`: length guards; `resolve` validation matrix (map-unknown →
  error; create bad id/category → error; ignore-with-canonical → error; happy
  paths); overlay refresh makes `normalize_skill` resolve the term.
- Capture: a signal with `canonical=None` skills lands in the queue via
  `ProfileSourceService`; a fully-mapped signal queues nothing; capture failure
  doesn't break ingestion.
- API: GET queue shape/order; POST resolve 200/404/422; admin-key gate (401).
- Migration `0011` drift guard.

**Smoke `scripts/smoke_s63.py`** (uvicorn, key-less):

1. create candidate → `POST /candidates/{id}/sources/linkedin` with an export
   containing a novel skill (e.g. `COBOL`)
2. `GET /curation/skills/unmapped?status=pending` → term present, `occurrences=1`,
   `source_types=["linkedin_export"]`
3. `POST /curation/skills/resolve` `{action:"create", canonical:"cobol",
   category:"language"}` → 200 resolved
4. re-`POST` the **same** export → its skill now carries `canonical="cobol"`
   (overlay applied live) **and** the term is no longer in `?status=pending`
5. `POST resolve` a second term with `action:"map"` to an existing canonical; a
   third with `action:"ignore"`; a bad resolve → 422; unknown term → 404
6. `DELETE /candidates/{id}` (DPDP) → the queue term **still present**
   (candidate-agnostic, by design)

Target: `pytest -q` green (725 → ~750+), smoke exit 0.

## 9. Non-goals / follow-ups

- **Employers/institutions curation** — needs an unmapped marker on
  `canonicalize_employer`/`canonicalize_institution` (they return best-effort
  strings today). Natural next curation surface.
- **Resume-extraction capture** — same `canonical=None` marker on `SkillClaim`; a
  small hook in `normalize_profile`'s caller. Deliberately out to keep PI-1
  untouched this sprint.
- **Retroactive re-normalization** — already-stored signals/profiles are *not*
  rewritten when a term is later resolved (append-only history stays). Forward-only.
  A "re-normalize stored signals" batch is a follow-up.
- **Decision history / audit table** — a re-resolve overwrites (decision (b)). A
  per-term decision log is a follow-up if provenance is needed.
- **Cross-process overlay propagation** — a resolve refreshes only the handling
  process; a multi-worker deployment would need a reload signal or short-TTL cache.
  Single-process today; restart reloads. Out of scope.
- **LLM-suggested mappings** — deterministic-only per the vision ("no auto-learning
  without review"). A reviewer-assist suggestion is a possible later add, always
  human-approved.
- **Candidate-facing anything** — S6.4 (auth + DPDP portal).

## 10. Definition of done

- `app/curation/` (schema, store, service) + overlay hook in `skills.py` + capture
  wiring in `ProfileSourceService` + `Services.curation` wiring + startup overlay
  load.
- Migration `0011_skill_curation`; drift/index/nullability guards extended.
- Two admin endpoints (`GET unmapped`, `POST resolve`).
- `cur_*` config knobs.
- `CURATION.md` written (peer of `PROFILE_SOURCES.md`): the loop, the pure/impure
  seams, the overlay precedence rule, the DPDP posture, the API contract, config.
- `PROFILE_SOURCES.md` "Normalization curation loop — S6.3" note updated from
  "deferred" to "shipped, see CURATION.md".
- All tests green offline; `scripts/smoke_s63.py` exit 0.
- ROADMAP status board + Current state + session log updated; S6.3 marked done.
