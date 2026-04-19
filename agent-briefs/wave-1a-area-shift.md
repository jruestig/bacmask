# Wave 1 — Session A: Area → Shoelace

Runs in parallel with wave 1B (canvas) and wave 1C (brush). Low risk;
good starter session. Cut the branch from post-wave-0 `master`.

---

You are refactoring BacMask (`/home/jruestig/pro/python/bacmask`). Read
[knowledge/030 — Polygons Are the Only Mask Truth](../knowledge/030-polygons-are-mask-truth.md)
first. That note is the doctrine; this brief is the operational slice.

## Why this change

Today BacMask has two conflicting definitions of "area":

1. `masking.polygon_area(vertices)` — mathematical enclosed area via the
   shoelace formula. Exact, float. Already in the codebase.
2. `state.region_areas[label_id]` — cached `int(region_mask.sum())` after
   `cv2.fillPoly` with the even-odd rule. Rasterized pixel count. Can drift
   by ±perimeter pixels when vertices round-trip through `contour_vertices`
   during brush commits or undo/redo.

The CSV export and results-panel area column both read (2). This is the
silent bug that motivated 030: numbers can shift without a user-visible
edit. Collapse to (1) — shoelace is correct for scientific reporting.

## Task

Make `MaskService.compute_area_rows` compute each region's `area_px` by
calling `masking.polygon_area(meta["vertices"])` instead of reading
`state.region_areas`. Propagate the float type through the `AreaRow` record
and the CSV writer. Regenerate any snapshot fixtures that pin specific
pixel-count integers.

## Scope — files you may modify

- `bacmask/services/mask_service.py` — the method `compute_area_rows` only
  (around line 617).
- `bacmask/core/io_manager.py` — the `AreaRow` dataclass (`area_px` field
  type) and any CSV-writing code that formats it.
- `tests/services/test_mask_service.py` — update `compute_area_rows`
  assertions to match shoelace numbers.
- `tests/core/test_io_manager.py` (or similar) — update CSV snapshot
  fixtures.
- Any `*.csv` fixture files the tests compare against.

## Files you must not modify

- `bacmask/core/state.py` — **do not remove** the `region_areas` field.
  Other in-flight sessions depend on it existing.
- `bacmask/core/commands.py` — **do not remove** the writes to
  `region_areas` in any command's `apply` / `undo`. They are orphaned
  writes now but wave 2 removes them.
- `bacmask/ui/**` — out of scope; wave 1B owns the canvas.
- Any other file — ask before editing.

## Implementation notes

- `masking.polygon_area(vertices)` returns a `float`. Do not cast to `int`
  anywhere. The CSV was previously writing an integer; now it writes a
  float via Python's default `repr`.
- If `AreaRow.area_px: int` is referenced anywhere else, update the
  annotation; do not add a conversion shim.
- For a triangle with vertices (0,0), (10,0), (0,10), shoelace gives 50.0.
  The old rasterized count for that same triangle is 55 (the boundary
  pixels get filled). This is the expected direction of drift.
- The `area_mm2` formula `px_to_mm2(area_px, scale)` already multiplies;
  it works unchanged when `area_px` is a float.
- Snapshot CSVs: regenerate manually by running the test once, copying the
  actual output into the fixture, and re-running. Verify the new numbers
  look sensible (positive, monotonically scaling with polygon size).

## Regression check

Before committing, add one new test:

```python
def test_compute_area_rows_uses_polygon_shoelace():
    """area_px must match polygon_area(vertices), not rasterized count."""
```

Build a service with a known triangle region, assert the returned
`area_px` equals the expected shoelace value to float tolerance.

## Exit criteria

- `uv run pytest` green.
- `uv run ruff check` clean.
- `uv run ruff format --check` clean.
- Grep confirms `state.region_areas` is no longer *read* anywhere in
  `bacmask/services/mask_service.py` (it is still *written* by commands,
  which is fine — wave 2 removes those writes).
- One commit. Suggested message:
  `refactor(area): compute area_px from polygon shoelace, not rasterized count`.

## Report

One short paragraph: which snapshot files regenerated, the measured drift
on any existing fixture (old vs new numbers), anything surprising.
