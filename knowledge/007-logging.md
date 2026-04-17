---
id: 007
title: Logging
tags: [ops]
created: 2026-04-17
status: accepted
related: [006]
---

# Logging

Python `logging` module. Never `print()`.

## Setup
- `bacmask/utils/logger.py` — configures root logger on app startup.
- Named loggers per module: `logger = logging.getLogger(__name__)`.
- Level read from `config.yaml` (see [006](006-configuration-management.md)). Default: `INFO`.

## What must be logged
- All file I/O — load image, save mask, save CSV, load mask. `INFO` on success, `ERROR` on failure with path.
- Calibration state transitions — `INFO` when scale set/cleared.
- Undo/redo operations — `DEBUG`.
- Exceptions — always `ERROR` or `CRITICAL` with full traceback via `logger.exception(...)`.

## What must NOT be logged
- Every brush stroke at `INFO` level — floods logs. Use `DEBUG`.
- Full NumPy arrays. Log shape/dtype only.

## Android note
Logs go to `adb logcat` via Kivy's handler on Android. Design log messages to be greppable.

## Related
- [006 — Configuration Management](006-configuration-management.md) — log level source.
