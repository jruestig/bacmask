---
id: 036
title: Single Action Dispatcher (App-Level)
tags: [architecture, ui]
created: 2026-05-04
status: accepted
related: [001, 016, 020, 026, 031]
---

# Single Action Dispatcher

One action vocabulary. One dispatcher. App-level.

## Decision

`BacMaskApp.dispatch_action(name: str) -> bool` is the only place semantic action names turn into service calls. Both producers route through it:

1. **Window keyboard** — `BacMaskApp._on_key_down` resolves Kivy key + modifiers via `keybinding_for(...)`, then calls `dispatch_action`.
2. **Canvas pointer/touch** — `ImageCanvas` receives `Action(name=...)` events from its `DesktopInputAdapter`, forwards them via the `on_action` callback wired through `MainScreen.__init__` from `BacMaskApp.dispatch_action`.

The canvas no longer dispatches anything itself.

## Why

Pre-refactor: two dispatchers — `BacMaskApp._run_action` (window keyboard) and `ImageCanvas._handle_action` (canvas Action events). Overlap on every action except `save_bundle` / `export_csv` / `load_image` / `pan_*`. Drift hazard:

- `cancel_stroke` cleared `_brush_preview_pts` only in the canvas dispatcher. A future Esc fired through the window path would have left the brush ghost on screen — narrowly avoided today only because window keyboard never reached the canvas dispatcher.
- New action = edit two places, remember both.

`DesktopInputAdapter.on_key_down` was unreachable code. Kivy delivers key events to `Window`, not widgets, so the adapter instance inside the canvas widget never saw a keystroke. Deleted.

## Cleanup as state effect, not dispatcher branch

The one canvas-internal side-effect (`_brush_preview_pts = []` on cancel) moved out of the dispatcher into a state subscription:

```python
# ImageCanvas._on_state_changed
stroke_active_now = state.active_brush_stroke is not None
if self._last_brush_stroke_active and not stroke_active_now:
    self._brush_preview_pts = []
self._last_brush_stroke_active = stroke_active_now
```

Cleanup fires whenever the stroke ends — commit, cancel, or subtract-empties-delete — regardless of *which key* triggered it. `_on_pointer_up` no longer self-clears either; it relies on the same transition.

## Wiring

```
BacMaskApp.build()
  └─ MainScreen(..., on_action=self.dispatch_action)
        └─ ImageCanvas(service, on_action=on_action)

Window.on_key_down ─▶ BacMaskApp._on_key_down ─▶ keybinding_for ─▶ dispatch_action
DesktopInputAdapter ─▶ canvas._on_input(Action) ─▶ self._on_action(name) ─▶ dispatch_action
```

## Touch / Android readiness

When the touch adapter ships ([020](020-platform-scope.md)), `Window.on_key_down` becomes mostly dead on tablets. The canvas adapter still emits `Action` events (long-press → context menu, etc.), still routes through `on_action` → `dispatch_action`. No window-keyboard handler change required, no new dispatcher needed.

## Tests

`tests/ui/test_image_canvas_edit.py::test_cancel_brush_stroke_clears_canvas_preview_via_state_subscription` — guards the bug the dual dispatch was hiding. Begins a brush stroke through the canvas, calls `svc.cancel_brush_stroke()` directly (the same call `dispatch_action("cancel_stroke")` makes), asserts `_brush_preview_pts == []` after the state notification fires.

Total `pytest`: 225 → 226, all pass.

## Files changed

- `bacmask/ui/app.py` — `_run_action` → `dispatch_action` (public); pass to `MainScreen`.
- `bacmask/ui/screens/main_screen.py` — `on_action` parameter forwarded to `ImageCanvas`.
- `bacmask/ui/widgets/image_canvas.py` — `on_action` constructor kwarg; `_handle_action` deleted; brush-preview cleanup moved into `_on_state_changed`.
- `bacmask/ui/input/desktop_adapter.py` — dead `on_key_down` deleted; module docstring + class docstring updated to reflect mouse-only adapter.

## Why not a per-widget keyboard adapter

Considered: instantiate a `DesktopInputAdapter` inside `BacMaskApp` purely for keyboard, sharing translation with the canvas. Rejected — extra wiring for zero new capability. `keybinding_for` is already a free function both call sites can use; the adapter class is for stateful pointer drag tracking, which the window-keyboard path does not need.

## Related

- [001 — Separation of Concerns](001-separation-of-concerns.md) — single dispatcher keeps `ui/` thin.
- [016 — Input Abstraction Layer](016-input-abstraction.md) — defines the `Action` vocabulary; this note collapses its dispatch.
- [020 — Platform Scope](020-platform-scope.md) — touch adapter readiness.
- [026 — Brush Edit Model](026-brush-edit-model.md) — `cancel_stroke` behavior; preview-cleanup motivation.
- [031 — Minimap Navigator + Keyboard Pan](031-minimap-navigator.md) — `pan_*` actions flow through the same dispatcher.
