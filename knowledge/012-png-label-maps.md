---
id: 012
title: 16-bit PNG Label Maps (superseded)
tags: [architecture, core]
created: 2026-04-17
updated: 2026-04-19
status: superseded
related: [000, 005, 011, 015, 018, 024, 025]
---

# 16-bit PNG Label Maps (superseded)

> **Superseded by [024 — Mask Export (deferred, Python-only)](024-mask-export-deferred.md)** and [025 — Overlapping Regions Allowed](025-overlapping-regions.md).
> A single PNG label map cannot represent overlapping regions ([025](025-overlapping-regions.md)), and mask persistence has been removed from the `.bacmask` bundle ([015](015-bacmask-bundle.md)). Raster mask output is now a deferred, headless `.npy` export ([024](024-mask-export-deferred.md)). This note is retained for the rationale behind the original choice and for the decision record.

## Decision (historical)
Masks serialized as **16-bit grayscale PNG**. One file per image, named `<image_stem>_mask.png`, written to `output/masks/`.

## Rationale

### 65,535 labels is plenty
A `uint16` pixel holds values 0–65,535. `0` = background, `1..N` = colony IDs. Even a dense plate with 10,000 colonies fits comfortably.

### Lossless
PNG is lossless. Any other format (JPEG especially) would silently corrupt label IDs at compression time. Non-negotiable for training data.

### ML framework native
PyTorch, TensorFlow, Keras, and monai all load 16-bit PNGs directly via PIL/imageio without conversion. Segmentation training pipelines expect exactly this format.

### Widely supported
Every OS, every image viewer, every language. If the user ever abandons BacMask, their masks remain portable.

## Metadata policy: stateless PNG
The mask PNG is **stateless** — no `tEXt`/`iTXt` chunks, no alpha-channel metadata tricks. Scale factor, source filename, region names, and polygon vertices live in the `.bacmask` bundle's `meta.json` ([015](015-bacmask-bundle.md)) and in the sibling CSV ([011](011-csv-for-area-output.md)).

Rationale: a stateless PNG remains a pure training-data artifact — any ML pipeline loads it directly without stripping custom chunks first.

## Gotchas to guard against
- **Silent downcast to uint8.** Pillow/OpenCV can quietly save a `uint16` array as 8-bit if the save path isn't explicit. Test the I/O round-trip at the byte level — see [005 — Testing Strategy](005-testing-strategy.md).
- **Display overlay ≠ saved file.** The semi-transparent color overlay on the canvas is rendered from the label map; it is never the persisted artifact. Persisting the overlay would discard label IDs.
- **Dimension mismatch on load.** Loading a mask whose size doesn't match the current image → prompt, reject by default. See [018](018-load-mask-dim-mismatch.md).

## Why not TIFF / NPZ / HDF5?
- TIFF supports 16-bit but is less universally double-clickable in viewers, and loaders vary in quirk handling.
- NPZ / HDF5 bind the data to Python. PNG stays framework-agnostic.
- The upside of those formats (multi-channel, metadata) isn't needed — metadata lives in the CSV ([011](011-csv-for-area-output.md)).

## Related
- [011 — CSV for Area Output](011-csv-for-area-output.md) — the paired human-readable output.
- [015 — .bacmask Bundle](015-bacmask-bundle.md) — container the mask lives inside.
- [018 — Load Mask Dimension Mismatch](018-load-mask-dim-mismatch.md) — loading contract.
- [005 — Testing Strategy](005-testing-strategy.md) — round-trip test requirement.
