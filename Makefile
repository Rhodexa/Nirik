PY      := .venv/bin/python
# Recursive (=) so Blender is only queried by targets that need it.
EXT_DIR  = $(shell $(PY) -m devtools.blender_env --extensions-dir)

.PHONY: test test-core test-blender goldens blender link unlink validate build census demo

test:                 ## everything
	$(PY) -m pytest -s

test-core:            ## fast, no Blender
	$(PY) -m pytest tests/core -q

test-blender:         ## headless Blender scripts
	$(PY) -m pytest -m blender -s

goldens:              ## accept current renders as golden images
	NIRIK_UPDATE_GOLDENS=1 $(PY) -m pytest -m blender -s

blender:              ## launch Blender with the dev environment (OCIO fix)
	$(PY) -m devtools.blender_env

link:                 ## symlink nirik/ into Blender's extensions and enable it
	mkdir -p $(EXT_DIR)
	ln -sfn $(CURDIR)/nirik $(EXT_DIR)/nirik
	$(PY) -m devtools.blender_env -b --python-expr \
	  "import bpy; bpy.ops.preferences.addon_enable(module='bl_ext.user_default.nirik'); bpy.ops.wm.save_userpref()"

unlink:
	rm -f $(EXT_DIR)/nirik

validate:
	$(PY) -m devtools.blender_env --command extension validate nirik

build:                ## installable zip in dist/
	mkdir -p dist
	$(PY) -m devtools.blender_env --command extension build --source-dir nirik --output-dir dist

SCENES ?= ../FLA-RE/fla/S08E23
census:               ## feature census over FLA scenes (SCENES=dir)
	$(PY) -m devtools.flash.census $(SCENES) --out out/census/$(notdir $(SCENES)) --jobs 6

CHAR ?= library/twilight
demo:                 ## open Blender with a character loaded (CHAR=library/<name>)
	$(PY) -m devtools.blender_env --python devtools/blender_demo.py -- $(abspath $(CHAR))
