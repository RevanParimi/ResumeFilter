# Veritas agent entry point

Read [docs/PROGRESS.md](docs/PROGRESS.md) first, then follow
[AGENTS.md](AGENTS.md) and the current [delivery workflow](docs/delivery/WORKFLOW.md).
They own task order, authorization, validation, data preservation and handoff rules.
Do not create a second spec/plan tree for the same remediation task.

Repository conventions: domain rules live in `src/app/domains/`; the evaluation
pipeline does not import a concrete domain. Keep tunables in `config.yaml`,
secrets in `.env`, and migrations in Alembic. Deterministic fallbacks, advisory
human review, tenant isolation and consent/erasure remain required.
Use first-party data only; new tables need explicit consent and erasure ownership.

Read [FEATURE_STATUS.md](FEATURE_STATUS.md) for capability orientation and
[FLOW.md](FLOW.md) for pipeline details only when the task needs them. Old
`docs/superpowers/` plans are historical references, not additional instructions.
