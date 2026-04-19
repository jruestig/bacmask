---
id: 029
title: Incremental Overlay Compositor + Per-Region Area Cache
tags: [perf, core, ui, services]
created: 2026-04-19
superseded_on: 2026-04-19
status: superseded
superseded_by: 030
related: [002, 003, 004, 025, 030]
---

> **Superseded by [030 — Polygons Are the Only Mask Truth](../030-polygons-are-mask-truth.md).**
>
> This note documented an O(bbox) compositor + `region_areas` cache layered on top of per-region `region_masks`. The underlying premise — that per-region masks and their summed areas must be stored and kept in sync — was itself the root of the complexity. [030](../030-polygons-are-mask-truth.md) deletes `region_masks` and `region_areas` entirely; area becomes shoelace, rendering walks polygons. The "rewrite hints" section of this note (sparse masks, bbox cache, ref-not-copy undo) is resolved by not storing masks in the first place. Kept here for reasoning trail.

# Incremental Overlay Compositor + Per-Region Area Cache

Session 7 perf pass. Adding the ~21st region stuttered; past 100 it was visibly slow. Three O(N) loops each fired on every edit and compounded into an O(N²) trajectory. This note documents the fix and lists what to do next if the region count keeps climbing.

## The three O(N·H·W) hot paths (before)

1. **Overlay texture rebuild** — `ImageCanvas._rebuild_overlay_texture` iterated every region on every `regions_version` bump, doing full-image float32 alpha-over compositing. At 2000×2000 + 25 regions that's ~100M ops per edit; at 100 regions it dominated the frame.
2. **Label-map full repaint** — every command called `masking.repaint_label_map`, which zeroed the whole `uint16` `label_map` and re-painted every region in ascending id order.
3. **`compute_area_rows`** — the results panel's data source summed every HxW bool mask on every refresh. At N=100 on 2000×2000 this was ~166 ms per add, a hidden O(N·H·W) cost in an "innocent" derived-data method.

A fourth, smaller cost was widget churn: `ResultsTable._refresh` did `clear_widgets()` + N fresh `_Row` widget creations each notify.

## Architecture now

### Bbox-scoped label-map repaint
- `masking.repaint_label_map_bbox(label_map, region_masks, bbox)` — half-open `(y0, y1, x0, x1)`. Zeroes the sub-rectangle and repaints only regions whose mask intersects it.
- `masking.mask_bbox(mask)` — O(H+W) axis reductions, cheap relative to rewriting the mask.
- `masking.union_bbox(a, b)` — half-open bbox union.
- Every `Lasso / Delete / VertexEdit / BrushStroke` command now passes the union bbox of (old_mask ∪ new_mask) and does no full-image repaint. `LassoCloseCommand.apply` skips the repaint entirely — the new region has the highest id so `label_map[mask] = id` is already correct on top.

### Persistent overlay accumulator
- `ImageCanvas` keeps `_overlay_acc_rgb` (H, W, 3) float32, `_overlay_acc_a` (H, W) float32, and `_overlay_rgba_buf` (H, W, 4) uint8 across edits.
- `_overlay_tracked: dict[int, np.ndarray]` — snapshot of last-composited masks (references, not copies). Next update diffs against this to classify ids as added / removed / changed.
- **Fast path (only additions, ids all above max tracked):** alpha-over the new region onto the accumulator inside its own bbox — typical "drew another lasso" case. O(bbox).
- **General path (removes, subtracts, shape edits):** zero the union bbox of every affected old + new mask, then re-composite only regions intersecting that bbox. O(N_intersecting · bbox).
- Texture is allocated once per image via `Texture.create`; subsequent updates `blit_buffer` the full RGBA buffer. No texture churn per edit.

### Per-region area cache
- `SessionState.region_areas: dict[int, int]` — lockstep with `region_masks`. Every command that swaps `region_masks[lid]` also writes `region_areas[lid] = int(new_mask.sum())`. `compute_area_rows` reads the cache — never sums an HxW mask.
- `MaskService.load_bundle` populates the cache once after rasterizing polygons.
- Invariant: **if you mutate `state.region_masks` directly, you must also update `state.region_areas`.** Two tests that poked masks directly were updated to maintain this.

### Incremental `ResultsTable`
- `self._rows: dict[int, _Row]` — per-region widget registry. Refresh diffs against it: remove widgets for deleted ids, create widgets only for new ids, mutate Label `.text` in place for kept ids if data changed.
- Selection-only notifies (arrow keys, canvas click-select) take a separate path: `_refresh_selection` just updates each `_Row._bg_color.rgba`. No widget teardown, no text churn.
- `_Row` retains its four `Label`s as attributes so updates don't re-traverse the widget tree.

