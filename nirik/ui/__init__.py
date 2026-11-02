import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy_extras import view3d_utils

from ..bridge import picking, rig_build, sync
from ..core import controls, library
from . import overlay

_characters: dict[str, library.Character] = {}  # disposable cache: library path -> Character


def character_for(arm) -> library.Character | None:
    path = arm.get("nirik_library") if arm else None
    if not path:
        return None
    if path not in _characters:
        _characters[path] = library.load(path)
    return _characters[path]


def nirik_armature(context):
    ob = context.active_object
    return ob if ob is not None and ob.type == "ARMATURE" and "nirik_library" in ob else None


def active_slot(context, char) -> str | None:
    pb = context.active_pose_bone
    return pb.name if pb is not None and pb.name in char.all_slots() and "nirik_drawing" in pb else None


def redraw_viewports(context):
    for area in context.screen.areas if context.screen else ():
        if area.type == "VIEW_3D":
            area.tag_redraw()


def part_label(arm, char, slot: str) -> str:
    drawing = char.drawings.get(arm.pose.bones[slot]["nirik_drawing"])
    return controls.drawing_label(drawing.symbol) if drawing else controls.label(slot)


def select_bones(arm, char, names: list[str], extend: bool = False):
    """Select `names` (Pose mode). Extra controls are hidden one by one; only
    the picked ones are revealed."""
    main = controls.main_bones(char)
    slots = char.all_slots()
    for pb in arm.pose.bones:
        if pb.name in names:
            pb.select = True
        elif not extend:
            pb.select = False
        if pb.name in slots and pb.name not in main:
            pb.hide = not pb.select
    if names:
        arm.data.bones.active = arm.data.bones[names[0]]


def autokey_frame(context) -> int | None:
    ts = context.scene.tool_settings
    return context.scene.frame_current if ts.use_keyframe_insert_auto else None


