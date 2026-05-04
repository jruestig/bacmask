---
id: 001
title: Separation of Concerns (MVC-ish)
tags: [architecture, core, services, ui]
created: 2026-04-17
status: accepted
related: [002, 005, 008, 036]
---

# Separation of Concerns

Strict three-layer split. The most critical architectural decision in the project.

## Rule
`bacmask/core/` contains **zero Kivy imports**. Ever.

## Layers
- **`core/`** — pure Python: state, masking, area, I/O, calibration, commands, history, validators. Headless-runnable. Fully unit-testable without any UI harness.
- **`services/`** — orchestration. Translates high-level intents (“user painted at x,y”, “save all”) into core calls + state updates + history pushes. Kivy-agnostic.
- **`ui/`** — all Kivy code. Widgets, screens, .kv files, dialogs. Thin shell that calls services.

## Why
- **Testability.** Core logic is deterministic and runs in `pytest` with no display.
- **Framework insurance.** If Kivy proves insufficient on a platform (likely: Android touch edge cases), swap UI for Toga/web without touching core.
- **Clarity.** A reader knows exactly where to look for a given concern.

## How to apply
- Reviewing a PR: if `core/*.py` imports `kivy` anything, reject.
- Reviewing a PR: if `ui/*.py` reaches into NumPy/OpenCV for domain logic instead of calling a service, reject — move logic down.
- New feature: design core API first, then service, then UI. Never the reverse.

## Related
- [002 — State Management](002-state-management.md) — the object the layers share.
- [005 — Testing Strategy](005-testing-strategy.md) — why the split pays off.
- [008 — Directory Layout](008-directory-layout.md) — where each layer lives.
