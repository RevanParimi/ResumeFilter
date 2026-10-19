# Normalization curation loop (skills)

Human review repairs gaps in deterministic skill normalization. GitHub and
LinkedIn-export adapters capture unknown terms only after the source commits.
Raw observations belong to that source and, through it, its candidate. Reviewers
explicitly approve vocabulary or ignore the term. No LLM or automatic learning.

## Capture and review lifetime

Original input is limited to 128 Unicode code points, including whitespace,
with no Unicode Cc controls. Configured normalized-key bounds still apply.
Rejected terms are skipped without truncation or failing source ingestion.
LinkedIn checks original CSV cells while source display behavior stays unchanged.
Capture errors log only the event and source type, without submitted values,
SQL parameters or exception text.

Migration `0028_owned_curation` supplies the owned tables. Each capture inserts
an independent `curation_observations` row against a durable source FK. Candidate
or source deletion cascades its observations. A refused source commit contributes
nothing. A failed HTTP response after a commit does not roll that commit back;
observations remain linked and erasable.

Each observation expires exactly 30 days after creation. Repeats do not extend
earlier lifetimes. Queue counts, source types and representative display text
come only from surviving unexpired observations in one SQL statement snapshot.
There is no detached raw aggregate. Reads and successful responses are snapshots;
erasure after the read can still race delivery. Pagination order changes with
capture, expiry or erasure. Fresh concurrent capture can form a later queue item.

## Reviewer contract

The admin router accepts authenticated operator sessions or the shared admin key.
Sessions require CSRF on writes. Organization and candidate credentials cannot
review the shared queue. The operator UI loads real pending terms and provides
review, map/create, ignore, refresh, paging and error recovery.

Promotion requires an explicit approved `alias`, `canonical` and `category`.
The alias starts blank in the UI; submitted raw text is never implicitly promoted.
Map validates the category against an existing canonical. Create validates a new
snake_case ID and the existing taxonomy categories. Static taxonomy always wins.
Approval is human judgment, not a guarantee that vocabulary is anonymous.

Resolution atomically deletes the claimed raw observations and inserts only
approved vocabulary in `curation_aliases`. Alias conflicts roll back deletion
and return a generic 409. Expired-only or erased terms cannot authorize approval,
including expiry while waiting for a database lock. Ignore deletes observations
without retaining an ignore-list entry; fresh submission may reappear.

