---
id: 015
title: .bacmask Bundle Format
tags: [architecture, core]
created: 2026-04-17
updated: 2026-04-19
status: accepted
related: [011, 014, 017, 024, 025]
---

# .bacmask Bundle Format

Primary project save artifact. Self-contained editor state — everything needed to resume annotation. Masks are **not** stored inside the bundle; polygons are the canonical truth ([025](025-overlapping-regions.md)). Raster export for downstream training is a separate, on-demand operation ([024](024-mask-export-deferred.md)).

## Container
A **ZIP archive** with extension `.bacmask`. Uses Python's stdlib `zipfile` — zero extra deps.

## Contents (v2)

```
project.bacmask/
├── image.<ext>      # original image, preserved byte-for-byte
└── meta.json        # session metadata (schema below)
```

- `image.<ext>` keeps its source extension (`.tif`, `.png`, `.jpg`, …) and byte contents — no re-encoding.
- No raster mask. The polygon list in `meta.json` is the source of truth; the in-memory label map is a derived display cache ([002](002-state-management.md)).

## meta.json schema (bacmask_version 2)

```json
{
  "bacmask_version": 2,
  "source_filename": "20251112093808947.tif",
  "image_shape": [2048, 2048],
  "created_at": "2026-04-17T15:42:11Z",
  "updated_at": "2026-04-19T16:10:55Z",
  "scale_mm_per_px": 0.0125,
  "next_label_id": 7,
  "regions": {
    "1": {
      "name": "region_01",
      "vertices": [[123, 45], [130, 50], [128, 58]]
    },
    "2": { "name": "region_02", "vertices": [[...]] }
  }
}
```

- `bacmask_version`: int. **v2** drops the `mask.png` entry and makes polygons canonical. v1 bundles remain readable (see Back-compat below).
- `image_shape`: `[H, W]` of the source image. Used to rasterize polygons on load and to validate exports; cheap sanity check.
- `scale_mm_per_px`: `null` when uncalibrated ([017](017-calibration-input.md)).
- `next_label_id`: persisted so IDs stay stable across save/reload (see [014](014-lasso-tool.md) — ID stability).
- `regions`: keys are label IDs as strings (JSON requirement); values hold auto-name and polygon vertices. Vertices are integer pixel coordinates in the source image's coordinate system.

## What Save writes
- `Save` (toolbar button, `Ctrl+S`) writes **only** the bundle. No CSV, no mask files.
- One file per image: `<image_stem>.bacmask`.
- `updated_at` is refreshed on every save. `created_at` is stable after initial creation.

## What Export writes
- `Export` (separate toolbar button) writes the sibling CSV of per-region areas ([011](011-csv-for-area-output.md)) — `<image_stem>_areas.csv`.
- CSV is regenerated from polygons in memory at export time. It is never read back.
- Mask export is **not** wired to the UI ([024](024-mask-export-deferred.md)).

## Back-compat (v1 bundles)
- Bundles written before the v2 change contain a `mask.png` entry and no `image_shape` field. Readers should:
  1. Prefer polygons from `meta.json` (v1 always stored them alongside the mask).
  2. Ignore `mask.png`.
  3. Infer `image_shape` from the decoded image if missing.
- Re-saving a v1 bundle promotes it to v2 automatically.

## Why a bundle
- **Self-contained session.** Share one file; recipient resumes editing.
- **Deterministic reload.** `image + meta` covers everything.
- **Vertex preservation** for the add/subtract edit model ([023](023-edit-mode-region-boolean-edits.md)). Raster-only storage loses edit fidelity.

## Why ZIP (not a custom binary)
- Cross-platform, stdlib-only.
- Users can unzip manually to inspect — debugging-friendly.
- OS file managers preview contents without extra tooling.

## Why CSV is NOT inside the bundle
- CSV is plain text; putting it inside the ZIP hides that value.
- CSV is disposable (can be regenerated from the bundle's polygons). The bundle is the source of truth.

## Versioning
- Readers check `bacmask_version`. v1 and v2 are both accepted; unknown versions refused.
- Future versions should add a `migrate_v{N}_to_v{N+1}` helper in `core/io_manager.py`.

## Related
- [011 — CSV for Area Output](011-csv-for-area-output.md) — produced by Export.
- [014 — Lasso Tool](014-lasso-tool.md) — consumer of vertex persistence.
- [017 — Calibration Input](017-calibration-input.md) — `scale_mm_per_px` semantics.
- [024 — Mask Export (deferred)](024-mask-export-deferred.md) — downstream raster export; not part of the bundle.
- [025 — Overlapping Regions Allowed](025-overlapping-regions.md) — invariant change that justified removing the in-bundle mask.
