"""Character library: character.json + drawings/<id>.png (written by an importer).

Coordinates: libraries store Flash-style 2D (y down, library units). Blender
rigs live in a plane with y up, in meters. `to_plane` converts a library
matrix; `socket_bones` splits it into the two bones that can express it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .affine import decompose

SCHEMA = 1
Mat = tuple[float, float, float, float, float, float]  # (a, b, c, d, tx, ty)


@dataclass
class Slot:
    name: str
    rig: str
    layer: str
    order: int
    mask: bool = False
    masked_by: str | None = None
    child_rig: str | None = None
    canvas: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1 (library units)


@dataclass
class SocketEntry:
    matrix: Mat
    color: tuple[float, ...] | None = None  # mult RGBA + offset RGBA (0..255)
    drawing: int = 0
    construction: int | None = None          # for slots holding a child rig


@dataclass
class Construction:
    id: int
    labels: list[str]
    frames: list[int]
    slots: dict[str, SocketEntry]


@dataclass
class Rig:
    name: str
    slots: list[Slot]                 # back to front
    constructions: list[Construction]

    def slot(self, name: str) -> Slot:
        return next(s for s in self.slots if s.name == name)


@dataclass
class Drawing:
    id: int
    slot: str
    symbol: str
    tags: list[str] = field(default_factory=list)


@dataclass
class Character:
    root: Path
    name: str
    ppu: float
    root_rig: str
    rigs: dict[str, Rig]
    drawings: dict[int, Drawing]

    def drawing_path(self, drawing: int) -> Path:
        return self.root / "drawings" / f"{drawing}.png"

    def all_slots(self) -> dict[str, Slot]:
        return {s.name: s for r in self.rigs.values() for s in r.slots}

    def slot_drawings(self, slot: str) -> list[int]:
        return sorted(d.id for d in self.drawings.values() if d.slot == slot)

    def draw_order(self, construction: int | None = None) -> list[str]:
        """Drawable slots back to front, expanding child rigs in place.

        Child rigs expand at their slot's position; which child construction is
        used doesn't change the slot order, which is fixed per rig.
        """
        out: list[str] = []

        def walk(rig: str):
            for s in self.rigs[rig].slots:
                if s.child_rig:
                    walk(s.child_rig)
                elif not s.mask and s.canvas:
                    out.append(s.name)

        walk(self.root_rig)
        return out


def load(root: str | Path) -> Character:
    root = Path(root).resolve()
    data = json.loads((root / "character.json").read_text())
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{root}: unsupported library schema {data.get('schema')}")
    rigs = {}
    for rname, r in data["rigs"].items():
        slots = [Slot(name=s["name"], rig=rname, layer=s["layer"], order=s["order"],
                      mask=s.get("mask", False), masked_by=s.get("masked_by"),
                      child_rig=s.get("rig"),
                      canvas=tuple(s["canvas"]) if "canvas" in s else None)
                 for s in r["slots"]]
        cons = [Construction(id=c["id"], labels=c["labels"], frames=c["frames"],
                             slots={k: SocketEntry(matrix=tuple(v["matrix"]),
                                                   color=tuple(v["color"]) if "color" in v else None,
                                                   drawing=v.get("drawing", 0),
                                                   construction=v.get("construction"))
                                    for k, v in c["slots"].items()})
                for c in r["constructions"]]
        rigs[rname] = Rig(rname, sorted(slots, key=lambda s: s.order), cons)
    drawings = {int(k): Drawing(int(k), d["slot"], d["symbol"], d.get("tags", []))
                for k, d in data["drawings"].items()}
    return Character(root, data["name"], data["ppu"], data["root_rig"], rigs, drawings)


# ── space conversion ─────────────────────────────────────────────────────────

def to_plane(m: Mat, units_per_meter: float) -> Mat:
    """Library matrix (y down, library units) -> plane matrix (y up, meters)."""
    a, b, c, d, tx, ty = m
    return (a, -b, -c, d, tx / units_per_meter, -ty / units_per_meter)


def point_to_plane(x: float, y: float, units_per_meter: float) -> tuple[float, float]:
    return x / units_per_meter, -y / units_per_meter


@dataclass(frozen=True)
class BonePair:
    """Two bone bases whose product is a plane matrix: A = T·R(rot_a)·S, B = R(rot_b)."""
    location: tuple[float, float]
    rot_a: float
    scale: tuple[float, float]
    rot_b: float


def socket_bones(m: Mat) -> BonePair:
    """Split a plane matrix into a SOCKET (loc/rot/scale) + SOCKET_SKEW (rot) bone pair."""
    r = decompose(m[:4])
    return BonePair((m[4], m[5]), r.rot_a, (r.sx, r.sy), r.rot_b)
