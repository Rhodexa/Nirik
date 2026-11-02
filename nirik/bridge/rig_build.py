"""Build a Blender puppet from a character library, and pose it.

Per slot the armature gets a bone chain (all bones rest at the origin, so a
pose is exactly the slot's 2D transform in the plane's local XY):

  <slot>.SOCKET   compiler: location, rotation, non-uniform scale of the socket
  <slot>.SKEW     compiler: second rotation; with SOCKET's scale this yields shear
  <slot>          animator: the control (CTRL) bone

Drawable slots get a card: a fixed quad covering the slot's canvas, deformed
by its CTRL bone through an Armature modifier. Every card's origin sits on the
armature's origin (offset toward the camera by draw order), because EEVEE
sorts transparent objects by origin; per-bone origins reorder parts as soon
as the camera turns. Its material samples
the slot's tiled image (the palette: only drawings in use, one UDIM tile each).

Bone properties are the animation interface; cards follow through drivers:
  CTRL["nirik_drawing"]   drawing ID (stable, authoring)
  CTRL["nirik_tile"]      palette index, -1 = empty (compiled)
  SOCKET["nirik_color"]   color transform: mult RGBA + offset RGBA (0..255)
"""

from __future__ import annotations

import os
from pathlib import Path

import bpy
from bpy_extras import anim_utils

from ..core import controls
from ..core import library as L

UNITS_PER_METER = 300.0   # library units (Flash px) per meter: ponies ~1.1 m tall
# Meters toward the camera per draw-order step. EEVEE sorts blended surfaces by
# object origin; all cards share one origin line, so any step orders them, and
# a tiny one keeps perspective parallax between layers invisible.
ORDER_STEP = 0.00001
BONE_LENGTH = 0.05
IDENTITY_COLOR = (1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0)
UDIM_COLUMNS = 10
SIDE_AUTO, SIDE_NEAR, SIDE_FAR = 0, 1, 2


def safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)


# ── palettes (tiled images) ──────────────────────────────────────────────────

def palette_dir(char: L.Character, slot: str) -> Path:
    return char.root / ".udim" / safe(slot)


def palette(arm: bpy.types.Object, slot: str) -> list[int]:
    return list(arm["nirik_palettes"].get(slot, []))


def ensure_in_palette(arm: bpy.types.Object, char: L.Character, slot: str, drawing: int) -> int:
    """Palette index of `drawing` in `slot`, adding a UDIM tile if needed."""
    pal = palette(arm, slot)
    if drawing in pal:
        return pal.index(drawing)
    index = len(pal)
    tile = 1001 + index
    folder = palette_dir(char, slot)
    folder.mkdir(parents=True, exist_ok=True)
    link = folder / f"t.{tile}.png"
    if link.is_symlink() or link.exists():
        link.unlink()
    os.symlink(char.drawing_path(drawing), link)
    pal.append(drawing)
    palettes = arm["nirik_palettes"]
    palettes[slot] = pal

    image = bpy.data.images.get(f"nirik:{char.name}:{slot}")
    if image is not None:
        if not image.tiles.get(tile):
            image.tiles.new(tile_number=tile)
        image.reload()
    return index


def palette_image(char: L.Character, slot: str) -> bpy.types.Image:
    name = f"nirik:{char.name}:{slot}"
    image = bpy.data.images.get(name)
    if image is None:
        folder = palette_dir(char, slot)
        image = bpy.data.images.load(str(folder / "t.1001.png"), check_existing=False)
        image.name = name
        image.source = "TILED"
        image.filepath = str(folder / "t.<UDIM>.png")
        image.alpha_mode = "STRAIGHT"
        # Raw sRGB values: color transforms apply in sRGB like Flash's, then
        # the shader converts to linear (see srgb_to_linear_group).
        image.colorspace_settings.name = "Non-Color"
        image.reload()
    return image


# ── materials ────────────────────────────────────────────────────────────────

