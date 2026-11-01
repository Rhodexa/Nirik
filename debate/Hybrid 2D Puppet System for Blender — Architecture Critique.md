# Hybrid 2D Puppet System for Blender — Architecture Critique

Oct 31, 2026 · @Robert Mereles

## Verdict

The philosophy is right; about a third of the proposed mechanics will fight Blender. "Reuse → transform → deform → redraw", slots that own attachment, stepped exposures, and unlit characters integrated in comp are all sound, and they match how mature cut-out tools (Spine, Toon Boom Harmony, Moho) already work. The trouble is in how some of it maps onto Blender's data model.

The three changes that matter most:

1. **Never change topology at runtime. Fake it with a superset.** Every slot a character could ever need exists permanently; a construction is just which slots show a drawing and which show the empty drawing (ID 0). "Variable construction" becomes data, not rig surgery.
2. **Separate authoring from playback with a compile step.** The animator edits intent (phoneme, expression, head angle, construction, overrides). The add-on compiles that into plain, stepped Blender F-curves that playback and rendering read directly. Rendering then needs no Python, no handlers, and not even the add-on installed.
3. **Decouple draw order from depth.** Tiny real z-offsets between cards cause perspective drift, sorting bugs and DOF mismatch. Put each character on one camera-facing plane and handle intra-character order explicitly (camera-ray offsets with scale compensation, see the depth section).

The single most valuable thing you have is the original show data. Use it as an **objective test oracle**: if the system can replay real episode animation and match your renderer frame for frame, the data model is proven. Everything it can't represent is the real requirements list.

## Core architecture

Build it as three layers: an authoring layer the animator edits, a compiler the add-on owns, and a playback layer that is 100% native Blender. This one decision answers most of your questions about undo, dependencies, render safety and maintainability.

&#91;embedded content: three layers · authoring, compile, native playback\]

Only the compiler reads the library; playback reads compiled curves and the shot texture, so a render needs neither the add-on nor the library.

**Authoring layer (what the animator touches).** One Armature per character. Bones are slots and controllers. Each bone carries ID properties such as `drawing_override`, `construction`, `phoneme`, `expression`, `look`. These are keyed with constant interpolation and edited in the Dope Sheet and your custom X-sheet overlay.

**Compiler (what the add-on does).** Pure Python that reads authoring channels plus the character library and resolves them into concrete results: which drawing each slot shows on each frame, socket offsets for children, draw-order indices, visibility. It writes those as ordinary F-curves on clearly namespaced properties (e.g. `_c.drawing`, `_c.socket_x`) in a separate action slot or NLA layer the animator never edits.

**Playback layer (what renders).** Card meshes parented to bones, one shared material per character, reading compiled values through Attribute nodes and simple drivers. No `frame_change` handlers, no Python at render time.

Why this matters:

- **Render safety.** Handlers that mutate data during playback are the classic way Blender add-ons break: inconsistent depsgraph state, broken background renders, render-farm surprises. Compiled F-curves are deterministic.
- **Undo works for free.** All state lives in ID properties and F-curves, so Blender's undo covers it. Python globals hold only disposable caches.
- **Lookup tables are allowed.** Drivers can't cheaply look things up ("eye socket position for head drawing 412"); a compiler can.
- **Debuggability.** You can inspect compiled curves directly and diff them.

The cost is two sources of truth. Mitigate it strictly: compiled channels are regenerated deterministically, never hand-edited, and visually locked. Every manual decision the animator makes lives in the authoring layer as an override. Recompile on an explicit operator plus a debounced `depsgraph_update_post` check that only flags "stale" (never writes during the handler; a `bpy.app.timers` callback does the write).

## Display representation and asset swapping

Cards are the right foundation, but the card should be fixed per slot and only its texture should change. Swapping should never create, delete or re-mesh objects, and object/material count should scale with slots (roughly 20–40 per character), not with library size.

**Bake registration into the raster: the canonical canvas.** When your renderer rasterizes a drawing for a slot, place it on a canvas where the drawing's pivot sits at the canvas center, at a fixed pixels-per-unit for that character. Every drawing in a slot family then shares one coordinate frame. The card is a fixed quad sized to the union bounds of everything that slot can show. Swapping is now a pure texture lookup with zero geometry or offset math. Transparent margin costs some VRAM; at this scale that's cheap.

