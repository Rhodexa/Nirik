"""The assembled puppet as a .blend in its library folder.

`<library>/<name>.blend` holds exactly one collection, "nirik:<name>": the
armature, cards, masks, materials and textures, ready for File > Append.
Nirik writes it the first time a library is loaded and rebuilds it when the
library description is newer; later loads simply append from it.
"""

from __future__ import annotations

from pathlib import Path

import bpy

from ..core import library as L
from . import relink


def path(char: L.Character) -> Path:
    return char.root / f"{char.name}.blend"


def collection_name(char: L.Character) -> str:
    return f"nirik:{char.name}"


def is_current(char: L.Character) -> bool:
    blend, description = path(char), L.description(char.root)
    return blend.exists() and blend.stat().st_mtime >= description.stat().st_mtime


def write(arm, char: L.Character):
    """Save the puppet's collection (and everything it uses) as its .blend,
    always under its proper name: a scene that already has "nirik:rarity"
    makes a new one "nirik:rarity.001", which must not end up in the file."""
    name = collection_name(char)
    coll = next(c for c in arm.users_collection if c.name.startswith(name))
    other = bpy.data.collections.get(name) if coll.name != name else None
    if other is not None:
        other.name = name + ".nirik-tmp"
    original, coll.name = coll.name, name
    try:
        bpy.data.libraries.write(str(path(char)), {coll}, fake_user=True, compress=True)
    finally:
        coll.name = original
        if other is not None:
            other.name = name


def append(char: L.Character, scene=None):
    """Append the puppet from its .blend into `scene`; returns the armature."""
    scene = scene or bpy.context.scene
    name = collection_name(char)
    with bpy.data.libraries.load(str(path(char)), link=False) as (src, dst):
        # its proper name, or a ".001" one written by older versions
        found = [c for c in src.collections if c == name or c.startswith(name + ".")]
        if not found:
            raise ValueError(f"{path(char)} holds no {name} collection")
        dst.collections = [sorted(found, key=len)[0]]
    coll = dst.collections[0]
    scene.collection.children.link(coll)
    arm = next(o for o in coll.objects if "nirik_library" in o)
    # It belongs to the library it was loaded from, even if the .blend was
    # written elsewhere (a copied folder). Then the same steps as for a
    # File > Append: tiles, shared textures.
    arm["nirik_library"] = str(char.root)
    for ob in coll.objects:
        for slot in ob.material_slots:
            for node in (slot.material.node_tree.nodes if slot.material and slot.material.node_tree else ()):
                if node.type == "TEX_IMAGE" and node.image and "nirik_slot" in node.image:
                    node.image["nirik_library"] = str(char.root)
    relink.adopt_new_puppets()
    return arm
