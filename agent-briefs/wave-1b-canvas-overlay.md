# Wave 1 — Session B: Canvas Overlay from Polygons

Runs in parallel with wave 1A (area) and wave 1C (brush). Highest risk
in wave 1 — visual regression potential. Cut the branch from
post-wave-0 `master`.

---

You are refactoring BacMask (`/home/jruestig/pro/python/bacmask`). Read
[knowledge/030 — Polygons Are the Only Mask Truth](../knowledge/030-polygons-are-mask-truth.md)
and
[knowledge/025 — Overlapping Regions Allowed](../knowledge/025-overlapping-regions.md)
first. Those notes are the doctrine; this brief is the operational slice.

## Why this change

`ImageCanvas._rebuild_overlay_texture` today reads
`state.region_masks: dict[int, np.ndarray]` — one full HxW bool mask per
region — and maintains `_overlay_tracked` as a snapshot of which mask
references it last composited. Each `regions_version` bump classifies
every region as added / removed / changed against that snapshot and
takes one of two code paths (pure-add fast path vs. general recomposite).
This is ~200 lines of diff machinery whose purpose is keeping per-region
stored masks in sync with the rendered texture.

Wave 2 will delete `state.region_masks`. Before that lands, the renderer
must stop depending on it. Your job is to rewrite the overlay compositor
so it iterates `state.regions` (polygon vertex lists) and paints directly
from polygons. Wave 0 added `masking.paint_label_map_bbox` as a shared
render helper.

## Task

Rebuild the overlay (RGBA accumulator + `state.label_map` texture) by
walking `state.regions` in ascending `label_id` order. For each polygon:

1. Compute its vertex bbox (from `vertices` — `min`/`max` on x and y).
2. `cv2.fillPoly` the region's color into the RGBA accumulator within that
   bbox, with straight-alpha "over" blend against whatever is already in
   the accumulator.
3. `cv2.fillPoly` the region's `label_id` into `state.label_map` within
   the same bbox.

Highest `label_id` lands last → wins visually on overlapping pixels. This
matches the existing behavior; the polygon walk replaces the mask-diff
machinery.

## Scope — files you may modify

- `bacmask/ui/widgets/image_canvas.py` — the `_rebuild_overlay_texture`,
  `_overlay_reset`, `_composite_region_bbox`, `_recomposite_bbox`,
  `_blit_overlay_texture` methods and any supporting state fields
  (`_overlay_tracked`, `_overlay_acc_rgb`, `_overlay_acc_a`,
  `_overlay_rgba_buf`).
- `bacmask/core/masking.py` — only if `paint_label_map_bbox` was not
  landed by wave 0. In that case, add it per the wave 0 brief.
- `tests/ui/test_image_canvas_edit.py` — update assertions that poked
  `region_masks` or `_overlay_tracked`.
- `tests/ui/test_image_canvas_view.py` — update if it probes overlay
  internals.

## Files you must not modify

- `bacmask/core/state.py` — **do not remove** the `region_masks` or
  `region_areas` fields. Other sessions depend on them.
- `bacmask/core/commands.py` — out of scope; do not touch.
- `bacmask/services/mask_service.py` — out of scope; do not touch.
- Hit-testing path (`ImageCanvas._region_at` at around line 852) — still
  reads `state.label_map`. Since you are still writing `label_map`, this
  keeps working without modification.

## Implementation notes

- Keep the persistent `_overlay_acc_rgb` (float32 HxW×3) and
  `_overlay_acc_a` (float32 HxW) accumulators — they are a valid
  rendering cache. Reset them on every `regions_version` bump instead of
  maintaining a diff.
- Keep the `_overlay_rgba_buf` (uint8 HxW×4) and the one-shot `Texture`
  allocation. Only the *decision of what to paint* changes.
- For each polygon, get its color from the same color-table lookup the
  current code uses (grep for where region colors are chosen today; do
  not change the palette).
- Straight-alpha "over" blend math, pseudocode:
  ```
  src_rgb, src_a = region_color_rgb, region_alpha  # e.g. 0.45
  dst_rgb = acc_rgb[bbox]
  dst_a = acc_a[bbox]
  out_a = src_a + dst_a * (1 - src_a)
  out_rgb = (src_rgb * src_a + dst_rgb * dst_a * (1 - src_a)) / max(out_a, ε)
  acc_rgb[bbox] = out_rgb
  acc_a[bbox] = out_a
  ```
  Apply only inside the polygon footprint (use `cv2.fillPoly` on a
  bbox-local bool mask, then boolean-index into the accumulator slice).
- `state.label_map` paint: same ascending-id loop, one `cv2.fillPoly` per
  polygon inside its vertex bbox. This can share the
  `masking.paint_label_map_bbox` helper if you pass the whole image shape
  as the bbox. Otherwise inline the loop — no need to add abstraction.

## Regression safety (do this first)

Before the rewrite lands, add a snapshot test. Open
`tests/ui/test_image_canvas_edit.py` or create
`tests/ui/test_image_canvas_overlay.py`:

1. Build a small `MaskService` with a fixed image (e.g. 200×200 gray).
2. Add two overlapping regions with known vertex lists — one small square
   at (50,50)-(100,100) with id=1, another at (80,80)-(130,130) with id=2.
3. Drive the canvas through whatever code path triggers
   `_rebuild_overlay_texture`.
4. Compute a hash (SHA-1) of the `_overlay_rgba_buf` contents and assert
   it equals a pinned value.

Run the test against the **pre-rewrite** code, copy the observed hash
into the test, and commit that test as the *first* change of your branch.
Then rewrite the compositor. The pinned hash must survive.

This catches the most likely failure mode: your new path paints the same
polygons but in a subtly different order or with a different blend mode.

## Exit criteria

- `uv run pytest` green.
- `uv run ruff check` clean.
- `uv run ruff format --check` clean.
- Snapshot hash test present and passing.
- Grep confirms `_overlay_tracked` is gone from the codebase.
- Grep confirms `state.region_masks` is no longer read in
  `image_canvas.py`.
- **Live smoke check.** If you have a display available:
  `uv run python main.py`, load any image, draw 3 overlapping lasso
  regions, visually confirm:
  - Each region is semi-transparent (alpha ≈ 0.45).
  - Higher `label_id` regions render on top.
  - Underlying regions' color is still visible through overlap (not
    fully occluded).
  - Deleting a region removes its overlay without ghosts.
  If no display is available, say so explicitly in the report.
- One commit. Suggested message:
  `refactor(canvas): rebuild overlay from polygons, drop mask-diff cache`.

## Report

One short paragraph: lines deleted from `image_canvas.py`, snapshot hash,
whether live smoke was possible, any visual differences observed.
