# Flash converter journal

Issues and ideas for the dev-only Flash converter (`devtools/flash/`): the
tooling that turns show files into puppets. Nirik's own issues live in
`docs/friction.md`; when an item has a half on each side, each journal gets
its half. Newest first; `(date)` marks when an item came up.

## Open

### Make Nirik Flash-free
Write into each puppet what Nirik currently infers from show conventions,
so Nirik can stop guessing (2026-11-06):
- `parts`: the animator-facing groups (Mouth, Brow, Blink, Eye 1 = iris +
  pupil + highlights under one mask). Today Nirik reads layer names.
- `label` per part and drawing: today Nirik strips rig codes (`PTS_`).
- `set` per drawing: today "Same Set" means "same Flash symbol".
- `far_color`: today Nirik picks the most common darkening tint. Spike's
  rig has none; leave it out there.
- Document the coordinate convention (y down, matrix a b c d tx ty) as the
  format's own.

### Loops and fades
- Mark looping sequences so Nirik can play them: which drawings, in what
  order, loop length, loop mode. Horn magic (`PTS_HornMagic`, 100 frames;
  `RY_HornMagic`), Luna's mane, blink cycles (2026-11-09)
- Fades in the source are color transforms on the instance (alpha), often
  tweened. Carry them as opacity data once Nirik has per-part opacity
  (2026-11-09)
- Twilight's magic also sits on a HAIR layer in 3 head poses (riggers
  reused the layer): the part label should come from the drawing, or the
  converter should split it out (2026-11-09)

### Walk cycles
- Walk libraries are heavy: most of it is the source shot's head
  performance (Twilight's side walk: 1,538 drawings, ~300 for the body
  loop). Import the body loop only, and attach the character's own standing
  head instead of the walk's copy (more mouths, smaller library).
- The walk head starts on the source shot's expression (Twilight: eyes
  closed).
- Import walks as cycles of the main puppet rather than separate puppets.
- The head bob is a classic tween in the source; it's baked to per-frame
  placements. Could export it as a curve.
- More walks: 3/4 and rear (circling the mailbox), trots, runs. Rarity has
  the most material (S08E13, S09E22).

### Rig structure
- Hooves and similar sub-pieces are flattened into their leg drawings.
  Promote nested pieces that move relative to their parent (the census saw
  animators move hooves) to their own parts.
- Body hierarchy: the stock body rig is flat (legs, torso, neck are
  siblings). If Nirik gains "part carries part", the converter could write
  a default pony hierarchy.

### Vector export
- Export drawings as vectors as well as rasters, for Nirik's vector-drawing
  idea (2026-11-09)

### Evaluator and census
- Custom eases aren't evaluated (affects replay accuracy only).
- The census measures raw nesting depth; measure *animated* depth instead.
- Draw-order changes are only detected among the same siblings.

### Data
- S09E24 extraction stopped partway (1,204 files); it held Spike's walk.
- MLP813_031.fla is a corrupt archive (bad CRC).

## Fixed
- Spike's walk head lost its skull under an empty "PUPIL" mask layer: empty
  masks mask nothing, as in Flash.
- Walk speed is measured from planted feet, per foot (a dipping toe broke it).
- Imports ran out of memory with 6 workers next to a big extraction: 2 workers
  by default, heavy jobs one at a time.
- Dark fringes around every drawing: transparent pixels get bled edge colors.
- Wrapper symbols around a rig (a walk's head) are imported as rigs, so the
  head inside stays editable.
