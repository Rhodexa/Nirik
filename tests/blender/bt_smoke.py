"""Smoke tests: the add-on loads, color management works, and an animated
object property reaches the shader per frame in a headless render."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bpy
from bpy_extras import anim_utils

import harness


def test_nirik_registers_and_reloads():
    nirik = harness.load_nirik()
    assert hasattr(bpy.types, "NIRIK_PT_main")
    nirik.unregister()
    assert not hasattr(bpy.types, "NIRIK_PT_main")
    nirik.register()
    assert hasattr(bpy.types, "NIRIK_PT_main")


def test_agx_available():
    # Fails when OCIO falls back to built-in config (see devtools/blender_env.py).
    scene = harness.clean()
    scene.view_settings.view_transform = "AgX"


def _card_with_keyed_drawing():
    scene = harness.clean()
    scene.render.resolution_x = scene.render.resolution_y = 64

    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 2.5
    cam.location = (0, 0, 5)
    scene.collection.objects.link(cam)
    scene.camera = cam

    mesh = bpy.data.meshes.new("Card")
    mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    card = bpy.data.objects.new("Card", mesh)
    scene.collection.objects.link(card)

    mat = bpy.data.materials.new("Card")
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "OBJECT"
    attr.attribute_name = "drawing"
    emit = nodes.new("ShaderNodeEmission")
    out = nodes.new("ShaderNodeOutputMaterial")
    links.new(attr.outputs["Color"], emit.inputs["Color"])
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    mesh.materials.append(mat)

    for frame, value in ((1, 0), (2, 1)):
        card["drawing"] = value
        card.keyframe_insert('["drawing"]', frame=frame)

    # Blender 5.x: F-curves live in the action's layer/strip channelbag.
    adt = card.animation_data
    bag = anim_utils.action_get_channelbag_for_slot(adt.action, adt.action_slot)
    for fc in bag.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"
    return scene


def test_object_attribute_drives_shader_per_frame():
    _card_with_keyed_drawing()
    _, f1 = harness.render("smoke_card_f1", 1)
    path, f2 = harness.render("smoke_card_f2", 2)
    center = (32, 32)
    assert f1[center][:3].max() < 0.05, f1[center]
    assert f2[center][:3].min() > 0.95, f2[center]
    harness.assert_golden("smoke_card_f2", path)


harness.run(globals())
