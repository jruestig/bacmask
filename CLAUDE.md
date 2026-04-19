# CLAUDE.md — BacMask: Bacteria Colony Masking & Area Measurement Tool

> **Deeper rationale and design notes live in [`knowledge/`](knowledge/README.md)** (Zettelkasten).
> CLAUDE.md holds scope, rules, and contracts. The knowledge base holds the **why**.
> When in doubt about a decision's motivation, read the linked note before diverging.

## Project Overview
BacMask is a cross-platform image analysis tool inspired by ImageJ, **focused exclusively**
on masking bacteria colonies in microscope/camera images and computing their areas in mm².
This is NOT a general-purpose image editor. There are no filters, color adjustments, or
unrelated tools.

The primary workflow is:
1. Load an image of bacteria colonies from disk.
2. Provide a scale factor (mm per pixel) for calibration.
3. Trace region boundaries around colonies with the lasso tool.
4. View computed areas (px and mm²) for all labeled regions.
5. Save a `.bacmask` bundle (image + mask + metadata) plus a sibling CSV of areas.

See [knowledge/000 — Project Overview](knowledge/000-project-overview.md) for the scope anchor.

## Tech Stack
- **Language:** Python 3.12 — managed via [`uv`](knowledge/019-dev-tooling.md).
- **UI Framework:** Kivy. Desktop-first MVP; Android post-MVP.
  See [knowledge/010 — Kivy over BeeWare](knowledge/010-kivy-over-beeware.md) and
  [knowledge/020 — Platform Scope](knowledge/020-platform-scope.md).
- **Image Processing:** OpenCV (`opencv-python-headless`) + NumPy.
- **Save Format:** `.bacmask` ZIP bundle — see [knowledge/015](knowledge/015-bacmask-bundle.md).
- **Sibling CSV** for areas — see [knowledge/011](knowledge/011-csv-for-area-output.md).
- **Mask Storage:** masks are no longer persisted — polygons are canonical ([knowledge/015](knowledge/015-bacmask-bundle.md), [knowledge/025](knowledge/025-overlapping-regions.md)). Historical PNG label-map rationale: [knowledge/superseded/012](knowledge/superseded/012-png-label-maps.md).
- **Formatter/Linter:** `ruff`. See [knowledge/019 — Dev Tooling](knowledge/019-dev-tooling.md).

## Architecture
Authoritative directory layout, layer separation, state management, undo/redo,
performance rules, testing strategy, config, and logging are documented in the
knowledge base. Start here:

- [knowledge/README.md](knowledge/README.md) — index
- [knowledge/008 — Directory Layout (authoritative)](knowledge/008-directory-layout.md)
- [knowledge/001 — Separation of Concerns](knowledge/001-separation-of-concerns.md)
- [knowledge/002 — State Management](knowledge/002-state-management.md)
- [knowledge/003 — Undo/Redo via Command Pattern](knowledge/003-undo-redo-commands.md)
- [knowledge/004 — Performance on Large Images](knowledge/004-performance-large-images.md)
- [knowledge/005 — Testing Strategy](knowledge/005-testing-strategy.md)
- [knowledge/006 — Configuration Management](knowledge/006-configuration-management.md)
- [knowledge/007 — Logging](knowledge/007-logging.md)
- [knowledge/016 — Input Abstraction Layer](knowledge/016-input-abstraction.md)
- [knowledge/superseded/023 — Edit Mode & Region Boolean Edits](knowledge/superseded/023-edit-mode-region-boolean-edits.md) *(superseded by 026)*
- [knowledge/024 — Mask Export (deferred, Python-only)](knowledge/024-mask-export-deferred.md)
- [knowledge/025 — Overlapping Regions Allowed](knowledge/025-overlapping-regions.md)
- [knowledge/026 — Brush Edit Model (Shift add / Ctrl subtract)](knowledge/026-brush-edit-model.md)
- [knowledge/027 — Toolbar Hotkey Labels](knowledge/027-toolbar-hotkey-labels.md)
- [knowledge/028 — File Picker Double-Click to Open](knowledge/028-file-picker-double-click.md)

## Core Concepts (contracts)

### Masks
- **Polygons are canonical.** Each region is fully specified by `label_id`, `name`, and an ordered `vertices` list. Everything mask-related is derived from the polygon set.
- **Regions may overlap.** A pixel can belong to any number of regions ([knowledge/025](knowledge/025-overlapping-regions.md)). There is no single owner; there is no stored label map. Display rendering and click-select resolve overlap by highest `label_id` (newest on top).
- IDs are **monotonic and never re-used** after deletion ([knowledge/014](knowledge/014-lasso-tool.md)).
- The `.bacmask` bundle stores only `image.<ext>` + `meta.json` ([knowledge/015](knowledge/015-bacmask-bundle.md)). No raster mask on disk.
- Raster masks for segmentation training are produced by a **deferred, headless export** — a Python function that greedy-packs polygons into layered `uint16` `.npy` files. Not wired to the UI; not MVP ([knowledge/024](knowledge/024-mask-export-deferred.md)).

