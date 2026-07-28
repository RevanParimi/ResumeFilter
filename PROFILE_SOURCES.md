# Profile sources — GitHub-as-signal (PI-6 / S6.1)

A **profile source** turns an external, candidate-owned account into a
structured, normalized, provenanced **skill + activity signal** stored as a peer
of resume extractions. The signal is **advisory evidence** — never a score,
never a gate, never auto-anything. Depth-eval scoring and verdicts are untouched.

S6.1 ships the reusable `app/profile_sources/` spine plus its first adapter,
**GitHub**. LinkedIn export parsing is the next adapter (S6.2) on the same spine;
`ProfileSourceType` grows then.

## Pipeline

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

## API (admin/candidate plane)

Candidate-facing auth is **S6.3**; until then these ride the existing
`X-API-Key` router. S6.3 will move them under candidate auth.

- `POST /candidates/{id}/sources/github` — body `{"handle": "octocat"}`
  (optional). **200** `ProfileSourceSignal`. A handle that 404s / is
  rate-limited returns **200** with `method="unavailable"` + warnings (a missing
  GitHub is a valid advisory outcome, not a client error). **404** unknown
  candidate; **400** no resolvable / malformed handle.
- `GET /candidates/{id}/sources?source_type=github` — **200** stored signals
  (newest first); **404** unknown candidate.

## DPDP posture

- **No new `ConsentPurpose`.** The handle is candidate-supplied and the data is
  public — the same first-party ingest posture as PI-1 resume ingest.
- **Store the derived signal only** — canonical skills + activity aggregates +
  the public handle. No raw repo dumps, no third-party PII.
- **Erasure:** `profile_sources.candidate_id` is `ON DELETE CASCADE`, so
  `DELETE /candidates/{id}` sweeps every stored source (proven by test).

## Config (`config.yaml` / `Settings`)

| knob | default | purpose |
|---|---|---|
| `ps_github_repo_limit` | 100 | max repos pulled for a user |
| `ps_github_language_repos` | 30 | top-N recent repos that get a byte-accurate `/languages` fetch |
| `ps_github_include_forks` | false | forks excluded from the signal by default |

`github_api_base` / `github_token` (secret) already exist. Unauthenticated public
API is enough (~60 req/hr/IP); a token only raises the limit.

## Non-goals / follow-ups

- **Corroboration** (resume-claimed vs source-observed skills, both directions) —
  deferred; a natural S6.2 / fabrication-layer addition now that the signal exists.
- **Feature-store consumption** of the signal — a small PI-4 feature-definition
  addition later; S6.1 lands the data + API only.
- **LinkedIn export** — S6.2 (second adapter on this spine).
- **Flywheel wiring** — the signal is not part of the eval graph.
- **Candidate auth** — S6.3.
