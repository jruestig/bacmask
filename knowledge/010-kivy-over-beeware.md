---
id: 010
title: Kivy over BeeWare (UI framework choice)
tags: [architecture, ui, ops]
created: 2026-04-17
status: accepted
related: [000, 001]
---

# Kivy over BeeWare

## Decision
Kivy is the default UI framework. BeeWare (Toga) is a potential fallback only, not a concurrent option.

## Rationale

### Consistent canvas rendering across platforms
Kivy uses a **custom rendering pipeline** (OpenGL ES 2 under the hood) that draws the same on Linux, Windows, macOS, and Android. For a mask-painting tool, pixel-accurate canvas behavior on every platform is the core requirement — native-widget differences would bite us immediately.

BeeWare/Toga wraps **native widgets**. Native widgets are excellent for forms (buttons, text fields, menus) but poorly suited for custom canvas interactions like painting, pan/zoom on a bitmap, and overlay compositing.

### Community and documentation
Kivy's community is larger and its documentation more mature than BeeWare's. For an image-heavy app hitting edge cases in texture handling, touch events, and Android packaging, the gap in available answers matters.

### Android path is proven
Buildozer + Python-for-Android is a well-trodden route. Required permissions, storage paths, and touch-event handling are all documented.

## When we'd reconsider
- Kivy fails on a specific Android API level or device class we must support.
- Native look-and-feel becomes a hard requirement (it currently isn't — this is a tool, not a consumer app).

In that case, evaluate Toga for the UI layer only. Because of [Separation of Concerns](001-separation-of-concerns.md), `core/` and `services/` would survive such a swap unchanged.

## Related
- [001 — Separation of Concerns](001-separation-of-concerns.md) — why a UI swap wouldn't touch domain logic.
- [000 — Project Overview](000-project-overview.md) — platform targets.
