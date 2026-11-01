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
    assert arm.pose.bones["ROOT"]["nirik_construction"] == 30
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


def test_swap_updates_without_frame_change():
    # Viewport case: no frame change, only a depsgraph update.
    arm = state["arm"]
    arm.animation_data_clear()
    _select(arm, "Head.MOUTH")
    card = bpy.data.objects["twilight:Head.MOUTH"]
    bpy.context.view_layer.update()
    before = card.evaluated_get(bpy.context.evaluated_depsgraph_get())["nirik_tile"]
    bpy.ops.nirik.step_drawing(step=1, scope="SLOT")
    bpy.context.view_layer.update()
    after = card.evaluated_get(bpy.context.evaluated_depsgraph_get())["nirik_tile"]
    assert after == arm.pose.bones["Head.MOUTH"]["nirik_tile"] != before


def test_iris_outside_eye_is_clipped():
    # Moving the iris far outside the eye must hide it, not sample another tile.
    arm = state["arm"]
    arm.animation_data_clear()
    bpy.ops.object.mode_set(mode="OBJECT")
    scene = bpy.context.scene
    scene.render.resolution_x = scene.render.resolution_y = 256
    cam = bpy.data.objects.get("Cam") or bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    if cam.name not in scene.collection.objects:
        scene.collection.objects.link(cam)
    cam.data.type, cam.data.ortho_scale = "ORTHO", 1.6
    cam.location, cam.rotation_euler = (0, -5, 0.6), (1.5707963, 0, 0)
    scene.camera = cam
    eye = [b for label, bones in __import__("nirik.core.controls", fromlist=["x"]).parts(
        __import__("nirik.ui", fromlist=["x"]).character_for(arm)) if label == "Eye 1" for b in bones]
    cards = [bpy.data.objects[f"twilight:{b}"] for b in eye]
    _, base = harness.render("ops_eye_base", 1)
    for b in eye:
        arm.pose.bones[b].location.x += 0.5  # far outside the eye
    _, moved = harness.render("ops_eye_moved", 1)
    for card in cards:
        card.hide_render = True
    _, hidden = harness.render("ops_eye_hidden", 1)
    for card in cards:
        card.hide_render = False
    for b in eye:
        arm.pose.bones[b].location.x -= 0.5
    assert np.abs(moved - hidden).max() < 0.02, "moved iris leaks outside the eye mask"


def test_parts_panel_selects_bones():
    arm = state["arm"]
    bpy.ops.object.mode_set(mode="POSE")
    assert bpy.ops.nirik.select_part(bones="Head.IRIS,Head.PUPIL") == {"FINISHED"}
    assert {pb.name for pb in arm.pose.bones if pb.select} == {"Head.IRIS", "Head.PUPIL"}


def test_more_parts_reveal_one_hidden_bone_at_a_time():
    arm = state["arm"]
    bpy.ops.object.mode_set(mode="POSE")
    tail, ear = arm.pose.bones["Character.Tail"], arm.pose.bones["Head.EAR"]
    assert tail.hide and ear.hide
    bpy.ops.nirik.select_part(bones="Character.Tail")
    assert not tail.hide and tail.select
    bpy.ops.nirik.select_part(bones="Head.EAR")
    assert tail.hide and not ear.hide and ear.select


def test_wheel_on_non_drawing_part_is_consumed():
    # Body (ROOT) has no drawings: the swap must still run (and cancel) so the
    # wheel event doesn't fall through to timeline scrubbing.
    arm = state["arm"]
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.nirik.select_part(bones="ROOT")
    assert bpy.ops.nirik.step_drawing.poll()
    assert bpy.ops.nirik.step_drawing(step=1) == {"CANCELLED"}


def _fcurves(arm):
    return [fc for layer in arm.animation_data.action.layers for strip in layer.strips
            for bag in strip.channelbags for fc in bag.fcurves]


def test_construction_keys_live_on_visible_bones_and_transforms_stay_smooth():
    arm = state["arm"]
    arm.animation_data_clear()
    scene = bpy.context.scene
    bpy.ops.object.mode_set(mode="POSE")
    scene.tool_settings.use_keyframe_insert_auto = True
    # The animator keys a head move (smooth) ...
    head = arm.pose.bones["Character.=HEADCOMP="]
    for frame, x in ((1, 0.0), (10, 0.1)):
        scene.frame_set(frame)
        head.location.x = x
        head.keyframe_insert("location", frame=frame)
    # ... then swaps constructions and drawings, which key Nirik channels.
    scene.frame_set(5)
    bpy.ops.nirik.step_construction(rig="Character", step=1)
    bpy.ops.nirik.select_part(bones="Head.MOUTH")
    bpy.ops.nirik.step_drawing(step=1)
    paths = {fc.data_path: fc for fc in _fcurves(arm)}
    assert 'pose.bones["ROOT"]["nirik_construction"]' in paths
    assert 'pose.bones["Character.=HEADCOMP="]["nirik_construction"]' in paths
    move = paths['pose.bones["Character.=HEADCOMP="].location']
    assert all(kp.interpolation == "BEZIER" for kp in move.keyframe_points)
    scene.tool_settings.use_keyframe_insert_auto = False


def test_rebuild_follows_retimed_construction_keys():
    arm = state["arm"]
    char = __import__("nirik.ui", fromlist=["x"]).character_for(arm)
    arm.animation_data_clear()
    rig_build.apply_construction(arm, char, "Character", 0, frame=1)
    rig_build.apply_construction(arm, char, "Character", 30, frame=10)
    scene = bpy.context.scene

    def sockets_at(frame):
        scene.frame_set(frame)
        return {pb.name: tuple(round(v, 5) for v in pb.location)
                for pb in arm.pose.bones if pb.name.endswith(".SOCKET")}

    before, after = sockets_at(1), sockets_at(10)
    bone = next(n for n in before if before[n] != after[n])

    def neck_at(frame):
        return sockets_at(frame)[bone]

    pose30 = neck_at(10)
    # Retime: move the visible construction key from frame 10 to 20, then sync.
    fc = next(f for f in _fcurves(arm) if f.data_path == 'pose.bones["ROOT"]["nirik_construction"]')
    fc.keyframe_points[1].co.x = 20
    assert neck_at(15) == pose30  # stale: hidden sockets still switch at 10
    assert bpy.ops.nirik.rebuild() == {"FINISHED"}
    assert neck_at(15) != pose30 and neck_at(20) == pose30


def test_card_origins_share_one_line():
    # EEVEE sorts transparent objects by origin; per-part origins break the
    # layering as soon as the camera turns.
    cards = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("twilight:")]
    xs = {round(o.matrix_world.translation.x, 6) for o in cards}
    zs = {round(o.matrix_world.translation.z, 6) for o in cards}
    assert xs == {0.0} and zs == {0.0}
    assert len({round(o.matrix_world.translation.y, 7) for o in cards}) == len(cards)


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
