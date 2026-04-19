---
id: 002
title: Centralized Session State
tags: [architecture, core]
created: 2026-04-17
updated: 2026-04-19
status: accepted
related: [001, 003, 008, 014, 015, 017, 025, 026, 030]
---

# Centralized Session State

Single source of truth for the annotation session. No state scattered across UI widgets. Polygons are the only canonical mask representation — see [030 — Polygons Are the Only Mask Truth](030-polygons-are-mask-truth.md) for the doctrine this note operationalizes.

## Location
`bacmask/core/state.py` → `SessionState` class.

## Persisted fields

- `image`: loaded source image (NumPy array, full resolution, **color preserved**) or `None`.
- `image_path`: absolute path of the loaded file.
- `image_filename`: basename with extension (written to CSV, see [011](011-csv-for-area-output.md)).
- `regions`: `dict[int, RegionMeta]` — per-region `name` + `vertices`. **The single source of truth.** Everything mask-shaped is derived from this dict on demand ([030](030-polygons-are-mask-truth.md)).
- `next_label_id`: int. Monotonic counter; never decremented on delete. Persisted to bundle ([015](015-bacmask-bundle.md)) so IDs remain stable across save/reload.
- `scale_mm_per_px`: `float | None`. `None` until calibrated. See [017](017-calibration-input.md).

## Session-local fields (not persisted)

- `view`: pan offset + zoom level.
- `active_lasso`: live in-progress lasso polyline (list of vertices), or `None`. Cleared on close or cancel.
- `active_brush_stroke`: `BrushStroke | None`. In-progress brush stroke: `target_id` (int or None — None for `create` mode), `mode`, accumulated `mask`, `last_pos`, `bbox`. The stroke's `mask` is a transient scratch buffer that exists only during the gesture; it is discarded on commit or cancel. See [026](026-brush-edit-model.md).
- `active_tool`: `Literal["lasso", "brush"]`. Default `"lasso"`. Picking the tool *is* the mode — there is no separate `edit_mode` flag (the old one from [023](superseded/023-edit-mode-region-boolean-edits.md) was removed).
- `brush_radius_px`: int. Image-space brush size, range `[1, 100]`, default 8.
- `brush_default_mode`: `Literal["create", "add", "subtract"]`. Persistent brush mode set by the brush-panel toggles or cycled with `Tab`. See [026](026-brush-edit-model.md).
- `selected_region_id`: int or `None`. The results-panel highlight, cyan outline, and brush selection lock all track this id. In add/subtract brush mode it doubles as the target when press-down hits background — the *selection lock* that lets a subtract begin off the boundary.
- `dirty`: bool. True when unsaved structural mutations exist.
- `regions_version`: int. Monotonic counter bumped by every region-mutating command (and `load_bundle` / `set_image`). Subscribers gate expensive rebuilds on it (canvas overlay rebuild, results table diff) so selection / mode / calibration notifies don't trigger a full re-render during drag.

## Render projection (not state)

There is exactly one derived rendering artifact exposed on `SessionState`:

- `label_map: np.ndarray | None` — `uint16` `(H, W)` texture **used only by the canvas and hit-test paths**. When `regions_version` bumps, the canvas rebuilds it by painting polygons in ascending `label_id` order (so the highest id wins on overlap, per [025](025-overlapping-regions.md)). It is never read as truth for area, commit decisions, or persistence. In the GPU-tessellation renderer path ([030](030-polygons-are-mask-truth.md)) this field is unused entirely — tessellated meshes handle both rendering and hit-test, and `label_map` can be set to `None`.

Either way, `label_map` is a render cache derived from polygons, not a second source of truth. See [030](030-polygons-are-mask-truth.md) for the rationale.

## What this state does NOT hold

The following were present in earlier architectures and have been removed (see [030](030-polygons-are-mask-truth.md)):

- `region_masks: dict[int, np.ndarray]` — per-region bool masks. Derived on demand.
- `region_areas: dict[int, int]` — cached `mask.sum()` per region. Replaced by `masking.polygon_area(vertices)` called at read-time; O(N) in vertex count, sub-microsecond.

Any code that was maintaining "`region_masks[lid]` in sync with `regions[lid]['vertices']`" is deleted. That invariant no longer exists because the second dict no longer exists.

## Rules

- Mutations go through **service methods**, never direct field assignment from UI.
- UI observes state and re-renders; it does not own state.
- `dirty` toggled on every structural mutation (lasso close, vertex edit, delete, calibration change). Cleared on Save.
- `next_label_id` persists in the bundle — reload continues the sequence without collision.

## Why

Without centralized state: state leaks into widget attributes, save detection breaks, undo/redo loses its anchor, label IDs collide on reload, headless testing is impossible. Restricting the canonical representation to polygons additionally removes a whole class of sync-invariant bugs ([030](030-polygons-are-mask-truth.md)).

## Related

- [001 — Separation of Concerns](001-separation-of-concerns.md).
- [003 — Undo/Redo](003-undo-redo-commands.md) — commands mutate this state; snapshots are vertex lists.
- [014 — Lasso Tool](014-lasso-tool.md) — consumer of `active_lasso` and `regions`.
- [015 — .bacmask Bundle](015-bacmask-bundle.md) — persistence of `next_label_id`, `regions`, scale.
- [017 — Calibration Input](017-calibration-input.md) — `scale_mm_per_px`.
- [025 — Overlapping Regions Allowed](025-overlapping-regions.md) — overlap is resolved at render time, not stored.
- [026 — Brush Edit Model](026-brush-edit-model.md) — consumer of `active_brush_stroke`, `brush_radius_px`, `brush_default_mode`, `selected_region_id`-as-lock.
- [029 — Incremental Overlay + Area Cache](superseded/029-incremental-overlay-and-area-cache.md) — superseded; `region_masks` / `region_areas` are gone.
- [030 — Polygons Are the Only Mask Truth](030-polygons-are-mask-truth.md) — the anchor doctrine.
