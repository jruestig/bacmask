---
id: 031
title: Minimap Navigator + Keyboard Pan
tags: [ui, perf]
created: 2026-04-19
status: accepted
related: [004, 016, 020, 027, 036]
---

# Minimap Navigator + Keyboard Pan

When the canvas is zoomed in the user loses the big-picture — what section of the
image is on screen, and how to navigate elsewhere quickly. Middle-mouse drag
works but is not available on every device (touchpads without a middle click,
touchscreens, Android). Keyboard arrows help on desktop but are absent on
touch-only platforms. This note locks in a single navigation affordance that
covers all three input classes.

## Decision

Add two coordinated UI affordances, both driven by the existing
[016 — Input Abstraction Layer](016-input-abstraction.md):

1. **Minimap overlay.** Small top-right thumbnail of the full image with a
   rectangle showing the current viewport. Visible **only when zoomed in**
   (`view_scale > 1.0`). Click-to-jump and click-drag repositions the viewport;
   the viewport center snaps to the pointer's image-space location under the
   minimap. Same pointer pipeline as every other widget — no device-specific
   code path.
2. **Arrow-key pan.** `←`/`→`/`↑`/`↓` emit `Action("pan_left" | "pan_right" |
   "pan_up" | "pan_down")`. Step is **10% of the canvas short side, clamped
   `[40, 120]` widget-px**, applied in widget-Y-up pixels via the same
   `_apply_pan` code the middle-mouse drag uses. Clamping keeps small canvases
   usable and large canvases from jumping half a screen at a time.

## Cross-platform rationale

| Device         | Primary nav        | Secondary             |
| -------------- | ------------------ | --------------------- |
| Mouse          | Middle-drag / wheel | Minimap, arrow keys  |
| Touchpad       | Minimap            | Arrow keys, two-finger scroll = zoom |
| Touch (Android)| Minimap            | (pinch + two-finger drag planned) |

The minimap is the **one navigation affordance that works identically on all
three**. Its interaction is a plain `PointerDown` → `PointerMove` → `PointerUp`
sequence, so the existing `TouchInputAdapter` sketch in [020](020-platform-scope.md) works
without a single branch for "touchpad" vs "touch". Arrow-key pan is a
desktop-only bonus — it does not leak into the minimap's contract.

## Contract

- **Minimap geometry.** Top-right anchor with 12 px margin. Bounded by a
  `220 × 220` widget-px box, scaled proportionally to preserve the image
  aspect ratio. Background is semi-transparent so it reads over bright images.
- **Viewport rectangle.** Drawn in the selected-region cyan so it is visually
  distinct from region overlays. Clamped to the minimap — if the viewport
  extends past the image (possible at the edges under pan-clamping), the
  rectangle is clipped, not truncated.
- **Drag semantics.** Pointer-down inside the minimap *centers* the viewport
  on the clicked image point; drag moves the center continuously. Does **not**
  initiate a lasso or brush stroke. Pointer-up ends the drag. If the press
  starts outside the minimap, the minimap is inert for that gesture even if
  the pointer crosses into it — prevents accidental jumps during long strokes.
- **Hidden when not zoomed.** At `view_scale == 1.0` the minimap would just
  mirror the canvas; hiding it reclaims the corner. The 1.0 threshold is
  strict — floating-point slop is fine because the first wheel tick always
  pushes scale past `1.0 + ε`.
- **Arrow-key step.** `step = clamp(min(canvas.width, canvas.height) * 0.10, 40, 120)`
  widget-px. Key-repeat (held arrow) continues to pan smoothly because each
  repeat emits a fresh `Action`. Clamping by
  [image_canvas.PAN_KEEP_VISIBLE_FRAC](../bacmask/ui/widgets/image_canvas.py)
  ensures arrows cannot push the image entirely off-screen.

## Non-goals

- **Minimap scroll-to-zoom.** Scroll over the minimap currently falls through
  to the canvas handler and zooms the main view at the canvas center. A
  dedicated minimap zoom gesture is not worth the complexity.
- **Resizable / collapsible minimap.** Fixed size keeps the interaction
  predictable and the geometry cheap to recompute each repaint.
- **Minimap for un-zoomed canvas.** Rejected — no navigation value when the
  entire image already fits.

## Related

- [016 — Input Abstraction Layer](016-input-abstraction.md) — the minimap
  consumes ordinary `PointerDown/Move/Up` events; the arrow-key `Action`
  names slot into the existing dispatch table.
- [020 — Platform Scope](020-platform-scope.md) — Android readiness was the
  forcing function; minimap is the cross-device nav primitive.
- [027 — Toolbar Hotkey Labels](027-toolbar-hotkey-labels.md) — arrow-key
  bindings are intentionally *not* surfaced on toolbar buttons because there
  are no pan buttons to label; discoverability is the minimap itself.
- [004 — Performance on Large Images](004-performance-large-images.md) — the
  minimap reuses the same image texture handle as the main canvas; no
  separate thumbnail cache.
