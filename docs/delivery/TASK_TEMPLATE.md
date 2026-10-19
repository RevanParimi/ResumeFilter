# Inline task record fields

Reuse these fields in the existing active task or sprint section. This is a
reference, not a request to create a file per task/chat. Follow [WORKFLOW.md](WORKFLOW.md).

- ID/title, status, PI/sprint/audit mapping and prerequisites.
- Trigger, expected observable result, exclusions and relevant entry points.
- Short design decision and compatibility/data implications.
- Acceptance criteria mapped to meaningful regression/API/browser scenarios.
- Required validation layers, explaining any that do not apply.
- Evidence: intended reproducer where applicable; final commands, environment,
  passed/failed/skipped counts, warning summary and artifact locations.
- Separate self-review: reviewed code state, scope, findings and resolutions;
  distinguish independent review and live-provider evidence when actually run.
- Remaining risks/missing validation and completion decision; never close a
  parent while its acceptance or required evidence is incomplete.

Put only the exact next task and current risks in `docs/PROGRESS.md`; avoid
copying evidence into each ancestor. Fold completed records into the relevant
PI evidence file under a stable task anchor and update inbound links.
