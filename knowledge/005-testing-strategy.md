---
id: 005
title: Testing Strategy
tags: [testing, core, services]
created: 2026-04-17
status: accepted
related: [001, 008, 014, 015, 017, 018, 019]
---

# Testing Strategy

The separation-of-concerns split earns its keep here.

## Coverage targets
- **Core logic:** 100% unit-testable, zero UI. Non-negotiable.
- **Services:** integration tests exercising core + state + history together.
- **UI:** manual / smoke tests only for MVP. Automated Kivy UI tests are costly and brittle.

## Specific test contracts

### Area calculation
- A synthetic filled 100×100 square yields exactly **10,000 px**.
- With `scale_mm_per_px = 0.01`, that square yields exactly **1.0 mm²** (tolerance 1e-9).
- Two disjoint regions → two distinct `region_id`s.

### Lasso rasterization
- Axis-aligned polygon `[(0,0), (10,0), (10,10), (0,10)]` rasterizes deterministically under `cv2.fillPoly`. Pin the expected pixel count and assert it — fillPoly's exact convention (inclusive/exclusive edges) must be fixed once by test, then never drift.
- Self-intersecting polygons follow `cv2.fillPoly`'s even-odd rule. Document + test.
- Sub-pixel vertices rounded via `np.round` — verify the rounding is consistent between draw and edit.

### Mask I/O round-trip
- Save label map → load label map → `np.array_equal` with original. Bit-identical.
- 16-bit PNG dtype preserved (not silently downcast to uint8).

### Bundle round-trip ([015](015-bacmask-bundle.md))
- Save `.bacmask` → load → `image`, `mask`, `meta` all restore identically.
- `next_label_id`, `regions` (names + vertices) preserved.
- Deleted region's ID stays reserved — new lasso after reload does not re-use it.
- Unknown `bacmask_version` → raise, do not silently proceed.

### CSV output
- Column order exactly: `filename, region_id, region_name, area_px, area_mm2, scale_factor`.
- Data types: `str, int, str, int, float | "", float | ""`.
- One row per region. Overwrite (not append) on re-save.

### Undo/redo
- `apply → undo` leaves state bit-identical to pre-apply.
- `apply → undo → redo` leaves state bit-identical to post-apply.
- History cap drops oldest, never newest.
- `LassoCloseCommand` → undo → new lasso close: same ID returned (monotonicity preserved during undo window).
- `DeleteRegionCommand` → new lasso close after delete: ID **not** re-used (gap persists).

### Calibration
- `scale_mm_per_px <= 0` rejected.
- Missing calibration → `area_px` populated, `area_mm2` + `scale_factor` are empty strings, no crash. See [017](017-calibration-input.md).

### Dimension mismatch on load ([018](superseded/018-load-mask-dim-mismatch.md))
- Mismatch triggers the service-level prompt; default action rejects.
- Resize path (non-default) uses `INTER_NEAREST`; logs a `WARNING`.

## Fixtures
- `tests/fixtures/synthetic_colony.png` — small deterministic synthetic image.
- `tests/fixtures/synthetic_mask.png` — known-good mask for round-trip checks.
- Real microscopy TIFFs in `images/` (`20251112…`, `20251201…`) are **manual smoke tests and perf inputs**, not CI fixtures — too large for the unit test loop.

## Tooling
`pytest` + `pytest-cov`. Environment managed via `uv` — see [019](019-dev-tooling.md).

## Related
- [001 — Separation of Concerns](001-separation-of-concerns.md) — the precondition for this strategy.
- [014 — Lasso Tool](014-lasso-tool.md).
- [015 — .bacmask Bundle](015-bacmask-bundle.md).
- [017 — Calibration Input](017-calibration-input.md).
- [018 — Load Mask Dimension Mismatch](superseded/018-load-mask-dim-mismatch.md).
- [019 — Dev Tooling](019-dev-tooling.md).