**Texture storage options, in order of preference:**

| Option | How the swap works | Pros | Cons |
| --- | --- | --- | --- |
| UDIM per slot family | Drawing ID → tile; shader adds integer UV offset (`u = id % 10`, `v = id // 10`) | Blender-native, one image datablock, one material, tiles can differ in resolution | \~1000 tiles per UDIM set; all tiles load into VRAM; needs a spike to confirm EEVEE behavior with computed UVs |
| Shot atlas + data texture | Drawing ID → row in a small float "lookup" image holding the atlas rect; shader samples it with Closest interpolation | Tight packing, VRAM proportional to what the shot uses | Packer + lookup texture to maintain; mip bleeding at atlas seams |
| Image sequence node | `frame_offset` driven by drawing ID | Trivial to build | Per-slot material, disk I/O on scrub, slow |
| One object or material per drawing | Toggle visibility | Obvious | Doesn't scale; avoid |

Either of the first two works. My lean: **a shot-local build** of whichever you pick. The compiler knows exactly which drawings a shot exposes (usually dozens to a few hundred), so it builds a small UDIM set or atlas from the cache for just those. VRAM and load time stay proportional to the shot, not to Twilight's entire mouth chart.

**Reading the ID in the shader.** An Attribute node of type *Object* reads an object's custom property, and that property can be animated or driven. So each card object gets an int `drawing` (driven from the compiled bone property) plus floats for tint, alpha and draw-order. One material per character serves every card.

**Stable IDs, not enums.** Animated `EnumProperty` with dynamic items is fragile: the stored value is an integer, and when items change the meaning silently shifts. Give every drawing a permanent integer ID in `character.json`, never reused, and map ID → name only in UI.

## Registration, sockets and attachment

Your rule (attachment belongs to the slot, registration to the drawing) is half right. It breaks the moment a parent drawing changes shape: a three-quarter head and a looking-down head put the eyes in different places. So attachment points must belong to the **parent drawing**, as named sockets.

The corrected model:

- **Drawing** owns its pivot (baked into the canonical canvas) and a set of named sockets: `eye_L`, `eye_R`, `mouth`, `ear_L`, `horn`, `mane_front`. Sockets carry position, and optionally rotation, scale and a draw-order hint.
- **Slot** declares which parent socket it binds to ("Mouth binds to Head.mouth").
- **Compiler** resolves, per frame, "Head shows drawing 412, so the mouth socket is at (x, y)" and writes that as a stepped offset on the child slot's socket bone.
- **Animator** transforms the child on top of that socket, in the child bone's own channels, untouched by the compiler.

Use a two-bone pattern per slot: a compiler-owned `SOCKET` bone (positioned by compiled curves) parenting an animator-owned `CTRL` bone. The animator never fights the compiler for the same channel.

Your original data almost certainly already contains this information. In the show's Flash rigs, a head is typically a nested symbol whose frames place the eyes and mouth differently per head angle. Importing those per-frame child placements as socket tables gives you real registration data for free, instead of authoring it by hand.

### Flash affine matrices vs Blender transforms

Flash instances carry full 2D affine matrices including **skew**, and animators use it. Blender objects and bones expose location, rotation and scale only. Shear can emerge from hierarchy (non-uniform parent scale plus child rotation), but you can't key it directly.

Any 2×2 matrix decomposes as rotation × scale × rotation (SVD). So if a slot needs arbitrary affine, give it a rotate → non-uniform scale → rotate chain, with bone "Inherit Scale" set so the shear actually propagates. Confirm this early in the replay test; skew will be one of the first things it surfaces. The same applies to Flash color transforms (tint, brightness, alpha multiply), which map cleanly to per-card shader inputs.

## Constructions (Pose Sets) and changing topology

Topology can change over time without making editing unbearable, as long as it changes in the data, never in the rig. Changing armature structure mid-shot breaks F-curve paths, constraints, the NLA and undo. A superset rig breaks none of them.

**Superset slots.** The character's armature contains every slot used by any construction: `Head`, `HeadDown`, `HeadComposite`, `MouthDown`, and so on. A slot that the current construction doesn't use shows drawing 0 (empty). Thirty mostly-empty slots cost almost nothing.

