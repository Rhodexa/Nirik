"""Swapping symbols onto layers, across libraries, mid-shot.

blender ... --python swap.py -- FOLDER      (FOLDER holds libraries twilight/ and twin/)
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bpy
from mathutils import Vector

import harness

folder = Path(sys.argv[sys.argv.index("--") + 1])
harness.load_nirik()
from nirik.bridge import picking, rig_build, swap, sync  # noqa: E402
from nirik.core import library  # noqa: E402
from nirik.ui import character_for  # noqa: E402

T = library.load(folder / "twilight")
TWIN = library.load(folder / "twin")
HOLDER = next(s for s in T.rigs[T.root_rig].slots if s.child_rig)  # the head layer
HEAD = HOLDER.child_rig
scene = bpy.context.scene
state = {}


def cards(arm, slots=None):
    return [c for c in arm.children if "nirik_slot" in c and (slots is None or c["nirik_slot"] in slots)]


def head_slots(char):
    return {s.name for r in char.symbols_below(HEAD) for s in char.rigs[r].slots}


def nkeys(arm):
    return sum(len(fc.keyframe_points) for fc in rig_build._channelbag(arm).fcurves)


def drawn(cs):
    return [c for c in cs if c["nirik_tile"] >= 0]


def test_swap_in_builds_only_the_symbol():
    harness.clean()
    scene.frame_start, scene.frame_end = 1, 40
    host = rig_build.build(T)
    rig_build.apply_construction(host, T, T.root_rig, 0, frame=1)
    pb = host.pose.bones[HOLDER.name]
    for f, angle in ((1, 0.0), (12, 0.3), (24, -0.3)):
        pb.rotation_euler = (0, 0, angle)
        pb.keyframe_insert("rotation_euler", frame=f)
    before = nkeys(host)
    inst = swap.swap_in(host, T, HOLDER.name, TWIN, HEAD)
    assert nkeys(host) == before, "a swap must not change what is keyed"
    sub = character_for(inst)
    assert sub.root_rig == HEAD and inst["nirik_library"] == str(TWIN.root)
    assert len(cards(inst)) == len(TWIN.subtree(HEAD).draw_order())
    assert inst[swap.INDEX] == 1 and inst.parent is host and inst.parent_bone == HOLDER.name
    rig_build.apply_construction(inst, sub, HEAD, 1, frame=13)  # the swapped-in head acts on its own
    state.update(host=host, inst=inst)


def test_show_switches_which_head_draws_from_its_frame():
    host, inst = state["host"], state["inst"]
    swap.show(host, HOLDER.name, 1, frame=13)
    body = cards(host, set(T.draw_order()) - head_slots(T))
    rig_build.rebuild_compiled(host, T)  # what auto-sync does after editing keys
    for frame, own in ((5, True), (12, True), (13, False), (30, False)):
        scene.frame_set(frame)
        assert bool(drawn(cards(host, head_slots(T)))) == own, frame
        assert bool(drawn(cards(inst))) != own, frame
        assert len(drawn(body)) == len([c for c in body if host.pose.bones[c["nirik_slot"]]["nirik_drawing"]])
        assert all(swap.card_shown(c) == own for c in cards(host, head_slots(T)))


def test_swapping_back_reuses_the_instance():
    host, inst = state["host"], state["inst"]
    assert swap.swap_in(host, T, HOLDER.name, TWIN, HEAD) is inst
    swap.show(host, HOLDER.name, 0, frame=20)
    scene.frame_set(25)
    assert drawn(cards(host, head_slots(T))) and not drawn(cards(inst))
    scene.frame_set(15)
    assert drawn(cards(inst)) and not drawn(cards(host, head_slots(T)))


def test_instance_moves_with_the_layer():
    host, inst = state["host"], state["inst"]
    scene.frame_set(18)  # head turned by the keyed rotation
    bpy.context.view_layer.update()
    pb = host.pose.bones[HOLDER.name]
    deform = host.matrix_world @ pb.matrix @ pb.bone.matrix_local.inverted()
    for p in (Vector((0.1, 0, 0.2)), Vector((-0.3, 0, 0.05))):
        a, b = inst.matrix_world @ p, deform @ p
        assert abs(a.x - b.x) < 1e-5 and abs(a.z - b.z) < 1e-5, (a, b)


def test_depth_lands_between_the_layers_neighbors():
    host, inst = state["host"], state["inst"]
    scene.frame_set(15)
    bpy.context.view_layer.update()
    first, count = T.order_span(HOLDER.name)
    by_order = {c["nirik_order"]: c for c in cards(host)}
    behind, front = by_order[first - 1], by_order[first + count]
    ys = [c.matrix_world.translation.y for c in cards(inst)]
    # The camera looks along +y: nearer cards have smaller y.
    lo, hi = front.matrix_world.translation.y, behind.matrix_world.translation.y
    assert all(lo < y < hi for y in ys), (lo, min(ys), max(ys), hi)
    assert len({round(y, 9) for y in ys}) == len(ys), "cards must not tie in depth"


def _ray_hit(arm, char):
    """A ray from the camera side that hits `arm`'s artwork, or None."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for card in drawn(cards(arm)):
        verts = [card.evaluated_get(depsgraph).matrix_world @ v.co
                 for v in card.evaluated_get(depsgraph).data.vertices]
        for u in (0.3, 0.5, 0.7):
            for v in (0.3, 0.5, 0.7):
                p = verts[0].lerp(verts[1], u).lerp(verts[3].lerp(verts[2], u), v)
                origin, direction = p + Vector((0, -5, 0)), Vector((0, 1, 0))
                if picking.hits(arm, char, origin, direction, depsgraph):
                    return origin, direction
    return None


