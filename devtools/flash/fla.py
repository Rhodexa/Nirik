"""FLA-RE shim: locate FLA-RE and load an XFL document.

FLA-RE is found at $FLARE_DIR, defaulting to ../FLA-RE next to this repo.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element

ROOT = Path(__file__).resolve().parents[2]
FLARE_DIR = Path(os.environ.get("FLARE_DIR", ROOT.parent / "FLA-RE"))

if str(FLARE_DIR) not in sys.path:
    sys.path.insert(0, str(FLARE_DIR))

import fla_inspect as FI  # noqa: E402  (FLA-RE)

t = FI.t
MAIN = "__main__"  # symbol key for the document's main timeline


@dataclass
class Document:
    path: Path
    symbols: dict[str, Element]  # library name -> DOMSymbolItem; MAIN -> main timeline holder
    width: int
    height: int
    fps: float


def load(path: str | Path) -> Document:
    path = Path(path)
    z = FI.open_fla(path)
    dom = FI.parse_dom(z)
    symbols = FI.get_symbols(z)
    # The main timeline sits at DOMDocument/timelines/DOMTimeline; wrap it so
    # it can be indexed like a symbol (DOMSymbolItem/timeline/DOMTimeline).
    main = Element(t("DOMSymbolItem"), name=MAIN)
    holder = Element(t("timeline"))
    holder.append(dom.find(t("timelines")).find(t("DOMTimeline")))
    main.append(holder)
    symbols[MAIN] = main
    return Document(
        path=path,
        symbols=symbols,
        width=int(float(dom.get("width", 550))),
        height=int(float(dom.get("height", 400))),
        fps=float(dom.get("frameRate", 24)),
    )
