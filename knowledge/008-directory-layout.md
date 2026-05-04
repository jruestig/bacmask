---
id: 008
title: Directory Layout (Authoritative)
tags: [architecture]
created: 2026-04-17
updated: 2026-05-04
status: accepted
related: [001, 002, 003, 005, 006, 007, 009, 014, 015, 016, 019, 035]
---

# Directory Layout (Authoritative)

This supersedes the simpler sketch in `CLAUDE.md` where the two conflict. See [009](009-deviations-from-claudemd.md).

```
bacmask/
├── main.py                         # entry point only — bootstraps app
├── bacmask/
│   ├── core/                       # NO UI IMPORTS (see 001)
│   │   ├── state.py                # SessionState (see 002)
│   │   ├── masking.py              # polygon rasterization, label assignment
│   │   ├── area.py                 # px → mm² area computation
│   │   ├── io_manager.py           # source carriers + decoders + write fns (see 035)
│   │   ├── calibration.py          # scale validation (see 017)
│   │   ├── commands.py             # LassoClose/VertexEdit/DeleteRegionCommand (see 003, 014)
│   │   ├── history.py              # UndoRedoStack (see 003)
│   │   └── validators.py           # input validation
│   ├── services/                   # core ↔ UI orchestration (see 001)
│   │   ├── mask_service.py
│   │   ├── export_service.py
│   │   └── import_service.py
│   ├── ui/                         # Kivy only (see 001)
│   │   ├── app.py                  # Kivy App subclass, wires services
│   │   ├── input/                  # input abstraction (see 016)
│   │   │   ├── events.py           # semantic InputEvent types
│   │   │   ├── desktop_adapter.py  # Kivy mouse/keyboard → events
│   │   │   └── touch_adapter.py    # post-MVP (see 020)
│   │   ├── screens/
│   │   │   └── main_screen.py
│   │   ├── widgets/
│   │   │   ├── image_canvas.py     # display + overlay + pan/zoom
│   │   │   ├── toolbar.py          # lasso / undo / redo / delete / save
│   │   │   ├── calibration_input.py
│   │   │   ├── results_table.py
│   │   │   └── file_dialogs.py
│   │   └── styles/
│   │       └── bacmask.kv
│   ├── config/                     # see 006
│   │   ├── defaults.py
│   │   └── config_loader.py
│   └── utils/
│       ├── image_utils.py          # resize, color convert, format detect
│       └── logger.py               # see 007
├── images/                         # real microscopy TIFFs (manual smoke tests)
├── output/                         # user-configurable root (see 006)
│   ├── bundles/                    # <image_stem>.bacmask  (see 015)
│   └── areas/                      # <image_stem>_areas.csv (see 011)
├── tests/                          # see 005
│   ├── core/
│   │   ├── test_masking.py
│   │   ├── test_area.py
│   │   ├── test_io_manager.py
│   │   ├── test_history.py
│   │   └── test_calibration.py
│   ├── services/
│   │   ├── test_mask_service.py
│   │   └── test_export_service.py
│   └── fixtures/
│       ├── synthetic_colony.png
│       └── synthetic_mask.png
├── knowledge/                      # Zettelkasten
├── buildozer.spec                  # Android build config (post-MVP, see 020)
├── config.yaml                     # user-editable runtime config
├── pyproject.toml                  # metadata + deps + ruff config (see 019)
├── uv.lock                         # pinned deps (see 019)
├── CLAUDE.md
└── README.md
```

## Naming rules
- Packages and modules: `snake_case`.
- Test files mirror source tree: `bacmask/core/masking.py` ↔ `tests/core/test_masking.py`.
- Output files deterministic: `<image_stem>.bacmask`, `<image_stem>_areas.csv`.

## Changes from earlier drafts
- `requirements.txt` + `requirements-dev.txt` → replaced by `pyproject.toml` + `uv.lock` ([019](019-dev-tooling.md)).
- `ui/widgets/brush_settings.py` removed — no brush in MVP ([013](013-minimal-toolset.md), [014](014-lasso-tool.md)).
- `ui/widgets/toolbar.py` now lists lasso / undo / redo / delete / save.
- `output/masks/` → `output/bundles/` — mask PNGs live inside `.bacmask` rather than standalone ([015](015-bacmask-bundle.md)).
- Added `ui/input/` for semantic input adapters ([016](016-input-abstraction.md)).
- `io_manager.py` split into source carriers (`ImageSource`, `BundleSource`) + pure decoders (`decode_image`, `open_bundle`) + path shims ([035](035-io-source-carriers.md)). No new module — same file, two layers.

## Related
Every other architecture note links back here. See this file's `related:` frontmatter.
