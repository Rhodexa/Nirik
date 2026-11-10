import json
import math

import pytest

from nirik.core import library as L
from nirik.core.affine import RotScaleRot, compose

FAR = [1.0, 1.0, 1.0, 1.0, -16.0, -21.0, -16.0, 0.0]

V2 = {
    "format": "nirik.library", "version": 2, "label": "Test", "root": "Character",
    "pixels_per_unit": 2.0, "units_per_meter": 300,
    "symbols": {
        "Character": {"label": "Test", "layers": [
            {"id": "Character.Body", "label": "Body", "kind": "drawing", "canvas": [0, 0, 10, 10]},
            {"id": "Character.HEAD", "label": "Head", "kind": "symbol", "symbols": ["Head"]},
            {"id": "Character.Tail", "label": "Tail", "kind": "drawing", "canvas": [0, 0, 5, 5]},
        ], "poses": [
            {"label": "Rotation", "layers": {
                "Character.Body": {"drawing": 1, "matrix": [1, 0, 0, 1, 0, 0]},
                "Character.HEAD": {"symbol": "Head", "pose": 0, "matrix": [1, 0, 0, 1, 5, -20]}}}]},
        "Head": {"label": "Head", "layers": [
            {"id": "Head.EYE mask", "label": "Eye mask", "kind": "mask", "canvas": [0, 0, 4, 4]},
            {"id": "Head.IRIS", "label": "Iris", "kind": "drawing", "masked_by": "Head.EYE mask",
             "canvas": [0, 0, 2, 2]},
            {"id": "Head.EYEWHITE", "label": "Eye White", "kind": "drawing", "masked_by": "Head.EYE mask",
             "canvas": [0, 0, 4, 4]},
            {"id": "Head.SKULL", "label": "Skull", "kind": "drawing", "canvas": [0, 0, 8, 8]},
        ], "poses": [{"label": "", "layers": {
            "Head.SKULL": {"drawing": 2, "matrix": [1, 0, 0, 1, 0, 0],
                           "color": [0.5, 0.5, 0.5, 1, 0, 0, 0, 0]}}}]},
    },
    "drawings": {"1": {"layer": "Character.Body", "label": "Body", "tags": ["chart:body"],
                       "file": "drawings/1.png"},
                 "2": {"layer": "Head.SKULL", "label": "Skull", "tags": ["chart:skull", "view:3q"],
                       "file": "drawings/2.png"}},
    "groups": [{"label": "Eye", "layers": ["Head.IRIS"]}],
    "far_color": FAR,
}


def write_library(tmp_path, **changes):
    data = json.loads(json.dumps(V2))
    data.update(changes)
    (tmp_path / "library.json").write_text(json.dumps(data))
    return tmp_path


def write_v1(tmp_path):
    data = {
        "schema": 1, "name": "test", "ppu": 2.0, "root_rig": "Character",
        "rigs": {
            "Character": {"symbol": "~T_Character", "slots": [
                {"name": "Character.Body", "layer": "Body", "order": 0, "canvas": [0, 0, 10, 10]},
                {"name": "Character.HEAD", "layer": "HEAD", "order": 1, "rig": "Head"},
                {"name": "Character.Tail", "layer": "Tail", "order": 2, "canvas": [0, 0, 5, 5]},
            ], "constructions": [
                {"id": 0, "frames": [0], "labels": ["Rotation"], "slots": {
                    "Character.Body": {"matrix": [1, 0, 0, 1, 0, 0], "drawing": 1},
                    "Character.HEAD": {"matrix": [1, 0, 0, 1, 5, -20], "construction": 0}}}]},
            "Head": {"symbol": "~T_Head", "slots": [
                {"name": "Head.EYE mask", "layer": "EYE mask", "order": 0, "mask": True, "canvas": [0, 0, 4, 4]},
                {"name": "Head.IRIS", "layer": "IRIS", "order": 1, "masked_by": "Head.EYE mask",
                 "canvas": [0, 0, 2, 2]},
                {"name": "Head.SKULL", "layer": "SKULL", "order": 2, "canvas": [0, 0, 8, 8]},
            ], "constructions": [{"id": 0, "frames": [0], "labels": [], "slots": {
                "Head.SKULL": {"matrix": [1, 0, 0, 1, 0, 0], "drawing": 2,
                               "color": [0.5, 0.5, 0.5, 1, 0, 0, 0, 0]}}}]},
        },
        "drawings": {"1": {"slot": "Character.Body", "symbol": "T_Body", "frames": [0], "tags": []},
                     "2": {"slot": "Head.SKULL", "symbol": "T_Skull", "frames": [0], "tags": ["3q"]}},
    }
    (tmp_path / "character.json").write_text(json.dumps(data))
    return tmp_path


def test_load(tmp_path):
    ch = L.load(write_library(tmp_path))
    assert ch.root_rig == "Character" and set(ch.rigs) == {"Character", "Head"}
    head = ch.rigs["Character"].slot("Character.HEAD")
    assert head.child_rig == "Head" and head.label == "Head"
    entry = ch.rigs["Head"].constructions[0].slots["Head.SKULL"]
    assert entry.drawing == 2 and entry.color[0] == 0.5
    assert ch.rigs["Head"].slot("Head.IRIS").masked_by == "Head.EYE mask"
    assert ch.rigs["Head"].slot("Head.EYE mask").mask
    assert ch.slot_drawings("Head.SKULL") == [2]
    assert ch.drawings[2].tag("chart") == "skull" and ch.drawings[2].tag("view") == "3q"
    assert ch.drawing_path(2) == ch.root / "drawings" / "2.png"
    assert ch.far_color() == tuple(FAR) and ch.units_per_meter == 300


