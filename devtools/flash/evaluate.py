"""Frame-accurate XFL timeline evaluator.

evaluate(doc, frame) walks the main timeline at one frame and returns every
visible element as a flat, back-to-front list of Nodes. Each Node carries its
world matrix, composed color transform and mask stack. Instances appear before
their contents, so the list doubles as a pre-order tree walk (Node.parent).

Supported:
  graphic-symbol frame resolution: loop, play once, single frame, reverse
    variants, firstFrame/lastFrame, offset from the keyframe span start
  movie clips: approximated as playing from the span start
  classic tweens: Flash-style matrix interpolation about the transformation
    point, rotation direction, acceleration easing, color lerp
  color transforms: alpha, brightness, tint, advanced; composed down the tree
  mask layers, nested mask stacks
  groups (with FLA-RE's redundant-shape-matrix rule)

Not supported (recorded on Node.unsupported for the census): shape tweens,
motion-object tweens, custom eases, motion guides, filters, blend modes,
3D transforms.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element

from .fla import FI, MAIN, Document, t

Mat = tuple[float, float, float, float, float, float]  # (a, b, c, d, tx, ty)
IDENTITY: Mat = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

TAG_INSTANCE = t("DOMSymbolInstance")
TAG_SHAPE = t("DOMShape")
TAG_GROUP = t("DOMGroup")
TAG_BITMAP = t("DOMBitmapInstance")
TEXT_TAGS = {t("DOMStaticText"), t("DOMDynamicText"), t("DOMInputText")}


# ── Matrices ────────────────────────────────────────────────────────────────

def mat_mul(p: Mat, c: Mat) -> Mat:
    """p ∘ c: apply c first, then p."""
    return (p[0] * c[0] + p[2] * c[1], p[1] * c[0] + p[3] * c[1],
            p[0] * c[2] + p[2] * c[3], p[1] * c[2] + p[3] * c[3],
            p[0] * c[4] + p[2] * c[5] + p[4], p[1] * c[4] + p[3] * c[5] + p[5])


def apply(m: Mat, x: float, y: float) -> tuple[float, float]:
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def read_matrix(elem: Element) -> Mat:
    return FI.read_matrix(elem.find(t("matrix")))


def flash_decompose(m: Mat) -> tuple[float, float, float, float]:
    """(scale_x, scale_y, skew_x, skew_y) as Flash's Transform panel sees it."""
    a, b, c, d = m[:4]
    return math.hypot(a, b), math.hypot(c, d), math.atan2(-c, d), math.atan2(b, a)


def flash_compose(sx: float, sy: float, skx: float, sky: float, tx=0.0, ty=0.0) -> Mat:
    return (sx * math.cos(sky), sx * math.sin(sky), -sy * math.sin(skx), sy * math.cos(skx), tx, ty)


def _wrap(angle: float) -> float:
    return math.remainder(angle, math.tau)


# ── Color transforms ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ColorXf:
    """out = mult * in + off, per RGBA channel; offsets in 0..255 units."""
    mult: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    off: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    def then(self, outer: ColorXf) -> ColorXf:
        """Apply self first, then outer (outer = parent instance)."""
        return ColorXf(tuple(o * s for o, s in zip(outer.mult, self.mult)),
                       tuple(om * so + oo for om, so, oo in zip(outer.mult, self.off, outer.off)))

    @property
    def is_identity(self) -> bool:
        return self == COLOR_IDENTITY

    def lerp(self, other: ColorXf, k: float) -> ColorXf:
        return ColorXf(tuple(a + (b - a) * k for a, b in zip(self.mult, other.mult)),
                       tuple(a + (b - a) * k for a, b in zip(self.off, other.off)))


COLOR_IDENTITY = ColorXf()


