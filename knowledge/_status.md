# Status — 2026-04-19

Session-handoff doc. Updated at the end of each working session. What follows `knowledge/` conventions — kept short on purpose.

## Currently working on
- Landing the overlap-aware data model. Spec is finalized across knowledge notes (002, 015, 023, 024, 025); code still reflects the old disjoint + in-bundle-mask model.

## In progress (started, not done)
- **Canvas interactions.** Tap-on-mask selects; tap-on-bg begins lasso (shipped this session). Zoom/pan still ignore the semantic events the input adapter emits.
- **Python 3.12 pin.** `.python-version` added and venv resynced; `uv run pytest` green. No further action needed unless the venv drifts again.

## Blocked (waiting on external input or deferred decisions)
- **Mask export output location + CLI.** User wants to pick `out_dir` and a CLI wrapper "later." Format contract is locked ([024](024-mask-export-deferred.md)); placement and ergonomics deferred.
- **Windows smoke test.** Needs a Windows machine; not arranged.
- **macOS validation.** Not an MVP target, intentionally deferred ([020](020-platform-scope.md)).

## Next actions (concrete, ordered)
1. **Bundle v2 read/write in `core/io_manager.py`.**
   - Stop writing `mask.png` on save; drop it from the zip.
   - Write `meta.json` with `bacmask_version: 2` + `image_shape`.
   - v1 reader back-compat: accept bundles that contain `mask.png`, ignore the raster, trust the polygons. Auto-promote on re-save.
2. **State refactor in `core/state.py` + `services/mask_service.py`.**
   - Make `regions` (polygons) the single source of truth.
   - Introduce `region_masks: dict[int, np.ndarray]` (per-region `bool`) and `label_map_cache` (display-only `uint16`), both derived on polygon mutation.
   - Rebuild both on `load_bundle`; patch within bbox on commands.
3. **UI: split Save and Export.**
   - `Save` → bundle only.
   - `Export` → CSV only. Add a separate toolbar button. Remove the CSV write from the Save path.
4. **Edit mode toggle in the toolbar + keyboard (`e`).**
   - Session-local `edit_mode: bool` on `SessionState`.
   - Gate the canvas' press-drag behavior on it.
5. **`RegionEditCommand` + add/subtract stroke implementation.**
   - Rename `VertexEditCommand` → `RegionEditCommand(label_id, old_vertices, new_vertices, old_mask_patch)`.
   - Port the algorithm from [023](023-edit-mode-region-boolean-edits.md): first-two-crossings, close-straight, apply, largest-CC with smallest-`(y, x)` tiebreak, re-derive vertices via `cv2.findContours`.
   - Subtract-empties-target → route to `DeleteRegionCommand`.
6. **Canvas double-click retargeting in edit mode.**
   - Single tap sets first target; double-tap retargets; background double-tap clears.
7. **Zoom/pan transform in `ImageCanvas`.**
   - Consume `Zoom`/`Pan` input events already emitted by `DesktopInputAdapter`; update `image_to_display` / `display_to_image` to account for a view transform.
8. **Zero-enclosed-area warning on lasso close.**
   - Already discarded silently with <3 points; add a warning popup or log line for non-trivial zero-area strokes.

## Recently completed (last ~2 sessions)
- First implementation of BacMask (commit `93992ab`): core + services + UI skeleton, 105 tests passing, ruff clean.
- **Python 3.12 pin.** `.python-version` added; `uv sync --extra dev` fixed stale `my-imagej` shebang in `.venv/bin/pytest`. `uv run pytest` picks the project venv.
- **Canvas click-select.** `ImageCanvas._on_input` routes PointerDown through `_region_at`: labeled pixel → `select_region`; background → `clear_selection` + `begin_lasso`. PointerMove ignored when no lasso is active.
- **Knowledge base overhaul.**
  - Lasso close trigger finalized: pointer-release is MVP; `Enter` is an equivalent explicit-close trigger. ε-proximity auto-close reserved for later. ([014](014-lasso-tool.md), [009](009-deviations-from-claudemd.md) Round 3)
  - Edit-mode add/subtract stroke model specced. New note [023](023-edit-mode-region-boolean-edits.md). `VertexEditCommand` → `RegionEditCommand`. ([014](014-lasso-tool.md), [003](003-undo-redo-commands.md), [009](009-deviations-from-claudemd.md) Round 4)
  - Overlap allowed; clip rule dropped. New notes [024](024-mask-export-deferred.md), [025](025-overlapping-regions.md). Superseded: [012](012-png-label-maps.md), [018](018-load-mask-dim-mismatch.md), [021](021-vertex-edit-collision.md). Bundle v2 rewritten ([015](015-bacmask-bundle.md)). State model updated to polygons-canonical ([002](002-state-management.md)). ([009](009-deviations-from-claudemd.md) Round 5)
  - `CLAUDE.md` rewritten: §Core Concepts §Masks, §Save vs. Export, §Masking Tools, §File Operations, §Key Behavioral Rules, §Definition of Done.
