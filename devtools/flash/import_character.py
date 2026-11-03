"""Import a stock-file rig into a Nirik character library.

  python -m devtools.flash.import_character \\
      ../FLA-RE/fla/STK_C23_Princess_Twilight_Sparkle.fla \\
      --root "~PTS_Character" --name twilight --out library/twilight

Mapping from the show's stock rigs:
  rig symbol (name starts with "~")  -> rig; each distinct frame is a construction
  layer of a rig                     -> slot ("Head.MOUTH", "Head.EAR_2")
  instance on a slot                 -> drawing (symbol, frame) + socket (matrix, color)
  rig instance on a slot             -> child rig, with its default construction
  mask layer                         -> mask slot; layers under it are masked_by it

Each drawing is flattened (all structural nesting baked in) and rasterized
onto its slot's canonical canvas: the union bounds of every drawing the slot
can show, in the slot's local units. Swapping drawings never moves anything.

Output: character.json, drawings/<id>.png, ids.json (stable drawing IDs that
survive re-imports; 0 means "empty").
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import io
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from . import evaluate as E
from . import fla, render
from .fla import FI, t

SCHEMA = 1
PAD = 6.0  # local units around geometry: covers stroke widths and antialiasing


# ── geometry ────────────────────────────────────────────────────────────────

def shape_points(shape, in_group: bool) -> list[tuple[float, float]]:
    """All edge points of a DOMShape (fills and strokes) in its parent's space."""
    pts = []
    for edge in shape.iter(t("Edge")):
        es = edge.get("edges", "").strip()
        if not es:
            continue
        try:
            cmds = FI.parse_edge_str(es)
        except Exception:  # noqa: BLE001 - malformed edge strings exist in the wild
            continue
        for c in cmds:
            pts.append((c[1], c[2]))
            if c[0] == "Q":
                pts.append((c[3], c[4]))
    if not in_group:
        m = E.read_matrix(shape)
        if m != E.IDENTITY:
            pts = [E.apply(m, x, y) for x, y in pts]
    return pts


