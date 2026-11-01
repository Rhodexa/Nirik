"""Render evaluated frames to SVG/PNG: the reference ("oracle") images.

Shape geometry comes from FLA-RE. Color transforms are applied per leaf, as
Flash does (an instance's alpha lets its own overlapping parts show through
each other). Consecutive leaves sharing a mask stack share one mask group.
"""

from __future__ import annotations

from pathlib import Path

import resvg_py

from .evaluate import ColorXf, Node
from .fla import FI


def _mat(m) -> str:
    return "matrix({:.6g},{:.6g},{:.6g},{:.6g},{:.6g},{:.6g})".format(*m)


class _SvgBuilder:
    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.defs: list[str] = []
        self.grad_cache: dict = {}
        self.filters: dict[ColorXf, str] = {}
        self.mask_ids: dict[int, str] = {}

    def color_filter(self, xf: ColorXf) -> str:
        if xf not in self.filters:
            fid = f"cx{len(self.filters)}"
            (mr, mg, mb, ma), (or_, og, ob, oa) = xf.mult, xf.off
            values = (f"{mr:.6g} 0 0 0 {or_ / 255:.6g} 0 {mg:.6g} 0 0 {og / 255:.6g} "
                      f"0 0 {mb:.6g} 0 {ob / 255:.6g} 0 0 0 {ma:.6g} {oa / 255:.6g}")
            self.defs.append(
                f'<filter id="{fid}" filterUnits="userSpaceOnUse" x="0" y="0" '
                f'width="{self.width}" height="{self.height}" color-interpolation-filters="sRGB">'
                f'<feColorMatrix type="matrix" values="{values}"/></filter>')
            self.filters[xf] = fid
        return self.filters[xf]

    def mask(self, clip) -> str:
        key = id(clip)
        if key not in self.mask_ids:
            mid = f"m{len(self.mask_ids)}"
            body = []
            for n in clip.nodes:
                body += [f'<g transform="{_mat(n.matrix)}">',
                         *FI._shape_svg_white(n.element, _in_group=n.in_group), "</g>"]
            self.defs += [f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="0" y="0" '
                          f'width="{self.width}" height="{self.height}" style="mask-type:alpha">',
                          *body, "</mask>"]
            self.mask_ids[key] = mid
        return self.mask_ids[key]

    def leaf(self, n: Node) -> list[str]:
        if n.kind != "shape":
            return []
        inner = FI._shape_svg(n.element, self.defs, self.grad_cache, _in_group=n.in_group)
        if not inner:
            return []
        lines = [f'<g transform="{_mat(n.matrix)}">', *inner, "</g>"]
        if not n.color.is_identity:
            # Filter on an untransformed wrapper so its region is the canvas.
            lines = [f'<g filter="url(#{self.color_filter(n.color)})">', *lines, "</g>"]
        return lines


def frame_svg(nodes: list[Node], width: int, height: int, background: str | None = None) -> str:
    b = _SvgBuilder(width, height)
    body: list[str] = []
    open_masks: list = []  # currently open mask clips, outermost first
    for n in nodes:
        lines = b.leaf(n)
        if not lines:
            continue
        common = 0
        while (common < len(open_masks) and common < len(n.masks)
               and open_masks[common] is n.masks[common]):
            common += 1
        for _ in range(len(open_masks) - common):
            body.append("</g>")
        del open_masks[common:]
        for clip in n.masks[common:]:
            body.append(f'<g mask="url(#{b.mask(clip)})">')
            open_masks.append(clip)
        body += lines
    body += ["</g>"] * len(open_masks)

    bg = f'<rect width="{width}" height="{height}" fill="{background}"/>' if background else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><defs>{"".join(b.defs)}</defs>{bg}{"".join(body)}</svg>')


def rasterize(svg: str, out: Path | None = None, scale: float = 1.0) -> bytes:
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg, zoom=scale if scale != 1.0 else None))
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png)
    return png
