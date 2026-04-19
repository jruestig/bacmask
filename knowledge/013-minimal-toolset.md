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

- **Lasso** — outline-trace creation. Press-drag-release; closes on release. See [014 — Lasso Tool](014-lasso-tool.md).
- **Brush** — three-mode painting tool. The **mode** (`create` / `add` / `subtract`) is a persistent toolbar setting cycled with `Tab`. Create makes a new region from the painted blob; add/subtract edit the locked target. See [026 — Brush Edit Model](026-brush-edit-model.md).

Exactly one tool is active at a time. The user switches via the toolbar or hotkey (`L` for lasso, `B` for brush). There is **no separate edit-mode toggle** — tool selection is the mode. The old lasso-against-region edit gesture from [023 — Edit Mode & Region Boolean Edits](superseded/023-edit-mode-region-boolean-edits.md) is superseded.

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
- **Draft 3 (2026-04-19):** lasso for create, brush for edit only (Shift add / Ctrl subtract). Dropped after iteration: modifier resolution at press-down was fragile and the gesture was harder to teach than a persistent toggle. The "brush cannot create" invariant was also dropped.
- **Current (2026-04-19):** lasso for outline-trace creation, brush as a three-mode painting tool (`create / add / subtract`) cycled with `Tab` ([026](026-brush-edit-model.md)).

## Rationale

### Two primitives, one job each
Lasso handles "I'm outlining a new colony" — a continuous-trace gesture. Brush handles "I need to nudge this boundary a bit" — a per-pixel painting gesture. Trying to stuff both jobs into one gesture (lasso-against-region in [023](superseded/023-edit-mode-region-boolean-edits.md)) conflated them and confused users. Two explicit tools are clearer than one overloaded one.

### Brush has three modes — including create
The brush can also create regions (in `create` mode). The lasso is still the right tool for outline-trace creation (you draw a boundary, get exactly that shape); the brush-create flow is for "paint a blob" creation where the user thinks in terms of filled area rather than a closed curve. Both pipelines end in the same `LassoCloseCommand` after the largest-CC + contour cleanup.

### Scope discipline protects the project
Every additional tool (threshold, watershed, magic select, smart edge) pulls the product toward "general image editor" — which BacMask is explicitly **not**. Adding tools is a one-way door. Brush is allowed because it directly serves the boundary-refinement use case that the lasso-edit gesture failed at; no other tool gets that justification yet.

## Explicitly NOT in MVP
- Eraser as a separate tool — brush in `subtract` mode already does this.
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
