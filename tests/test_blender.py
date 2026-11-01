"""Runs each tests/blender/bt_*.py in its own headless Blender process.

  pytest -m blender -s                 run all, show per-test PASS/FAIL lines
  NIRIK_UPDATE_GOLDENS=1 pytest ...    accept current renders as goldens
"""

import subprocess
from pathlib import Path

import pytest

from devtools.blender_env import blender_cmd, blender_env

SCRIPTS = sorted((Path(__file__).parent / "blender").glob("bt_*.py"))


@pytest.mark.blender
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.stem)
def test_in_blender(script):
    result = subprocess.run(
        blender_cmd("-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script)),
        env=blender_env(), capture_output=True, text=True, timeout=600,
    )
    report = [l for l in result.stdout.splitlines() if l.startswith(("PASS", "FAIL", "NEW GOLDEN"))]
    print("\n".join(report))
    if result.returncode != 0:
        pytest.fail(f"Blender exited {result.returncode}\n{result.stdout[-6000:]}\n{result.stderr[-3000:]}")
