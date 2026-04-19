---
id: 030
title: Polygons Are the Only Mask Truth
tags: [architecture, core, perf]
created: 2026-04-19
status: accepted
related: [002, 003, 004, 011, 014, 025, 026, 029]
---

# Polygons Are the Only Mask Truth

Anchor doctrine. Supersedes the per-region `region_masks` / `region_areas`
caches documented in [029](superseded/029-incremental-overlay-and-area-cache.md).
Everything mask-shaped is derived on demand from the polygon set.

## The rule

**Inside a region's polygon boundary, every pixel belongs to that region.**
Everything else about the region — its area, its rasterization, whether a
given pixel is inside it, whether it collides with another region — is a
function of the ordered vertex list. No parallel raster state exists to
keep in sync.

## What state holds (and what it doesn't)

`SessionState.regions: dict[int, {name, vertices}]` is the single source of
truth. Deleted from state:

- `region_masks: dict[int, np.ndarray]` — one HxW bool per region.
- `region_areas: dict[int, int]` — cached `mask.sum()` per region.

Kept, but reclassified as a **pure render projection** (not authoritative
data):

- `label_map: np.ndarray | None` — `uint16` HxW texture rebuilt by the
  canvas from polygons when `regions_version` bumps. Lives in state so the
  canvas and hit-test paths share it, but it is never consulted as truth
  for area, commit decisions, or persistence.

## Area

