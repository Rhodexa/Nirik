# Nirik symbol format, version 2 (proposal)

Status: **draft for review**, 2026-11-09. Nothing here is implemented yet.
Version 1 is what `character.json` holds today; section 9 maps old to new.

## 1. The line this format draws

A **converter** writes a symbol folder; **Nirik** reads it. Nirik knows
nothing about where a symbol came from: a Flash show file, a sprite sheet,
a Krita document or a hand-written file all look the same to it.

So everything Nirik needs is written here explicitly. Nirik never infers
meaning from names, layer conventions or "most common" values. When a
converter can't provide something (Spike's rig has no far-limb color), it
leaves the field out and Nirik offers the feature without it.

Nirik writes only inside the folder's `.nirik/` directory (its caches). A
converter writes everything else and may regenerate it at any time.

## 2. Vocabulary

| Term | Meaning | Flash equivalent | In code today |
|---|---|---|---|
| **Symbol** | A thing that contains things: it has layers and poses. Symbols nest: Twilight contains Head, Head could contain Eye. | a symbol | rig / character |
| **Symbol folder** | One folder on disk holding a root symbol, every symbol nested in it, and their drawings. What "Load Symbol" loads. | the character in a stock file | library |
| **Layer** | A place inside a symbol that shows one thing at a time: a drawing, another symbol, or (for a mask layer) a clipping shape. | a layer | slot / part |
| **Drawing** | One picture a layer can show. | a frame of a part symbol | drawing |
| **Pose** | One stored arrangement of a symbol: for each layer, what it shows and where. | a frame of the symbol | construction |
| **Placement** | Where a pose puts a layer's content: a 2D matrix and a color tint. | an instance's matrix and color transform | socket |
| **Part** | An animator-facing group of layers selected together ("Eye 1" = iris, pupil, highlights). | (none) | Parts button |

Proposed rename in the panel: the draw-order arrows become **Stack**
(Forward, Back, To Front, To Back), since **Layer** now means the place
itself.

## 3. Folder layout

```
twilight/
  symbol.json            the description (this document)
  drawings/<id>.png      raster drawings
  drawings/<id>.svg      vector drawings (reserved, section 7)
  .nirik/                Nirik's own files; never written by converters
    palettes/<layer>/    texture tiles and palette.json
  .converter/            converter's own files; never read by Nirik
    ids.json             keeps drawing IDs stable across re-imports
```

Changes from today: `character.json` → `symbol.json`; `.udim/` →
`.nirik/palettes/`; `ids.json` moves under `.converter/` because only the
converter uses it.

## 4. Space, units and color

- **Units.** Drawings and placements use *symbol units*: 2D, x to the right,
  **y downward**, origin at the symbol's pivot. `pixels_per_unit` says how
  many raster pixels one unit spans. `units_per_meter` says how big the
  symbol is in a scene (today Nirik hard-codes 300).
- **Matrices** are `[a, b, c, d, tx, ty]`: a point (x, y) maps to
  (a·x + c·y + tx, b·x + d·y + ty). They can rotate, scale, mirror and skew.
- **Canvas.** Every layer has one canvas `[x0, y0, x1, y1]` in its own units:
  the union of everything it can show. All its drawings are rendered onto
  that same canvas, so swapping drawings never moves the artwork.
- **Color** placements are `[r, g, b, a, R, G, B, A]`: multiply each channel
  by the first four, then add the last four (0–255 scale), applied in sRGB.
  Missing means unchanged.

These conventions happen to match Flash's; they are this format's own.

## 5. symbol.json

```jsonc
{
  "format": "nirik.symbol",
  "version": 2,
  "label": "Princess Twilight Sparkle",
  "root": "Character",                 // id of the outermost symbol
  "pixels_per_unit": 4.0,
  "units_per_meter": 300,

  "symbols": {
    "Character": {
      "label": "Twilight",
      "layers": [ /* back to front, see below */ ],
      "poses": [ /* see below */ ],
      "cycle": null                     // or { "poses": [0, 23], "speed": -4.86 }
    },
    "Head": { "label": "Head", "layers": [], "poses": [] }
  },

  "drawings": {
    "1347": {
      "layer": "Head.MOUTH",
      "label": "Mouth 3/4",
      "set": "mouth-3q",               // drawings browsed together
      "tags": ["happy", "a,e,i"],
      "file": "drawings/1347.png"
    }
  },

  "parts": [                           // animator-facing groups, in panel order
    { "label": "Mouth", "layers": ["Head.MOUTH"] },
    { "label": "Eye 1", "layers": ["Head.IRIS", "Head.PUPIL", "Head.HIGHLIGHTS"] }
  ],

  "far_color": [1, 1, 1, 1, -16, -21, -16, 0],   // optional

  // Reserved for version 2.x, written as soon as converters can provide them:
  "loops": [],                         // section 6
  "attachments": [],                   // section 6
  "carries": []                        // section 6
}
```

