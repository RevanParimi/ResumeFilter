# S8.5 — org-plane outcome route (plan)

Spec: `docs/superpowers/specs/2026-08-10-org-outcome-route-design.md`.
Branch: `s86-org-outcome-route`. Baseline measured: **1553 passed** (183s).
TDD: a failing test proven before every change, one commit per task.

| # | Task | Files | Test first |
|---|---|---|---|
| 1 | `OutcomeSource` + provenance fields on `OutcomeRecord` (`recorded_by` **required**) | `app/reports/schema.py` | `tests/test_report_outcomes.py` |
| 2 | `build_outcome` + `OutcomeRefused` — the ONE constructor, carrying all three rules | `app/reports/outcomes.py` | `tests/test_report_outcomes.py` |
| 3 | `max_outcome_notes_chars` | `app/core/config.py`, `config.yaml` | task 2's cap test |
| 4 | Three columns on `OutcomeRow` | `app/reports/models.py` | `tests/test_migrations.py` |
| 5 | Migration `0020_outcome_authorship` (+ backfill, + drop server_default) | `alembic/versions/0020_outcome_authorship.py` | `tests/test_migrations.py` |
| 6 | Store: persist/read the three fields; `outcomes_for_org` | `app/reports/store.py` | `tests/test_report_store.py` |
| 7 | Facade: rename `OrgScopedReads` → `OrgScopedAccess`, add `record_outcome` + `outcomes` | `app/screening/scope.py`, `app/services/__init__.py`, `tests/conftest.py` | `tests/test_screening_scope.py` |
| 8 | Admin route through `build_outcome`; flywheel record loses `notes`, gains provenance | `app/api/routes.py` | `tests/test_api.py` |
| 9 | The two org routes | `app/api/routes.py` | `tests/test_screening_outcome_api.py` |
| 10 | Cross-tenant + erasure proofs | — | `tests/test_screening_outcome_api.py` |
| 11 | Smoke over real HTTP | `scripts/smoke_s85_outcome.py` | — |
| 12 | UI: the four buttons return + recorded history | `frontend/Veritas.dc.html`, `frontend/api.js` | the three checkers |
| 13 | Docs: TENANCY.md §5, SCREENING.md, FLOW.md, UI.md §4.B, REQUIREMENTS.md, ROADMAP | — | — |

## Ordering constraints

- 1 → 2 (the constructor needs the field), 4 → 5 (the guard compares migration
  to ORM), 6 → 7 → 9 (the route reads through the facade reads through the store).
- 8 before 9: the admin door must already go through `build_outcome`, or task 9
  writes the second door beside an unmigrated first one — which is the exact
  shape the shared constructor exists to prevent.

## Mutation probes (after green)

| Mutant | Must be caught by |
|---|---|
| `build_outcome` drops the `max_notes_chars` check | the cap test, at BOTH doors |
| `build_outcome` defaults `recorded_by` to `OPERATOR` | the org route's provenance test |
| `outcomes_for_org` drops the `org_id` filter | the operator-note-not-visible test |
| `outcomes_for_org` drops the ownership check | org B's 404 on the GET |
| `record_outcome` returns a record for an unowned report | org B's 404 on the POST |
| `0020` uses `CASCADE` instead of `SET NULL` on `org_id` | the org-offboarding test |

## Definition of done

`pytest -q` green and above 1553 · `smoke_s85_outcome` exit 0 · `smoke_s84a`
and `smoke_s84b` re-run green · all three UI checkers green · docs updated ·
ROADMAP status board + session log written.
