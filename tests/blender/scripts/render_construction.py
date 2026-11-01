"""Build a puppet from a library, pose one construction, render it.

blender -b --factory-startup --python render_construction.py -- \
    LIBRARY RIG CONSTRUCTION OUT.png CENTER_X CENTER_Y ORTHO_SCALE WIDTH HEIGHT

Center and ortho scale are in plane meters (y up).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bpy

import harness

lib_path, rig, cid, out, cx, cy, scale, w, h = sys.argv[sys.argv.index("--") + 1:]
harness.load_nirik()
from nirik.bridge import rig_build  # noqa: E402
from nirik.core import library  # noqa: E402

scene = harness.clean()
scene.render.resolution_x, scene.render.resolution_y = int(w), int(h)
scene.eevee.taa_render_samples = 16
scene.render.film_transparent = False
world = bpy.data.worlds.new("white")
world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
scene.world = world

char = library.load(lib_path)
arm = rig_build.build(char)
rig_build.apply_construction(arm, char, rig, int(cid))

cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = float(scale)
cam.location = (float(cx), -5, float(cy))
cam.rotation_euler = (1.5707963267948966, 0, 0)  # look along +Y at the XZ plane
scene.collection.objects.link(cam)
scene.camera = cam

harness.render(Path(out).stem, 1)
import shutil  # noqa: E402
shutil.copyfile(harness.OUT / f"{Path(out).stem}.png", out)
print("RENDERED", out)
