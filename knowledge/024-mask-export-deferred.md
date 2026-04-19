---
id: 024
title: Mask Export (deferred, Python-only)
tags: [architecture, core]
created: 2026-04-19
status: proposed
related: [002, 012, 015, 023, 025]
---

# Mask Export (deferred, Python-only)

Masks are no longer stored inside `.bacmask` bundles. Polygons are canonical (see [002](002-state-management.md), [015](015-bacmask-bundle.md)). Producing raster masks for downstream training is a **separate, headless, on-demand operation** — out of scope for the MVP UI.

This note locks the format contract so when the exporter is built it lands in a predictable shape.

## Scope boundary
- **Not** in the UI. No button, no menu, no file dialog.
- **Not** called by `Save` or `Export` (those only touch the bundle and the CSV).
- **Not** in the MVP deliverable list — intentionally deferred.
- Is a **pure Python function** callable from a script, notebook, or future CLI. No dependency on `MaskService`, `kivy`, or any widget.

## Placement (when implemented)
`bacmask/services/mask_export.py` — fits the services layer ([001](001-separation-of-concerns.md)). A future CLI wrapper can live in `bacmask/cli/` without touching the UI.

## Signature

```python
def export_masks(bundle_path: Path, out_dir: Path) -> ExportResult: ...
```

- `bundle_path`: existing `.bacmask` file.
- `out_dir`: directory to write into. Created if missing.
- Returns a small dataclass: layer count, per-layer label-id lists, manifest path.

No UI callback, no observer, no side effects beyond the filesystem.

## Output layout
For a bundle `plate_42.bacmask`:

```
<out_dir>/plate_42_masks/
├── mask_00.npy
├── mask_01.npy            # present only if overlaps forced a second layer
├── mask_02.npy            # ... etc.
└── layers.json
```

- File count = number of layers produced by the greedy packer. Most bundles → 1 file.
- Re-running the exporter overwrites; behavior is idempotent given identical inputs.

## `.npy` format
- `np.save` via NumPy's v1 format — no pickle, no compression.
- `dtype=np.uint16`.
- `shape=(H, W)` — same as the source image.
- Values: `0` = background; every other pixel = the `label_id` of whichever region owns that pixel *in this layer*. No shared pixels within a layer — that's the whole point of layering.
- `np.save` on identical input produces byte-identical output. Determinism is a contract.

## layers.json manifest

```json
{
  "bacmask_version": 2,
  "image_filename": "plate_42.tif",
  "image_shape": [1024, 1024],
  "scale_mm_per_px": 0.0125,
  "layers": [
    {"file": "mask_00.npy", "label_ids": [1, 2, 3, 4, 7]},
    {"file": "mask_01.npy", "label_ids": [5, 6]}
  ]
}
```

Downstream consumers read only `layers.json` + the `.npy` files. They don't parse `meta.json` from the bundle. The manifest is the export contract.

## Greedy layered packing
1. Load polygons from `meta.json`. Rasterize each region's polygon into its own `HxW` `bool` mask via `cv2.fillPoly`.
2. Sort regions by ascending `label_id` (creation order — deterministic).
3. For each region in order:
   - Walk existing layers in index order. Place the region in the first layer whose occupied pixels don't intersect this region's pixels.
   - If no layer fits, open a new layer at the end.
4. Within each layer, fill `uint16[label_id]` at the region's pixels. Intra-layer fill order is ascending `label_id` for byte-identical output (doesn't affect pixel values since a layer is disjoint by construction).
5. Write each layer array with `np.save`.
6. Write `layers.json` with the manifest above.

Typical colony image: 1 layer. Occasional two-region overlap: 2 layers. Rare triple overlap: 3. No hard cap.

## Edge cases
- **Zero regions.** `layers` array is empty. `layers.json` still written. No `.npy` files.
- **All regions disjoint.** One layer. `mask_00.npy` matches what the old in-bundle `mask.png` would have contained (pre-overlap architecture).
- **N mutually overlapping regions.** N layers. Documented consequence of the greedy packer; no attempt to minimize via graph coloring beyond the greedy heuristic.
- **Empty polygons** (shouldn't exist post-validation but possible from malformed bundles): skip with a warning; do not add to any layer.

## Not in MVP
- UI wiring (no button).
- User-specified `out_dir` via a file picker.
- CLI wrapper (`bacmask-export-masks`).
- Alternate formats (PNG, TIFF, NPZ, multi-channel HDF5).
- Batch mode over directories.
- Streaming / chunked writes for giant images.

All of these are straightforward additions on top of the pure function when the need arises.

## Related
- [015 — .bacmask Bundle Format](015-bacmask-bundle.md) — bundle is the exporter's input.
- [002 — State Management](002-state-management.md) — polygons canonical.
- [023 — Edit Mode & Region Boolean Edits](superseded/023-edit-mode-region-boolean-edits.md) — the editing model that allows overlaps.
- [012 — 16-bit PNG Label Maps](superseded/012-png-label-maps.md) — superseded; explains why PNG was the original choice and why `.npy` is better for the deferred, headless use case.
