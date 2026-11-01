"""Cross-check the evaluator against FLA-RE on real show data.

At frame 0 every graphic symbol shows its firstFrame, which is the case FLA-RE
handles; with color transforms stripped both renders must agree.
"""

import io
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("devtools.flash.fla", reason="FLA-RE not found (set FLARE_DIR)")

from PIL import Image  # noqa: E402

from devtools.flash import evaluate as E  # noqa: E402
from devtools.flash import fla, render  # noqa: E402
from devtools.flash.fla import FI  # noqa: E402

SCENE = fla.FLARE_DIR / "fla" / "S08E23" / "MLP823_027.fla"


def only_scene_layer(container, layer):
    return container == fla.MAIN and layer != "SCENE"


def pixels(svg: str) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(render.rasterize(svg)))).astype(int)


@pytest.mark.skipif(not SCENE.exists(), reason=f"{SCENE} missing")
def test_frame0_matches_fla_re():
    doc = fla.load(SCENE)
    nodes = E.Evaluator(doc, only_scene_layer).evaluate(0)
    scene = next(n for n in nodes if n.kind == "instance" and n.depth == 0)
    for n in nodes:
        n.color = E.COLOR_IDENTITY
    ours = render.frame_svg(nodes, doc.width, doc.height, "#ffffff")

    body, defs = FI._render_sym(scene.symbol, doc.symbols, scene.child_frame)
    theirs = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{doc.width}" height="{doc.height}" '
              f'viewBox="0 0 {doc.width} {doc.height}"><defs>{"".join(defs)}</defs>'
              f'<rect width="{doc.width}" height="{doc.height}" fill="#ffffff"/>'
              f'<g transform="{render._mat(scene.matrix)}">{"".join(body)}</g></svg>')

    diff = np.abs(pixels(ours) - pixels(theirs)).max(axis=2)
    assert diff.mean() < 0.01
    assert (diff > 8).sum() < 0.0002 * diff.size  # antialiasing at mask edges only