### Calibration
- The user provides a **scale factor** in mm per pixel via a text input field.
- The scale is stored per-session and persisted in the bundle's `meta.json`.
- If the field is empty, the session is **uncalibrated** — area is still computed in px,
  and `area_mm2` + `scale_factor` CSV cells are empty strings.
- See [knowledge/017 — Calibration Input Model](knowledge/017-calibration-input.md).

### Area Calculation
```
area_mm2 = pixel_count * (scale_factor_mm_per_px ** 2)
```
- Area is reported for **every** labeled region — no filtering, no truncation.

### Save vs. Export (two separate actions)

**Save** (`Ctrl+S` / toolbar button) writes the bundle only:

- **`<image_stem>.bacmask`** — ZIP with:
  - `image.<ext>` (original bytes)
  - `meta.json` (v2 schema: scale, region vertices + names, next_label_id, image_shape)
  - No raster mask.

**Export** (separate toolbar button) writes the areas CSV:

- **`<image_stem>_areas.csv`** — locked column order:
  ```
  filename, region_id, region_name, area_px, area_mm2, scale_factor
  ```
  One row per region; areas computed from polygons. Overwrite on re-export.
  `area_px` is per-region and inclusive of any overlap — a shared pixel is counted once per region that contains it.

**Mask export** for training is a separate, non-UI Python operation ([knowledge/024](knowledge/024-mask-export-deferred.md)) — deferred; not MVP.

Details: [knowledge/015](knowledge/015-bacmask-bundle.md), [knowledge/011](knowledge/011-csv-for-area-output.md), [knowledge/025](knowledge/025-overlapping-regions.md).

## UI/UX Requirements

1. **Image Canvas:**
   - Displays the loaded image **in original color** with mask overlay (semi-transparent, color-coded per region).
   - Supports pan and zoom (wheel zoom on desktop; touch gestures post-MVP).
   - **Masks remain visible at all times.** They are never auto-hidden or cleared.
     The user must explicitly clear or delete them.

2. **Masking Tools (two primitives — see [knowledge/013](knowledge/013-minimal-toolset.md)):**
   - **Lasso (`L`)** — creates new regions ([knowledge/014](knowledge/014-lasso-tool.md)). Press-drag to trace an outline; release to close. The stored polygon is re-derived from the rasterized stroke via `largest_connected_component` + `findContours` so the shape is always a clean simple closed curve (no random closing chord).
     - Keyboard close: `Enter` (equivalent trigger for stylus loss-of-contact).
     - Cancel in-progress lasso: `Escape`.
     - Lassos with fewer than 3 points or zero enclosed area are silently discarded.
   - **Brush (`B`)** — three modes ([knowledge/026](knowledge/026-brush-edit-model.md)). Select the brush tool, then press-drag:
     - Mode is set via the **Create** / **Add** / **Subtract** toggles in the brush panel and cycled with **`Tab`** (order: create → add → subtract).
     - **Create** mode: press-drag-release commits a brand-new region built from the painted blob. Press-down location is irrelevant — the brush ignores any existing region under the cursor.
     - **Add / Subtract** modes target an existing region. The target locks at press-down: a hit on a region selects + targets it; press-down on background uses the currently selected region as target. This lets a subtract begin off the boundary and carve in from outside.
     - In add/subtract with no selected region, press on background is a no-op.
     - If a subtract empties the region entirely, the edit resolves as a Delete.
     - Overlap with other regions is allowed — edits are strictly per-target ([knowledge/025](knowledge/025-overlapping-regions.md)).
     - Brush radius is a session-local scalar in a toolbar numeric field (default 8 px, image-space).
   - **Delete region (`Delete` / `Backspace`):** select region → delete key or toolbar button. Label ID is NOT re-used.
   - No eraser tool (use `Ctrl`-brush), no flood fill, no threshold, no smart-select.

   Every toolbar button displays its keyboard shortcut in its label ([knowledge/027](knowledge/027-toolbar-hotkey-labels.md)).

3. **Results Panel:**
   - Scrollable table showing: Region ID | Name | Area (px) | Area (mm²)
   - Updates live as regions are created, edited, or deleted.
   - Full set of regions always visible — do not paginate or truncate.

4. **File Operations:**
   - **Load Image (`Ctrl+O`):** file picker, accepts common formats (PNG, JPG, TIFF, BMP). File upload only — no camera, no URL. Double-click on a file in the picker opens it ([knowledge/028](knowledge/028-file-picker-double-click.md)).
   - **Load Bundle:** `.bacmask` → restore image + polygons + scale. Rasterization happens in memory from polygons; no in-bundle mask to reconcile. Double-click opens, same as Load Image.
   - **Save (`Ctrl+S`):** writes only the `.bacmask` bundle.
   - **Export CSV (`Ctrl+E`):** writes only the areas CSV. Separate button from Save.

