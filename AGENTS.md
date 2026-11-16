# Veritas agent guide

The remediation queue (the R1-R4 PI, sprint and session-task records) is closed
by owner decision of 16 November 2026. Do not resume any open remediation task.
There is no standing "next task": work starts from an explicit owner request.
The closed delivery records remain in Git history.

## Repository conventions

- FastAPI backend in `src/app`, plain-JavaScript UI in `frontend/`, Alembic
  migrations in `alembic/`, pytest suite in `tests/`.
- Domain rules live in `src/app/domains/`; the evaluation pipeline does not
  import a concrete domain.
- Tunables live in `config.yaml` and `src/app/core/config.py`, secrets in
  `.env`. Schema changes are new Alembic revisions; never edit an existing one.
- Use first-party data only. A new table needs explicit consent and erasure
  ownership.
- Preserve deterministic model fallbacks, advisory human review, tenant
  isolation and consent/erasure semantics.
- Never equate polished or AI-assisted writing with fabricated experience.
  Interview scoring judges answer content, not appearance or inferred emotion.
- Keep secrets out of output and documentation. Do not open, migrate or
  overwrite `data/veritas.db`; use scratch databases.

## Validation

- Python: `.resume/Scripts/python.exe` on Windows (system Python is not the
  project environment). On Linux export `PYTHONPATH=src` first.
- Clear inherited `DEE_*` variables before running tests. Set
  `DEE_TEST_DB_URL` only to a database you may destroy: the Postgres variants
  run migrations against it.
- Full suite: `python -m pytest -q --tb=short`. Tests run offline with the
  existing fake providers and isolated stores. Correctness and security fixes
  need a regression test.
- UI: `node scripts/check_ui_bindings.js`, `node --check` on each touched
  frontend file and the matching `node scripts/test_ui_*.js`. Binding and
  source checks are not browser execution, and fakes are not live-provider
  validation.