## Measured wins (2000×2000 image)

| Op | Before | After (N≈100–150) | Speedup |
|---|---|---|---|
| Overlay composite, 30 adds | 8541 ms | 18 ms | ~480× |
| `LassoCloseCommand.apply` at N=100 | O(N·H·W), growing | ~2–4 ms flat | — |
| `compute_area_rows` at N=150 | 166 ms | 0.12 ms | ~1400× |
| Results panel per-add | N widget rebuilds | 1 widget add, O(1) text mutations | — |

Tests: 210 passing, ruff clean.

## Hints for a future rewrite

If the app ever needs to scale past a few hundred regions on large images, the current architecture still has O(N) factors in edit paths. The full-HxW bool mask per region is the main source of trouble — 100 masks × (2000×2000) = 400 MB just for the per-region masks.

### 1. Sparse per-region masks (biggest structural win)
- Store each region as `(bbox, mask_in_bbox)` instead of a full HxW bool. Memory drops from N·H·W to sum of individual bbox areas — typically 10–100× reduction.
- Every place that currently does `region_masks[lid][y0:y1, x0:x1]` becomes a bbox-intersect followed by a sub-slice inside the region's own coordinate frame.
- Non-trivial: touches `masking.py` helpers (`repaint_label_map_bbox`, `mask_bbox` become bbox-arithmetic only), commands, `MaskService.load_bundle`, and canvas `_composite_region_bbox` / `_recomposite_bbox`.
- Pays for itself once `N · mean_region_bbox² / (H · W)` drops below ~0.5 — i.e. when regions are small relative to the image.

### 2. Per-region bbox cache
- Already a natural byproduct of (1), but worth as a standalone step: `SessionState.region_bboxes: dict[int, tuple]` updated by commands.
- Lets `repaint_label_map_bbox` and `_recomposite_bbox` skip non-intersecting regions without a per-region `.any()` probe on a sub-slice. Turns their inner loop from O(N · bbox_area) into O(N_intersecting · bbox_area).

### 3. Drop defensive `old_mask.copy()` in commands
- `VertexEditCommand` and `BrushStrokeCommand` both copy the pre-edit mask into the command's undo snapshot. `state.region_masks[lid]` is only ever *replaced* with a fresh ndarray — never mutated in place — so the old reference is safe to retain without a copy.
- Saves ~4 MB + ~2 ms per edit on 2000×2000. Low risk if the invariant is documented in `002-state-management.md`.

### 4. Kivy `RecycleView` for `ResultsTable`
- The current incremental refresh handles hundreds of rows fine. If the list grows into thousands (unlikely for a colony-counting tool but possible for multi-image batches), replace the `BoxLayout` + `_Row` dict with a `RecycleView` + `ViewClass`. RecycleView only instantiates widgets for visible rows; off-screen rows are just data.

### 5. Partial texture upload
- `_blit_overlay_texture` currently uploads the full HxW RGBA buffer per edit. `Texture.blit_buffer(pos=(x, y), size=(w, h))` accepts a sub-rectangle — feed only the dirty bbox. Caveat: `flip_vertical` makes the coordinate math awkward; worth it only if profiling flags the blit as a bottleneck (it's GPU bandwidth, typically cheap).

### 6. Per-region cached RGBA layer
- Memoize each region's pre-multiplied RGBA tile at its bbox. Recomposites from cached layers instead of recomputing the color math. Memory cost is ~4× the sparse-mask cost (4 bytes/pixel vs. 1 bit). Only worth it if the composite math itself becomes hot, which it isn't today.

### Order of return-on-effort
1 ⟶ 2 ⟶ 3 are all one direction (sparse storage + bbox cache + ref-not-copy) and compose. 4–6 are situational and only if profiling points there.

## Related
- [002 — State Management](002-state-management.md) — `region_masks`, `region_areas`, `label_map` roles.
- [003 — Undo/Redo](003-undo-redo-commands.md) — command snapshot policy; a ref-not-copy move here would amend §"what a command stores."
- [004 — Performance on Large Images](004-performance-large-images.md) — the "lazy region rendering" rule this note operationalizes.
- [025 — Overlapping Regions](025-overlapping-regions.md) — the alpha-over order the compositor preserves.
