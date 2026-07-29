# Profile sources — GitHub + LinkedIn export (PI-6 / S6.1–S6.2)

A **profile source** turns an external, candidate-owned account or export into
a structured, normalized, provenanced **skill + activity signal** stored as a
peer of resume extractions. The signal is **advisory evidence** — never a
score, never a gate, never auto-anything. Depth-eval scoring and verdicts are
untouched.

S6.1 shipped the reusable `app/profile_sources/` spine plus its first adapter,
**GitHub**. S6.2 adds the second adapter, **LinkedIn export** — the candidate's
own "Get a copy of your data" ZIP, uploaded base64 over the API (no network, no
LLM, no scraping). Both adapters share the same pure `parse → to_signal →
persist` shape and the same `ProfileSourceSignal` envelope. The **normalization
curation loop** (reviewing/correcting unmapped taxonomy terms) is deferred to
**S6.3**.

## GitHub pipeline

```
candidate handle (explicit, or derived from the profile's GitHub link)
        │
        ▼
GitHubClient.gather_user_signal(login)   → GitHubUserRaw   (the only network)
        │
        ▼
to_signal(raw, settings, *, fetched_at)  → ProfileSourceSignal   (PURE, no I/O)
        │
        ▼
ProfileSourceStore.save_signal(...)      → profile_sources row   (CASCADE)
```

- **`GitHubClient.gather_user_signal`** (`app/services/github.py`) — fetches
  `/users/{login}` + `/users/{login}/repos` (bounded by `ps_github_repo_limit`)
  and per-repo `/languages` for the top `ps_github_language_repos` recent
  non-fork repos. Any failure (404 / rate-limit / network) returns
  `available=False` + a warning — it **never raises**. Public data only.
- **`to_signal`** (`app/profile_sources/github.py`) — pure transform. Aggregates
  per-language bytes across the candidate's non-fork repos, maps each language to
  the S1.4 skill taxonomy (`normalize_skill`; unknown languages are kept with
  `canonical=None`), and derives a bounded, evidence-monotone confidence
  (`0.3 + 0.6·(weight/max_weight)`, capped at `0.9`). Repos beyond the
  language-fetch window contribute their primary language at
  `PRIMARY_LANGUAGE_NOMINAL_BYTES`. An unavailable raw becomes a
  `method="unavailable"` signal (empty skills, warnings copied).
- **`ProfileSourceStore`** (`app/profile_sources/store.py`) — append-only on the
  candidates DB (one row per fetch → history for point-in-time later),
  newest-first reads, `latest_for_source`. No delete path: rows CASCADE with the
  candidate.

## Handle resolution

`ProfileSourceService.ingest_github(candidate_id, handle=None)`:

1. Explicit `handle` wins (a bare login `[A-Za-z0-9-]{1,39}` or a
   `github.com/...` URL, parsed via `parse_github_url`).
2. Else derived from the candidate's latest profile `LinkType.GITHUB` link.
3. Else `ValueError` → **400**.

Unknown candidate → `LookupError` → **404**.

## LinkedIn pipeline (S6.2)

```
candidate's own "Get a copy of your data" export, base64-encoded over HTTP
        │
        ▼
base64.b64decode (route)                 → bytes                 (transport only)
        │
        ▼
parse_linkedin_export(bytes, settings)   → LinkedInExportRaw      (PURE, no I/O)
        │
        ▼
to_signal(raw, settings, *, fetched_at)  → ProfileSourceSignal    (PURE, no I/O)
        │
        ▼
ProfileSourceStore.save_signal(...)      → profile_sources row    (CASCADE)
```

- **Transport**: the candidate downloads their own LinkedIn data export (a
  ZIP of CSVs) and the client base64-encodes it into
  `POST /candidates/{id}/sources/linkedin` as `{"export_b64": ...}`. There is
  no network call and no LLM anywhere in this path — everything downstream of
  the decode is pure, offline parsing.
- **`parse_linkedin_export`** (`app/profile_sources/linkedin.py`) — pure,
  tolerant ZIP/CSV reader. Recognizes `Skills.csv` / `Positions.csv` /
  `Education.csv` / `Profile.csv` / `Certifications.csv` / `Languages.csv` by
  case-insensitive basename (tolerating a nested export directory), accepts
  LinkedIn's known column-name variants (e.g. `Company Name`/`Company`,
  `School Name`/`School`), and degrades **per row** — a ragged/corrupt row is
  skipped, not the whole section. A non-ZIP payload or a ZIP with none of the
  known CSVs yields `available=False` + a warning rather than raising. Row
  count per CSV is capped by `ps_linkedin_max_rows`.
