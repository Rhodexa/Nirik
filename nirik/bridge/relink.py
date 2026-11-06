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
from . import rig_build

SEARCH_LEVELS = 4  # how many folders above the .blend to look in


def find_library(old_path: str, blend_path: str) -> Path | None:
    """Same library folder name ("library/twilight") near the .blend."""
    old = Path(old_path)
    if (old / "character.json").exists():
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
            if (candidate / "character.json").exists():
                return candidate
    return None


def repair_palettes(arm, char: L.Character):
    """Recreate missing or dangling tile links and re-point palette images."""
    for slot, drawings in arm["nirik_palettes"].items():
        folder = rig_build.palette_dir(char, slot)
        folder.mkdir(parents=True, exist_ok=True)
        for i, drawing in enumerate(drawings):
            link = folder / f"t.{1001 + i}.png"
            if not link.exists():  # missing, or a dangling symlink
                if link.is_symlink():
                    link.unlink()
                os.symlink(os.path.relpath(char.drawing_path(drawing), folder), link)
        image = bpy.data.images.get(f"nirik:{char.name}:{slot}")
        if image is not None:
            wanted = str(folder / "t.<UDIM>.png")
            if image.filepath != wanted:
                image.filepath = wanted
            image.reload()


def relink(arm) -> bool:
    """Make `arm`'s library path and tiles valid; False if the library is lost."""
    found = find_library(arm["nirik_library"], bpy.data.filepath)
    if found is None:
        return False
    arm["nirik_library"] = str(found.resolve())
    repair_palettes(arm, L.load(found))
    return True


@persistent
def on_load(_filepath):
    lost = [ob.name for ob in bpy.data.objects
            if ob.type == "ARMATURE" and "nirik_library" in ob and not relink(ob)]
    if lost:
        print(f"Nirik: library not found for {', '.join(lost)}; use Load Character or move it back")


def register():
    bpy.app.handlers.load_post.append(on_load)


def unregister():
    if on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load)