5. **Input abstraction:**
   - All gestures go through a semantic input layer so desktop↔touch profiles can be swapped
     without changes to core/services. See [knowledge/016](knowledge/016-input-abstraction.md).

## Key Behavioral Rules

- **DO NOT** build any image editing features (brightness, contrast, crop, rotate, filters).
- **DO NOT** build flood fill, threshold, or magic-select tools. The two primitives are lasso (create) and brush (edit) — nothing else.
- **DO NOT** let the brush create regions. Press-down on background must be a no-op. New-region creation is the lasso's exclusive job ([knowledge/026](knowledge/026-brush-edit-model.md)).
- **DO NOT** auto-close, auto-hide, or reset masks after saving. Masks stay on the canvas
  until the user explicitly clears them or loads a new image.
- **DO NOT** re-use a region's label ID after deletion. Monotonic IDs only.
- **DO NOT** add features beyond masking and area measurement. This tool has one job.
- **DO NOT** hide keyboard shortcuts behind a help overlay — every shortcut must appear in its button's label ([knowledge/027](knowledge/027-toolbar-hotkey-labels.md)).
- **DO** keep the UI minimal and focused. Every element serves the
  trace → label → measure → save workflow.
- **DO** ensure persistence is deterministic — same polygons + same creation order = bit-identical bundle (`meta.json` + `image.<ext>`) and exported CSV. Same contract applies to the deferred mask export ([knowledge/024](knowledge/024-mask-export-deferred.md)) when implemented.
- **DO** write unit tests for all core logic (rasterization, area, bundle I/O, CSV export, undo/redo).
- **DO** handle edge cases gracefully:
  - Self-intersecting lasso polygon → rasterize per `cv2.fillPoly` even-odd rule; document in tests.
  - Lasso with zero enclosed area → warn, don't create a zero-area region.
  - Missing calibration → warn user, still allow saving; CSV `area_mm2` + `scale_factor` are empty strings.
  - Very large images → downsample for display, but compute areas on full resolution.
  - Overlapping regions are allowed — treat per-region masks independently ([knowledge/025](knowledge/025-overlapping-regions.md)).

## Cross-Platform Notes

- **Linux/Windows (MVP targets):** Run with `uv run python main.py`. Packaging with PyInstaller optional.
- **macOS:** not validated in MVP.
- **Android (post-MVP):** Buildozer, touch adapter, SAF file access — deferred. See [knowledge/020](knowledge/020-platform-scope.md).

## Dependencies

Declared in `pyproject.toml` (managed via `uv`). See [knowledge/019](knowledge/019-dev-tooling.md).

Runtime:
```
kivy>=2.3.0
opencv-python-headless>=4.9.0
numpy>=1.26.0
Pillow>=10.0.0
```

Dev:
```
pytest
pytest-cov
ruff
```

No other dependencies. Keep it lean.

## Definition of Done (MVP)

> **Status (2026-04-19):** all items are functionally implemented except the Windows-run validation. Boxes below reflect code state — re-check by running `pytest` + `ruff check` + `ruff format --check`, and by doing a live smoke run in a Kivy window. Update this block when items change.

- [x] User can load an image from disk via file picker (shown in original color).
- [x] User can input a scale factor (mm per pixel); empty = uncalibrated.
- [x] User can trace a closed boundary around a colony with the lasso tool (release to close; `Enter` as equivalent explicit trigger). Stored polygon is the cleaned raster contour, not the raw scribble.
- [x] User can edit an existing region's boundary with the brush tool. Mode (Create / Add / Subtract) is a persistent toolbar toggle cycled with `Tab` ([knowledge/026](knowledge/026-brush-edit-model.md)). In add/subtract the target locks at press-down — press on a region targets it; press on background uses the selected region, letting subtract carve in from outside. Overlap with other regions is allowed.
- [x] User can delete a region; its label ID is not re-used. A subtract-mode brush stroke that empties a region resolves as a Delete.
- [x] All region areas (px and mm²) are displayed in a results panel, updating live.
- [x] Masks persist on the canvas — they never auto-disappear.
- [x] **Save** writes `<image_stem>.bacmask` (bundle only, no mask, no CSV).
- [x] **Export** writes `<image_stem>_areas.csv` (CSV only).
- [x] Bundle can be reloaded for a given image and restores regions + scale + IDs exactly (polygons canonical). Double-click on a file in the picker opens it.
- [x] CSV is directly human-readable with the locked column schema.
- [x] Undo / redo works for lasso close, brush stroke, and delete, with a bounded history.
- [x] Every toolbar button label includes its keyboard shortcut.
- [ ] App runs on Linux and Windows. *(Linux verified; Windows validation deferred — `packaging/bacmask.spec` exists but no built/tested `.exe` yet.)*
- [x] Unit tests pass for core logic (rasterization, area, bundle I/O, CSV, undo/redo, calibration).
- [x] `ruff check` and `ruff format --check` pass.