**A construction is a template in `character.json`**, declaring:

- which slots are active
- which drawing set each active slot draws from
- socket bindings (MouthDown binds to HeadDown.mouth)
- how high-level controls map onto this construction

**Intent channels survive construction changes.** The animator keys controls that mean the same thing in every construction: `look`, `phoneme`, `expression`, `blink`, `head_turn`. Each construction has a resolver that turns intent into drawings. In `NORMAL_3Q`, `look` moves pupils inside the eye slots. In `EXTREME_WORRIED`, the eyes are baked into the composite head, so `look` selects a composite variant, or is ignored and flagged in the UI.

**Overrides always win.** Any slot can be keyed with an explicit `drawing_override`, which beats the resolver for those frames. That's your escape hatch for "just this frame needs this drawing", and it keeps the animator in charge.

**Switching construction** is one constant-interpolated int on the root bone. The animator keys `construction = EXTREME_WORRIED` at frame 140; the compiler handles hiding, socket rebinding and drawing resolution. Controls carry across the switch, so the Dope Sheet still shows one continuous character.

The animator's mental model becomes "I'm keying what the character is doing", while the system handles "which pieces of paper make that up". That's the core of what you described as persistent controls over replaceable construction.

## Deformation and replacement drawings

The canonical canvas makes deformation and replacement compose naturally: deformation acts on the card's geometry, replacement acts on its texture, and they never touch the same data.

- **Deformable slots** use a subdivided grid instead of a quad, still covering the slot's union bounds, deformed by an Armature modifier (a few deform bones) or a Lattice for squash and stretch. UVs are fixed, so a swapped drawing inherits the current deformation automatically.
- **Deformation profiles belong to the slot, not the drawing.** That's a deliberate limitation. Spine and Live2D allow per-attachment meshes and weights, but in Blender that means swapping mesh data per frame, which is exactly the churn you want to avoid. If a drawing needs a genuinely different deformation, it belongs to a different slot in a different construction.
- **Deformation strength can be an intent channel.** For example, `ear_bend` drives deform bones. When a pose exceeds what looks good, the animator keys an override or a construction switch. That's "redraw when necessary" as a first-class operation, not a failure.

One caution: keep deforming slots few. Arbitrary mesh warps on flat-colored vector art reveal stretched linework (line weight thickens and thins) much faster than on painted art. Ears, tails, mane tips, and squash on the head and body are the sweet spot.

### Replacement-drawing workflow

The canonical canvas also solves the hardest part of your eight-step workflow, registering the new drawing. If the template is exported in slot-canvas space, whatever the artist paints is already registered.

1. "Create Replacement" on `Rarity.Head` at frame N.
2. The add-on renders the current construction, inverse-transformed into that slot's canvas space, at 2–4× working resolution. It adds previous and next exposures as tinted onion layers, plus a socket overlay showing where children attach.
3. It writes a layered file (PSD or KRA) into `characters/rarity/custom/`, pre-assigns the next drawing ID, and opens your painter.
4. A `bpy.app.timers` poller watches the exported PNG's mtime (never touch `bpy` from a thread). On change: rasterize to cache, register in the library, rebuild the shot texture, key an override at frame N.

Offer two modes: **replace slot** (just the head) and **flatten subtree** (head plus eyes, mouth and mane, painted as one composite drawing, which automatically keys a composite construction). The second is how extreme poses really get made.

If new drawings should match the show's vector line quality, painting raster at 2–4× is fine for this shot. Longer term, consider a vector path (Inkscape, or vectorizing clean raster) into the same renderer, so custom art and source art go through one pipeline.

## Exposure timing, X-sheet and lip sync

Stepped timing is easy in Blender; seeing it is the hard part. The Dope Sheet shows a diamond for an int key, not the drawing name, so the exposure sheet is where the real UI investment goes.

**Timing mechanics:**