def _hex_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def read_color(elem: Element) -> tuple[ColorXf, str | None]:
    """(transform, kind) where kind is alpha/brightness/tint/advanced/None."""
    c = elem.find(t("color"))
    c = c.find(t("Color")) if c is not None else None
    if c is None:
        return COLOR_IDENTITY, None
    g = lambda k, dflt: float(c.get(k, dflt))  # noqa: E731
    am, ao = g("alphaMultiplier", 1), g("alphaOffset", 0)
    if c.get("brightness") is not None:
        br = g("brightness", 0)
        m, o = (1 + br, 0.0) if br < 0 else (1 - br, 255 * br)
        return ColorXf((m, m, m, am), (o, o, o, ao)), "brightness"
    if c.get("tintMultiplier") is not None:
        tm = g("tintMultiplier", 0)
        r, gg, b = _hex_rgb(c.get("tintColor", "#000000"))
        return ColorXf((1 - tm, 1 - tm, 1 - tm, am), (r * tm, gg * tm, b * tm, ao)), "tint"
    xf = ColorXf((g("redMultiplier", 1), g("greenMultiplier", 1), g("blueMultiplier", 1), am),
                 (g("redOffset", 0), g("greenOffset", 0), g("blueOffset", 0), ao))
    rgb_touched = xf.mult[:3] != (1, 1, 1) or xf.off[:3] != (0, 0, 0)
    if xf.is_identity:
        return xf, None
    return xf, "advanced" if rgb_touched else "alpha"


# ── Timeline index ──────────────────────────────────────────────────────────

@dataclass
class Span:
    start: int
    duration: int
    frame: Element
    elements: list[Element]


@dataclass
class LayerIndex:
    i: int
    name: str
    type: str
    parent: int | None
    visible: bool
    spans: list[Span]
    starts: list[int] = field(default_factory=list)

    def span_at(self, frame: int) -> tuple[Span, Span | None] | None:
        k = bisect.bisect_right(self.starts, frame) - 1
        if k < 0:
            return None
        s = self.spans[k]
        if frame >= s.start + s.duration:
            return None
        return s, (self.spans[k + 1] if k + 1 < len(self.spans) else None)


@dataclass
class SymbolIndex:
    name: str
    layers: list[LayerIndex]
    frame_count: int
    masked: dict[int, list[int]]  # mask layer -> masked layers, top to bottom


def index_symbol(name: str, sym: Element) -> SymbolIndex:
    tl = sym.find(t("timeline"))
    dom_tl = tl.find(t("DOMTimeline")) if tl is not None else None
    layers_e = dom_tl.find(t("layers")) if dom_tl is not None else None
    layers = []
    for i, le in enumerate(list(layers_e) if layers_e is not None else []):
        spans = []
        frames_e = le.find(t("frames"))
        for fe in (list(frames_e) if frames_e is not None else []):
            els = fe.find(t("elements"))
            spans.append(Span(int(fe.get("index", 0)), int(fe.get("duration", 1)), fe,
                              list(els) if els is not None else []))
        spans.sort(key=lambda s: s.start)
        p = le.get("parentLayerIndex")
        layers.append(LayerIndex(i, le.get("name", ""), le.get("layerType", "normal"),
                                 int(p) if p is not None else None,
                                 le.get("visible", "true") != "false", spans,
                                 [s.start for s in spans]))
    masked: dict[int, list[int]] = {}
    for L in layers:
        if L.parent is not None and L.parent < len(layers) and layers[L.parent].type == "mask":
            masked.setdefault(L.parent, []).append(L.i)
    count = max((s.start + s.duration for L in layers for s in L.spans), default=1)
    return SymbolIndex(name, layers, max(count, 1), masked)


# ── Nodes ───────────────────────────────────────────────────────────────────

@dataclass(eq=False)
class MaskClip:
    nodes: list[Node]  # leaf shapes of the mask layer, in world space


@dataclass(eq=False)
class Node:
    kind: str                    # instance | shape | bitmap | text | other
    element: Element
    container: str               # symbol whose timeline holds this element
    layer: str
    parent: Node | None
    depth: int                   # nesting depth (main timeline children = 0)
    matrix: Mat                  # world matrix (for shapes: container space incl. groups)
    local: Mat                   # matrix relative to the container (after tweening)
    color: ColorXf               # composed world color transform
    masks: tuple[MaskClip, ...]  # outermost first
    in_group: bool = False       # shapes: FLA-RE's redundant-matrix rule
    symbol: str | None = None    # instances: library item name
    child_frame: int | None = None
    span_start: int = 0
    color_kind: str | None = None
    tween: str | None = None     # classic | shape | motion object | ...
    unsupported: tuple[str, ...] = ()


# ── Evaluation ──────────────────────────────────────────────────────────────

