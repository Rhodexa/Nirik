# Nirik library format, version 2

Status: **implemented** (2026-11-09) except the reserved parts (sections 7
and 8) and symbol layers holding more than one symbol (Nirik uses the
first). Version 1 (`character.json`) is still read, without groups or
display labels; `python -m devtools.library_v2 <folder>` upgrades it.

## 1. The line this format draws

A **converter** writes a library; **Nirik** reads it. Nirik knows nothing
about where a library came from: a Flash show file, a sprite sheet, a Krita
document or a hand-written file all look the same to it.

So everything Nirik needs is written here explicitly. Nirik never infers
meaning from names, layer conventions or "most common" values. When a
converter can't provide something (Spike's rig has no far-limb color), it
leaves the field out and Nirik offers the feature without it.

Nirik writes only inside the library's `.nirik/` directory (its caches). A
converter writes everything else and may regenerate it at any time.

## 2. Vocabulary

| Term | Meaning | Flash equivalent | In code today |
|---|---|---|---|
| **Library** | A folder holding symbols and their drawings. Twilight's library holds Twilight, her Head, and every drawing they use. | the document's library | library |
| **Symbol** | A thing that contains things: a stack of layers, plus poses. Symbols nest: Twilight contains Head. | a symbol | rig / character |
| **Layer** | A place inside a symbol that shows one thing at a time: a drawing, another symbol, or (a mask layer) a clipping shape. The order of layers is the symbol's *default* draw order. | a layer | slot / part |
| **Drawing** | One picture a layer can show. | a frame of a part symbol | drawing |
| **Pose** | One stored arrangement of a symbol: for each layer, what it shows and where. | a frame of the symbol | construction |
| **Placement** | Where a pose puts a layer's content: a 2D matrix and a color tint. | an instance's matrix and color transform | socket |
| **Instance** | A symbol placed in a Blender scene: what "Load Symbol" creates. Several instances of one symbol can coexist. | an instance on the stage | armature + cards |
| **Group** | Layers selected together that aren't one node of the tree, e.g. "Eye 1" = iris, pupil and highlights, which are siblings inside Head. Written by converters or made by you. | (none) | "Parts" buttons |
| **Stack** | The draw-order control: moves a layer forward or back in its symbol's stack, over time. | (layer order, fixed) | "Layer" arrows |

The word "part" is retired: it meant a layer in the code and a group in the
panel.

## 3. Folder layout

```
twilight/
  twilight.blend         the assembled symbol: File > Append from here
  library.json           the description (this document)
  drawings/<id>.png      raster drawings
  drawings/<id>.svg      vector drawings (reserved, section 8)
  .nirik/                Nirik's own files; never written by converters
    palettes/<layer>/    texture tiles and palette.json
  .converter/            converter's own files; never read by Nirik
    ids.json             keeps drawing IDs stable across re-imports
```

`<name>.blend` holds one collection, `nirik:<name>`, with everything the
symbol needs. Nirik writes it the first time the library is loaded and
rebuilds it when `library.json` is newer. **Load Symbol** appends from it;
plain File > Append works too, and Nirik adopts the appended copy.

**Collections are packaging, not structure.** A collection is a fixed box:
the instance's armature, cards and helpers, which never change from frame
to frame. The frame-by-frame tree lives in the poses, which decide what in
the box shows, where and with which drawing. A symbol that looks entirely
different on two frames has both arrangements in its box.

Changes from today: `character.json` → `library.json`; `.udim/` →
`.nirik/palettes/`; `ids.json` moves under `.converter/`.

## 4. Canvas: the peg bar

Animators draw on paper punched for a **peg bar**, so every sheet sits in
exactly the same place. A layer's **canvas** is its sheet: one fixed
rectangle that every drawing of that layer is painted into, at the same
position. Flipping from one mouth to another never shifts anything, because
all mouths are on identically pegged sheets.

In numbers, the canvas is `[x0, y0, x1, y1]` in the layer's own units,
chosen as the union of everything the layer can show (the smallest sheet
that fits every mouth). In Blender, the canvas is the card: one fixed
rectangle per layer whose texture changes.

## 5. Space, units and color

- **Units.** Drawings and placements use *symbol units*: 2D, x to the right,
  **y downward**, origin at the symbol's pivot. `pixels_per_unit` says how
  many raster pixels one unit spans. `units_per_meter` is the symbol's
  default size in a scene (today Nirik hard-codes 300); scaling an instance
  overrides it.
- **Matrices** are `[a, b, c, d, tx, ty]`: a point (x, y) maps to
  (a·x + c·y + tx, b·x + d·y + ty). They can rotate, scale, mirror and skew.
- **Color** placements are `[r, g, b, a, R, G, B, A]`: multiply each channel
  by the first four, then add the last four (0–255 scale), applied in sRGB.
  Missing means unchanged.

These conventions happen to match Flash's; they are this format's own.

## 6. library.json

```jsonc
{
  "format": "nirik.library",
  "version": 2,
  "label": "Princess Twilight Sparkle",
  "root": "Character",                 // the symbol "Load Symbol" places by default
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
      "tags": ["chart:mouth-3q", "expression:happy", "phoneme:a,e,i"],
      "file": "drawings/1347.png"
    }
  },

  "groups": [                          // in panel order
    { "label": "Eye 1", "layers": ["Head.IRIS", "Head.PUPIL", "Head.HIGHLIGHTS"] }
  ],

  "far_color": [1, 1, 1, 1, -16, -21, -16, 0],   // optional

  // Reserved for version 2.x (section 7):
  "loops": [], "attachments": [], "carries": []
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
  "symbols": []              // kind "symbol": the symbols this layer can hold,
                             // e.g. ["Head"] or ["StandBody", "WalkBody"]; each
                             // pose says which one shows (and in which pose)
}
```

