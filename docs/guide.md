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
3. Drawing swaps and constructions are **held** until the next key, like an
   exposure sheet. Moves and rotations interpolate smoothly by default; to
   pose on twos, select keys in the Graph Editor and set *Key → Interpolation
   Mode → Constant*.
4. `Space` plays.

Typical order: block poses with constructions (body, head angle), set
expressions with Mouth/Brow/Blink swaps, then refine with transforms.

## Rendering

Add a camera in front of the character (front view, `Ctrl+Alt+Numpad 0` to
align), then `F12`. Characters are unlit drawings; set *Color Management →
View Transform* to *Standard* to see the model colors exactly.

## Not there yet

- Clicking the artwork to select a part (use the Parts buttons).
- A thumbnail browser for drawings (stepping only, for now).
- Per-part "animate on twos" settings, lip sync, the X-sheet overlay.
- Custom replacement drawings (Rarity's captain shirt).
