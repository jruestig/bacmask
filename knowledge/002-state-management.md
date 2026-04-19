---
id: 002
title: Centralized Session State
tags: [architecture, core]
created: 2026-04-17
updated: 2026-04-19
status: accepted
related: [001, 003, 008, 014, 015, 017, 023, 025]
---

# Centralized Session State

Single source of truth for the annotation session. No state scattered across UI widgets.

## Location
`bacmask/core/state.py` → `SessionState` class.

## Fields (minimum)
- `image`: loaded source image (NumPy array, full resolution, **color preserved**) or `None`.
- `image_path`: absolute path of the loaded file.
- `image_filename`: basename with extension (written to CSV, see [011](011-csv-for-area-output.md)).
- `regions`: `dict[int, RegionMeta]` — per-region `name` + `vertices`. **Canonical** ([025](025-overlapping-regions.md)). Everything mask-related is derived from this dict.
- `next_label_id`: int. Monotonic counter; never decremented on delete. Persisted to bundle ([015](015-bacmask-bundle.md)) so IDs remain stable across save/reload.
- `scale_mm_per_px`: `float | None`. `None` until calibrated. See [017](017-calibration-input.md).
- `view`: pan offset + zoom level (display-only state, not persisted).
- `active_lasso`: live in-progress polyline vertices, or `None`. Cleared on close or cancel. Used for both new-region and edit strokes — the distinction is inferred from `edit_mode` + `selected_region_id` at press-down, not stored on the lasso itself.
- `edit_mode`: bool. `True` when the Edit toggle is on ([023](superseded/023-edit-mode-region-boolean-edits.md)). Session-local; not persisted.
- `selected_region_id`: int or `None`. Doubles as the *edit target* when `edit_mode` is on. One slot, two uses — the results-panel highlight and the cyan outline track it.
- `dirty`: bool. True when unsaved structural mutations exist.

## Derived state (not persisted)
Mask representations are computed from `regions`, cached for performance, and invalidated on any polygon mutation. They are **never** written to disk by Save — masks leave the system only via the deferred export ([024](024-mask-export-deferred.md)).

- `region_masks: dict[int, np.ndarray]` — one `bool` array `(H, W)` per region, rasterized from its polygon. Authoritative for hit-testing, area computation, and the edit-mode "inside" check ([023](superseded/023-edit-mode-region-boolean-edits.md)).
- `label_map_cache: np.ndarray | None` — `uint16` `(H, W)` display cache, populated by painting each region's pixels in ascending `label_id` order so the highest `label_id` wins on overlapping pixels. Used only for rendering and click-select tiebreak ([025](025-overlapping-regions.md)). Never the source of truth; always regeneratable from `region_masks`.

Regeneration granularity:
- On `LassoCloseCommand` / `RegionEditCommand` / `DeleteRegionCommand`, only the affected region's entry in `region_masks` is rebuilt (or removed), and the `label_map_cache` is patched within the region's bounding box.
- On `load_bundle`, both caches are built fresh from polygons.

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
- [023 — Edit Mode](superseded/023-edit-mode-region-boolean-edits.md) — consumer of `edit_mode` + `selected_region_id`-as-target.
- [025 — Overlapping Regions Allowed](025-overlapping-regions.md) — polygons canonical; derived masks may overlap.
