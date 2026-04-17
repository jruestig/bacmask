---
id: 002
title: Centralized Session State
tags: [architecture, core]
created: 2026-04-17
status: accepted
related: [001, 003, 008, 014, 015, 017]
---

# Centralized Session State

Single source of truth for the annotation session. No state scattered across UI widgets.

## Location
`bacmask/core/state.py` → `SessionState` class.

## Fields (minimum)
- `image`: loaded source image (NumPy array, full resolution, **color preserved**) or `None`.
- `image_path`: absolute path of the loaded file.
- `image_filename`: basename with extension (written to CSV, see [011](011-csv-for-area-output.md)).
- `label_map`: `uint16` NumPy array, same `HxW` as `image`. `0` = background, `1..N` = region IDs.
- `regions`: `dict[int, RegionMeta]` — per-region `name` + `vertices`. See [014](014-lasso-tool.md).
- `next_label_id`: int. Monotonic counter; never decremented on delete. Persisted to bundle ([015](015-bacmask-bundle.md)) so IDs remain stable across save/reload.
- `scale_mm_per_px`: `float | None`. `None` until calibrated. See [017](017-calibration-input.md).
- `view`: pan offset + zoom level (display-only state, not persisted).
- `active_lasso`: live in-progress polyline vertices, or `None`. Cleared on close or cancel.
- `dirty`: bool. True when unsaved structural mutations exist.

## Rules
- Mutations go through **service methods**, never direct field assignment from UI.
- UI observes state and re-renders; it does not own state.
- `dirty` toggled on every structural mutation (lasso close, vertex edit, delete, calibration change). Cleared on Save All.
- `next_label_id` persists in the bundle — reload continues the sequence without collision.

## Why
Without this, state leaks into widget attributes, save detection breaks, undo/redo loses its anchor, label IDs collide on reload, and headless testing becomes impossible.

## Related
- [001 — Separation of Concerns](001-separation-of-concerns.md).
- [003 — Undo/Redo](003-undo-redo-commands.md) — commands mutate this state.
- [014 — Lasso Tool](014-lasso-tool.md) — consumer of `active_lasso` and `regions`.
- [015 — .bacmask Bundle](015-bacmask-bundle.md) — persistence of `next_label_id`, `regions`, scale.
- [017 — Calibration Input](017-calibration-input.md) — `scale_mm_per_px`.