### Layers

```jsonc
{
  "id": "Head.MOUTH",        // stable: becomes a bone name in saved scenes
  "label": "Mouth",
  "kind": "drawing",         // drawing | symbol | mask
  "canvas": [-48.5, -60.0, 40.25, 32.0],
  "masked_by": null,         // id of a mask layer in the same symbol
  "symbol": null             // for kind "symbol": the nested symbol's id
}
```

### Poses

```jsonc
{
  "label": "Rotation 3",
  "tags": ["3/4", "talk"],
  "layers": {
    "Head.MOUTH": { "drawing": 1347, "matrix": [1, 0, 0, 1, 12.5, 40.0] },
    "Character.HEAD": { "pose": 4, "matrix": [0.98, 0.1, -0.1, 0.98, 0, -120],
                        "color": [1, 1, 1, 1, -16, -21, -16, 0] }
  }
}
```

A layer missing from a pose shows nothing in it.

## 6. Reserved: living symbols

Planned for the next step (journal: "Poses are cages"). The fields are
named now so converters can start writing them.

- **`loops`**: a layer that plays drawings by itself, e.g. the horn magic:
  `{ "layer": "Head.MAGIC", "drawings": [3001, 3002, ...], "mode": "loop" }`.
  Mode is `loop`, `once` or `pingpong`.
- **`attachments`**: a layer that follows another one's placement, e.g. the
  aura on the horn tip: `{ "layer": "Head.MAGIC", "follows": "Head.HORN",
  "offset": [1, 0, 0, 1, 0, -30] }`.
- **`carries`**: which layer moves with which, for posing: `{ "layer":
  "Character.TORSO", "carries": ["Character.LEG_FRONT", ...] }`.
- **Opacity** needs no format field: it's a keyable value in Nirik.

## 7. Reserved: vector drawings

A drawing may have `"file": "drawings/<id>.svg"` instead of a PNG (filled
paths only, already placed on the layer's canvas). Nirik decides how to
display it (raster from it, or Grease Pencil). Not supported yet.

## 8. Rules

- **IDs are stable.** Layer ids become bone names in saved scenes; drawing
  ids are keyed values. A converter must keep both across re-imports.
- **Drawing 0** means "nothing".
- **An empty mask masks nothing**: a mask layer showing nothing in a pose
  leaves the layers under it fully visible.
- **Order** is the order of `layers`, back to front, within each symbol; a
  nested symbol is drawn at its layer's place.

## 9. From version 1

| Version 1 (`character.json`) | Version 2 (`symbol.json`) |
|---|---|
| `rigs` | `symbols` |
| `slots` | `layers` (+ `label`, `kind`) |
| `constructions` | `poses` (`labels` → `label` + `tags`) |
| slot `rig` (child) | layer `kind: "symbol"`, `symbol` |
| slot `mask: true` | layer `kind: "mask"` |
| `ppu` | `pixels_per_unit` |
| drawing `symbol` (Flash symbol name) | drawing `set` (any grouping) + `label` |
| *(inferred from layer names)* | `parts` |
| *(inferred: most common darkening)* | `far_color` |
| `cycle.frames` | `cycle.poses` (first, last) |

Layer and drawing ids keep their current values, so saved scenes keep
working. Nirik reads version 1 during the transition.

## 10. Open questions

1. **Folder name in the UI:** "Load Symbol" for the whole folder, or keep
   "puppet" for the folder only ("Load Puppet") and "symbol" for everything
   inside?
2. **Stack** for the draw-order arrows: does that name read right to you?
3. **Parts:** should converters always write `parts`, or should Nirik also
   let you define your own groups in a scene (e.g. "Spike's whole arm")?
4. **Sets vs tags:** a drawing has one `set` (what the browser groups by) and
   free `tags` (phonemes, expressions). Enough, or do you want several
   groupings?
5. **Scale:** `units_per_meter` per folder. Should Nirik let you override it
   per scene (a giant Spike)?
