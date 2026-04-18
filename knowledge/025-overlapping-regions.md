---
id: 025
title: Overlapping Regions Allowed
tags: [architecture, core]
created: 2026-04-19
status: accepted
related: [002, 013, 014, 015, 021, 023, 024]
---

# Overlapping Regions Allowed

Regions may share pixels. Dropping the disjoint-regions invariant is the central data-model change that makes the add/subtract edit model ([023](023-edit-mode-region-boolean-edits.md)) feel natural, and obsoletes the clip-at-neighbors rule ([021](021-vertex-edit-collision.md)).

## Contract

- **Polygons are canonical.** Each region is fully specified by its `label_id`, `name`, and ordered `vertices`. Everything else is derived.
- **Per-pixel membership is a multi-set.** A pixel may belong to zero, one, or many regions. There is no uint16 label map on disk; there is no single "owner" per pixel in persisted state.
- **In-memory, rendering and hit-testing use a derived display cache** ([002](002-state-management.md)). Collisions in the cache resolve by highest `label_id` (newest on top) — a display choice, not a data claim.

## Why

- Users naturally draw regions that touch, graze, or stack when lighting / focus / colony growth make boundaries ambiguous. Forcing disjointness required a constant clip rule, which made the editing UI silently steal pixels from neighbors during otherwise-innocent add strokes.
- The add/subtract stroke model ([023](023-edit-mode-region-boolean-edits.md)) is a per-region operation; inter-region constraints don't belong in it.
- For training data, the preferred downstream format is a layered stack ([024](024-mask-export-deferred.md)) in which each layer is disjoint by construction. Overlap handling is solved at export time, not during annotation.

## Consequences

### Area semantics
`area_px` for a region = count of pixels inside its own rasterized polygon. Pixels shared with other regions are counted once *per region*. Sum of `area_px` across regions may exceed the image's pixel count. This is intentional and documented in the CSV description ([011](011-csv-for-area-output.md)).

### Click-select tiebreak
When a click lands on a pixel shared by multiple regions, the region with the highest `label_id` (most recently created) wins. Deterministic, predictable, no extra state. Future work could add cycle-through or explicit z-order; both are additive.

### Edit-mode "inside" check
`label_map[y, x] == target_id` is no longer valid when the label map is a display cache with collision resolution. The correct check is against the *target region's own binary mask*: `target_binary_mask[y, x]`. Implementations must raster the target polygon (or keep its rasterization cached) and query that mask.

### Bundle round-trip
`.bacmask` stores polygons, nothing else mask-related ([015](015-bacmask-bundle.md)). Overlap is preserved losslessly because the polygon list preserves every region independently. No mask reconciliation on load.

### Mask export
Raster export is a separate, headless operation ([024](024-mask-export-deferred.md)). The greedy layered packer splits regions across `mask_NN.npy` layers so that each layer is disjoint — the place where overlap turns into a pixel-exclusive format for training.

## Invariants that still hold

- **Monotonic `label_id`s**, never reused after delete ([014](014-lasso-tool.md)).
- **Deterministic rasterization.** Same polygons + same ordering = bit-identical derived masks (in memory cache, export output).
- **One polygon per region.** No multi-part polygons, no holes. A region that would need to be multi-part must be split into separate regions (each with its own `label_id`) via delete + redraw.

## Not in MVP

- Explicit z-order per region (we use creation order implicitly).
- User-visible overlap indicators (overlay blending density already hints at it).
- Merge-regions / subtract-one-from-another tools.

## Related

- [002 — State Management](002-state-management.md) — storage implications.
- [014 — Lasso Tool & Boundary Editing](014-lasso-tool.md) — primitive that can now create overlapping strokes.
- [015 — .bacmask Bundle Format](015-bacmask-bundle.md) — polygon-only bundle.
- [021 — Edit Collision Policy (Clip)](021-vertex-edit-collision.md) — **superseded** by this note.
- [023 — Edit Mode & Region Boolean Edits](023-edit-mode-region-boolean-edits.md) — add/subtract stroke; no longer clips.
- [024 — Mask Export (deferred)](024-mask-export-deferred.md) — where overlap is resolved into layered disjoint masks.
