# Addendum: interaction, render components and masks

Oct 31, 2026 · @Robert Mereles

## Changes to the baseline

None of these ten areas breaks the baseline's core (authoring → compile → native playback, superset slots, canonical canvases). But you were right that it conflated slots with cards, and fixing that ripples into draw order, masks and atlases. Eight revisions:

1. **Four levels, not two.** Control → Slot → Drawing → Render component. The render component, not the slot, is the unit of cards, atlas tiles, draw order and masking.
2. **Draw order is per component**, resolved from a per-construction layer stack plus keyed overrides. One drawing can put components anywhere in the stack.
3. **Card pools.** Each slot owns a fixed pool of card objects sized to the largest component count among its drawings. Unused pool cards show tile 0.
4. **Masks are two-tier.** Static masks bake into the raster; live masks are a per-pixel shader multiply. This revises "one material per character" to one shared material plus a handful of masked variants.
5. **Bone chain grows.** It becomes SOCKET → CTRL → AFFINE (two compiler-owned bones for skew). Flip becomes an intent, so the resolver can also flip near/far draw order.
6. **Selection goes through a custom tool**, not object selection. Cards are never selectable; clicks are resolved by alpha-picking components and mapping them to controls.
7. **Depth generalizes.** The camera-ray offset with scale compensation becomes a per-component depth parameter, so a hoof can occlude like it's in front of the yoke without changing its image.
8. **Nested timelines become clips.** A slot can play a drawing sequence with Flash's graphic-symbol semantics (loop, play once, single frame, first frame).

The replay test becomes two-stage with a feature census (section 10). That census, more than anything in this document, should decide which of these features are worth building.

## 1. Viewport selection

The animator clicks the artwork, and the click selects a control (a pose bone), never a card. Cards are always `hide_select = True`. Blender's object selection never sees them, so there's nothing to fight.

**The Puppet Select tool.** A Python `WorkSpaceTool` for Pose mode on the character armature, with its own keymap, replacing the default Tweak or Select tool. On click it:

1. Projects the mouse onto each character plane and converts to each candidate card's canvas coordinates.
2. Samples a low-res alpha copy (for example 128 px, kept in the raster cache as a NumPy array) of the component currently exposed on that card. A hit means alpha above about 0.3, so clicks on transparent margins pass through.
3. Sorts hits by compiled draw order, topmost first.
4. Maps each hit component to its owning control, then raises it to the current **pick level**.
5. Selects that pose bone and makes it active. From there, G, R, S, I and auto-key behave exactly as native Blender.

**Pick levels** solve the overlapping-face problem: one click on the face shouldn't have to choose among mane, eye, iris, mouth and head.

| Level | A click on the eye selects | Typical use |
| --- | --- | --- |
| Character | Root | Placing and blocking |
| Part (default) | Head | Most acting |
| Feature | Eye | Expressions and looks |
| Detail | Iris | Rare, fine tweaks |

- **Double-click** drills one level deeper at that spot (the Flash "enter symbol" gesture); **Esc** or **Ctrl+Up** climbs to the parent.
- **Alt+click** cycles through the other controls under the cursor, in draw order. **Ctrl+Alt+click** opens a list of them with names and thumbnails.
- **Shift+click** extends the selection, as usual.
- **Locks** are per control. A locked control is skipped by picking and its hits fall through to whatever is beneath. Mane Front is the usual candidate, since it covers so much of the face.

**Other entry points** select the same pose bones: an outliner-style tree in the sidebar (Root ▸ Body ▸ Head ▸ Eye L), and clicking bone shapes directly in Controls mode.

**Bone shapes vs gizmos.** Use custom bone shapes as the visible handles, because transforms on them are native (keying, undo, snapping, constraints all just work). Use a `GizmoGroup` only for special handles that aren't plain transforms, such as a look-at target you drag to set eye direction. Avoid reimplementing G, R or S as gizmos.

Feasibility check for a spike: deforming cards (grid plus armature) won't match the undeformed alpha copy exactly. Picking on the undeformed grid is fine for modest deformation.

## 2. Transform chain and ownership