def resolve_child_frame(el: Element, offset: int, count: int) -> int:
    """Which frame of the child symbol shows, `offset` frames into the span."""
    first = int(el.get("firstFrame", 0))
    if el.get("symbolType") != "graphic":  # movie clip / button
        return offset % count
    loop = el.get("loop", "loop")
    last = el.get("lastFrame")
    last = min(int(last), count - 1) if last is not None else None
    if loop == "single frame":
        return min(first, count - 1)
    if loop == "play once":
        return min(first + offset, last if last is not None else count - 1)
    if loop == "play once reverse":
        return max(first - offset, last if last is not None else 0)
    if loop == "loop reverse":
        lo = last if last is not None else 0
        return first - offset % (first - lo + 1)
    if last is not None and last >= first:  # loop within [first, last]
        return first + offset % (last - first + 1)
    return (first + offset) % count


def ease(k: float, acceleration: float) -> float:
    """Flash classic-tween ease; acceleration in -100 (in) .. 100 (out)."""
    e = acceleration / 100
    return (1 + e) * k - e * k * k


def _transformation_point(el: Element) -> tuple[float, float]:
    tp = el.find(t("transformationPoint"))
    p = tp.find(t("Point")) if tp is not None else None
    return (float(p.get("x", 0)), float(p.get("y", 0))) if p is not None else (0.0, 0.0)


def tween_matrix(el0: Element, el1: Element, k: float, rotate: str = "auto", times: int = 0) -> Mat:
    m0, m1 = read_matrix(el0), read_matrix(el1)
    p0, p1 = _transformation_point(el0), _transformation_point(el1)
    w0, w1 = apply(m0, *p0), apply(m1, *p1)
    sx0, sy0, kx0, ky0 = flash_decompose(m0)
    sx1, sy1, kx1, ky1 = flash_decompose(m1)

    d_rot = _wrap(ky1 - ky0)
    if rotate == "clockwise":
        d_rot = (d_rot if d_rot > 0 else d_rot + math.tau) + math.tau * times
    elif rotate in ("counter-clockwise", "counterclockwise"):
        d_rot = (d_rot if d_rot < 0 else d_rot - math.tau) - math.tau * times
    d_skew = _wrap((kx1 - ky1) - (kx0 - ky0))

    m = flash_compose(sx0 + (sx1 - sx0) * k, sy0 + (sy1 - sy0) * k,
                      kx0 + (d_rot + d_skew) * k, ky0 + d_rot * k)
    px, py = p0[0] + (p1[0] - p0[0]) * k, p0[1] + (p1[1] - p0[1]) * k
    wx, wy = w0[0] + (w1[0] - w0[0]) * k, w0[1] + (w1[1] - w0[1]) * k
    lx, ly = apply(m, px, py)  # m has zero translation here
    return m[:4] + (wx - lx, wy - ly)