def nodes_bbox(nodes: list[E.Node]) -> tuple[float, float, float, float] | None:
    xs, ys = [], []
    for n in nodes:
        if n.kind != "shape":
            continue
        for x, y in shape_points(n.element, n.in_group):
            wx, wy = E.apply(n.matrix, x, y)
            xs.append(wx)
            ys.append(wy)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def union(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def leaf_signature(nodes: list[E.Node]) -> str:
    """Identity of a drawing's content within one run (uses object ids); equal
    for frames that look the same. Not stable across runs."""
    h = hashlib.blake2b(digest_size=12)
    for n in nodes:
        if n.kind == "shape":
            h.update(repr((id(n.element), [round(v, 4) for v in n.matrix],
                           n.color.mult, n.color.off, len(n.masks))).encode())
    return h.hexdigest()


# ── labels ──────────────────────────────────────────────────────────────────

def frame_labels(idx: E.SymbolIndex, frame: int) -> list[str]:
    """Active frame labels: per layer, the latest label at or before `frame`."""
    out = []
    for L in idx.layers:
        current = None
        for s in L.spans:
            if s.start > frame:
                break
            if s.frame.get("name") is not None:
                current = s.frame.get("name").strip()
        if current and current not in out:
            out.append(current)
    return out


# ── rig discovery ───────────────────────────────────────────────────────────

def short(name: str) -> str:
    return name.rsplit("/", 1)[-1]


def is_rig(name: str | None, ev: E.Evaluator | None = None) -> bool:
    """Rig symbols start with "~". With `ev`, a wrapper that directly holds a rig
    (a walk cycle's "PTS_walk_head" around "~PTS_Head") counts too, so the head
    inside stays editable instead of being flattened."""
    if not name:
        return False
    if short(name).startswith("~"):
        return True
    if ev is None:
        return False
    cache = ev.__dict__.setdefault("_wraps_rig", {})
    if name not in cache:
        idx = ev.index(name)
        cache[name] = bool(idx) and any(
            short(el.get("libraryItemName") or "").startswith("~")
            for L in idx.layers for sp in L.spans for el in sp.elements)
    return cache[name]


def rig_name(symbol: str) -> str:
    """'~PTS_Head' -> 'Head'."""
    base = short(symbol).lstrip("~")
    return base.split("_", 1)[1] if "_" in base else base


@dataclass
class Slot:
    name: str
    rig: str
    layer: str
    layer_index: int
    order: int                      # back to front within the rig
    mask: bool = False
    masked_by: str | None = None
    child_rig: str | None = None    # symbol, when the slot holds a rig
    symbols: set = field(default_factory=set)
    bbox: tuple | None = None


def discover(ev: E.Evaluator, root: str):
    """Walk rigs from `root`; return (rigs: symbol -> [Slot], order of rigs)."""
    rigs: dict[str, list[Slot]] = {}
    pending = [root]
    while pending:
        sym = pending.pop(0)
        if sym in rigs:
            continue
        idx = ev.index(sym)
        rname = rig_name(sym)
        slots, seen = [], defaultdict(int)
        visible = [L for L in idx.layers if L.type not in ("guide", "folder")]
        by_layer = {}
        for L in visible:  # top first, for stable "_2" numbering
            seen[L.name.strip() or "Layer"] += 1
            n = seen[L.name.strip() or "Layer"]
            sname = f"{rname}.{L.name.strip() or 'Layer'}" + (f"_{n}" if n > 1 else "")
            slot = Slot(sname, rname, L.name, L.i, len(visible) - 1 - visible.index(L),
                        mask=L.type == "mask")
            by_layer[L.i] = slot
            for s in L.spans:
                for el in s.elements:
                    name = el.get("libraryItemName")
                    if el.tag != E.TAG_INSTANCE or not name:
                        continue
                    if is_rig(name, ev):
                        slot.child_rig = name
                        pending.append(name)
                    else:
                        slot.symbols.add(name)
            slots.append(slot)
        for L in visible:
            if L.parent is not None and L.parent in by_layer and by_layer[L.parent].mask:
                by_layer[L.i].masked_by = by_layer[L.parent].name
        rigs[sym] = sorted(slots, key=lambda s: s.order)
    return rigs


# ── constructions ───────────────────────────────────────────────────────────

def matrix_list(m: E.Mat) -> list[float]:
    return [round(v, 6) for v in m]


def color_list(c: E.ColorXf) -> list[float] | None:
    return None if c.is_identity else [round(v, 6) for v in (*c.mult, *c.off)]


def constructions(ev: E.Evaluator, sym: str, slots: list[Slot], drawing_of, construction_of,
                  frames: range | None = None):
    """Distinct frames of a rig -> construction records, plus {frame: construction}."""
    idx = ev.index(sym)
    by_layer = {s.layer_index: s for s in slots}
    records, frame_map, keys = [], {}, {}
    for f in frames if frames is not None else range(idx.frame_count):
        entries = {}
        for L in idx.layers:
            slot = by_layer.get(L.i)
            found = L.span_at(f) if slot else None
            if not found:
                continue
            span, _ = found
            insts = [el for el in span.elements if el.tag == E.TAG_INSTANCE and el.get("libraryItemName")]
            if not insts:
                continue
            el = insts[0]  # stock rigs hold at most one instance per slot span
            name = el.get("libraryItemName")
            child = ev.index(name)
            cf = E.resolve_child_frame(el, f - span.start, child.frame_count if child else 1)
            color, _ = E.read_color(el)
            entry = {"matrix": matrix_list(E.read_matrix(el))}
            if color_list(color):
                entry["color"] = color_list(color)
            if is_rig(name, ev):
                entry["construction"] = construction_of(name, cf)
            else:
                entry["drawing"] = drawing_of(slot.name, name, cf)
            entries[slot.name] = entry
        key = json.dumps(entries, sort_keys=True)
        if key not in keys:
            keys[key] = len(records)
            records.append({"id": len(records), "frames": [], "labels": frame_labels(idx, f),
                            "slots": entries})
        records[keys[key]]["frames"].append(f)
        frame_map[f] = keys[key]
    return records, frame_map


def cycle_speed(ev: E.Evaluator, root: str, frames: range) -> float | None:
    """Walking speed of an in-place cycle, in character units per frame
    (negative = toward screen left): a planted hoof slides backward at exactly
    the speed the body must travel for the hooves to stay put."""
    lowest: dict[str, list] = {}
    for i, f in enumerate(frames):
        for n in ev.evaluate(f, root=root):
            if n.kind != "shape":
                continue
            p, leg = n, None
            while p is not None and leg is None:
                if p.symbol and re.search(r"leg|hoof|foot", short(p.symbol), re.I):
                    leg = p.symbol
                p = p.parent
            if leg is None:
                continue
            seq = lowest.setdefault(leg, [None] * len(frames))
            for x, y in shape_points(n.element, n.in_group):
                wx, wy = E.apply(n.matrix, x, y)
                if seq[i] is None or wy > seq[i][1]:
                    seq[i] = (wx, wy)
    slides = []
    for seq in lowest.values():
        ys = sorted(v[1] for v in seq if v)
        if not ys:
            continue
        ground = ys[int(0.75 * (len(ys) - 1))]  # this foot's usual low point; ignores a dipping toe
        for a, b in zip(seq, seq[1:] + seq[:1]):
            # planted: down on the ground and not lifting or landing
            if a and b and min(a[1], b[1]) > ground - 2.5 and abs(b[1] - a[1]) < 1.5:
                slides.append(b[0] - a[0])
    slides.sort()
    return -slides[len(slides) // 2] if slides else None


# ── rendering workers ───────────────────────────────────────────────────────

_worker: dict = {}


def _init_worker(path: str):
    doc = fla.load(path)
    _worker["ev"] = E.Evaluator(doc)


def bleed_alpha(png: bytes, steps: int = 8) -> Image.Image:
    """Spread edge colors into transparent pixels (alpha unchanged).

    GPUs filter straight-alpha textures without premultiplying; transparent
    pixels stored as black then darken every edge into a visible fringe.
    """
    img = np.asarray(Image.open(io.BytesIO(png)).convert("RGBA")).astype(np.float32)
    rgb, known = img[..., :3].copy(), img[..., 3] > 0
    for _ in range(steps):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(known.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            shifted_known = np.roll(known, (dy, dx), axis=(0, 1))
            acc += np.roll(rgb, (dy, dx), axis=(0, 1)) * shifted_known[..., None]
            cnt += shifted_known
        grow = ~known & (cnt > 0)
        rgb[grow] = acc[grow] / cnt[grow][:, None]
        known |= grow
    if known.any():
        rgb[~known] = rgb[known].mean(axis=0)
    img[..., :3] = rgb
    return Image.fromarray(np.clip(img + 0.5, 0, 255).astype(np.uint8), "RGBA")


def _render_job(job):
    symbol, frame, canvas, ppu, out = job
    x0, y0, x1, y1 = canvas
    w, h = max(1, math.ceil((x1 - x0) * ppu)), max(1, math.ceil((y1 - y0) * ppu))
    world = (ppu, 0.0, 0.0, ppu, -x0 * ppu, -y0 * ppu)
    nodes = _worker["ev"].evaluate(frame, root=symbol, world=world)
    bleed_alpha(render.rasterize(render.frame_svg(nodes, w, h))).save(out, optimize=False)
    return out


# ── main ────────────────────────────────────────────────────────────────────

def import_character(path: Path, root: str, name: str, out: Path, ppu: float, jobs: int,
                     frames: range | None = None):
    """`frames` limits the root rig to those frames: a walk cycle's loop."""
    t0 = time.time()
    doc = fla.load(path)
    ev = E.Evaluator(doc)
    if root not in doc.symbols:
        matches = [s for s in doc.symbols if short(s) == root]
        if not matches:
            sys.exit(f"root symbol {root!r} not found")
        root = matches[0]
    rigs = discover(ev, root)
    print(f"{len(rigs)} rigs, {sum(len(s) for s in rigs.values())} slots")

    # Pass 1: every frame of every symbol a slot can show -> unique drawings + bounds.
    out.mkdir(parents=True, exist_ok=True)
    ids_path = out / "ids.json"
    ids: dict[str, int] = json.loads(ids_path.read_text()) if ids_path.exists() else {}
    next_id = max(ids.values(), default=0) + 1

    drawings: dict[int, dict] = {}
    frame_drawing: dict[tuple[str, str, int], int] = {}  # (slot, symbol, frame) -> id
    slots_by_name = {s.name: s for slots in rigs.values() for s in slots}
    for slot in slots_by_name.values():
        sig_to_id: dict[str, int] = {}
        for symbol in sorted(slot.symbols):
            idx = ev.index(symbol)
            for f in range(idx.frame_count if idx else 0):
                nodes = ev.evaluate(f, root=symbol)
                sig = leaf_signature(nodes)
                if sig not in sig_to_id:
                    key = f"{slot.name}|{short(symbol)}|{f}"  # stable across re-imports
                    if key not in ids:
                        ids[key] = next_id
                        next_id += 1
                    did = ids[key]
                    sig_to_id[sig] = did
                    drawings[did] = {"slot": slot.name, "symbol": short(symbol), "frames": [],
                                     "tags": frame_labels(idx, f)}
                    slot.bbox = union(slot.bbox, nodes_bbox(nodes))
                did = sig_to_id[sig]
                drawings[did]["frames"].append(f)
                frame_drawing[(slot.name, symbol, f)] = did
    print(f"{len(drawings)} unique drawings ({len(frame_drawing)} symbol frames) "
          f"in {time.time() - t0:.0f}s")

    # Constructions per rig (children first so parents can reference them).
    rig_constructions: dict[str, tuple[list, list]] = {}

    def construction_of(sym: str, frame: int) -> int:
        _, frame_map = rig_constructions[sym]
        return frame_map.get(frame, frame_map[max(frame_map)])

    def drawing_of(slot: str, symbol: str, frame: int) -> int:
        return frame_drawing.get((slot, symbol, frame), 0)

    for sym in reversed(list(rigs)):
        rig_constructions[sym] = constructions(ev, sym, rigs[sym], drawing_of, construction_of,
                                               frames if sym == root else None)

    # Canvases: union bounds, padded, snapped to whole pixels.
    for slot in slots_by_name.values():
        if slot.bbox:
            x0, y0, x1, y1 = slot.bbox
            x0, y0 = math.floor((x0 - PAD) * ppu) / ppu, math.floor((y0 - PAD) * ppu) / ppu
            x1, y1 = math.ceil((x1 + PAD) * ppu) / ppu, math.ceil((y1 + PAD) * ppu) / ppu
            slot.bbox = (x0, y0, x1, y1)

    # Pass 2: rasterize (only drawings whose PNG is missing).
    draw_dir = out / "drawings"
    draw_dir.mkdir(exist_ok=True)
    first_symbol = {did: next(s for s in slots_by_name[d["slot"]].symbols if short(s) == d["symbol"])
                    for did, d in drawings.items()}
    jobs_list = [(first_symbol[did], d["frames"][0], slots_by_name[d["slot"]].bbox, ppu,
                  str(draw_dir / f"{did}.png"))
                 for did, d in drawings.items()
                 if slots_by_name[d["slot"]].bbox and not (draw_dir / f"{did}.png").exists()]
    if jobs_list:
        with ProcessPoolExecutor(jobs, initializer=_init_worker, initargs=(str(path),)) as pool:
            for i, _ in enumerate(pool.map(_render_job, jobs_list, chunksize=8), 1):
                if i % 50 == 0 or i == len(jobs_list):
                    print(f"\rrendered {i}/{len(jobs_list)}", end="", file=sys.stderr)
        print(file=sys.stderr)

    character = {
        "schema": SCHEMA,
        "name": name,
        "source": {"file": path.name, "root": short(root)},
        "ppu": ppu,
        "root_rig": rig_name(root),
        **({"cycle": {"frames": len(frames), "speed": cycle_speed(ev, root, frames)}} if frames else {}),
        "rigs": {
            rig_name(sym): {
                "symbol": short(sym),
                "slots": [{
                    "name": s.name,
                    "layer": s.layer.strip(),
                    "order": s.order,
                    **({"mask": True} if s.mask else {}),
                    **({"masked_by": s.masked_by} if s.masked_by else {}),
                    **({"rig": rig_name(s.child_rig)} if s.child_rig else {}),
                    **({"canvas": list(s.bbox)} if s.bbox and not s.child_rig else {}),
                } for s in slots],
                "constructions": rig_constructions[sym][0],
            } for sym, slots in rigs.items()
        },
        "drawings": {str(did): {k: v for k, v in d.items() if k != "frames"} | {"frames": d["frames"]}
                     for did, d in sorted(drawings.items())},
    }
    (out / "character.json").write_text(json.dumps(character, indent=1))
    ids_path.write_text(json.dumps(ids, indent=0, sort_keys=True))
    n_cons = sum(len(r["constructions"]) for r in character["rigs"].values())
    print(f"{name}: {len(character['rigs'])} rigs, {len(slots_by_name)} slots, "
          f"{n_cons} constructions, {len(drawings)} drawings -> {out} ({time.time() - t0:.0f}s)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fla", type=Path)
    ap.add_argument("--root", required=True, help='rig symbol, e.g. "~PTS_Character"')
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ppu", type=float, default=4.0, help="raster pixels per Flash pixel")
    ap.add_argument("--frames", help="root frames to keep, e.g. 0-23 for a walk cycle's loop")
    ap.add_argument("--jobs", type=int, default=6)
    args = ap.parse_args(argv)
    frames = None
    if args.frames:
        a, b = (int(v) for v in args.frames.split("-"))
        frames = range(a, b + 1)
    import_character(args.fla, args.root, args.name, args.out, args.ppu, args.jobs, frames)


if __name__ == "__main__":
    main()
