---
id: 014
title: Lasso Tool & Boundary Editing
tags: [architecture, core, ui]
created: 2026-04-17
updated: 2026-04-19
status: accepted
related: [002, 003, 013, 015, 016, 022, 023, 025]
---

# Lasso Tool & Boundary Editing

Primary (and only) mask-editing primitive in MVP. Replaces the brush/eraser/flood list from earlier drafts of [013 — Minimal Toolset](013-minimal-toolset.md).

## Draw flow
1. User press-drags to trace an outline. While dragging, the polyline renders on the overlay (not yet in the label map).
2. Path closes on **pointer release** — the last captured point is joined to the first and the polygon is committed.
3. **Enter** (bound to `close_lasso`) is an equivalent explicit-close trigger; useful for input devices that do not emit a clean release (e.g. stylus loss-of-contact) and in tests. It invokes the same close path.
4. On close, enclosed interior is rasterized (`cv2.fillPoly`) into the full-resolution label map with the next free label ID.
5. Lassos with fewer than 3 captured points are silently discarded on close — no region is created and nothing enters the history stack.

- Vertex coordinates are captured in display space, mapped to full-res space before the rasterization command runs ([004](004-performance-large-images.md)).
- `LASSO_CLOSE_THRESHOLD_PX` (default 10 px) remains in `config/defaults.py` as a reserved knob for a future "snap to start on proximity" preview affordance. It is **not** used as a close trigger in MVP — release is the trigger. Do not wire it in without revisiting this note.

## Edit flow (region boolean edits)
Boundary refinement happens in **Edit mode**. The user toggles it on (toolbar button / `e` hotkey), picks a target region, and draws a second lasso *against* that region. The start side decides add vs. subtract:

- Stroke starts **inside** target → the outside lobe is **added** to the region.
- Stroke starts **outside** target → the inside cut is **subtracted**.

Full semantics (boundary-crossing detection, multi-piece tie-break, discard rules, canonical vertex re-derivation) live in [023 — Edit Mode & Region Boolean Edits](023-edit-mode-region-boolean-edits.md). That note supersedes the handle-drag / insert-vertex / remove-vertex model sketched in earlier drafts of this file.

Area updates live as the mask changes — same as for the initial draw. (CSV is produced by the separate Export action, not by edits.)

### Collision with other regions
**Overlap is allowed** ([025](025-overlapping-regions.md)). An add-stroke can grow the target into pixels that other regions also claim; those pixels then belong to both. No clipping, no pixel theft. Overlap is resolved deterministically at mask-export time ([024](024-mask-export-deferred.md)), not during editing.

## Delete region
- Select region → invoke delete (toolbar button or `Delete` key).
- Mask pixels for that ID are zeroed. The region's entry disappears from the CSV.

## ID stability (load-bearing)
- IDs are assigned monotonically: 1, 2, 3, …
- Deleting region 2 does **not** shift later IDs down — the gap persists.
- `next_label_id` is persisted in the `.bacmask` bundle ([015](015-bacmask-bundle.md)) so reloading continues the sequence.
- Rationale: external references (notes, downstream scripts, the user's own memory) stay valid across sessions. Reassignment would silently corrupt that.

## Vertex persistence
- The **mask PNG** is the canonical training artifact.
- The **per-region vertex list** is persisted in the bundle's `meta.json` ([015](015-bacmask-bundle.md)). Without it, vertex editing after reload would require polygon recovery from the raster mask — lossy and imprecise.

## Commands (see [003](003-undo-redo-commands.md))
- `LassoCloseCommand(vertices, assigned_label_id)` — add region.
- `RegionEditCommand(label_id, old_vertices, new_vertices, old_mask_patch)` — modify boundary via an add/subtract stroke ([023](023-edit-mode-region-boolean-edits.md)).
- `DeleteRegionCommand(label_id, mask_patch, vertices, name)` — remove region; retains patch + vertices for undo.

## Granularity
- One lasso press→close = one command.
- One edit stroke press→release = one command.
- One delete = one command.

## Cancelling an in-progress lasso
- `Escape` discards the active polyline without closing. Nothing enters the history stack.

## Not in MVP
- Brush paint, eraser, flood fill, magic-wand, threshold select.
- Boolean ops between regions (union / subtract).
- Region merging by adjacency.
- Splitting one region into two — proposed in [022](022-region-split-helper.md); delete + redraw covers the case in MVP.

## Related
- [013 — Minimal Toolset](013-minimal-toolset.md) — updated scope lock.
- [003 — Undo/Redo](003-undo-redo-commands.md) — command structure.
- [015 — .bacmask Bundle](015-bacmask-bundle.md) — where vertex data persists.
- [016 — Input Abstraction Layer](016-input-abstraction.md) — gesture delivery.
- [023 — Edit Mode & Region Boolean Edits](023-edit-mode-region-boolean-edits.md) — full spec of the add/subtract stroke model.
- [025 — Overlapping Regions Allowed](025-overlapping-regions.md) — invariant change; no clip rule.
