---
id: 026
title: Brush Edit Model (Shift add / Ctrl subtract)
tags: [architecture, core, ui]
created: 2026-04-19
status: accepted
related: [002, 003, 013, 014, 016, 023, 025, 027]
---

# Brush Edit Model

Supersedes the lasso-based add/subtract stroke model in [023 — Edit Mode & Region Boolean Edits](superseded/023-edit-mode-region-boolean-edits.md). Boundary refinement now uses a GIMP-style brush with modifier keys for add vs. subtract. The old edit-mode toggle and boundary-crossing logic are removed.

## Why the pivot

The lasso-against-region stroke ([023](superseded/023-edit-mode-region-boolean-edits.md)) required the user to produce a shape that crossed the region boundary exactly twice — any other input (fewer crossings, wrong start side, press-drag that never entered the region) was silently discarded. In practice this confused users: strokes looked correct but committed nothing, and there was no visible per-pixel feedback. Brush painting is the idiom every user in this space (ImageJ, GIMP, Photoshop, QuPath) already knows.

## Tool model

Region-editing is now one explicit tool: **Brush**. The brush is a top-level tool on the toolbar alongside **Lasso** ([014](014-lasso-tool.md)). The previous "Edit mode toggle" is removed — there is no separate mode state; picking the brush is the mode.

- **Lasso** — creates new regions (press-drag-release on background).
- **Brush** — modifies existing regions (press-drag-release on/against a region).
- **Select tool** — pointer without either tool active; clicking a region sets `selected_region_id` for deletion / results-panel highlight (behavior unchanged).

Exactly one tool is active at a time; switching tools cancels any in-progress stroke.

## Brush stroke semantics

Press-drag-release with the brush tool active:

1. **Press-down** resolves the **target region** from the pixel under the cursor:
   - Resolve via the display `label_map` (highest-id wins on overlap, per [025](025-overlapping-regions.md)).
   - If the press-down pixel is background (no labeled region) → stroke is a **no-op**. The brush does not create new regions — that is the lasso's job. No history entry.
   - Otherwise the hit region is locked as the target for the entire stroke. Dragging across other regions does **not** re-target.
   - On successful resolution, `state.selected_region_id` is set to the target — the brush's target and the results-panel highlight / cyan outline are one and the same. This unifies "the region my next action will touch" with "the region I'm currently focused on."
2. **Modifier at press-down** decides add vs. subtract:
   - No modifier, or **Shift** → **add** (paint the brush stamp into `target_mask`).
   - **Ctrl** → **subtract** (erase the brush stamp from `target_mask`).
   - Holding both Shift+Ctrl → subtract (Ctrl wins, matches GIMP).
   - The modifier state is captured at press-down and held for the duration of the stroke; releasing or changing the modifier mid-drag does not switch mode.
3. **Drag** accumulates pointer samples. Each sample stamps a filled disc of radius `brush_radius_px` into the stroke's temp bool mask `S`.
   - Between samples, the disc is swept along the straight segment (`cv2.line` with `thickness = 2 * brush_radius_px`) so there are no gaps at fast cursor speeds.
   - `S` lives in the stroke buffer only; the stored region's mask is not touched until release.
4. **Release** commits:
   - `add`: `new_mask = target_mask | S`
   - `subtract`: `new_mask = target_mask & ~S`
   - If `new_mask == target_mask` (brush never intersected the target) → discard silently.
   - If subtract empties the region (`not new_mask.any()`) → fires a `DeleteRegionCommand` instead of a brush edit, same as [023](superseded/023-edit-mode-region-boolean-edits.md).
   - Otherwise commits a `BrushStrokeCommand(label_id, new_vertices, new_region_mask)`.
5. **Vertex re-derivation.** The canonical polygon for the stored region is re-derived from `new_mask` via `largest_connected_component` + `contour_vertices` (same pipeline as [close_lasso cleanup](014-lasso-tool.md)). Stored polygons are always simple closed curves tracing the filled region's real boundary.

## Brush size

A single scalar `brush_radius_px` (integer, pixels in full-resolution image space). Default `brush_radius_px = 8`. Range `[1, 100]`.

- **Control.** A slider exposed via a **popover that opens on click of the Brush toolbar button**. First click of the Brush button (when the brush is already active) opens the size popover; clicking outside or pressing Escape closes it. When the brush is not active, clicking the Brush button activates the tool *and* opens the popover in one shot — one click to both select the brush and set its size.
- Size is applied in **image-space pixels**, not display-space. Zooming in/out changes the on-screen footprint of the brush but not the pixel count painted.
- Size is session-local; not persisted to the bundle (same reasoning as edit-mode was in [023](superseded/023-edit-mode-region-boolean-edits.md)).

## Live preview

- During drag, render a ghost of the accumulated `S` mask as a semi-transparent fill in the add color (green) or subtract color (red) on top of the overlay. No Kivy `Line` preview — the preview *is* the temp mask being painted.
- Render a brush-cursor **circle** at the pointer position (radius `brush_radius_px`) at all times while the brush tool is active, even when not pressing, so the user sees the current footprint. The circle tints green when no modifier / Shift is held (add) and red when Ctrl is held (subtract) — live-tracking modifier state even before press-down.

