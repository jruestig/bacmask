# Wave 0 — Preflight

Land this first. Blocks all of wave 1. Small, focused commit.

---

You are preparing the BacMask codebase (`/home/jruestig/pro/python/bacmask`)
for the refactor described in
[knowledge/030 — Polygons Are the Only Mask Truth](../knowledge/030-polygons-are-mask-truth.md).
Read that note first; it is the doctrine.

## Task

Two small pieces of preparation so that the wave 1 parallel sessions can
share tooling and so that wave 3 has baseline numbers to compare against.

### 1. Add the shared render helper

Add a new function to `bacmask/core/masking.py`:

```python
def paint_label_map_bbox(
    label_map: np.ndarray,
    regions: dict[int, dict],
    bbox: tuple[int, int, int, int],
) -> None:
    """Repaint a sub-rectangle of ``label_map`` from polygon ``regions``.

    Zeroes the half-open ``(y0, y1, x0, x1)`` window of ``label_map`` and
    paints each polygon whose vertex bbox intersects the window, in
    ascending ``label_id`` order so the highest id wins on overlap
    (knowledge/025). ``regions`` is the canonical
    ``{label_id: {"name": str, "vertices": list[[x, y]]}}`` dict from
    ``SessionState``.
    """
```

Implementation notes:

- Use `cv2.fillPoly` per polygon; feed it the vertex list coerced to `np.int32`.
- Compute each polygon's vertex bbox via `min`/`max` on the vertex array; skip
  polygons whose bbox does not intersect the target window.
- Do not read `state.region_masks`. Do not require it as an argument.
- Validate `label_map.dtype == np.uint16`; raise `TypeError` otherwise, same as
  `masking.repaint_label_map`.

Add a small unit test in `tests/core/test_masking.py` that covers:

- Empty `regions` dict zeros the bbox.
- Two overlapping polygons → higher `label_id` wins in the overlap pixels.
- Polygon entirely outside the bbox leaves the label_map untouched outside
  the bbox.

### 2. Record pre-refactor benchmark numbers

Add a script at `scripts/bench_polygon_refactor.py` (create the directory if
it does not exist). The script runs headlessly (no Kivy window) and reports
wall-clock for:

- Loading `images/20251112093808947.tif` if it exists, or the smallest TIFF
  in `images/` otherwise, into a `MaskService`.
- 10 synthetic lasso adds (hardcoded vertex lists — see existing fixtures in
  `tests/` for examples). Use `close_lasso` via the service.
- 5 undos followed by 5 redos.
- 1 synthetic brush stroke committed via `begin_brush_stroke` /
  `add_brush_sample` / `end_brush_stroke` on one of the regions.
- `compute_area_rows()` call.
- `save_bundle` to a tempfile.
- `export_csv` to a tempfile.

Print each step's milliseconds to stdout as `step_name: 12.34 ms`. Use
`time.perf_counter`, not wall-clock. Pin any random seeds.

Run the script, capture the output, and append the numbers to
`knowledge/030-polygons-are-mask-truth.md` as a new section:

```markdown
## Pre-refactor baseline (wave 0)

Recorded on <date> against commit <sha>. Fixture: <image path> (<HxW>).

| Step | Baseline (ms) | Post-refactor (ms) | Delta |
|---|---:|---:|---:|
| load_image | 12.3 | — | — |
| lasso_add (×10) | ... | — | — |
...
```

Wave 3 re-runs this script and fills in the remaining columns.

## Scope

**Files you may modify:**

- `bacmask/core/masking.py` (add helper)
- `tests/core/test_masking.py` (add helper tests)
- `scripts/bench_polygon_refactor.py` (new file)
- `knowledge/030-polygons-are-mask-truth.md` (append baseline table)

**Files you must not modify:**

- `bacmask/core/state.py`
- `bacmask/core/commands.py`
- `bacmask/services/mask_service.py`
- `bacmask/ui/**`

## Exit criteria

- `uv run pytest tests/core/test_masking.py` passes.
- `uv run pytest` overall green.
- `uv run ruff check` clean; `uv run ruff format --check` clean.
- `uv run python scripts/bench_polygon_refactor.py` runs without error and
  produces numbers.
- Baseline table landed in `knowledge/030-polygons-are-mask-truth.md`.
- One commit. Suggested message:
  `refactor(masking): add paint_label_map_bbox helper + wave-0 benchmark harness`.

## Report

One short paragraph: which tests you added, baseline numbers measured, any
surprises. No running commentary — just the outcome.
