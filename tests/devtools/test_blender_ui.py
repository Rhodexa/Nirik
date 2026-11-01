"""Drive Nirik's operators in headless Blender against a real library."""

import subprocess
from pathlib import Path

import pytest

pytest.importorskip("devtools.flash.fla", reason="FLA-RE not found (set FLARE_DIR)")

from devtools.blender_env import blender_cmd, blender_env  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "blender" / "scripts" / "operators.py"


@pytest.mark.blender
def test_operators(twilight_library):
    result = subprocess.run(blender_cmd("-b", "--factory-startup", "--python-exit-code", "1",
                                        "--python", str(SCRIPT), "--", str(twilight_library)),
                            env=blender_env(), capture_output=True, text=True, timeout=600)
    print("\n".join(l for l in result.stdout.splitlines() if l.startswith(("PASS", "FAIL"))))
    assert result.returncode == 0, result.stdout[-5000:] + result.stderr[-2000:]