- Drawing IDs, construction and phoneme: int properties, always **constant** interpolation (enforce it when the add-on inserts keys).
- Transforms on twos or threes: the **Stepped Interpolation** F-modifier (step size plus offset). The add-on manages it per channel group, via a `rate` property on each character or slot group: environment at 24, character poses at 12, effects at 24.
- Variable exposures: just key poses with constant interpolation, as in blocking. Nothing is smoothed unless someone asks.
- Mixed: a head turn can be smooth on ones while the mouth holds on twos, because rate is per group.

**Exposure sheet UI.** Python can't create a new editor type, so don't build a fake one in a sidebar. Draw into the Dope Sheet instead: a `SpaceDopeSheetEditor.draw_handler_add` overlay that prints drawing names (and small thumbnails when zoomed in) beside each slot's channel and key. Pair it with a few modal operators (scroll a drawing at the current key, type a drawing name, extend or shorten an exposure). That keeps Blender's selection, box-select, copy and paste and NLA working. A separate panel-based X-sheet is optional, later.

**Lip sync.** Run an analyzer (Rhubarb Lip Sync is the usual open-source choice) to key the *phoneme* intent channel, not drawings. The resolver picks the actual mouth from (character, expression, head angle, phoneme), so changing expression later re-resolves every mouth automatically. That's exactly your "contextual mouths, not universal decals" goal, achieved structurally. The animator then edits phoneme timing, adds overrides for acting beats, and tends to thin the automated keys toward fewer, stronger shapes. Your original mouth sets should map directly into phoneme tables per expression and angle.

## Depth ordering and 2.5D

Draw order and depth are different things, and the proposal conflates them. In 2D animation draw order changes constantly (the far foreleg crosses in front, a wing tucks behind the mane). Encoding that as real z-offsets causes four problems:

- **Perspective drift.** Cards at different depths scale differently. Close to camera, an eye card 1 cm in front visibly shifts against the head.
- **Sorting.** EEVEE sorts blended transparent surfaces per object, not per pixel. Closely stacked cards flicker as their order flips with camera moves.
- **DOF and motion blur** treat the layers as separate depths, splitting the drawing.
- **Draw-order changes** become z-position animation, which is miserable to edit.

**Recommended model:**