- **`to_signal`** (`app/profile_sources/linkedin.py`) — pure transform.
  Self-reported `Skills.csv` entries are treated as **claims**: each is mapped
  to the S1.4 taxonomy (`normalize_skill`; unknown terms kept with
  `canonical=None`) at a conservative base confidence
  (`ps_linkedin_skill_base_confidence`, default 0.4). A skill is bumped to a
  higher **corroborated** confidence (`ps_linkedin_skill_corroborated_confidence`,
  default 0.6) when it also appears as a standalone token in a position's
  title/description or in the headline — token-boundary matching, so
  "Java" never corroborates off "JavaScript". Positions/education are
  de-identified into a `LinkedInActivity` (employer names run through the S1.4
  `canonicalize_employer`/`canonicalize_institution` normalizers and deduped;
  counts only otherwise — no descriptions, no raw text). A raw with
  `available=False` becomes a `method="unavailable"` signal (empty skills,
  warnings copied) — a valid-but-unrecognized export is a valid advisory
  outcome, not an error.
- **Schema**: `ProfileSourceType.LINKEDIN_EXPORT`; `ProfileSourceSignal.activity`
  is a discriminated union `GitHubActivity | LinkedInActivity` (discriminator
  `kind`). Rows stored before S6.2 have no `activity.kind`; a
  `model_validator(mode="before")` backfills it from the row's own
  `source_type` (`github` vs `linkedin_export`) so old GitHub rows keep
  validating with **no migration**. `method` gained an `"export"` literal
  alongside the existing `"api"`/`"unavailable"`.
- **`ProfileSourceService.ingest_linkedin(candidate_id, data: bytes)`** —
  unknown candidate → `LookupError` → **404**; otherwise
  parse → transform → `ProfileSourceStore.save_signal` (same append-only,
  CASCADE store the GitHub adapter uses). Persisted `identifier` is the fixed
  string `"linkedin_export"` (there is no per-account handle to key on).

## API (admin/candidate plane)

Candidate-facing auth is **S6.3's successor, S6.4**; until then these ride the
existing `X-API-Key` router, which will move them under candidate auth.

- `POST /candidates/{id}/sources/github` — body `{"handle": "octocat"}`
  (optional). **200** `ProfileSourceSignal`. A handle that 404s / is
  rate-limited returns **200** with `method="unavailable"` + warnings (a missing
  GitHub is a valid advisory outcome, not a client error). **404** unknown
  candidate; **400** no resolvable / malformed handle.
- `POST /candidates/{id}/sources/linkedin` — body `{"export_b64": "..."}`.
  **200** `ProfileSourceSignal` with `method="export"`; a valid ZIP with no
  recognizable LinkedIn CSVs still returns **200** with `method="unavailable"`
  + warnings. **404** unknown candidate. **422** malformed base64 (fails
  strict `b64decode`) or oversize payload (`export_b64` longer than
  `max_linkedin_b64_chars`) — malformed transport is a client error, unlike an
  unrecognized-but-valid export.
- `GET /candidates/{id}/sources?source_type=...` — **200** stored signals
  (newest first), optionally filtered by `github` / `linkedin_export`;
  **404** unknown candidate.

## DPDP posture

- **No new `ConsentPurpose`** for either adapter. GitHub: the handle is
  candidate-supplied and the data is public. LinkedIn: the export is the
  candidate's own first-party data, uploaded by the candidate — the same
  posture as PI-1 resume ingest.
- **Store the derived signal only.** GitHub: canonical skills + activity
  aggregates + the public handle, no raw repo dumps. LinkedIn: canonical
  skills + de-identified counts/canonical employer & institution names only —
  **no raw contact PII, no position/summary text, no connections list** are
  ever persisted; the uploaded ZIP itself is never stored, only its derived
  signal.
- **Erasure:** `profile_sources.candidate_id` is `ON DELETE CASCADE` for both
  adapters, so `DELETE /candidates/{id}` sweeps every stored source of every
  type (proven by test).

## Config (`config.yaml` / `Settings`)

| knob | default | purpose |
|---|---|---|
| `ps_github_repo_limit` | 100 | max repos pulled for a user |
| `ps_github_language_repos` | 30 | top-N recent repos that get a byte-accurate `/languages` fetch |
| `ps_github_include_forks` | false | forks excluded from the signal by default |
| `max_linkedin_b64_chars` | 8,000,000 | reject oversize `export_b64` uploads (≈6 MB zip) → 422 |
| `ps_linkedin_skill_base_confidence` | 0.4 | confidence for a self-reported skill with no corroboration |
| `ps_linkedin_skill_corroborated_confidence` | 0.6 | confidence once a position/headline mentions the skill as a token |
| `ps_linkedin_max_rows` | 5,000 | per-CSV row cap while parsing an export |

`github_api_base` / `github_token` (secret) already exist. Unauthenticated public
API is enough (~60 req/hr/IP); a token only raises the limit.

## Non-goals / follow-ups

- **Resume-vs-source corroboration** (resume-claimed vs source-observed
  skills, both directions, across *all* profile sources) — still deferred;
  LinkedIn's within-export corroboration (skill vs. that same export's
  positions/headline) is not this — it's a narrower, single-source signal.
- **Normalization curation loop** (reviewing/correcting unmapped taxonomy
  terms surfaced by either adapter) — **S6.3**.
- **Feature-store consumption** of the signal — a small PI-4 feature-definition
  addition later; S6.1/S6.2 land the data + API only.
- **Flywheel wiring** — the signal is not part of the eval graph.
- **Candidate auth + DPDP portal** — **S6.4**.
