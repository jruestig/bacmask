---
id: 014
title: Lasso Tool (region creation)
tags: [architecture, core, ui]
created: 2026-04-17
updated: 2026-04-19
status: accepted
related: [002, 003, 013, 015, 016, 022, 025, 026]
---

# Lasso Tool (region creation)

One of two mask primitives in MVP ([013](013-minimal-toolset.md)). The lasso **creates** new regions. Editing an existing region's boundary is the job of the brush ([026](026-brush-edit-model.md)) — this note no longer covers that flow.

## Draw flow
1. User press-drags to trace an outline. While dragging, the polyline renders on the overlay (not yet in the label map).
2. Path closes on **pointer release** — the last captured point is joined to the first and the polygon is committed.
3. **Enter** (bound to `close_lasso`) is an equivalent explicit-close trigger; useful for input devices that do not emit a clean release (e.g. stylus loss-of-contact) and in tests. It invokes the same close path.
4. On close, enclosed interior is rasterized (`cv2.fillPoly`) into the full-resolution label map with the next free label ID.
5. Lassos with fewer than 3 captured points are silently discarded on close — no region is created and nothing enters the history stack.

- Vertex coordinates are captured in display space, mapped to full-res space before the rasterization command runs ([004](004-performance-large-images.md)).
- `LASSO_CLOSE_THRESHOLD_PX` (default 10 px) remains in `config/defaults.py` as a reserved knob for a future "snap to start on proximity" preview affordance. It is **not** used as a close trigger in MVP — release is the trigger. Do not wire it in without revisiting this note.

## Canonical vertex cleanup
On close, the raw stroke polygon is passed through `largest_connected_component` + `cv2.findContours(RETR_EXTERNAL, CHAIN_APPROX_NONE)` before being stored. The result:

- Self-intersecting strokes commit only their largest lobe.
- The "implicit closing chord" from the user's release point back to the start is dissolved — the stored polygon traces the filled region's real outer boundary, not the raw scribble.
- Every stored vertex sits on the rasterized mask's edge, so the selected-region cyan outline is always a clean closed curve.

Live-UI feedback that landed this pass: pre-cleanup, releasing away from the start produced visually surprising filled shapes. The raster-then-recontour pipeline reliably kills that.

## Editing created regions
Not done here. Boundary refinement is the **brush** tool's job — see [026 — Brush Edit Model](026-brush-edit-model.md). The brush handles add (`Shift`-drag) and subtract (`Ctrl`-drag) on an existing region. Overlap with other regions is allowed ([025](025-overlapping-regions.md)); no clipping.

Area recomputes live as regions change, same as on initial draw. (CSV is produced by the separate Export action, not by edits.)

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
- `LassoCloseCommand(vertices, region_mask=clean_mask)` — add region. `region_mask` is the pre-cleaned bool mask; when present, apply uses it directly instead of re-rasterizing the vertices (avoids pixel drift on round-trip).
- `BrushStrokeCommand(label_id, new_vertices, new_region_mask)` — modify boundary via a brush stroke ([026](026-brush-edit-model.md)).
- `DeleteRegionCommand(label_id, mask_patch, vertices, name)` — remove region; retains patch + vertices for undo.

## Granularity
- One lasso press→close = one command.
- One brush stroke press→release = one command.
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
- [026 — Brush Edit Model](026-brush-edit-model.md) — the editing tool (replaces the old edit-mode stroke).
- [025 — Overlapping Regions Allowed](025-overlapping-regions.md) — invariant change; no clip rule.
