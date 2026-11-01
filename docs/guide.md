# Animating with Nirik (current prototype)

## Open a character

```
make demo                          # Twilight
make demo CHAR=library/rarity      # Rarity
```

Blender opens with the character in a front view and the **Nirik** tab in the
sidebar (press `N` if it's hidden). In any other file: *Nirik tab → Load
Character* and pick a folder under `library/`.

## The Nirik tab

**Parts.** Click a button to select that part's control and enter Pose mode:
Body (everything), Head, Mouth, Brow, Blink, Eye. *Eye* selects iris, pupil
and highlights together, so the look moves as one; the eye shape clips them.

**Character / Head ◀ ▶.** Step through the stock constructions: the body's
turnarounds and poses, and the head's angles, tilts and expressions. Each body
pose comes with the head pose the stock rig pairs with it; step the head
afterwards to change it on its own.

**Selected part.** Shows the current drawing, its tags (on mouths:
expression and phoneme, e.g. `happy · a,e,i`) and swap arrows.

## Selecting by clicking

In Pose mode, click the artwork with your select button (left or right,
whatever your Blender uses):

| Click | Selects |
|---|---|
| Click | the part you mean: a face feature (Mouth, Eye, Brow, Blink), else the Head, else the Body |
| Double-click | the exact piece under the cursor (an ear, the tail, a wing) |
| `Alt` + click | cycles through every piece stacked under the cursor |
| `Shift` + click | adds to the selection |

Clicks are tested against the drawing itself: transparent areas, and parts
hidden by a mask (an iris under the eyelid), pass through to whatever is
behind, or to Blender's normal selection.

## Posing

With a part selected, use Blender as usual: `G` move, `R` rotate, `S` scale.
Children follow their parent (the head carries eyes, mouth, mane). `Alt+G`,
`Alt+R`, `Alt+S` reset.

## Swapping drawings

| Input | Swaps through |
|---|---|
| `Alt + Wheel` | the current set (e.g. the 3/4 mouth chart) |
| `Ctrl + Alt + Wheel` | everything the part can show (other angles too) |

## Animating

1. Turn on **auto-key** (record button in the Timeline).
2. Go to a frame, then pose, swap drawings or change constructions.
   Everything you change is keyed on that frame.
3. Drawing swaps and constructions **hold** until the next key, like an
   exposure sheet. Your own moves and rotations interpolate smoothly; to pose
   on twos, select keys in the Graph Editor and set *Key → Interpolation Mode
   → Constant*.
4. `Space` plays.

### Finding your keys

- The **Character**, **Head** and **Drawing** fields in the Nirik tab are the
  real keyed values: yellow on a key, green between keys, like any Blender
  property.
- **Prev Key / Next Key** (or `Up` / `Down` arrow) jump between keys of the
  selected part. Constructions are keyed on **Body** (whole character) and
  **Head**; drawing swaps on the part itself (Mouth, Blink, ...).
- In the **Dope Sheet**, select a part to see its keys. Move or delete
  construction and drawing keys there like any others; the hidden parts of
  the rig follow automatically a moment later.

Typical order: block poses with constructions (body, head angle), set
expressions with Mouth/Brow/Blink swaps, then refine with transforms.

## Rendering

The character is a flat drawing with its layers kept in order from any camera
angle; past roughly 30 degrees off-axis she visibly reads as a cut-out, which
is where a different construction (head angle, turnaround pose) belongs.

Add a camera in front of the character (front view, `Ctrl+Alt+Numpad 0` to
align), then `F12`. Characters are unlit drawings; set *Color Management →
View Transform* to *Standard* to see the model colors exactly.

## Not there yet

- A thumbnail browser for drawings (stepping only, for now).
- Per-part "animate on twos" settings, lip sync, the X-sheet overlay.
- Custom replacement drawings (Rarity's captain shirt).
