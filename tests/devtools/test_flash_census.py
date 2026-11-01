import math

import pytest

pytest.importorskip("devtools.flash.fla", reason="FLA-RE not found (set FLARE_DIR)")

from devtools.flash.census import _runs, symbol_group, transform_features  # noqa: E402


def test_rig_codes_map_to_focus_groups():
    assert symbol_group("~PTS_Character") is None  # leading ~ is not a rig code
    assert symbol_group("PTS_Head") == "twilight"
    assert symbol_group("folder/RA_Eye") == "rarity"
    assert symbol_group("FS_WingBack") == "other_char"
    assert symbol_group("table_top") is None


def test_mirror_is_not_skew():
    assert transform_features((-1, 0, 0, 1, 0, 0)) == ["transform: mirror"]


def test_rotation_is_not_skew():
    r = math.radians(40)
    assert transform_features((math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)) == []


def test_skew_and_non_uniform_scale():
    s = math.radians(20)
    assert "transform: skew" in transform_features((1, 0, -math.sin(s), math.cos(s), 0, 0))
    assert transform_features((2, 0, 0, 1, 0, 0)) == ["transform: non-uniform scale"]


def test_runs():
    assert _runs([1, 1, 2, 2, 2, 1]) == [2, 3, 1]
