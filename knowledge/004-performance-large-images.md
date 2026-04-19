---
id: 004
title: Performance on Large Images
tags: [perf, core, ui]
created: 2026-04-17
updated: 2026-04-19
status: accepted
related: [003, 008, 014, 020, 030]
---

# Performance on Large Images

Microscopy TIFFs in `images/` are ~20 MB with dimensions in the thousands per side. Naive implementation will stutter.

## Three rules

### 1. Display resolution ≠ computation resolution

- Canvas renders at widget resolution; large images downsample for display.
- Polygon vertex coordinates are always stored in **full source resolution**.
- Area is computed at polygon-math precision (shoelace over full-res vertices — see [030](030-polygons-are-mask-truth.md)).
- Lasso / brush sample coordinates are captured in display space, mapped to full-res space before being committed to a polygon.

### 2. Polygons are canonical; rasters are transient

- Per-region bool masks are **not stored**. Area is `polygon_area(vertices)` (shoelace, O(N) in vertex count). See [030](030-polygons-are-mask-truth.md).
- Rendering is either GPU tessellation (per-polygon `Mesh`) or a single CPU `label_map` texture rebuilt from polygons when `regions_version` bumps. Either way, there's at most one render artifact per polygon — never a persistent N·H·W mask pool.
- Brush commit uses a **transient bbox-local raster** (scratch bool crop over the stroke bbox) to run the boolean op + CC + contour cleanup; the raster is discarded once the new vertex list is extracted ([026](026-brush-edit-model.md)). Typical bbox is tiny vs. the full image.
- Undo snapshots are vertex lists, not mask copies ([003](003-undo-redo-commands.md)) — ~KB per snapshot instead of ~MB.

### 3. NumPy / OpenCV only

- All pixel operations vectorized. No Python `for y in range(h): for x in range(w):` loops.
- Use `cv2.fillPoly` for transient rasterization, `cv2.polylines` for the in-progress outline preview, `cv2.connectedComponents` for cleanup, `cv2.pointPolygonTest` for hit-testing without a label map, `cv2.resize` (nearest-neighbor) only where labels are involved.
- Catch yourself writing a pixel loop → stop, find the OpenCV/NumPy primitive.

## What used to live here

Earlier sessions documented a bbox-scoped `label_map` repaint + persistent overlay accumulator + per-region area cache ([029](superseded/029-incremental-overlay-and-area-cache.md), now superseded). That entire machinery existed to keep per-region masks in sync across commands. [030 — Polygons Are the Only Mask Truth](030-polygons-are-mask-truth.md) deleted the masks; the machinery is moot. Rendering costs drop to one polygon tessellation per changed region (GPU path) or one `fillPoly` per polygon on `regions_version` bump (CPU fallback).

## Why

- Responsive editing is non-negotiable for annotation UX.
- Memory footprint matters on larger images. Under the polygon-canonical doctrine, 1000 regions on a 20 MP image cost ~KB of vertex data — not the ~20 GB of bool masks the naive per-region approach would need.
- Android is post-MVP ([020](020-platform-scope.md)), but these rules cost nothing on desktop and pay for themselves when touch + constrained-memory devices land.

## Related

- [003 — Undo/Redo](003-undo-redo-commands.md) — vertex-only snapshots.
- [008 — Directory Layout](008-directory-layout.md) — `utils/image_utils.py`.
- [014 — Lasso Tool](014-lasso-tool.md) — shoelace area.
- [020 — Platform Scope](020-platform-scope.md).
- [029 — Incremental Overlay + Area Cache](superseded/029-incremental-overlay-and-area-cache.md) — superseded; the machinery it describes is no longer needed.
- [030 — Polygons Are the Only Mask Truth](030-polygons-are-mask-truth.md) — the doctrine this perf note follows.
