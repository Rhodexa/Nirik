"""Nirik: drawing-based 2D puppets inside Blender scenes.

Layers:
  core/    pure Python, never imports bpy (tested with plain pytest)
  bridge/  the only layer that reads or writes bpy data
  ui/      panels, operators, tools, overlays

bpy-dependent modules are imported inside register(), so `import nirik.core`
works outside Blender.
"""

import sys

# F3 > Reload Scripts re-executes this file but keeps submodules cached.
# Drop them so register() imports fresh code.
for _name in [n for n in sys.modules if n.startswith(__name__ + ".")]:
    del sys.modules[_name]


def register():
    from . import ui
    ui.register()


def unregister():
    from . import ui
    ui.unregister()
