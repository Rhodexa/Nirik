"""First loads that failed on real libraries: broken tile links after the
cache move, half-built puppets, and ".001" collections in library .blends."""

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("devtools.flash.fla", reason="FLA-RE not found (set FLARE_DIR)")

from devtools.blender_env import blender_cmd, blender_env  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "blender" / "scripts" / "first_load.py"


@pytest.mark.blender
def test_first_loads(twilight_library, tmp_path):
    lib = tmp_path / "twilight"
    shutil.copytree(twilight_library, lib, symlinks=True)
    r = subprocess.run(blender_cmd("-b", "--factory-startup", "--python-exit-code", "1",
                                   "--python", str(SCRIPT), "--", str(lib)),
                       env=blender_env(), capture_output=True, text=True, timeout=600)
    print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL"))))
    assert r.returncode == 0, r.stdout[-5000:] + r.stderr[-2000:]
