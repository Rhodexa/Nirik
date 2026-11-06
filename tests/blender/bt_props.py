"""Props from images: sprite sheet split, swapping, rendering, facing the camera."""

import json
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bpy
import numpy as np

import harness

harness.load_nirik()
from nirik.bridge import props, rig_build  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="nirik_props_"))
state = {}


def write_sheet(path):
    """Three pieces of different sizes and colors, plus a faint glow bridge."""
    h, w = 200, 300
    rgba = np.zeros((h, w, 4), np.float32)
    for (x0, y0, x1, y1), color in (((20, 20, 80, 90), (1, 0, 0)), ((150, 30, 270, 80), (0, 1, 0)),
                                    ((40, 120, 100, 190), (0, 0, 1))):
        rgba[y0:y1, x0:x1, :3] = color
        rgba[y0:y1, x0:x1, 3] = 1
    rgba[50:60, 80:150, 3] = 0.15  # glow between the top pieces must not merge them
    props._save_rgba(path, rgba)


def test_import_prop_operator_splits_sheet():
    harness.clean()
    sheet = TMP / "sheet.png"
    write_sheet(sheet)
    bpy.ops.wm.save_as_mainfile(filepath=str(TMP / "scene.blend"))
    assert bpy.ops.nirik.import_prop(filepath=str(sheet), height=0.5) == {"FINISHED"}
    data = json.loads((TMP / "library" / "sheet" / "character.json").read_text())
    assert len(data["drawings"]) == 3
    arm = bpy.context.active_object
    assert arm["nirik_library"].endswith("library/sheet")
    state["arm"] = arm


def _render(name):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = 96
    scene.render.film_transparent = True
    cam = scene.camera
    if cam is None:
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.data.type, cam.data.ortho_scale = "ORTHO", 1.0
    cam.location, cam.rotation_euler = (0, -5, 0), (math.pi / 2, 0, 0)
    return harness.render(name, 1)[1]


def test_drawings_swap_and_render_with_their_color():
    arm = state["arm"]
    from nirik.ui import character_for
    char = character_for(arm)
    colors = []
    for drawing in (1, 2, 3):
        rig_build.set_drawing(arm, char, "Prop.Art", drawing)
        px = _render(f"prop_{drawing}")
        opaque = px[px[..., 3] > 0.9]
        assert len(opaque), f"drawing {drawing} renders empty"
        colors.append(int(np.argmax(opaque[:, :3].mean(axis=0))))
    assert colors == [0, 1, 2]  # red, green, blue in reading order


def test_two_instances_show_different_drawings():
    # Tiles are shared by every puppet of a library: a second envelope must
    # not repaint the first one's tile.
    from nirik.core import library
    from nirik.ui import character_for
    arm = state["arm"]
    char = character_for(arm)
    other = rig_build.build(library.load(char.root))
    rig_build.apply_construction(other, char, "Prop", 0)
    rig_build.set_drawing(arm, char, "Prop.Art", 2)    # green
    rig_build.set_drawing(other, char, "Prop.Art", 3)  # blue
    arm.location, other.location = (-0.25, 0, 0), (0.25, 0, 0)
    px = _render("prop_two")
    half = px.shape[1] // 2
    left, right = px[:, :half], px[:, half:]
    assert int(np.argmax(left[left[..., 3] > 0.9][:, :3].mean(axis=0))) == 1
    assert int(np.argmax(right[right[..., 3] > 0.9][:, :3].mean(axis=0))) == 2
    for ob in [other] + list(other.children):
        bpy.data.objects.remove(ob)
    arm.location = (0, 0, 0)


def test_parts_offer_the_art():
    from nirik.core import controls
    from nirik.ui import character_for
    assert dict(controls.parts(character_for(state["arm"])))["Art"] == ["Prop.Art"]


def test_face_camera_turns_the_prop():
    arm = state["arm"]
    scene = bpy.context.scene
    _render("prop_cam")  # makes sure a camera exists
    scene.camera.location = (3, -3, 0)
    props.face_camera(arm, True)
    bpy.context.view_layer.update()
    facing = arm.matrix_world.to_3x3() @ __import__("mathutils").Vector((0, -1, 0))
    to_cam = (scene.camera.location - arm.matrix_world.translation).normalized()
    assert facing.dot(to_cam) > 0.99
    props.face_camera(arm, False)
    assert props.FACE_CAMERA not in arm.constraints


harness.run(globals())
