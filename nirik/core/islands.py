"""Find separate pieces of art in an image (sprite sheets): pure numpy."""

from __future__ import annotations

import numpy as np

Box = tuple[int, int, int, int]  # x0, y0, x1, y1 (exclusive), image rows top-down


def islands(alpha: np.ndarray, threshold: float = 0.5, min_area: int = 64, step: int = 4) -> list[Box]:
    """Bounding boxes of connected opaque regions, sorted in reading order.

    Works on a downsampled mask (every `step` pixels) so large sheets stay
    fast in pure Python; boxes are scaled back to full resolution.
    """
    mask = alpha[::step, ::step] > threshold
    h, w = mask.shape
    label = np.zeros((h, w), dtype=np.int32)
    boxes: list[Box] = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if label[y0, x0]:
            continue
        n = len(boxes) + 1
        stack = [(y0, x0)]
        label[y0, x0] = n
        xs, ys, area = [x0, x0], [y0, y0], 0
        while stack:
            y, x = stack.pop()
            area += 1
            xs[0], xs[1] = min(xs[0], x), max(xs[1], x)
            ys[0], ys[1] = min(ys[0], y), max(ys[1], y)
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not label[ny, nx]:
                    label[ny, nx] = n
                    stack.append((ny, nx))
        # One sample step of slack each side: sampling can miss up to step-1 pixels.
        full_h, full_w = alpha.shape
        boxes.append(grow((xs[0] * step, ys[0] * step, (xs[1] + 1) * step, (ys[1] + 1) * step),
                          step if step > 1 else 0, full_w, full_h)
                     if area * step * step >= min_area else None)
    found = [tuple(int(v) for v in b) for b in boxes if b]
    # Reading order: rows (by vertical center, tolerant to ragged rows), then left to right.
    rows: list[list[Box]] = []
    for b in sorted(found, key=lambda b: (b[1] + b[3]) / 2):
        if rows and (b[1] + b[3]) / 2 < max(r[3] for r in rows[-1]):
            rows[-1].append(b)
        else:
            rows.append([b])
    return [b for row in rows for b in sorted(row, key=lambda b: b[0])]


def grow(box: Box, margin: int, w: int, h: int) -> Box:
    x0, y0, x1, y1 = box
    return max(0, x0 - margin), max(0, y0 - margin), min(w, x1 + margin), min(h, y1 + margin)
