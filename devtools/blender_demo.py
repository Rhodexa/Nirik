"""Runs inside Blender: load a character library and frame it for playing.

  make demo CHAR=library/twilight
"""

import sys

import bpy

LIBRARY = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "library/twilight"


def setup():
    scene = bpy.context.scene
    for ob in list(scene.objects):  # startup cube, camera, light
        bpy.data.objects.remove(ob)
    scene.view_settings.view_transform = "Standard"
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)

    bpy.ops.nirik.load_character(directory=LIBRARY)
    bpy.ops.object.mode_set(mode="POSE")

    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            space = area.spaces.active
            space.shading.type = "MATERIAL"
            space.overlay.show_floor = space.overlay.show_axis_x = space.overlay.show_axis_y = False
            region = next(r for r in area.regions if r.type == "WINDOW")
            with bpy.context.temp_override(area=area, region=region):
                bpy.ops.view3d.view_axis(type="FRONT")
                bpy.ops.view3d.view_all()
            space.region_3d.view_distance *= 0.6
            space.region_3d.view_location.z += 0.5
            space.show_region_ui = True
            break
    return None  # run once


bpy.app.timers.register(setup, first_interval=0.5)