def test_picking_sees_only_the_head_that_shows():
    host, inst = state["host"], state["inst"]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    scene.frame_set(15)
    ray = _ray_hit(inst, character_for(inst))
    assert ray is not None, "the swapped-in head can be clicked"
    assert not [h for h in picking.hits(host, T, *ray, depsgraph) if h.slot in head_slots(T)]
    scene.frame_set(25)
    assert not picking.hits(inst, character_for(inst), *ray, depsgraph)


def test_swap_a_whole_symbol_onto_a_drawing_layer():
    # The silly one: a whole character where the tail was.
    host = state["host"]
    tail = next(n for n in T.draw_order()[1:-1]  # a layer with neighbors on both sides
                if n not in head_slots(T) and host.pose.bones[n]["nirik_drawing"])
    whole = swap.swap_in(host, T, tail, TWIN, TWIN.root_rig)
    swap.show(host, tail, 1, frame=30)
    scene.frame_set(31)
    bpy.context.view_layer.update()
    assert not drawn(cards(host, {tail})) and drawn(cards(whole))
    first, _ = T.order_span(tail)
    by_order = {c["nirik_order"]: c for c in cards(host)}
    lo, hi = by_order[first + 1].matrix_world.translation.y, by_order[first - 1].matrix_world.translation.y
    assert all(lo < c.matrix_world.translation.y < hi for c in cards(whole))
    scene.frame_set(29)
    assert drawn(cards(host, {tail})) and not drawn(cards(whole))
    state["whole"] = whole


def test_a_swap_inside_a_swap_hides_with_its_host():
    host, inst = state["host"], state["inst"]
    mouth = next(n for n in character_for(inst).draw_order() if inst.pose.bones[n]["nirik_drawing"])
    nested = swap.swap_in(inst, character_for(inst), mouth, T, HEAD)
    swap.show(inst, mouth, 1)  # no key: always
    scene.frame_set(15)  # host shows the twin's head, which shows the nested head
    assert drawn(cards(nested)) and not drawn(cards(inst, {mouth}))
    scene.frame_set(25)  # host back on its own head: the twin's head and what's on it hide
    assert not drawn(cards(nested)) and not drawn(cards(inst))
    state["nested"] = nested


def test_survives_save_and_reload():
    path = Path(tempfile.mkdtemp(prefix="nirik_swap_")) / "swap.blend"
    names = {k: state[k].name for k in ("host", "inst", "whole", "nested")}
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    bpy.ops.wm.open_mainfile(filepath=str(path))  # relinks every instance on load
    host, inst = bpy.data.objects[names["host"]], bpy.data.objects[names["inst"]]
    assert inst.parent is host and character_for(inst).root_rig == HEAD
    sync.sync_now(inst, character_for(inst))  # must not apply the body's poses to the head
    bones = {rig_build._bone_of(fc.data_path) for fc in rig_build._channelbag(inst).fcurves}
    assert bones <= set(inst.pose.bones.keys()), bones - set(inst.pose.bones.keys())
    assert inst.pose.bones["ROOT"]["nirik_construction"] in (0, 1)
    scene = bpy.context.scene
    scene.frame_set(15)
    assert drawn(cards(inst)) and not drawn(cards(host, head_slots(T)))
    scene.frame_set(25)
    assert drawn(cards(host, head_slots(T))) and not drawn(cards(inst))
    state.update({k: bpy.data.objects[n] for k, n in names.items()})


def test_operator_offers_every_library_and_swaps():
    host = state["host"]
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    host.select_set(True)
    bpy.context.view_layer.objects.active = host
    bpy.ops.object.mode_set(mode="POSE")
    host.data.bones.active = host.data.bones[HOLDER.name]
    from nirik import ui
    items = [i[0] for i in ui._swap_items(None, bpy.context)]
    assert items[:2] == ["0", "1"], items[:3]
    assert f"new|{TWIN.root}|{T.root_rig}" in items and f"new|{T.root}|{HEAD}" in items
    assert f"new|{TWIN.root}|{HEAD}" not in items  # already on this layer, listed as "1"
    scene = bpy.context.scene
    scene.frame_set(35)
    scene.tool_settings.use_keyframe_insert_auto = True
    assert bpy.ops.nirik.swap(target=f"new|{T.root}|{HEAD}") == {"FINISHED"}
    assert bpy.context.mode == "POSE" and bpy.context.active_object is host
    own_again = [ob for ob in swap.swapped_in(host, HOLDER.name) if ob["nirik_library"] == str(T.root)]
    assert len(own_again) == 1 and own_again[0] in bpy.context.objects_in_mode
    assert swap.showing(host, HOLDER.name) == own_again[0][swap.INDEX]
    scene.frame_set(34)
    assert swap.showing(host, HOLDER.name) == 0
    bpy.ops.object.mode_set(mode="OBJECT")


harness.run(globals())
