---
id: 023
title: Edit Mode & Region Boolean Edits
tags: [architecture, core, ui]
created: 2026-04-19
updated: 2026-04-19
status: superseded
supersededBy: 026
related: [002, 003, 013, 014, 025, 026]
---

# Edit Mode & Region Boolean Edits (SUPERSEDED)

> **Superseded by [026 — Brush Edit Model](../026-brush-edit-model.md) (2026-04-19).**
> Live-UI feedback: the lasso-against-region stroke was too restrictive — users produced strokes that looked correct but committed nothing because the two-boundary-crossing rule was violated (wrong start side, <2 crossings, or drag never entered the region). Replaced by a GIMP-style brush with explicit `Shift` (add) / `Ctrl` (subtract) modifiers. `state.edit_mode`, the `e` hotkey, `find_boundary_crossings`, `rasterize_stroke_polygon`, and `edit_region_stroke` are retired. `RegionEditCommand` is renamed to `BrushStrokeCommand`.
> The note below is preserved for historical context only — do **not** implement against it.

Replaces the handle-drag / insert-vertex / remove-vertex edit model sketched in the
first draft of [014 — Lasso Tool](../014-lasso-tool.md). Region boundaries are now
refined by drawing a second lasso *against* an existing region — start side decides
whether the stroke adds to or subtracts from the target.

Regions may overlap after an edit ([025](../025-overlapping-regions.md)); there is no
clip-at-neighbors rule. Edits are strictly per-target.

## Why

Handle dragging is finicky on dense colony outlines (many short segments, small
handles, pan/zoom interactions). A lasso-against-region gesture reuses the same
primitive users already know, needs no handle hit-testing, and composes with
neighbor-clipping ([021](021-vertex-edit-collision.md), also superseded) naturally.

## Edit mode toggle

An explicit **Edit** mode gates all region-editing strokes. The mode has two states:

- **OFF (default).** Canvas behaves as today: single tap inside a labeled region
  sets `selected_region_id`; press-drag on background starts a new-region lasso.
- **ON.** Single-click / double-click pick the *edit target*. Press-drag performs
  an edit stroke on the current target.

Toggle via a toolbar button and the `e` hotkey. The mode is a session-local UI
state; not persisted to the bundle.

## Targeting (edit mode ON)

- No target set → single click on a region sets it.
- Target set → single click on a *different* region does **not** retarget (it may
  be the start of a drag on the current target).
- **Double-click** on any region retargets to that region. Double-click on
  background clears the target.
- Cyan outline marks the current target — the same `selected_region_id` the
  results panel highlights. One slot, two uses ([002](../002-state-management.md)).

## Stroke semantics

Press-down at image pixel `(x0, y0)`:

- `target_binary_mask[y0, x0] == True` → **add** mode.
- Else → **subtract** mode.

"Inside the region" is defined strictly against the *target region's own binary
mask* (rasterized from its polygon) — **not** against the display label-map cache,
which under overlap resolves collisions to the newest region on top. Boundary
pixels resolve to whatever the rasterizer wrote there (typically background) —
that edge case falls into subtract mode, which is the safe default outside the
region.

## Boundary-crossing detection

Walk consecutive stroke samples. A *crossing* between samples `i` and `i+1` is:

```
target_binary_mask[sample_i] != target_binary_mask[sample_{i+1}]
```

Let `P` be the first crossing, `Q` the second. Subsequent crossings are ignored.
The stroke segment used for the edit is `samples[P..Q]` — the raw path between
the first exit/entry and the first re-entry/exit.

## Apply

Close the truncated stroke into a polygon by a straight line `Q → P`. Rasterize
to a binary mask `S` (`cv2.fillPoly`). Let `target_mask` be the target's current
binary mask (rasterized from its polygon).

- **add:** `new_mask = target_mask ∪ S`
- **subtract:** `new_mask = target_mask \ S`

No inter-region constraint is applied — other regions' masks are untouched.
If the target now covers pixels that other regions also cover, those pixels are
shared ([025](../025-overlapping-regions.md)). Overlap resolution happens at mask
export time ([024](../024-mask-export-deferred.md)), not during editing.

## Multi-piece results

Compute connected components of `new_mask` (8-connectivity). If more than one
component exists, keep the largest by pixel count. Ties resolved deterministically:
the component containing the pixel with the smallest `(y, x)` in raster-scan order
wins. This is unambiguous for any shape and avoids nondeterministic RNG, which
would violate the "same inputs → bit-identical `mask.png`" contract in CLAUDE.md.

## Validation & discard

The stroke is discarded silently (no mask change, no history entry) when:

- fewer than 3 captured samples,
- `P` not found (add: never exited; subtract: never entered),
- `Q` not found (stroke released before re-crossing the boundary),
- `new_mask == target_mask` (no-op),
- enclosed area of the closed stroke polygon is zero.

The stroke is treated as a **Delete** (fires `DeleteRegionCommand` instead) when:

- `new_mask` is empty — the subtract erased the entire region.

## Canonical vertex list

After `new_mask` is committed, re-derive the region's vertex list from the raster:

```
contours, _ = cv2.findContours(new_mask.astype(np.uint8),
                               cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_NONE)
vertices = contours[0][:, 0, :]   # outermost, pixel-accurate, no simplification
```

This guarantees the stored polygon is simple (non-self-intersecting) regardless
of how messy the user's stroke was. The raster is the source of truth; vertices
are re-derived. Re-editing later remains exact.

## Escape / cancel

`Escape` during an in-progress edit stroke discards it. Uses the existing
`cancel_lasso` action ([016 — Input Abstraction](../016-input-abstraction.md)); no
new action is needed.

## Leaving edit mode

Toggling Edit OFF clears the in-progress stroke (if any) but **keeps** the current
target in `selected_region_id` — the selection persists for the results-panel
highlight. Turning Edit back ON resumes with the same target.

## Commands

One stroke → one `RegionEditCommand(label_id, old_vertices, new_vertices,
old_mask_patch)` on the undo stack. Renames the obsolete `VertexEditCommand`.
See [003](../003-undo-redo-commands.md). The patch is stored per the bounding-box
rule of [004](../004-performance-large-images.md).

## Not in MVP

- Creating a new region via add-from-outside. (Add mode requires the start point
  to be inside the current target. New-region creation still happens only in
  OFF-mode press-drag on background.)
- Merging two regions into one. Use delete + redraw.
- Splitting one region into two — see [022](../022-region-split-helper.md).

## Related

- [014 — Lasso Tool](../014-lasso-tool.md) — primitive the edit mode reused.
- [002 — State Management](../002-state-management.md) — target lives in
  `selected_region_id`; no new state slot.
- [003 — Undo/Redo Commands](../003-undo-redo-commands.md) — `RegionEditCommand`
  (now renamed `BrushStrokeCommand`).
- [013 — Minimal Toolset](../013-minimal-toolset.md) — edit is no longer a *mode*
  of the lasso primitive; the brush ([026](../026-brush-edit-model.md)) is a
  second tool.
- [025 — Overlapping Regions Allowed](../025-overlapping-regions.md) — invariant
  change; explains why no clip rule applies.
- [026 — Brush Edit Model](../026-brush-edit-model.md) — successor.
