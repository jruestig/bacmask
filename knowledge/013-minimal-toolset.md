---
id: 013
title: Minimal Toolset (MVP scope lock)
tags: [architecture, ui]
created: 2026-04-17
status: accepted
related: [000, 014]
---

# Minimal Toolset

## Decision
MVP ships with **one mask primitive**: the lasso / boundary-draw tool. See [014 — Lasso Tool & Boundary Editing](014-lasso-tool.md) for mechanics.

Supporting global actions:
- **Undo / redo** ([003](003-undo-redo-commands.md))
- **Delete region**
- **Save All** (bundle + CSV)
- **Load**
- **Calibration input** ([017](017-calibration-input.md))

That's it.

## Supersedes earlier draft
An earlier version of this note listed **brush + eraser + flood fill** as the three MVP tools. That was dropped once the tool model shifted to boundary-contour drawing: once a region's outline is closed, its interior is auto-filled and labeled. A brush is redundant in that workflow, and flood fill adds ambiguity without a clear win.

## Rationale

### One good primitive > three mediocre ones
Lasso + vertex editing covers initial outline, refinement, edge cleanup, and deletion. Done well, it handles every annotation case the MVP needs.

### Scope discipline protects the project
Every additional tool (threshold, watershed, brush, magic select, smart edge) pulls the product toward "general image editor" — which BacMask is explicitly **not**. Adding tools is a one-way door.

### Better tools can come later
Architecture permits adding watershed, threshold, or brush in v2 if observed annotation friction demands it. MVP's job is to prove the lasso workflow end-to-end.

## Explicitly NOT in MVP
- Brush paint
- Eraser
- Flood fill / magic wand
- Threshold / binarize
- Edge detection (Canny, Sobel)
- User-facing morphological operators
- Image adjustments (brightness, contrast, gamma)
- Boolean region operations
- Region splitting / merging by adjacency

## Related
- [014 — Lasso Tool & Boundary Editing](014-lasso-tool.md).
- [000 — Project Overview](000-project-overview.md) — scope anchor.
