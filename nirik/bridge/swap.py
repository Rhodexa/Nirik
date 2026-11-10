"""Swapping: a layer shows another symbol from some frame on.

Any symbol of any library can go on any layer of a placed symbol (the
host): Rarity's head on Twilight's head layer, a standing head on a walk,
an eye on an eye. The swapped-in symbol is its own instance, an armature
built from that symbol alone and hung from the layer's bone, so it lands
where the layer's own content was and moves with it.

Which one shows is a keyed value on the layer's bone, `nirik_swap`:
0 is the layer's own content, k the k-th instance swapped onto it. Cards
read it through their tile driver (tile -1 draws nothing), so playback and
renders stay Python-free. Nothing already keyed is touched by a swap.
"""

from __future__ import annotations

import bpy
from mathutils import Matrix

from ..core import library as L
from . import rig_build

SWAP = "nirik_swap"          # on a layer bone: which content shows
SYMBOL = "nirik_symbol"      # on an instance: the symbol it was built from, if not the root
INDEX = "nirik_swap_index"   # on a swapped-in instance: its number on the host layer
# How much of a layer's draw-order slot its replacement may fill: a little
# less than the whole, so it never ties with the neighbors' depth.
FILL = 0.9


def _swap_path(bone: str) -> str:
    return f'pose.bones["{bone}"]["{SWAP}"]'


def is_instance(ob) -> bool:
    return ob is not None and ob.type == "ARMATURE" and "nirik_library" in ob


def host_of(arm):
    """(host armature, layer) a swapped-in instance hangs from, or (None, None)."""
    if arm.get(INDEX) and is_instance(arm.parent) and arm.parent_type == "BONE":
        return arm.parent, arm.parent_bone
    return None, None


def swapped_in(host, bone: str) -> list:
    """Instances swapped onto `bone`, by their number."""
    found = [ob for ob in host.children if is_instance(ob) and host_of(ob) == (host, bone)]
    return sorted(found, key=lambda ob: ob[INDEX])


def showing(host, bone: str) -> int:
    pb = host.pose.bones[bone]
    return int(round(pb.get(SWAP, 0)))


def _layer_chain(arm, slot: str) -> list[str]:
    """`slot` and the layers holding it, innermost first (bones, not helpers)."""
    out = []
    bone = arm.data.bones.get(slot)
    while bone is not None:
        if bone.name != "ROOT" and not bone.name.endswith((".SOCKET", ".SKEW")):
            out.append(bone.name)
        bone = bone.parent
    return out


def shown_terms(arm, slot: str) -> list[tuple[object, str, int]]:
    """What must hold for `slot`'s card to show: (object, data path, value)."""
    terms = [(arm, _swap_path(b), 0) for b in _layer_chain(arm, slot) if SWAP in arm.pose.bones[b]]
    host, bone = host_of(arm)
    if host is not None:
        terms.append((host, _swap_path(bone), arm[INDEX]))
        terms += [t for t in shown_terms(host, bone) if t[1] != _swap_path(bone)]
    return terms


def card_shown(card) -> bool:
    """Whether a card's layer is showing its own content (ignores the drawing)."""
    return all(round(owner.path_resolve(path)) == value
               for owner, path, value in shown_terms(card.parent, card["nirik_slot"]))


def refresh_visibility(arm):
    """Rewrite every card's tile driver of `arm` and of the instances hanging
    from it, so each card draws only while its branch is the one showing."""
    for card in [c for c in arm.children if "nirik_slot" in c]:
        slot = card["nirik_slot"]
        terms = shown_terms(arm, slot)
        card.driver_remove('["nirik_tile"]')
        extra = {f"w{i}": (owner, path) for i, (owner, path, _) in enumerate(terms)}
        cond = " and ".join(f"w{i} == {value}" for i, (_, _, value) in enumerate(terms))
        rig_build._drive(card, "nirik_tile", -1, arm, slot, "nirik_tile",
                         expression=f"v if {cond} else -1" if cond else "v", extra=extra)
    for child in arm.children:
        if is_instance(child) and host_of(child)[0] is arm:
            refresh_visibility(child)


def _depth_map(host, host_char: L.Character, bone: str, cards: int) -> Matrix:
    """Squeeze an instance's stack (card orders 0..cards-1) into the depth
    range the layer's own content uses in the host, so it is drawn at the
    layer's place between the host's other cards."""
    first, count = host_char.order_span(bone)
    if count:
        lo, hi = first - FILL / 2, first + count - 1 + FILL / 2
    else:  # an empty layer: the gap before the next drawing
        lo, hi = first - 0.5 - FILL / 2, first - 0.5 + FILL / 2
    k = (hi - lo) / max(cards, 1)
    # Cards sit at y = -order * ORDER_STEP; map order r to lo + (r + 0.5) * k.
    return Matrix.Translation((0, -(lo + 0.5 * k) * rig_build.ORDER_STEP, 0)) @ Matrix.Diagonal((1, k, 1, 1))


def swap_in(host, host_char: L.Character, bone: str, char: L.Character, symbol: str):
    """Hang `symbol` of `char`'s library from the host's layer `bone`, or
    return the instance already there. Needs Object mode. Returns it."""
    for ob in swapped_in(host, bone):
        if ob["nirik_library"] == str(char.root) and ob.get(SYMBOL, char.root_rig) == symbol:
            return ob
    sub = char.subtree(symbol)
    arm = rig_build.build(sub, collection=host.users_collection[0],
                          units_per_meter=host["nirik_units_per_meter"])
    label = char.rigs[symbol].label or symbol
    arm.name = arm.data.name = f"{char.name}:{label}"
    arm[SYMBOL] = symbol
    arm[INDEX] = max([ob[INDEX] for ob in swapped_in(host, bone)], default=0) + 1
    rig_build.apply_construction(arm, sub, sub.root_rig, 0)

    pb = host.pose.bones[bone]
    if SWAP not in pb:
        pb[SWAP] = 0
        pb.id_properties_ui(SWAP).update(min=0, description="Which symbol this layer shows: 0 is its own")
    rest = host.data.bones[bone]
    arm.parent, arm.parent_type, arm.parent_bone = host, "BONE", bone
    # Bone parenting hangs a child from the bone's tail, in bone space; the
    # layer's own content is placed by the bone's deform (pose @ rest^-1).
    arm.matrix_parent_inverse = (Matrix.Translation((0, -rest.length, 0)) @ rest.matrix_local.inverted()
                                 @ _depth_map(host, host_char, bone, len(sub.draw_order())))
    arm.matrix_basis = Matrix.Identity(4)
    top = host
    while host_of(top)[0] is not None:
        top = host_of(top)[0]
    refresh_visibility(top)
    return arm


def show(host, bone: str, index: int, frame: int | None = None):
    """Show content `index` on the layer (0: its own), keyed at `frame` if
    given. The first key also keys what showed before, one frame earlier,
    so earlier frames keep it."""
    pb = host.pose.bones[bone]
    path = f'["{SWAP}"]'
    if frame is not None:
        bag = rig_build._channelbag(host)
        full = f"pose.bones[\"{bone}\"]{path}"
        if bag is None or bag.fcurves.find(full) is None:
            pb.keyframe_insert(path, frame=frame - 1)
    pb[SWAP] = index
    if frame is not None:
        pb.keyframe_insert(path, frame=frame)
        rig_build.make_constant(host)
    host.update_tag()
