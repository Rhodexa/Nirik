import math
import random

import pytest

from nirik.core.affine import RotScaleRot, compose, decompose


def assert_mat_close(m1, m2, tol=1e-9):
    assert all(abs(x - y) < tol for x, y in zip(m1, m2)), (m1, m2)


def test_identity():
    r = decompose((1, 0, 0, 1))
    assert_mat_close(compose(r), (1, 0, 0, 1))
    assert r.sx == pytest.approx(1) and r.sy == pytest.approx(1)


def test_pure_rotation_has_unit_scale():
    t = math.radians(30)
    r = decompose((math.cos(t), math.sin(t), -math.sin(t), math.cos(t)))
    assert (r.sx, r.sy) == (pytest.approx(1), pytest.approx(1))
    assert math.remainder(r.rot_a + r.rot_b - t, math.tau) == pytest.approx(0, abs=1e-9)


def test_mirror_folds_into_negative_sy():
    r = decompose((-1, 0, 0, 1))
    assert r.sx > 0 and r.sy < 0
    assert_mat_close(compose(r), (-1, 0, 0, 1))


@pytest.mark.parametrize("seed", range(200))
def test_roundtrip_random_affine(seed):
    rng = random.Random(seed)
    m = tuple(rng.uniform(-3, 3) for _ in range(4))
    assert_mat_close(compose(decompose(m)), m)


def test_flash_skew():
    # Flash skewX=20deg, skewY=0: a=1, b=0, c=-sin(20), d=cos(20)
    s = math.radians(20)
    m = (1.0, 0.0, -math.sin(s), math.cos(s))
    assert_mat_close(compose(decompose(m)), m)


def test_compose_is_rotation_times_scale_times_rotation():
    m = compose(RotScaleRot(rot_a=0.0, sx=2.0, sy=3.0, rot_b=0.0))
    assert_mat_close(m, (2, 0, 0, 3))
