"""Props from images: one picture, or a sprite sheet split into drawings.

A prop is an ordinary Nirik library with one rig ("Prop") and one part
("Prop.Art") whose drawings are the sheet's pieces, centered on a shared
canvas so swapping never jumps. Everything else (browser, layers, depth,
keys) works as for characters.
"""

from __future__ import annotations

import json
from pathlib import Path

import bpy
import numpy as np

from ..core import islands as I
from ..core import library as L
from . import rig_build

SLOT = "Prop.Art"


def _load_rgba(path: Path) -> np.ndarray:
    """(H, W, 4) float, top row first."""
    img = bpy.data.images.load(str(path), check_existing=False)
    try:
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1].copy()


def _save_rgba(path: Path, rgba: np.ndarray):
    h, w, _ = rgba.shape
    img = bpy.data.images.new("_nirik_prop", w, h, alpha=True)
    try:
        img.pixels.foreach_set(np.ascontiguousarray(rgba[::-1]).ravel())
        img.filepath_raw = str(path)
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def bleed(rgba: np.ndarray, steps: int = 8) -> np.ndarray:
    """Spread edge colors into fully transparent pixels (alpha unchanged), so
    texture filtering never darkens edges."""
    rgb, known = rgba[..., :3].copy(), rgba[..., 3] > 0
    for _ in range(steps):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(known.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            k = np.roll(known, (dy, dx), axis=(0, 1))
            acc += np.roll(rgb, (dy, dx), axis=(0, 1)) * k[..., None]
            cnt += k
        grow = ~known & (cnt > 0)
        rgb[grow] = acc[grow] / cnt[grow][:, None]
        known |= grow
    out = rgba.copy()
    out[..., :3] = rgb
    return out


def import_prop(image: Path, name: str, out: Path, height: float, split: bool = True,
                pivot: str = "AUTO", margin: int = 12) -> Path:
    """Write library `out` from `image`. `height`: meters of the tallest piece.
    pivot: BOTTOM (stands on the ground), CENTER, or AUTO (bottom for a single
    picture, center for sheets)."""
    rgba = _load_rgba(image)
    h, w, _ = rgba.shape
    alpha = rgba[..., 3]
    boxes = I.islands(alpha) if split else []
    if not boxes:
        ys, xs = np.nonzero(alpha > 0)
        if not len(xs):
            raise ValueError(f"{image}: nothing visible")
        boxes = [(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)]
    boxes = [I.grow(b, margin, w, h) for b in boxes]
    cw = max(b[2] - b[0] for b in boxes)
    ch = max(b[3] - b[1] for b in boxes)
    if pivot == "AUTO":
        pivot = "BOTTOM" if len(boxes) == 1 else "CENTER"

    out = Path(out)
    (out / "drawings").mkdir(parents=True, exist_ok=True)
    drawings = {}
    for i, (x0, y0, x1, y1) in enumerate(boxes, 1):
        canvas = np.zeros((ch, cw, 4), dtype=np.float32)
        ox, oy = (cw - (x1 - x0)) // 2, (ch - (y1 - y0)) if pivot == "BOTTOM" else (ch - (y1 - y0)) // 2
        canvas[oy:oy + y1 - y0, ox:ox + x1 - x0] = rgba[y0:y1, x0:x1]
        _save_rgba(out / "drawings" / f"{i}.png", bleed(canvas))
        drawings[str(i)] = {"slot": SLOT, "symbol": name, "frames": [i - 1], "tags": [f"#{i}"]}

    # Library units: rig_build.UNITS_PER_METER per meter; ppu = canvas pixels per unit.
    ppu = (ch - 2 * margin) / (height * rig_build.UNITS_PER_METER)
    uw, uh = cw / ppu, ch / ppu
    top = -uh if pivot == "BOTTOM" else -uh / 2  # library y points down
    data = {
        "schema": L.SCHEMA, "name": name, "ppu": ppu, "root_rig": "Prop",
        "source": {"file": image.name, "pieces": len(boxes)},
        "rigs": {"Prop": {"symbol": name, "slots": [
            {"name": SLOT, "layer": "ART", "order": 0, "canvas": [-uw / 2, top, uw / 2, top + uh]}],
            "constructions": [{"id": 0, "frames": [0], "labels": [],
                               "slots": {SLOT: {"matrix": [1, 0, 0, 1, 0, 0], "drawing": 1}}}]}},
        "drawings": drawings,
    }
    (out / "character.json").write_text(json.dumps(data, indent=1))
    return out


# ── facing the camera ────────────────────────────────────────────────────────

FACE_CAMERA = "Nirik Face Camera"


def face_camera(arm, on: bool, camera=None):
    """Keep the puppet turned toward the camera, upright (rotating about Z).
    The constraint's Influence is keyable: drop it to 0 for the reveal."""
    con = arm.constraints.get(FACE_CAMERA)
    if not on:
        if con is not None:
            arm.constraints.remove(con)
        return
    if con is None:
        con = arm.constraints.new("LOCKED_TRACK")
        con.name = FACE_CAMERA
        con.track_axis = "TRACK_NEGATIVE_Y"  # cards face -Y
        con.lock_axis = "LOCK_Z"
    con.target = camera or bpy.context.scene.camera
