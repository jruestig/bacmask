---
id: 021
title: Edit Collision Policy (Clip) (superseded)
tags: [architecture, core]
created: 2026-04-17
updated: 2026-04-19
status: superseded
related: [014, 022, 023, 025]
---

# Edit Collision Policy: Clip (superseded)

> **Superseded by [025 — Overlapping Regions Allowed](../025-overlapping-regions.md)** and the revised edit model in [026 — Brush Edit Model](../026-brush-edit-model.md) (which itself superseded [023 — Edit Mode & Region Boolean Edits](023-edit-mode-region-boolean-edits.md)).
> The disjoint-regions invariant has been dropped. Add-strokes no longer clip at neighbors; shared pixels are allowed. This note is retained for the reasoning trail.

## Decision (historical)
When an edit to a region would grow its mask into pixels owned by another region, the new pixels were **clipped** — the region only gained pixels that were background or already its own.

Regions remained disjoint at all times.

## Applies to
- Add-mode edit strokes ([023](023-edit-mode-region-boolean-edits.md)) that extend the target region into a neighbor's territory.
- Any future polygon-replace path that re-rasterizes a full region outline.

Subtract-mode strokes and Delete operations never *gain* pixels, so clipping is a no-op for them.

## Behavior
Let `L` be the label map, `id` the region being edited, `new_pixels` the set of pixels the edit proposes to assign to `id` (e.g. `target_mask ∪ S` for an add stroke).

1. Define the *allowed* mask: `allowed = (L == 0) | (L == id)` — background + self.
2. Zero out the region's existing pixels inside the edit's bounding box.
3. Assign `id` to pixels where `new_pixels & allowed`.

Pixels owned by other regions are untouched. Adjacent regions keep their territory.

## Example
- Region 5 is a rectangle. Region 2 is a circle adjacent to it.
- User adds a lobe to region 5 via an add stroke that loops around region 2.
- Result: region 5 takes on a notched shape that curves around region 2. Region 2 is unchanged.

## Alternatives considered
- **Overwrite.** New polygon wins; other regions silently lose pixels. Fast but surprising — breaks the "disjoint regions" invariant silently.
- **Reject.** Edit fails with an error. User must manually resolve before the drag can commit. Strictest; annoying during natural editing.
- **Clip (chosen).** Preserves disjoint invariant. Natural feel — edits affect the region you're editing, nothing else.

## Implementation notes
- Clip requires one additional `uint16` mask slice in the bbox region — negligible memory cost.
- Self-overlap within the same stroke polygon still rasterizes per `cv2.fillPoly`'s even-odd rule. Clip only affects inter-region overlap.
- Bounding box must be the **union of old target pixels and proposed new pixels**, clamped to image bounds, so both the clear-old and fill-new operations are bounded per [004](../004-performance-large-images.md).

## Related
- [014 — Lasso Tool](../014-lasso-tool.md) — where editing is introduced.
- [023 — Edit Mode & Region Boolean Edits](023-edit-mode-region-boolean-edits.md) — the add/subtract stroke model that once invoked this clip rule (also superseded).
- [022 — Region Split Helper](../022-region-split-helper.md) — post-MVP way to actively cut a region (different semantics from clip).
