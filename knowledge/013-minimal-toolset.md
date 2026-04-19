---
id: 013
title: Minimal Toolset (MVP scope lock)
tags: [architecture, ui]
created: 2026-04-17
updated: 2026-04-19
status: accepted
related: [000, 014, 026, 027]
---

# Minimal Toolset

## Decision
MVP ships with **two mask primitives**:

- **Lasso** — creates new regions. Press-drag-release on background; closes on release. See [014 — Lasso Tool](014-lasso-tool.md).
- **Brush** — modifies existing regions. Press-drag-release on the region to edit, with `Shift` to add paint and `Ctrl` to subtract. See [026 — Brush Edit Model](026-brush-edit-model.md).

Exactly one of these is active at a time. The user switches via the toolbar or hotkey (`L` for lasso, `B` for brush). There is **no separate edit-mode toggle** — tool selection is the mode. The old lasso-against-region edit gesture from [023 — Edit Mode & Region Boolean Edits](superseded/023-edit-mode-region-boolean-edits.md) is superseded.

Supporting global actions:
- **Undo / redo** ([003](003-undo-redo-commands.md))
- **Delete region**
- **Save** — writes the `.bacmask` bundle only ([015](015-bacmask-bundle.md)). No masks, no CSV.
- **Export** — writes the sibling areas CSV ([011](011-csv-for-area-output.md)). Separate button, user-invoked.
- **Load** — reads an image or a `.bacmask` bundle. Double-click on a file opens it ([028](028-file-picker-double-click.md)).
- **Calibration input** ([017](017-calibration-input.md))

Every button surfaces its keyboard shortcut in its label ([027](027-toolbar-hotkey-labels.md)).

Mask export for training-data use is deferred and lives outside the UI entirely ([024](024-mask-export-deferred.md)).

That's it.

## Supersedes earlier drafts
- **Draft 1 (2026-04-17):** brush + eraser + flood fill as the three MVP tools. Dropped when the model shifted to boundary-contour drawing.
- **Draft 2 (2026-04-19):** lasso-only, with an "edit mode" toggle that reused the lasso gesture for add/subtract stroke edits ([023](superseded/023-edit-mode-region-boolean-edits.md)). Dropped after live-UI feedback: the two-boundary-crossings requirement silently discarded too many user strokes.
- **Current (2026-04-19):** lasso for create, brush for edit. The brush is back — but only for editing existing regions, not creating them. New-region creation is still lasso-only ([026](026-brush-edit-model.md)).

## Rationale

### Two primitives, one job each
Lasso handles "I'm outlining a new colony" — a continuous-trace gesture. Brush handles "I need to nudge this boundary a bit" — a per-pixel painting gesture. Trying to stuff both jobs into one gesture (lasso-against-region in [023](superseded/023-edit-mode-region-boolean-edits.md)) conflated them and confused users. Two explicit tools are clearer than one overloaded one.

### Brush is *only* for edits
The brush cannot create a region — painting onto background does nothing. This preserves the "lasso is the authoritative creation path" invariant and keeps the mental model simple: the thing under your cursor at press-down decides what happens.

### Scope discipline protects the project
Every additional tool (threshold, watershed, magic select, smart edge) pulls the product toward "general image editor" — which BacMask is explicitly **not**. Adding tools is a one-way door. Brush is allowed because it directly serves the boundary-refinement use case that the lasso-edit gesture failed at; no other tool gets that justification yet.

## Explicitly NOT in MVP
- Eraser as a separate tool — `Ctrl`-brush already does this.
- Flood fill / magic wand
- Threshold / binarize
- Edge detection (Canny, Sobel)
- User-facing morphological operators
- Image adjustments (brightness, contrast, gamma)
- Boolean region operations between two regions
- Region splitting / merging by adjacency

## Related
- [014 — Lasso Tool](014-lasso-tool.md) — creation tool.
- [026 — Brush Edit Model](026-brush-edit-model.md) — edit tool.
- [027 — Toolbar Hotkey Labels](027-toolbar-hotkey-labels.md) — discoverability rule.
- [028 — File Picker Double-Click](028-file-picker-double-click.md) — open-on-double-click rule.
- [000 — Project Overview](000-project-overview.md) — scope anchor.
