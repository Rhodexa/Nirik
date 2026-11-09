"""A puppet saved as a .blend in its library folder works when appended."""

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("devtools.flash.fla", reason="FLA-RE not found (set FLARE_DIR)")

from devtools.blender_env import blender_cmd, blender_env  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "blender" / "scripts" / "append.py"


@pytest.mark.blender
def test_append_puppet_blend_twice(twilight_library, tmp_path):
    lib = tmp_path / "library" / "twilight"
    shutil.copytree(twilight_library, lib)
    for stage in ("build", "use", "reopen"):
        r = subprocess.run(blender_cmd("-b", "--factory-startup", "--python-exit-code", "1",
                                       "--python", str(SCRIPT), "--", str(lib), stage),
                           env=blender_env(), capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, f"{stage}:\n" + r.stdout[-4000:] + r.stderr[-2000:]
