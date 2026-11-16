# Veritas agent entry point

Follow [AGENTS.md](AGENTS.md) for repository conventions and validation.
The remediation queue is closed by owner decision; do not resume it.
[docs/PROGRESS.md](docs/PROGRESS.md) records the current state.

Repository conventions: domain rules live in `src/app/domains/`; the evaluation
pipeline does not import a concrete domain. Keep tunables in `config.yaml`,
secrets in `.env`, and migrations in Alembic. Deterministic fallbacks, advisory
human review, tenant isolation and consent/erasure remain required.
Use first-party data only; new tables need explicit consent and erasure ownership.

Read [FEATURE_STATUS.md](FEATURE_STATUS.md) for capability orientation and
[FLOW.md](FLOW.md) for pipeline details only when the task needs them.
Superseded plans and the closed delivery records live in Git history.
