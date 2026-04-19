---
id: 022
title: Region Split Helper (post-MVP)
tags: [architecture, ui]
created: 2026-04-17
status: proposed
related: [014, 021]
---

# Region Split Helper

## Idea
A dedicated tool that slices an existing region across a user-drawn stroke, producing two sibling regions with new IDs — an alternative to "delete + redraw" when a region needs to be cut in two.

## Status
**Proposed. Not in MVP.** Captured to avoid losing the idea during the MVP build; revisit once lasso + vertex editing are in real use.

## Sketch of semantics
- User activates the split tool, then draws a stroke that crosses an existing region.
- The stroke acts as a cut-line: the region is split along it.
- Both resulting sub-regions get **new** label IDs (not the original ID + one new) — consistent with ID monotonicity ([014](014-lasso-tool.md)). The original ID is retired.
- Vertex lists for the two new regions are derived from the original polygon + the cut intersection points.

## Why it's post-MVP
- Need real user behavior to know if splits are common enough to warrant a dedicated tool.
- Delete + redraw covers the case today, at some UX cost.
- Requires non-trivial polygon-cut geometry (Sutherland–Hodgman or similar).

## Contrast with [021 — Clip](superseded/021-vertex-edit-collision.md)
- Clip is **defensive**: keeps regions from colliding during normal editing.
- Split is **active**: deliberately cuts one region into two.
- They don't conflict — both can coexist.

## Related
- [014 — Lasso Tool & Boundary Editing](014-lasso-tool.md).
- [021 — Vertex-Edit Collision Policy](superseded/021-vertex-edit-collision.md).
