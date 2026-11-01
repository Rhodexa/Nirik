"""Helpers for scripts that run inside Blender (tests/blender/bt_*.py).

A bt_ script defines test_* functions and ends with `harness.run(globals())`.
Renders land in out/blender/; goldens live in tests/blender/goldens/.
"""

import os
import shutil
import sys
import traceback
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
GOLDENS = Path(__file__).parent / "goldens"
OUT = ROOT / "out" / "blender"
UPDATE_GOLDENS = os.environ.get("NIRIK_UPDATE_GOLDENS") == "1"


def load_nirik():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import nirik
    nirik.register()
    return nirik


def clean():
    """Remove scene content so each test starts from an empty scene."""
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials,
                 bpy.data.cameras, bpy.data.actions, bpy.data.images):
        bpy.data.batch_remove(list(coll))
    scene = bpy.context.scene
    scene.world = None
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 1
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    return scene


def load_pixels(path):
    """(H, W, 4) float array of a PNG's stored values (no color conversion)."""
    img = bpy.data.images.load(str(path), check_existing=False)
    try:
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        return buf.reshape(h, w, 4)
    finally:
        bpy.data.images.remove(img)


def save_pixels(path, pixels):
    h, w, _ = pixels.shape
    img = bpy.data.images.new("_nirik_save", w, h, alpha=True)
    try:
        img.pixels.foreach_set(pixels.astype(np.float32).ravel())
        img.filepath_raw = str(path)
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def render(name, frame, scene=None):
    """Render one frame to out/blender/<name>.png; return (path, pixels)."""
    scene = scene or bpy.context.scene
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    scene.frame_set(frame)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return path, load_pixels(path)


def assert_golden(name, path, max_tol=2 / 255, mean_tol=0.5 / 255):
    golden = GOLDENS / f"{name}.png"
    if UPDATE_GOLDENS or not golden.exists():
        GOLDENS.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, golden)
        print(f"NEW GOLDEN {golden.relative_to(ROOT)}")
        return
    got, want = load_pixels(path), load_pixels(golden)
    assert got.shape == want.shape, f"{name}: size {got.shape} != golden {want.shape}"
    diff = np.abs(got - want)
    if diff.max() > max_tol or diff.mean() > mean_tol:
        heat = np.zeros_like(got)
        heat[..., 0] = diff[..., :3].max(axis=2) * 10
        heat[..., 3] = 1
        save_pixels(OUT / f"{name}.diff.png", np.clip(heat, 0, 1))
        raise AssertionError(
            f"{name}: max diff {diff.max() * 255:.1f}/255, mean {diff.mean() * 255:.2f}/255 "
            f"(see out/blender/{name}.diff.png)")


def run(namespace):
    tests = [(n, f) for n, f in namespace.items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc(file=sys.stdout)
    if failed:
        raise SystemExit(f"{failed} of {len(tests)} Blender tests failed")
