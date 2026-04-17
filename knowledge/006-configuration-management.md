---
id: 006
title: Configuration Management
tags: [config, ops]
created: 2026-04-17
status: accepted
related: [007, 008]
---

# Configuration Management

No hardcoded paths, sizes, or colors. User-tweakable settings live in config.

## Layout
- `config.yaml` at repo root — user-editable runtime config.
- `bacmask/config/defaults.py` — default values as Python constants.
- `bacmask/config/config_loader.py` — loads YAML, validates, falls back to defaults on missing keys.

## What belongs in config
- Default output paths (`output/masks/`, `output/areas/`).
- Default brush size, flood-fill tolerance.
- Mask overlay alpha, colony color palette.
- Undo history cap ([003](003-undo-redo-commands.md)).
- Display downsample threshold ([004](004-performance-large-images.md)).
- Log level ([007](007-logging.md)).

## What does NOT belong in config
- The scale factor — that's **per-image session state**, not a global setting. Lives in [SessionState](002-state-management.md), serialized into each CSV.
- File format choices (PNG 16-bit for masks, CSV for areas). These are locked contracts.

## Why YAML over JSON
- Comments supported — users will want to document their own tweaks.
- Human-edit-friendly. This config is meant to be opened in a text editor.

## Related
- [002 — Session State](002-state-management.md) — session state vs. config boundary.
- [007 — Logging](007-logging.md) — log level is config-driven.
