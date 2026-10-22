"""Execute shipped JS handler regressions offline; Chrome is a separate gate."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="offline UI behavior requires Node")
@pytest.mark.parametrize("screen", [
    "admin_orgs", "admin_users", "curation", "evaluate", "screening", "interview",
    "interview_audio", "verification",
])
def test_shipped_handlers_offline(screen):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["node", "--test", f"scripts/test_ui_{screen}.js"],
                            cwd=root, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
