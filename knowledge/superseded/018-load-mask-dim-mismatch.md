---
id: 018
title: Load Mask Dimension Mismatch (superseded)
tags: [core]
created: 2026-04-17
updated: 2026-04-19
status: superseded
related: [012, 015, 024, 025]
---

# Load Mask Dimension Mismatch (superseded)

> **Superseded by [015 — .bacmask Bundle Format](../015-bacmask-bundle.md) + [025 — Overlapping Regions Allowed](../025-overlapping-regions.md).**
> Masks are no longer stored inside the `.bacmask` bundle — polygons are canonical. There is no in-bundle mask to dimension-check on load. Rasterization happens in memory from polygons, always at the current image's `(H, W)`, so a mismatch can't occur. Mask export ([024](../024-mask-export-deferred.md)) is a one-way downstream operation; it produces masks, it doesn't load them. This note is kept for the reasoning trail and in case external-mask-import is ever reintroduced.

## Decision (historical)
When a user loaded a mask PNG (or `.bacmask` bundle whose mask differed from the current image) with `(H, W)` not matching the currently loaded image:

1. Show a modal dialog with both dimensions, e.g.:
   > "Mask size **3000 × 4000** does not match image size **2048 × 2048**. Load anyway?"
2. **Default button: Reject.**
3. Secondary button: **Resize to fit (nearest-neighbor, lossy)** — with a warning label attached.

## Why prompt rather than silent reject
The user explicitly asked for a prompt-with-rejection-default — leaves an out for the rare case where they know the resize is intentional (e.g. downsampled workflow) without creating a trap.

## Why reject by default
- Labels are discrete integers. Any non-nearest-neighbor resize silently corrupts them.
- Even nearest-neighbor can split thin regions or merge adjacent ones.
- Silently proceeding would corrupt training data without warning.

## Why offer the lossy path at all
Occasional power-user need. Gating it behind a non-default button with a visible warning is the right trade-off.

## Implementation notes
- Resize uses `cv2.resize(..., interpolation=cv2.INTER_NEAREST)`.
- After resize, log at `WARNING` level with old/new dims ([007](../007-logging.md)).
- Sets the `dirty` flag — user must explicitly save if they want the resized result persisted.
- The bundle's `meta.json` vertex lists are also resized proportionally and a warning is added to the bundle's next-save audit trail (post-MVP).

## Related
- [012 — 16-bit PNG Label Maps](012-png-label-maps.md).
