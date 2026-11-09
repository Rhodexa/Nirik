"""Puppet as a .blend in its library folder, appended into scenes.

blender ... --python append.py -- LIBRARY STAGE   (STAGE: build | use | reopen)

build:  assemble the puppet, save LIBRARY/<name>.blend
use:    empty scene, File > Append the puppet twice, swap different mouths,
        check picking, hiding and sync on the second copy, save scene.blend
reopen: open scene.blend again and render: both copies still right
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bpy
import numpy as np
from mathutils import Vector

import harness

lib, stage = Path(sys.argv[sys.argv.index("--") + 1]), sys.argv[sys.argv.index("--") + 2]
harness.load_nirik()
from nirik.bridge import picking, relink, rig_build, sync  # noqa: E402
from nirik.core import library  # noqa: E402
from nirik.ui import character_for  # noqa: E402

char = library.load(lib)
puppet_blend = lib / f"{char.name}.blend"
scene_blend = lib.parent / "shot" / "scene.blend"
MOUTH = "Head.MOUTH"


def camera_and_render(name):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 256, 128
    scene.render.film_transparent = True
    scene.eevee.taa_render_samples = 4
    cam = scene.camera or bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    if cam.name not in scene.collection.objects:
        scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type, cam.data.ortho_scale = "ORTHO", 3.0
    cam.location, cam.rotation_euler = (0, -5, 0.55), (math.pi / 2, 0, 0)
    return harness.render(name, 1)[1]


def armatures():
    return sorted((o for o in bpy.data.objects if "nirik_library" in o), key=lambda o: o.name)


def mouth_region(px, arm):
    """Pixels of the half of the image this armature stands in."""
    half = px.shape[1] // 2
    return px[:, :half] if arm.location.x < 0 else px[:, half:]


if stage == "build":
    harness.clean()
    bpy.ops.nirik.load_character(directory=str(lib))
    bpy.ops.wm.save_as_mainfile(filepath=str(puppet_blend))
    print("BUILT", puppet_blend)

elif stage == "use":
    bpy.ops.wm.read_homefile(use_empty=True)  # a fresh, empty file (Nirik stays loaded)
    collection = f"nirik:{char.name}"
    for _ in range(2):
        bpy.ops.wm.append(filepath=str(puppet_blend / "Collection" / collection),
                          directory=str(puppet_blend / "Collection"), filename=collection)
    # In the UI a timer adopts appended puppets after the next update; there
    # is no event loop here, so run what the timer runs.
    relink.adopt_new_puppets()
    a, b = armatures()
    assert a.name != b.name, "two separate copies"
    a.location.x, b.location.x = -0.7, 0.7

    # The two copies share their textures (one set in GPU memory)
    tex = lambda arm: {n.image.name for m in rig_build.card_of(arm, MOUTH).data.materials
                       for n in m.node_tree.nodes if n.type == "TEX_IMAGE"}
    assert tex(a) == tex(b)

    # Each copy finds its own cards, through its armature
    card_a, card_b = rig_build.card_of(a, MOUTH), rig_build.card_of(b, MOUTH)
    assert card_a is not None and card_b is not None and card_a != card_b

    # Different mouths on each copy, rendered at once
    mouths = char.slot_drawings(MOUTH)
    rig_build.set_drawing(a, char, MOUTH, mouths[10])
    rig_build.set_drawing(b, char, MOUTH, mouths[40])
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    tile_a = card_a.evaluated_get(dg)["nirik_tile"]
    tile_b = card_b.evaluated_get(dg)["nirik_tile"]
    assert tile_a != tile_b, (tile_a, tile_b)
    px = camera_and_render("append_two")
    assert mouth_region(px, a)[..., 3].max() > 0.9 and mouth_region(px, b)[..., 3].max() > 0.9

    # Picking on the second copy
    pupil_card = rig_build.card_of(b, "Head.PUPIL").evaluated_get(dg)
    v0, v1, _, v3 = (pupil_card.matrix_world @ v.co for v in pupil_card.data.vertices)
    hits = []
    for u in np.linspace(0.2, 0.8, 7):
        for v in np.linspace(0.2, 0.8, 7):
            p = v0 + (v1 - v0) * u + (v3 - v0) * v
            hits += [h.slot for h in picking.hits(b, char, Vector((p.x, p.y - 2, p.z)), Vector((0, 1, 0)), dg)]
    assert hits, "picking finds the second copy's artwork"

    # Hiding on the second copy leaves the first alone
    rig_build.set_hidden(b, [MOUTH], True)
    assert card_b.hide_get() and not card_a.hide_get()
    rig_build.set_hidden(b, [MOUTH], False)

    # Keys and auto-sync on the second copy
    rig_build.apply_construction(b, char, "Character", 0, frame=1)
    rig_build.apply_construction(b, char, "Character", 30, frame=10)
    sync.mark_synced(b)
    assert not sync.out_of_sync(b)

    # Load Symbol from the panel appends from the same .blend
    assert bpy.ops.nirik.load_character(directory=str(lib)) == {"FINISHED"}
    third = bpy.context.active_object
    assert len(armatures()) == 3 and rig_build.card_of(third, MOUTH) is not None
    for ob in [third] + list(third.children):
        bpy.data.objects.remove(ob)

    # Key the second copy's mouth too, then take the reference picture
    rig_build.set_drawing(b, char, MOUTH, mouths[40])
    rig_build.key_drawing(b, MOUTH, 1)
    sync.mark_synced(b)
    px = camera_and_render("append_keyed")
    scene_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_blend))
    np.save(scene_blend.parent / "use.npy", px)
    print("USED")

else:  # reopen
    bpy.ops.wm.open_mainfile(filepath=str(scene_blend))
    a, b = armatures()
    assert character_for(a) is not None
    px = camera_and_render("append_reopen")
    before = np.load(scene_blend.parent / "use.npy")
    assert np.abs(px - before).max() < 0.05, "scene reopens looking the same"
    print("REOPENED")
