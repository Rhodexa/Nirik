"""Animator-facing selection: what the Parts buttons hold, what a click selects.

Everything comes from the library's structure and its explicit groups
(docs/format.md): Body (the root), one button per nested symbol (Head), then
the library's groups (Mouth, Eye 1, ...). Nirik doesn't read layer names.
"""

from __future__ import annotations

from .library import Character

ROOT = "ROOT"


def parts(char: Character) -> list[tuple[str, list[str]]]:
    """[(label, bone names)], in panel order."""
    out: list[tuple[str, list[str]]] = [("Body", [ROOT])]
    slots = char.all_slots()
    out += [(char.rigs[s.child_rig].name if s.child_rig in char.rigs else s.child_rig, [s.name])
            for s in slots.values() if s.child_rig]
    out += [(label, [n for n in layers if n in slots]) for label, layers in char.groups]
    return [(label, bones) for label, bones in out if bones]


def main_bones(char: Character) -> set[str]:
    return {b for _, bones in parts(char) for b in bones}


def more_parts(char: Character) -> dict[str, list[str]]:
    """Drawable layers outside the Parts buttons, per symbol: {symbol: [layer ids]}."""
    main = main_bones(char)
    out: dict[str, list[str]] = {}
    for rig in char.rigs.values():
        names = [s.name for s in rig.slots if s.canvas and not s.mask and s.name not in main]
        if names:
            out[rig.name] = names
    return out


def part_for_slot(char: Character, slot: str) -> list[str]:
    """Bones a plain click on `slot`'s artwork selects.

    A layer in a group selects the group; a layer clipped by the same mask as
    a group's layers (an eye white under the eye mask) selects that group;
    anything else in a nested symbol selects the layer carrying the symbol
    (the head); the rest selects the body.
    """
    slots = char.all_slots()
    for _, bones in parts(char):
        if slot in bones:
            return bones
    s = slots[slot]
    if s.masked_by:
        for _, layers in char.groups:
            if any(slots[n].masked_by == s.masked_by for n in layers if n in slots):
                return [n for n in layers if n in slots]
    if s.rig != char.root_rig:
        holder = next((h.name for h in slots.values() if h.child_rig == s.rig), None)
        if holder:
            return [holder]
    return [ROOT]


def part_level_bones(char: Character) -> set[str]:
    """Bones a plain click can select: groups, symbol carriers, the body."""
    return main_bones(char) | {s.name for s in char.all_slots().values() if s.child_rig} | {ROOT}


def pick(char: Character, stack: list[str], mode: str, extend: bool, selected: set[str],
         cycle_index: int = 0) -> set[str]:
    """New selection after clicking artwork whose pieces, front first, are `stack`.

    mode: PART (the part you mean), EXACT (the piece itself), CYCLE (the
    `cycle_index`-th piece). With `extend`, a click keeps the level of the
    current selection: if it holds exact pieces (an upper arm), a plain
    Shift+click adds exact pieces too instead of the whole body; clicking
    something already selected deselects it.
    """
    if mode == "PART" and extend and selected and not selected <= part_level_bones(char):
        mode = "EXACT"
    if mode == "CYCLE":
        target = [stack[cycle_index % len(stack)]]
    elif mode == "EXACT":
        target = [stack[0]]
    else:
        target = part_for_slot(char, stack[0])
    if not extend:
        return set(target)
    if set(target) <= selected:
        return selected - set(target)
    return selected | set(target)
