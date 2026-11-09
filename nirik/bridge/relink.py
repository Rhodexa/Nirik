"""Repair puppets whose library moved (project folder renamed, files copied).

Runs when a .blend is opened: a character whose stored library path is gone
is re-pointed to the nearest `library/<name>` found next to the .blend, in
its parent folders or their sibling projects, or in the add-on's own project, and every palette's tile links are rebuilt, since they
point into the library.
"""

from __future__ import annotations

import os
from pathlib import Path

import bpy
from bpy.app.handlers import persistent

from ..core import library as L
from . import rig_build, sync

SEARCH_LEVELS = 4  # how many folders above the .blend to look in


def find_library(old_path: str, blend_path: str) -> Path | None:
    """Same library folder name ("library/twilight") near the .blend."""
    old = Path(old_path)
    if L.description(old).exists():
        return old
    tail = Path(*old.parts[-2:])  # e.g. library/twilight
    folders = []
    if blend_path:
        folder = Path(blend_path).resolve().parent
        for _ in range(SEARCH_LEVELS):
            # the folder itself, then sibling projects (Studio/<project>/library/...)
            folders.append(folder)
            folders += sorted(p for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []
            folder = folder.parent
    # the add-on's own project (dev setup: <project>/nirik is the extension)
    folders.append(Path(__file__).resolve().parents[2])
    for folder in folders:
        for candidate in (folder / tail, folder / old.name):
            if L.description(candidate).exists():
                return candidate
    return None


def repair_palettes(arm, char: L.Character):
    """Make tiles and palette images valid again, and every part's tile index
    match its drawing in the shared palette."""
    # Files from before shared palettes kept one list per puppet: seed the
    # shared palette from it so existing tile numbers stay meaningful.
    for slot, drawings in dict(arm.get("nirik_palettes", {})).items():
        if not rig_build.palette(char, slot):
            rig_build._write_palette(char, slot, list(drawings))
    slots = char.all_slots()
    for slot in slots:
        pal = rig_build.palette(char, slot)
        if not pal:
            continue
        folder = rig_build.palette_dir(char, slot)
        rig_build.repair_links(char, slot)
        for image in rig_build.palette_images(char, slot):
            wanted = str(folder / "t.<UDIM>.png")
            if image.filepath != wanted:
                image.filepath = wanted
            rig_build.sync_tiles(image, char, slot)
    for name in slots:
        pb = arm.pose.bones.get(name)
        if pb is not None and pb.get("nirik_drawing"):
            pb["nirik_tile"] = rig_build.ensure_in_palette(char, name, pb["nirik_drawing"])
    sync.sync_now(arm, char)  # keyed tiles too


def relink(arm) -> bool:
    """Make `arm`'s library path and tiles valid; False if the library is lost."""
    found = find_library(arm["nirik_library"], bpy.data.filepath)
    if found is None:
        return False
    old_root = arm["nirik_library"]
    arm["nirik_library"] = str(found.resolve())
    char = L.load(found)
    for im in bpy.data.images:  # textures remember their library too
        if im.get("nirik_library") == old_root:
            im["nirik_library"] = str(char.root)
    rig_build.tag_legacy(arm, char)
    repair_palettes(arm, char)
    return True


@persistent
def on_load(_filepath):
    _adopted.clear()
    lost = [ob.name for ob in bpy.data.objects
            if ob.type == "ARMATURE" and "nirik_library" in ob and not relink(ob)]
    _adopted.update(ob.session_uid for ob in bpy.data.objects if "nirik_library" in ob)
    share_textures()
    if lost:
        print(f"Nirik: library not found for {', '.join(lost)}; use Load Character or move it back")


def register():
    bpy.app.handlers.load_post.append(on_load)


def unregister():
    if on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load)


def share_textures():
    """Copies of one puppet (File > Append twice) bring their own textures;
    point every copy at one texture per library layer so GPU memory isn't
    doubled. Safe to run any time."""
    keep: dict[tuple[str, str], bpy.types.Image] = {}
    for image in list(bpy.data.images):
        key = (image.get("nirik_library"), image.get("nirik_slot"))
        if None in key or image.library is not None:
            continue
        if key in keep:
            image.user_remap(keep[key])
            bpy.data.images.remove(image)
        else:
            keep[key] = image


_adopted: set[int] = set()  # session_uid of puppets already checked this session


def adopt_new_puppets() -> bool:
    """Make newly appended puppets valid: library path, tiles, shared
    textures. Returns whether anything was new."""
    new = [ob for ob in bpy.data.objects
           if ob.type == "ARMATURE" and "nirik_library" in ob and ob.session_uid not in _adopted]
    for ob in new:
        _adopted.add(ob.session_uid)
        relink(ob)
    if new:
        share_textures()
    return bool(new)
