"""Real CLI journey on temporary synthetic copies; no app/env/DB access."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


SCRIPT = Path(__file__).with_name("cleanup_legacy_flywheel.py").resolve()


def main():
    checks = 0
    with tempfile.TemporaryDirectory(prefix="veritas-legacy-smoke-") as folder:
        scratch = Path(folder)
        source = scratch / "legacy.jsonl"
        sibling = scratch / "other.jsonl"
        data = b'{"report_id":"known","claim_text":"PRIVATE-KNOWN"}\n' \
               b'{"report_id":"deleted","notes":"PRIVATE-DELETED"}\n' \
               b'{"claim_text":"PRIVATE-MISSING"}\n' \
               b'{"candidate_id":["a","b"],"notes":"PRIVATE-AMBIGUOUS"}\n' \
               b'PRIVATE-MALFORMED\n'
        source.write_bytes(data)
        sibling.write_bytes(data)

        def invoke(*args, expected=0):
            result = subprocess.run([sys.executable, str(SCRIPT), str(source), *args],
                                    cwd=scratch, capture_output=True, text=True, timeout=15,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            assert result.returncode == expected
            assert "PRIVATE" not in result.stdout + result.stderr
            return json.loads(result.stdout)

        dry = invoke()
        assert dry["status"] == "dry_run" and dry["unresolved_ownership"] == 4
        assert dry["malformed_lines"] == 1
        assert source.read_bytes() == sibling.read_bytes() == data
        assert set(scratch.iterdir()) == {source, sibling}
        checks += 4
        bad = invoke("--apply", "--expected-sha256", "0" * 64, "--writers-stopped", expected=2)
        assert bad["code"] == "digest_mismatch" and source.read_bytes() == data
        checks += 1
        applied = invoke("--apply", "--expected-sha256", dry["sha256"], "--writers-stopped")
        assert applied["status"] == "cleared" and source.read_bytes() == b""
        assert sibling.read_bytes() == data
        checks += 2
        retry = invoke("--apply", "--expected-sha256", dry["sha256"], "--writers-stopped")
        assert retry["status"] == "already_empty"
        inspected = invoke()
        assert inspected["bytes"] == inspected["records"] == 0
        assert set(scratch.iterdir()) == {source, sibling}
        checks += 3
    print(f"R1-S1-T2 synthetic CLI smoke: {checks}/{checks} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
