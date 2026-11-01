"""Feature census: which Flash features do real scenes use, how often, and on whom.

Evaluates every frame of every scene and counts features per node-frame,
split by character group (twilight, rarity, other characters, non-character).
Characters are recognized from rig codes in symbol names (PTS_Head, RA_Eye...)
using FLA-RE's lineage table. The output ranks features so each can be given
a decision: support live, bake at raster time, approximate, or ignore.

  python -m devtools.flash.census ../FLA-RE/fla/S08E23 --out out/census/s08e23
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from . import evaluate as E
from . import fla

FOCUS = {"twilight_sparkle": "twilight", "princess_twilight": "twilight", "rarity": "rarity"}
GROUPS = ("twilight", "rarity", "other_char", "none")
SKIP_MAIN_LAYERS = re.compile(r"GUIDE|BOARD|AUDIO|CAM|REF|ANIMATIC", re.I)
MOUTH = re.compile(r"mouth|mth|lip", re.I)
SKEW_EPS = math.radians(0.5)


def _rig_codes() -> dict[str, str]:
    path = fla.FLARE_DIR / "lineage" / "rig_family_tree.json"
    try:
        return json.loads(path.read_text())["meta"]["rig_codes"]
    except (OSError, KeyError, ValueError):
        return {"PTS": "princess_twilight", "TS": "twilight_sparkle", "RA": "rarity", "RY": "rarity"}


RIG_CODES = _rig_codes()


def symbol_group(name: str | None) -> str | None:
    if not name:
        return None
    m = re.match(r"([A-Za-z]+)[_\- ]", name.rsplit("/", 1)[-1])
    char = RIG_CODES.get(m.group(1).upper()) if m else None
    return FOCUS.get(char, "other_char") if char else None


def skip_layer(container: str, layer: str) -> bool:
    return container == fla.MAIN and bool(SKIP_MAIN_LAYERS.search(layer))


def transform_features(m: E.Mat) -> list[str]:
    a, b, c, d = m[:4]
    det = a * d - b * c
    sx, sy, kx, ky = E.flash_decompose(m)
    out = []
    if det < 0:
        out.append("transform: mirror")
    skew = abs(E._wrap(kx - ky - (math.pi if det < 0 else 0)))
    if skew > SKEW_EPS:
        out.append("transform: skew")
    if sy > 1e-9 and abs(sx / sy - 1) > 0.01:
        out.append("transform: non-uniform scale")
    return out


def node_features(n: E.Node) -> list[str]:
    if n.kind != "instance":
        f = [f"leaf: {n.kind}"]
        if n.masks:
            f.append(f"mask: depth {len(n.masks)}")
        return f
    el = n.element
    stype = el.get("symbolType", "movie clip")
    f = [f"symbol: {stype}", f"nesting depth: {min(n.depth, 9)}"]
    if stype == "graphic":
        f.append(f"loop: {el.get('loop', 'loop')}")
        if el.get("lastFrame") is not None:
            f.append("loop: lastFrame range")
    if n.tween:
        f.append(f"tween: {n.tween}")
    if n.color_kind:
        f.append(f"color: {n.color_kind}")
    f += transform_features(n.local)
    f += [f"unsupported: {u}" for u in n.unsupported]
    return f


def _runs(values: list) -> list[int]:
    runs, length = [], 1
    for prev, cur in zip(values, values[1:]):
        if cur == prev:
            length += 1
        else:
            runs.append(length)
            length = 1
    runs.append(length)
    return runs


def scan(path: Path) -> dict:
    doc = fla.load(path)
    ev = E.Evaluator(doc, skip_layer)
    frames = ev.frame_count()
    counts: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, str] = {}
    exposures: dict[tuple, list] = defaultdict(lambda: [None] * frames)  # slot -> (symbol, frame)
    moves: dict[tuple, list] = defaultdict(lambda: [None] * frames)      # slot -> local matrix
    slot_group: dict[tuple, str] = {}
    slot_mouth: dict[tuple, bool] = {}
    order_prev: dict[tuple, list] = {}

    for f in range(frames):
        group: dict[int, str] = {}
        key: dict[int, tuple] = {}
        names: dict[int, str] = {}
        children: dict[tuple, list] = defaultdict(list)
        for n in ev.evaluate(f):
            p = n.parent
            # The outermost character wins: rigs reuse parts named after other characters.
            inherited = group[id(p)] if p is not None else "none"
            g = inherited if inherited != "none" else (symbol_group(n.symbol) or "none")
            group[id(n)] = g
            name = (names[id(p)] + "/" if p is not None else "") + (n.symbol or n.kind)
            names[id(n)] = name
            for feat in node_features(n):
                counts[feat][g] += 1
                examples.setdefault(feat, f"frame {f}: {name}")
            if n.kind != "instance":
                continue
            # Slot identity: parent slot + container + layer (+ occurrence among siblings).
            pk = key[id(p)] if p is not None else ()
            base = pk + ((n.container, n.layer),)
            siblings = children[pk]
            k = base + (sum(1 for s in siblings if s[:-1] == base),)
            siblings.append(k)
            key[id(n)] = k
            exposures[k][f] = (n.symbol, n.child_frame)
            moves[k][f] = tuple(round(v, 3) for v in n.local)
            slot_group[k] = g
            slot_mouth[k] = slot_mouth.get(k, False) or bool(MOUTH.search(f"{n.layer} {n.symbol}"))
        for pk, kids in children.items():
            prev = order_prev.get(pk)
            if prev is not None and set(prev) == set(kids) and prev != kids:
                g = slot_group.get(pk, "none")
                counts["draw order: change"][g] += 1
                examples.setdefault("draw order: change", f"frame {f}: {'/'.join(map(str, pk[-1:]))}")
            order_prev[pk] = kids

    holds = Counter()
    for k, seq in exposures.items():
        vals = [v for v in seq if v is not None]
        if len(set(vals)) > 1:
            kind = "mouth" if slot_mouth[k] else "drawing"
            for r in _runs(vals):
                holds[f"{slot_group[k]}|{kind}|{min(r, 12)}"] += 1
    for k, seq in moves.items():
        vals = [v for v in seq if v is not None]
        if len(set(vals)) > 1:
            for r in _runs(vals):
                holds[f"{slot_group[k]}|transform|{min(r, 12)}"] += 1

    return {"scene": path.name, "frames": frames,
            "counts": {k: dict(v) for k, v in counts.items()},
            "examples": examples, "holds": dict(holds)}


# ── aggregation and report ───────────────────────────────────────────────────

def aggregate(results: list[dict]) -> dict:
    feats: dict[str, dict] = {}
    holds = Counter()
    for r in results:
        holds.update(r["holds"])
        for feat, by_group in r["counts"].items():
            entry = feats.setdefault(feat, {"groups": Counter(), "scenes": 0, "examples": []})
            entry["groups"].update(by_group)
            entry["scenes"] += 1
            if len(entry["examples"]) < 3:
                entry["examples"].append(f"{r['scene']} {r['examples'][feat]}")
    return {"scenes": len(results), "frames": sum(r["frames"] for r in results),
            "features": {k: {**v, "groups": dict(v["groups"])} for k, v in feats.items()},
            "holds": dict(holds)}


def report(agg: dict, failures: list[str]) -> str:
    lines = [f"# Feature census\n",
             f"{agg['scenes']} scenes, {agg['frames']} frames. Counts are node-frames "
             f"(one node visible on one frame).\n",
             "| Feature | Twilight | Rarity | Other chars | Non-char | Scenes | Example |",
             "|---|---:|---:|---:|---:|---:|---|"]

    def focus(item):
        g = item[1]["groups"]
        return (g.get("twilight", 0) + g.get("rarity", 0), sum(g.values()))

    for feat, e in sorted(agg["features"].items(), key=focus, reverse=True):
        g = e["groups"]
        cells = " | ".join(f"{g.get(x, 0):,}" for x in GROUPS)
        lines.append(f"| {feat} | {cells} | {e['scenes']} | {e['examples'][0]} |")

    lines += ["", "## Exposure and hold lengths", "",
              "Run lengths (frames) of animated slots. 12 means 12 or more.", "",
              "| Group | Kind | " + " | ".join(str(i) for i in range(1, 13)) + " |",
              "|---|---|" + "---:|" * 12]
    table = defaultdict(Counter)
    for k, v in agg["holds"].items():
        g, kind, r = k.split("|")
        table[(g, kind)][int(r)] += v
    for (g, kind), runs in sorted(table.items()):
        total = sum(runs.values()) or 1
        lines.append(f"| {g} | {kind} | " + " | ".join(f"{100 * runs[i] / total:.0f}%" for i in range(1, 13)) + " |")

    if failures:
        lines += ["", "## Failed scenes", "", *[f"- {x}" for x in failures]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path, help=".fla files or directories")
    ap.add_argument("--out", type=Path, default=Path("out/census"))
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, help="scan at most N scenes")
    args = ap.parse_args(argv)

    files = sorted(p for x in args.paths for p in ([x] if x.is_file() else x.rglob("*.fla")))
    files = files[: args.limit] if args.limit else files
    results, failures = [], []
    t0 = time.time()
    with ProcessPoolExecutor(args.jobs) as pool:
        futures = {pool.submit(scan, f): f for f in files}
        for i, fut in enumerate(as_completed(futures), 1):
            f = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:  # noqa: BLE001 - a broken scene must not stop the census
                failures.append(f"{f.name}: {type(e).__name__}: {e}")
            print(f"\r[{i}/{len(files)}] {time.time() - t0:.0f}s", end="", file=sys.stderr)
    print(file=sys.stderr)

    args.out.mkdir(parents=True, exist_ok=True)
    agg = aggregate(results)
    (args.out / "scenes.json").write_text(json.dumps(results, indent=1))
    (args.out / "census.json").write_text(json.dumps(agg, indent=1))
    (args.out / "census.md").write_text(report(agg, failures))
    print(f"{len(results)} scenes, {len(failures)} failed -> {args.out / 'census.md'}")


if __name__ == "__main__":
    main()
