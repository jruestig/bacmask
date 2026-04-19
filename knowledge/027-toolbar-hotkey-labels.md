---
id: 027
title: Toolbar Hotkey Labels
tags: [ui]
created: 2026-04-19
status: accepted
related: [013, 016, 026]
---

# Toolbar Hotkey Labels

Every keyboard shortcut must be visible on the button that invokes the same action. No separate help overlay, no "discoverable by accident" shortcuts.

## Rule

A toolbar button's displayed label is `<Action name> (<Shortcut>)` for every action that has a shortcut. Buttons without a shortcut just show the action name. Modifier keys render in the label exactly as the user types them: `Ctrl+S`, `Shift+B`, `Ctrl+Shift+Z`.

Examples (MVP):

| Button label           | Action                 | Keybinding ([016](016-input-abstraction.md)) |
|------------------------|------------------------|--------------------------------|
| `Load (Ctrl+O)`        | Open image             | `Ctrl+O`                       |
| `Save (Ctrl+S)`        | Write `.bacmask` bundle| `Ctrl+S`                       |
| `Export CSV (Ctrl+E)`  | Write areas CSV        | `Ctrl+E`                       |
| `Lasso (L)`            | Activate lasso tool    | `L`                            |
| `Brush (B)`            | Activate brush tool    | `B`                            |
| `Create (Tab)`         | Brush mode = create    | `Tab` (cycles modes)           |
| `Add (Tab)`            | Brush mode = add       | `Tab` (cycles modes)           |
| `Subtract (Tab)`       | Brush mode = subtract  | `Tab` (cycles modes)           |
| `Delete (Del)`         | Delete selected region | `Delete` / `Backspace`         |
| `Undo (Ctrl+Z)`        | Undo                   | `Ctrl+Z`                       |
| `Redo (Ctrl+Y)`        | Redo                   | `Ctrl+Y` / `Ctrl+Shift+Z`      |

The three brush-mode toggles share one Tab keybinding (action `toggle_brush_mode`) that cycles them in panel order. They all show `(Tab)` rather than fragment the discoverability — the panel grouping makes the cycle behavior obvious at a glance.

## Why

- **Discoverability.** Hotkeys that aren't visible may as well not exist. A user who opens the app once should be able to learn every shortcut from the UI alone.
- **No duplicate sources of truth.** Labels are generated from the keybinding registry in [016 — Input Abstraction Layer](016-input-abstraction.md). Rebinding a key changes the label automatically; neither can drift from the other.
- **Cheap.** One small helper maps `keybinding_for_action("undo") → "Ctrl+Z"` and is called by toolbar construction.

## Tooltips

Tooltips add *semantic* information that doesn't fit in the label: what the button does, conditions under which it's disabled, or any subtle behavior worth surfacing without crowding the label.

## Not in scope

- Rebinding keys through the UI — use config ([006](006-configuration-management.md)) for now.
- Chorded shortcuts (two-key sequences). Single-key + modifiers only.
- Platform-specific modifier display (`⌘` on macOS). macOS isn't an MVP target ([020](020-platform-scope.md)); when it lands, map `Ctrl` → `⌘` in the label helper.

## Related

- [013 — Minimal Toolset](013-minimal-toolset.md) — the set of actions this rule applies to.
- [016 — Input Abstraction Layer](016-input-abstraction.md) — source of truth for keybindings.
- [026 — Brush Edit Model](026-brush-edit-model.md) — Tab cycles the brush mode toggles.
