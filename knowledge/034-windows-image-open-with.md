---
id: 034
title: Windows — "Open with BioMask" for Image Files (Opt-In, Never Default)
tags: [ops, ui]
created: 2026-04-30
status: accepted
related: [020]
---

# Windows — "Open with BioMask" for Image Files

## Rule

The Windows installer offers an opt-in task that registers BioMask as a **secondary** handler for image formats (`.tif`, `.tiff`, `.png`, `.jpg`, `.jpeg`, `.bmp`). BioMask must **never** become the default opener for these extensions on installation.

The user can promote BioMask to default themselves via Windows' "Choose another app → Always use this app" dialog. That is a deliberate user choice, not an installer side-effect.

## Behaviour

- Inno Setup task `associate_images` (off by default, sits in the *File associations* group alongside `.bmsk`).
- When ticked, the installer writes:
  - `Software\Classes\BioMask.image` ProgID (friendly name `Image (BioMask)`, `DefaultIcon`, `shell\open\command`).
  - `Software\Classes\<ext>\OpenWithProgids` value `BioMask.image` for each supported extension.
- Result: right-click any `.tif` → **Open with** → BioMask appears in the submenu.
- Default handler (Photos, IrfanView, …) is untouched.
- Uninstall removes the ProgID (`uninsdeletekey`) and the per-extension `OpenWithProgids` values (`uninsdeletevalue`). The user's existing default association remains intact because we never wrote to `(Default)` of `Software\Classes\<ext>`.

Runtime side already works: `main.py:_initial_path` passes `argv[1]` to `BioMaskApp`, and `BioMaskApp._load_path` routes any non-`.bmsk` path through `MaskService.load_image`. No Python changes were needed.

## Why `OpenWithProgids`, not direct association

Two competing patterns exist:

- **Default association** — write `Software\Classes\<ext>` `(Default) = ProgID`. Forces BioMask as the opener; obliterates whatever the user had configured. Hostile.
- **`OpenWithProgids`** — append a ProgID to the per-extension list of "apps that *can* open this file." Microsoft's documented [recommendation for non-default handlers](https://learn.microsoft.com/en-us/windows/win32/shell/how-to-include-an-application-on-the-open-with-dialog-box). Adds BioMask to the *Open with* menu without dethroning anyone.

We use the second. Microscope users already have an image viewer they trust; surprising them with a different default after running our installer would be a support burden and a violation of the desktop-environment contract.

## Why opt-in

Defaults that touch global Windows state should never auto-apply. The `.bmsk` association follows the same opt-in pattern in this installer (and was the model for this one). A user who never wants BioMask in their context menus gets exactly that by leaving the box unticked.

## Verification

On a Windows install with the task ticked:

1. Right-click `*.tif` in Explorer → **Open with**. BioMask should appear.
2. Click → app launches with the image loaded (lasso/brush ready).
3. Confirm Photos / IrfanView / whatever was default still opens on plain double-click.
4. Uninstall → repeat step 1; BioMask should be gone from the submenu.
5. Re-check `Software\Classes\.tif\OpenWithProgids` in `regedit` — `BioMask.image` value should be absent.

## Implementation pointer

`packaging/installer.iss`:

- `[Tasks]` — `associate_images` (off by default).
- `[Registry]` — one `BioMask.image` ProgID block + six `OpenWithProgids` rows (one per extension).
- Trailing notes block carries the same don't-make-default warning so future edits don't accidentally promote it.

`packaging/README-windows.md` documents the wizard checkbox.

## Related

- [020 — Platform Scope (Desktop-First MVP)](020-platform-scope.md) — Windows is an MVP target; this is a Windows-shell ergonomics rule, not a cross-platform contract.
