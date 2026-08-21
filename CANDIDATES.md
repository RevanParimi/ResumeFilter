# veritas — Candidate Data Backbone (PI-1 complete: S1.1–S1.4, + S2.3 fingerprints)

How a resume becomes a durable, versioned, deduplicated, India-normalized
candidate record — and how that record is wired into the vetting pipeline
([FLOW.md](FLOW.md)) via `POST /candidates`. The fabrication signals that
read this data are in [FABRICATION.md](FABRICATION.md). Source of truth is
the code; file refs are clickable.

---

## Module layout

```
src/app/
├── core/
│   ├── config.py          Settings: contact_hash_salt, candidates_db_url
│   └── db.py              ★ shared SQLAlchemy foundation (S1.2)
│                            Base            — ONE metadata root for all
│                            make_engine()     subsystems (candidates now;
│                            make_session_factory()   ledger/features later)
│
├── candidates/
│   ├── schema.py          S1.1 — Pydantic contracts (CandidateProfile, ...)
│   ├── dates.py           S1.1 — deterministic "Jan 2021 – Present" parser
│   ├── hashing.py         S1.1 — normalize + salted-SHA256 contact hashes
│   ├── extractor.py       S1.1 — resume text → ExtractionResult
│   │                        LLM (parsing tier) with deterministic
│   │                        section-parser fallback (no key ⇒ still works)
│   ├── normalize/         S1.4 — pure India normalization (no LLM, no tables):
│   │                        text.py (norm_key aliasing) · skills.py (~85-skill
│   │                        taxonomy) · degrees.py (degree families + canonical
│   │                        CGPA/10) · orgs.py (institution/employer aliases,
│   │                        IIT/IIM/NIT/IIIT campus patterns + tiers) ·
│   │                        location.py (city gazetteer + notice-period parser)
│   │                        → normalize_profile() orchestrator; offset-preserving
│   │                        so SourceSpan provenance survives
│   ├── models.py          ★ S1.2 — ORM rows (CandidateRow/ResumeRow/ExtractionRow)
│   │                        + FingerprintRow (S2.3 — MinHash signatures)
│   └── store.py           ★ S1.2 — CandidateStore: ingest, identity resolution,
│                            reads, DPDP hard deletes, build_candidate_store()
│                            + save_fingerprint()/similar_resumes() (S2.3)
│
alembic/                   ★ S1.2 — schema migrations (one head for the shared Base)
├── env.py                   URL: explicit config > Settings.candidates_db_url
└── versions/
    ├── 0001_candidate_store.py       candidates + resumes + extractions
    └── 0002_resume_fingerprints.py   S2.3 — resume_fingerprints (CASCADE FKs)

scripts/
├── smoke_s11.py           extractor end-to-end on fixture resumes
├── smoke_s12.py           migrate scratch DB → ingest → dedup → delete
├── smoke_s13.py           uvicorn: POST /candidates → auto depth-eval → DPDP deletes
├── smoke_s14.py           normalization end-to-end on fixture resumes
└── smoke_s23.py           farm detection over HTTP (see FABRICATION.md)
```

## End-to-end flow (S1.1 → S1.2)

```
 resume text (normalized)
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ EXTRACTOR             src/app/candidates/extractor.py               │
│                                                                   │
│   primary:  LLM (tier "parsing") → JSON profile + verbatim       │
│             excerpts re-located in the text → character spans     │
│   fallback: deterministic section parser (regex contact, degree,  │
│             date ranges, seniority hints) — no API key required   │
│                                                                   │
│   every field carries: confidence [0..1] + SourceSpan provenance  │
│                                                                   │
│   S1.4: BOTH paths end with normalize_profile() — canonical       │
│   sibling fields (skills, degree families, CGPA/10, institution   │
│   tiers, employers, cities, notice period), all Optional so       │
│   legacy stored JSON still validates                              │
└──────────────────────────────┬───────────────────────────────────┘
                               │ ExtractionResult
                               │   .profile : CandidateProfile
                               │   .method  : "llm" | "heuristic"
                               │   .warnings: list[str]
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ HASHING               src/app/candidates/hashing.py                 │
│   email → lower/strip ─┐                                         │
│   phone → +91-normal  ─┼→ sha256(salt + ":" + value)             │
│                        │   salt = contact_hash_salt (config.yaml,│
│                        │   stable across deploys, NOT a secret)  │
│   fills contact.email_hash / contact.phone_hash on the profile   │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ STORE                 src/app/candidates/store.py                   │
│   CandidateStore.ingest(result, resume_text)                     │
│     1. resolve identity by hash (tree below)                     │
│     2. backfill missing hashes; latest non-empty name wins       │
│     3. dedup resume by sha256(text) per candidate                │
│     4. else new ResumeRow at version = max(version)+1            │
│     5. always append an ExtractionRow (full profile as JSON)     │
│   → IngestOutcome {candidate_id, resume_id, extraction_id,       │
│      resume_version, matched_existing, matched_on,               │
│      duplicate_resume}                                           │
└──────────────────────────────┬───────────────────────────────────┘
                               │ SQLAlchemy session
                               ▼
                    SQLite (candidates_db_url)
                    Postgres-shaped: switch = connection string
                    schema owned by Alembic (0001_candidate_store)
```