def test_v1_still_loads_without_guessing(tmp_path):
    ch = L.load(write_v1(tmp_path))
    assert ch.groups == [] and ch.far_color() is None
    assert ch.rigs["Head"].slot("Head.IRIS").label == "IRIS"  # raw layer name, no clean-up


def test_draw_order_expands_child_rigs_and_skips_masks(tmp_path):
    ch = L.load(write_library(tmp_path))
    assert ch.draw_order() == ["Character.Body", "Head.IRIS", "Head.EYEWHITE", "Head.SKULL",
                               "Character.Tail"]


def test_subtree_is_one_symbol_and_what_it_holds(tmp_path):
    ch = L.load(write_library(tmp_path))
    head = ch.subtree("Head")
    assert head.root_rig == "Head" and list(head.rigs) == ["Head"]
    assert head.draw_order() == ["Head.IRIS", "Head.EYEWHITE", "Head.SKULL"]
    assert list(head.drawings) == [2] and head.root == ch.root
    assert head.groups == [("Eye", ["Head.IRIS"])] and head.cycle is None
    assert head.rigs["Head"].label == "Head" and ch.rigs["Character"].label == "Test"
    assert ch.subtree("Character") is ch
    assert ch.symbols_below("Character") == ["Character", "Head"]


def test_order_span_covers_nested_stacks_and_empty_layers(tmp_path):
    ch = L.load(write_library(tmp_path))
    assert ch.order_span("Character.Body") == (0, 1)
    assert ch.order_span("Character.HEAD") == (1, 3)   # iris, eye white, skull
    assert ch.order_span("Head.EYE mask") == (1, 0)    # masks draw nothing
    assert ch.order_span("Character.Tail") == (4, 1)


def test_rejects_unknown_versions(tmp_path):
    (tmp_path / "character.json").write_text(json.dumps({"schema": 99}))
    with pytest.raises(ValueError):
        L.load(tmp_path)
    (tmp_path / "library.json").write_text(json.dumps({"format": "nirik.library", "version": 3}))
    with pytest.raises(ValueError):
        L.load(tmp_path)


def test_to_plane_flips_y_and_scales_translation():
    # 90 deg clockwise on screen (y down) is counter-clockwise with y up.
    m = L.to_plane((0, 1, -1, 0, 100, 50), units_per_meter=100)
    assert m == (0, -1, 1, 0, 1.0, -0.5)


def test_socket_bones_roundtrip():
    s = math.radians(15)
    m = (1.2, 0.3, -math.sin(s), 0.9, 0.4, -0.2)
    pair = L.socket_bones(m)
    a, b, c, d = compose(RotScaleRot(pair.rot_a, pair.scale[0], pair.scale[1], pair.rot_b))
    assert (a, b, c, d) == pytest.approx(m[:4])
    assert pair.location == (0.4, -0.2)


def test_parts_come_from_structure_and_groups(tmp_path):
    from nirik.core import controls
    ch = L.load(write_library(tmp_path))
    parts = dict(controls.parts(ch))
    assert parts["Body"] == ["ROOT"]
    assert parts["Head"] == ["Character.HEAD"]
    assert parts["Eye"] == ["Head.IRIS"]


def test_click_on_slot_selects_its_part(tmp_path):
    from nirik.core.controls import part_for_slot
    ch = L.load(write_library(tmp_path))
    assert part_for_slot(ch, "Head.IRIS") == ["Head.IRIS"]        # eye look (a group)
    assert part_for_slot(ch, "Head.EYEWHITE") == ["Head.IRIS"]    # same mask as the group
    assert part_for_slot(ch, "Head.SKULL") == ["Character.HEAD"]  # rest of the face -> head
    assert part_for_slot(ch, "Character.Tail") == ["ROOT"]        # body pieces -> body


def test_pick_keeps_the_level_and_toggles(tmp_path):
    from nirik.core.controls import pick
    ch = L.load(write_library(tmp_path))
    stack = ["Head.SKULL", "Character.Body"]  # front first
    # plain click: the part you mean
    assert pick(ch, stack, "PART", False, set()) == {"Character.HEAD"}
    # exact pieces selected: Shift+click adds exact pieces, not the carrier
    sel = pick(ch, ["Character.Tail"], "EXACT", False, set())
    assert sel == {"Character.Tail"}
    assert pick(ch, stack, "PART", True, sel) == {"Character.Tail", "Head.SKULL"}
    # part-level selection: Shift+click stays at part level
    assert pick(ch, stack, "PART", True, {"ROOT"}) == {"ROOT", "Character.HEAD"}
    # Shift+click on something selected deselects it
    assert pick(ch, stack, "EXACT", True, {"Head.SKULL", "Character.Tail"}) == {"Character.Tail"}
    assert pick(ch, stack, "CYCLE", False, set(), cycle_index=1) == {"Character.Body"}