### Poses

```jsonc
{
  "label": "Rotation 3",
  "tags": ["view:3/4"],
  "frames": [102, 103],      // optional: the source frames this pose came from
  "layers": {
    "Head.MOUTH": { "drawing": 1347, "matrix": [1, 0, 0, 1, 12.5, 40.0] },
    "Character.HEAD": { "symbol": "Head", "pose": 4,
                        "matrix": [0.98, 0.1, -0.1, 0.98, 0, -120],
                        "color": [1, 1, 1, 1, -16, -21, -16, 0] }
  }
}
```

A layer missing from a pose shows nothing there, by default (section 7
lets the animator switch it on anyway).

### Tags

Tags are `key:value` text. Nirik gives meaning to a few keys and keeps the
rest for search:

- `chart`: drawings browsed together (the browser's "same chart"); replaces
  today's "same set".
- `phoneme`: mouth shapes for lip sync.
- `expression`, `view`: free, shown in the browser.

### Navigating: the tree, with groups beside it

The intended UI shows the **tree of the current pose**: the symbol, its
layers, what each shows, and nested symbols below them; selecting a node
selects its control. Groups appear next to the tree for selections the tree
can't express as one node. Converters may write groups; animators can add
their own in a scene.

## 7. Reserved: living symbols

Planned for the next step (journal: "Poses are cages"). The fields are
named now so converters can start writing them.

- **Poses as defaults**: in Nirik, any layer can be switched on in any pose
  with a drawing and a placement of the animator's choosing. No format field.
- **`loops`**: a layer that plays drawings by itself, e.g. the horn magic:
  `{ "layer": "Head.MAGIC", "drawings": [3001, 3002, ...], "mode": "loop" }`.
  Mode is `loop`, `once` or `pingpong`.
- **`attachments`**: a layer that follows another one's placement, e.g. the
  aura on the horn: `{ "layer": "Head.MAGIC", "follows": "Head.HORN",
  "offset": [1, 0, 0, 1, 0, -30] }`.
- **`carries`**: which layer moves with which, for posing: `{ "layer":
  "Character.TORSO", "carries": ["Character.LEG_FRONT", ...] }`.
- **Opacity** needs no format field: it's a keyable value in Nirik.

## 8. Reserved: vector drawings

A drawing may have `"file": "drawings/<id>.svg"` instead of a PNG (filled
paths only, already on the layer's canvas). Nirik decides how to display it
(raster from it, or Grease Pencil). Not supported yet. For the show's files
this gains sharpness and size, not constant line widths: their outlines
are filled shapes.

## 9. Composition: in the scene, not between libraries

Decided 2026-11-09. Libraries never reference each other: a library that
depends on another folder breaks when either moves.

- **Composing** happens in the Blender scene: Spike on Twilight is one
  instance attached to another's layer. No format change.
- **Saving a composition, a scene as a symbol, reusing a performance** use
  Blender's own tools on collections and actions, revisited when needed.
- **A layer switching between whole symbols** (standing body / walk body)
  is in the format: a symbol layer lists every symbol it can hold
  (section 6) and each pose says which one shows. That covers what "two
  frames with entirely different rigs" needs within one library.

## 10. Rules

- **IDs are stable.** Layer ids become bone names in saved scenes; drawing
  ids are keyed values. A converter must keep both across re-imports.
- **Drawing 0** means "nothing".
- **An empty mask masks nothing**: a mask layer showing nothing in a pose
  leaves the layers under it fully visible.
- **Order**: `layers` lists each symbol's stack back to front; a nested
  symbol is drawn at its layer's place. This is a default: Stack changes it
  over time in Nirik.

## 11. From version 1

| Version 1 (`character.json`) | Version 2 (`library.json`) |
|---|---|
| `rigs` | `symbols` |
| `slots` | `layers` (+ `label`, `kind`) |
| `constructions` | `poses` (`labels` → `label` + `tags`) |
| slot `rig` (child) | layer `kind: "symbol"`, `symbol` |
| slot `mask: true` | layer `kind: "mask"` |
| `ppu` | `pixels_per_unit` |
| drawing `symbol` (Flash symbol name) | `label` + tag `chart:…` |
| *(inferred from layer names)* | `groups` |
| *(inferred: most common darkening)* | `far_color` |
| `cycle.frames` | `cycle.poses` (first, last) |

Layer and drawing ids keep their current values, so saved scenes keep
working. Nirik reads version 1 during the transition.

## 12. Decided in review (2026-11-09)

- **Library** for the folder; **Load Symbol** places an instance of a
  library's symbol (its root by default).
- **Layer** for the places inside a symbol; **Stack** for draw-order moves.
- **Group** instead of "part"; converters may write groups, animators may
  add their own.
- **Tags** as `key:value`, replacing the separate "set".
- Scale is overridable per instance.
- The library folder holds `<name>.blend`, appended into scenes;
  collections are packaging, poses are structure.
- No references between libraries; composition happens in scenes.
- A symbol layer can hold one of several symbols.

## 13. Open questions

1. **Tree view**: show only what the current pose uses, plus the empty
   layers dimmed so pieces like the aura stay findable? And a pose browser
   to bring a layer's content from another pose into the current one.
2. **Groups made in a scene**: saved with the symbol by default, with a
   "this file only" toggle (like Scratch's variables for one sprite or the
   whole project)?
