"""2D affine decomposition for skew-capable bone chains.

Bones key location, rotation and scale but not shear. Any 2x2 linear part
factors as R(rot_a) @ diag(sx, sy) @ R(rot_b) (SVD), which maps onto two
bones: a parent with rotation rot_a and scale (sx, sy), and a child with
rotation rot_b. With Inherit Scale = Full, the child's rotation inside the
parent's non-uniform scale reproduces the shear.

Matrices use the Flash convention (a, b, c, d):
  x' = a*x + c*y
  y' = b*x + d*y
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

Mat2 = tuple[float, float, float, float]  # (a, b, c, d)


@dataclass(frozen=True)
class RotScaleRot:
    rot_a: float  # radians, applied last (parent bone rotation)
    sx: float     # parent bone scale; sx >= 0
    sy: float     # negative when the matrix mirrors
    rot_b: float  # radians, applied first (child bone rotation)


def _rot(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s], [s, c]])


def decompose(m: Mat2) -> RotScaleRot:
    a, b, c, d = m
    u, sigma, vt = np.linalg.svd(np.array([[a, c], [b, d]]))
    sx, sy = float(sigma[0]), float(sigma[1])
    # SVD may return reflections in u or vt; fold them into the sign of sy
    # so both factors are pure rotations.
    if np.linalg.det(u) < 0:
        u[:, 1] *= -1
        sy = -sy
    if np.linalg.det(vt) < 0:
        vt[1, :] *= -1
        sy = -sy
    return RotScaleRot(
        rot_a=math.atan2(u[1, 0], u[0, 0]),
        sx=sx,
        sy=sy,
        rot_b=math.atan2(vt[1, 0], vt[0, 0]),
    )


def compose(r: RotScaleRot) -> Mat2:
    m = _rot(r.rot_a) @ np.diag([r.sx, r.sy]) @ _rot(r.rot_b)
    return (float(m[0, 0]), float(m[1, 0]), float(m[0, 1]), float(m[1, 1]))
