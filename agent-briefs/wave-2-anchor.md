# Wave 2 — Anchor Commit: Commands + State + Masking Prune

Runs **after** all three wave 1 branches (A, B, C) have merged to master.
Highest risk of the entire refactor. This is where `region_masks` and
`region_areas` leave the codebase. `ruff` and `pytest` are your forcing
function: any stray reference anywhere in the tree blocks the merge.

---

You are refactoring BacMask (`/home/jruestig/pro/python/bacmask`). Read
[knowledge/030 — Polygons Are the Only Mask Truth](../knowledge/030-polygons-are-mask-truth.md),
[knowledge/002 — Centralized Session State](../knowledge/002-state-management.md),
[knowledge/003 — Undo/Redo via Command Pattern](../knowledge/003-undo-redo-commands.md),
and [knowledge/026 — Brush Edit Model](../knowledge/026-brush-edit-model.md)
before touching code. These notes are the doctrine; this brief is the
operational slice.

## Why this change

After wave 1, `state.region_masks` and `state.region_areas` are still
allocated, still written by every command's apply/undo, but no longer
read by the renderer, the brush commit, or the area computation. They
are orphaned. This wave removes them, rewrites commands to snapshot
vertex lists only, and prunes the masking helpers whose sole purpose was
maintaining sync between the polygon and mask representations.

This is the payoff of the whole refactor. The structural simplification
lives here — not in wave 1.

## Preconditions (verify before you start)

1. `git status` is clean.
2. You are on `master` and `git log --oneline -10` shows the three wave 1
   merge commits (area, canvas, brush) plus the wave 0 commit.
3. `uv run pytest` is green.
4. `uv run ruff check` + `uv run ruff format --check` are clean.
5. `grep -r "region_masks\|region_areas" bacmask/` returns hits only in
   `bacmask/core/state.py` and `bacmask/core/commands.py`. If it returns
   hits in `services/`, `ui/`, or anywhere else, **stop** — wave 1 is
   incomplete and you must escalate to the orchestrator.

If any precondition fails, report and wait for instructions. Do not
improvise around a dirty tree.

## Task structure

Five sub-steps, **one commit per sub-step**, in the order below. The tree
must be green after each commit. If step N breaks the suite in a way
you cannot fix inside that step's scope, stop and report — do not let a
broken state persist into step N+1.

### Step 1: Rewrite commands to snapshot vertex lists only

File: `bacmask/core/commands.py`.

- `LassoCloseCommand`: drop the `region_mask` parameter. `apply` inserts
  the polygon into `state.regions`, assigns `next_label_id`, and paints
  the new region into `state.label_map` via
  `masking.paint_label_map_bbox(state.label_map, state.regions,
  polygon_vertex_bbox)`. The polygon is the newest, so painting it last
  inside its bbox is sufficient — no need to iterate all regions in the
  bbox. Use a simpler direct `cv2.fillPoly` on `state.label_map` inside
  the bbox. `undo` pops the region, rolls `next_label_id` back, and
  repaints the bbox via `paint_label_map_bbox` (which iterates remaining
  regions in ascending id). Drop all `region_masks` / `region_areas` /
  `_prev_region_mask` fields and logic.
- `DeleteRegionCommand`: store only `_name` and `_vertices` (pop them
  from `state.regions` in `apply`; restore in `undo`). Both apply and
  undo repaint the popped region's vertex bbox via
  `paint_label_map_bbox`. Drop `_region_mask`, `_region_area`, any mask
  snapshot fields.
- `BrushStrokeCommand`: drop the `new_region_mask` parameter. Store
  `_old_vertices` snapshot in `apply`. Swap `state.regions[lid][
  "vertices"]` to the new list. Repaint the union bbox of
  (old_vertices_bbox, new_vertices_bbox) via `paint_label_map_bbox`.
  `undo` restores old vertices and repaints the same union bbox. Drop
  `_old_region_mask`, `_old_region_area`, all mask logic.
- `VertexEditCommand`: **delete** the class entirely. Its only consumer
  is `MaskService.edit_vertices` which is used by one test. See step 2.

Bbox computation helper: add `vertices_bbox(vertices, image_shape) ->
(y0, y1, x0, x1) | None` back into `bacmask/core/masking.py` if it was
removed during wave 1. (Commands need it; it is the natural counterpart
to `paint_label_map_bbox`.) If wave 0 kept it, reuse it.

