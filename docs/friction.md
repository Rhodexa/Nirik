# Friction log

One line per moment where Nirik got in the way, or a workaround was needed.
No need to fix things when writing them down; lines that keep coming back
become the priority list. Newest first within each section.

## Open

### Walk cycles
- Walks are separate characters: standing and walking Twilight can't be one
  rig, so stopping at the mailbox means swapping characters mid-shot.
- Walk heads come with their own, smaller drawing sets (missing mouths the
  standing head has). Want: the character's own head on the walk body,
  keeping the whole rig.
- The head bob is baked into hidden socket keys on every frame of the cycle:
  it plays, but there's no visible curve to see or edit what drives it.
- Walk imports are heavy: most of a walk library is the head performance
  (Twilight's side walk: 1,538 drawings, of which the body loop needs ~300).
- The walk head starts on the source shot's expression (Twilight: eyes closed).

### Posing
- No body hierarchy: rotating a torso leaves legs behind; Spike's arm needs
  three pieces selected (upper, lower, hand) to rotate together.
- No movable pivots (stand on hind legs: pivot at the hips).
- Hooves and similar sub-pieces are baked into their leg drawings; can't
  move a hoof alone.
- Spike's rig has no far-limb darkening, so Far does nothing on him.

### Drawings
- Drawing browser: you click the button under a thumbnail, not the
  thumbnail itself (Blender limitation; a matcap-style picker would allow it).
- Stretching a part stretches its raster (smeared stripes, clipped tail tip).

## Fixed
- Several puppets (or .blend files) of the same library repainted each
  other's texture tiles: palettes are shared per library now.
- Importing your own art: Import Prop (pictures and sprite sheets).
- Characters missing pieces under an empty mask layer (Spike's walk head lost
  its skull): empty masks now mask nothing, as in Flash.
- Selecting several exact pieces: Shift+double-click, Shift on panel buttons.
- Importer exhausted memory with 6 workers next to a big extraction: default
  is 2 workers now, heavy jobs run one at a time.
- Renaming the project folder broke saved scenes: libraries relink on load.
- Moving keys in the Dope Sheet desynced the rig: syncs automatically.
- Swapping drawings while auto-keying turned the animator's own transform
  keys into holds.
- Parts reordered when the camera turned.
- Alt+Wheel scrubbed the timeline when the part had no drawings.
