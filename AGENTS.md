# Veritas project handoff

Read `docs/PROGRESS.md` first at the start of every chat. If the user says
"continue", resume its next incomplete task without repeating the audit or
asking whether the already-authorized fixes should proceed.

Execution structure is in `docs/delivery/README.md`: remediation PI -> sprint
-> session task. Read `docs/delivery/WORKFLOW.md` and the current task brief/PI
section before implementing. Each task requires acceptance criteria, meaningful
regressions, full pytest for code changes, relevant API/browser journeys and a
recorded diff review. Follow the workflow's database/migration gates where
applicable. Do not equate source/binding checks with browser execution, fakes
with live-provider validation, or self-review with independent review.
Missing required evidence leaves the task awaiting validation, not done.

The user wants exactly one task per chat session (confirmed 9 September 2026).
Complete and test the next task, update the handoff, then stop. Do not start
another backlog task in the same chat unless the user explicitly requests it.
If an item is too large for a focused session, split it into bounded subtasks
in the handoff and complete only the next subtask. Record unfinished work
honestly; do not mark the parent task complete until all its subtasks are done.
Read only the source, tests, and design notes relevant to that task; the long
`docs/ROADMAP.md` is historical reference, not required reading end to end.

Standing authorization (7 September 2026): fix the findings in
`docs/CODEBASE_REVIEW_2026-09-07.md`, complete the unfinished feature flows, and
simplify unnecessary code. Prefer small direct fixes over new abstraction
layers. This does not authorize publishing, deployment, sending messages, or
discarding existing user data.

Use `.resume/Scripts/python.exe` on Windows for Python commands. System Python
is not the project environment. Tests: `.resume/Scripts/python.exe -m pytest -q`.
Add meaningful regression tests for correctness/security fixes; tests must run
offline using the existing fake providers and isolated stores. UI checks:
`node scripts/check_ui_bindings.js`, plus relevant browser/contract tests.

Preserve advisory/human-review behavior, tenant isolation, consent/erasure
semantics, domain-independent evaluation, and deterministic model fallbacks.
Never equate polished/AI-assisted writing with fabricated experience. Video
interview scoring must judge answer content, not appearance or inferred emotion.
Keep secrets out of output and documentation. Do not overwrite the existing
modified `data/veritas.db` or previously uncommitted work.

Before finishing a chat, update `docs/PROGRESS.md` with completed task IDs,
tests actually run, changed behavior, remaining risks, and the exact next task.
Update the task's PI status and `docs/delivery/tasks/<id>.md` evidence record.
Keep that file short. Add detailed evidence to the relevant task document and
a brief session entry to `docs/ROADMAP.md` when appropriate.