def srgb_to_linear_group() -> bpy.types.ShaderNodeTree:
    """Node group: exact sRGB transfer curve, per channel."""
    name = "nirik: sRGB to linear"
    group = bpy.data.node_groups.get(name)
    if group is not None:
        return group
    group = bpy.data.node_groups.new(name, "ShaderNodeTree")
    group.interface.new_socket("Color", in_out="INPUT", socket_type="NodeSocketVector")
    group.interface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketVector")
    nodes, links = group.nodes, group.links
    gin, gout = nodes.new("NodeGroupInput"), nodes.new("NodeGroupOutput")
    split, join = nodes.new("ShaderNodeSeparateXYZ"), nodes.new("ShaderNodeCombineXYZ")
    links.new(gin.outputs[0], split.inputs[0])
    for i in range(3):
        c = split.outputs[i]
        lo = _math(nodes, links, "DIVIDE", c, value=12.92)
        hi = _math(nodes, links, "POWER",
                   _math(nodes, links, "DIVIDE", _math(nodes, links, "ADD", c, value=0.055), value=1.055),
                   value=2.4)
        above = _math(nodes, links, "GREATER_THAN", c, value=0.04045)
        mixed = _math(nodes, links, "ADD", lo,
                      _math(nodes, links, "MULTIPLY", above, _math(nodes, links, "SUBTRACT", hi, lo)))
        links.new(mixed, join.inputs[i])
    links.new(join.outputs[0], gout.inputs[0])
    return group


def _tile_uv(nodes, links, uv_socket, tile_socket, size):
    """clamp(uv, half texel) + (tile % 10, floor(tile / 10))

    The half-texel inset keeps linear filtering from blending in texels
    across the tile border, i.e. from the neighboring drawing.
    """
    hx, hy = 0.5 / size[0], 0.5 / size[1]
    lo = nodes.new("ShaderNodeVectorMath")
    lo.operation = "MAXIMUM"
    links.new(uv_socket, lo.inputs[0])
    lo.inputs[1].default_value = (hx, hy, 0)
    hi = nodes.new("ShaderNodeVectorMath")
    hi.operation = "MINIMUM"
    links.new(lo.outputs[0], hi.inputs[0])
    hi.inputs[1].default_value = (1 - hx, 1 - hy, 0)
    uv_socket = hi.outputs[0]
    mod = nodes.new("ShaderNodeMath")
    mod.operation = "MODULO"
    mod.inputs[1].default_value = UDIM_COLUMNS
    links.new(tile_socket, mod.inputs[0])
    div = nodes.new("ShaderNodeMath")
    div.operation = "DIVIDE"
    div.inputs[1].default_value = UDIM_COLUMNS
    links.new(tile_socket, div.inputs[0])
    floor = nodes.new("ShaderNodeMath")
    floor.operation = "FLOOR"
    links.new(div.outputs[0], floor.inputs[0])
    offset = nodes.new("ShaderNodeCombineXYZ")
    links.new(mod.outputs[0], offset.inputs[0])
    links.new(floor.outputs[0], offset.inputs[1])
    add = nodes.new("ShaderNodeVectorMath")
    add.operation = "ADD"
    links.new(uv_socket, add.inputs[0])
    links.new(offset.outputs[0], add.inputs[1])
    return add.outputs[0]


def _attr(nodes, name):
    n = nodes.new("ShaderNodeAttribute")
    n.attribute_type = "OBJECT"
    n.attribute_name = name
    return n


def _math(nodes, links, op, a, b=None, value=None):
    n = nodes.new("ShaderNodeMath")
    n.operation = op
    links.new(a, n.inputs[0])
    if b is not None:
        links.new(b, n.inputs[1])
    elif value is not None:
        n.inputs[1].default_value = value
    return n.outputs[0]


def canvas_pixels(char: L.Character, slot: L.Slot) -> tuple[int, int]:
    x0, y0, x1, y1 = slot.canvas
    return max(1, round((x1 - x0) * char.ppu)), max(1, round((y1 - y0) * char.ppu))


