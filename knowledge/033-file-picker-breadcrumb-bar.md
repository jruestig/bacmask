---
id: 033
title: File Picker — Breadcrumb Path Bar
tags: [ui]
created: 2026-04-30
status: accepted
related: [028, 032]
---

# File Picker — Breadcrumb Path Bar

## Rule

Every in-app file chooser (Load image / bundle, Save bundle, Export CSV) shows a **horizontal breadcrumb bar above the file list**. Each path segment is a button; clicking a segment jumps the chooser to that directory.

## Behaviour

- Bar sits between the popup title and the `FileChooserListView`, full width, height 30 px.
- Segments are derived from `Path(chooser.path).parents` (root-first). Root is rendered as `/` (POSIX) or the drive root string (Windows).
- A `/` separator label sits between adjacent segments — purely visual; not clickable.
- Clicking a segment sets `chooser.path` to that absolute directory. The chooser's existing `path` binding triggers `rebuild`, so the bar always reflects the chooser's current location (covers double-click navigation, the New Folder flow, and breadcrumb clicks alike).
- The bar is wrapped in a horizontal `ScrollView` (`do_scroll_x=True`, `do_scroll_y=False`) so deep paths stay usable without truncation.

## Why

Kivy's `FileChooserListView` exposes the current directory only implicitly (the highlighted folder in the tree, or none). Users had no quick way to jump up two levels — they had to click `..` repeatedly or type a path nowhere. The breadcrumb bar is the standard file-manager idiom and adds zero clicks to the common case (open the dialog and start navigating).

## Why breadcrumbs and not an editable path field

Asked the user; they explicitly chose breadcrumbs. Pros: one-click jump to any ancestor, no typing, no validation surface, no risk of `~` / `..` / env-var expansion ambiguity. The trade-off is no paste-a-path workflow — acceptable because the same dialog accepts double-click drill-down ([028](028-file-picker-double-click.md)) and the OS file manager remains available out-of-band.

## Implementation pointer

`bacmask/ui/app.py`:

- `_make_path_bar(chooser)` — builds the `ScrollView` + `BoxLayout` + per-segment `Button`s. Binds `chooser.path` to a local `rebuild` closure so navigation from any source refreshes the bar.
- `_set_chooser_path(chooser, target)` — guarded `chooser.path = target` (no-op if `target` no longer exists, e.g. a folder deleted out-of-band between dialog open and click).
- Wired into `_open_load_dialog` and `_open_save_as_dialog` — both pickers get the bar.

## Related

- [028 — File Picker Double-Click to Open](028-file-picker-double-click.md) — sister navigation rule for the same chooser widgets.
- [032 — Save As / Export As Dialog](032-save-as-dialog.md) — host dialog for Save / Export pickers; the bar mounts inside its content tree.
