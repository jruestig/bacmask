# Wave 1 — Session C: Brush Commit via Transient Raster

Runs in parallel with wave 1A (area) and wave 1B (canvas). Medium risk —
the boolean-op math on the bbox crop must be exactly right. Cut the
branch from post-wave-0 `master`.

---

You are refactoring BacMask (`/home/jruestig/pro/python/bacmask`). Read
[knowledge/030 — Polygons Are the Only Mask Truth](../knowledge/030-polygons-are-mask-truth.md)
and
[knowledge/026 — Brush Edit Model](../knowledge/026-brush-edit-model.md)
first. Those notes are the doctrine; this brief is the operational slice.

## Why this change

`MaskService.end_brush_stroke` (around line 397 in
`bacmask/services/mask_service.py`) today does the add/subtract boolean
op against `state.region_masks[target_id]` — the stored per-region HxW
bool mask. It copies that mask, boolean-ops the stroke footprint into
the bbox, re-derives the contour, and hands the new mask to
`BrushStrokeCommand.new_region_mask` for storage.

Wave 2 will delete `state.region_masks`. Your job is to rewrite the
commit so the working raster is a **freshly-rasterized, bbox-local**
version of the target polygon — a scratch buffer created at commit time,
used for the boolean op + contour extraction, then discarded. Nothing
stores it after the commit returns.

## Task

Rewrite the add/subtract branch of `end_brush_stroke`. Keep the
create-mode branch (`_commit_brush_create`) as-is — it is already
polygon-native.

For add and subtract modes:

1. Validate the stroke bbox and extract `s_crop = stroke.mask[bbox]` as
   before.
2. **New:** compute the union bbox of (stroke bbox, target polygon's
   vertex bbox). For subtract, the stroke bbox alone suffices
   (subtract can only shrink the region). For add, use the union since
   the new boundary may extend past the target.
3. **New:** rasterize `state.regions[target_id]["vertices"]` into a
   scratch bool crop `target_crop` sized to the chosen bbox. Use
   `masking.rasterize_polygon_mask` with an offset, or
   `cv2.fillPoly` directly on a pre-zeroed bbox-sized uint8 array with
   translated vertex coords. Document the choice in a comment if
   non-obvious.
4. Do the boolean op on the crops:
   - add: `new_crop = target_crop | s_crop_in_same_bbox`
   - subtract: `new_crop = target_crop & ~s_crop_in_same_bbox`
5. No-op detection: if `new_crop` is equal to `target_crop`, discard the
   stroke.
6. Empty-region detection (subtract): if `new_crop` has no True pixels
   anywhere, route through `DeleteRegionCommand` — same as today.
7. `largest_connected_component` + `contour_vertices` on `new_crop`,
   translate the resulting vertex coords back to image space by adding
   the bbox origin, and commit a `BrushStrokeCommand`.

## Scope — files you may modify

- `bacmask/services/mask_service.py` — the `end_brush_stroke` method and
  its private helpers (`_any_outside_bbox`, etc.) only if you need to
  adjust them. `_commit_brush_create` should be untouched.
- `tests/services/test_mask_service.py` — update brush-edit assertions
  to probe `state.regions[lid]["vertices"]` and (where applicable)
  `state.label_map[y, x]` instead of `state.region_masks[lid]`.
- `tests/core/test_commands.py` — update only the tests that exercise
  the brush-commit end-to-end flow through the service.

## Files you must not modify

- `bacmask/core/state.py` — **do not remove** the `region_masks` or
  `region_areas` fields.
- `bacmask/core/commands.py` — **do not remove** the
  `new_region_mask` parameter from `BrushStrokeCommand`. Still pass it in,
  even though your new code will construct it by rasterizing the new
  polygon. Wave 2 removes the parameter; wave 1 keeps the interface
  stable so other sessions compile.
- `bacmask/ui/**` — out of scope.

## Implementation notes

- "Still pass `new_region_mask`" means: after you have the new polygon's
  vertices, rasterize them **once** into a full-image bool mask via
  `masking.rasterize_polygon_mask(new_vertices, label_map.shape)` and
  hand that to the command. This is the only remaining full-image raster
  in this path, and wave 2 will remove it along with the parameter. It
  exists in wave 1 solely to keep the command interface unchanged while
  parallel sessions run.
- The critical correctness concern is bbox alignment. If `stroke.bbox`
  and the target-polygon bbox have different origins, you must
  translate both masks into the same coordinate frame before ORing /
  ANDing. Either:
  - Pick a union bbox and translate both crops into it (my preference:
    allocate `target_crop` sized to the union bbox, offset the vertices
    by `(-ux0, -uy0)` when calling `fillPoly`; then do the same for the
    stroke via `stroke.mask[union_bbox]`), or
  - Allocate in the original stroke bbox and clip the target
    accordingly (subtract only — add may overflow).
- Benchmark-friendly: skip rasterizing the target outside the chosen
  bbox. That's the whole point — transient, local, cheap.
- Preserve the existing "subtract emptied the region" → `DeleteRegionCommand`
  routing. Same undo path.

## Regression check

Add one test that exercises the new rasterize-on-demand path end-to-end:

```python
def test_brush_add_does_not_read_region_masks():
    """Brush add must commit correctly even when state.region_masks is
    stale (i.e. does not reflect the current polygon). After the wave 2
    removal, this is guaranteed by construction; for now, force the
    staleness by corrupting state.region_masks[target] before the commit."""
```

Build a region, overwrite its `region_masks` entry with zeros (a stale
mask), run an add-brush stroke, verify the committed polygon correctly
reflects the union of the (real) original polygon and the stroke
footprint — not the zeros.

## Exit criteria

- `uv run pytest` green.
- `uv run ruff check` clean.
- `uv run ruff format --check` clean.
- Grep confirms `end_brush_stroke` no longer reads
  `state.region_masks[target_id]`.
- The regression test above passes.
- One commit. Suggested message:
  `refactor(brush): commit via transient polygon rasterization, not stored target mask`.

## Report

One short paragraph: which boolean-op ordering you chose (bbox union vs.
stroke-bbox-only), the regression test outcome, any surprises with bbox
translation math.
