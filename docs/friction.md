# Nirik journal

Friction in Nirik itself (where it got in the way, or a workaround was
needed) and ideas we don't want to forget. Nirik knows nothing about Flash:
anything about turning show files into puppets goes in the converter's own
journal, `devtools/flash/JOURNAL.md`. When an item has a half on each side,
each journal gets its half.

No need to fix anything when writing it down; lines that keep coming back
become the priority list. Add lines directly, or say them in chat. Newest
first within each section; `(date)` marks when an item came up.

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
- Can't borrow from other puppets: show a drawing, or put a whole part,
  from another puppet (another character's mouth, a standing head on a walk
  body) (2026-11-09)
- A puppet can't be both standing and walking: stopping at the mailbox means
  swapping puppets mid-shot. Want: a puppet with several cycles and its
  standing poses, switched by pose.

### Parts that move on their own
- Looping parts: some parts animate by themselves whatever the puppet does,
  e.g. the horn magic aura (a 100-drawing loop) or Luna's waving mane. Nirik
  imports every frame as a drawing but can't *play* them: you can only step
  through by hand. Want: a part that plays a sequence (loop, once) from a
  start frame (2026-11-09)
- Opacity: no way to fade a part in and out (the aura fades on and off).
  Want: a keyable opacity per part (2026-11-09)
- Finding such parts: the aura only exists in the head poses that use it
  (19 of Twilight's 55), so with another pose it's nowhere in the UI.
  Want: every part reachable regardless of the current pose (2026-11-09)
- Cycle motion (a walk's head bob) is baked into hidden socket keys on every
  frame: it plays, but there's no visible curve to see or edit.

### Posing
- UI hard to work around, especially on Spike. Specifics to collect: which
  parts, which actions (2026-11-09)
- No body hierarchy: rotating a torso leaves legs behind; Spike's arm needs
  three pieces selected (upper, lower, hand) to rotate together. Want: a
  puppet can declare which part carries which.
- No movable pivots (stand on hind legs: pivot at the hips).
- Far does nothing on puppets without a far color (Spike). Want: set or
  override a puppet's far color in Nirik.

### Drawings and rendering
- Tiny editing and rendering issues on Spike. Specifics to collect
  (screenshots in `screenshots/` work); then triage: Nirik or converter
  (2026-11-09)
- Drawing browser: you click the button under a thumbnail, not the
  thumbnail itself (Blender limitation; a matcap-style picker would allow it).
- Stretching a part stretches its raster (smeared stripes, clipped tail tip).

## Ideas and side quests
- **Vector drawings:** a drawing can be vector (e.g. Grease Pencil) instead
  of a raster, per part, for exact line quality. Nirik's half: display and
  pose vector drawings; the converter's half: export them (2026-11-09)
- **Bendable cards:** a part's card as a grid instead of a quad, so a
  drawing can bend (Simple Deform, lattice, cloth). For things like the
  envelope, tails, manes (2026-11-06)
- **Vocabulary:** Puppet / Symbol / Node / Pose instead of character / rig /
  slot / construction; rename UI and format together (2026-11-06)
- **Stop guessing:** Nirik reads parts, labels, sets and the far color from
  the puppet instead of inferring them from naming conventions; the format
  documents its coordinate convention as Nirik's own (2026-11-06)
- **Lip sync** from audio, keyed by the mouth drawings' phoneme tags;
  real-time from a microphone as a toy (2026-11-02)

## Fixed
- Several puppets (or .blend files) of the same library repainted each
  other's texture tiles: palettes are shared per library now.
- Importing your own art: Import Prop (pictures and sprite sheets).
- A part under an empty mask disappeared: empty masks now mask nothing.
- Selecting several exact pieces: Shift+double-click, Shift on panel buttons.
- Renaming or moving the project folder broke saved scenes: libraries
  relink on load, including from sibling projects.
- Moving keys in the Dope Sheet desynced the rig: syncs automatically.
- Swapping drawings while auto-keying turned the animator's own transform
  keys into holds.
- Parts reordered when the camera turned.
- Alt+Wheel scrubbed the timeline when the part had no drawings.
