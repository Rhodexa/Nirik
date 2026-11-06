"""Save a puppet, move its project folder, reopen: it must find its library.

blender ... --python relink.py -- PROJECT_DIR STAGE   (STAGE: build | reopen)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bpy
import numpy as np

import harness

args = sys.argv[sys.argv.index("--") + 1:]
project, stage = Path(args[0]), args[1]
expected = Path(args[2]) if len(args) > 2 else project / "library" / "twilight"
harness.load_nirik()

if stage == "build":
    harness.clean()
    bpy.ops.nirik.load_character(directory=str(project / "library" / "twilight"))
    bpy.ops.wm.save_as_mainfile(filepath=str(project / "Blends" / "scene.blend"))
    print("BUILT")
else:
    bpy.ops.wm.open_mainfile(filepath=str(project / "Blends" / "scene.blend"))
    arm = next(o for o in bpy.data.objects if "nirik_library" in o)
    assert arm["nirik_library"] == str(expected.resolve()), arm["nirik_library"]
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = 128
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.type, cam.data.ortho_scale = "ORTHO", 2.0
    cam.location, cam.rotation_euler = (0, -5, 0.6), (1.5707963, 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.film_transparent = True
    _, px = harness.render("relinked", 1)
    assert px[..., 3].max() > 0.9, "character renders empty: tiles not found"
    print("REOPENED")
