---
id: 020
title: Platform Scope (Desktop-First MVP)
tags: [architecture, ops]
created: 2026-04-17
status: accepted
related: [000, 010, 016]
---

# Platform Scope

## Decision
**Desktop-first MVP** — Linux and Windows are the supported targets for v0.

Android is explicitly **post-MVP**.

macOS is not a target for MVP. Likely works (Kivy + Python 3.12), but not validated.

## Rationale
- Android (Buildozer + Python-for-Android + touch tuning + SAF file access) is weeks of work separate from the core annotation workflow.
- The value hypothesis — "can users annotate colonies efficiently?" — is answerable on desktop alone.
- Trying to ship all three platforms simultaneously delays the first useful version.

## Architectural hooks kept for later
Android readiness is preserved without Android being a current target:
- [016 — Input Abstraction Layer](016-input-abstraction.md) — touch profile can slot in without touching core.
- [010 — Kivy over BeeWare](010-kivy-over-beeware.md) — Buildozer is a documented path when we're ready.
- `opencv-python-headless` is the declared dep — no GUI binaries leak in that would break headless / Android builds.
- Output path is configurable ([006](006-configuration-management.md)) — Android sandbox paths accommodable without code changes.
- `buildozer.spec` can ship in the repo as a post-MVP stub, left empty until Android lands.

## When Android lands
MVP ships, gets real desktop use for at least a few weeks, then Android is a discrete milestone.

## Related
- [000 — Project Overview](000-project-overview.md).
- [010 — Kivy over BeeWare](010-kivy-over-beeware.md).
- [016 — Input Abstraction Layer](016-input-abstraction.md).
