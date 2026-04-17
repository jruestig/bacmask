---
id: 017
title: Calibration Input Model
tags: [architecture, core, ui]
created: 2026-04-17
status: accepted
related: [002, 011, 015]
---

# Calibration Input Model

## Canonical storage: mm per pixel
`SessionState.scale_mm_per_px` ([002](002-state-management.md)) is the single source of truth. Persisted to the bundle's `meta.json` ([015](015-bacmask-bundle.md)) and written to the CSV `scale_factor` column ([011](011-csv-for-area-output.md)).

## Input UX: two synced fields
Both are visible simultaneously — no mode toggle, no dropdown:

- **mm/px** — e.g. `0.0125`
- **px/mm** — e.g. `80`

Users who know one can type in either field. On commit (Enter), the service is called with the converted canonical value. The other field auto-updates from state.

Rationale: different users think in different directions. Objective specs often state "pixel size in µm" (→ mm/px small number); imaging systems sometimes publish magnification (→ px/mm large number). Supporting both eliminates mental division without introducing a hidden toggle that silently changes what the same typed number means.

## Validation
- Values ≤ 0 rejected silently (field keeps prior state; no popup).
- NaN / ±Inf rejected.
- Empty input is valid (clears calibration — uncalibrated state).
- Unparseable text leaves the field contents alone so the user can correct.

## Uncalibrated state
- `scale_mm_per_px = None`. `area_px` still populated in the table and CSV.
- CSV `area_mm2` and `scale_factor` columns are **empty strings** ([011](011-csv-for-area-output.md)).
- Bundle `meta.json` stores `scale_mm_per_px: null` ([015](015-bacmask-bundle.md)).

## Changing the scale mid-session
- Allowed. Area column recomputes immediately on any commit.
- Not pushed to the undo stack — calibration is session-level, not a mask mutation ([003](003-undo-redo-commands.md)).
- Sets the `dirty` flag.

## Keyboard behavior
Global keyboard shortcuts (close-lasso, delete, undo, save) must not fire while a calibration field has focus — otherwise backspace, delete, Ctrl+Z inside the field would be swallowed. The app's keyboard handler checks for any focused `TextInput` and returns the key to the widget when one is found.

## Future: measure-line tool (post-MVP)
User draws a line on the image, enters its real-world length in mm → derives mm/px. Architecturally: a service method `calibrate_from_line(p1, p2, length_mm)`. Out of MVP.

## Related
- [002 — Session State](002-state-management.md).
- [011 — CSV for Area Output](011-csv-for-area-output.md).
- [015 — .bacmask Bundle](015-bacmask-bundle.md).
