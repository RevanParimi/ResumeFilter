# veritas — Candidate Data Backbone (PI-1: S1.1 + S1.2)

How a resume becomes a durable, versioned, deduplicated candidate record.
This documents the *candidates* subsystem built in PI-1 so far; the vetting
pipeline it will plug into (S1.3) is documented in [FLOW.md](FLOW.md).
Source of truth is the code; file refs are clickable.

---

## Module layout

```
app/
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
│   ├── models.py          ★ S1.2 — ORM rows (CandidateRow/ResumeRow/ExtractionRow)
│   └── store.py           ★ S1.2 — CandidateStore: ingest, identity resolution,
│                            reads, DPDP hard deletes, build_candidate_store()
│
alembic/                   ★ S1.2 — schema migrations (one head for the shared Base)
├── env.py                   URL: explicit config > Settings.candidates_db_url
└── versions/
    └── 0001_candidate_store.py   candidates + resumes + extractions

scripts/
├── smoke_s11.py           extractor end-to-end on fixture resumes
└── smoke_s12.py           migrate scratch DB → ingest → dedup → delete
```

## End-to-end flow (S1.1 → S1.2)

```
 resume text (normalized)
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ EXTRACTOR             app/candidates/extractor.py               │
│                                                                   │
│   primary:  LLM (tier "parsing") → JSON profile + verbatim       │
│             excerpts re-located in the text → character spans     │
│   fallback: deterministic section parser (regex contact, degree,  │
│             date ranges, seniority hints) — no API key required   │
│                                                                   │
│   every field carries: confidence [0..1] + SourceSpan provenance  │
└──────────────────────────────┬───────────────────────────────────┘
                               │ ExtractionResult
                               │   .profile : CandidateProfile
                               │   .method  : "llm" | "heuristic"
                               │   .warnings: list[str]
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ HASHING               app/candidates/hashing.py                 │
│   email → lower/strip ─┐                                         │
│   phone → +91-normal  ─┼→ sha256(salt + ":" + value)             │
│                        │   salt = contact_hash_salt (config.yaml,│
│                        │   stable across deploys, NOT a secret)  │
│   fills contact.email_hash / contact.phone_hash on the profile   │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ STORE                 app/candidates/store.py                   │
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
```

Postgres-shaped on SQLite: UUID-string PKs, real FKs with `ondelete=CASCADE`,
JSON columns, timezone-aware timestamps. The PG migration is
`candidates_db_url` + `alembic upgrade head`, never a schema rewrite.

## DPDP delete paths (hard deletes, always available)

```
delete_candidate(id) ──► candidates row
                          └─ CASCADE ─► all resumes (raw_text erased)
                                         └─ CASCADE ─► all extractions

delete_resume(id) ─────► one resume version (raw_text erased)
                          └─ CASCADE ─► its extractions
                          (candidate row + other versions stay)
```

**Why raw_text is stored at all** (deliberate divergence from the report
store, which never persists resume text): every extracted field carries a
`SourceSpan` whose character offsets index into this exact text — without it,
provenance is unauditable and PI-2 fabrication forensics has nothing to
re-examine. It is first-party submitted data, and both delete paths above
erase it on request.

## Public surface (what S1.3 wires into the API)

```
app/candidates/store.py
├── build_candidate_store(settings?) → CandidateStore    # NO create_all —
│                                                        # schema is Alembic's
└── CandidateStore(session_factory)
    ├── ingest(result: ExtractionResult, resume_text: str) → IngestOutcome
    ├── get_candidate(candidate_id)   → CandidateSummary | None
    ├── latest_profile(candidate_id)  → CandidateProfile | None
    │     (newest resume version; ties → newest extraction)
    ├── list_resumes(candidate_id)    → list[ResumeSummary]   (by version)
    ├── delete_candidate(candidate_id) → bool     # DPDP cascade
    └── delete_resume(resume_id)       → bool     # DPDP single version
```

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
