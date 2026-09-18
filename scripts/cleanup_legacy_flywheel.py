"""Counts-only offline inspection; see docs/LEGACY_FLYWHEEL.md before apply.

No app imports, settings, database access, ownership inference or text backups.
Run only with stopped writers and exclusive operator control of the directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile


MAX_LINE_BYTES = 1024 * 1024


class CleanupError(Exception):
    """Messages are fixed codes, never paths, records or raw OS exceptions."""


def _signature(info):
    # Windows stat/fstat can disagree on ctime (creation vs metadata change).
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _validate_path(path: Path):
    if not path.is_absolute() or ".." in path.parts or path.suffix.lower() != ".jsonl":
        raise CleanupError("explicit_absolute_jsonl_file_required")
    # Reject aliases, including Windows junctions/reparse points and ADS paths.
    if any(":" in part for part in path.parts[1:]):
        raise CleanupError("unsafe_path")
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise CleanupError("linked_path_refused")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise CleanupError("single_regular_file_required")
    return info


def inspect_file(path: Path):
    before = _validate_path(path)
    counts = dict(bytes=0, lines=0, records=0, unresolved_ownership=0,
                  candidate_reference_records=0, report_reference_records=0,
                  malformed_lines=0, oversized_lines=0, blank_lines=0)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        if _signature(os.fstat(source.fileno())) != _signature(before):
            raise CleanupError("source_changed")
        while chunk := source.readline(MAX_LINE_BYTES + 1):
            counts["lines"] += 1
            oversized = len(chunk) > MAX_LINE_BYTES
            first = chunk
            while True:
                digest.update(chunk)
                counts["bytes"] += len(chunk)
                if chunk.endswith(b"\n") or not oversized:
                    break
                chunk = source.readline(MAX_LINE_BYTES + 1)
                if not chunk:
                    break
            if oversized:
                counts["oversized_lines"] += 1
                continue
            if not first.strip():
                counts["blank_lines"] += 1
                continue
            try:
                row = json.loads(first)
            except (ValueError, UnicodeError, RecursionError):
                row = None
            if not isinstance(row, dict):
                counts["malformed_lines"] += 1
                continue
            counts["records"] += 1
            counts["unresolved_ownership"] += 1
            # Presence only: these fields never authorize retaining or joining data.
            counts["candidate_reference_records"] += int("candidate_id" in row)
            counts["report_reference_records"] += int("report_id" in row)
        if _signature(os.fstat(source.fileno())) != _signature(before):
            raise CleanupError("source_changed")
    if _signature(_validate_path(path)) != _signature(before):
        raise CleanupError("source_changed")
    return {**counts, "sha256": digest.hexdigest()}, _signature(before)


def cleanup(path: Path, *, apply=False, expected_sha256=None, writers_stopped=False):
    if apply and (not writers_stopped or not expected_sha256
                  or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256)):
        raise CleanupError("apply_requires_digest_and_stopped_writers")
    summary, original = inspect_file(path)
    if not apply:
        return {"status": "dry_run", **summary}
    if not summary["bytes"]:
        return {"status": "already_empty", **summary}
    if summary["sha256"] != expected_sha256.lower():
        raise CleanupError("digest_mismatch")

    # Temporary files contain ZERO source bytes. A process crash can leave an
    # empty .tmp file, never another personal-data copy. Do not sweep old temps.
    fd, temp_name = tempfile.mkstemp(prefix=".flywheel-empty-", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as empty:
            empty.flush()
            os.fsync(empty.fileno())
        # Detect ordinary edits/replacement since inspection. This is not a
        # lock against hostile directory mutation; stopped writers are required.
        if _signature(_validate_path(path)) != original:
            raise CleanupError("source_changed")
        os.replace(temp, path)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temp.unlink(missing_ok=True)
    return {"status": "cleared", **summary}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal error includes arbitrary supplied argument text.
        raise CleanupError("invalid_arguments")


def main(argv=None):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("file", type=Path, help="Absolute path to one regular .jsonl file")
    parser.add_argument("--apply", action="store_true", help="Replace all content with an empty file")
    parser.add_argument("--expected-sha256", help="Digest from a reviewed dry-run")
    parser.add_argument("--writers-stopped", action="store_true", help="Confirm exclusive access and stopped legacy writers")
    try:
        args = parser.parse_args(argv)
        result = cleanup(args.file, apply=args.apply, expected_sha256=args.expected_sha256,
                         writers_stopped=args.writers_stopped)
    except CleanupError as exc:
        print(json.dumps({"status": "error", "code": str(exc)}))
        return 2
    except OSError:
        print(json.dumps({"status": "error", "code": "filesystem_operation_failed"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
