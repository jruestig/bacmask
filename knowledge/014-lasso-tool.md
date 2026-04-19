---
id: 014
title: Lasso Tool (region creation)
tags: [architecture, core, ui]
created: 2026-04-17
updated: 2026-04-19
status: accepted
related: [002, 003, 013, 015, 016, 022, 025, 026, 030]
---

# Lasso Tool (region creation)

One of two mask primitives in MVP ([013](013-minimal-toolset.md)). The lasso **creates** new regions. Editing an existing region's boundary is the job of the brush ([026](026-brush-edit-model.md)) — this note no longer covers that flow.

## Draw flow
1. User press-drags to trace an outline. While dragging, the polyline renders on the overlay (no commit yet).
2. Path closes on **pointer release** — the last captured point is joined to the first and the polygon is committed to `state.regions` with the next free `label_id`.
3. **Enter** (bound to `close_lasso`) is an equivalent explicit-close trigger; useful for input devices that do not emit a clean release (e.g. stylus loss-of-contact) and in tests. It invokes the same close path.
4. The polygon itself is canonical ([030](030-polygons-are-mask-truth.md)); no per-region mask is stored. Rendering and area are derived on demand.
5. Lassos with fewer than 3 captured points are silently discarded on close — no region is created and nothing enters the history stack.

- Vertex coordinates are captured in display space, mapped to full-res space before the rasterization command runs ([004](004-performance-large-images.md)).
- `LASSO_CLOSE_THRESHOLD_PX` (default 10 px) remains in `config/defaults.py` as a reserved knob for a future "snap to start on proximity" preview affordance. It is **not** used as a close trigger in MVP — release is the trigger. Do not wire it in without revisiting this note.

## Canonical vertex cleanup
On close, the raw stroke polygon is passed through a **transient** rasterize → `largest_connected_component` → `cv2.findContours(RETR_EXTERNAL, CHAIN_APPROX_NONE)` pipeline before being stored. The temporary bool mask is the smallest tool that produces a clean simple closed curve; it is thrown away the instant the contour is extracted — nothing about the stored region retains it ([030](030-polygons-are-mask-truth.md)). The result:

- Self-intersecting strokes commit only their largest lobe.
- The "implicit closing chord" from the user's release point back to the start is dissolved — the stored polygon traces the filled region's real outer boundary, not the raw scribble.
- Every stored vertex sits on the rasterized blob's edge, so the selected-region cyan outline is always a clean closed curve.

Live-UI feedback that landed this pass: pre-cleanup, releasing away from the start produced visually surprising filled shapes. The raster-then-recontour pipeline reliably kills that.

## Editing created regions
Not done here. Boundary refinement is the **brush** tool's job — see [026 — Brush Edit Model](026-brush-edit-model.md). The brush handles Create / Add / Subtract modes set in the brush panel and cycled with `Tab`. Overlap with other regions is allowed ([025](025-overlapping-regions.md)); no clipping.

Area recomputes live as regions change (it's `polygon_area(vertices)` — shoelace, O(N), sub-microsecond). CSV is produced by the separate Export action, not by edits.

## Area

`area_px = masking.polygon_area(vertices)` — mathematical enclosed area via the shoelace formula ([030](030-polygons-are-mask-truth.md)). Exact, float, no rasterization round-trip. Zero-area polygons (collinear / fewer than 3 vertices / duplicate points) are silently discarded on close and log a WARNING — `cv2.fillPoly` would still paint their boundary pixels, but the enclosed area is zero and nothing sensible exists to measure.

### CSV number shift (migrating from pre-030)

Older bundles and CSVs computed `area_px` as `mask.sum()` after `cv2.fillPoly` with the even-odd rule — the integer pixel count under that rasterization. Shoelace gives the true enclosed area in px² units. Differences are typically sub-1% for convex clean shapes; up to a few percent for thin or noisy boundaries. New CSVs are the mathematically correct number and supersede the old ones — re-export to refresh.

## Delete region
- Select region → invoke delete (toolbar button or `Delete` key).
- The polygon is removed from `state.regions`. The region's entry disappears from the CSV. `next_label_id` is unchanged (ID is not re-used).

## ID stability (load-bearing)
- IDs are assigned monotonically: 1, 2, 3, …
- Deleting region 2 does **not** shift later IDs down — the gap persists.
- `next_label_id` is persisted in the `.bacmask` bundle ([015](015-bacmask-bundle.md)) so reloading continues the sequence.
- Rationale: external references (notes, downstream scripts, the user's own memory) stay valid across sessions. Reassignment would silently corrupt that.

## Vertex persistence
- The **per-region vertex list** is the canonical representation ([030](030-polygons-are-mask-truth.md)) and persists in the bundle's `meta.json` ([015](015-bacmask-bundle.md)). Nothing else mask-shaped is stored — the mask export for training data is a separate, deferred operation ([024](024-mask-export-deferred.md)).

## Commands (see [003](003-undo-redo-commands.md))
- `LassoCloseCommand(vertices)` — add region. Stores only the vertex list; no mask snapshot.
- `BrushStrokeCommand(label_id, new_vertices)` — modify boundary via a brush stroke ([026](026-brush-edit-model.md)). Stores old + new vertex lists; no mask snapshot.
- `DeleteRegionCommand(label_id)` — remove region; retains the popped `name` + `vertices` for undo.

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
- [030 — Polygons Are the Only Mask Truth](030-polygons-are-mask-truth.md) — area via shoelace; commands store vertices only.