## Identity resolution (decision tree)

Matching NEVER merges two existing candidates — that needs human judgment.
It only attaches a new resume to at most one existing candidate.

```
ingest(profile, text)
│
├── profile.contact.email_hash present?
│   ├── yes → candidate with same email_hash exists?
│   │         ├── yes ──► MATCH (matched_on="email_hash")
│   │         └── no  ──┐
│   └── no ─────────────┤
│                       ▼
├── profile.contact.phone_hash present?
│   ├── yes → candidate with same phone_hash exists?
│   │         ├── yes ──► MATCH (matched_on="phone_hash")
│   │         └── no  ──┐
│   └── no ─────────────┤
│                       ▼
└──────────────► NEW CANDIDATE (no hashes ⇒ never guess identity)

on MATCH:  backfill candidate's missing email_hash/phone_hash from this
           resume; full_name updated to this resume's non-empty name
on same sha256(text) for that candidate:  reuse the ResumeRow (no new
           version), still record a fresh ExtractionRow (audit trail)
```

## Database schema (ER, ASCII)

```
┌────────────────────────────┐
│ candidates                 │
│────────────────────────────│
│ id           VARCHAR(36) PK│  UUID string
│ email_hash   VARCHAR(64) ix│  salted SHA256, nullable
│ phone_hash   VARCHAR(64) ix│  salted SHA256, nullable
│ full_name    TEXT          │  latest resume's name
│ created_at   DATETIME(tz)  │
│ updated_at   DATETIME(tz)  │  touched on every matched ingest
└──────────────┬─────────────┘
               │ 1
               │        ON DELETE CASCADE (enforced: PRAGMA foreign_keys=ON)
               │ *
┌──────────────▼─────────────┐
│ resumes                    │
│────────────────────────────│
│ id           VARCHAR(36) PK│
│ candidate_id FK → cand.  ix│
│ version      INTEGER       │  1, 2, 3... per candidate
│ raw_text     TEXT          │  ← persisted ON PURPOSE (see DPDP note)
│ text_sha256  VARCHAR(64) ix│  exact-duplicate detection
│ created_at   DATETIME(tz)  │
│ UNIQUE (candidate_id,      │
│         version)           │
└──────────────┬─────────────┘
               │ 1
               │ *
┌──────────────▼─────────────┐
│ extractions                │
│────────────────────────────│
│ id           VARCHAR(36) PK│
│ resume_id    FK → resumes ix│
│ candidate_id FK → cand.  ix│  denormalized for direct queries
│ method       VARCHAR(16)   │  "llm" | "heuristic"
│ profile      JSON          │  full CandidateProfile dump
│ warnings     JSON          │
│ created_at   DATETIME(tz)  │
└────────────────────────────┘

┌────────────────────────────┐
│ resume_fingerprints (S2.3) │  one per resume per algo id
│────────────────────────────│
│ id           VARCHAR(36) PK│
│ resume_id    FK → resumes ix│  ON DELETE CASCADE
│ candidate_id FK → cand.  ix│  ON DELETE CASCADE (self-exclusion key)
│ algo         VARCHAR(32) ix│  e.g. "minhash-v1:128x3" — rows only ever
│ signature    JSON          │  join on an exact algo id
│ shingle_count INTEGER      │
│ created_at   DATETIME(tz)  │
│ UNIQUE (resume_id, algo)   │
└────────────────────────────┘
```

