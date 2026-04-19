---
id: 003
title: Undo/Redo via Command Pattern
tags: [architecture, core]
created: 2026-04-17
updated: 2026-04-19
status: accepted
related: [002, 004, 014, 023, 026, 030]
---

# Undo/Redo via Command Pattern

Not optional. Designed in from MVP day one.

## Design

Each structural mutation is a **Command object** in `bacmask/core/commands.py`. Commands snapshot **vertex lists only** — no per-region mask fields ([030](030-polygons-are-mask-truth.md)):

- `LassoCloseCommand(vertices)` — adds a new region. On `apply`, assigns `next_label_id`, inserts the polygon into `state.regions`, bumps `next_label_id`. On `undo`, removes the region and restores the previous counter.
- `BrushStrokeCommand(label_id, new_vertices)` — replaces the target region's vertex list. Stores `_old_vertices` for undo.
- `DeleteRegionCommand(label_id)` — removes a region. Stores the popped `name` + `vertices` for undo.

All commands implement `apply(state)` and `undo(state)`.

Stack lives in `bacmask/core/history.py` → `UndoRedoStack` with `push`, `undo`, `redo`, `clear`.

## What a command stores

Only polygon-level data. No bool masks, no patches, no label-map slices. On a 4000×3000 image this is the difference between a ~4 MB snapshot (old per-region mask copy) and a ~KB snapshot (vertex list) per undo step — the motivating insight for [030](030-polygons-are-mask-truth.md).

## Calibration is NOT on the stack

`scale_mm_per_px` changes are session-level, not structural mutations. They update state and trigger live recompute but do not push to history. See [017](017-calibration-input.md).

## Bounded history

- Default cap: **50 operations**. Configurable via `config.yaml` ([006](006-configuration-management.md)).
- Drop oldest when cap exceeded.
- Vertex-list snapshots mean the cap is memory-cheap even at high cap values.

## Redo invalidation

Pushing a new command after an `undo` clears the redo stack. Standard behavior.

## Service integration

UI never touches the stack directly. `mask_service.close_lasso(...)` constructs a `LassoCloseCommand`, applies it, pushes to history. UI calls `mask_service.undo()` / `.redo()`.

## Granularity

- One lasso press→close = **one** `LassoCloseCommand`.
- One brush stroke press→release = **one** `BrushStrokeCommand` (or `LassoCloseCommand` for create mode, or `DeleteRegionCommand` if subtract emptied the region).
- One delete = **one** `DeleteRegionCommand`.

## ID monotonicity under undo

Undoing a `LassoCloseCommand` removes the region **and** rolls `next_label_id` back by one — so a subsequent redraw gets the same ID. Redo re-assigns the original ID. This keeps the label space clean when users are iterating during creation. Delete, by contrast, does **not** free its ID (see [014](014-lasso-tool.md) — ID stability).

## Why

Users will make mistakes. Manual annotation without undo is unusable. Command pattern also gives us a free audit trail for future session-replay debugging. Vertex-only snapshots keep memory bounded even with long histories on large images.

## Related

- [002 — Session State](002-state-management.md) — what these commands mutate.
- [004 — Performance](004-performance-large-images.md) — why vertex snapshots beat mask snapshots.
- [014 — Lasso Tool](014-lasso-tool.md) — the commands these wrap.
- [026 — Brush Edit Model](026-brush-edit-model.md) — `BrushStrokeCommand` details.
- [030 — Polygons Are the Only Mask Truth](030-polygons-are-mask-truth.md) — anchor doctrine for vertex-only snapshots.
