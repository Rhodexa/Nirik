import json
import math

import pytest

from nirik.core import library as L
from nirik.core.affine import RotScaleRot, compose


def write_library(tmp_path):
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
    assert head.child_rig == "Head"
    entry = ch.rigs["Head"].constructions[0].slots["Head.SKULL"]
    assert entry.drawing == 2 and entry.color[0] == 0.5
    assert ch.rigs["Head"].slot("Head.IRIS").masked_by == "Head.EYE mask"
    assert ch.slot_drawings("Head.SKULL") == [2]


def test_draw_order_expands_child_rigs_and_skips_masks(tmp_path):
    ch = L.load(write_library(tmp_path))
    assert ch.draw_order() == ["Character.Body", "Head.IRIS", "Head.SKULL", "Character.Tail"]


def test_rejects_unknown_schema(tmp_path):
    (tmp_path / "character.json").write_text(json.dumps({"schema": 99}))
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


def test_parts_group_eye_layers_per_mask(tmp_path):
    from nirik.core import controls
    ch = L.load(write_library(tmp_path))
    parts = dict(controls.parts(ch))
    assert parts["Body"] == ["ROOT"]
    assert parts["Head"] == ["Character.HEAD"]
    assert parts["Eye"] == ["Head.IRIS"]


def test_part_labels():
    from nirik.core.controls import label
    assert label("Character.Hind leg_2") == "Hind Leg 2"
    assert label("Head.EAR_3") == "Ear 3"
    assert label("Character.=HEADCOMP=") == "Headcomp"
    assert label("Character.Arm OL") == "Arm OL"


def test_drawing_labels():
    from nirik.core.controls import drawing_label
    assert drawing_label("PTS_Wing_Front") == "Wing Front"
    assert drawing_label("PTS_HindLeg_3-4nomark") == "Hind Leg 3-4nomark"
    assert drawing_label("RY_Mouth_3-4") == "Mouth 3-4"
    assert drawing_label("table_top") == "table top"