def build_material(char: L.Character, slot: L.Slot, image, mask_image=None, mask_empty=None,
                   mask_slot: L.Slot | None = None):
    mat = bpy.data.materials.new(f"nirik:{char.name}:{slot.name}")
    mat.surface_render_method = "BLENDED"
    mat.use_transparency_overlap = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()

    uv = nodes.new("ShaderNodeUVMap")
    tile = _attr(nodes, "nirik_tile")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.extension = "CLIP"
    tex.interpolation = "Linear"
    links.new(_tile_uv(nodes, links, uv.outputs["UV"], tile.outputs["Fac"], canvas_pixels(char, slot)),
              tex.inputs["Vector"])

    # Color transform: rgb * mult + off / 255, alpha * mult_a + off_a / 255.
    mult, off = _attr(nodes, "nirik_mult"), _attr(nodes, "nirik_off")
    scaled = nodes.new("ShaderNodeVectorMath")
    scaled.operation = "MULTIPLY"
    links.new(tex.outputs["Color"], scaled.inputs[0])
    links.new(mult.outputs["Vector"], scaled.inputs[1])
    off255 = nodes.new("ShaderNodeVectorMath")
    off255.operation = "SCALE"
    links.new(off.outputs["Vector"], off255.inputs[0])
    off255.inputs["Scale"].default_value = 1 / 255
    rgb = nodes.new("ShaderNodeVectorMath")
    rgb.operation = "ADD"
    links.new(scaled.outputs[0], rgb.inputs[0])
    links.new(off255.outputs[0], rgb.inputs[1])

    alpha = _math(nodes, links, "MULTIPLY", tex.outputs["Alpha"], mult.outputs["Alpha"])
    alpha = _math(nodes, links, "ADD", alpha, _math(nodes, links, "DIVIDE", off.outputs["Alpha"], value=255))
    visible = _math(nodes, links, "GREATER_THAN", tile.outputs["Fac"], value=-0.5)
    alpha = _math(nodes, links, "MULTIPLY", alpha, visible)

    if mask_image is not None:
        coords = nodes.new("ShaderNodeTexCoord")
        coords.object = mask_empty
        mask_tile = _attr(nodes, "nirik_mask_tile")
        mtex = nodes.new("ShaderNodeTexImage")
        mtex.image = mask_image
        mtex.extension = "CLIP"
        links.new(_tile_uv(nodes, links, coords.outputs["Object"], mask_tile.outputs["Fac"],
                           canvas_pixels(char, mask_slot)), mtex.inputs["Vector"])
        mask_visible = _math(nodes, links, "GREATER_THAN", mask_tile.outputs["Fac"], value=-0.5)
        # Outside the mask canvas the lookup would land on a neighboring tile
        # (another drawing): treat it as fully masked instead.
        split = nodes.new("ShaderNodeSeparateXYZ")
        links.new(coords.outputs["Object"], split.inputs[0])
        for axis in (0, 1):
            c = split.outputs[axis]
            inside = _math(nodes, links, "MULTIPLY", _math(nodes, links, "GREATER_THAN", c, value=0.0),
                           _math(nodes, links, "LESS_THAN", c, value=1.0))
            mask_visible = _math(nodes, links, "MULTIPLY", mask_visible, inside)
        alpha = _math(nodes, links, "MULTIPLY", alpha, _math(nodes, links, "MULTIPLY",
                                                             mtex.outputs["Alpha"], mask_visible))
    alpha = _math(nodes, links, "MINIMUM", _math(nodes, links, "MAXIMUM", alpha, value=0.0), value=1.0)
    # Texture filtering leaves near-zero alpha around card edges; drop it.
    alpha = _math(nodes, links, "MULTIPLY", alpha, _math(nodes, links, "GREATER_THAN", alpha, value=1 / 255))

    emit = nodes.new("ShaderNodeEmission")
    clamp = nodes.new("ShaderNodeVectorMath")
    clamp.operation = "MINIMUM"
    links.new(rgb.outputs[0], clamp.inputs[0])
    clamp.inputs[1].default_value = (1, 1, 1)
    to_linear = nodes.new("ShaderNodeGroup")
    to_linear.node_tree = srgb_to_linear_group()
    links.new(clamp.outputs[0], to_linear.inputs[0])
    links.new(to_linear.outputs[0], emit.inputs["Color"])
    clear = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(alpha, mix.inputs["Fac"])
    links.new(clear.outputs[0], mix.inputs[1])
    links.new(emit.outputs[0], mix.inputs[2])
    out = nodes.new("ShaderNodeOutputMaterial")
    links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


# ── drivers ──────────────────────────────────────────────────────────────────