The head moves as one unit because every child socket is a child of the parent's control chain. Sockets are expressed in the parent drawing's canvas space, which is the parent's local space, so they inherit whatever the animator does to the parent.

```
ROOT_CTRL                      animator
└─ Body_SOCKET                 compiler (from root / construction)
   └─ Body_CTRL                animator
      └─ Body_AFFINE_A/B       compiler (skew; identity by default)
         ├─ cards: body.*      render components, parented here
         └─ Head_SOCKET        compiler (Body drawing's "neck" socket)
            └─ Head_CTRL       animator   <- scale/rotate/move here
               └─ Head_AFFINE_A/B
                  ├─ cards: head.fill, head.outline_rear, ...
                  ├─ Eye_L_SOCKET   compiler (Head drawing's "eye_L")
                  │  └─ Eye_L_CTRL  animator
                  │     └─ ...  cards: eye.*, live mask
                  │        └─ Iris_L_SOCKET -> Iris_L_CTRL (Detail level)
                  ├─ Mouth_SOCKET -> Mouth_CTRL
                  ├─ Ear_*, Horn, ManeFront ...
```

**Ownership rule: animators own CTRL bones and intent; the compiler owns everything named SOCKET or AFFINE, plus all card properties.** Neither ever writes the other's channels.

| Animator owns | Compiler owns |
| --- | --- |
| CTRL location, rotation, scale | SOCKET transforms (from parent drawing's socket tables) |
| `flip`, `skew` intent values | AFFINE helper bones (skew decomposition) |
| Drawing overrides, construction, phoneme, expression, look | Card tile IDs, draw order, depth offset, mask tile, tint |
| Draw-order overrides, depth breakout (section 9) | Visibility of pool cards and dormant controls |

**Edge cases:**

- **Non-uniform head scale.** With bone Inherit Scale set to *Full*, children rotating inside a squashed head shear, exactly as Flash's matrix multiplication does. That's correct 2D behavior. For parts that must stay round (pupils, highlights), set *Aligned* or *Fix Shear* per slot in the character definition.
- **Flip.** Don't let animators put negative scale on arbitrary bones. Make `flip_x` an intent on the character (or on Head), compiled into a scale of −1 on a dedicated FLIP bone near the root. Because the resolver knows about it, it can also swap near/far layers (near ear ↔ far ear) and refuse drawings tagged "asymmetric, don't mirror". Twilight's part and Rarity's curl make that tag essential.
- **Skew.** Bones can't key shear. The animator keys a `skew` property; the compiler decomposes the full 2×2 matrix as rotation × scale × rotation into the two AFFINE bones. Skew sits after the animator's transform, so children inherit it. In the replay, imported source matrices go through the same decomposition.
- **Child drawing changes.** The child's own registration is baked into its canvas, so nothing moves. Its sockets for grandchildren (for example where the iris sits) step to the new drawing's values. The animator's CTRL offsets stay relative to the new socket, so the eye keeps its acting offset across the swap.
- **Whole character scaled.** Everything follows the root. The only consequence is resolution: the compiler computes each component's maximum on-screen size across the shot and picks the raster resolution for the shot texture accordingly.
- **Construction switch under a transformed parent.** CTRL bones are shared across constructions, so the new construction inherits current transforms with no pop, provided every drawing in a family registers to the same pivot (the neck joint for all head drawings, including HeadDown and HeadComposite). Make that a library validation rule with a checker. Controls a construction doesn't use go dormant: their keys stay but have no effect, greyed out in the UI.

## 3. Control, slot, drawing, render component

Yes, this distinction belongs in the data model, and it's the most important correction in this pass. The baseline merged "what the animator grabs" with "what the GPU draws"; they need to be separate.

| Level | What it is | Blender form | Animator sees it? |
| --- | --- | --- | --- |
| Control | A transform the animator grabs, plus intent channels | CTRL pose bone (+ SOCKET, AFFINE) | Yes |
| Slot | An exposure channel: which drawing, over time, in a control's space | Compiled `drawing` property on the control | Yes, through the X-sheet and browser |
| Drawing | One exposed state: registration, sockets, tags, and its component list | Entry in `character.json` | Yes, as a thumbnail |
| Render component | One layer of a drawing: tile, mask, layer key, tint, blend | A card from the slot's pool | Only in Render Debug mode |

**When does something deserve a control rather than a component?** If it moves independently over time, it's a control (possibly hidden at the Detail pick level, like the iris). If it only renders separately (different draw-order position, its own mask, its own color transform), it's a component. A Head drawing's fill, rear outline, front outline and shading layer are components of one drawing; the eye is a separate control because it's animated relative to the head.

Usually one control has one slot. A control can own several slots when parts swap independently but always move together, such as an eye shape and an eyelid that blink on different drawings.

A drawing's component list looks like this in the library:

```
"drawing": {
  "id": 4120, "slot": "head", "tags": ["3q", "neutral"],
  "sockets": { "eye_L": [..], "mouth": [..], "mane_front": [..] },
  "components": [
    { "key": "outline_rear", "layer": "head.rear",   "raster": "..." },
    { "key": "fill",         "layer": "head.base",   "raster": "..." },
    { "key": "outline_front","layer": "head.front",  "raster": "...",
      "mask": null, "tint": null, "blend": "normal" }
  ]
}
```

Components rasterize into the same slot canvas as their drawing, so their local transform is normally identity. Keep an optional transform field for the rare flattened-symbol case where baking it into the raster isn't practical.

## 4. Clipping and masks

Recommendation: two tiers. Bake every mask whose relationship to its content doesn't change in the shot; render the rest as a per-pixel shader multiply that samples the mask tile in the mask owner's space. No stencil, no compositor, no per-frame Python.

| Approach | Verdict | Why |
| --- | --- | --- |
| Bake into raster | **Use for static masks** | Your renderer already clips correctly. If the iris never moves relative to the eye in this shot, there's nothing to do at runtime |
| Shader alpha mask | **Use for live masks** | Per-pixel, deterministic, works in EEVEE and Cycles, independent of draw order, fast |
| Stencil buffer | Not viable | EEVEE exposes no user stencil |
| Geometry masks (mesh cut) | Fallback only | Mask changes mean re-meshing per drawing; heavy and awkward |
| Compositor masks | Avoid | Not in the viewport, breaks per-component ordering, per-pass complexity |
| Precomposed subtree | Same as baking | Good when a whole subtree doesn't animate internally |

**How a live mask works.** Say the iris card is clipped by the eye opening:

1. The eye drawing declares a mask component (`eye.mask`). It's rasterized into the eye's slot canvas like any other component and gets a tile in the shot texture, but it's never drawn.
2. The iris card gets a **masked material variant**: the shared character material plus a mask branch. A Texture Coordinate node with its *Object* field set to the eye's card (or an empty at the eye CTRL) gives each iris pixel's position in eye-canvas space.
3. The compiler writes the mask's tile ID onto the iris card as a property (`_c.mask_tile`), so when the eye drawing changes, the mask changes with it on the same frame.
4. The shader samples the mask tile at that position and multiplies alpha. The iris moves freely under its own control; the mask follows the eye.

This survives draw-order changes because it's geometric, not order-based like Flash's layer masks. It costs one extra texture sample per masked pixel. The trade-off is that each masked card needs its own material (the Object field is per node), but a character has only a handful: two irises, two pupils, two highlights.

**Details that matter:**

- **Nested masks** (iris inside eye, highlight clipped to iris): give the variant two mask slots and multiply. Deeper nesting is rare; bake it or flag it in the census.
- **Edges.** Rasterize masks antialiased. Seams are usually invisible because the eye's front outline is a separate component drawn above the iris, exactly as the source rigs do it.
- **Deformed mask owners.** Object space ignores mesh deformation, so don't deform cards that own live masks. That's an easy rule to enforce.
- **Spike item:** confirm Texture Coordinate (Object) plus computed tile UVs behaves identically in EEVEE viewport, EEVEE render and Cycles.

## 5. Split outlines and interleaved draw order

Yes, one drawing ID can produce several components at different points in the global order, and the four-level model already handles it. Components carry a **layer key**, not a position; each construction owns an ordered **layer stack** that says where each key goes.

```
construction NORMAL_3Q, layer stack (back to front):
  mane.back
  wing.far
  leg.far
  body.base
  head.rear        <- head drawing's rear outline
  head.base        <- head drawing's fill
  ear.far
  eye.*            <- eye shape, iris (masked), highlight
  mouth.*
  muzzle.front
  head.front       <- head drawing's front outline
  mane.front
  ear.near
  leg.near
```

**Resolution per frame:**

1. Start from the active construction's stack.
2. Apply flip (swap `near` and `far` keys).
3. Apply keyed draw-order overrides, Spine-style: "move `leg.near` below `body.base` from frame 140 to 152".
4. Assign every exposed component an integer order; the compiler writes it to that card's `_c.order`, which feeds the camera-ray depth offset.

Components keep their owner's transform because the cards stay parented to the owner's chain. Only their order is global, so a head outline can sit above the mouth while moving with the head. The animator never sees any of this; they see Head.

**Interaction with the shot texture:** each component is its own tile. The compiler's atlas key becomes (drawing ID, component key) rather than drawing ID. Nothing else changes.

**Interaction with card pools:** a head slot whose richest drawing has four components gets four pool cards. A drawing with two components leaves two cards on tile 0. Pool cards aren't tied to layer keys; the compiler assigns order per frame, so a pool card can be the rear outline on one frame and the fill on another.

One caveat: draw order must be resolved per character, then mapped to depth. Two characters' stacks never interleave, which matches how a scene like the cockpit works (Twilight entirely behind or in front of Rarity's plane).

