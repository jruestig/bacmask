---
id: 015
title: .bacmask Bundle Format
tags: [architecture, core]
created: 2026-04-17
status: accepted
related: [011, 012, 014, 017]
---

# .bacmask Bundle Format

Primary project save artifact. Contains everything needed to resume editing. A sibling CSV ([011](011-csv-for-area-output.md)) is also written as human-readable double-bookkeeping.

## Container
A **ZIP archive** with extension `.bacmask`. Uses Python's stdlib `zipfile` — zero extra deps.

## Contents

```
project.bacmask/
├── image.<ext>      # original image, preserved byte-for-byte
├── mask.png         # 16-bit grayscale label map (see 012)
└── meta.json        # session metadata (schema below)
```

- `image.<ext>` keeps its source extension (`.tif`, `.png`, `.jpg`, …) and byte contents — no re-encoding.
- `mask.png` is bit-identical to what the standalone mask PNG would be for this image.

## meta.json schema (bacmask_version 1)

```json
{
  "bacmask_version": 1,
  "source_filename": "20251112093808947.tif",
  "created_at": "2026-04-17T15:42:11Z",
  "updated_at": "2026-04-17T16:10:55Z",
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

- `bacmask_version`: int, bumped on breaking schema changes.
- `scale_mm_per_px`: `null` when uncalibrated ([017](017-calibration-input.md)).
- `next_label_id`: persisted so IDs stay stable across save/reload (see [014](014-lasso-tool.md) — ID stability).
- `regions`: keys are label IDs as strings (JSON requirement); values hold auto-name and polygon vertices.

## Why a bundle
- **Self-contained session.** Share one file; recipient sees exactly what the author saw.
- **Deterministic reload.** `image + mask + meta` covers everything needed to resume editing.
- **Vertex preservation** for lasso editing after reload ([014](014-lasso-tool.md)). Raster-only storage would lose boundary fidelity.

## Why ZIP (not a custom binary)
- Cross-platform, stdlib-only.
- Users can unzip manually to inspect — debugging-friendly.
- OS file managers preview contents without extra tooling.

## Why CSV is NOT inside the bundle
- CSV is plain text; putting it inside the ZIP hides that value.
- CSV is disposable (can be regenerated from bundle). The bundle is the source of truth.

## Versioning
- Readers must check `bacmask_version` and refuse or migrate unknown versions.
- MVP only writes v1. Future versions should add a `migrate_v{N}_to_v{N+1}` helper in `core/io_manager.py`.

## Related
- [011 — CSV for Area Output](011-csv-for-area-output.md) — sibling artifact.
- [012 — 16-bit PNG Label Maps](012-png-label-maps.md) — mask format inside the bundle.
- [014 — Lasso Tool](014-lasso-tool.md) — consumer of vertex persistence.
- [017 — Calibration Input](017-calibration-input.md) — `scale_mm_per_px` semantics.
