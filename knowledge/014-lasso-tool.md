---
id: 014
title: Lasso Tool & Boundary Editing
tags: [architecture, core, ui]
created: 2026-04-17
status: accepted
related: [002, 003, 013, 015, 016, 021, 022]
---

# Lasso Tool & Boundary Editing

Primary (and only) mask-editing primitive in MVP. Replaces the brush/eraser/flood list from earlier drafts of [013 — Minimal Toolset](013-minimal-toolset.md).

## Draw flow
1. User press-drags to trace an outline. While dragging, the polyline renders on the overlay (not yet in the label map).
2. Path closes when either:
   - The live endpoint reaches within **ε pixels** of the starting point → auto-close.
   - The user presses **Enter** (or the configured `close_path` action) → snap last→first.
3. On close, enclosed interior is rasterized (`cv2.fillPoly`) into the full-resolution label map with the next free label ID.

- ε is configurable via `config.yaml`. Default: 10 px in display space.
- Vertex coordinates are captured in display space, mapped to full-res space before the rasterization command runs ([004](004-performance-large-images.md)).

## Edit flow (vertex editing)
1. Click on an existing region's boundary → vertex handles appear.
2. Drag a handle → vertex moves. On release, the polygon is re-rasterized into the mask using **the same label ID**.
3. Insert vertex: double-click on a segment.
4. Remove vertex: double-click on a handle.
5. Area/CSV updates live as the mask changes.

### Collision with other regions
If the edited polygon would overlap pixels owned by another region, the new polygon is **clipped** — it only fills background pixels or its own former pixels. Adjacent regions keep their territory. See [021 — Vertex-Edit Collision Policy](021-vertex-edit-collision.md).

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
- `VertexEditCommand(label_id, old_vertices, new_vertices)` — modify boundary.
- `DeleteRegionCommand(label_id, mask_patch, vertices, name)` — remove region; retains patch + vertices for undo.

## Granularity
- One lasso press→close = one command.
- One vertex drag press→release = one command.
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
