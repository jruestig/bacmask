---
id: 003
title: Undo/Redo via Command Pattern
tags: [architecture, core]
created: 2026-04-17
updated: 2026-04-19
status: accepted
related: [002, 004, 014, 023]
---

# Undo/Redo via Command Pattern

Not optional. Designed in from MVP day one.

## Design
Each structural mutation is a **Command object** in `bacmask/core/commands.py`:

- `LassoCloseCommand(vertices, assigned_label_id)` — adds a new region.
- `RegionEditCommand(label_id, old_vertices, new_vertices, old_mask_patch)` — modifies an existing region via an add/subtract stroke ([023](superseded/023-edit-mode-region-boolean-edits.md)). Replaces the earlier `VertexEditCommand`.
- `DeleteRegionCommand(label_id, mask_patch, vertices, name)` — removes a region; stores mask patch + vertices for undo.

All commands implement `apply(state)` and `undo(state)`.

Stack lives in `bacmask/core/history.py` → `UndoRedoStack` with `push`, `undo`, `redo`, `clear`.

## Calibration is NOT on the stack
`scale_mm_per_px` changes are session-level, not mask mutations. They update state and trigger live recompute but do not push to history. See [017](017-calibration-input.md).

## Bounded history
- Default cap: **50 operations**. Configurable via `config.yaml` ([006](006-configuration-management.md)).
- Drop oldest when cap exceeded.
- Commands store **region patches** (bounding box + before/after label-map slice) rather than full-mask snapshots. Critical on large images ([004](004-performance-large-images.md)).

## Redo invalidation
Pushing a new command after an `undo` clears the redo stack. Standard behavior.

## Service integration
UI never touches the stack directly. `mask_service.close_lasso(...)` constructs a `LassoCloseCommand`, applies it, pushes to history. UI calls `mask_service.undo()` / `.redo()`.

## Granularity
- One lasso press→close = **one** `LassoCloseCommand`.
- One edit stroke press→release = **one** `RegionEditCommand`.
- One delete = **one** `DeleteRegionCommand`.

## ID monotonicity under undo
Undoing a `LassoCloseCommand` restores the mask patch to empty **and** rolls `next_label_id` back by one — so a subsequent redraw gets the same ID. Redo re-assigns the original ID. This keeps the label space clean when users are iterating during creation. Delete, by contrast, does **not** free its ID (see [014](014-lasso-tool.md) — ID stability).

## Why
Users will make mistakes. Manual annotation without undo is unusable. Command pattern also gives us a free audit trail for future session-replay debugging.

## Related
- [002 — Session State](002-state-management.md).
- [004 — Performance](004-performance-large-images.md) — patch storage rationale.
- [014 — Lasso Tool](014-lasso-tool.md) — the commands these wrap.
