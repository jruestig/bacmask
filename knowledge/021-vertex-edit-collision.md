---
id: 021
title: Vertex-Edit Collision Policy (Clip)
tags: [architecture, core]
created: 2026-04-17
status: accepted
related: [014, 022]
---

# Vertex-Edit Collision Policy: Clip

## Decision
When editing a region's vertices produces a polygon that would overlap pixels owned by another region, the new polygon is **clipped** — it rasterizes only into pixels that are either background or already owned by the region being edited.

Regions remain disjoint at all times.

## Behavior
Let `L` be the label map, `id` the region being edited, `P` the new polygon.

1. Compute the set of pixels inside `P` (via `cv2.fillPoly` into a temp mask).
2. Define the *allowed* mask: `allowed = (L == 0) | (L == id)` — background + self.
3. Zero out all existing pixels of `id` inside the union bbox of old+new polygons.
4. Assign `id` to pixels where `(inside_P) & allowed`.

Pixels owned by other regions are untouched. Adjacent regions keep their territory.

## Example
- Region 5 is a rectangle. Region 2 is a circle adjacent to it.
- User drags one of region 5's vertices across region 2.
- Result: region 5 takes on a notched shape that curves around region 2. Region 2 is unchanged.

## Alternatives considered
- **Overwrite.** New polygon wins; other regions silently lose pixels. Fast but surprising — breaks the "disjoint regions" invariant silently.
- **Reject.** Edit fails with an error. User must manually resolve before the drag can commit. Strictest; annoying during natural editing.
- **Clip (chosen).** Preserves disjoint invariant. Natural feel — edits affect the region you're editing, nothing else.

## Implementation notes
- Clip requires one additional `uint16` mask slice in the bbox region — negligible memory cost.
- Self-overlap within the same polygon still rasterizes per `cv2.fillPoly`'s even-odd rule. Clip only affects inter-region overlap.
- Bounding box must be **union of old and new polygon bboxes**, clamped to image bounds, so both the clear-old and fill-new operations are bounded per [004](004-performance-large-images.md).

## Related
- [014 — Lasso Tool & Boundary Editing](014-lasso-tool.md) — where vertex editing is introduced.
- [022 — Region Split Helper](022-region-split-helper.md) — post-MVP way to actively cut a region (different semantics from clip).