After this step, commands no longer touch `state.region_masks` or
`state.region_areas` — but the fields still exist and are still
initialized to empty dicts. The fields are now dead code.

Commit message: `refactor(commands): snapshot vertex lists only, drop mask fields`.

### Step 2: Delete VertexEditCommand and edit_vertices

File: `bacmask/services/mask_service.py`.

- Remove `VertexEditCommand` from the import list.
- Remove the `edit_vertices` method.

File: `tests/services/test_mask_service.py` (and any other test file).

- Find tests that call `edit_vertices` (grep for it). There should be a
  small number — likely in a single test file. Delete them. The brush
  tests cover the vertex-replacement path now.

File: `bacmask/core/commands.py`.

- If `VertexEditCommand` is still defined (it was not deleted in step 1
  because step 1 said "delete the class entirely" — if you did, skip
  this), remove it now.

Commit message: `refactor(commands): drop unused VertexEditCommand and edit_vertices`.

### Step 3: Drop region_masks and region_areas from SessionState

File: `bacmask/core/state.py`.

- Remove the `region_masks` field and its type annotation.
- Remove the `region_areas` field and its type annotation.
- Remove the `self.region_masks = {}` and `self.region_areas = {}` lines
  from `set_image`.

Then run:

```
uv run ruff check
uv run pytest
```

Any error reports an orphaned reference you missed. Fix each one — the
fix should always be "delete the code that reads it," never "put the
field back." This is the forcing-function completeness check.

Likely orphans to check: `bacmask/services/mask_service.py` `load_bundle`
which today populates both dicts. That code should be deleted, not
updated.

Commit message: `refactor(state): drop region_masks and region_areas fields`.

### Step 4: Clean up load_bundle

File: `bacmask/services/mask_service.py`, method `load_bundle`.

- Remove the dict-comprehension that builds `state.region_masks` from
  polygons.
- Remove the dict-comprehension that builds `state.region_areas` from
  masks.
- Replace the `masking.repaint_label_map(state.label_map, state.region_masks)`
  call with a walk over `state.regions` in ascending id that paints each
  polygon into `state.label_map` via `cv2.fillPoly` (or, if the whole
  image fits, one call to `masking.paint_label_map_bbox(state.label_map,
  state.regions, (0, h, 0, w))`).
- `set_image` already zeros `state.label_map`; nothing else to do there.

Commit message: `refactor(service): stop pre-rasterizing per-region masks on bundle load`.

### Step 5: Prune masking.py

File: `bacmask/core/masking.py`.

Delete:

- `erase_region`
- `repaint_label_map` (superseded by the explicit walk in step 4)
- `repaint_label_map_bbox` (superseded by `paint_label_map_bbox`)
- `mask_bbox`
- `union_bbox`
- `rasterize_polygon` (the in-place uint16 painter — callers use
  `cv2.fillPoly` directly now)

Keep:

- `rasterize_polygon_mask` (still needed by the brush commit's transient
  scratch raster)
- `polygon_area` (area computation)
- `largest_connected_component`
- `contour_vertices`
- `stamp_brush_disc`
- `stamp_brush_segment`
- `paint_label_map_bbox` (added in wave 0)
- `vertices_bbox` (re-added in step 1 if it was dropped)

Update `tests/core/test_masking.py` — delete tests for the deleted
functions. Keep tests for the retained ones.

After this step, `bacmask/core/masking.py` should be roughly 120–140
lines (down from ~310).

Commit message: `refactor(masking): drop mask-sync helpers, keep polygon + stamp primitives`.

## Exit criteria

- Five commits landed, each green on its own.
- `uv run pytest` green on master after step 5.
- `uv run ruff check` + `uv run ruff format --check` clean.
- `grep -rn "region_masks\|region_areas" bacmask/ tests/` returns zero
  hits.
- `grep -rn "VertexEditCommand\|edit_vertices" bacmask/ tests/` returns
  zero hits.
- `wc -l bacmask/core/masking.py` reports roughly 120–140 lines.
- `wc -l bacmask/core/commands.py` reports roughly 80–110 lines.
- `wc -l bacmask/services/mask_service.py` reports roughly 350–450
  lines.
- Live smoke check if a display is available: `uv run python main.py`,
  load an image, draw two overlapping lasso regions, brush-edit one,
  delete one, undo, redo, save, export CSV. All should work identically
  to pre-refactor.

## Report

One paragraph: line counts per file (before → after), any invariants that
shifted, any tests that required substantive rewriting (beyond simple
probe updates), whether live smoke was possible.
