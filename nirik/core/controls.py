"""Animator-facing parts: which bones a click on "Mouth" or "Eye 1" selects.

Derived from the stock rigs' semantic layer names, so any character imported
from the show's rigs gets the same short list. Everything else stays reachable
as "more" controls.
"""

from __future__ import annotations

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