1. **One character plane.** Each character has a world-space anchor (in the seat) and a plane that faces the camera, via a Damped Track or Copy Rotation from the camera. A drawing seen at an angle foreshortens and stops looking like a drawing, so screen-parallel is the default.
2. **Explicit draw order.** Each slot has a compiled `order` value, keyable (like Spine's draw-order timeline), with a construction default.
3. **Order → depth with scale compensation.** The add-on pushes each card toward the camera along the camera ray by `order × ε` and scales it by `(d − order·ε) / d`. The card projects to exactly the same pixels with zero parallax, but the depth buffer and sort order are correct. Implement it as a driver or constraint on the card, not a handler.
4. **Authored parallax, if you want it.** If you want the subtle pseudo-volume you described, add it as a separate parameter ("near layers shift x% more on camera move"), off by default. Emergent parallax from real z is uncontrollable; authored parallax is a style choice.

**Interaction with the cockpit** uses the character plane's real depth. The window frames, glare shield and seat back occlude the character correctly because the plane sits at the right place in the scene. For tricky contact (a hoof resting on the yoke), use a holdout proxy mesh or a per-slot depth bias.

In your reference frame the characters sit a few meters behind the glass, seen nearly front-on. Any parallax between layers would be sub-pixel, so a flat plane is clearly the right call here.

## Rendering and color pipeline

Unlit characters plus integration in comp is the right philosophy. The trap is the view transform: decide the color pipeline before anything else.

**AgX (or Filmic) will shift model-sheet colors.** It's designed to compress and desaturate highlights, so Twilight's purple and Rarity's white won't land on their show values. Options:

- **Two-pass comp (recommended).** Render the environment through AgX as usual. Render characters in a pass meant for Standard. Composite in display space, with the environment already tone-mapped and the characters' flat colors preserved, then apply integration effects on top. The simplest robust route is two scenes or a final comp in a Standard-transform scene.
- **Pre-compensation.** Invert the view transform on character colors so they land correctly after AgX. Fragile, and it breaks whenever exposure changes.

**Alpha.** Rasterize premultiplied with clean edges, and set the image alpha mode to match, or you'll get dark fringes on every card. Use 2× screen resolution or more for close shots and generate mips. In EEVEE, blended mode plus the depth scheme above gives clean edges; dithered or hashed is noisy in the viewport. Cycles has no sorting problem but is overkill for emissive cards.

**Integration passes,** each driven from scene data rather than painted:

- **Light wrap and color influence:** a blurred environment plate tinted into the character's edges, plus a global multiply or screen grade. Your dusk scene wants a warm rim from the windows and a cool fill.
- **Contact shadows and AO:** a duplicate of the character silhouette as a shadow-only card, offset onto the seat back, and a soft AO proxy.
- **Glass:** the windshield's reflections and glare go **over** the characters; this matters a lot for your reference shot.
- **Atmosphere, DOF, grain, softness:** applied to the final comp, so characters and environment share them.

Keep character cards out of the environment's light bounce, so the cockpit isn't lit by a glowing purple pony. In Cycles, use light-path tricks; in EEVEE, use light linking or put characters on their own view layer.

## Data placement, caching, undo and reloads

The .blend holds decisions; the library holds artwork and its metadata; the cache holds anything regenerable. A deleted cache should cost only time, never work.

| Lives in | Contents |
| --- | --- |
| .blend | Armatures and cards, authoring and compiled F-curves, scene, camera, comp. A **manifest** of drawing IDs the shot uses, each with a content hash, plus the library path (relative) and schema version |
| Library (`characters/<name>/`) | `character.json` (slots, constructions, socket tables, phoneme maps, ID registry), source artwork (SVG, source data, PSD/KRA), per-drawing metadata and tags |
| Cache (outside both) | Rasters keyed by `hash(source, resolution, renderer version)`, thumbnails, shot UDIMs or atlases |

**Undo.** Keep all persistent state in ID properties, PropertyGroups and F-curves. Python module globals hold only caches keyed by content hash, so an undo that changes the data simply misses the cache and rebuilds. Never cache Blender object references across operators; store names or IDs.

**Dependencies.** Playback uses only drivers, constraints and shader attributes, which the depsgraph already understands. The add-on's handlers only mark things stale (`depsgraph_update_post` noticing an authoring F-curve changed, `load_post` validating the manifest). Actual work runs from operators or a debounced timer.

**Reloads.** A timer polls library mtimes for drawings in the manifest. On change: re-rasterize, update the shot texture with `image.reload()`, done. No objects change. On file open, verify manifest hashes against the library and warn about drift ("drawing 412 changed since this shot was animated").

**Thumbnails and browser.** Don't use Blender's Asset Browser for drawings. It wants every asset as a datablock in a .blend, which is wrong for thousands of rasters with rich metadata. Use `bpy.utils.previews` collections fed from the thumbnail cache, shown in a popup or sidebar grid filtered by character, slot, angle, expression and tags. Load previews lazily for the filtered set only; loading thousands at once stalls the UI. The Asset Browser does fit for **rig and construction presets** and environment props.

**Proxies.** Viewport resolution is a per-shot setting on the texture build (½ or ¼ res), with full resolution swapped in at render. Because registration is baked into a normalized canvas, resolution changes never move anything.

**Pack for render.** One operator gathers the shot's used rasters into a self-contained folder beside the .blend, so a render machine needs neither the library nor the add-on.

## Add-on internal structure

Keep the hard logic out of `bpy`. Most of this system (library schema, resolvers, the compiler's decisions, packing) is pure data transformation, testable with pytest in milliseconds and easy for Claude Code to iterate on.

```
puppet/
  core/          # no bpy imports. Ever.
    schema.py      character.json models + versioned migrations
    library.py     load/index drawings, ID registry, tag queries
    resolve.py     intent + construction + overrides -> per-frame slot state
    sockets.py     socket tables, affine/SVD decomposition
    timing.py      exposure maths, stepped rates, lip-sync import
    pack.py        UDIM/atlas layout from a set of drawing IDs
  bridge/        # the only layer that touches bpy data
    rig_build.py   create armature + cards + material from a character
    compile.py     run core.resolve, write compiled F-curves
    textures.py    build/reload shot textures, previews
    handlers.py    stale-flagging + timers only
  ui/            # panels, operators, Dope Sheet overlay, browser
  io/            # your SVG renderer bridge, painter round-trip, file watch
  tests/
    core/          pytest, no Blender
    blender/       blender -b --python runners, golden-frame diffs
```

Rules that keep it maintainable:

- `core` defines a frame-by-frame **slot state** dataclass (drawing ID, socket offset, order, tint, visibility). It's the contract between resolver and compiler, and the thing your golden tests compare.
- `bridge` is idempotent: running the compiler twice produces identical curves. Make that a test.
- Package it as a Blender extension (`blender_manifest.toml`), with the renderer as a vendored wheel or a separate process. If your renderer is heavy, run rasterization out of process and talk over files; it keeps Blender responsive and isolates crashes.
- Version `character.json` from day one and write migrations. The schema will change a lot in the first months.

## Prior art worth stealing from

Your design is closest to Spine's data model; borrow its vocabulary and its separation of concerns rather than inventing new ones.

| Tool | Idea to steal | Where it lands here |
| --- | --- | --- |
| Spine | Bones → slots → attachments; skins; draw order as its own keyed timeline; attachment keys; empty attachment | Superset slots, drawing 0, the `order` channel |
| Toon Boom Harmony | Drawing substitution with an exposure sheet; pegs vs drawing layers; master controllers driving many substitutions; template libraries | Peg = `CTRL` bone; master controllers = intent channels; constructions = templates |
| Moho | Switch layers (a layer whose child is chosen per frame); Smart Bones (a bone angle drives arbitrary actions) | Switch layer = a slot; Smart Bones = resolvers keyed off controls, e.g. head turn picking drawings |
| Live2D Cubism | Parameters as the animator's interface, with art meshes and warp deformers resolving underneath | Intent channels; deformation profiles for slots |
| Flash (the show's own rigs) | Nested symbols with per-frame child placement; frame labels as states | Socket tables and constructions, imported from your source files |

The common lesson across all of them: animators key **parameters**, and the system resolves parameters into drawings. That's the authoring and compile split above. The architecture you described is reinventing it under different names, which is a good sign the core idea is sound.

## Smallest serious prototype

Build a replay of original show animation before building any authoring UI. Your access to the real rigs and timelines is what makes this possible, and it turns "does the architecture work?" into a measurable pixel diff.

**Spike 1: texture swap feasibility (2–3 days).** One card, Rarity's complete mouth set, int property keyed constant.

- Build it with UDIM and with atlas + lookup texture, and compare.
- Measure viewport fps while scrubbing, VRAM, load time, edge quality at 1× and 2× resolution, EEVEE and Cycles parity.
- Confirm the Attribute (Object) → shader path updates per frame, in the viewport and in a background render.

**Spike 2: the replay test (the real prototype).** Take 5–10 seconds of an actual episode shot featuring Twilight from the original files.

1. Convert its symbol timeline (nested instances, matrices, frame indices, color transforms) into the armature, sockets and compiled drawing keys. No authoring layer yet; compile directly.
2. Render through an orthographic camera matching the stage.
3. Diff every frame against your existing renderer's output. Track mean and max pixel error per frame.

Every mismatch is a requirement discovered for free: skew, masks, nested animated symbols (your "idle\_loop mane"), color effects, symbols whose internal frame advances independently of the timeline, and draw-order changes mid-shot. Fix the model until the diff is near zero, and you'll know the data model can represent everything the show actually did.

**Spike 3: authoring the cockpit shot.** Only now build the authoring layer: intent channels, two constructions for Twilight, Rarity's book-reading pose, Rhubarb-driven phonemes, the Dope Sheet name overlay, one replacement drawing round-trip, and the two-pass AgX/Standard comp. Animate the 10 seconds, and keep a log of every moment you reached for a tool that didn't exist. That log is the real roadmap.

Things to deliberately **not** build yet: the full browser UI, nested animated symbols as a general feature, deformation beyond one ear, lip-sync tuning, and a standalone X-sheet panel.

A useful side effect: the replay importer becomes your bulk-ingest path. Every original scene becomes a source of real constructions, socket tables and mouth-per-angle maps, so the library fills itself with production-proven data rather than hand-entered metadata.

Second-pass addendum (selection, transforms, render components, masks, depth, replay census): Addendum: second pass
