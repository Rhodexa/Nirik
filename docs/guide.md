# Animating with Nirik (current prototype)

## Open a character

```
make demo                          # Twilight
make demo CHAR=library/rarity      # Rarity
```

Blender opens with the character in a front view and the **Nirik** tab in the
sidebar (press `N` if it's hidden). In any other file: *Nirik tab → Load
Symbol* and pick a folder under `library/`, or use *File → Append* on the
`.blend` inside that folder (open it, then `Collection → nirik:<name>`).

## The Nirik tab

**Groups.** Click a button to select that part's control and enter Pose mode:
Body (everything), Head, Mouth, Brow, Blink, Eye. *Eye* selects iris, pupil
and highlights together, so the look moves as one; the eye shape clips them.

**Character Pose / Head Pose ◀ ▶.** Step through the stock poses: the body's
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
| `Shift` + double-click | adds the exact piece (e.g. upper arm + lower arm + hand) |

Shift+click on the Parts and More Layers buttons adds to the selection too.

Clicks are tested against the drawing itself: transparent areas, and parts
hidden by a mask (an iris under the eyelid), pass through to whatever is
behind, or to Blender's normal selection.

## Overlay

With a part selected, the viewport shows a box around the artwork it moves
(Head: the whole head), a cross at its pivot, and its name. Toggle it with
the armature button in the viewport header; Blender's own *Overlays* switch
hides it too.

## Layers and sides

In the Nirik tab, for the selected part (and everything it carries):

- **Stack** arrows: back one / forward one visible part, all the way to the
  back / front, or reset to the stock order. Keyed with auto-key, so a leg
  can cross in front of the body for a few frames.
- **Depth** arrows: push parts away from the camera (1 cm per click) or pull
  them forward. Stack orders parts *within* a character; Depth decides
  overlap *between* characters and scene objects. Spike riding Twilight:
  place Spike slightly in front of her, then push his far wing and far
  limbs back so they tuck behind her body.
- **Auto / Near / Far**: *Auto* uses the stock pose's shading; *Far* applies
  the character's far-limb darkening (learned from her stock poses); *Near*
  removes it. Use *Far* when you move a limb behind the body.

## Layers list and hiding

*Nirik tab → Layers* lists the parts showing a drawing, front first, in their
current order (Forward/Back moves rows). Click a row to select the part; the
eye hides it **in the viewport only**, so renders never lose it. Hidden parts
can't be clicked, which is the point: hide the blink, pose the eye under it,
show it again. *Hide Selected* (also the eye button next to Auto/Near/Far)
and *Show All* work on whole selections.

## Posing

With a part selected, use Blender as usual: `G` move, `R` rotate, `S` scale.
Children follow their parent (the head carries eyes, mouth, mane). `Alt+G`,
`Alt+R`, `Alt+S` reset.

## Swapping drawings

| Input | Swaps through |
|---|---|
| `Alt + Wheel` | the current set (e.g. the 3/4 mouth chart) |
| `Ctrl + Alt + Wheel` | everything the part can show (other angles too) |

## Swapping symbols

Any layer can show another symbol from some frame on: Rarity's head on
Twilight, the standing head on a walk, a whole character where a tail was.
Click the layer (for a head, the head), go to the frame, press
`Shift+Alt+D` (or **Swap** in the Nirik tab) and pick from the list: every
symbol of every library next to this one, plus what the layer showed
before. With auto-key on, the swap is keyed and earlier frames keep what
they showed. Pick the layer's own content (first in the list) to swap back.

The swapped-in symbol is its own armature hanging from the layer, in Pose
mode together with the one it's on: click it to pose it, step its poses,
swap its drawings. It moves with the layer, and nothing keyed before
changes. The Nirik tab says what a layer shows (*Shows:*).

Not yet: Stack, Depth and Side on the layer don't reach the swapped-in
symbol, the layer's mask doesn't apply to it, and removing a swap means
deleting its armature with its cards. Riggers sometimes keep part of a head
on the body (Twilight's ear): those parts stay.

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

## Props

*Nirik tab → Import Image*: pick an image and its height. A sprite sheet
(separate pieces of art on one transparent image) becomes one prop whose
drawings are the pieces, in reading order, centered on one canvas: swap them
with the browser or Alt+Wheel like any part (Parts → **Art**). Single
pictures pivot at the bottom (they stand on the ground), sheets at the center.
The library is written to `library/<name>` next to the saved .blend.

**Face Camera** (next to the character's name) keeps any character or prop
turned toward the scene camera, upright. It's a Locked Track constraint on
the armature: key its *Influence* to 0 to let it turn away, e.g. to reveal
it's paper-thin.

## Walk cycles

Walks are their own libraries (`library/twilight_walk_side`,
`library/spike_walk_side`): the show's cycle rigs, where every body part loops
in place and the head is the regular head rig. Load one, then *Add Cycle* in
the Nirik tab: pick the frame range and it keys the loop on every frame and
slides Body at the walk's speed, measured from the cycle so the feet stay
planted (*Speed %* corrects any sliding). The head isn't touched: swap
mouths, blink and turn it on top as usual. Both side walks face left.

To walk with the full standing head (all its mouths, brows and poses):
click the walk's head, *Swap* → *twilight › Head*, then step the swapped-in
head to a profile pose (pose 10 for Twilight; the side walks face left).

Import another walk from a scene file:

```
.venv/bin/python -m devtools.flash.import_character SCENE.fla \
    --root "~RY_Pwalk_Character_side_WALK" --name rarity_walk_side --frames 0-23 --jobs 2 \
    --out library/rarity_walk_side
```

## Rendering

The character is a flat drawing with its layers kept in order from any camera
angle; past roughly 30 degrees off-axis she visibly reads as a cut-out, which
is where a different construction (head angle, turnaround pose) belongs.

Add a camera in front of the character (front view, `Ctrl+Alt+Numpad 0` to
align), then `F12`. Characters are unlit drawings; set *Color Management →
View Transform* to *Standard* to see the model colors exactly.

## Not there yet

- A thumbnail browser for drawings and poses, and pictures in the Swap list.
- Per-part "animate on twos" settings, lip sync, the X-sheet overlay.
- Custom replacement drawings (Rarity's captain shirt).
