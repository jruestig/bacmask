---
id: 009
title: Deviations from CLAUDE.md Sketch
tags: [architecture, meta]
created: 2026-04-17
status: accepted
related: [001, 002, 003, 006, 007, 008]
---

# Deviations from CLAUDE.md Sketch

The directory tree in `CLAUDE.md` was a first sketch. [008](008-directory-layout.md) is now authoritative. This note enumerates the diffs so nothing gets lost in translation.

## Additions

### New `services/` layer
`CLAUDE.md` had `core/` + `ui/` only. Added an explicit orchestration layer to keep UI widgets dumb and core pure. See [001](001-separation-of-concerns.md).

### New `core/` modules
- `state.py` — centralized session state ([002](002-state-management.md)).
- `commands.py` + `history.py` — command pattern + bounded undo/redo stack ([003](003-undo-redo-commands.md)).
- `validators.py` — explicit input validation module.
- `calibration.py` — split scale logic out of area/io.

### New `config/` package
- `config.yaml` + `config/defaults.py` + `config/config_loader.py` ([006](006-configuration-management.md)).

### New `utils/logger.py`
Centralized logging setup ([007](007-logging.md)).

### UI reorganization
`ui/` now has `screens/` + `widgets/` + `styles/` subdirs instead of flat files.

### Test tree mirrors source
`tests/core/`, `tests/services/`, `tests/fixtures/` — was flat `tests/*.py` in CLAUDE.md.

### New build/dev files
- `requirements-dev.txt` — pytest, flake8, mypy.
- `pyproject.toml` — project metadata + tool configs.

## Renames
- `core/io.py` → `core/io_manager.py` (avoids shadowing stdlib `io`).

## Removals
None.

## Why keep this note
If someone reads `CLAUDE.md` first and wonders why the real tree has extra packages, this is the answer. Do not delete `CLAUDE.md`'s sketch — it's still a useful high-level summary for the north-star description of the project.

## Follow-up (resolved 2026-04-17)
`CLAUDE.md`'s inline directory tree was removed and replaced with a pointer to [008](008-directory-layout.md). Rationale paragraphs (Kivy, CSV, PNG, minimal toolset) were extracted into dedicated notes ([010](010-kivy-over-beeware.md), [011](011-csv-for-area-output.md), [012](012-png-label-maps.md), [013](013-minimal-toolset.md)). Behavioral rules, core-concept contracts, cross-platform notes, and definition-of-done remain in `CLAUDE.md`.

## Round 5 updates (resolved 2026-04-19, overlap + bundle simplification)
- **Overlaps allowed.** Regions may share pixels. New note: [025](025-overlapping-regions.md). Supersedes the disjoint-regions invariant and the clip rule in [021](021-vertex-edit-collision.md).
- **Polygons are canonical.** `regions` dict (vertex lists) is the source of truth. In-memory per-region binary masks + a label-map display cache are derived; neither is persisted. [002](002-state-management.md) revised.
- **Bundle v2 drops the mask.** `.bacmask` = `image.<ext>` + `meta.json` only. `bacmask_version` bumped to 2; v1 remains readable (its `mask.png` is ignored on load). [015](015-bacmask-bundle.md) rewritten; [012](012-png-label-maps.md) and [018](018-load-mask-dim-mismatch.md) marked `superseded`.
- **Save / Export split in the UI.** `Save` writes only the bundle. `Export` (separate button) writes the areas CSV. No mask files touched by either action. [013](013-minimal-toolset.md) revised.
- **Mask export deferred and UI-free.** A pure Python function (future location: `bacmask/services/mask_export.py`) will produce layered `uint16` `.npy` files via greedy packing + a `layers.json` manifest. Not wired to the UI; not MVP. Format contract recorded in [024](024-mask-export-deferred.md).
- **Click-select tiebreak on overlap** = highest `label_id` wins (newest on top). Documented in [025](025-overlapping-regions.md).
- **Edit-mode "inside" check** now reads the target's own binary mask, not the label-map cache. [023](023-edit-mode-region-boolean-edits.md) revised.
- **CLAUDE.md** §Core Concepts §Masks, §Save Artifacts, §Definition of Done rewritten to match.

