---
id: 026
title: Brush Edit Model (Create / Add / Subtract)
tags: [architecture, core, ui]
created: 2026-04-19
updated: 2026-04-19
status: accepted
related: [002, 003, 013, 014, 016, 023, 025, 027, 030]
---

# Brush Edit Model

Supersedes the lasso-based add/subtract stroke model in [023 — Edit Mode & Region Boolean Edits](superseded/023-edit-mode-region-boolean-edits.md). Region boundary refinement (and now also new-region creation) uses a GIMP-style brush whose mode is a persistent toolbar setting cycled with **Tab**.

## History

This note has iterated across the same session as it was implemented. Earlier drafts proposed:

1. **Modifier-key model** (`Shift` = add, `Ctrl` = subtract). Dropped after live use — modifier resolution at press-down through Kivy's `Window.modifiers` was fragile and the gesture was harder to teach than a persistent toggle. Replaced by the brush-panel toggles + Tab cycle.
2. **Brush-only-edits invariant** (the brush could not create regions; that was the lasso's exclusive job). Dropped when **Create** mode was added — the brush now subsumes "paint a blob into a new region" alongside add/subtract editing.
3. **Click-on-region required at press-down for add/subtract** (a press on background was a no-op). Dropped in favor of the **selection lock** below — the press-down location no longer needs to hit the target region, which made subtract-from-outside (carving from the empty pixels next to the boundary) work.

What follows describes the current accepted model.

## Why a brush at all

The lasso-against-region stroke ([023](superseded/023-edit-mode-region-boolean-edits.md)) required the user to produce a shape that crossed the region boundary exactly twice — any other input was silently discarded. In practice this confused users: strokes looked correct but committed nothing, and there was no per-pixel feedback. Brush painting is the idiom every user in this space (ImageJ, GIMP, Photoshop, QuPath) already knows.

## Tool model

Region-editing is one explicit tool: **Brush**. The brush is a top-level tool on the toolbar alongside **Lasso** ([014](014-lasso-tool.md)). Picking the brush is the mode — there is no separate edit-mode toggle.

- **Lasso (`L`)** — outline-trace creation tool ([014](014-lasso-tool.md)).
- **Brush (`B`)** — three-mode painting tool. See "Brush mode" below.

Exactly one tool is active at a time. Tool switching mid-stroke does not interrupt the in-flight stroke (it commits or cancels on its own terms); the switch lands on the next press-down.

## Brush mode

`state.brush_default_mode: Literal["create", "add", "subtract"]` is the persistent default. It is read at press-down and held for the entire stroke; flipping the toggle mid-stroke does not retarget the in-flight stroke.

Modes:

- **Create** — press-drag-release commits a brand-new region built from the painted blob (LassoCloseCommand under the hood). Press-down location is irrelevant beyond seeding the first stamp; the target-resolution rule below does **not** apply, and the user's existing selection is left unchanged so they can flip between create and add/subtract on the same focus region.
- **Add** — paint extends the locked target region (`new_mask = target | S`).
- **Subtract** — paint removes pixels from the locked target (`new_mask = target & ~S`). Subtract that empties the region resolves as a delete (see [Delete-empties-region](#delete-empties-region)).

Mode is set by the toggle buttons in the [brush panel](#ui-surface) and cycled with **Tab** in the order `create → add → subtract → create`. There is **no modifier-key override**: the toggle is the mode.

## Press-down target resolution (add / subtract only)

For add and subtract modes, press-down resolves the **target region** in this priority order:

1. If the pressed pixel hits an existing region in `label_map` (highest-id wins on overlap, per [025](025-overlapping-regions.md)), that region becomes the target *and* `state.selected_region_id` is set to it. Tapping another region re-targets the brush.
2. Otherwise (background or out-of-bounds press-down) the existing `state.selected_region_id` is the target. The brush is **locked to the selected region** — this is what lets a subtract stroke begin on the empty pixels next to the boundary and carve a bite into the region from outside in. Without the lock the user would have to start every subtract from inside the region, making thin slices off the edge awkward.
3. If neither the pressed pixel nor the selection resolves to an existing region → stroke is a **no-op**. No history entry.

Once resolved the target is locked for the entire stroke. Dragging across other regions or off the canvas does **not** re-target.

The brush's target and the results-panel highlight / cyan outline are the same id — "the region my next action will touch" is the same as "the region I'm currently focused on."

## Drag

Drag accumulates pointer samples. Each sample stamps a filled disc of radius `brush_radius_px` into the stroke's temp bool mask `S`.

- Between samples, the disc is swept along the straight segment (`cv2.line` with `thickness = 2 * brush_radius_px + 1`) so there are no gaps at fast cursor speeds.
- Round caps are added with explicit disc stamps at both endpoints.
- `S` lives in the stroke buffer only; the stored region's mask is not touched until release.
- The stroke bbox is tracked incrementally as samples are stamped (in `BrushStroke.bbox`), so the commit path doesn't need a full `np.where(S)` pass on a multi-megapixel image.

## Release

Release commits per mode. The commit path uses **transient, bbox-local rasters** — no per-region mask is ever written to state ([030](030-polygons-are-mask-truth.md)). The rasters exist for the duration of a single commit (microseconds) and are discarded once the new vertex list has been extracted.

- **Create**: `largest_connected_component(S[bbox])` → `contour_vertices` → translate back to image-space → `LassoCloseCommand(new_vertices)`.
- **Add / Subtract**: rasterize the target polygon **only within the stroke bbox** (or the union bbox for add, when the stroke extends past the target) into a scratch bool crop `T`. Boolean op: `N = T | S_crop` (add) or `T & ~S_crop` (subtract). If `N == T` (no pixels changed), discard the stroke — no-op. Otherwise `largest_connected_component(N)` → `contour_vertices` → translate back → `BrushStrokeCommand(label_id, new_vertices)`. Only the vertex list is committed; the scratch crops are thrown away.
- **Subtract that empties the target**: if `N` has no surviving True pixels, fire a `DeleteRegionCommand(label_id)` instead — same code path as explicit delete, so undo + monotonic-id behavior stay unified.

Every post-edit vertex list runs through `largest_connected_component` + `contour_vertices` on the scratch crop. Stored polygons are simple closed curves tracing the edit result's real boundary — same pipeline as [close_lasso cleanup](014-lasso-tool.md).

## Brush size

A single scalar `brush_radius_px` (integer, pixels in full-resolution image space). Default 8, range `[1, 100]`. Set via the slider + numeric input in the [brush panel](#ui-surface). Image-space — zoom changes the on-screen footprint but not the pixel count painted. Session-local; not persisted.

## Live preview

Drawn directly with Kivy graphics primitives (no per-move full-image RGBA blit). On press-down the canvas seeds a `_brush_preview_pts` list in image-space; each `PointerMove` appends a point. `_repaint` renders one `Line` (cap=round, joint=round) of width `radius_widget` through those points. A single draw call regardless of stroke length.

A brush-cursor circle (image-space radius mapped to widget pixels) is also drawn at the pointer position whenever the brush tool is active, even between strokes, so the user can see the current footprint and mode color before pressing.

Color coding (knowledge/026):
- Add → green (`(0.2, 1.0, 0.2)`).
- Subtract → red (`(1.0, 0.2, 0.2)`).
- Create → blue (`(0.3, 0.6, 1.0)`).

## Escape / cancel

`Escape` during an in-progress brush or lasso stroke fires the `cancel_stroke` action which discards the in-flight buffer with no history entry. (Old `cancel_lasso` action name was renamed to `cancel_stroke` to reflect the dual use.)

## Tool switching mid-stroke

Pressing `L` while a brush stroke is in progress, or `B` while a lasso stroke is in progress: the in-progress stroke continues on the tool it was started with — the switch is queued and takes effect on the next press-down. No silent cancel.

Same applies to clicking the toolbar buttons. Rationale: once a user has started drawing, their gesture is in motion; an accidental hotkey bump shouldn't discard work that's mid-flight.

## Freed hotkeys

- `e` (was `toggle_edit_mode`) — freed, no binding. Kept honest: leaving it unbound means nothing the user types accidentally "works."
- `Shift` / `Ctrl` modifiers (were add/subtract overrides) — no longer special-cased. The Add/Subtract toggles + Tab are the only way to set the mode.

## Commands

One stroke → one command on the undo stack. Commands store vertex lists only; there are no mask fields ([030](030-polygons-are-mask-truth.md)):

- `LassoCloseCommand(vertices)` — fired by create mode (and the lasso tool).
- `BrushStrokeCommand(label_id, new_vertices)` — fired by add/subtract. Stores `_old_vertices` for undo.
- `DeleteRegionCommand(label_id)` — when a subtract empties the region. Stores the popped `name` + `vertices` for undo.

## Validation & discard rules

Silent discard (no mask change, no history entry):

- Add/subtract press on background with no selected region (no target resolved).
- Stamp `S` is empty (degenerate stroke).
- Add: every painted pixel was already inside the target.
- Subtract: brush never touched any target pixel.
- Create: the cleaned CC is empty or its contour has fewer than 3 vertices.
- Stroke canceled via `Escape`.

## UI surface

- The **Brush (B)** toolbar button activates the tool.
- A separate **brush panel** appears beneath the toolbar only while the brush is active, sized to match the toolbar height. Layout, left → right: `Brush size` label · numeric input · slider · `Create (Tab)` toggle · `Add (Tab)` toggle · `Subtract (Tab)` toggle. Reuses the same `BrushPanel` widget instance across tool switches so size + mode persist.
- The Tab hotkey (action `toggle_brush_mode`) cycles the three modes in the order shown in the panel.

The earlier popover-on-button-click design was dropped in favor of this inline panel — easier to discover and doesn't disappear when the user moves the mouse.

## Performance

The commit path is bbox-restricted: connected-component analysis and contour re-derivation run on the cropped post-edit mask, not the full image. On a 16 MP image with a small region the commit takes ~60 ms (down from a multi-second timeout pre-optimization). The live preview costs one Kivy `Line` draw per `_repaint`. The `ResultsTable` widget gates its rebuild on `regions_version` so brush-stroke notifies don't rebuild every row each `PointerMove`.

## Not in MVP

- Variable-size brush via shortcut (`[` / `]`). Toolbar slider only.
- Pressure sensitivity (stylus). Future.
- Brush hardness / soft edges. Binary paint only.
- Multi-region paint (one stroke editing multiple regions). Locked target only.

## Removed by this note

- **Edit mode toggle** (`e` hotkey, `state.edit_mode`, `MaskService.set_edit_mode` / `toggle_edit_mode`). Tool selection replaces it.
- **Boundary-crossing detection** (`find_boundary_crossings`, P/Q truncation, `rasterize_stroke_polygon`). Brush paints a raster patch directly.
- **Start-side heuristic** (press-down inside target → add, outside → subtract). Replaced by the explicit mode toggle.
- **RegionEditCommand** — renamed to `BrushStrokeCommand`.
- **Modifier overrides** (`Shift` / `Ctrl` at press-down). Replaced by the toggle + Tab.
- **`PointerDown.modifiers` field** and the `Window.modifiers` plumbing in `DesktopInputAdapter`. No longer needed.
- **"Brush cannot create" invariant.** Create mode is the new third option.

## Related

- [014 — Lasso Tool](014-lasso-tool.md) — outline-trace creation, the other tool.
- [023 — Edit Mode & Region Boolean Edits](superseded/023-edit-mode-region-boolean-edits.md) — superseded model.
- [003 — Undo/Redo Commands](003-undo-redo-commands.md) — `BrushStrokeCommand` (vertex-only snapshots).
- [013 — Minimal Toolset](013-minimal-toolset.md) — scope lock.
- [016 — Input Abstraction](016-input-abstraction.md) — semantic events + keybindings.
- [025 — Overlapping Regions Allowed](025-overlapping-regions.md) — per-target edit invariant.
- [027 — Toolbar Hotkey Labels](027-toolbar-hotkey-labels.md) — labels and the Tab cycle.
- [030 — Polygons Are the Only Mask Truth](030-polygons-are-mask-truth.md) — commit uses transient bbox raster; no per-region mask stored.