class NIRIK_OT_load_character(bpy.types.Operator):
    """Build a puppet from a Nirik character library folder"""
    bl_idname = "nirik.load_character"
    bl_label = "Load Character"
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(subtype="DIR_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            char = library.load(self.directory)
        except (OSError, ValueError) as e:
            self.report({"ERROR"}, f"Not a Nirik library: {e}")
            return {"CANCELLED"}
        _characters[str(char.root)] = char
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        arm = rig_build.build(char)
        rig_build.apply_construction(arm, char, char.root_rig, 0)
        sync.mark_synced(arm)
        for ob in context.selected_objects:
            ob.select_set(False)
        arm.select_set(True)
        context.view_layer.objects.active = arm
        return {"FINISHED"}


class NIRIK_OT_step_construction(bpy.types.Operator):
    """Switch to the previous/next construction of a rig"""
    bl_idname = "nirik.step_construction"
    bl_label = "Step Construction"
    bl_options = {"REGISTER", "UNDO"}

    rig: StringProperty()
    step: IntProperty(default=1)

    @classmethod
    def poll(cls, context):
        return nirik_armature(context) is not None

    def execute(self, context):
        arm = nirik_armature(context)
        char = character_for(arm)
        total = len(char.rigs[self.rig].constructions)
        cid = (rig_build.current_construction(arm, char, self.rig) + self.step) % total
        rig_build.apply_construction(arm, char, self.rig, cid, autokey_frame(context))
        sync.mark_synced(arm)
        redraw_viewports(context)
        return {"FINISHED"}


class NIRIK_OT_select_part(bpy.types.Operator):
    """Select this part's controls (Pose mode)"""
    bl_idname = "nirik.select_part"
    bl_label = "Select Part"
    bl_options = {"REGISTER", "UNDO"}

    bones: StringProperty(description="Comma-separated bone names")
    extend: BoolProperty(description="Add to the selection (Shift+click the button)")

    @classmethod
    def poll(cls, context):
        return nirik_armature(context) is not None

    def invoke(self, context, event):
        self.extend = event.shift
        return self.execute(context)

    def execute(self, context):
        arm = nirik_armature(context)
        if context.mode != "POSE":
            bpy.ops.object.mode_set(mode="POSE")
        names = [n for n in self.bones.split(",") if n in arm.data.bones]
        select_bones(arm, character_for(arm), names, self.extend)
        return {"FINISHED"}


_last_pick: dict = {}  # Alt+click cycling: position, stack under the cursor, index


class NIRIK_OT_pick(bpy.types.Operator):
    """Select the part under the cursor by clicking its artwork"""
    bl_idname = "nirik.pick"
    bl_label = "Pick Part"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(items=(
        ("PART", "Part", "The part a click means: a face feature, the head, or the body"),
        ("EXACT", "Exact", "The exact piece under the cursor"),
        ("CYCLE", "Cycle", "Step through every piece stacked under the cursor"),
    ), default="PART")
    extend: BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return (nirik_armature(context) is not None and context.mode == "POSE"
                and context.region is not None and context.region.type == "WINDOW")

    def invoke(self, context, event):
        # Bound to both mouse buttons; act only on the user's select button.
        prefs = context.window_manager.keyconfigs.active.preferences
        select = getattr(prefs, "select_mouse", "LEFT") if prefs else "LEFT"
        if event.type != f"{select}MOUSE":
            return {"PASS_THROUGH"}
        arm = nirik_armature(context)
        char = character_for(arm)
        coord = (event.mouse_region_x, event.mouse_region_y)
        rv3d = context.region_data
        origin = view3d_utils.region_2d_to_origin_3d(context.region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(context.region, rv3d, coord)
        found = picking.hits(arm, char, origin, direction, context.evaluated_depsgraph_get())
        if not found:
            return {"PASS_THROUGH"}  # empty space: Blender's own selection
        stack = [h.slot for h in found]

        if self.mode == "CYCLE":
            last = _last_pick
            near = last.get("stack") == stack and abs(last["x"] - coord[0]) + abs(last["y"] - coord[1]) < 6
            index = (last["index"] + 1) % len(stack) if near else 0
            _last_pick.update(x=coord[0], y=coord[1], stack=stack, index=index)
            names = [stack[index]]
        elif self.mode == "EXACT":
            names = [stack[0]]
        else:
            names = controls.part_for_slot(char, stack[0])
        select_bones(arm, char, names, self.extend)
        label = part_label(arm, char, stack[0]) if self.mode != "CYCLE" else part_label(arm, char, names[0])
        self.report({"INFO"}, label if self.mode != "CYCLE" else f"{label} ({index + 1}/{len(stack)})")
        return {"FINISHED"}


class NIRIK_OT_step_drawing(bpy.types.Operator):
    """Swap the selected part to the previous/next drawing"""
    bl_idname = "nirik.step_drawing"
    bl_label = "Step Drawing"
    bl_options = {"REGISTER", "UNDO"}

    step: IntProperty(default=1)
    scope: EnumProperty(items=(
        ("SYMBOL", "Same Set", "Only drawings from the current drawing's set (e.g. the 3/4 mouth chart)"),
        ("SLOT", "All", "Every drawing this part can show"),
    ), default="SYMBOL")

    @classmethod
    def poll(cls, context):
        # Deliberately permissive: if poll failed, Alt+Wheel would fall through
        # to Blender's own binding and scrub the timeline instead.
        return nirik_armature(context) is not None and context.mode == "POSE"

    def execute(self, context):
        arm = nirik_armature(context)
        char = character_for(arm)
        slot = active_slot(context, char)
        if slot is None:
            self.report({"INFO"}, "Select a part with drawings (Mouth, Eye, ...) to swap")
            return {"CANCELLED"}
        current = arm.pose.bones[slot]["nirik_drawing"]
        options = [0] + char.slot_drawings(slot)
        if self.scope == "SYMBOL" and current in char.drawings:
            symbol = char.drawings[current].symbol
            options = [d for d in options[1:] if char.drawings[d].symbol == symbol]
        index = options.index(current) if current in options else 0
        drawing = options[(index + self.step) % len(options)]
        rig_build.set_drawing(arm, char, slot, drawing)
        frame = autokey_frame(context)
        if frame is not None:
            rig_build.key_drawing(arm, slot, frame)
            sync.mark_synced(arm)
        redraw_viewports(context)
        return {"FINISHED"}


class NIRIK_PT_main(bpy.types.Panel):
    bl_label = "Nirik"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Nirik"

    def draw(self, context):
        layout = self.layout
        layout.operator("nirik.load_character", icon="FILE_FOLDER")
        arm = nirik_armature(context)
        char = character_for(arm)
        if char is None:
            layout.label(text="Select a Nirik character")
            return

        box = layout.box()
        box.label(text="Parts", icon="RESTRICT_SELECT_OFF")
        grid = box.grid_flow(columns=3, align=True)
        selected = {pb.name for pb in arm.pose.bones if pb.select} if context.mode == "POSE" else set()
        for label, bones in controls.parts(char):
            op = grid.operator("nirik.select_part", text=label, depress=bool(selected) and selected == set(bones))
            op.bones = ",".join(bones)

        box = layout.box()
        box.label(text=f"{char.name}", icon="ARMATURE_DATA")
        for rig in char.rigs.values():
            control = arm.pose.bones[rig_build.construction_bone(char, rig.name)]
            cid = control.get("nirik_construction", 0)
            row = box.row(align=True)
            op = row.operator("nirik.step_construction", text="", icon="TRIA_LEFT")
            op.rig, op.step = rig.name, -1
            # Shown as the real property so keyed frames are colored like any
            # Blender value; change it with the arrows (typing skips the rig).
            sub = row.row(align=True)
            sub.enabled = False
            sub.prop(control, '["nirik_construction"]', text=rig.name)
            op = row.operator("nirik.step_construction", text="", icon="TRIA_RIGHT")
            op.rig, op.step = rig.name, 1
            labels = ", ".join(rig.constructions[cid].labels)
            if labels:
                box.label(text=f"   {labels}  ({len(rig.constructions)} poses)")
        row = box.row(align=True)
        row.operator("screen.keyframe_jump", text="Prev Key", icon="PREV_KEYFRAME").next = False
        row.operator("screen.keyframe_jump", text="Next Key", icon="NEXT_KEYFRAME").next = True

        pb = context.active_pose_bone if context.mode == "POSE" else None
        box = layout.box()
        if pb is None or not (pb.name == "ROOT" or pb.name in char.all_slots()):
            box.label(text="Pose mode: click a part", icon="BONE_DATA")
            return
        slot = active_slot(context, char)
        drawable = slot is not None and char.all_slots()[slot].canvas is not None
        box.label(text=part_label(arm, char, slot) if drawable else
                  ("Body" if pb.name == "ROOT" else char.all_slots()[pb.name].child_rig or pb.name),
                  icon="BONE_DATA")

        # Layer and side act on everything the selection carries.
        row = box.row(align=True)
        row.operator("nirik.layer", text="", icon="TRIA_DOWN_BAR").how = "BACK"
        row.operator("nirik.layer", text="", icon="TRIA_DOWN").how = "BACKWARD"
        if drawable:
            sub = row.row(align=True)
            sub.enabled = False
            sub.prop(pb, '["nirik_layer"]', text="Layer")
        else:
            row.label(text="Layer")
        row.operator("nirik.layer", text="", icon="TRIA_UP").how = "FORWARD"
        row.operator("nirik.layer", text="", icon="TRIA_UP_BAR").how = "FRONT"
        row.operator("nirik.layer", text="", icon="LOOP_BACK").how = "RESET"
        row = box.row(align=True)
        row.operator("nirik.depth", text="", icon="TRIA_LEFT").how = "BACK"
        if drawable:
            row.prop(pb, '["nirik_depth"]', text="Depth")
        else:
            row.label(text="Depth")
        row.operator("nirik.depth", text="", icon="TRIA_RIGHT").how = "FORWARD"
        row.operator("nirik.depth", text="", icon="LOOP_BACK").how = "RESET"
        row = box.row(align=True)
        side = pb.get("nirik_side", rig_build.SIDE_AUTO) if drawable else None
        for value, text in ((rig_build.SIDE_AUTO, "Auto"), (rig_build.SIDE_NEAR, "Near"),
                            (rig_build.SIDE_FAR, "Far")):
            row.operator("nirik.set_side", text=text, depress=side == value).side = value
        row.operator("nirik.hide", text="", icon="HIDE_ON").action = "HIDE"
        if not slot:
            return

        did = arm.pose.bones[slot]["nirik_drawing"]
        drawing = char.drawings.get(did)
        row = box.row(align=True)
        row.operator("nirik.step_drawing", text="", icon="TRIA_LEFT").step = -1
        sub = row.row(align=True)
        sub.enabled = False
        sub.prop(arm.pose.bones[slot], '["nirik_drawing"]', text="Drawing")
        row.operator("nirik.step_drawing", text="", icon="TRIA_RIGHT").step = 1
        box.operator("nirik.browse_drawings", text="Browse Drawings (Alt+D)", icon="IMAGE_DATA")
        box.label(text=drawing.symbol if drawing else "(empty)")
        if drawing and drawing.tags:
            box.label(text=" · ".join(drawing.tags), icon="BOOKMARKS")
        box.label(text=f"{len(char.slot_drawings(slot))} drawings, "
                       f"{len(rig_build.palette(arm, slot))} loaded", icon="IMAGE_DATA")
        box.label(text="Alt+Wheel: swap (same set)", icon="MOUSE_MMB_SCROLL")
        box.label(text="Ctrl+Alt+Wheel: swap (all)", icon="MOUSE_MMB_SCROLL")


def selected_controls(arm, char) -> list[str]:
    slots = char.all_slots()
    return [pb.name for pb in arm.pose.bones if pb.select and (pb.name == "ROOT" or pb.name in slots)]


class NIRIK_OT_layer(bpy.types.Operator):
    """Restack the selected parts (and everything they carry)"""
    bl_idname = "nirik.layer"
    bl_label = "Change Layer"
    bl_options = {"REGISTER", "UNDO"}

    how: EnumProperty(items=(
        ("FORWARD", "Forward", "In front of the next visible part"),
        ("BACKWARD", "Backward", "Behind the next visible part"),
        ("FRONT", "To Front", "In front of every other part"),
        ("BACK", "To Back", "Behind every other part"),
        ("RESET", "Reset", "Back to the stock layer order"),
    ))

    @classmethod
    def poll(cls, context):
        return nirik_armature(context) is not None and context.mode == "POSE"

    def execute(self, context):
        arm = nirik_armature(context)
        char = character_for(arm)
        rig_build.move_layers(arm, char, selected_controls(arm, char), self.how, autokey_frame(context))
        sync.mark_synced(arm)
        redraw_viewports(context)
        return {"FINISHED"}


class NIRIK_OT_depth(bpy.types.Operator):
    """Move the selected parts away from / toward the camera, e.g. a rider's
    far wing behind the character he sits on"""
    bl_idname = "nirik.depth"
    bl_label = "Change Depth"
    bl_options = {"REGISTER", "UNDO"}

    how: EnumProperty(items=(("BACK", "Push Back", "Away from the camera"),
                             ("FORWARD", "Pull Forward", "Toward the camera"),
                             ("RESET", "Reset", "Back to the character's plane")))

    @classmethod
    def poll(cls, context):
        return nirik_armature(context) is not None and context.mode == "POSE"

    def execute(self, context):
        arm = nirik_armature(context)
        char = character_for(arm)
        rig_build.move_depth(arm, char, selected_controls(arm, char), self.how, autokey_frame(context))
        sync.mark_synced(arm)
        redraw_viewports(context)
        return {"FINISHED"}


class NIRIK_OT_set_side(bpy.types.Operator):
    """Near/far shading of the selected parts: Auto follows the stock pose,
    Far applies the character's far-limb darkening"""
    bl_idname = "nirik.set_side"
    bl_label = "Set Side"
    bl_options = {"REGISTER", "UNDO"}

    side: IntProperty(min=0, max=2)

    @classmethod
    def poll(cls, context):
        return nirik_armature(context) is not None and context.mode == "POSE"

    def execute(self, context):
        arm = nirik_armature(context)
        char = character_for(arm)
        rig_build.set_side(arm, char, selected_controls(arm, char), self.side, autokey_frame(context))
        sync.mark_synced(arm)
        redraw_viewports(context)
        return {"FINISHED"}


class NIRIK_OT_hide(bpy.types.Operator):
    """Hide or show parts in the viewport only (renders are unaffected)"""
    bl_idname = "nirik.hide"
    bl_label = "Hide Parts"
    bl_options = {"REGISTER", "UNDO"}

    slot: StringProperty(description="One part; empty = the selection")
    action: EnumProperty(items=(("TOGGLE", "Toggle", ""), ("HIDE", "Hide", ""), ("SHOW_ALL", "Show All", "")))

    @classmethod
    def poll(cls, context):
        return nirik_armature(context) is not None

    def execute(self, context):
        arm = nirik_armature(context)
        char = character_for(arm)
        if self.action == "SHOW_ALL":
            rig_build.set_hidden(char, char.draw_order(), False)
        elif self.slot:
            card = rig_build.card_of(char, self.slot)
            rig_build.set_hidden(char, [self.slot], not card.hide_get())
        else:
            parts = {s for b in selected_controls(arm, char) for s in rig_build.carried_slots(arm, char, b)}
            rig_build.set_hidden(char, parts, True)
        redraw_viewports(context)
        return {"FINISHED"}


class NIRIK_UL_layers(bpy.types.UIList):
    """Parts front to back, as currently stacked."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        arm = data.id_data
        char = character_for(arm)
        card = rig_build.card_of(char, item.name)
        hidden = card is not None and card.hide_get()
        row = layout.row(align=True)
        op = row.operator("nirik.hide", text="", icon="HIDE_ON" if hidden else "HIDE_OFF", emboss=False)
        op.slot, op.action = item.name, "TOGGLE"
        row.label(text=part_label(arm, char, item.name), icon="SELECT_SET" if item.select else "BLANK1")

    def filter_items(self, context, data, propname):
        bones = getattr(data, propname)
        arm = data.id_data
        rows = rig_build.stack(arm, character_for(arm))
        position = {name: i for i, name in enumerate(rows)}
        flags = [self.bitflag_filter_item if pb.name in position else 0 for pb in bones]
        order = sorted(range(len(bones)), key=lambda i: position.get(bones[i].name, len(rows) + i))
        new_order = [0] * len(bones)
        for new, old in enumerate(order):
            new_order[old] = new
        return flags, new_order


def _layer_index_changed(arm, context):
    """Clicking a row in the Layers list selects that part."""
    bones = arm.pose.bones
    if 0 <= arm.nirik_layer_index < len(bones) and context.mode == "POSE":
        select_bones(arm, character_for(arm), [bones[arm.nirik_layer_index].name])


class NIRIK_PT_layers(bpy.types.Panel):
    bl_label = "Layers"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Nirik"
    bl_parent_id = "NIRIK_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return character_for(nirik_armature(context)) is not None

    def draw(self, context):
        arm = nirik_armature(context)
        layout = self.layout
        layout.template_list("NIRIK_UL_layers", "", arm.pose, "bones", arm, "nirik_layer_index", rows=12)
        row = layout.row(align=True)
        row.operator("nirik.hide", text="Hide Selected", icon="HIDE_ON").action = "HIDE"
        row.operator("nirik.hide", text="Show All", icon="HIDE_OFF").action = "SHOW_ALL"


_previews = None  # bpy.utils.previews collection: drawing thumbnails, loaded lazily
BROWSER_LIMIT = 96


def drawing_icon(char, drawing: int) -> int:
    key = f"{char.root}:{drawing}"
    if key not in _previews:
        _previews.load(key, str(char.drawing_path(drawing)), "IMAGE")
    return _previews[key].icon_id


class NIRIK_OT_set_drawing(bpy.types.Operator):
    """Show this drawing on the selected part (keyed with auto-key)"""
    bl_idname = "nirik.set_drawing"
    bl_label = "Use Drawing"
    bl_options = {"REGISTER", "UNDO"}

    drawing: IntProperty()

    @classmethod
    def poll(cls, context):
        arm = nirik_armature(context)
        return arm is not None and active_slot(context, character_for(arm)) is not None

    def execute(self, context):
        arm = nirik_armature(context)
        char = character_for(arm)
        slot = active_slot(context, char)
        rig_build.set_drawing(arm, char, slot, self.drawing)
        frame = autokey_frame(context)
        if frame is not None:
            rig_build.key_drawing(arm, slot, frame)
            sync.mark_synced(arm)
        redraw_viewports(context)
        return {"FINISHED"}


class NIRIK_OT_browse_drawings(bpy.types.Operator):
    """Pick a drawing for the selected part from thumbnails"""
    bl_idname = "nirik.browse_drawings"
    bl_label = "Drawings"

    show_all: BoolProperty(name="All", default=True,
                           description="Every drawing this part can show, not just the current set")

    @classmethod
    def poll(cls, context):
        arm = nirik_armature(context)
        return arm is not None and active_slot(context, character_for(arm)) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=720)

    def execute(self, context):
        return {"FINISHED"}

    def draw(self, context):
        arm = nirik_armature(context)
        char = character_for(arm)
        slot = active_slot(context, char)
        current = arm.pose.bones[slot]["nirik_drawing"]
        options = char.slot_drawings(slot)
        symbol = char.drawings[current].symbol if current in char.drawings else None
        if not self.show_all and symbol:
            options = [d for d in options if char.drawings[d].symbol == symbol]
        # Current set first, then the other sets grouped together.
        options.sort(key=lambda d: (char.drawings[d].symbol != symbol, char.drawings[d].symbol, d))
        layout = self.layout
        row = layout.row()
        row.label(text=f"{part_label(arm, char, slot)}: {len(options)} drawings")
        row.prop(self, "show_all", toggle=True)
        grid = layout.grid_flow(columns=6, even_columns=True, align=True)
        for d in options[:BROWSER_LIMIT]:
            col = grid.column(align=True)
            col.template_icon(icon_value=drawing_icon(char, d), scale=5.0)
            tags = " · ".join(t for t in char.drawings[d].tags if t.strip("- "))[:22]
            op = col.operator("nirik.set_drawing", text=tags or f"#{d}", depress=d == current)
            op.drawing = d
        if len(options) > BROWSER_LIMIT:
            layout.label(text=f"First {BROWSER_LIMIT} shown; Alt+Wheel reaches the rest")


class NIRIK_OT_rebuild(bpy.types.Operator):
    """Re-sync the rig's hidden channels with the visible construction and
    drawing keys (after moving or deleting them in the Dope Sheet)"""
    bl_idname = "nirik.rebuild"
    bl_label = "Nirik: Re-sync Keys"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return nirik_armature(context) is not None

    def execute(self, context):
        arm = nirik_armature(context)
        sync.sync_now(arm, character_for(arm))
        context.scene.frame_set(context.scene.frame_current)
        redraw_viewports(context)
        return {"FINISHED"}


class NIRIK_PT_more(bpy.types.Panel):
    bl_label = "More Parts"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Nirik"
    bl_parent_id = "NIRIK_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return character_for(nirik_armature(context)) is not None

    def draw(self, context):
        arm = nirik_armature(context)
        char = character_for(arm)
        layout = self.layout
        layout.label(text="Parts showing a drawing in this pose:")
        for rig, names in controls.more_parts(char).items():
            showing = [n for n in names if arm.pose.bones[n]["nirik_drawing"]]
            if not showing:
                continue
            layout.label(text=rig)
            grid = layout.grid_flow(columns=2, align=True)
            seen: dict[str, int] = {}
            for name in showing:
                text = part_label(arm, char, name)
                seen[text] = seen.get(text, 0) + 1
                if seen[text] > 1:
                    text = f"{text} {seen[text]}"
                op = grid.operator("nirik.select_part", text=text, depress=arm.pose.bones[name].select)
                op.bones = name


classes = (NIRIK_OT_load_character, NIRIK_OT_step_construction, NIRIK_OT_select_part, NIRIK_OT_pick,
           NIRIK_OT_step_drawing, NIRIK_OT_set_drawing, NIRIK_OT_browse_drawings, NIRIK_OT_layer, NIRIK_OT_depth, NIRIK_OT_set_side, NIRIK_OT_hide, NIRIK_OT_rebuild,
           NIRIK_UL_layers, NIRIK_PT_main, NIRIK_PT_layers, NIRIK_PT_more)
_keymaps = []


def register():
    global _previews
    import bpy.utils.previews
    _previews = bpy.utils.previews.new()
    bpy.types.Object.nirik_layer_index = IntProperty(default=-1, update=_layer_index_changed)
    for cls in classes:
        bpy.utils.register_class(cls)
    sync.register()
    overlay.register()
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="Pose", space_type="EMPTY")
        for button in ("LEFTMOUSE", "RIGHTMOUSE"):
            for value, mods, mode, extend in (("PRESS", {}, "PART", False),
                                              ("PRESS", {"shift": True}, "PART", True),
                                              ("PRESS", {"alt": True}, "CYCLE", False),
                                              ("DOUBLE_CLICK", {}, "EXACT", False),
                                              ("DOUBLE_CLICK", {"shift": True}, "EXACT", True)):
                kmi = km.keymap_items.new("nirik.pick", button, value, **mods)
                kmi.properties.mode, kmi.properties.extend = mode, extend
                _keymaps.append((km, kmi))
        _keymaps.append((km, km.keymap_items.new("nirik.browse_drawings", "D", "PRESS", alt=True)))
        for key, step in (("WHEELUPMOUSE", -1), ("WHEELDOWNMOUSE", 1)):
            for ctrl, scope in ((False, "SYMBOL"), (True, "SLOT")):
                kmi = km.keymap_items.new("nirik.step_drawing", key, "PRESS", alt=True, ctrl=ctrl)
                kmi.properties.step, kmi.properties.scope = step, scope
                _keymaps.append((km, kmi))


def unregister():
    overlay.unregister()
    sync.unregister()
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Object.nirik_layer_index
    bpy.utils.previews.remove(_previews)