## Round 4 updates (resolved 2026-04-19, vertex-edit UI design)
- **Vertex editing model replaced.** The handle-drag / double-click-insert / double-click-remove model in early drafts of [014](014-lasso-tool.md) was dropped before implementation. MVP edits regions by drawing a second lasso against an existing target: start inside → add a lobe; start outside → subtract a bite. Spec: [023](023-edit-mode-region-boolean-edits.md). [014](014-lasso-tool.md) rewritten to point at 023.
- **Edit mode toggle.** New toolbar button + `e` hotkey gate edit strokes. Off = create-only. On = target + edit-stroke interactions.
- **Command rename.** `VertexEditCommand` → `RegionEditCommand(label_id, old_vertices, new_vertices, old_mask_patch)`. [003](003-undo-redo-commands.md) updated.
- **State additions.** `edit_mode: bool` on `SessionState`; `selected_region_id` doubles as edit target. [002](002-state-management.md) updated.
- **Collision policy scope clarified.** [021](021-vertex-edit-collision.md) renamed from "Vertex-Edit Collision Policy" to "Edit Collision Policy"; applies to add strokes now, not handle drags.
- **CLAUDE.md** §Masking Tools + §Definition of Done revised to match.

## Round 3 updates (resolved 2026-04-18, post first-impl review)
- **Lasso close trigger simplified.** MVP closes on pointer release; `Enter` kept as equivalent explicit-close trigger for devices without clean release. ε-proximity auto-close during drag was specced in an earlier draft but the release-based mechanism is sufficient and already shipped in `93992ab`. `LASSO_CLOSE_THRESHOLD_PX` remains reserved in `config/defaults.py` for a future snap-preview affordance but is not a close trigger. [014](014-lasso-tool.md) and CLAUDE.md §Masking Tools revised to match.

## Round 2 updates (resolved 2026-04-17, post-spec session)
Based on user's answers to the open-questions list, the following behavioral and scope changes were applied:

- **Tool model shift.** Brush + eraser + flood fill dropped. Lasso (boundary draw + vertex editing + delete) is the single MVP primitive. Notes: [013](013-minimal-toolset.md) rewritten, [014](014-lasso-tool.md) added.
- **Save format.** `.bacmask` ZIP bundle containing `image.<ext>`, `mask.png`, `meta.json` — sibling CSV for human-readable bookkeeping. Note: [015](015-bacmask-bundle.md) added.
- **Input decoupling.** New input-abstraction layer at `ui/input/` — semantic events not raw Kivy events. Note: [016](016-input-abstraction.md) added.
- **Calibration.** mm-per-pixel input only; uncalibrated rows have empty `area_mm2` + `scale_factor` cells. Note: [017](017-calibration-input.md) added.
- **Load dim mismatch.** Prompt with reject-default. Note: [018](018-load-mask-dim-mismatch.md) added.
- **Dev tooling.** Python 3.12, `uv` for env, `ruff` for lint+format. Note: [019](019-dev-tooling.md) added; `requirements*.txt` removed in favor of `pyproject.toml` + `uv.lock`.
- **Platform scope.** Desktop-first MVP; Android post-MVP. Note: [020](020-platform-scope.md) added.
- **CSV schema changed.** New columns: `filename, region_id, region_name, area_px, area_mm2, scale_factor`. [011](011-csv-for-area-output.md) revised.
- **State + command naming updated** for lasso model: `LassoCloseCommand`, `VertexEditCommand`, `DeleteRegionCommand`. [002](002-state-management.md), [003](003-undo-redo-commands.md), [008](008-directory-layout.md) revised.
- **CLAUDE.md updated** to reflect all of the above — Masking Tools, Key Behavioral Rules, Definition of Done, Dependencies sections rewritten.