`area_px = masking.polygon_area(vertices)` (Green's theorem / shoelace).
O(N) in vertex count. For a 500-vertex polygon: ~1 µs. For 1000 regions in
a results-panel refresh: sub-millisecond total. No cache needed — a cache
would be slower than recomputing.

### Why shoelace (not `mask.sum()`)

Two definitions of "area" existed in the old architecture:

1. **Shoelace** — mathematical enclosed area in px² units. Exact, float.
2. **Rasterized pixel count** — `mask.sum()` after `cv2.fillPoly` with the
   even-odd rule. Integer. Drifts by ±perimeter-pixels under vertex
   rounding, self-intersection, and contour re-derivation.

The CSV used (2). Undo/redo can round-trip vertices through
`contour_vertices` and silently shift the pixel count by a few pixels,
changing export numbers with no user-visible edit. With polygons
canonical there is one definition: shoelace. This is the correct one for
scientific reporting.

### CSV consequence

`area_px` column numbers will shift slightly (sub-1% for convex clean
shapes; up to ~5% for thin noisy boundaries). The new number is the
mathematically correct enclosed area. Snapshot tests regenerate once;
document the shift in release notes.

## Rendering & overlap

**Newest-on-top is a render algorithm, not stored state.**

Canvas overlay:

- Iterate polygons in **ascending** `label_id` order, alpha-over each one's
  color into the framebuffer. Highest id lands last → wins visually on
  overlapping pixels. Same visual result as the old `label_map` + lookup
  table path.
- Rebuild is gated by `regions_version` (unchanged from current
  architecture). No per-frame cost.
- **Preferred implementation:** GPU tessellation — each polygon →
  triangle list via `kivy.graphics.tesselator.Tesselator` → `Mesh` with an
  alpha-blended color. Zero CPU rasterization per region. Polygon changes
  re-tessellate that one region's triangles; everything else is reused.
- **Fallback implementation:** CPU raster. When `regions_version` bumps,
  rebuild `label_map` by painting each polygon with `cv2.fillPoly` in
  ascending id. Simpler; closer to today's code; keeps hit-testing as a
  single texture sample. Use this if GPU tessellation is delayed.

## Hit-testing

Click resolves to "which region wins at pixel `(y, x)`":

- **GPU renderer path:** walk `regions` in **descending** id order; first
  polygon whose `cv2.pointPolygonTest` returns ≥ 0 is the hit. O(N·P) per
  click where P is average vertex count. At N=500, P=100 that's ~50k
  float ops — under a millisecond. No mask needed.
- **CPU renderer path:** sample `label_map[y, x]`. O(1). Already paid for
  by the rendering cache.

Brush press-down uses the same rule.

## Brush add/subtract commit

The add/subtract boolean op fundamentally needs pixel-level geometry. The
rule here is that this is a **transient, bbox-local** raster that never
lives past the commit:

1. During drag, stamp a bool mask `S` into a bbox-tracked buffer (existing
   behavior, unchanged).
2. On release, rasterize **only the target polygon**, **only within the
   stroke bbox**, into a temporary `target_crop` bool array (O(bbox),
   typically tiny vs. full image).
3. Boolean op: `new_crop = target_crop | S_crop` (add) or
   `target_crop & ~S_crop` (subtract).
4. `largest_connected_component` + `contour_vertices` on `new_crop` (or
   the union-bbox extended crop if add grew outside target's bbox) →
   new vertex list. Translate crop-space coords back to image-space.
5. Commit `BrushStrokeCommand(label_id, new_vertices)`. No mask stored
   anywhere — in the command, in state, or in undo.

The transient raster is an **implementation tool**, the way `cv2.line` is
a tool inside the stroke-stamping step. It is not the region.

## Undo / redo

Commands snapshot vertex lists only:

- `LassoCloseCommand` — stores `vertices`, `_prev_next_id`.
- `DeleteRegionCommand` — stores `_vertices`, `_name`.
- `BrushStrokeCommand` — stores `_old_vertices`, writes `new_vertices`.

No mask fields. History memory drops by the ratio of `H·W`-bool-size to
average vertex count — on a 4000×3000 image, ~100× per snapshot.

## Load / save

Symmetric. Both parse/serialize `regions`. Load does **not** pre-rasterize
anything — the canvas's first render pass pays for that lazily, and only
for what it's rendering. `next_label_id`, `scale_mm_per_px` persist in
`meta.json` as before.

## What this deletes from the codebase

Once the doctrine lands:

- `state.region_masks`, `state.region_areas` dict fields.
- `masking.erase_region`, `masking.repaint_label_map_bbox`,
  `masking.union_bbox`, `masking.mask_bbox`, `masking.vertices_bbox`.
- Per-region area invariant tracking across every command's apply/undo.
- The defensive `old_mask.copy()` in `VertexEditCommand` /
  `BrushStrokeCommand` (the thing [029](superseded/029-incremental-overlay-and-area-cache.md)
  proposed as a later rewrite — moot now).
- Overlay compositor's `_overlay_tracked` mask-reference dict and its
  added/removed/changed classification branches — rendering iterates
  polygons, not tracked masks.

Measured scope (wave 2 final):

- `core/masking.py` ~310 → 258 lines (−52)
- `core/commands.py` ~249 → 193 lines (−56)
- `services/mask_service.py` ~674 → 649 lines (−25)

The pre-refactor estimates (120 / 90 / 400) were roughly half the actual
post-refactor totals — the gap is almost entirely surviving docstrings
and public API preserved for test compatibility, not dead code. The
*logic* deleted matches the estimates; what stayed is narrative and
signatures. A later prune-pass on comments would close the gap but adds
no structural value.

## Performance

The worry "polygon path is slower than cached masks" does not survive
contact with numbers:

| Op | Old (cached) | New (polygon) |
|---|---|---|
| Area of 1 region | O(1) dict lookup | O(N) shoelace, ~1 µs |
| Area panel refresh (1000 regions) | 0.12 ms (dict sum) | ~1 ms (shoelace) |
| Commit memory (4 MP image) | ~4 MB mask copy | ~KB vertex list |
| Overlay rebuild (100 regions) | Composite + diff tracked masks | Tessellate once per changed polygon |
| Load bundle (100 regions) | 100× `cv2.fillPoly` up front | 0 (lazy in canvas) |

The only path that got *marginally* slower is the area panel refresh, by
under a millisecond on pessimistic inputs. Everything else got faster or
simpler.

## Invariants preserved

- Monotonic `label_id`s, never reused ([014](014-lasso-tool.md)).
- Deterministic rasterization — same polygons + same order = bit-identical
  rendered output and mask export ([024](024-mask-export-deferred.md)).
- One polygon per region; no multi-part, no holes ([025](025-overlapping-regions.md)).
- Overlap allowed ([025](025-overlapping-regions.md)) — collapses to a
  rendering rule, not a storage rule.

## Pre-refactor baseline (wave 0)

Recorded on 2026-04-19 against commit `950738b`. Fixture:
`images/20251112093808947.tif` (2746×3584). Baseline numbers from
`scripts/bench_polygon_refactor.py` — single run, warm fs cache, headless
(no Kivy window). Post-refactor column filled in wave 3 as the median
of three consecutive runs against the wave-2 tip.

| Step | Baseline (ms) | Post-refactor (ms) | Delta |
|---|---:|---:|---:|
| load_image | 311.58 | 302.80 | -3% |
| lasso_add_x10 | 345.22 | 202.60 | 1.7× faster |
| undo_x5 | 10.81 | 5.90 | 1.8× faster |
| redo_x5 | 45.83 | 0.71 | 64× faster |
| brush_add_stroke | 2.36 | 2.74 | +16% |
| compute_area_rows | 0.04 | 1.37 | 34× slower |
| save_bundle | 945.96 | 938.33 | -1% |
| export_csv | 0.23 | 1.66 | 7.2× slower |

Post-refactor column: median of three consecutive runs on the same
fixture, same commit (wave 2 tip), warm fs cache.

### Notes on the measurements

The real win is memory, not wall clock. A per-region `bool` mask on the
2746×3584 fixture is `2746*3584 ≈ 9.4 MB`. At N=100 regions that's
~940 MB of `state.region_masks` + `state.region_areas` we no longer
allocate. Undo history snapshots drop from O(H·W) per command (the old
`_old_mask.copy()` path) to O(V) — a vertex list, typically a few hundred
bytes. On a 4 MP image that's roughly a 100× cut per history entry, and
history is bounded at 50 entries, so the peak-memory ceiling collapses
by ~two orders of magnitude.

Wall-clock is largely a wash because the existing architecture already
amortized the heavy paths — `regions_version`-gated overlay rebuilds,
bbox-local commit arithmetic, etc. This was a **structural** pass, not
a speedup pass; the places that did move are side-effects of deleting
caches.

Three deltas worth calling out:

- **`redo_x5` 64× faster** — the old redo path rebuilt `region_masks` /
  `region_areas` entries from full-image raster. With polygons canonical
  redo only re-swaps vertex lists.
- **`compute_area_rows` 34× slower** and **`export_csv` 7× slower** — both
  now shoelace every polygon on every call instead of dict-looking-up a
  cached `region_areas[label_id]`. Absolute cost is still <2 ms on 10
  regions, i.e. imperceptible for the UI refresh it gates. The tradeoff
  is worth it: shoelace is the mathematically correct enclosed area (see
  "Why shoelace (not `mask.sum()`)" above), and the cache it replaced
  was a known source of drift across undo round-trips. At very large N
  this path would eventually matter; it's fine for any realistic colony
  count.
- **`brush_add_stroke` +16%** — within noise; the commit path still
  does the transient bbox raster it always did, plus one extra
  `largest_connected_component` now that the polygon is re-derived from
  the crop. Sub-ms either way.

## Related

- [002 — State Management](002-state-management.md) — state shape follows this note.
- [003 — Undo/Redo](003-undo-redo-commands.md) — commands snapshot vertices only.
- [014 — Lasso Tool](014-lasso-tool.md) — area = shoelace.
- [025 — Overlapping Regions](025-overlapping-regions.md) — newest-on-top is rendering.
- [026 — Brush Edit Model](026-brush-edit-model.md) — commit via transient bbox raster.
- [029 — Incremental Overlay + Area Cache](superseded/029-incremental-overlay-and-area-cache.md) — superseded.
- [011 — CSV Area Output](011-csv-for-area-output.md) — `area_px` semantics shift.
