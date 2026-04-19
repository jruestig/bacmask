---
id: 004
title: Performance on Large Images
tags: [perf, core, ui]
created: 2026-04-17
status: accepted
related: [003, 008, 014, 020, 029]
---

# Performance on Large Images

Microscopy TIFFs in `images/` are ~20 MB with dimensions in the thousands per side. Naive implementation will stutter.

## Three rules

### 1. Display resolution ≠ computation resolution
- Canvas renders a downsampled copy of the image (fit to widget).
- Label map is always kept at **full source resolution**.
- Area computation runs on the full-res label map — never on the downsampled view.
- Lasso vertex coordinates are captured in display space, mapped to full-res space before the rasterization command runs.

### 2. Lazy region rendering
- A lasso close or vertex edit touches a bounding box, not the whole image.
- Re-render only the changed region of the mask overlay texture — not the entire canvas.
- Undo/redo command patches are bounded by the same bounding box ([003](003-undo-redo-commands.md)).
- Implementation: [029 — Incremental Overlay Compositor + Per-Region Area Cache](029-incremental-overlay-and-area-cache.md) lays out the bbox-scoped label map repaint, persistent overlay accumulator, and `region_areas` cache that turn every edit path into O(bbox) rather than O(N·H·W). That note also lists future moves (sparse masks, bbox cache, ref-not-copy undo) if region counts keep climbing.

### 3. NumPy / OpenCV only
- All pixel operations vectorized. No Python `for y in range(h): for x in range(w):` loops.
- Use `cv2.fillPoly` for lasso interior fill, `cv2.polylines` for the in-progress outline preview, `cv2.connectedComponents` when needed for validation, `cv2.resize` (nearest-neighbor) only where labels are involved.
- Catch yourself writing a pixel loop → stop, find the OpenCV/NumPy primitive.

## Why
- Responsive editing is non-negotiable for annotation UX.
- Android is post-MVP ([020](020-platform-scope.md)), but these rules cost nothing on desktop and pay for themselves when touch lands.

## Related
- [003 — Undo/Redo](003-undo-redo-commands.md) — patch-based storage.
- [008 — Directory Layout](008-directory-layout.md) — `utils/image_utils.py`.
- [014 — Lasso Tool](014-lasso-tool.md).
- [020 — Platform Scope](020-platform-scope.md).
- [029 — Incremental Overlay Compositor + Area Cache](029-incremental-overlay-and-area-cache.md) — the concrete implementation of rule 2, plus rewrite hints.
