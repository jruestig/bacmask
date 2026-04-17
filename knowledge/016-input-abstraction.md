---
id: 016
title: Input Abstraction Layer
tags: [architecture, ui]
created: 2026-04-17
status: accepted
related: [001, 010, 014, 020]
---

# Input Abstraction Layer

Decouple gesture/input handling from domain commands so desktop ↔ touch profiles can be swapped without touching core or services.

## Decision
All raw gestures are translated into a small vocabulary of **semantic input events** at `bacmask/ui/input/`. Widgets and services consume the semantic events — they never see raw Kivy events.

## Semantic events (MVP)
- `PointerDown(pos, modifiers)`
- `PointerMove(pos)`
- `PointerUp(pos)`
- `Zoom(center, delta)` — wheel on desktop; pinch on touch (future).
- `Pan(delta)` — right-drag / gesture.
- `Action(name)` — e.g. `"close_lasso"`, `"cancel_lasso"`, `"delete_region"`, `"undo"`, `"redo"`, `"save_all"`, `"load"`.

## Adapters
- `DesktopInputAdapter` — translates Kivy mouse/keyboard events.
  - Left-drag → pointer sequence.
  - Wheel → `Zoom`.
  - `Enter` → `Action("close_lasso")`.
  - `Escape` → `Action("cancel_lasso")`.
  - `Delete` → `Action("delete_region")`.
  - `Ctrl+Z` / `Ctrl+Shift+Z` → `Action("undo" | "redo")`.
  - `Ctrl+S` → `Action("save_all")`.
- `TouchInputAdapter` (future, post-MVP — see [020](020-platform-scope.md)) — multi-touch gestures.
  - Single-finger drag → pointer sequence.
  - Two-finger pinch → `Zoom`.
  - Two-finger drag → `Pan`.
  - Long-press → context menu (close/delete).

## Rationale
Without this layer, UI widgets hard-code Kivy event paths and close-lasso semantics leak into framework handlers. Swapping desktop for touch (or swapping Kivy entirely per [010](010-kivy-over-beeware.md)) becomes invasive.

With this layer, a widget's handler is just:

```python
def on_input(self, event: InputEvent):
    match event:
        case Action(name="close_lasso"): mask_service.close_lasso()
        case PointerDown(pos=p):         mask_service.begin_lasso(p)
        ...
```

## Keybindings are config-driven
Action names are mapped to keys via `config.yaml` ([006](006-configuration-management.md)). Users can rebind without touching code. Defaults live in `config/defaults.py`.

## Related
- [001 — Separation of Concerns](001-separation-of-concerns.md) — the layer keeps `ui/` thin.
- [014 — Lasso Tool](014-lasso-tool.md) — primary consumer.
- [020 — Platform Scope](020-platform-scope.md) — why the touch adapter can wait.
