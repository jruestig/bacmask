---
id: 028
title: File Picker — Double-Click to Open
tags: [ui]
created: 2026-04-19
status: accepted
related: [015, 020, 033]
---

# File Picker — Double-Click to Open

## Rule

Inside any in-app file chooser (Load image, Load bundle), **double-clicking a file opens it**. No separate "Open" button press is required after selecting the file.

Single-click still works — it selects the file and highlights it; the user then presses the Open button or hits `Enter`. But double-click is the fast path and must be wired up.

## Applies to

- **Load image** dialog (Ctrl+O) — picks an image off disk.
- **Load bundle** dialog — picks a `.bacmask` file ([015](015-bacmask-bundle.md)).
- Any future picker (e.g. export-CSV destination) — same rule.

## Implementation note

Kivy's `FileChooserListView` / `FileChooserIconView` both fire `on_submit` on double-click (and `Enter` when a file is selected). Bind the load-image callback to `on_submit` in addition to the Open button — no custom double-click timing needed. The OS file dialog on desktop platforms (`Ctrl+O` via a platform-native picker, if ever used) already behaves this way.

## Why this is a spec rule, not an "obviously do the right thing"

Because the first MVP shipped with single-click + Open button only, and the user noticed. Calling it out explicitly so regressions don't sneak back in, and so any new picker added later gets this treatment from day one.

## Related

- [015 — .bacmask Bundle Format](015-bacmask-bundle.md) — the primary file type users pick.
- [020 — Platform Scope](020-platform-scope.md) — desktop-first; touch adapter will need an equivalent "tap-tap" shortcut on Android.
- [033 — File Picker Breadcrumb Path Bar](033-file-picker-breadcrumb-bar.md) — companion navigation primitive on the same chooser.
