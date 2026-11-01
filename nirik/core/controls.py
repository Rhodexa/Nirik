"""Animator-facing parts: which bones a click on "Mouth" or "Eye 1" selects.

Derived from the stock rigs' semantic layer names, so any character imported
from the show's rigs gets the same short list. Everything else stays reachable
as "more" controls.
"""

from __future__ import annotations

import re

from .library import Character

ROOT = "ROOT"
EYE_LAYERS = {"IRIS", "PUPIL", "HIGHLIGHTS"}
SINGLE = (("MOUTH", "Mouth"), ("BROW", "Brow"), ("BLINK", "Blink"))


def parts(char: Character) -> list[tuple[str, list[str]]]:
    """[(label, bone names)], in panel order."""
    out: list[tuple[str, list[str]]] = [("Body", [ROOT])]
    slots = list(char.all_slots().values())
    out += [(s.child_rig, [s.name]) for s in slots if s.child_rig]

    for layer, label in SINGLE:
        matches = [s.name for s in slots if s.layer.strip().upper() == layer]
        for i, name in enumerate(matches, 1):
            out.append((label if len(matches) == 1 else f"{label} {i}", [name]))

    masks = [s for s in slots if s.mask]
    for i, mask in enumerate(masks, 1):
        eye = [s.name for s in slots
               if s.masked_by == mask.name and s.layer.strip().upper() in EYE_LAYERS]
        if eye:
            out.append((f"Eye {i}" if len(masks) > 1 else "Eye", eye))
    return out


def main_bones(char: Character) -> set[str]:
    return {b for _, bones in parts(char) for b in bones}


def label(slot_name: str) -> str:
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


def more_parts(char: Character) -> dict[str, list[str]]:
    """Drawable slots outside the main parts, per rig: {rig: [slot names]}."""
    main = main_bones(char)
    out: dict[str, list[str]] = {}
    for rig in char.rigs.values():
        names = [s.name for s in rig.slots if s.canvas and not s.mask and s.name not in main]
        if names:
            out[rig.name] = names
    return out


def drawing_label(symbol: str) -> str:
    """What a drawing shows: 'PTS_Wing_Front' -> 'Wing Front', 'PTS_HindLeg_3-4nomark' ->
    'Hind Leg 3-4nomark'. Riggers reuse layers (a layer named "Neck" may hold a
    wing), so the current drawing names a part better than its layer does."""
    parts = symbol.split("_")
    if len(parts) > 1 and parts[0].isupper():
        parts = parts[1:]  # rig code (PTS, RY, ...)
    words = [w for p in parts for w in re.sub(r"(?<=[a-z])(?=[A-Z])", " ", p).split()]
    return " ".join(words)
