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
    """Save the puppet's collection (and everything it uses) as its .blend."""
    coll = next(c for c in arm.users_collection if c.name.startswith(collection_name(char)))
    bpy.data.libraries.write(str(path(char)), {coll}, fake_user=True, compress=True)


def append(char: L.Character, scene=None):
    """Append the puppet from its .blend into `scene`; returns the armature."""
    scene = scene or bpy.context.scene
    with bpy.data.libraries.load(str(path(char)), link=False) as (src, dst):
        dst.collections = [collection_name(char)]
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
