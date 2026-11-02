"""Renaming the project folder must not break saved scenes."""

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("devtools.flash.fla", reason="FLA-RE not found (set FLARE_DIR)")

from devtools.blender_env import blender_cmd, blender_env  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "blender" / "scripts" / "relink.py"


def run(project, stage):
    r = subprocess.run(blender_cmd("-b", "--factory-startup", "--python-exit-code", "1",
                                   "--python", str(SCRIPT), "--", str(project), stage),
                       env=blender_env(), capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]


@pytest.mark.blender
def test_scene_survives_project_rename(twilight_library, tmp_path):
    old = tmp_path / "Autumn"
    shutil.copytree(twilight_library, old / "library" / "twilight")
    (old / "Blends").mkdir()
    run(old, "build")
    new = tmp_path / "Nirik"
    old.rename(new)
    run(new, "reopen")
