# Nirik journal

Friction (where Nirik got in the way, or a workaround was needed) and ideas
we don't want to forget. No need to fix anything when writing it down; lines
that keep coming back become the priority list. Add lines directly, or say
them in chat. Newest first within each section; `(date)` marks when an item
came up.

## Friction

### Puppets and scenes
- Moving between puppets is clunky: to stop animating one and start
  another you leave Pose mode, select the other armature, re-enter Pose
  mode. Want: a quick switcher (2026-11-09)
- Reusing a performance: animate Rainbow Dash flying, then use that in
  another scene. Needs a way to take one puppet's animation out of a scene
  and bring it into another (2026-11-09)
- Appending a puppet into another .blend (Blender's Append): its textures
  point into the library folder on disk. What happens when the .blend or the
  library is copied elsewhere, sent to another machine, or rendered on a
  farm? Relinking covers renamed project folders, not copies. Probably
  wants a "pack for render" (2026-11-09)
- Can't use parts from other puppets: swap in a drawing or a whole part
  from another puppet (e.g. another character's mouth, a walk body with the
  standing head) (2026-11-09)

### Rig features we can't reach
- Horn magic: Twilight's and Rarity's puppets include the horn aura and
  sparkles (stock layers "stk_F17_magic_comp", "HORN MAGIC"), but there's no
  way to switch it on or play it. It's an animated loop in the source
  (2026-11-09)

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
- UI hard to work around, especially on Spike. Specifics to collect: which
  parts, which actions (2026-11-09)
- No body hierarchy: rotating a torso leaves legs behind; Spike's arm needs
  three pieces selected (upper, lower, hand) to rotate together.
- No movable pivots (stand on hind legs: pivot at the hips).
- Hooves and similar sub-pieces are baked into their leg drawings; can't
  move a hoof alone.
- Spike's rig has no far-limb darkening, so Far does nothing on him.

### Drawings and rendering
- Tiny editing and rendering issues on Spike. Specifics to collect
  (screenshots in `screenshots/` work) (2026-11-09)
- Drawing browser: you click the button under a thumbnail, not the
  thumbnail itself (Blender limitation; a matcap-style picker would allow it).
- Stretching a part stretches its raster (smeared stripes, clipped tail tip).

## Ideas and side quests
- **Vector rendering path:** render puppets from their vectors through the
  same pipeline (e.g. Grease Pencil per part) for exact line quality, at
  least as an option per part. Compare against the raster path (2026-11-09)
- **Bendable cards:** a part's card as a grid instead of a quad, so a
  drawing can bend (Simple Deform, lattice, cloth). For things like the
  envelope, tails, manes (2026-11-06)
- **Vocabulary:** Puppet / Symbol / Node / Pose instead of character / rig /
  slot / construction; rename UI and format together (2026-11-06)
- **Flash-free Nirik:** the converter writes parts, labels, sets and the
  far color into the puppet, so Nirik stops guessing them from show-rig
  conventions (2026-11-06)
- **Lip sync** from audio, keyed by the phoneme tags of the stock mouth
  charts; real-time from a microphone as a toy (2026-11-02)
- **More walks:** 3/4 and rear walks for circling (Special Delivery), trots
  and runs; merge walks into the main puppet (2026-11-03)

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
