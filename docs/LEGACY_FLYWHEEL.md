# Legacy flywheel file policy

Production no longer writes JSONL (R1-S1-T1). SQL reports and outcomes retain
their existing lifecycle. Historical files can still contain personal text in
claims, probes, notes and other fields, including records for erased candidates.
Removing identifiers does not anonymize this text.

The policy is to remove **all content of an explicitly selected legacy file**
when its cleanup is authorized. No rows are imported into SQL or retained based
on inferred identity. A known candidate, a deleted candidate, an absent ID and
an ambiguous identity all have the same outcome: preserved during inspection,
removed on apply. Candidate/report IDs are only unverified references. The CLI
does not query a database or guess owners from names, email or claim text.

## Inspection and application

Use the project Python environment. Substitute the absolute path to the one
intended legacy `.jsonl` file; there is no directory scan or default data path.

```powershell
.resume/Scripts/python.exe scripts/cleanup_legacy_flywheel.py 'C:\scratch\legacy.jsonl'
```

Inspection opens the file read-only, creates no backup or temporary file and
prints JSON counts plus SHA256. It never prints paths, IDs, record types, free
text or raw exceptions. `unresolved_ownership` counts every parsed object;
malformed and oversized lines are counted separately and are also removed on
apply. Reference counts indicate field presence only, including invalid values.
Blank lines are counted separately. Parsing is limited to 1 MiB per line;
larger lines are streamed into the digest without parsing or retaining them.

After reviewing the counts, obtain authorization to clear the specified file,
stop every legacy writer/reader, and control the containing directory exclusively.
Use the inspected digest:

```powershell
.resume/Scripts/python.exe scripts/cleanup_legacy_flywheel.py 'C:\scratch\legacy.jsonl' --apply --expected-sha256 '<64-character digest>' --writers-stopped
```

The explicit file must be a regular, singly linked file. Relative paths, `..`,
symlinks, junctions/reparse points, alternate data streams and non-JSONL paths
are refused. It must be independently identified as the intended legacy file;
the extension and digest do not prove provenance. No application settings,
`.env`, live providers or database are loaded. Source and sibling files remain
untouched by dry-run. Apply replaces only the specified directory entry.

## Failure, retries and retention limits

Apply refuses a changed digest and rechecks file identity/metadata immediately
before replacement. This is an offline operator tool, not a concurrent-writer
protocol: these checks do not defeat hostile directory mutation or a writer
racing the final replacement. Do not run it against active writers.

An empty temporary file in the same directory is flushed/fsynced, then replaces
the source atomically. Before replacement, interruption leaves the original;
after replacement, the source is empty. Retry inspection and apply as needed.
An empty source returns `already_empty` even with the previous digest, supporting
retry after a lost success response. Errors exit 2 with fixed codes and never
claim completion. `cleared` includes the **pre-cleanup** counts/digest; inspect
again to verify zero bytes. No missing file is silently treated as success.

There is no source backup and no automatic rollback: a backup would retain the
same personal data. Hard interruption may leave an empty `.flywheel-empty-*.tmp`
file; inspect individually rather than running a broad cleanup. On POSIX the
directory is also fsynced; Windows has no portable directory fsync here. Atomic
process-interruption behavior is tested; sudden power-loss durability is not
claimed. Network/cloud filesystems may provide different guarantees.

Clearing this directory entry does not securely erase media, open file handles,
snapshots, sync history or external backups. Those copies require their own
authorized retention action. No whole-system erasure completion can be inferred
from this command. This development task applies only to synthetic test files;
the user's existing legacy files remain untouched.
