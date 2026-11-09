"""First loads that went wrong on real libraries (2026-11-09).

blender ... --python first_load.py -- LIBRARY
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bpy

import harness

lib = Path(sys.argv[sys.argv.index("--") + 1])
harness.load_nirik()
from nirik.bridge import puppet_file, rig_build  # noqa: E402
from nirik.core import library  # noqa: E402

char = library.load(lib)


def nirik_objects():
    return [o for o in bpy.data.objects if "nirik_library" in o or "nirik_slot" in o or "nirik_mask" in o]


def test_failed_build_leaves_nothing_behind():
    harness.clean()
    original = rig_build.build_material
    rig_build.build_material = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        try:
            bpy.ops.nirik.load_character(directory=str(lib))
        except RuntimeError:
            pass
    finally:
        rig_build.build_material = original
    assert nirik_objects() == [], [o.name for o in nirik_objects()]
    assert not [c for c in bpy.data.collections if c.name.startswith("nirik:")]


def test_broken_tile_links_are_repaired_on_first_load():
    # Links made for the old .udim/ depth point nowhere after the move.
    harness.clean()
    for link in (lib / ".nirik" / "palettes").glob("*/t.*.png"):
        if link.is_symlink():
            name = Path(os.readlink(link)).name
            link.unlink()
            link.symlink_to(f"../../drawings/{name}")
    puppet_file.path(char).unlink(missing_ok=True)
    assert bpy.ops.nirik.load_character(directory=str(lib)) == {"FINISHED"}
    arm = bpy.context.active_object
    cards = [o for o in arm.children if "nirik_slot" in o]
    assert len(cards) == len(char.draw_order())


def test_second_copy_writes_the_proper_collection_name():
    # The scene already holds "nirik:<name>"; a rebuild is "nirik:<name>.001"
    # but the library's .blend must still hold "nirik:<name>".
    puppet_file.path(char).unlink(missing_ok=True)
    assert bpy.ops.nirik.load_character(directory=str(lib)) == {"FINISHED"}
    with bpy.data.libraries.load(str(puppet_file.path(char))) as (src, _):
        names = list(src.collections)
    assert names == [puppet_file.collection_name(char)], names
    assert bpy.ops.nirik.load_character(directory=str(lib)) == {"FINISHED"}  # appends


def test_reads_a_dot_001_file_from_older_versions():
    harness.clean()
    arm = rig_build.build(char)
    coll = arm.users_collection[0]
    coll.name = puppet_file.collection_name(char) + ".001"
    bpy.data.libraries.write(str(puppet_file.path(char)), {coll}, fake_user=True)
    harness.clean()
    assert bpy.ops.nirik.load_character(directory=str(lib)) == {"FINISHED"}


harness.run(globals())
