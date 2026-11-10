"""Runs the Node tests for the browser scripts (scripts/test_*.cjs) as part of pytest."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE_TESTS = sorted((ROOT / "scripts").glob("test_*.cjs"))


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
@pytest.mark.parametrize("script", NODE_TESTS, ids=lambda path: path.name)
def test_browser_script_suite_passes(script):
    result = subprocess.run(
        ["node", "--test", str(script)],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]


def test_node_suites_are_found():
    names = {path.name for path in NODE_TESTS}
    assert {"test_core_browser_dependencies.cjs", "test_preferences.cjs"} <= names
