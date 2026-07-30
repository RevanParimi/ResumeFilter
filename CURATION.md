# Normalization curation loop (skills) — PI-6 / S6.3

A human-in-the-loop taxonomy repair loop. Skill terms that `normalize_skill`
can't map (`canonical=None`), surfaced by the GitHub + LinkedIn adapters, are
captured into a candidate-agnostic review queue. An admin reviewer resolves each
term — **map** to an existing canonical, **create** a new canonical, or
**ignore** — and the resolution feeds a deterministic in-memory overlay that
`normalize_skill` consults everywhere. No LLM, no auto-learning.

## The loop
[ingest → _capture_unmapped → CurationStore(queue) → admin GET/POST resolve →
CurationService.refresh_overlay → set_curated_overlay → normalize_skill]

## Pure / impure seams
- `normalize_skill` stays a pure dict lookup: `_INDEX.get(key) or _CURATED_OVERLAY.get(key)`.
  **Static taxonomy always wins**; the overlay only fills gaps. No per-call I/O.
- `_CURATED_OVERLAY` is loaded once in `build_default_services` (startup) and
  refreshed in-process on every `resolve`.
- Capture (`ProfileSourceService._capture_unmapped`) is best-effort and never
  breaks ingestion.

## DPDP posture
The queue (`unmapped_terms`) holds **no candidate_id** — aggregate taxonomy-gap
metadata (norm_key + counts + source_types), not personal data. No new
`ConsentPurpose`, no CASCADE. Candidate erasure deliberately leaves queue terms
intact. `cur_min_term_len`/`cur_max_term_len` drop noise/overlong junk before it
is ever persisted.

## API (admin plane, X-API-Key)
- `GET /curation/skills/unmapped?status=pending&limit=N` → 200 `list[UnmappedTerm]`
  (occurrence-ranked; `status` optional — one of pending|resolved|ignored; omit it
  to return all statuses).
- `POST /curation/skills/resolve` — body `{norm_key, action, canonical?, category?,
  note?, decided_by?}` → 200 updated term · 404 unknown term · 422 invalid
  (map without/to unknown canonical; create bad id/category or an existing
  canonical; ignore with canonical/category). Term rides in the body — `norm_key`
  is not URL-safe.

## Config
| knob | default | purpose |
|---|---|---|
| `cur_queue_default_limit` | 200 | default + max rows returned by the queue endpoint |
| `cur_min_term_len` | 2 | skip single-char noise before queueing |
| `cur_max_term_len` | 64 | drop overlong junk (also caps what we persist) |

## Non-goals / follow-ups
Employers/institutions curation · resume-extraction capture · retroactive
re-normalization of stored signals (forward-only) · decision-history/audit table
(re-resolve overwrites) · cross-process overlay propagation (single-process
today; restart reloads) · LLM-suggested mappings (deterministic-only per vision)
· candidate-facing UX (S6.4).
