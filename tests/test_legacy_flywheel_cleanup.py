"""Only synthetic files; the CLI never loads application settings or stores."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import cleanup_legacy_flywheel as cleanup


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/cleanup_legacy_flywheel.py"


def run_cli(path, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), *args],
        capture_output=True, text=True, cwd=path.parent, timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def legacy_bytes():
    # Ground truth belongs to this fixture, never to a guessed name in the CLI.
    rows = [
        {"candidate_id": "known-A", "report_id": "active-report", "claim_text": "PRIVATE-KNOWN"},
        {"report_id": "deleted-report", "notes": "PRIVATE-DELETED"},
        {"claim_text": "PRIVATE-MISSING"},
        {"candidate_id": ["A", "B"], "name": "PRIVATE-AMBIGUOUS"},
    ]
    return b"".join(json.dumps(row).encode() + b"\n" for row in rows) + b'PRIVATE-MALFORMED\n[]\n\n'


def test_dry_run_counts_without_text_or_writes(tmp_path):
    path = tmp_path / "legacy.jsonl"
    before = legacy_bytes()
    path.write_bytes(before)
    proc = run_cli(path)
    assert proc.returncode == 0, proc.stdout
    summary = json.loads(proc.stdout)
    assert summary["status"] == "dry_run"
    assert summary["records"] == 4
    assert summary["unresolved_ownership"] == 4
    assert summary["malformed_lines"] == 2
    assert summary["blank_lines"] == 1
    assert summary["sha256"] == hashlib.sha256(before).hexdigest()
    assert "PRIVATE" not in proc.stdout + proc.stderr
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_apply_removes_all_ownership_states_and_is_repeatable(tmp_path):
    path = tmp_path / "legacy.jsonl"
    sibling = tmp_path / "other.jsonl"
    before = legacy_bytes()
    path.write_bytes(before)
    sibling.write_bytes(before)
    digest = hashlib.sha256(before).hexdigest()
    proc = run_cli(path, "--apply", "--expected-sha256", digest, "--writers-stopped")
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["status"] == "cleared"
    assert path.read_bytes() == b""
    assert sibling.read_bytes() == before
    again = run_cli(path, "--apply", "--expected-sha256", digest, "--writers-stopped")
    assert again.returncode == 0
    assert json.loads(again.stdout)["status"] == "already_empty"
    assert set(tmp_path.iterdir()) == {path, sibling}


@pytest.mark.parametrize("extra,code", [
    (("--apply",), "apply_requires_digest_and_stopped_writers"),
    (("--apply", "--expected-sha256", "0" * 64, "--writers-stopped"), "digest_mismatch"),
    (("--PRIVATE-INVALID",), "invalid_arguments"),
    (("--app", "--expected-sha256", "0" * 64, "--writers-stopped"), "invalid_arguments"),
])
def test_refusals_preserve_source_and_hide_argument_text(tmp_path, extra, code):
    path = tmp_path / "PRIVATE-PATH.jsonl"
    path.write_bytes(legacy_bytes())
    result = run_cli(path, *extra)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "error", "code": code}
    assert "PRIVATE" not in result.stdout + result.stderr
    assert path.read_bytes() == legacy_bytes()


def test_changed_file_requires_new_inspection(tmp_path):
    path = tmp_path / "legacy.jsonl"
    path.write_bytes(legacy_bytes())
    digest = json.loads(run_cli(path).stdout)["sha256"]
    path.write_bytes(b'{"notes":"NEW-PRIVATE"}\n')
    result = run_cli(path, "--apply", "--expected-sha256", digest, "--writers-stopped")
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "digest_mismatch"
    assert path.read_bytes() == b'{"notes":"NEW-PRIVATE"}\n'


def test_bounded_lines_invalid_utf8_and_deep_json(tmp_path):
    path = tmp_path / "legacy.jsonl"
    data = (b'x' * (cleanup.MAX_LINE_BYTES * 2) + b'\n' + b'\xff\n'
            + b'[' * 2000 + b']' * 2000 + b'\n{}\n' + b'y' * (cleanup.MAX_LINE_BYTES + 1))
    path.write_bytes(data)
    result = run_cli(path)
    assert result.returncode == 0
    counts = json.loads(result.stdout)
    assert counts["lines"] == 5
    assert counts["oversized_lines"] == 2
    assert counts["malformed_lines"] == 2
    assert counts["records"] == 1
    assert counts["bytes"] == len(data)
    assert counts["sha256"] == hashlib.sha256(data).hexdigest()
    assert path.read_bytes() == data


@pytest.mark.parametrize("kind", ["relative", "parent", "directory", "extension", "missing", "hardlink"])
def test_unsafe_targets_refused(tmp_path, kind):
    source = tmp_path / "source.jsonl"
    source.write_bytes(legacy_bytes())
    target = source
    if kind == "relative":
        target = Path("source.jsonl")
    elif kind == "parent":
        target = tmp_path / ".." / tmp_path.name / "source.jsonl"
    elif kind == "directory":
        target = tmp_path / "directory.jsonl"
        target.mkdir()
    elif kind == "extension":
        target = tmp_path / "database.db"
        target.write_bytes(legacy_bytes())
    elif kind == "missing":
        target = tmp_path / "absent.jsonl"
    elif kind == "hardlink":
        target = tmp_path / "alias.jsonl"
        os.link(source, target)
    # All errors use fixed output, including paths that fail before parsing.
    result = subprocess.run([sys.executable, str(SCRIPT), str(target)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "error"
    assert source.read_bytes() == legacy_bytes()


def test_linked_ancestor_refused(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    source = actual / "source.jsonl"
    source.write_bytes(legacy_bytes())
    alias = tmp_path / "alias"
    if os.name == "nt":
        # Creating a junction needs no symlink privilege; no deletion via cmd.
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(actual)],
                              capture_output=True, timeout=15)
        assert made.returncode == 0
    else:
        alias.symlink_to(actual, target_is_directory=True)
    try:
        result = run_cli(alias / "source.jsonl")
        assert result.returncode == 2
        assert json.loads(result.stdout)["code"] == "linked_path_refused"
        assert source.read_bytes() == legacy_bytes()
    finally:
        if os.name == "nt":
            os.rmdir(alias)
        else:
            alias.unlink()


@pytest.mark.parametrize("failure", ["sync", "replace", "changed"])
def test_precommit_failure_preserves_content_and_retry(tmp_path, monkeypatch, capsys, failure):
    path = tmp_path / "source.jsonl"
    path.write_bytes(legacy_bytes())
    digest = hashlib.sha256(legacy_bytes()).hexdigest()
    real_sync = cleanup.os.fsync
    def fail(*args):
        raise OSError("PRIVATE-OS-ERROR")
    def changed(fd):
        real_sync(fd)
        path.write_bytes(b'CHANGED-PRIVATE\n')
    with monkeypatch.context() as patch:
        if failure == "replace":
            patch.setattr(cleanup.os, "replace", fail)
        else:
            patch.setattr(cleanup.os, "fsync", changed if failure == "changed" else fail)
        code = cleanup.main([str(path), "--apply", "--expected-sha256", digest, "--writers-stopped"])
        assert code == 2
    assert "PRIVATE" not in capsys.readouterr().out
    expected = b'CHANGED-PRIVATE\n' if failure == "changed" else legacy_bytes()
    assert path.read_bytes() == expected
    assert list(tmp_path.iterdir()) == [path]
    result = cleanup.cleanup(path, apply=True, expected_sha256=hashlib.sha256(expected).hexdigest(), writers_stopped=True)
    assert result["status"] == "cleared"
    assert path.read_bytes() == b""


def test_read_failure_is_sanitized_without_mutation(tmp_path, monkeypatch, capsys):
    path = tmp_path / "source.jsonl"
    path.write_bytes(legacy_bytes())
    with monkeypatch.context() as patch:
        def refused(*args, **kwargs):
            raise PermissionError("PRIVATE-PATH")
        patch.setattr(Path, "open", refused)
        assert cleanup.main([str(path)]) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "error", "code": "filesystem_operation_failed"}
    assert output.err == ""
    assert path.read_bytes() == legacy_bytes()


@pytest.mark.parametrize("stage", ["before", "after"])
def test_process_interruption_at_replace_boundary(tmp_path, stage):
    path = tmp_path / "source.jsonl"
    path.write_bytes(legacy_bytes())
    digest = hashlib.sha256(legacy_bytes()).hexdigest()
    # Real child process exits abruptly at the replacement boundary; no finally.
    harness = tmp_path / "interrupt.py"
    harness.write_text(
        "import os, sys\n"
        f"sys.path.insert(0, {str(SCRIPT.parent)!r})\n"
        "import cleanup_legacy_flywheel as c\n"
        "replace = c.os.replace\n"
        "def interrupted(src, dst):\n"
        + ("    replace(src, dst)\n" if stage == "after" else "")
        + "    os._exit(73)\n"
        "c.os.replace = interrupted\n"
        "raise SystemExit(c.main(sys.argv[1:]))\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(harness), str(path), "--apply",
                           "--expected-sha256", digest, "--writers-stopped"],
                          capture_output=True, timeout=15)
    assert proc.returncode == 73
    assert path.read_bytes() == (legacy_bytes() if stage == "before" else b"")
    leftovers = list(tmp_path.glob(".flywheel-empty-*.tmp"))
    assert len(leftovers) == (1 if stage == "before" else 0)
    assert all(p.read_bytes() == b"" for p in leftovers)
    again = run_cli(path, "--apply", "--expected-sha256", digest, "--writers-stopped")
    assert again.returncode == 0
    assert path.read_bytes() == b""
