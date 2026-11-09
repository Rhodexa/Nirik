"""Recompose a pose from a Nirik library (PNGs + placements) as SVG.

This is the reference for what the Blender rig must do: walk slots back to
front, place each drawing's canvas through the socket chain, apply socket
color transforms, and clip masked slots with their mask slot's drawing.
Comparing it against a direct render of the source rig validates the library.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from . import evaluate as E
from .render import _mat


class Library:
    """A library read with Nirik's own loader, plus SVG image helpers."""

    def __init__(self, root: Path):
        from nirik.core import library as L
        self.char = L.load(root)
        self.root = self.char.root
        self.ppu = self.char.ppu
        self.rigs = self.char.rigs

    def constructions(self, rig: str):
        return self.rigs[rig].constructions

    @lru_cache(maxsize=None)
    def href(self, drawing: int) -> str:
        png = self.char.drawing_path(drawing).read_bytes()
        return "data:image/png;base64," + base64.b64encode(png).decode()

    def drawing_xf(self, slot, world: E.Mat) -> E.Mat:
        """Canvas pixels -> world: world ∘ translate(canvas origin) ∘ scale(1/ppu)."""
        x0, y0 = slot.canvas[:2]
        return E.mat_mul(world, (1 / self.ppu, 0, 0, 1 / self.ppu, x0, y0))

    def image(self, slot, drawing: int, world: E.Mat) -> str:
        x0, y0, x1, y1 = slot.canvas
        w, h = round((x1 - x0) * self.ppu), round((y1 - y0) * self.ppu)
        return (f'<image transform="{_mat(self.drawing_xf(slot, world))}" width="{w}" height="{h}" '
                f'href="{self.href(drawing)}"/>')


def _color(entry, parent: E.ColorXf) -> E.ColorXf:
    c = entry.color
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
        cons = rig.constructions[cid].slots
        by_name = {s.name: s for s in rig.slots}
        for slot in rig.slots:  # back to front
            entry = cons.get(slot.name)
            if entry is None or slot.mask:
                continue
            m = E.mat_mul(world, entry.matrix)
            c = _color(entry, color)
            if slot.child_rig:
                walk(slot.child_rig, entry.construction, m, c)
                continue
            if not entry.drawing or slot.canvas is None:
                continue
            el = lib.image(slot, entry.drawing, m)
            if not c.is_identity:
                el = f'<g filter="url(#{color_filter(c)})">{el}</g>'
            mask_entry = cons.get(slot.masked_by) if slot.masked_by else None
            if mask_entry is not None and mask_entry.drawing:  # empty masks mask nothing
                mid = f"m{len(defs)}"
                mask_img = lib.image(by_name[slot.masked_by], mask_entry.drawing,
                                     E.mat_mul(world, mask_entry.matrix))
                defs.append(f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="0" y="0" width="{width}" '
                            f'height="{height}" style="mask-type:alpha">{mask_img}</mask>')
                el = f'<g mask="url(#{mid})">{el}</g>'
            body.append(el)

    walk(rig, construction, world, E.COLOR_IDENTITY)
    bg = f'<rect width="{width}" height="{height}" fill="{background}"/>' if background else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
            f'<defs>{"".join(defs)}</defs>{bg}{"".join(body)}</svg>')
