---
id: 025
title: Overlapping Regions Allowed
tags: [architecture, core]
created: 2026-04-19
updated: 2026-04-19
status: accepted
related: [002, 013, 014, 015, 024, 030]
---

# Overlapping Regions Allowed

Regions may share pixels. Dropping the disjoint-regions invariant is the central data-model change that makes the add/subtract edit model ([026](026-brush-edit-model.md)) feel natural and obsoletes the clip-at-neighbors rule ([021](superseded/021-vertex-edit-collision.md)).

Anchored by [030 — Polygons Are the Only Mask Truth](030-polygons-are-mask-truth.md): because polygons are canonical, overlap is simply "two polygons that happen to cover overlapping pixels." There is no unified pixel-label structure that needs to pick a winner — the winner is chosen at the moment of rendering or hit-testing.

## Contract

- **Polygons are canonical.** Each region is fully specified by its `label_id`, `name`, and ordered `vertices`. Everything mask-shaped is derived on demand.
- **Per-pixel membership is a multi-set.** A pixel may belong to zero, one, or many regions. There is no stored label map on disk and no single "owner" per pixel in persisted state or in-memory state.
- **Overlap is resolved at render/hit-test time, not in storage** ([002](002-state-management.md), [030](030-polygons-are-mask-truth.md)). The rule is *newest-on-top*: highest `label_id` wins. This is an algorithm applied to the polygon list, not a data invariant.

## Why

- Users naturally draw regions that touch, graze, or stack when lighting / focus / colony growth make boundaries ambiguous. Forcing disjointness required a constant clip rule, which made the editing UI silently steal pixels from neighbors during otherwise-innocent add strokes.
- The add/subtract stroke model ([026](026-brush-edit-model.md)) is a per-region operation; inter-region constraints don't belong in it.
- For training data, the preferred downstream format is a layered stack ([024](024-mask-export-deferred.md)) in which each layer is disjoint by construction. Overlap handling is solved at export time, not during annotation.

## Consequences

### Area semantics

`area_px` for a region = `masking.polygon_area(vertices)` — the mathematical enclosed area via the shoelace formula ([030](030-polygons-are-mask-truth.md), [014](014-lasso-tool.md)). Pixels shared with other regions are counted once *per region* (area is a property of the polygon, not of the pixel grid's multi-set membership). Sum of `area_px` across regions may exceed the image's pixel count. This is intentional and documented in the CSV description ([011](011-csv-for-area-output.md)).

### Click-select tiebreak

When a click lands on a pixel covered by multiple regions, the region with the highest `label_id` (most recently created) wins. Implementation: walk `regions` in descending `label_id` order; first polygon whose `cv2.pointPolygonTest(vertices, (x, y), False) >= 0` is the hit. No explicit z-order state; creation order is the z-order.

Future work could add cycle-through or user-settable z-order; both are additive to this rule.

### Rendering

Overlay rendering paints polygons in **ascending** `label_id` order with alpha-blend. The highest id lands last → wins visually. No stored "who owns this pixel" needed. In the GPU-tessellation renderer ([030](030-polygons-are-mask-truth.md)) each polygon is a separate `Mesh`; in the CPU-fallback renderer this becomes `cv2.fillPoly` calls in ascending id into the `label_map` texture.

### Brush edit "inside" check

A press-down's "is this pixel in region R?" test is polygon-based: `cv2.pointPolygonTest(regions[R]['vertices'], (x, y), False) >= 0`. No per-region cached mask needed. The add/subtract boolean op at commit time uses a transient bbox-local raster (see [026](026-brush-edit-model.md)) — not a stored mask, not shared with other regions.

### Bundle round-trip

`.bacmask` stores polygons, nothing else mask-related ([015](015-bacmask-bundle.md)). Overlap is preserved losslessly because the polygon list preserves every region independently. No mask reconciliation on load.

### Mask export

Raster export is a separate, headless operation ([024](024-mask-export-deferred.md)). The greedy layered packer splits regions across `mask_NN.npy` layers so that each layer is disjoint — the place where overlap turns into a pixel-exclusive format for training.

## Invariants that still hold

- **Monotonic `label_id`s**, never reused after delete ([014](014-lasso-tool.md)).
- **Deterministic rendering.** Same polygons + same creation order = bit-identical rendered overlay and bit-identical mask export output.
- **One polygon per region.** No multi-part polygons, no holes. A region that would need to be multi-part must be split into separate regions (each with its own `label_id`) via delete + redraw.

## Not in MVP

- Explicit z-order per region (we use creation order implicitly).
- User-visible overlap indicators (overlay alpha-blend density already hints at it).
- Merge-regions / subtract-one-from-another tools.

## Related

- [002 — State Management](002-state-management.md) — storage implications.
- [014 — Lasso Tool](014-lasso-tool.md) — primitive that creates overlapping polygons.
- [015 — .bacmask Bundle Format](015-bacmask-bundle.md) — polygon-only bundle.
- [021 — Edit Collision Policy (Clip)](superseded/021-vertex-edit-collision.md) — **superseded** by this note.
- [023 — Edit Mode & Region Boolean Edits](superseded/023-edit-mode-region-boolean-edits.md) — add/subtract stroke; no longer clips.
- [024 — Mask Export (deferred)](024-mask-export-deferred.md) — where overlap is resolved into layered disjoint masks.
- [026 — Brush Edit Model](026-brush-edit-model.md) — per-target editing; commit uses transient bbox raster.
- [030 — Polygons Are the Only Mask Truth](030-polygons-are-mask-truth.md) — anchor doctrine.
