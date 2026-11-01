import bpy


class NIRIK_PT_main(bpy.types.Panel):
    bl_label = "Nirik"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Nirik"

    def draw(self, context):
        self.layout.label(text="Nirik is loaded")


classes = (NIRIK_PT_main,)

register, unregister = bpy.utils.register_classes_factory(classes)
