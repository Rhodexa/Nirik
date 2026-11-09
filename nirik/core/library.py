"""A library folder: library.json + drawings, written by a converter.

The format is specified in docs/format.md. Nirik only reads explicit
fields; it never infers meaning from names. Version 1 (character.json) is
still read during the transition, without groups or display labels.

Coordinates (format section 5): 2D, y down, symbol units. Blender rigs live
in a plane with y up, in meters: `to_plane` converts a matrix;
`socket_bones` splits it into the two bones that can express it.

Internal names still follow version 1: Character = library, Rig = symbol,
Slot = layer, Construction = pose, SocketEntry = placement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .affine import decompose

SCHEMA = 1        # character.json (version 1)
FORMAT = "nirik.library"
VERSION = 2       # library.json
Mat = tuple[float, float, float, float, float, float]  # (a, b, c, d, tx, ty)


@dataclass
class Slot:
    name: str
    rig: str
    layer: str                       # source layer name (version 1); kept for reference
    order: int
    mask: bool = False
    masked_by: str | None = None
    child_rig: str | None = None
    canvas: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1 (library units)
    label: str = ""                  # display name


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
    label: str = ""
    tags: list[str] = field(default_factory=list)   # "key:value" (version 2)
    file: str = ""

    def tag(self, key: str) -> str | None:
        """Value of a `key:value` tag, e.g. tag("chart") -> "mouth-3q"."""
        prefix = key + ":"
        return next((t[len(prefix):] for t in self.tags if t.startswith(prefix)), None)


@dataclass
class Character:
    root: Path
    name: str
    ppu: float
    root_rig: str
    rigs: dict[str, Rig]
    drawings: dict[int, Drawing]
    cycle: dict | None = None  # {"frames": n, "speed": units/frame}: root rig loops in place
    groups: list[tuple[str, list[str]]] = field(default_factory=list)  # (label, layer ids)
    far: tuple[float, ...] | None = None   # far-side color placement, if the library has one
    units_per_meter: float | None = None
    label: str = ""

    def drawing_path(self, drawing: int) -> Path:
        d = self.drawings.get(drawing)
        return self.root / (d.file if d and d.file else f"drawings/{drawing}.png")

    def all_slots(self) -> dict[str, Slot]:
        return {s.name: s for r in self.rigs.values() for s in r.slots}

    def slot_drawings(self, slot: str) -> list[int]:
        return sorted(d.id for d in self.drawings.values() if d.slot == slot)

    def far_color(self) -> tuple[float, ...] | None:
        return self.far

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


def description(root: Path) -> Path:
    """The library's description file: library.json, or version 1's."""
    v2 = root / "library.json"
    return v2 if v2.exists() else root / "character.json"


def load(root: str | Path) -> Character:
    root = Path(root).resolve()
    path = description(root)
    data = json.loads(path.read_text())
    if path.name == "library.json":
        if data.get("format") != FORMAT or data.get("version") != VERSION:
            raise ValueError(f"{path}: not a Nirik library version {VERSION}")
        return _load_v2(root, data)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{root}: unsupported library schema {data.get('schema')}")
    return _load_v1(root, data)


def _load_v2(root: Path, data: dict) -> Character:
    rigs = {}
    for sid, sym in data["symbols"].items():
        slots = []
        for order, layer in enumerate(sym["layers"]):
            symbols = layer.get("symbols") or []
            slots.append(Slot(name=layer["id"], rig=sid, layer=layer.get("label", layer["id"]),
                              order=order, mask=layer.get("kind") == "mask",
                              masked_by=layer.get("masked_by"),
                              child_rig=symbols[0] if layer.get("kind") == "symbol" and symbols else None,
                              canvas=tuple(layer["canvas"]) if "canvas" in layer else None,
                              label=layer.get("label", layer["id"])))
        poses = []
        for i, pose in enumerate(sym["poses"]):
            entries = {k: SocketEntry(matrix=tuple(v["matrix"]),
                                      color=tuple(v["color"]) if "color" in v else None,
                                      drawing=v.get("drawing", 0), construction=v.get("pose"))
                       for k, v in pose["layers"].items()}
            labels = [pose["label"]] if pose.get("label") else []
            poses.append(Construction(id=i, labels=labels + pose.get("tags", []),
                                      frames=pose.get("frames", []), slots=entries))
        rigs[sid] = Rig(sid, slots, poses)
        if sid == data["root"] and sym.get("cycle"):
            first, last = sym["cycle"]["poses"]
            cycle = {"frames": last - first + 1, "speed": sym["cycle"].get("speed")}
    drawings = {int(k): Drawing(int(k), d["layer"], d.get("label", ""), d.get("tags", []),
                                d.get("file", ""))
                for k, d in data["drawings"].items()}
    root_sym = data["symbols"][data["root"]]
    return Character(root, root.name, data["pixels_per_unit"], data["root"], rigs, drawings,
                     cycle if root_sym.get("cycle") else None,
                     groups=[(g["label"], list(g["layers"])) for g in data.get("groups", [])],
                     far=tuple(data["far_color"]) if data.get("far_color") else None,
                     units_per_meter=data.get("units_per_meter"), label=data.get("label", ""))


def _load_v1(root: Path, data: dict) -> Character:
    """Version 1, read as-is: no groups, no display labels beyond raw names."""
    rigs = {}
    for rname, r in data["rigs"].items():
        slots = [Slot(name=s["name"], rig=rname, layer=s["layer"], order=s["order"],
                      mask=s.get("mask", False), masked_by=s.get("masked_by"),
                      child_rig=s.get("rig"),
                      canvas=tuple(s["canvas"]) if "canvas" in s else None,
                      label=s["layer"])
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
    return Character(root, data["name"], data["ppu"], data["root_rig"], rigs, drawings,
                     data.get("cycle"))


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
