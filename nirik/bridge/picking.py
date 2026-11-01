"""Which parts of a puppet are under a ray: alpha-tested, mask-aware, front first.

Cards are quads deformed by one bone (an affine map), so a hit point converts
to the drawing's texture coordinates exactly; the drawing's alpha decides
whether the click lands on artwork or passes through.
"""

from __future__ import annotations

from dataclasses import dataclass

import bpy
import numpy as np
from mathutils import Vector, geometry

from ..core import library as L

ALPHA_HIT = 0.3          # clicks on faint antialiasing pass through
ALPHA_MAX_SIZE = 256     # alpha copies are downsampled to this many pixels

_alpha_cache: dict[tuple[str, int], np.ndarray] = {}  # (library, drawing) -> alpha, bottom row first


def drawing_alpha(char: L.Character, drawing: int) -> np.ndarray:
    key = (str(char.root), drawing)
    if key not in _alpha_cache:
        img = bpy.data.images.load(str(char.drawing_path(drawing)), check_existing=False)
        try:
            w, h = img.size
            px = np.empty(w * h * 4, dtype=np.float32)
            img.pixels.foreach_get(px)
        finally:
            bpy.data.images.remove(img)
        alpha = px.reshape(h, w, 4)[..., 3]
        step = max(1, max(w, h) // ALPHA_MAX_SIZE)
        _alpha_cache[key] = alpha[::step, ::step].copy()
    return _alpha_cache[key]


def alpha_at(char: L.Character, drawing: int, u: float, v: float) -> float:
    if not (0.0 <= u < 1.0 and 0.0 <= v < 1.0):
        return 0.0
    a = drawing_alpha(char, drawing)
    return float(a[int(v * a.shape[0]), int(u * a.shape[1])])


@dataclass
class Hit:
    slot: str
    order: int     # draw order: higher is in front
    depth: float   # distance along the ray


def _card_uv(card, depsgraph, origin: Vector, direction: Vector):
    """Ray vs the card's deformed quad -> (u, v, distance, point) or None."""
    ev = card.evaluated_get(depsgraph)
    mw = ev.matrix_world
    v0, v1, _, v3 = (mw @ v.co for v in ev.data.vertices)
    edge_u, edge_v = v1 - v0, v3 - v0
    normal = edge_u.cross(edge_v)
    if normal.length < 1e-12:
        return None
    point = geometry.intersect_line_plane(origin, origin + direction, v0, normal)
    if point is None or (point - origin).dot(direction) < 0:
        return None
    # Solve point - v0 = u * edge_u + v * edge_v in the quad's plane.
    d = point - v0
    uu, uv, vv = edge_u.dot(edge_u), edge_u.dot(edge_v), edge_v.dot(edge_v)
    du, dv = d.dot(edge_u), d.dot(edge_v)
    det = uu * vv - uv * uv
    if abs(det) < 1e-18:
        return None
    u = (du * vv - dv * uv) / det
    v = (dv * uu - du * uv) / det
    return u, v, (point - origin).length, point


def _mask_alpha(arm, char: L.Character, mask_slot: str, point: Vector, depsgraph) -> float:
    empty = bpy.data.objects.get(f"nirik:{char.name}:{mask_slot}")
    drawing = arm.pose.bones[mask_slot]["nirik_drawing"]
    if empty is None or not drawing:
        return 0.0
    local = empty.evaluated_get(depsgraph).matrix_world.inverted() @ point
    return alpha_at(char, drawing, local.x, local.y)


def hits(arm, char: L.Character, origin: Vector, direction: Vector, depsgraph) -> list[Hit]:
    """Parts with artwork under the ray, front first."""
    order = {name: i for i, name in enumerate(char.draw_order())}
    found = []
    for name, i in order.items():
        card = bpy.data.objects.get(f"{char.name}:{name}")
        drawing = arm.pose.bones[name]["nirik_drawing"]
        if card is None or not drawing or card.hide_get() or card.hide_viewport:
            continue
        hit = _card_uv(card, depsgraph, origin, direction)
        if hit is None:
            continue
        u, v, dist, point = hit
        if alpha_at(char, drawing, u, v) < ALPHA_HIT:
            continue
        masked_by = char.all_slots()[name].masked_by
        if masked_by and _mask_alpha(arm, char, masked_by, point, depsgraph) < ALPHA_HIT:
            continue
        found.append(Hit(name, i, dist))
    found.sort(key=lambda h: -h.order)
    return found