Postgres-shaped on SQLite: UUID-string PKs, real FKs with `ondelete=CASCADE`,
JSON columns, timezone-aware timestamps. The PG migration is
`candidates_db_url` + `alembic upgrade head`, never a schema rewrite.

## DPDP delete paths (hard deletes, always available)

```
delete_candidate(id) ──► candidates row
                          └─ CASCADE ─► all resumes (raw_text erased)
                                         ├─ CASCADE ─► all extractions
                                         └─ CASCADE ─► all fingerprints (S2.3)

delete_resume(id) ─────► one resume version (raw_text erased)
                          ├─ CASCADE ─► its extractions
                          └─ CASCADE ─► its fingerprints (S2.3)
                          (candidate row + other versions stay)

DELETE /candidates/{id} additionally deletes every Report linked to the
candidate (report_store.delete_for_candidate) — derived data never outlives
the erasure, including a report finishing mid-delete (post-save re-check).
```

**Why raw_text is stored at all** (deliberate divergence from the report
store, which never persists resume text): every extracted field carries a
`SourceSpan` whose character offsets index into this exact text — without it,
provenance is unauditable and PI-2 fabrication forensics has nothing to
re-examine. It is first-party submitted data, and both delete paths above
erase it on request.

## Public surface

```
src/app/candidates/store.py
├── build_candidate_store(settings?) → CandidateStore    # NO create_all —
│                                                        # schema is Alembic's
└── CandidateStore(session_factory)
    ├── ingest(result: ExtractionResult, resume_text: str) → IngestOutcome
    ├── get_candidate(candidate_id)   → CandidateSummary | None
    ├── latest_profile(candidate_id)  → CandidateProfile | None
    │     (newest resume version; ties → newest extraction)
    ├── list_resumes(candidate_id)    → list[ResumeSummary]   (by version)
    ├── delete_candidate(candidate_id) → bool     # DPDP cascade
    ├── delete_resume(resume_id)       → bool     # DPDP single version
    ├── save_fingerprint(fp, resume_id, candidate_id) → bool   # S2.3,
    │     idempotent per (resume, algo)
    └── similar_resumes(fp, exclude_candidate_id, threshold, limit)
          → (matches best-first, corpus_size)     # S2.3, other candidates
                                                  # only, same algo only
```

## HTTP surface (S1.3) — [app/api/routes.py](src/app/api/routes.py)

| Endpoint | What it does |
|---|---|
| `POST /candidates` | upload (`resume_text` \| `resume_pdf_b64`) → extract → ingest → fingerprint + farm check (S2.3) → auto depth-eval (`evaluate: false` to skip for bulk import). Response: `IngestOutcome` fields + `extraction_method` + `resume_farm` + the `Report` (stamped with `candidate_id`) |
| `GET /candidates/{id}` | store summary + newest extracted profile (hashes only — no raw PII) |
| `GET /candidates/{id}/resumes` | resume versions (id, version, sha256, created_at) |
| `GET /candidates/{id}/reports` | all reports linked to the candidate |
| `DELETE /candidates/{id}` | DPDP erasure: candidate + resumes + extractions + fingerprints + linked reports |
| `DELETE /candidates/{id}/resumes/{rid}` | DPDP erasure of one version (ownership-checked) |

The engine and graph stay candidate-blind: the route passes the extracted
profile + farm assessment *into* `evaluate(...)` and stamps
`report.candidate_id` *after* — the graph never resolves identity.

## Extraction coverage (S9.2)

`src/app/candidates/coverage.py` — `assess_coverage(text, profile)` — is an
advisory assessment that compares the raw resume text against the extracted
`CandidateProfile` and reports where the text evidently states something the
profile does not carry. It is a statement about **the parser, never about the
candidate**, and it feeds no score, band, threshold or verdict — see
`ExtractionCoverage` in
[src/app/schemas/extraction.py](src/app/schemas/extraction.py).

**Why it exists.** Every signal veritas emits — depth score, fabrication
risk, the FABRICATION.md checks — is derived from `CandidateProfile`. When
the extractor silently drops a section, every downstream check runs
correctly over an empty list and honestly reports insufficient data. That
leaves the operator unable to tell *"this candidate has no work history"* (a
fresher) from *"the parser dropped it"* (a senior hire nobody actually
screened) — and for a fraud screen those are opposite conclusions.