class Evaluator:
    def __init__(self, doc: Document, skip_layer=None):
        """skip_layer(container, layer_name) -> bool hides layers (e.g. camera guides)."""
        self.doc = doc
        self.skip_layer = skip_layer or (lambda container, name: False)
        self._index: dict[str, SymbolIndex] = {}

    def index(self, name: str) -> SymbolIndex | None:
        if name not in self._index:
            sym = self.doc.symbols.get(name)
            self._index[name] = index_symbol(name, sym) if sym is not None else None
        return self._index[name]

    def frame_count(self, name: str = MAIN) -> int:
        idx = self.index(name)
        return idx.frame_count if idx else 0

    def evaluate(self, frame: int, root: str = MAIN, world: Mat = IDENTITY) -> list[Node]:
        out: list[Node] = []
        self._walk(root, frame, world, COLOR_IDENTITY, (), None, 0, out, {root})
        return out

    # The walk appends to `out`; mask layers are walked into a separate list.
    def _walk(self, name, frame, world, color, masks, parent, depth, out, stack):
        idx = self.index(name)
        if idx is None:
            return
        consumed = {i for group in idx.masked.values() for i in group}
        for L in reversed(idx.layers):  # XFL lists layers top first
            if L.type in ("guide", "folder") or L.i in consumed:
                continue
            if self.skip_layer(name, L.name):
                continue
            if L.type == "mask":
                mask_nodes: list[Node] = []
                self._walk_layer(idx, L, frame, world, color, (), parent, depth, mask_nodes, stack)
                clip = MaskClip([n for n in mask_nodes if n.kind == "shape"])
                for mi in reversed(idx.masked.get(L.i, [])):
                    self._walk_layer(idx, idx.layers[mi], frame, world, color, masks + (clip,),
                                     parent, depth, out, stack)
            else:
                self._walk_layer(idx, L, frame, world, color, masks, parent, depth, out, stack)

    def _walk_layer(self, idx, L, frame, world, color, masks, parent, depth, out, stack):
        found = L.span_at(frame)
        if found is None:
            return
        span, nxt = found
        offset = frame - span.start
        tween = span.frame.get("tweenType")
        tween_pair = None
        if tween == "motion" and nxt is not None and len(span.elements) == 1 and len(nxt.elements) == 1:
            a, b = span.elements[0], nxt.elements[0]
            if a.tag == b.tag == TAG_INSTANCE and a.get("libraryItemName") == b.get("libraryItemName"):
                tween_pair = (a, b)

        for el in span.elements:
            self._element(idx.name, L.name, el, span, offset, tween, tween_pair,
                          world, color, masks, parent, depth, out, stack)

    def _element(self, container, layer, el, span, offset, tween, tween_pair,
                 world, color, masks, parent, depth, out, stack, group_mat=None):
        tag = el.tag
        common = dict(element=el, container=container, layer=layer, parent=parent,
                      depth=depth, masks=masks, span_start=span.start)

        if tag == TAG_SHAPE:
            in_group = group_mat is not None and read_matrix(el) == group_mat
            out.append(Node("shape", matrix=world, local=read_matrix(el), color=color,
                            in_group=in_group, **common))
        elif tag == TAG_GROUP:
            gm = read_matrix(el)
            members = el.find(t("members"))
            for child in (list(members) if members is not None else []):
                self._element(container, layer, child, span, offset, None, None,
                              mat_mul(world, gm), color, masks, parent, depth, out, stack, gm)
        elif tag == TAG_INSTANCE:
            self._instance(el, span, offset, tween, tween_pair, world, color,
                           common, out, stack)
        elif tag == TAG_BITMAP:
            local = read_matrix(el)
            out.append(Node("bitmap", matrix=mat_mul(world, local), local=local, color=color,
                            symbol=el.get("libraryItemName"), **common))
        else:
            kind = "text" if tag in TEXT_TAGS else "other"
            local = read_matrix(el)
            out.append(Node(kind, matrix=mat_mul(world, local), local=local, color=color, **common))

    def _instance(self, el, span, offset, tween, tween_pair, world, color, common, out, stack):
        name = el.get("libraryItemName")
        local = read_matrix(el)
        own_color, color_kind = read_color(el)
        unsupported = []
        node_tween = None

        if tween_pair is not None and tween_pair[0] is el:
            fe = span.frame
            k = ease(offset / span.duration, float(fe.get("acceleration", 0)))
            if fe.get("hasCustomEase") == "true" or fe.find(t("tweens")) is not None:
                unsupported.append("custom ease")
            local = tween_matrix(el, tween_pair[1], k, fe.get("motionTweenRotate", "auto"),
                                 int(fe.get("motionTweenRotateTimes", 0)))
            end_color, end_kind = read_color(tween_pair[1])
            own_color = own_color.lerp(end_color, k)
            color_kind = color_kind or end_kind
            node_tween = "classic"
        elif tween:
            node_tween = tween
            if tween != "motion":
                unsupported.append(f"{tween} tween")

        if el.find(t("filters")) is not None:
            unsupported.append("filters")
        if el.get("blendMode") not in (None, "normal"):
            unsupported.append(f"blend {el.get('blendMode')}")
        if el.get("cacheAsBitmap") == "true":
            unsupported.append("cacheAsBitmap")
        if any(el.get(a) for a in ("rotationX", "rotationY", "z")) or el.find(t("matrix3D")) is not None:
            unsupported.append("3D")

        idx = self.index(name)
        count = idx.frame_count if idx else 1
        child_frame = resolve_child_frame(el, offset, count)
        node_world = mat_mul(world, local)
        node_color = own_color.then(color)
        node = Node("instance", matrix=node_world, local=local, color=node_color, symbol=name,
                    child_frame=child_frame, color_kind=color_kind, tween=node_tween,
                    unsupported=tuple(unsupported), **common)
        out.append(node)
        if idx is None or name in stack:
            return
        self._walk(name, child_frame, node_world, node_color, common["masks"], node,
                   common["depth"] + 1, out, stack | {name})
