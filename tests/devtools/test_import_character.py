"""Import Princess Twilight's stock rig and rebuild poses from the library alone."""

import io
import json

import numpy as np
import pytest

pytest.importorskip("devtools.flash.fla", reason="FLA-RE not found (set FLARE_DIR)")

from PIL import Image  # noqa: E402

from devtools.flash import evaluate as E  # noqa: E402
from devtools.flash import fla, render  # noqa: E402
from devtools.flash.import_character import import_character, nodes_bbox  # noqa: E402
from devtools.flash.library_compose import Library, compose_svg  # noqa: E402

STOCK = fla.FLARE_DIR / "fla" / "STK_C23_Princess_Twilight_Sparkle.fla"
pytestmark = pytest.mark.skipif(not STOCK.exists(), reason=f"{STOCK} missing")


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    out = tmp_path_factory.mktemp("twilight")
    import_character(STOCK, "~PTS_Character", "twilight", out, ppu=2.0, jobs=6)
    return out


def pixels(svg):
    return np.asarray(Image.open(io.BytesIO(render.rasterize(svg)))).astype(int)


@pytest.mark.parametrize("construction", [0, 4, 16, 31])
def test_library_recomposes_source_rig(library, construction):
    lib = Library(library)
    doc = fla.load(STOCK)
    ev = E.Evaluator(doc)
    root = next(s for s in doc.symbols if s.endswith("~PTS_Character"))
    frame = lib.rigs["Character"]["constructions"][construction]["frames"][0]

    x0, y0, x1, y1 = nodes_bbox(ev.evaluate(frame, root=root))
    w, h = int(x1 - x0) + 20, int(y1 - y0) + 20
    world = (1, 0, 0, 1, 10 - x0, 10 - y0)
    direct = pixels(render.frame_svg(ev.evaluate(frame, root=root, world=world), w, h, "#ffffff"))
    rebuilt = pixels(compose_svg(lib, "Character", construction, world, w, h, "#ffffff"))

    diff = np.abs(direct - rebuilt).max(axis=2)
    assert diff.mean() < 2.0, diff.mean()          # resampling along outlines only
    assert (diff > 64).mean() < 0.01


def test_reimport_keeps_drawing_ids(library):
    before = json.loads((library / "ids.json").read_text())
    import_character(STOCK, "~PTS_Character", "twilight", library, ppu=2.0, jobs=6)
    assert json.loads((library / "ids.json").read_text()) == before


def test_mouths_carry_phoneme_tags(library):
    drawings = Library(library).data["drawings"].values()
    tags = {tag for d in drawings if d["symbol"] == "PTS_Mouth_3-4" for tag in d["tags"]}
    assert {"happy", "sad", "a,e,i", "m,b,p"} <= tags
