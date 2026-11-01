"""Recompose a construction from a Nirik library (PNGs + sockets) as SVG.

This is the reference for what the Blender rig must do: walk slots back to
front, place each drawing's canvas through the socket chain, apply socket
color transforms, and clip masked slots with their mask slot's drawing.
Comparing it against a direct render of the source rig validates the library.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path

from . import evaluate as E
from .render import _mat


class Library:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.data = json.loads((self.root / "character.json").read_text())
        self.ppu = self.data["ppu"]
        self.rigs = self.data["rigs"]

    @lru_cache(maxsize=None)
    def href(self, drawing: int) -> str:
        png = (self.root / "drawings" / f"{drawing}.png").read_bytes()
        return "data:image/png;base64," + base64.b64encode(png).decode()

    def drawing_xf(self, slot: dict, world: E.Mat) -> E.Mat:
        """Canvas pixels -> world: world ∘ translate(canvas origin) ∘ scale(1/ppu)."""
        x0, y0 = slot["canvas"][:2]
        return E.mat_mul(world, (1 / self.ppu, 0, 0, 1 / self.ppu, x0, y0))

    def image(self, slot: dict, drawing: int, world: E.Mat) -> str:
        x0, y0, x1, y1 = slot["canvas"]
        w, h = round((x1 - x0) * self.ppu), round((y1 - y0) * self.ppu)
        return (f'<image transform="{_mat(self.drawing_xf(slot, world))}" width="{w}" height="{h}" '
                f'href="{self.href(drawing)}"/>')


def _color(entry: dict, parent: E.ColorXf) -> E.ColorXf:
    c = entry.get("color")
    own = E.ColorXf(tuple(c[:4]), tuple(c[4:])) if c else E.COLOR_IDENTITY
    return own.then(parent)


def compose_svg(lib: Library, rig: str, construction: int, world: E.Mat, width: int, height: int,
                background: str | None = None) -> str:
    defs: list[str] = []
    body: list[str] = []
    filters: dict = {}

    def color_filter(xf: E.ColorXf) -> str:
        if xf not in filters:
            fid = f"c{len(filters)}"
            (mr, mg, mb, ma), (o_r, og, ob, oa) = xf.mult, xf.off
            defs.append(
                f'<filter id="{fid}" filterUnits="userSpaceOnUse" x="0" y="0" width="{width}" '
                f'height="{height}" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" '
                f'values="{mr} 0 0 0 {o_r / 255} 0 {mg} 0 0 {og / 255} 0 0 {mb} 0 {ob / 255} '
                f'0 0 0 {ma} {oa / 255}"/></filter>')
            filters[xf] = fid
        return filters[xf]

    def walk(rig_name: str, cid: int, world: E.Mat, color: E.ColorXf):
        rig = lib.rigs[rig_name]
        cons = rig["constructions"][cid]["slots"]
        by_name = {s["name"]: s for s in rig["slots"]}
        for slot in rig["slots"]:  # sorted back to front
            entry = cons.get(slot["name"])
            if entry is None or slot.get("mask"):
                continue
            m = E.mat_mul(world, entry["matrix"])
            c = _color(entry, color)
            if "rig" in slot:
                walk(slot["rig"], entry["construction"], m, c)
                continue
            if not entry.get("drawing") or "canvas" not in slot:
                continue
            el = lib.image(slot, entry["drawing"], m)
            if not c.is_identity:
                el = f'<g filter="url(#{color_filter(c)})">{el}</g>'
            mask_name = slot.get("masked_by")
            if mask_name:
                mask_entry = cons.get(mask_name)
                if mask_entry is None or not mask_entry.get("drawing"):
                    continue  # nothing shows through an empty mask
                mid = f"m{len(defs)}"
                mask_img = lib.image(by_name[mask_name], mask_entry["drawing"],
                                     E.mat_mul(world, mask_entry["matrix"]))
                defs.append(f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="0" y="0" width="{width}" '
                            f'height="{height}" style="mask-type:alpha">{mask_img}</mask>')
                el = f'<g mask="url(#{mid})">{el}</g>'
            body.append(el)

    walk(rig, construction, world, E.COLOR_IDENTITY)
    bg = f'<rect width="{width}" height="{height}" fill="{background}"/>' if background else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
            f'<defs>{"".join(defs)}</defs>{bg}{"".join(body)}</svg>')
