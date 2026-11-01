"""Operator-level checks against a real library (path after --)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bpy
import numpy as np

import harness

LIB = sys.argv[sys.argv.index("--") + 1]
harness.load_nirik()
from nirik.bridge import rig_build  # noqa: E402

state = {}


def test_load_character():
    harness.clean()
    assert bpy.ops.nirik.load_character(directory=LIB) == {"FINISHED"}
    arm = bpy.context.active_object
    assert arm.type == "ARMATURE" and "nirik_library" in arm
    state["arm"] = arm


def test_step_construction_moves_sockets():
    arm = state["arm"]

    def sockets():
        return [tuple(pb.location) + tuple(pb.rotation_euler) + tuple(pb.scale)
                for pb in arm.pose.bones if pb.name.endswith(".SOCKET")]

    before = sockets()
    assert bpy.ops.nirik.step_construction(rig="Character", step=30) == {"FINISHED"}
    assert arm["nirik_construction"]["Character"] == 30
    assert sockets() != before


def _select(arm, bone):
    bpy.ops.object.mode_set(mode="POSE")
    arm.data.bones.active = arm.data.bones[bone]


def test_step_drawing_grows_palette_and_keys():
    arm = state["arm"]
    scene = bpy.context.scene
    scene.tool_settings.use_keyframe_insert_auto = True
    scene.frame_set(12)
    _select(arm, "Head.MOUTH")
    pal_before = len(rig_build.palette(arm, "Head.MOUTH"))
    for _ in range(3):
        assert bpy.ops.nirik.step_drawing(step=1) == {"FINISHED"}
    pb = arm.pose.bones["Head.MOUTH"]
    assert pb["nirik_drawing"] != 0
    assert len(rig_build.palette(arm, "Head.MOUTH")) > pal_before
    image = bpy.data.images[f"nirik:twilight:Head.MOUTH"]
    assert len(image.tiles) == len(rig_build.palette(arm, "Head.MOUTH"))
    fcurves = [fc for layer in arm.animation_data.action.layers for strip in layer.strips
               for bag in strip.channelbags for fc in bag.fcurves]
    keyed = [fc for fc in fcurves if fc.data_path == 'pose.bones["Head.MOUTH"]["nirik_drawing"]']
    assert keyed and all(kp.interpolation == "CONSTANT" for kp in keyed[0].keyframe_points)


def test_swapped_drawing_renders():
    # Two different mouths must render differently: the new tile is live.
    arm = state["arm"]
    arm.animation_data_clear()  # keyed drawings would override unkeyed swaps on frame change
    bpy.ops.object.mode_set(mode="OBJECT")
    scene = bpy.context.scene
    scene.render.resolution_x = scene.render.resolution_y = 256
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 1.6
    cam.location, cam.rotation_euler = (0, -5, 0.6), (1.5707963, 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.frame_set(1)
    _, a = harness.render("ops_mouth_a", 1)
    bpy.ops.object.mode_set(mode="POSE")
    _select(arm, "Head.MOUTH")
    scene.tool_settings.use_keyframe_insert_auto = False
    for _ in range(5):
        bpy.ops.nirik.step_drawing(step=1)
    bpy.ops.object.mode_set(mode="OBJECT")
    _, b = harness.render("ops_mouth_b", 1)
    assert np.abs(a - b).max() > 0.2


harness.run(globals())
