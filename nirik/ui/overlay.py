"""Viewport overlay for Nirik puppets in Pose mode.

For each selected control: a box around the artwork it carries (tight to the
drawings' visible pixels, not the cards' padded canvases), its pivot, and its
name. Toggled by the header button; hidden with Blender's overlays.
"""

from __future__ import annotations

import blf
import bpy
import gpu
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ..bridge import picking, rig_build

COLOR = (1.0, 0.62, 0.1, 1.0)        # Blender's selection orange
COLOR_ACTIVE = (1.0, 0.85, 0.4, 1.0)
PIVOT_SIZE = 7                       # pixels

_bbox_cache: dict[tuple[str, int], tuple[float, float, float, float] | None] = {}
_handle = None


def artwork_uv_box(char, drawing: int):
    """(u0, v0, u1, v1) of a drawing's visible pixels, or None if it's empty."""
    key = (str(char.root), drawing)
    if key not in _bbox_cache:
        alpha = picking.drawing_alpha(char, drawing)
        ys, xs = np.nonzero(alpha > 0.05)
        _bbox_cache[key] = None if not len(xs) else (
            xs.min() / alpha.shape[1], ys.min() / alpha.shape[0],
            (xs.max() + 1) / alpha.shape[1], (ys.max() + 1) / alpha.shape[0])
    return _bbox_cache[key]


def artwork_corners(arm, char, bone: str, depsgraph) -> list[Vector]:
    """World-space corners of the visible artwork of every part `bone` carries."""
    corners = []
    for slot in rig_build.carried_slots(arm, char, bone):
        drawing = arm.pose.bones[slot]["nirik_drawing"]
        card = bpy.data.objects.get(f"{char.name}:{slot}")
        box = artwork_uv_box(char, drawing) if drawing else None
        if card is None or box is None:
            continue
        ev = card.evaluated_get(depsgraph)
        v0, v1, _, v3 = (ev.matrix_world @ v.co for v in ev.data.vertices)
        u0, w0, u1, w1 = box
        for u, w in ((u0, w0), (u1, w0), (u1, w1), (u0, w1)):
            corners.append(v0 + (v1 - v0) * u + (v3 - v0) * w)
    return corners


def _lines(coords, color, width=1.5):
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.line_width_set(width)
    gpu.state.blend_set("ALPHA")
    shader.bind()
    shader.uniform_float("color", color)
    batch_for_shader(shader, "LINES", {"pos": coords}).draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")


def draw():
    context = bpy.context
    space = context.space_data
    if not context.window_manager.nirik_overlay or not space.overlay.show_overlays:
        return
    from . import character_for, nirik_armature, part_label
    arm = nirik_armature(context)
    if arm is None or context.mode != "POSE":
        return
    char = character_for(arm)
    region, rv3d = context.region, context.region_data
    depsgraph = context.evaluated_depsgraph_get()
    active = context.active_pose_bone
    slots = char.all_slots()

    for pb in arm.pose.bones:
        if not pb.select or pb.name not in slots and pb.name != "ROOT":
            continue
        color = COLOR_ACTIVE if active is not None and pb.name == active.name else COLOR
        points = [location_3d_to_region_2d(region, rv3d, c)
                  for c in artwork_corners(arm, char, pb.name, depsgraph)]
        points = [p for p in points if p is not None]
        if points:
            x0, y0 = min(p.x for p in points), min(p.y for p in points)
            x1, y1 = max(p.x for p in points), max(p.y for p in points)
            _lines([(x0, y0), (x1, y0), (x1, y0), (x1, y1), (x1, y1), (x0, y1), (x0, y1), (x0, y0)], color)
            if pb.name == "ROOT":
                name = "Body"
            elif slots[pb.name].child_rig:
                name = slots[pb.name].child_rig  # e.g. "Head"
            else:
                name = part_label(arm, char, pb.name)
            blf.size(0, 12)
            blf.color(0, *color)
            blf.position(0, x0 + 2, y1 + 4, 0)
            blf.draw(0, name)
        pivot = location_3d_to_region_2d(region, rv3d, arm.matrix_world @ pb.head)
        if pivot is not None:
            s = PIVOT_SIZE
            _lines([(pivot.x - s, pivot.y), (pivot.x + s, pivot.y),
                    (pivot.x, pivot.y - s), (pivot.x, pivot.y + s)], color, 2.0)


def header_toggle(self, context):
    if any("nirik_library" in ob for ob in context.scene.objects):
        self.layout.prop(context.window_manager, "nirik_overlay", text="", icon="OUTLINER_OB_ARMATURE")


def register():
    global _handle
    bpy.types.WindowManager.nirik_overlay = bpy.props.BoolProperty(
        name="Nirik Overlay", description="Show selected parts' outlines, pivots and names",
        default=True)
    _handle = bpy.types.SpaceView3D.draw_handler_add(draw, (), "WINDOW", "POST_PIXEL")
    bpy.types.VIEW3D_HT_header.append(header_toggle)


def unregister():
    global _handle
    bpy.types.VIEW3D_HT_header.remove(header_toggle)
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, "WINDOW")
        _handle = None
    del bpy.types.WindowManager.nirik_overlay
