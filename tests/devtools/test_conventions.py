"""The Flash converter's conventions, and the version 1 -> 2 upgrade."""

import json

from devtools import library_v2
from devtools.flash import conventions as C
from nirik.core import controls
from nirik.core import library as L

V1 = {
    "schema": 1, "name": "test", "ppu": 2.0, "root_rig": "Character",
    "source": {"file": "stk_test.fla", "root": "~T_Character"},
    "rigs": {
        "Character": {"symbol": "~T_Character", "slots": [
            {"name": "Character.Body", "layer": "Body", "order": 0, "canvas": [0, 0, 10, 10]},
            {"name": "Character.HEAD", "layer": "HEAD", "order": 1, "rig": "Head"},
        ], "constructions": [
            {"id": 0, "frames": [0, 1], "labels": ["Rotation"], "slots": {
                "Character.Body": {"matrix": [1, 0, 0, 1, 0, 0], "drawing": 1,
                                   "color": [1, 1, 1, 1, -16, -21, -16, 0]},
                "Character.HEAD": {"matrix": [1, 0, 0, 1, 5, -20], "construction": 0}}}]},
        "Head": {"symbol": "~T_Head", "slots": [
            {"name": "Head.EYE mask", "layer": "EYE mask", "order": 0, "mask": True, "canvas": [0, 0, 4, 4]},
            {"name": "Head.IRIS", "layer": "IRIS", "order": 1, "masked_by": "Head.EYE mask",
             "canvas": [0, 0, 2, 2]},
            {"name": "Head.MOUTH", "layer": "MOUTH", "order": 2, "canvas": [0, 0, 3, 3]},
        ], "constructions": [{"id": 0, "frames": [0], "labels": [], "slots": {
            "Head.MOUTH": {"matrix": [1, 0, 0, 1, 0, 0], "drawing": 2}}}]},
    },
    "drawings": {"1": {"slot": "Character.Body", "symbol": "T_Body", "frames": [0], "tags": []},
                 "2": {"slot": "Head.MOUTH", "symbol": "T_Mouth_3-4", "frames": [0],
                       "tags": ["happy", "a,e,i", "-"]}},
}


def test_labels():
    assert C.layer_label("Character.Hind leg_2") == "Hind Leg 2"
    assert C.layer_label("Head.EAR_3") == "Ear 3"
    assert C.layer_label("Character.Arm OL") == "Arm OL"
    assert C.drawing_label("PTS_Wing_Front") == "Wing Front"
    assert C.drawing_label("PTS_HindLeg_3-4nomark") == "Hind Leg 3-4nomark"
    assert C.drawing_label("table_top") == "table top"


def test_tags_from_frame_labels():
    assert C.drawing_tags("PTS_Mouth_3-4", ["happy", "a,e,i", "-"]) == [
        "chart:mouth-3-4", "label:happy", "phoneme:a,e,i", "phoneme:rest"]


def test_far_color_is_the_common_darkening():
    dark = [1, 1, 1, 1, -16, -21, -16, 0]
    assert C.far_color([dark, dark, [0.5, 0.5, 0.5, 1, 0, 0, 0, 0]]) == dark
    assert C.far_color([[1, 1, 1, 0.2, 0, 0, 0, 0]]) is None


def test_upgrade_writes_explicit_fields_nirik_reads(tmp_path):
    (tmp_path / "character.json").write_text(json.dumps(V1))
    (tmp_path / "ids.json").write_text("{}")
    (tmp_path / ".udim" / "Head.MOUTH").mkdir(parents=True)
    assert library_v2.upgrade(tmp_path)
    assert (tmp_path / "library.json").exists() and not (tmp_path / "character.json").exists()
    assert (tmp_path / ".converter" / "ids.json").exists()
    assert (tmp_path / ".converter" / "character.v1.json").exists()
    assert (tmp_path / ".nirik" / "palettes" / "Head.MOUTH").is_dir()

    ch = L.load(tmp_path)
    assert ch.groups == [("Mouth", ["Head.MOUTH"]), ("Eye", ["Head.IRIS"])]
    assert ch.far_color() == (1, 1, 1, 1, -16, -21, -16, 0)
    assert ch.drawings[2].label == "Mouth 3-4" and ch.drawings[2].tag("phoneme") == "a,e,i"
    assert ch.rigs["Character"].slot("Character.HEAD").label == "Head"
    # same structure as before the upgrade
    entry = ch.rigs["Character"].constructions[0].slots["Character.HEAD"]
    assert entry.construction == 0 and entry.matrix == (1, 0, 0, 1, 5, -20)
    assert dict(controls.parts(ch))["Mouth"] == ["Head.MOUTH"]


def test_upgrade_of_a_picture_keeps_its_art_group(tmp_path):
    pic = {"schema": 1, "name": "mailbox", "ppu": 1.0, "root_rig": "Prop",
           "source": {"file": "mailbox base.png", "pieces": 1},
           "rigs": {"Prop": {"symbol": "mailbox", "slots": [
               {"name": "Prop.Art", "layer": "ART", "order": 0, "canvas": [0, 0, 1, 1]}],
               "constructions": [{"id": 0, "frames": [0], "labels": [], "slots": {
                   "Prop.Art": {"matrix": [1, 0, 0, 1, 0, 0], "drawing": 1}}}]}},
           "drawings": {"1": {"slot": "Prop.Art", "symbol": "mailbox", "frames": [0], "tags": ["#1"]}}}
    (tmp_path / "character.json").write_text(json.dumps(pic))
    library_v2.upgrade(tmp_path)
    ch = L.load(tmp_path)
    assert ch.groups == [("Art", ["Prop.Art"])] and ch.far_color() is None
