---
id: 000
title: Project Overview
tags: [meta]
created: 2026-04-17
status: accepted
related: [008]
---

# Project Overview

BacMask is a cross-platform, single-purpose tool: mask bacteria colonies in microscope/camera images and compute per-colony area in mm².

## Scope anchor
- **In scope:** load image → calibrate (mm/px) → paint/erase/flood-fill masks → view areas → save masks (16-bit PNG) + areas (CSV).
- **Out of scope:** brightness/contrast/filters/crop/rotate, smart thresholding, batch processing, camera capture, URL loading.

## Platforms
Linux, Windows, Android. UI framework: Kivy. Android build via Buildozer.

## North-star principle
Masks are training data for future ML. They must be **deterministic, reproducible, lossless**. Same image + same user actions → bit-identical mask PNG.

## Canonical references
- `CLAUDE.md` at repo root — project instructions, behavioral rules, definition of done.
- [008 — Directory Layout](008-directory-layout.md) — authoritative file tree.
