import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty

from ..bridge import rig_build
from ..core import controls, library

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
        redraw_viewports(context)
        return {"FINISHED"}


class NIRIK_OT_select_part(bpy.types.Operator):
    """Select this part's controls (Pose mode)"""
    bl_idname = "nirik.select_part"
    bl_label = "Select Part"
    bl_options = {"REGISTER", "UNDO"}

    bones: StringProperty(description="Comma-separated bone names")

    @classmethod
    def poll(cls, context):
        return nirik_armature(context) is not None

    def execute(self, context):
        arm = nirik_armature(context)
        if context.mode != "POSE":
            bpy.ops.object.mode_set(mode="POSE")
        names = [n for n in self.bones.split(",") if n in arm.data.bones]
        main = controls.main_bones(character_for(arm))
        for pb in arm.pose.bones:
            pb.select = pb.name in names
            if pb.name in character_for(arm).all_slots() and pb.name not in main:
                pb.hide = pb.name not in names  # show only the extra part you picked
        if names:
            arm.data.bones.active = arm.data.bones[names[0]]
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
        box.operator("nirik.rebuild", icon="FILE_REFRESH")

        slot = active_slot(context, char)
        box = layout.box()
        if slot is None:
            box.label(text="Pose mode: select a part's bone", icon="BONE_DATA")
            return
        did = arm.pose.bones[slot]["nirik_drawing"]
        drawing = char.drawings.get(did)
        box.label(text=f"{part_label(arm, char, slot)}  ({slot})", icon="BONE_DATA")
        row = box.row(align=True)
        row.operator("nirik.step_drawing", text="", icon="TRIA_LEFT").step = -1
        sub = row.row(align=True)
        sub.enabled = False
        sub.prop(arm.pose.bones[slot], '["nirik_drawing"]', text="Drawing")
        row.operator("nirik.step_drawing", text="", icon="TRIA_RIGHT").step = 1
        box.label(text=drawing.symbol if drawing else "(empty)")
        if drawing and drawing.tags:
            box.label(text=" · ".join(drawing.tags), icon="BOOKMARKS")
        box.label(text=f"{len(char.slot_drawings(slot))} drawings, "
                       f"{len(rig_build.palette(arm, slot))} loaded", icon="IMAGE_DATA")
        box.label(text="Alt+Wheel: swap (same set)", icon="MOUSE_MMB_SCROLL")
        box.label(text="Ctrl+Alt+Wheel: swap (all)", icon="MOUSE_MMB_SCROLL")


class NIRIK_OT_rebuild(bpy.types.Operator):
    """Re-sync the rig's hidden channels with the visible construction and
    drawing keys (after moving or deleting them in the Dope Sheet)"""
    bl_idname = "nirik.rebuild"
    bl_label = "Sync After Retiming"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return nirik_armature(context) is not None

    def execute(self, context):
        arm = nirik_armature(context)
        rig_build.rebuild_compiled(arm, character_for(arm))
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


classes = (NIRIK_OT_load_character, NIRIK_OT_step_construction, NIRIK_OT_select_part,
           NIRIK_OT_step_drawing, NIRIK_OT_rebuild, NIRIK_PT_main, NIRIK_PT_more)
_keymaps = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="Pose", space_type="EMPTY")
        for key, step in (("WHEELUPMOUSE", -1), ("WHEELDOWNMOUSE", 1)):
            for ctrl, scope in ((False, "SYMBOL"), (True, "SLOT")):
                kmi = km.keymap_items.new("nirik.step_drawing", key, "PRESS", alt=True, ctrl=ctrl)
                kmi.properties.step, kmi.properties.scope = step, scope
                _keymaps.append((km, kmi))


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
