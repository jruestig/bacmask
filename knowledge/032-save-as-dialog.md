---
id: 032
title: Save As / Export As Dialog (User-Chosen Path)
tags: [ui]
created: 2026-04-30
status: accepted
related: [015, 011, 028, 033]
---

# Save As / Export As Dialog (User-Chosen Path)

## Rule

Save (`Ctrl+S`) and Export CSV (`Ctrl+E`) open a **Save As-style file chooser**. The user picks the directory and filename — neither path is forced into a fixed output tree.

## Behaviour

- **Default location:** loaded image's directory → `Path.cwd()` (fallback if the image path's parent is somehow gone). No cross-image stickiness — loading a new image immediately re-targets the dialog.
- **Default filename:** pre-filled to `<image_stem>.bacmask` (Save) or `<image_stem>_areas.csv` (Export). Editable.
- **Extension safety:** if the user clears or changes the extension, it's restored to `.bacmask` / `.csv` on confirm. Whatever the user typed in the stem is preserved.
- **No session memory of output dir.** Earlier revisions cached `_last_save_dir` / `_last_export_dir` (later collapsed to a single `_last_output_dir`). Both removed — once you'd saved once, every subsequent image's dialog opened at the *old* folder, not the new image's folder. The image directory is the only sane default for this tool: bundles + CSVs belong next to the image they describe. Users who want a different output root can navigate there in the chooser (now ergonomic with the breadcrumb bar — see [033](033-file-picker-breadcrumb-bar.md)).
- **No directory pre-creation.** The app never creates `output/bundles/` or `output/areas/` on startup or on dialog open. The only `mkdir` happens on the user-confirmed path's parent at write time, so saving into a fresh subdir works without leaving stray empty directories behind on cancel.
- **New Folder button** inside the dialog: prompts for a name, creates the folder under the chooser's current path, then navigates the chooser into it. Rejects names containing `/` or `\`, and refuses to overwrite an existing directory.

## Modal keyboard isolation

While any popup (Load, Save As, Export As, New Folder) is open, global keyboard shortcuts are suppressed. Implementation: `BacMaskApp._open_modal_count` is incremented on `popup.on_open` and decremented on `popup.on_dismiss`; the `Window.on_key_down` handler returns `False` early when the count is non-zero.

This keeps:

- Arrow keys from panning the canvas while you're editing the filename.
- `Delete` / `Backspace` from deleting the selected region while you're typing.
- `Ctrl+S` / `Ctrl+E` / `L` / `B` / `Tab` / etc. from firing inside dialogs.

The Save As dialog auto-focuses its filename `TextInput` on open so caret-edit keys land where the user expects.

## Why not a fixed `BUNDLES_DIR` / `AREAS_DIR`

The first cut wrote to `defaults.BUNDLES_DIR` / `defaults.AREAS_DIR` and silently created those directories. That was wrong for this tool: bacteria-colony datasets are organised per-experiment by the user, and burying outputs under a global `output/` tree forces them to move files afterward. The defaults still exist as constants ([006](006-configuration-management.md)) but are no longer eagerly created and are no longer the Save As starting point.

`BACMASK_OUTPUT_ROOT` env override remains available for users who *want* a fixed root.

## Why "New Folder" lives in the dialog

Users routinely need a fresh per-experiment subfolder at save time, and the alternative (cancel, switch to a file manager, mkdir, return) is friction the app can absorb in three lines of UI.

## Implementation pointer

`bacmask/ui/app.py`:

- `_save_bundle` / `_export_csv` — choose default dir, hand off to `_open_save_as_dialog`.
- `_open_save_as_dialog(title, start_dir, default_filename, on_confirm)` — generic chooser + filename input + Save/Cancel + New Folder.
- `_open_new_folder_dialog(parent_dir, chooser)` — name prompt; navigates the chooser into the new dir on success.
- `_track_modal(popup)` — wires `on_open`/`on_dismiss` to the modal counter.

## Related

- [015 — .bacmask Bundle Format](015-bacmask-bundle.md) — what Save writes; path is now user-chosen.
- [011 — CSV for Area Output](011-csv-for-area-output.md) — what Export writes; same.
- [028 — File Picker Double-Click](028-file-picker-double-click.md) — sister rule for the load-side picker.
- [033 — File Picker Breadcrumb Path Bar](033-file-picker-breadcrumb-bar.md) — breadcrumb mounts inside this dialog and the load dialog.
