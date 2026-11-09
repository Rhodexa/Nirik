"""Keep hidden (compiled) channels in step with the animator's keys.

The armature stores a fingerprint of its authoring keys (constructions and
drawings) as of the last compile. Living in the file's data, it is restored
by undo together with the keys, so undo never looks out of sync. A
depsgraph handler notices a mismatch after Dope Sheet / Graph Editor edits
and schedules a rebuild on a timer, never writing data inside the handler.
"""

from __future__ import annotations

import hashlib

import bpy
from bpy.app.handlers import persistent

from ..core import library as L
from . import rig_build

FINGERPRINT = "nirik_synced"
DELAY = 0.25  # seconds; drags in the Dope Sheet settle before we rebuild

_pending: set[str] = set()  # armature names with a scheduled rebuild


def fingerprint(arm) -> str:
    bag = rig_build._channelbag(arm)
    h = hashlib.blake2b(digest_size=12)
    if bag is not None:
        for fc in sorted(bag.fcurves, key=lambda f: (f.data_path, f.array_index)):
            if rig_build.is_compiled(fc.data_path) or "nirik_" not in fc.data_path:
                continue
            h.update(fc.data_path.encode())
            for kp in fc.keyframe_points:
                h.update(f"{kp.co[0]:.3f}:{kp.co[1]:.3f};".encode())
    return h.hexdigest()


def mark_synced(arm):
    arm[FINGERPRINT] = fingerprint(arm)


def out_of_sync(arm) -> bool:
    return arm.get(FINGERPRINT) != fingerprint(arm)


def sync_now(arm, char: L.Character):
    rig_build.rebuild_compiled(arm, char)
    mark_synced(arm)


def _run(name: str):
    _pending.discard(name)
    arm = bpy.data.objects.get(name)
    if arm is None or "nirik_library" not in arm or not out_of_sync(arm):
        return None
    from ..ui import character_for  # cached library per armature
    sync_now(arm, character_for(arm))
    bpy.context.scene.frame_set(bpy.context.scene.frame_current)
    return None


_adopt_pending = False


def _adopt():
    global _adopt_pending
    _adopt_pending = False
    from . import relink
    relink.adopt_new_puppets()
    return None


@persistent
def on_depsgraph_update(scene, depsgraph):
    global _adopt_pending
    if not any(isinstance(u.id, (bpy.types.Action, bpy.types.Object)) for u in depsgraph.updates):
        return
    # File > Append has no notification: a puppet we haven't seen gets adopted
    # (library path, tiles, shared textures) on a timer, outside the handler.
    from . import relink
    if not _adopt_pending and any("nirik_library" in ob and ob.session_uid not in relink._adopted
                                  for ob in scene.objects if ob.type == "ARMATURE"):
        _adopt_pending = True
        bpy.app.timers.register(_adopt, first_interval=0.1)
    for ob in scene.objects:
        if ob.type == "ARMATURE" and "nirik_library" in ob and ob.name not in _pending:
            ob = ob.original
            if out_of_sync(ob):
                _pending.add(ob.name)
                bpy.app.timers.register(lambda n=ob.name: _run(n), first_interval=DELAY)


def register():
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)


def unregister():
    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
    _pending.clear()
