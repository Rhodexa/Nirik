"""Build Princess Twilight in headless Blender and compare with the library rebuild."""

import io
import subprocess
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("devtools.flash.fla", reason="FLA-RE not found (set FLARE_DIR)")

from PIL import Image  # noqa: E402

from devtools.blender_env import blender_cmd, blender_env  # noqa: E402
from devtools.flash import render  # noqa: E402
from devtools.flash.library_compose import Library, compose_svg  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "blender" / "scripts" / "render_construction.py"
UNITS_PER_METER = 300.0  # nirik.bridge.rig_build.UNITS_PER_METER
SCALE = 1.5              # output pixels per library unit


def pixels(svg):
    return np.asarray(Image.open(io.BytesIO(render.rasterize(svg)))).astype(int)


@pytest.mark.blender
@pytest.mark.parametrize("construction", [4, 31])
def test_blender_rig_matches_library(twilight_library, tmp_path, construction):
    lib = Library(twilight_library)
    pad = 600  # frame the shot from the rebuilt image's alpha bounds
    pre = pixels(compose_svg(lib, "Character", construction, (1, 0, 0, 1, pad, pad), 2 * pad, 2 * pad))
    ys, xs = np.nonzero(pre[..., 3])
    x0, x1, y0, y1 = xs.min() - pad - 10, xs.max() - pad + 10, ys.min() - pad - 10, ys.max() - pad + 10
    w, h = int((x1 - x0) * SCALE), int((y1 - y0) * SCALE)
    world = (SCALE, 0, 0, SCALE, -x0 * SCALE, -y0 * SCALE)
    expected = pixels(compose_svg(lib, "Character", construction, world, w, h, "#ffffff"))

    out = tmp_path / f"c{construction}.png"
    args = [str(twilight_library), "Character", str(construction), str(out),
            str((x0 + x1) / 2 / UNITS_PER_METER), str(-(y0 + y1) / 2 / UNITS_PER_METER),
            str(max(w, h) / SCALE / UNITS_PER_METER), str(w), str(h)]
    result = subprocess.run(blender_cmd("-b", "--factory-startup", "--python-exit-code", "1",
                                        "--python", str(SCRIPT), "--", *args),
                            env=blender_env(), capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]

    got = np.asarray(Image.open(out).convert("RGBA")).astype(int)
    diff = np.abs(expected - got).max(axis=2)
    # Remaining differences: Blender antialiases and blends in linear light,
    # Flash/resvg in sRGB (thinner outlines, lighter translucent shadow).
    assert diff.mean() < 8, diff.mean()
    assert (diff > 64).mean() < 0.03
