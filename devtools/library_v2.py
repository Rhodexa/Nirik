"""Library format version 1 -> 2 (docs/format.md, section 11).

  python -m devtools.library_v2 library/*        upgrade folders in place

No drawing is re-rendered: the description is rewritten as library.json,
Nirik's caches move to .nirik/, the converter's IDs to .converter/, and the
old description is kept as .converter/character.v1.json. Libraries made by
the Flash converter get the show's conventions written out explicitly;
others get plain defaults.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

FORMAT, VERSION = "nirik.library", 2
UNITS_PER_METER = 300  # what Nirik assumed for every version 1 library


def from_v1(data: dict, flash: bool) -> dict:
    """Version 2 description from a version 1 one."""
    if flash:
        from devtools.flash import conventions as C
    slots = [s for r in data["rigs"].values() for s in r["slots"]]
    symbols = {}
    for rid, rig in data["rigs"].items():
        layers = []
        for s in sorted(rig["slots"], key=lambda s: s["order"]):
            layer = {"id": s["name"],
                     "label": C.layer_label(s["name"]) if flash else s["layer"],
                     "kind": "mask" if s.get("mask") else "symbol" if s.get("rig") else "drawing"}
            if "canvas" in s:
                layer["canvas"] = s["canvas"]
            if s.get("masked_by"):
                layer["masked_by"] = s["masked_by"]
            if s.get("rig"):
                layer["symbols"] = [s["rig"]]
            layers.append(layer)
        poses = []
        for c in rig["constructions"]:
            entries = {}
            for lid, e in c["slots"].items():
                entry = {}
                if "construction" in e:
                    entry["symbol"] = next(s["rig"] for s in rig["slots"] if s["name"] == lid)
                    entry["pose"] = e["construction"]
                elif e.get("drawing"):
                    entry["drawing"] = e["drawing"]
                entry["matrix"] = e["matrix"]
                if e.get("color"):
                    entry["color"] = e["color"]
                entries[lid] = entry
            labels = [l for l in c.get("labels", []) if l.strip()]
            pose = {"label": labels[0] if labels else "", "tags": [f"label:{l}" for l in labels[1:]],
                    "frames": c.get("frames", []), "layers": entries}
            poses.append(pose)
        symbols[rid] = {"label": rid, "layers": layers, "poses": poses}
    cycle = data.get("cycle")
    if cycle:
        symbols[data["root_rig"]]["cycle"] = {"poses": [0, cycle["frames"] - 1], "speed": cycle.get("speed")}

    drawings = {}
    for did, d in data["drawings"].items():
        drawings[did] = {"layer": d["slot"],
                         "label": C.drawing_label(d["symbol"]) if flash else d["symbol"],
                         "tags": C.drawing_tags(d["symbol"], d.get("tags", [])) if flash
                         else [t if ":" in t else f"label:{t}" for t in d.get("tags", [])],
                         "file": f"drawings/{did}.png"}

    out = {"format": FORMAT, "version": VERSION, "label": data["name"], "root": data["root_rig"],
           "pixels_per_unit": data["ppu"], "units_per_meter": UNITS_PER_METER,
           "symbols": symbols, "drawings": drawings}
    if flash:
        out["groups"] = C.groups(slots)
        far = C.far_color([e["color"] for r in data["rigs"].values() for c in r["constructions"]
                           for e in c["slots"].values() if e.get("color")])
        if far:
            out["far_color"] = far
    elif any(s["layer"] == "ART" for s in slots):  # pictures made by Import Image
        out["groups"] = [{"label": "Art", "layers": [s["name"] for s in slots if s["layer"] == "ART"]}]
    return out


def is_flash(data: dict) -> bool:
    return str(data.get("source", {}).get("file", "")).lower().endswith(".fla")


def write(folder: Path, v2: dict):
    """Write library.json and move version 1's side files to their new places."""
    folder = Path(folder)
    (folder / "library.json").write_text(json.dumps(v2, indent=1))
    old_cache, new_cache = folder / ".udim", folder / ".nirik" / "palettes"
    if old_cache.exists() and not new_cache.exists():
        new_cache.parent.mkdir(exist_ok=True)
        old_cache.rename(new_cache)
    conv = folder / ".converter"
    conv.mkdir(exist_ok=True)
    if (folder / "ids.json").exists():
        (folder / "ids.json").replace(conv / "ids.json")
    if (folder / "character.json").exists():
        (folder / "character.json").replace(conv / "character.v1.json")


def upgrade(folder: Path) -> bool:
    folder = Path(folder)
    v1 = folder / "character.json"
    if not v1.exists():
        return False
    data = json.loads(v1.read_text())
    write(folder, from_v1(data, is_flash(data)))
    return True


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(f"{arg}: {'upgraded' if upgrade(Path(arg)) else 'nothing to upgrade'}")
    sys.exit(0)
