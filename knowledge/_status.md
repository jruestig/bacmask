# Status — 2026-04-19 (session 3 update)

Session-handoff doc. Updated at the end of each working session. What follows `knowledge/` conventions — kept short on purpose.

## Currently working on
- Nothing in flight at end of session. First live UI smoke pass done — a few small fit-and-finish items found and fixed below.

## In progress (started, not done)
- Nothing half-done.

## Blocked (waiting on external input or deferred decisions)
- **Mask export output location + CLI.** User wants to pick `out_dir` and a CLI wrapper "later." Format contract is locked ([024](024-mask-export-deferred.md)); placement and ergonomics deferred.
- **Windows smoke test.** Needs a Windows machine; not arranged.
- **macOS validation.** Not an MVP target, intentionally deferred ([020](020-platform-scope.md)).

## Next actions (concrete, ordered)
1. **More live-UI passes.** Keep exercising real images. Known polish candidates:
   - Distinct color/style for the edit-stroke preview (green for add, red for subtract) once mode can be inferred client-side.
   - Click feedback or row highlight when selecting via canvas tap.
2. **Windows smoke test.** Needs a Windows box.
3. **Mask export** (`bacmask/services/mask_export.py`). Headless `export_masks(bundle_path, out_dir)` per [024](024-mask-export-deferred.md). Not UI-wired. Deferred until someone has a concrete training pipeline to consume the layered `.npy` output.
4. **CLI wrapper for mask export** + user-chosen `out_dir`. After item 3.
5. **Region rename.** Users can't change `region_01` / `region_02` names today. Add an inline edit in the results panel. Post-MVP.
6. **Numeric input polish** — calibration field accepts units other than mm/px? Not in spec, ignore for now.

## Recently completed (last ~3 sessions)
- **Live UI polish (session 3).**
  - **Zoomed image no longer covers toolbar/calibration.** Added a Kivy stencil in `ImageCanvas._repaint`. Rectangle extends very far in x (both sides) and downward, but caps at `self.top` — toolbar + calibration above stay visible; image can still bleed horizontally into the results panel on the right and downward (matching pre-stencil behavior the user prefers).
  - **Results panel stays on the right.** Brief detour moving it above the canvas; reverted. Layout is unchanged from pre-session: toolbar → calibration → body (canvas left, results 30% right).
  - **Overlay alpha-over compositing for overlapping regions.** `_rebuild_overlay_texture` now iterates `region_masks` in ascending label order and alpha-blends each region's color on top of the running accumulator (straight-alpha Porter-Duff "over"). Non-overlapping pixels render identical to before (single color at 0.45 alpha). Overlap pixels mix: newer region weighted heavier, older region's color still visible underneath — supports knowledge/025's "you should be able to see both regions" user expectation.
- **Core data-model refactor (session 2).**
  - **State.** Added `region_masks: dict[int, np.ndarray]` (bool per region) to `SessionState`. Polygons in `regions` are canonical; `label_map` is now a derived display cache painted in ascending `label_id` order so newest-on-top wins overlap. `masking.py` gained `rasterize_polygon_mask` + `repaint_label_map`. All commands (LassoClose, Delete, VertexEdit) maintain both stores; `compute_area_rows` counts `region_masks[id]` (overlap-inclusive). `load_bundle` rasterizes polygons to populate both. (`knowledge/002`, `knowledge/025`)
  - **Bundle v2 format** (agent). `.bacmask` now contains `image.<ext>` + `meta.json` only; no `mask.png`. `meta.json` has `bacmask_version: 2` + `image_shape`. v1 bundles still loadable — `mask.png` is ignored. Re-saving promotes to v2 automatically. Dropped `save_mask_png` / `load_mask_png` / `load_mask_for_image` / `MaskDimensionMismatch`. (`knowledge/015`)
  - **RegionEditCommand + add/subtract stroke algorithm** (agent). Implements `knowledge/023` fully: first-two-boundary-crossings truncation, straight-line close of the truncated segment, `target ∪ S` / `target \ S`, largest-CC filter with smallest-`(y, x)` tiebreak, re-derive vertices via `cv2.findContours`. `masking.py` gained `find_boundary_crossings`, `rasterize_stroke_polygon`, `largest_connected_component`, `contour_vertices`. `MaskService.edit_region_stroke(target_id, samples)` returns `"added"` / `"subtracted"` / `"deleted"` / `None`; subtract-empties-region routes through `DeleteRegionCommand`. No neighbor clipping — overlap is preserved per `knowledge/025`.
  - **Canvas edit-mode wiring.** `ImageCanvas._on_input` branches on `state.edit_mode`. Create mode: existing tap-selects / drag-starts-lasso. Edit mode: double-tap retargets (or clears on bg); single tap when no target sets first target; press-drag with target accumulates samples via the existing `active_lasso` buffer and dispatches `edit_region_stroke` + `cancel_lasso` on release. `PointerDown` gained `is_double: bool`; `DesktopInputAdapter` forwards `touch.is_double_tap`.
  - **Suite.** 137 → 172 passing. New tests: 13 masking helpers, 5 RegionEditCommand, 9 service edit-stroke, 8 canvas edit routing. Ruff + format clean.