## 6. Nested symbols: what survives import

Use a hybrid, decided by evidence rather than by hand. Each nested symbol instance in the source becomes exactly one of three things, based on how it behaves across the corpus:

| Becomes | When | Example |
| --- | --- | --- |
| **Control** (with slot) | Its transform relative to its parent varies over time, or it's a library semantic part | Head, Eye, Mouth, Iris |
| **Clip** (slot playing a sequence) | It has its own internal timeline that advances independently of the parent's drawing changes | Blink cycle, mane idle loop |
| **Flattened into components** | Its relative transform is constant for a given parent frame, and it has no independent timeline | Eye sclera, head shading, highlight shapes, outline pieces |

The test for "varies" is mechanical: for each nested instance, collect its matrix relative to its parent for every use with the same parent frame. Constant means it's construction, so it becomes a socket or is flattened. Varying means an animator moved it, so it needs a control. The census in section 10 produces exactly this data.

**Clips** reuse Flash's graphic-symbol semantics, which the show's pipeline almost certainly relied on (graphic symbols scrub with the timeline; movie clips don't): a slot gets `clip`, `clip_mode` (loop, play once, single frame) and `clip_first_frame`. The compiler expands them into stepped drawing IDs, so playback is still plain F-curves.

**Depth limit.** Aim for at most four control levels (Root ▸ Head ▸ Eye ▸ Iris). Anything deeper gets flattened, and the census will tell you whether that ever loses something real.

One structural fact worth knowing for the importer: in Flash, a nested symbol's contents draw **contiguously** in the parent's display list. A symbol can't render half its layers behind a sibling and half in front. So when the show's rigs achieve split outlines, they do it with separate instances on separate parent layers that move together. The importer should detect those co-moving instances (identical matrices on every frame, same library family) and group them as components of one drawing.

## 7. Controller visualization

All five modes are realistic with stock API. Split the work by what changes: static handles are custom bone shapes; anything that depends on the current drawing (silhouettes, names, sockets, masks, order) is drawn by a `SpaceView3D` draw handler using the `gpu` module for lines and points and `blf` for text.

| Mode | Shows | Built with |
| --- | --- | --- |
| Clean | Finished character; only the selected control's silhouette outline | Draw handler |
| Controls | Handles for the \~10–15 controls at the current pick level; hover highlights the silhouette | Bone shapes + bone collections + draw handler |
| Slots | Control names and current drawing names, with override markers | `blf` labels anchored to bone heads |
| Sockets | Socket crosses and parent → child links; dormant controls greyed | `gpu` lines and points |
| Render Debug | Component outlines, order numbers, tile IDs, mask outlines, pool cards on tile 0 | Draw handler reading compiled props |

**Keeping it from becoming a forest of bones:**

- Put SOCKET, AFFINE and FLIP bones in a bone collection that's always hidden. Detail-level controls (iris, pupil) go in a collection shown only at Detail pick level.
- Bone shapes stay simple and stable: a ring around the head pivot, small rings on the eyes, a bar under the mouth. Custom shapes can't be swapped per frame, so they shouldn't try to match the drawing.
- Silhouettes come from the alpha copies already used for picking: trace a contour once per component at cache time, simplify it, store the polyline. The draw handler just transforms and strokes it, which is cheap.
- Use bone colors (per-bone palettes) by role: body controls, face controls, intent-only controls.

**Hover** needs mouse position, which a draw handler doesn't get. The Puppet Select tool's keymap can run a lightweight mouse-move handler, or a `GizmoGroup` with one gizmo per control can provide hover through its built-in hit-testing and simply draw the silhouette when highlighted. Prototype both; the gizmo route is less code.

Place the mode switch in the viewport header (a small enum popover), plus number-row shortcuts inside the Puppet Select tool's keymap.

## 8. Interaction map

The guiding rule: transforms stay native Blender; swapping is one hotkey away and keys itself. Hotkeys below are placeholders living in the Puppet Select tool's keymap, so they only apply while that tool is active and can be remapped.

| Action | Input | Result |
| --- | --- | --- |
| Select a part | Click artwork | Control at current pick level |
| Transform | G / R / S, I | Native; auto-key works |
| Swap drawing (browse) | Hotkey, e.g. Alt+D | Thumbnail popup, filtered (below); click keys an override at the current frame |
| Swap drawing (quick) | Hotkey + scroll, e.g. Alt+wheel | Steps through compatible drawings in place, live in the viewport; release keys it |
| Set expression | Pie menu | Keys the `expression` intent; every mouth and eye re-resolves |
| Set phoneme on mouth | Pie menu (mouth selected) | Keys `phoneme`, not a drawing |
| Switch construction | Pie or sidebar | Keys `construction` on the root |
| Inspect / fine-tune | Sidebar "Puppet" tab | Current drawing, construction, socket, overrides, locks, mask, order |
| Retime exposures | Dope Sheet, with name overlay | Native key moves; overlay shows names |
| Replace or redraw | Sidebar or browser button | The round-trip from the baseline |

**Browser filtering.** The popup's default query is the resolver's answer to "what could go here": same character and slot family, valid for the active construction, matching the current head angle (read from the parent head drawing's tags) and the current expression intent. Two tabs: **Fits** (strict) and **All in slot** (relaxed). Choosing from All in slot keys an override and shows a small warning badge in Slots mode.

**Override vs intent.** When the animator picks a mouth whose tags say "phoneme O, worried, 3Q", the popup offers a choice: key it as an override (this exact drawing) or as intent (phoneme O, so it re-resolves later). Default to intent when the tags make that unambiguous. That keeps lip sync editable after expressions change.

**Keying semantics.** The swap writes a constant key at the current frame, replacing any existing key there. The exposure holds until the next key, exactly like an X-sheet entry. Hover previews in the popup set a transient, unkeyed preview property, so they never touch undo history or the animation.

## 9. Leaving the viewing plane

The scale-compensated camera-ray offset is more powerful than the baseline used it for: it makes a card's depth a free parameter that doesn't change its image. That lets individual slots take part in real 3D occlusion without breaking the 2D model.

**Four kinds of depth, kept separate:**

| Kind | Decides | Owned by |
| --- | --- | --- |
| Screen-space draw order | Which component covers which, inside one character | Layer stack + overrides → `_c.order` (tiny ε steps) |
| Character-local pseudo-depth | Optional authored parallax between layers on camera moves | A style parameter, off by default |
| World-space anchor depth | Where the character plane sits in the scene; its parallax against the cockpit | Root anchor position |
| Occlusion with geometry | What's in front of or behind 3D objects | Per-slot depth breakout (below) + holdouts |

**Depth breakout.** Any control can carry a keyable `depth_offset` that moves its components along the camera ray by a real distance, with scale compensation. For the yoke:

- Body stays at the plane depth, behind the seat edge.
- Hoof gets `depth_offset` that puts it in front of the yoke for the frames it's resting there.
- On screen nothing changes; the depth buffer now says hoof in front of yoke, body behind seat edge. DOF treats the hoof at its new depth, which is usually what you want.

Its limit is large lateral camera moves. A compensated card still moves on screen as if it sat on the character plane, so a hoof "at" yoke depth will slide against the yoke as the camera trucks. For real contact during camera motion, switch that control to **world-anchored**: its position comes from a locator on the yoke, and the parent chain follows via IK or a constraint. That's the rare case; plane-locked is the default.

**Camera and character angles.**

- The character plane always faces the camera, so lateral camera moves never reveal the card's edge.
- Small yaw on the plane (up to roughly 10–15°) is an acceptable cheat for a character turning slightly away; beyond that, foreshortening reads as a flat cutout.
- Real turning is a drawing problem, and yes, it's an artistic responsibility: a different head angle or construction. The system's job is to make that visible, not automatic.

**Angle validity.** Tag each construction or angle drawing with the view-angle range it's valid for. The compiler computes, per frame, the angle between the camera ray and the character's authored facing, and marks frames where the exposed drawings fall outside their range as a red band in the timeline overlay. An optional resolver mode can feed that angle into the head-angle intent to pick turnaround drawings automatically during camera orbits, but it should stay opt-in.

## 10. Replay test, revised

Split the replay into two stages and run a feature census across many scenes, not just one. The two stages separate rendering bugs from data-model gaps; the census tells you which features are worth supporting at all.

**Stage A, flat replay.** Every leaf instance in the source becomes its own card with its baked world matrix, color transform and live mask per frame. No controls, slots or constructions. Diff against your renderer. This proves the render path: rasters, alpha, the mask shader, skew decomposition, depth ordering, color pipeline.

**Stage B, semantic replay.** Same shot, routed through controls, slots, sockets, constructions, layer stacks and clips. Diff against Stage A as well as your renderer. Any pixel that differs between A and B is a data-model gap, not a rendering bug.

**Render golden frames per subtree,** not only whole frames. Have your renderer output each semantic subtree (head, eye, mane) in isolation, so a mismatch points at a component rather than a whole frame.

### What to extract (the census)

For every instance on every frame of every scanned scene, record:

| Category | Fields | Answers |
| --- | --- | --- |
| Transform | Full matrix, decomposed scale/rotation/skew, determinant sign, transformation point vs registration point | How common is skew? Flips? Do pivots agree within a family? |
| Relative transform | Matrix relative to parent, grouped by parent's current frame | Socket (constant) vs control (varies), per section 6 |
| Symbol behavior | Type (graphic, movie clip, button), loop mode, first frame, resolved internal frame per parent frame | Which symbols need clips; any truly independent playback? |
| Masks | Mask layer → masked layers, nesting depth, mask transform relative to content over time | Bake vs live; is depth ever above 2? |
| Draw order | Per-frame order within each parent, order inversions between frames | How often do overrides happen, and where? |
| Co-movement | Instances with identical matrices on every frame from the same library family | Split outline and fill groupings (section 6) |
| Exposure | Library symbol swaps per layer per frame, hold lengths | Twos vs ones vs variable; mouth and eye swap rates |
| Color and effects | Color transform multipliers and offsets, alpha, blend modes, filters (blur, glow, drop shadow) | What the shader and comp must support |
| Tweens | Classic tweens and easing, shape tweens, frame-by-frame shapes | Shape tweens can't be swaps; how often do they occur? |
| Other | Bitmaps, gradients, text, strokes vs fills in one shape | Rasterizer and component-splitting edge cases |

**Output:** a census report ranking every feature by frequency across scenes, with links to occurrences (scene, frame, symbol path). Each feature then gets one of four decisions: support live, bake at raster time, approximate, or ignore. That table becomes the real feature spec, and every row is backed by actual show usage instead of speculation.

A useful scope for the census is your two characters across a few dozen scenes with dialogue, including some extreme poses and some head turns. That covers the cockpit shot's needs and stresses constructions, masks and lip sync where they're hardest.