def _drive(obj, prop: str, index: int, arm, bone: str, bone_prop: str, bone_index: int | None = None,
           expression: str = "v", extra: dict[str, str] | None = None):
    """Drive obj[prop] from a bone property. `expression` must stay a simple
    expression (arithmetic, comparisons, `a if c else b`): those evaluate
    without Python, so renders never need scripts enabled."""
    path = f'["{prop}"]' if prop != "location" else "location"
    fc = obj.driver_add(path, index) if index >= 0 else obj.driver_add(path)
    # Blender seeds some driver curves (e.g. location) with keyframes that
    # remap and clamp the driver's output; drivers here must pass through.
    while fc.keyframe_points:
        fc.keyframe_points.remove(fc.keyframe_points[0])
    while fc.modifiers:
        fc.modifiers.remove(fc.modifiers[0])
    drv = fc.driver
    drv.type = "SCRIPTED"
    suffix = f"[{bone_index}]" if bone_index is not None else ""
    for name, data_path in {"v": f'pose.bones["{bone}"]["{bone_prop}"]{suffix}', **(extra or {})}.items():
        var = drv.variables.new()
        var.name = name
        var.targets[0].id = arm
        var.targets[0].data_path = data_path
    drv.expression = expression


# ── build ────────────────────────────────────────────────────────────────────

