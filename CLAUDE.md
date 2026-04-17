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
- **Mask Storage:** 16-bit grayscale PNG label map inside the bundle — see [knowledge/012](knowledge/012-png-label-maps.md).
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

## Core Concepts (contracts)

### Masks
- Each region gets a **unique integer label** in a single label map (dtype: `uint16`).
- Label map has the same dimensions as the source image.
- On disk, the mask lives inside a `.bacmask` ZIP bundle as `mask.png` (16-bit grayscale).
- IDs are **monotonic and never re-used** after deletion ([knowledge/014](knowledge/014-lasso-tool.md)).
- These mask files are intended for **later use as training data** for segmentation models.
  They must be clean, deterministic, and reproducible.

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

### Save Artifacts
Two files per image on Save All:

1. **`<image_stem>.bacmask`** — ZIP bundle with:
   - `image.<ext>` (original bytes)
   - `mask.png` (16-bit grayscale label map)
   - `meta.json` (scale, region vertices, region names, next_label_id)
2. **`<image_stem>_areas.csv`** — human-readable CSV with locked column order:
   ```
   filename, region_id, region_name, area_px, area_mm2, scale_factor
   ```
   One row per region. Overwrite on re-save.

Details: [knowledge/015](knowledge/015-bacmask-bundle.md), [knowledge/011](knowledge/011-csv-for-area-output.md).

## UI/UX Requirements

1. **Image Canvas:**
   - Displays the loaded image **in original color** with mask overlay (semi-transparent, color-coded per region).
   - Supports pan and zoom (wheel zoom on desktop; touch gestures post-MVP).
   - **Masks remain visible at all times.** They are never auto-hidden or cleared.
     The user must explicitly clear or delete them.

2. **Masking Tools (exactly one primitive — see [knowledge/013](knowledge/013-minimal-toolset.md), [knowledge/014](knowledge/014-lasso-tool.md)):**
   - **Lasso:** press-drag to trace the outline of a region. On close, the interior is
     filled with the next free label ID.
     - Auto-close when the live endpoint reaches within ε pixels of the start (default 10 px).
     - Keyboard close: `Enter` snaps last→first.
     - Cancel in-progress lasso: `Escape`.
   - **Vertex editing:** click an existing region's boundary to reveal handles; drag to edit.
     Double-click a segment to insert a vertex; double-click a handle to remove it.
   - **Delete region:** select region → `Delete` key or toolbar button. Label ID is NOT re-used.
   - No brush, no eraser, no flood fill, no threshold, no smart-select.

3. **Results Panel:**
   - Scrollable table showing: Region ID | Name | Area (px) | Area (mm²)
   - Updates live as regions are created, edited, or deleted.
   - Full set of regions always visible — do not paginate or truncate.

4. **File Operations:**
   - **Load Image:** file picker, accepts common formats (PNG, JPG, TIFF, BMP).
     File upload only — no camera, no URL.
   - **Load Bundle:** `.bacmask` → restore image + mask + regions + scale.
   - **Save All:** writes both the `.bacmask` bundle and the sibling CSV in one action.
   - **Load Mask (dimension mismatch):** prompt, **reject by default**. See [knowledge/018](knowledge/018-load-mask-dim-mismatch.md).

5. **Input abstraction:**
   - All gestures go through a semantic input layer so desktop↔touch profiles can be swapped
     without changes to core/services. See [knowledge/016](knowledge/016-input-abstraction.md).

## Key Behavioral Rules

- **DO NOT** build any image editing features (brightness, contrast, crop, rotate, filters).
- **DO NOT** build brush / eraser / flood fill / threshold / magic-select tools — lasso is the only primitive.
- **DO NOT** auto-close, auto-hide, or reset masks after saving. Masks stay on the canvas
  until the user explicitly clears them or loads a new image.
- **DO NOT** re-use a region's label ID after deletion. Monotonic IDs only.
- **DO NOT** add features beyond masking and area measurement. This tool has one job.
- **DO** keep the UI minimal and focused. Every element serves the
  trace → label → measure → save workflow.
- **DO** ensure saved masks are deterministic — same image + same vertices = bit-identical `mask.png` and CSV.
- **DO** write unit tests for all core logic (rasterization, area, I/O, bundle round-trip, undo/redo).
- **DO** handle edge cases gracefully:
  - Self-intersecting lasso polygon → rasterize per `cv2.fillPoly` even-odd rule; document in tests.
  - Lasso with zero enclosed area → warn, don't create a zero-area region.
  - Missing calibration → warn user, still allow saving; CSV `area_mm2` + `scale_factor` are empty strings.
  - Very large images → downsample for display, but compute areas on full resolution.
  - Mask dimensions don't match image on load → prompt (reject by default).

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

- [ ] User can load an image from disk via file picker (shown in original color).
- [ ] User can input a scale factor (mm per pixel); empty = uncalibrated.
- [ ] User can trace a closed boundary around a colony with the lasso tool (auto-close + `Enter`).
- [ ] User can edit an existing region's boundary via vertex handles.
- [ ] User can delete a region; its label ID is not re-used.
- [ ] All region areas (px and mm²) are displayed in a results panel, updating live.
- [ ] Masks persist on the canvas — they never auto-disappear.
- [ ] "Save All" writes `<image_stem>.bacmask` + `<image_stem>_areas.csv`.
- [ ] Bundle can be reloaded for a given image and restores regions + scale + IDs exactly.
- [ ] CSV is directly human-readable with the locked column schema.
- [ ] Undo / redo works for lasso close, vertex edit, and delete, with a bounded history.
- [ ] App runs on Linux and Windows.
- [ ] Unit tests pass for core logic (rasterization, area, bundle I/O, CSV, undo/redo, calibration).
- [ ] `ruff check` and `ruff format --check` pass.