**The five measured shapes** that motivated the sprint. Each was run against
`main` at `016f91f`, before the S9.2 fixes:

| Shape | Before |
|---|---|
| roles written as bullets, e.g. `- Senior Data Engineer, Acme Analytics (2019 - Present)` | 0 experience entries |
| the same resume with bullets removed | 2 entries |
| header reads `CAREER HISTORY` instead of `EXPERIENCE` | 0 entries |
| `Bachelor of Technology in Computer Science, VIT Vellore, 2015` | 0 education entries |
| `Programming Languages: Python, Java, Go` | a skill named `"Programming Languages: Python"` |

All five now extract correctly and report `complete`.

**The independence rule, and why it is load-bearing.** `coverage.py` must
not detect evidence with the extractor's own code. An instrument sharing the
extractor's eyes is blind exactly where the extractor is: point the
education check at `_DEGREE` and widening `_DEGREE` silently switches the
check off, while leaving it narrow makes the check agree there was nothing
there. Either way it reports `complete` on the exact resume it exists to
catch. `tests/test_extraction_coverage_independence.py` enforces the import
allow-list, including a ban on relative imports — `from . import extractor`
parses to `module=None` and would otherwise slip through the guard.

**The bands.** `insufficient_data` — below `coverage_min_chars` — is a
refusal, and it carries **no gaps at all**; `complete`; `minor_gaps`
(informational only); `major_gaps` (a field the text evidently describes is
entirely absent). A refusal carries no gaps deliberately, so a measurement
that could not be taken never reads as one that came back clean.

**The five checks**, each firing only when its field is **entirely empty**,
never on "fewer than expected": `experience_not_extracted`,
`education_not_extracted`, `skills_not_extracted`, `contact_not_extracted`,
`section_unrecognized` (a MINOR hint, evidence-gated so it does not fire on
every resume's name line).

**Where it is computed.** Once, inside `extract_profile`, after the LLM and
heuristic paths have already converged on `profile` — so one instrument
measures both doors. `_is_empty` is an all-of check, so an LLM profile
carrying a name, an email and zero experience never falls back to the
heuristic path, and would otherwise go unmeasured.

**Two deliberate non-additions**, both worth recording because someone will
try to "fix" them:

- **`professional summary` is not an experience alias.** It is prose in most
  resumes, and `_experience` opens an entry for any dated line in its
  section — treating it as an experience header would manufacture a
  fabricated job with no employer. Missing a role is an honest, bounded gap
  that coverage now reports; inventing one is not.
- **`bs` and `ms` are not in the degree pattern.** They match `MS Office`
  and `MS SQL Server`.

## Config knobs

| Key | Where | Default | Notes |
|---|---|---|---|
| `contact_hash_salt` | [config.yaml](config.yaml) | `veritas-dedup-v1` | NOT a secret; must stay stable or every stored hash is orphaned |
| `candidates_db_url` | [config.yaml](config.yaml) | `sqlite:///./data/veritas.db` | SQLAlchemy URL; Postgres = change string + `alembic upgrade head` |

## Testing & smoke

```
tests/
├── test_db_core.py           engine/session plumbing, FK pragma, StaticPool
├── test_candidate_models.py  table shapes, version uniqueness, cascades
├── test_migrations.py        upgrade head + DRIFT GUARD (migration ≡ models)
├── test_candidate_store.py   ingest/dedup/versioning/reads/deletes/builder
├── test_candidate_schema.py  S1.1: contracts, spans, confidence bounds
├── test_contact_hashing.py   S1.1: email/phone normalization + salted hashes
├── test_candidate_dates.py   S1.1: date-range parsing
└── test_candidate_extractor_{heuristic,llm}.py   S1.1: both extractor paths
```

All offline (in-memory SQLite, no network, no API key). End-to-end:
`python scripts/smoke_s12.py` — migrates a scratch DB, ingests a fixture
resume three ways (new / updated text / identical text), verifies match +
versioning + dedup + latest_profile + delete, prints `SMOKE OK`. Green both
with a live OpenRouter key (`[llm]`) and key-less (`[heuristic]`).