- **Save/Export UI split.** `Save` writes only the bundle; new `Export CSV` button writes only the areas CSV. Service exposes `save_bundle` + `export_csv` (replacing `save_all`). `Ctrl+E` binds export, `Ctrl+S` still saves. Bundle internals unchanged (still v1 with `mask.png`); format refactor is next session.
- **Edit mode toggle scaffolding.** `edit_mode: bool` on `SessionState` (session-local, not persisted). `ToggleButton` in toolbar reflects + drives the flag via `MaskService.set_edit_mode` / `toggle_edit_mode`. Bare `e` hotkey bound to `toggle_edit_mode` action in `app.py`. In-progress lasso is canceled on any mode flip so users can't commit a cross-mode stroke. No add/subtract behavior wired yet.
- **Zero-area lasso guard.** `masking.polygon_area` (wraps `cv2.contourArea`) exposes the mathematical enclosed area. `mask_service.close_lasso` discards polygons with `area <= 0` and logs a WARNING. Catches collinear / duplicate-point / sub-3-vertex cases deterministically — `cv2.fillPoly` fills boundary pixels for degenerate polygons, so the rasterization count is misleading; shoelace area is the right primitive.
- **Zoom/pan in `ImageCanvas`** (completed by background agent). View-local `_view_scale` + `_view_offset`, reset on new image load. Wheel zoom cursor-centered, clamped `[0.1, 20.0]`. Middle-mouse drag emits `Pan` via `DesktopInputAdapter`; canvas applies with clamp so at least 10% of the fit-displayed image stays on-screen. `image_utils` gained `display_to_image_view` / `image_to_display_view`. 15 new tests (coord round-trip, adapter pan emission, cursor-centered zoom invariant). Lasso / click-select remain accurate under non-identity view.
- First implementation of BacMask (commit `93992ab`): core + services + UI skeleton, 105 tests passing, ruff clean.
- **Python 3.12 pin.** `.python-version` added; `uv sync --extra dev` fixed stale `my-imagej` shebang in `.venv/bin/pytest`. `uv run pytest` picks the project venv.
- **Canvas click-select.** `ImageCanvas._on_input` routes PointerDown through `_region_at`: labeled pixel → `select_region`; background → `clear_selection` + `begin_lasso`. PointerMove ignored when no lasso is active.
- **Knowledge base overhaul.**
  - Lasso close trigger finalized: pointer-release is MVP; `Enter` is an equivalent explicit-close trigger. ε-proximity auto-close reserved for later. ([014](014-lasso-tool.md), [009](009-deviations-from-claudemd.md) Round 3)
  - Edit-mode add/subtract stroke model specced. New note [023](023-edit-mode-region-boolean-edits.md). `VertexEditCommand` → `RegionEditCommand`. ([014](014-lasso-tool.md), [003](003-undo-redo-commands.md), [009](009-deviations-from-claudemd.md) Round 4)
  - Overlap allowed; clip rule dropped. New notes [024](024-mask-export-deferred.md), [025](025-overlapping-regions.md). Superseded: [012](012-png-label-maps.md), [018](018-load-mask-dim-mismatch.md), [021](021-vertex-edit-collision.md). Bundle v2 rewritten ([015](015-bacmask-bundle.md)). State model updated to polygons-canonical ([002](002-state-management.md)). ([009](009-deviations-from-claudemd.md) Round 5)
  - `CLAUDE.md` rewritten: §Core Concepts §Masks, §Save vs. Export, §Masking Tools, §File Operations, §Key Behavioral Rules, §Definition of Done.