def build(char: L.Character, collection=None, units_per_meter: float = UNITS_PER_METER) -> bpy.types.Object:
    scene = bpy.context.scene
    coll = collection
    if coll is None:
        coll = bpy.data.collections.new(f"nirik:{char.name}")
        scene.collection.children.link(coll)

    arm_data = bpy.data.armatures.new(char.name)
    arm = bpy.data.objects.new(char.name, arm_data)
    coll.objects.link(arm)
    arm["nirik_library"] = str(char.root)
    arm["nirik_units_per_meter"] = units_per_meter
    arm["nirik_palettes"] = {}

    slots = char.all_slots()
    holder = {s.child_rig: s.name for s in slots.values() if s.child_rig}  # rig -> holding slot

    # Bones: all rest at the origin pointing +Z (local X = world X, local Y = up).
    view_layer = bpy.context.view_layer
    view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    internal = arm_data.collections.new("Nirik Internal")
    main = arm_data.collections.new("Controls")
    more = arm_data.collections.new("More Controls")
    main_bones = controls.main_bones(char)
    root = arm_data.edit_bones.new("ROOT")
    root.head, root.tail = (0, 0, 0), (0, 0, BONE_LENGTH * 3)
    main.assign(root)
    for rig in char.rigs.values():
        for s in rig.slots:
            parent_name = holder.get(rig.name, "ROOT")
            sock = arm_data.edit_bones.new(f"{s.name}.SOCKET")
            skew = arm_data.edit_bones.new(f"{s.name}.SKEW")
            ctrl = arm_data.edit_bones.new(s.name)
            for b in (sock, skew, ctrl):
                b.head, b.tail, b.roll = (0, 0, 0), (0, 0, BONE_LENGTH), 0
            internal.assign(sock)
            internal.assign(skew)
            (main if s.name in main_bones else more).assign(ctrl)
            sock.parent = arm_data.edit_bones[parent_name] if parent_name != "ROOT" else root
            skew.parent, ctrl.parent = sock, skew
    bpy.ops.object.mode_set(mode="OBJECT")
    internal.is_visible = False

    holders = set(holder.values())
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        if pb.name == "ROOT" or pb.name in holders:
            pb["nirik_construction"] = 0
        # Extra controls stay hidden one by one; the panel reveals the one you pick.
        pb.hide = pb.name in slots and pb.name not in main_bones
        if pb.name in slots:
            pb["nirik_drawing"] = 0
            pb["nirik_tile"] = -1
            pb["nirik_layer"] = 0.0  # draw-order offset, in layers
            pb["nirik_side"] = SIDE_AUTO
        elif pb.name.endswith(".SOCKET"):
            pb["nirik_color"] = list(IDENTITY_COLOR)

    # Mask empties: object coordinates == mask canvas UVs.
    mask_empties = {}
    for s in slots.values():
        if s.mask and s.canvas:
            empty = bpy.data.objects.new(f"nirik:{char.name}:{s.name}", None)
            coll.objects.link(empty)
            _parent_to_bone(empty, arm, s.name)
            x0, y0, x1, y1 = s.canvas
            empty.location = (x0 / units_per_meter, -y1 / units_per_meter - BONE_LENGTH, 0)
            empty.scale = ((x1 - x0) / units_per_meter, (y1 - y0) / units_per_meter, 1)
            empty.hide_select = True
            mask_empties[s.name] = empty

    far = char.far_color() or IDENTITY_COLOR

    # Cards, back to front.
    for order, name in enumerate(char.draw_order()):
        s = slots[name]
        x0, y0, x1, y1 = s.canvas
        mesh = bpy.data.meshes.new(f"nirik:{char.name}:{name}")
        px0, px1 = x0 / units_per_meter, x1 / units_per_meter
        py0, py1 = -y1 / units_per_meter, -y0 / units_per_meter  # y up: bottom, top
        # Rest geometry in armature space: bones rest at the origin with local
        # XY = world XZ, so plane (x, y) sits at (x, 0, y).
        mesh.from_pydata([(px0, 0, py0), (px1, 0, py0), (px1, 0, py1), (px0, 0, py1)], [], [(0, 1, 2, 3)])
        uv = mesh.uv_layers.new(name="UVMap")
        for loop, co in zip(uv.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
            loop.uv = co
        card = bpy.data.objects.new(f"{char.name}:{name}", mesh)
        coll.objects.link(card)
        card.parent = arm
        _drive(card, "location", 1, arm, name, "nirik_layer",
               expression=f"-({order} + v) * {ORDER_STEP!r}")
        card["nirik_order"] = order
        group = card.vertex_groups.new(name=name)
        group.add(range(4), 1.0, "REPLACE")
        mod = card.modifiers.new("Nirik", "ARMATURE")
        mod.object = arm
        card.hide_select = True
        card["nirik_tile"] = -1
        card["nirik_mult"] = [1.0, 1.0, 1.0, 1.0]
        card["nirik_off"] = [0.0, 0.0, 0.0, 0.0]
        _drive(card, "nirik_tile", -1, arm, name, "nirik_tile")
        for i in range(4):
            # Side: auto = the stock pose's color, near = none, far = the
            # character's far-limb darkening.
            side = {"s": f'pose.bones["{name}"]["nirik_side"]'}
            _drive(card, "nirik_mult", i, arm, f"{name}.SOCKET", "nirik_color", i,
                   expression=f"v if s == {SIDE_AUTO} else (1.0 if s == {SIDE_NEAR} else {far[i]!r})",
                   extra=side)
            _drive(card, "nirik_off", i, arm, f"{name}.SOCKET", "nirik_color", 4 + i,
                   expression=f"v if s == {SIDE_AUTO} else (0.0 if s == {SIDE_NEAR} else {far[4 + i]!r})",
                   extra=side)

        mask_image = mask_empty = None
        if s.masked_by:
            card["nirik_mask_tile"] = -1
            _drive(card, "nirik_mask_tile", -1, arm, s.masked_by, "nirik_tile")
            mask_image = _palette_image_seeded(arm, char, s.masked_by)
            mask_empty = mask_empties[s.masked_by]
        image = _palette_image_seeded(arm, char, name)
        mesh.materials.append(build_material(char, s, image, mask_image, mask_empty,
                                             slots.get(s.masked_by)))
    return arm


def _palette_image_seeded(arm, char, slot: str):
    """Palette image for `slot`; seeds tile 1001 with the slot's first drawing."""
    if not palette(arm, slot):
        drawings = char.slot_drawings(slot)
        if drawings:
            ensure_in_palette(arm, char, slot, drawings[0])
    return palette_image(char, slot)


def _parent_to_bone(obj, arm, bone: str):
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone


# ── posing ───────────────────────────────────────────────────────────────────
#
# Authoring channels (visible, what the animator keys and retimes):
#   <control>["nirik_construction"]  on ROOT (root rig) or the slot holding a child rig
#   <slot>["nirik_drawing"]
# Compiled channels (hidden, regenerated by rebuild_compiled):
#   SOCKET/SKEW transforms and colors, <slot>["nirik_tile"]

def construction_bone(char: L.Character, rig: str) -> str:
    if rig == char.root_rig:
        return "ROOT"
    return next(s.name for s in char.all_slots().values() if s.child_rig == rig)


def current_construction(arm, char: L.Character, rig: str) -> int:
    return arm.pose.bones[construction_bone(char, rig)].get("nirik_construction", 0)


def set_drawing(arm, char: L.Character, slot: str, drawing: int):
    pb = arm.pose.bones[slot]
    pb["nirik_drawing"] = drawing
    pb["nirik_tile"] = ensure_in_palette(arm, char, slot, drawing) if drawing else -1
    # Custom properties don't notify the depsgraph; without this the cards'
    # drivers keep showing the old drawing until something else updates.
    arm.update_tag()


def key_drawing(arm, slot: str, frame: int):
    pb = arm.pose.bones[slot]
    pb.keyframe_insert('["nirik_drawing"]', frame=frame)
    pb.keyframe_insert('["nirik_tile"]', frame=frame)
    make_constant(arm)


def _apply_sockets(arm, char: L.Character, rig: str, construction: int, frame: int | None):
    """Socket transforms and colors of one rig's slots (no drawings, no children)."""
    upm = arm["nirik_units_per_meter"]
    cons = char.rigs[rig].constructions[construction]
    for s in char.rigs[rig].slots:
        entry = cons.slots.get(s.name)
        if entry is None:
            continue
        sock, skew = arm.pose.bones[f"{s.name}.SOCKET"], arm.pose.bones[f"{s.name}.SKEW"]
        pair = L.socket_bones(L.to_plane(entry.matrix, upm))
        sock.location = (pair.location[0], pair.location[1], 0)
        sock.rotation_euler = (0, 0, pair.rot_a)
        sock.scale = (pair.scale[0], pair.scale[1], 1)
        skew.rotation_euler = (0, 0, pair.rot_b)
        sock["nirik_color"] = list(entry.color or IDENTITY_COLOR)
        if frame is not None:
            for path in ("location", "rotation_euler", "scale", '["nirik_color"]'):
                sock.keyframe_insert(path, frame=frame)
            skew.keyframe_insert("rotation_euler", frame=frame)


def apply_construction(arm, char: L.Character, rig: str, construction: int, frame: int | None = None):
    """Pose a library construction: sockets, the stock drawings, and the child
    rigs' paired constructions. With `frame`, everything is keyed there."""
    control = arm.pose.bones[construction_bone(char, rig)]
    control["nirik_construction"] = construction
    if frame is not None:
        control.keyframe_insert('["nirik_construction"]', frame=frame)
    _apply_sockets(arm, char, rig, construction, frame)
    cons = char.rigs[rig].constructions[construction]
    for s in char.rigs[rig].slots:
        entry = cons.slots.get(s.name)
        if s.child_rig:
            if entry is not None and entry.construction is not None:
                apply_construction(arm, char, s.child_rig, entry.construction, frame)
            continue
        set_drawing(arm, char, s.name, entry.drawing if entry else 0)
        if frame is not None:
            key_drawing(arm, s.name, frame)
    if frame is not None:
        make_constant(arm)
    arm.update_tag()


def _channelbag(arm):
    adt = arm.animation_data
    if not adt or not adt.action:
        return None
    return anim_utils.action_get_channelbag_for_slot(adt.action, adt.action_slot)


def _bone_of(data_path: str) -> str | None:
    if data_path.startswith('pose.bones["'):
        return data_path[len('pose.bones["'):].split('"]', 1)[0]
    return None


def is_compiled(data_path: str) -> bool:
    bone = _bone_of(data_path) or ""
    return bone.endswith((".SOCKET", ".SKEW")) or data_path.endswith('["nirik_tile"]')


def is_nirik(data_path: str) -> bool:
    return is_compiled(data_path) or '["nirik_' in data_path


def rebuild_compiled(arm, char: L.Character):
    """Regenerate hidden channels from the visible ones, e.g. after retiming
    construction or drawing keys in the Dope Sheet."""
    bag = _channelbag(arm)
    if bag is None:
        return
    authoring = {fc.data_path: [(kp.co[0], kp.co[1]) for kp in fc.keyframe_points]
                 for fc in bag.fcurves if not is_compiled(fc.data_path)}
    for fc in [fc for fc in bag.fcurves if is_compiled(fc.data_path)]:
        bag.fcurves.remove(fc)

    for rig in char.rigs:  # rigs in library order: parents before children
        path = f'pose.bones["{construction_bone(char, rig)}"]["nirik_construction"]'
        for frame, value in authoring.get(path, []):
            _apply_sockets(arm, char, rig, int(round(value)), int(round(frame)))
    for slot in char.all_slots():
        for frame, value in authoring.get(f'pose.bones["{slot}"]["nirik_drawing"]', []):
            set_drawing(arm, char, slot, int(round(value)))
            arm.pose.bones[slot].keyframe_insert('["nirik_tile"]', frame=int(round(frame)))
    make_constant(arm)
    arm.update_tag()


def make_constant(arm):
    """Nirik's channels hold until the next key, like exposures. The
    animator's own transform keys keep their interpolation."""
    bag = _channelbag(arm)
    if bag is None:
        return
    for fc in bag.fcurves:
        if is_nirik(fc.data_path):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


# ── layers and sides ─────────────────────────────────────────────────────────

def carried_slots(arm, char: L.Character, bone: str) -> list[str]:
    """Drawable slots that move with `bone`: its own card and every card below it."""
    names = {bone} | {b.name for b in arm.data.bones[bone].children_recursive}
    return [s for s in char.draw_order() if s in names]


def effective_order(arm, char: L.Character, slot: str) -> float:
    card = bpy.data.objects.get(f"{char.name}:{slot}")
    return card["nirik_order"] + arm.pose.bones[slot]["nirik_layer"] if card else 0.0


def move_layers(arm, char: L.Character, bones: list[str], how: str, frame: int | None = None):
    """Restack the parts carried by `bones`: FORWARD/BACKWARD past the next
    visible part, FRONT/BACK past all of them, RESET to the stock order."""
    moving = {s for b in bones for s in carried_slots(arm, char, b)}
    if not moving:
        return
    if how == "RESET":
        delta_for = {s: -arm.pose.bones[s]["nirik_layer"] for s in moving}
    else:
        visible = [s for s in char.draw_order() if arm.pose.bones[s]["nirik_drawing"]]
        others = [effective_order(arm, char, s) for s in visible if s not in moving]
        mine = [effective_order(arm, char, s) for s in moving]
        lo, hi = min(mine), max(mine)
        above, below = [o for o in others if o > hi], [o for o in others if o < lo]
        delta = {"FRONT": (max(others) - lo + 1) if above else 0,
                 "BACK": (min(others) - hi - 1) if below else 0,
                 "FORWARD": (min(above) - lo + 0.5) if above else 0,
                 "BACKWARD": (max(below) - hi - 0.5) if below else 0}[how]
        delta_for = {s: delta for s in moving}
    for s, d in delta_for.items():
        pb = arm.pose.bones[s]
        pb["nirik_layer"] = pb["nirik_layer"] + d
        if frame is not None:
            pb.keyframe_insert('["nirik_layer"]', frame=frame)
    if frame is not None:
        make_constant(arm)
    arm.update_tag()


def set_side(arm, char: L.Character, bones: list[str], side: int, frame: int | None = None):
    for s in {s for b in bones for s in carried_slots(arm, char, b)}:
        pb = arm.pose.bones[s]
        pb["nirik_side"] = side
        if frame is not None:
            pb.keyframe_insert('["nirik_side"]', frame=frame)
    if frame is not None:
        make_constant(arm)
    arm.update_tag()


# ── viewport visibility ──────────────────────────────────────────────────────

def stack(arm, char: L.Character) -> list[str]:
    """Parts showing a drawing, front first, in their current (offset) order."""
    shown = [s for s in char.draw_order() if arm.pose.bones[s]["nirik_drawing"]]
    return sorted(shown, key=lambda s: -effective_order(arm, char, s))


def card_of(char: L.Character, slot: str):
    return bpy.data.objects.get(f"{char.name}:{slot}")


def set_hidden(char: L.Character, slots, hidden: bool):
    """Viewport-only hiding (renders unaffected), e.g. hide a blink to pose the eye."""
    for s in slots:
        card = card_of(char, s)
        if card is not None:
            card.hide_set(hidden)