## Escape / cancel

`Escape` during an in-progress brush stroke discards `S` and exits the stroke — no history entry. Same semantics as the lasso ([014](014-lasso-tool.md)); reuses the `cancel_lasso` action name in [016 — Input Abstraction](016-input-abstraction.md). (Renaming the action to `cancel_stroke` is cosmetic; defer.)

## Tool switching mid-stroke

If the user presses `L` while a brush stroke is in progress, or `B` while a lasso stroke is in progress, the **in-progress stroke continues on the tool it was started with** — the switch is queued and takes effect on the next press-down. No silent cancel.

Same applies to clicking the toolbar buttons: clicking Lasso or Brush while a stroke is in flight is absorbed or queued (implementation choice), but must never commit a cross-tool stroke.

Rationale: once a user has started drawing, their gesture is in motion; an accidental hotkey bump shouldn't discard work that's mid-flight. The stroke commits (or cancels via Escape) on its own terms, then the tool switch lands.

## Freed hotkey

The `e` keybinding previously invoked `toggle_edit_mode` ([023](superseded/023-edit-mode-region-boolean-edits.md)). With edit mode removed, `e` is **freed** — no binding. Do not repurpose it silently; leaving it unbound keeps discoverability honest (nothing the user tries accidentally "works").

## Delete-empties-region

Identical to [023](superseded/023-edit-mode-region-boolean-edits.md) step: subtract that empties the region fires a `DeleteRegionCommand` so the undo path, monotonic ID behavior, and CSV sync are unified with explicit delete.

## Overlap

Brush edits are strictly per-target. Painting into pixels that other regions also claim is allowed — those pixels belong to both regions (overlap preserved per [025](025-overlapping-regions.md)). No clipping, no pixel theft.

## Commands

One stroke → one command on the undo stack:

- `BrushStrokeCommand(label_id, new_vertices, new_region_mask)` — functionally equivalent to the retired `RegionEditCommand` in [023](superseded/023-edit-mode-region-boolean-edits.md). Stores the pre-edit `old_vertices` + `old_region_mask` for undo.
- `DeleteRegionCommand` — when a subtract empties the region.

## Validation & discard rules

Silent discard (no mask change, no history entry):

- Press-down on background (no target resolved).
- Brush stamp `S` never intersects `target_mask` (no-op).
- `new_mask == target_mask` after the boolean op.
- Stroke canceled via `Escape`.

## UI surface

Brush lives in the toolbar. Per [027 — Toolbar Hotkey Labels](027-toolbar-hotkey-labels.md) every button's shortcut is on its label:

- **Brush (B)** — activates brush tool. Clicking the button when the brush is already active opens the **size-slider popover** (see [Brush size](#brush-size)). Tooltip spells out modifier semantics: "Shift = add, Ctrl = subtract."
- Color-coded cursor circle makes mode obvious at a glance: green when add, red when subtract.
- The size popover is a lightweight floating panel anchored under the Brush button — slider `[1, 100]`, current value display, closes on outside-click or Escape.

## Not in MVP

- Variable-size brush via shortcut (`[` / `]`). Toolbar numeric field only.
- Pressure sensitivity (stylus). Future.
- Brush hardness / soft edges. Binary paint only.
- Multi-region paint (painting touches multiple regions in one stroke). Locked target only.
- Creating a new region via brush — still the lasso's job, per [013](013-minimal-toolset.md).

## Removed by this note

- **Edit mode toggle** (`e` hotkey, `state.edit_mode`, `MaskService.set_edit_mode` / `toggle_edit_mode`). Gone — tool selection replaces it.
- **Boundary-crossing detection** (`find_boundary_crossings`, P/Q truncation, `rasterize_stroke_polygon`). Gone — brush paints a raster patch directly.
- **Start-side heuristic** (press-down inside target → add, outside → subtract). Gone — modifier keys are explicit.
- **RegionEditCommand** — renamed to `BrushStrokeCommand` for clarity.

Implementation still needs to delete `find_boundary_crossings`, `rasterize_stroke_polygon`, `edit_region_stroke`, `state.edit_mode`, and the edit-mode toolbar button. Tracked under the toolbar overhaul.

## Related

- [014 — Lasso Tool](014-lasso-tool.md) — new-region creation, the other tool.
- [023 — Edit Mode & Region Boolean Edits](superseded/023-edit-mode-region-boolean-edits.md) — superseded model.
- [003 — Undo/Redo Commands](003-undo-redo-commands.md) — `BrushStrokeCommand`.
- [013 — Minimal Toolset](013-minimal-toolset.md) — scope lock updated for two primitives.
- [016 — Input Abstraction](016-input-abstraction.md) — modifier-key plumbing in `PointerDown`.
- [025 — Overlapping Regions Allowed](025-overlapping-regions.md) — per-target edit invariant.
- [027 — Toolbar Hotkey Labels](027-toolbar-hotkey-labels.md) — surfacing shortcuts in buttons.
