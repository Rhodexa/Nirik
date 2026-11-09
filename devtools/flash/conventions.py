"""What the show's rigs mean by their names, written out as explicit data.

Nirik never reads names for meaning (docs/format.md, section 1); the Flash
converter uses these conventions to fill a library's groups, labels, tags
and far color instead.
"""

from __future__ import annotations

import re

# Layer names in the stock rigs that are one animator-facing group each.
GROUP_LAYERS = (("MOUTH", "Mouth"), ("BROW", "Brow"), ("BLINK", "Blink"))
# Layers under an eye mask that move together as the eye's look.
EYE_LAYERS = {"IRIS", "PUPIL", "HIGHLIGHTS"}
# Mouth-chart frame labels that name a phoneme ("-" marks in-between frames).
PHONEMES = {"a,e,i", "0", "r,o,u", "s", "l", "f", "th", "m,b,p", "-"}


def layer_label(slot_name: str) -> str:
    """'Character.Hind leg_2' -> 'Hind Leg 2', 'Head.EAR_3' -> 'Ear 3'."""
    layer = slot_name.split(".", 1)[-1]
    base, _, n = layer.rpartition("_")
    if not (base and n.isdigit()):
        base, n = layer, ""
    words = base.replace("=", " ").split()
    # Title-case, but keep short abbreviations ("OL" = outline) as they are.
    text = " ".join(w.capitalize() if w.islower() or (w.isupper() and len(w) > 2) else w
                    for w in words)
    return f"{text} {n}".strip()


def drawing_label(symbol: str) -> str:
    """'PTS_Wing_Front' -> 'Wing Front', 'PTS_HindLeg_3-4nomark' -> 'Hind Leg 3-4nomark':
    drop the rig code, split camel case."""
    parts = symbol.split("_")
    if len(parts) > 1 and parts[0].isupper():
        parts = parts[1:]
    return " ".join(w for p in parts for w in re.sub(r"(?<=[a-z])(?=[A-Z])", " ", p).split())


def chart(symbol: str) -> str:
    """Drawings from one Flash symbol are one chart: 'PTS_Mouth_3-4' -> 'mouth-3-4'."""
    return re.sub(r"[^a-z0-9]+", "-", drawing_label(symbol).lower()).strip("-")


def drawing_tags(symbol: str, frame_labels: list[str]) -> list[str]:
    """Chart, plus frame labels as phonemes or free labels."""
    tags = [f"chart:{chart(symbol)}"]
    for label in frame_labels:
        label = label.strip()
        if not label:
            continue
        tag = f"phoneme:{'rest' if label == '-' else label}" if label in PHONEMES else f"label:{label}"
        if tag not in tags:
            tags.append(tag)
    return tags


def groups(slots: list[dict]) -> list[dict]:
    """Animator-facing groups from layer names: Mouth, Brow, Blink, and one
    Eye per mask (its iris, pupil and highlights). `slots` are version 1
    slot records across all rigs."""
    out = []
    for layer, label in GROUP_LAYERS:
        matches = [s["name"] for s in slots if s["layer"].strip().upper() == layer]
        for i, name in enumerate(matches, 1):
            out.append({"label": label if len(matches) == 1 else f"{label} {i}", "layers": [name]})
    masks = [s for s in slots if s.get("mask")]
    for i, mask in enumerate(masks, 1):
        eye = [s["name"] for s in slots
               if s.get("masked_by") == mask["name"] and s["layer"].strip().upper() in EYE_LAYERS]
        if eye:
            out.append({"label": f"Eye {i}" if len(masks) > 1 else "Eye", "layers": eye})
    return out


def far_color(poses_colors: list[list[float]]) -> list[float] | None:
    """The riggers' far-limb darkening: the most common pure darkening tint
    (multipliers 1, negative offsets) across the stock poses."""
    counts: dict[tuple, int] = {}
    for c in poses_colors:
        c = tuple(c)
        if c[3] == 1 and c[7] == 0 and sum(c[4:7]) < 0 and min(c[:3]) >= 0.99:
            counts[c] = counts.get(c, 0) + 1
    return list(max(counts, key=counts.get)) if counts else None
