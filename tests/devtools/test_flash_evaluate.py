import math
import xml.etree.ElementTree as ET

import pytest

pytest.importorskip("devtools.flash.fla", reason="FLA-RE not found (set FLARE_DIR)")

from devtools.flash import evaluate as E  # noqa: E402
from devtools.flash.fla import MAIN, Document  # noqa: E402

NS = "http://ns.adobe.com/xfl/2008/"


def symbol(name, layers):
    return ET.fromstring(
        f'<DOMSymbolItem xmlns="{NS}" name="{name}"><timeline><DOMTimeline name="{name}">'
        f"<layers>{layers}</layers></DOMTimeline></timeline></DOMSymbolItem>")


def layer(frames, name="L", extra=""):
    return f'<DOMLayer name="{name}" {extra}><frames>{frames}</frames></DOMLayer>'


def frame(index, duration, elements="", extra=""):
    return f'<DOMFrame index="{index}" duration="{duration}" {extra}><elements>{elements}</elements></DOMFrame>'


def instance(name, attrs="", matrix="", inner=""):
    m = f"<matrix><Matrix {matrix}/></matrix>" if matrix else ""
    return f'<DOMSymbolInstance libraryItemName="{name}" {attrs}>{m}{inner}</DOMSymbolInstance>'


SQUARE = ('<DOMShape><fills><FillStyle index="1"><SolidColor color="#FF0000"/></FillStyle></fills>'
          '<edges><Edge fillStyle1="1" edges="!0 0|200 0!200 0|200 200!200 200|0 200!0 200|0 0"/></edges>'
          "</DOMShape>")


def four_frame_child():
    return symbol("Child", layer("".join(frame(i, 1) for i in range(4))))


def doc(main_layers, *others):
    symbols = {MAIN: symbol(MAIN, main_layers)}
    symbols.update({s.get("name"): s for s in others})
    return Document(path=None, symbols=symbols, width=100, height=100, fps=24)


def nodes_at(d, f, kind="instance"):
    return [n for n in E.Evaluator(d).evaluate(f) if n.kind == kind]


def child_frames(attrs, frames=range(10), span_start=0):
    d = doc(layer(frame(span_start, 20, instance("Child", attrs))), four_frame_child())
    return [nodes_at(d, f)[0].child_frame for f in frames]


# ── graphic symbol timing ────────────────────────────────────────────────────

def test_graphic_loop_wraps_from_first_frame():
    assert child_frames('symbolType="graphic" loop="loop" firstFrame="1"', range(6)) == [1, 2, 3, 0, 1, 2]


def test_play_once_holds_last_frame():
    assert child_frames('symbolType="graphic" loop="play once" firstFrame="2"', range(4)) == [2, 3, 3, 3]


def test_single_frame_never_advances():
    assert child_frames('symbolType="graphic" loop="single frame" firstFrame="3"', range(3)) == [3, 3, 3]


def test_loop_within_last_frame_range():
    assert child_frames('symbolType="graphic" loop="loop" firstFrame="1" lastFrame="2"', range(4)) == [1, 2, 1, 2]


def test_offset_counts_from_span_start():
    assert child_frames('symbolType="graphic" loop="loop"', [5, 6, 7], span_start=5) == [0, 1, 2]


def test_movie_clip_plays_from_span_start():
    assert child_frames("", range(5)) == [0, 1, 2, 3, 0]


# ── classic tweens ───────────────────────────────────────────────────────────

def tweened(m0, m1, frame_extra="", inst_extra="", f=5):
    d = doc(layer(frame(0, 10, instance("Child", inst_extra, m0), f'tweenType="motion" {frame_extra}')
                  + frame(10, 1, instance("Child", inst_extra, m1))), four_frame_child())
    return nodes_at(d, f)[0]


def test_tween_linear_translation():
    n = tweened('tx="0"', 'tx="100"')
    assert n.local[4] == pytest.approx(50)
    assert n.tween == "classic"


def test_tween_acceleration_eases_out():
    assert tweened('tx="0"', 'tx="100"', 'acceleration="100"').local[4] == pytest.approx(75)


def test_tween_rotation_takes_shortest_path():
    def rot(deg):
        r = math.radians(deg)
        return f'a="{math.cos(r)}" b="{math.sin(r)}" c="{-math.sin(r)}" d="{math.cos(r)}"'
    a, b = tweened(rot(170), rot(-170)).local[:2]
    assert math.degrees(math.atan2(b, a)) == pytest.approx(180, abs=1e-6) or \
        math.degrees(math.atan2(b, a)) == pytest.approx(-180, abs=1e-6)


def test_tween_pivots_about_transformation_point():
    # Rotate 0 -> 90 deg about local point (10, 0), which stays put at (10, 0).
    tp = '<transformationPoint><Point x="10" y="0"/></transformationPoint>'
    d = doc(layer(frame(0, 10, instance("Child", "", 'tx="0"', tp), 'tweenType="motion"')
                  + frame(10, 1, instance("Child", "", 'a="0" b="1" c="-1" d="0" tx="10" ty="-10"', tp))),
            four_frame_child())
    n = nodes_at(d, 5)[0]
    assert E.apply(n.local, 10, 0) == (pytest.approx(10), pytest.approx(0))


def test_tween_needs_same_symbol_on_both_keys():
    d = doc(layer(frame(0, 10, instance("Child", "", 'tx="0"'), 'tweenType="motion"')
                  + frame(10, 1, instance("Other", "", 'tx="100"'))), four_frame_child())
    assert nodes_at(d, 5)[0].local[4] == 0


# ── color transforms ─────────────────────────────────────────────────────────

def test_color_kinds():
    def read(attrs):
        el = ET.fromstring(f'<X xmlns="{NS}"><color><Color {attrs}/></color></X>')
        return E.read_color(el)
    assert read('alphaMultiplier="0.5"')[1] == "alpha"
    xf, kind = read('brightness="-0.5"')
    assert kind == "brightness" and xf.mult[:3] == (0.5, 0.5, 0.5)
    xf, kind = read('tintMultiplier="1" tintColor="#FF0000"')
    assert kind == "tint" and xf.off[:3] == (255, 0, 0) and xf.mult[0] == 0


def test_color_composes_parent_last():
    child = E.ColorXf((0.5, 1, 1, 1), (10, 0, 0, 0))
    parent = E.ColorXf((0.5, 1, 1, 0.5), (100, 0, 0, 0))
    both = child.then(parent)
    # 0.5 * (0.5 x + 10) + 100
    assert both.mult[0] == 0.25 and both.off[0] == 105 and both.mult[3] == 0.5


# ── masks and draw order ─────────────────────────────────────────────────────

def test_mask_layer_clips_masked_layers_only():
    layers = (layer(frame(0, 1, SQUARE), "mask", 'layerType="mask"')
              + layer(frame(0, 1, SQUARE), "masked", 'parentLayerIndex="0"')
              + layer(frame(0, 1, SQUARE), "plain"))
    shapes = nodes_at(doc(layers), 0, "shape")
    assert [n.layer for n in shapes] == ["plain", "masked"]  # back to front
    assert shapes[0].masks == ()
    assert len(shapes[1].masks) == 1 and len(shapes[1].masks[0].nodes) == 1


def test_guide_layers_are_skipped():
    layers = layer(frame(0, 1, SQUARE), "g", 'layerType="guide"') + layer(frame(0, 1, SQUARE), "n")
    assert [n.layer for n in nodes_at(doc(layers), 0, "shape")] == ["n"]
