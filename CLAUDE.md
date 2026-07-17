# CLAUDE.md — veritas (talent intelligence platform)

This repo is **veritas**: an Indian-market talent intelligence platform
(Mercor-inspired) grown from the depth-eval-resume-engine. Multi-PI project;
work continues across many chat sessions.

## Start of every session

1. **Read `docs/ROADMAP.md` first** — it has the current sprint, next action,
   and the full PI/sprint status board. Continue from there unless the user
   says otherwise.
2. Product design + decisions:
   `docs/superpowers/specs/2026-07-06-veritas-talent-platform-design.md`.
   Architecture: `FLOW.md` (pipeline) · `CANDIDATES.md` (PI-1 candidate
   backbone) · `FABRICATION.md` (PI-2 fabrication defense).
3. **End of session:** update `docs/ROADMAP.md` (status board, "Current state",
   session log) before finishing.

## Non-negotiable conventions

- TDD with fully offline tests (NullLLM/fake-services pattern in
  `tests/conftest.py`); `pytest -q` must be green before merge.
- Every LLM-assisted step needs a deterministic fallback (no API key ⇒ still works).
- Advisory only: no auto-reject anywhere; conservative calibration stays.
- DPDP: first-party data only, consent objects + delete paths on new tables.
- Config: tunables in `config.yaml`, secrets only in `.env` (`DEE_*` prefix).
- DB: SQLAlchemy + Alembic on SQLite, written Postgres-shaped.
- Domain knowledge goes in `app/domains/` via `@register_domain`; the graph
  never imports a concrete domain.
- Each sprint ends with a local smoke run (uvicorn + scripted HTTP calls on
  fixture resumes), not just unit tests.
- Sprint workflow: spec → plan (`docs/superpowers/specs|plans/`) → TDD build →
  smoke → update ROADMAP.
