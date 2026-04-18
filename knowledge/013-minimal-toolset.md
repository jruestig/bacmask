---
id: 013
title: Minimal Toolset (MVP scope lock)
tags: [architecture, ui]
created: 2026-04-17
updated: 2026-04-19
status: accepted
related: [000, 014, 023]
---

# Minimal Toolset

## Decision
MVP ships with **one mask primitive**: the lasso / boundary-draw tool. See [014 — Lasso Tool & Boundary Editing](014-lasso-tool.md) for mechanics.

The lasso operates in two *modes* of the same gesture (press-drag-release):

- **Create.** Default mode. Stroke on background becomes a new region.
- **Edit.** Toggled via a dedicated Edit button (or `e`). Stroke on/against an existing target region adds or subtracts pixels via the add/subtract rule in [023](023-edit-mode-region-boolean-edits.md).

This is still one primitive, not two tools — the gesture, the input abstraction ([016](016-input-abstraction.md)), and the rasterization path are shared. Only the outcome differs based on mode + start side.

Supporting global actions:
- **Undo / redo** ([003](003-undo-redo-commands.md))
- **Delete region**
- **Save** — writes the `.bacmask` bundle only ([015](015-bacmask-bundle.md)). No masks, no CSV.
- **Export** — writes the sibling areas CSV ([011](011-csv-for-area-output.md)). Separate button, user-invoked.
- **Load** — reads a `.bacmask` bundle.
- **Calibration input** ([017](017-calibration-input.md))
- **Edit mode toggle** ([023](023-edit-mode-region-boolean-edits.md))

Mask export for training-data use is deferred and lives outside the UI entirely ([024](024-mask-export-deferred.md)).

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
