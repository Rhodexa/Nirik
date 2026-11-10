"""Swapping symbols onto layers across libraries (Blender)."""

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("devtools.flash.fla", reason="FLA-RE not found (set FLARE_DIR)")

from devtools.blender_env import blender_cmd, blender_env  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "blender" / "scripts" / "swap.py"


@pytest.mark.blender
def test_swap(twilight_library, tmp_path):
    # Two libraries: the same art in two folders, so every swap crosses libraries.
    for name in ("twilight", "twin"):
        shutil.copytree(twilight_library, tmp_path / name, symlinks=True)
    r = subprocess.run(blender_cmd("-b", "--factory-startup", "--python-exit-code", "1",
                                   "--python", str(SCRIPT), "--", str(tmp_path)),
                       env=blender_env(), capture_output=True, text=True, timeout=900)
    print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL"))))
    assert r.returncode == 0, r.stdout[-6000:] + r.stderr[-2000:]