Queue terms include an opaque `review_revision` for their exact live
observation set. HTTP callers must pass it as `expected_revision` on resolution;
omitted/null preconditions return 422 before mutation. The operator browser sends
the loaded revision for map/create/ignore and starts approved aliases blank.
A changed live set returns generic 409 and rolls back the claim; missing or
expired-only terms retain 404. Matching uses the observations returned by the
atomic DELETE and time sampled after lock waits, not a separate preflight read.
Identical fresh submissions have different revisions. Older resolution clients
must fetch a queue snapshot and send its revision; direct internal store/service
callers keep their optional maintenance contract. Stale/absent browser reviews
clear the editor and refresh without silently retrying a fresh submission.
Unknown write outcomes retain a read-only draft until a successful refresh
checks its revision. Queue/editor state clears on navigation and session loss;
bounded requests and reply validation settle refusals safely. Evidence belongs
to [R3-S2-T3B](docs/delivery/EVIDENCE-R3.md#r3-s2-t3b).
Revisions are transient hashes, not stored raw-history or authentication tokens.
Later concurrent capture outside the DELETE snapshot can remain a new queue item.

New decisions retain action/time and a real authenticated operator ID when
available. Shared keys have NULL operator identity. Notes and caller-supplied
reviewer names/IDs are rejected. Decision receipts contain no submitted raw key,
display name or contributors. A response failure after a committed decision does
not imply rollback; refresh/restart reads persisted state.

## Physical maintenance and compatibility

Default application startup physically purges expired observations before loading
the overlay. A purge failure fails startup. Run this command **daily**, from the
project environment with the intended candidates database configured and migrated:

```powershell
.resume/Scripts/python.exe scripts/purge_curation.py
```

The command prints a removed-row count only and exits nonzero on failure. An
operator must schedule and monitor it; no background timer or OS job is installed
by this change. Delayed maintenance or downtime can retain expired rows physically
past 30 days even though review reads and resolution exclude them.

Legacy `unmapped_terms` content stays classified `legacy_unattributed`. Runtime
legacy write/list/resolve methods are removed. Ordinary queue responses never
expose its raw displays, notes or reviewer names. Existing resolved keys still
provide normalization compatibility; those keys may contain personal text.
The [legacy disposition evidence](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2d2c)
owns validation of the offline procedure below. No ownership is inferred and no
working-data cleanup has been performed. The [working-data inventory decision](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2d4)
verified no legacy rows in the named active database; none required disposition.
That snapshot does not inventory other databases, backups or OneDrive history.
Nonempty legacy stores still require explicit review of all raw fields and keys,
including keys used for normalization compatibility.

The approved overlay loads at startup and refreshes in the resolving process.
Other running processes do not receive updates automatically; restart reloads
persisted approvals. Stored source signals are not retroactively renormalized.
New explicit aliases override legacy overlay collisions; static taxonomy prevails.

## Explicit legacy disposition procedure

`scripts/dispose_legacy_curation.py` uses only an explicitly supplied existing
database. It reads neither `.env` nor application configuration and performs no
migrations, database creation, backups or automatic cleanup. First migrate the
intended database to `0028_owned_curation` through the normal migration process.
Inventory and selected preview run with database-enforced read-only access:

```powershell
.resume/Scripts/python.exe scripts/dispose_legacy_curation.py --database C:/scratch/synthetic.db
.resume/Scripts/python.exe scripts/dispose_legacy_curation.py --database C:/scratch/synthetic.db --selection C:/scratch/disposition.json
```

For PostgreSQL, use `--database-url-env VERITAS_DISPOSITION_DB_URL` instead of
`--database`; the named environment variable must already hold the intended URL.
Never put credentials in a command argument or evidence log. The tool outputs
fixed numeric legacy counts (`total`, `pending`, `ignored`, `resolved`, `other`)
and, for a selection, numeric planned/committed `selected`, `matched`, `absent`,
`removed`, `approved` counts. Unknown status text, IDs, names, aliases, notes and
database exceptions are not printed. Default inventory includes all remaining
unattributed rows; it does not infer ownership or certify absence of personal text.

An authorized operator reviews the historical rows in a restricted local database
viewer, including resolved keys and all display/note/reviewer fields. Keep that
review and any manifests outside repository/evidence logs. Select exact existing
row IDs; unselected rows remain unchanged. Each manifest is a JSON array of
1–200 entries, at most 256 KiB, with only these fields (synthetic example):

```json
[
  {"id": "synthetic-pending-id", "action": "remove"},
  {"id": "synthetic-resolved-id", "action": "map", "alias": "Reviewed vocabulary", "canonical": "python", "category": "language"}
]
```

`remove` deletes the entire selected legacy row, including its compatibility
mapping. `map`/`create` delete that row and retain only explicitly supplied
approved vocabulary using the ordinary review validation rules. Nothing is copied
from historical strings. An operator can explicitly approve the same alias to
preserve compatibility or replace it; approval is human judgment, not anonymization.
There is no inferred operator ID, free-text note or permanent raw ignore entry.

After reviewing the counts and obtaining authorization **for that working-data
selection**, stop all application workers and other legacy writers. Run the same
command with `--apply`, then inventory the remainder and restart every worker to
reload normalization. This task authorizes apply only against disposable synthetic
stores. Existing backup/archive copies need their own retention disposition; this
tool does not create or remove them. Physical storage reclamation is database
maintenance, separate from logical row deletion.

Apply commits all selected removals and approvals in one transaction. Conflicting
approved aliases or retained resolved mappings, nonlegacy selections and invalid
fields refuse the entire batch; no existing vocabulary is overwritten. PostgreSQL
serializes legacy writers with a table lock and uses bounded lock/statement waits;
SQLite reserves its write transaction before selection. Interruption before commit
rolls back; a lost response after commit can be retried. Missing IDs are reported
as `absent` and do not authorize approval, including on replay. Absence alone is
not proof of a previous cleanup: inspect the remaining inventory. Previews are
snapshots, so apply rechecks rows/conflicts; never infer success from a preview.
New owned observations and unselected legacy rows remain intact. A later source
submission can create a new owned observation after a historical alias is removed.

## API and configuration

- `GET /curation/skills/unmapped?status=pending&limit=N&cursor=...` returns
  `{terms, next_cursor}`. Omit status for the same active queue. Compatibility
  `resolved`/`ignored` filters return empty pages; decisions retain no raw history.
- `POST /curation/skills/resolve`: `{norm_key, expected_revision, action, alias?, canonical?, category?}`.
  Map/create require all three vocabulary fields; ignore takes none. Returns
  `{action, alias, canonical, category, decided_at, admin_user_id}`. Missing terms:
  404 with a well-formed revision; invalid/missing/null preconditions or decisions:
  422; changed live snapshots or alias conflicts: 409; unauthorized reviewers: 401.
  The browser requests 20-term pages and shows loaded counts, not a queue total.
- Queue default/max: `cur_queue_default_limit=200`. Normalized-key capture bounds:
  `cur_min_term_len=2`, `cur_max_term_len=64`. Fixed raw bound and review TTL are
  independent of these settings.

[Activation evidence](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2d2b2b) owns the runtime,
API, browser, maintenance, regression and review results. The wider retention
finding remains open through legacy disposition and combined validation.
